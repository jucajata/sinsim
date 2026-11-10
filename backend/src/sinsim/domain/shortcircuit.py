"""Reglas puras del cortocircuito IEC 60909 (spec 004: FR-063, FR-064, FR-065, FR-073).

Sin pandapower ni E/S (constitución IV). Aquí viven: las reglas de parámetros faltantes de las
unidades síncronas (FR-064, S27, S28), la propuesta de equivalencias unidad ↔ transformador
elevador (research R4), la corrección a la tensión nominal de PARATEC (S26), la relación X/R, el
resumen y el hash de configuración. Las conversiones de unidades (pu → Ω) están en
`adapters/sources_to_pandapower/generators.py` (constitución III.1).
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date
from typing import Any

import pandas as pd

from sinsim.domain.entities import (
    ScAssumption,
    ScBusResult,
    ScExtreme,
    ScImputed,
    ScMethod,
    ScQuality,
    ScSource,
    ScSummary,
    StepUpEquivalence,
    StepUpMethod,
)

SYNC_TECHS = ("hidráulica", "térmica")
CONVERTER_TECHS = ("solar", "eólica")
MACHINE_PARAMS = ("sn_mva", "cos_phi", "xdss_pu", "rdss_pu")
SDL_MAX_KV = 57.5
"""Un devanado por debajo de este nivel identifica un transformador elevador (S1)."""
LV_TOLERANCE_KV = 0.2
"""Tolerancia para casar la tensión de baja del elevador con `ratedU` (research R4)."""
LARGE_MACHINE_MVA = 100.0
LV_MACHINE_KV = 1.0


# --- Parámetros de las unidades síncronas (FR-064) --------------------------------------------


@dataclass(frozen=True)
class RgRatios:
    """Relaciones R_G/X''_d de IEC 60909-0 §6.6.1 (S28), desde la configuración."""

    large: float
    small: float
    lv: float

    def for_machine(self, sn_mva: float, vn_kv: float) -> float:
        """Relación aplicable según tamaño y tensión de la máquina."""
        if vn_kv <= LV_MACHINE_KV:
            return self.lv
        return self.large if sn_mva >= LARGE_MACHINE_MVA else self.small


@dataclass(frozen=True)
class SourceParams:
    """Parámetros resueltos de una unidad síncrona con el origen de cada uno."""

    sn_mva: float
    vn_kv: float
    cos_phi: float
    xdss_pu: float
    rdss_pu: float
    origins: dict[str, ScMethod]
    imputed: list[ScImputed] = field(default_factory=list)


def _positive(value: object) -> float | None:
    try:
        v = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return v if v == v and v > 0 else None  # excluye NaN y ceros


def medians_by_tech(units: pd.DataFrame) -> dict[str, dict[str, float]]:
    """Medianas por tecnología de los parámetros publicados (> 0), para imputar (FR-064)."""
    out: dict[str, dict[str, float]] = {}
    if units.empty:
        return out
    for tech, group in units.groupby("tech"):
        meds: dict[str, float] = {}
        for col in MACHINE_PARAMS:
            if col not in group.columns:
                continue
            vals = pd.to_numeric(group[col], errors="coerce")
            vals = vals[vals > 0]
            if not vals.empty:
                meds[col] = float(vals.median())
        out[str(tech)] = meds
    return out


def source_parameters(
    unit: Mapping[str, Any],
    medians: Mapping[str, Mapping[str, float]],
    *,
    step_up_lv_kv: float | None,
    bus_kv: float,
    rg: RgRatios,
) -> SourceParams | None:
    """Resuelve los parámetros de una unidad síncrona (FR-064, S27, S28).

    Reglas, en orden y siempre con su origen:
    - `sn_mva`: publicado; si falta, `p_max_mw / cos_phi` (`derivado_p_cosphi`); si tampoco,
      mediana de la tecnología (`mediana`).
    - `cos_phi` y `xdss_pu`: publicado o mediana de la tecnología.
    - `vn_kv`: la tensión de baja del elevador casado manda (`tension_elevador`, registrada
      como imputación si difiere de `ratedU` o este falta); sin elevador, la tensión de la
      barra de alta (`tension_barra`), porque la máquina se conecta ahí directamente (S31).
    - `rdss_pu`: publicado > 0; si falta o es 0, `R_G/X''_d` de IEC 60909 (`relacion_iec`).

    Returns:
        `None` si no hay forma de obtener `sn_mva`, `cos_phi` o `xdss_pu` (la unidad se excluye).
    """
    unit_id = str(unit["unit_id"])
    tech = str(unit.get("tech", ""))
    meds = medians.get(tech, {})
    origins: dict[str, ScMethod] = {}
    imputed: list[ScImputed] = []

    def record(param: str, value: float, method: ScMethod) -> float:
        origins[param] = method
        if method != "publicado":
            imputed.append(ScImputed(unit_id=unit_id, parameter=param, value=value, method=method))
        return value

    cos_phi = _positive(unit.get("cos_phi"))
    if cos_phi is not None and cos_phi <= 1.0:
        cos_phi = record("cos_phi", cos_phi, "publicado")
    elif "cos_phi" in meds:
        cos_phi = record("cos_phi", meds["cos_phi"], "mediana")
    else:
        return None

    sn = _positive(unit.get("sn_mva"))
    p_max = _positive(unit.get("p_max_mw"))
    if sn is not None:
        sn = record("sn_mva", sn, "publicado")
    elif p_max is not None:
        sn = record("sn_mva", p_max / cos_phi, "derivado_p_cosphi")
    elif "sn_mva" in meds:
        sn = record("sn_mva", meds["sn_mva"], "mediana")
    else:
        return None

    xdss = _positive(unit.get("xdss_pu"))
    if xdss is not None:
        xdss = record("xdss_pu", xdss, "publicado")
    elif "xdss_pu" in meds:
        xdss = record("xdss_pu", meds["xdss_pu"], "mediana")
    else:
        return None

    rated_u = _positive(unit.get("vn_gen_kv"))
    if step_up_lv_kv is not None:
        if rated_u is not None and abs(rated_u - step_up_lv_kv) <= LV_TOLERANCE_KV:
            vn = record("vn_kv", step_up_lv_kv, "publicado")
        else:
            vn = record("vn_kv", step_up_lv_kv, "tension_elevador")
    else:
        # Sin elevador la máquina se conecta directamente a la barra de alta (FR-065 c, S31):
        # pandapower refiere Z_G a `vn_kv`, así que debe ser la tensión de esa barra, nunca
        # `ratedU` (daría una impedancia de 13,8 kV en una barra de 230 kV).
        vn = record("vn_kv", bus_kv, "tension_barra")

    rdss = _positive(unit.get("rdss_pu"))
    if rdss is not None:
        rdss = record("rdss_pu", rdss, "publicado")
    else:
        rdss = record("rdss_pu", rg.for_machine(sn, vn) * xdss, "relacion_iec")

    return SourceParams(
        sn_mva=sn,
        vn_kv=vn,
        cos_phi=cos_phi,
        xdss_pu=xdss,
        rdss_pu=rdss,
        origins=origins,
        imputed=imputed,
    )


# --- Equivalencias unidad ↔ transformador elevador (FR-065, research R4) ----------------------

_RATING = re.compile(
    r"\d+(?:[.,]\d+)?\s*MVA\b|\(?\d+(?:[.,]\d+)?\)?(?:\s*/\s*\(?\d+(?:[.,]\d+)?\)?)+\s*KV\b",
    re.IGNORECASE,
)
"""Placa del transformador («162 MVA», «230/13.8 kV», «115/34.5/(13.2) kV»): no nombra unidades."""
_MARK = re.compile(r"\b[GU](\d+)\b")
HV_TOLERANCE = 0.12
"""El devanado de alta de un elevador suele estar por encima de la red (127 kV en una barra de
115 kV, que PARATEC clasifica como 138): basta con quedar a ±12 % de la clase de la barra."""
SHARE_MARGIN = 1.15
"""Un transformador se comparte solo si la suma de las unidades no pasa de 1,15 veces sus MVA."""


def normalize_name(text: object) -> str:
    """Mayúsculas sin tildes ni signos, con espacios simples, para comparar nombres."""
    s = unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode()
    return " ".join(re.sub(r"[^A-Z0-9 ]", " ", s.upper()).split())


def designation(name: object) -> str:
    """Nombre del transformador sin su placa, normalizado.

    «CHIVOR G8 162 MVA 230/13.8 kV» → «CHIVOR G8». Sin quitar la placa, el «8» de «13.8» parece el
    número de una unidad.
    """
    return normalize_name(_RATING.sub(" ", str(name or "")))


def plant_words(plant: object) -> list[str]:
    """Palabras de la planta que la identifican (3 letras o más, sin números)."""
    return [p for p in normalize_name(plant).split() if len(p) >= 3 and not p.isdigit()]


def _lv_windings(row: pd.Series) -> list[float]:
    out: list[float] = []
    for col in ("vn_mv_kv", "vn_lv_kv"):
        v = _positive(row.get(col))
        if v is not None and v < SDL_MAX_KV:
            out.append(v)
    return out


def unit_numbers(unit: object) -> list[int]:
    """Números con que el nombre de un transformador puede referirse a la unidad.

    Del más al menos directo: el suyo y, en plantas numeradas por series (GUADALUPE 31…36), su
    último dígito.
    """
    m = re.search(r"(\d+)\s*$", normalize_name(unit))
    if not m:
        return []
    n = int(m.group(1))
    return [n, n % 10] if n >= 10 and n % 10 else [n]


def _mark_rank(desig: str, numbers: list[int], three_winding: bool) -> float | None:
    """Qué tan directamente nombra el transformador a la unidad (menor es mejor), o `None`.

    0 marca G<n> exacta; 1 marca del último dígito; +0,5 marca compartida de tres devanados
    (G12 = unidades 1 y 2); +2 el número suelto en el nombre («CHIVOR 1»).
    """
    marks = _MARK.findall(desig)
    for rank, n in enumerate(numbers):
        if str(n) in marks:
            return float(rank)
        if three_winding and any(len(m) > 1 and str(n) in m for m in marks):
            return rank + 0.5
    for rank, n in enumerate(numbers):
        if re.search(rf"\b{n}\b", desig):
            return rank + 2.0
    return None


_CYCLE = ("GAS", "VAPOR")
"""En un ciclo combinado la unidad y su elevador dicen si son de la turbina de gas o de vapor."""


def _other_cycle(unit: object, desig: str) -> bool:
    """La unidad es de gas (o vapor) y el transformador está marcado para la otra turbina."""
    words = set(normalize_name(unit).split())
    mine = [c for c in _CYCLE if c in words]
    return bool(mine) and any(re.search(rf"\b{c}\b", desig) for c in _CYCLE if c not in mine)


def _marked_for_another(desig: str, numbers: list[int]) -> bool:
    """El transformador lleva marca G<n> de otra unidad (TERMOZIPA 2 G2 no es de ZIPAEMG 3)."""
    marks = _MARK.findall(desig)
    return bool(marks and numbers) and _mark_rank(desig, numbers, three_winding=True) is None


def _name_matches(desig: str, words: list[str]) -> bool:
    """Una palabra de la planta en el transformador.

    Las de 5 letras o más también cuentan dentro de un nombre compuesto (FLORES en «TERMOFLORES»).
    """
    return any(re.search(rf"\b{w}\b", desig) or (len(w) >= 5 and w in desig) for w in words)


def hv_matches(hv_kv: float | None, bus_kv: float, class_of: Callable[[float], float]) -> bool:
    """La alta del transformador corresponde a la barra de la unidad (misma clase o ±12 %)."""
    if hv_kv is None:
        return False
    bus_class = class_of(bus_kv)
    return class_of(hv_kv) == bus_class or abs(hv_kv / bus_class - 1) <= HV_TOLERANCE


def _voltage_matches(lv_windings: list[float], rated_u: float | None) -> bool:
    return rated_u is not None and any(abs(lv - rated_u) <= LV_TOLERANCE_KV for lv in lv_windings)


def unit_sn_mva(unit: pd.Series) -> float | None:
    """Potencia aparente de la unidad: la publicada o P máx / 0,9."""
    sn = _positive(unit.get("sn_mva"))
    if sn is not None:
        return sn
    p = _positive(unit.get("p_max_mw"))
    return p / 0.9 if p is not None else None


def _trafo_sn(row: pd.Series) -> float | None:
    vals = [_positive(row.get(c)) for c in ("sn_mva", "sn_hv_mva", "sn_mv_mva", "sn_lv_mva")]
    known = [v for v in vals if v is not None]
    return max(known) if known else None


def propose_step_ups(
    units: pd.DataFrame,
    trafos2w: pd.DataFrame,
    trafos3w: pd.DataFrame,
    *,
    aliases: Mapping[str, str],
    class_of: Callable[[float], float],
    valid_from: date,
) -> list[StepUpEquivalence]:
    """Propuesta inicial de `elevadores.csv` (research R4), marcada `curated = false`.

    Candidatos: transformadores de la misma subestación (con alias) cuya tensión de alta es de
    la clase de la barra de la unidad (`class_of`: 220 ≡ 230, 110 ≡ 115; o a ±12 %) y con algún
    devanado por debajo de 57,5 kV. Método: `nombre+tension` (una palabra de la planta en el
    transformador **y** devanado de baja igual a `ratedU` ± 0,2 kV), `nombre`, `marca+tension`
    (sin la planta en el nombre, pero con la marca G<n> de la unidad y su tensión de baja: PARATEC
    nombra muchos elevadores por la subestación, «ANTIOQUIA G1» para ITUANGO 1) o `tension` (solo
    si no hay otro criterio y hay un único candidato por tensión). Entre candidatos gana el
    que nombra a la unidad (`_mark_rank`), y cada transformador recibe unidades mientras sus MVA
    alcancen (`SHARE_MARGIN`); si ninguno alcanza, la unidad comparte el mejor. Sin coincidencia ⇒
    sin equivalencia.
    """
    if units.empty:
        return []

    def canon(sub: object) -> str:
        s = str(sub or "")
        return aliases.get(s, s)

    frames = []
    for df, kind in ((trafos2w, "2w"), (trafos3w, "3w")):
        if not df.empty:
            part = df.copy()
            part["_kind"] = kind
            frames.append(part)
    if not frames:
        return []
    trafos = pd.concat(frames, ignore_index=True, sort=False)
    trafos["_sub"] = trafos["substation"].map(canon)
    trafos["_hv"] = pd.to_numeric(trafos["vn_hv_kv"], errors="coerce")
    trafos["_lv"] = trafos.apply(_lv_windings, axis=1)
    trafos["_desig"] = trafos["name"].map(designation)
    trafos = trafos[trafos["_lv"].map(len) > 0]

    # Candidatos de cada unidad, ordenados del mejor al peor.
    plans: list[tuple[tuple[float, str], pd.Series, StepUpMethod, list[pd.Series]]] = []
    sync = units[units["tech"].isin(SYNC_TECHS)]
    for _, u in sync.iterrows():
        bus_kv = _positive(u.get("vn_kv"))
        if bus_kv is None or not isinstance(u.get("substation"), str):
            continue
        sub = canon(u["substation"])
        cand = trafos[trafos["_sub"] == sub]
        cand = cand[[hv_matches(_positive(v), bus_kv, class_of) for v in cand["_hv"]]]
        if cand.empty:
            continue
        words = plant_words(u.get("plant"))
        rated_u = _positive(u.get("vn_gen_kv"))
        numbers = unit_numbers(u.get("unit"))
        cand = cand[[not _other_cycle(u.get("unit"), d) for d in cand["_desig"]]]
        named = [r for _, r in cand.iterrows() if _name_matches(r["_desig"], words)]
        method: StepUpMethod
        if named:
            with_v = [r for r in named if _voltage_matches(r["_lv"], rated_u)]
            method = "nombre+tension" if with_v else "nombre"
            pool = with_v or named
        else:
            volts = [
                r
                for _, r in cand.iterrows()
                if _voltage_matches(r["_lv"], rated_u)
                and not _marked_for_another(r["_desig"], numbers)
            ]
            marked = [
                r
                for r in volts
                if (rank := _mark_rank(r["_desig"], numbers, r["_kind"] == "3w")) is not None
                and rank < 2
            ]
            if marked:
                method, pool = "marca+tension", marked
            elif len(volts) == 1:
                method, pool = "tension", volts
            else:
                continue

        def score(r: pd.Series, numbers: list[int] = numbers) -> tuple[float, str]:
            rank = _mark_rank(r["_desig"], numbers, r["_kind"] == "3w")
            return (9.0 if rank is None else rank, str(r["trafo_id"]))

        pool = sorted(pool, key=score)
        plans.append(((score(pool[0])[0], str(u["unit_id"])), u, method, pool))

    # Reparto: primero las unidades que su transformador nombra mejor; cada transformador recibe
    # unidades mientras sus MVA alcancen.
    used: dict[str, float] = {}
    count: dict[str, int] = {}
    out: list[StepUpEquivalence] = []
    for _, u, method, pool in sorted(plans, key=lambda p: p[0]):
        sn = unit_sn_mva(u)

        def fits(r: pd.Series, sn: float | None = sn) -> bool:
            tid = str(r["trafo_id"])
            cap = _trafo_sn(r)
            if not count.get(tid):
                return True
            if cap is None:
                return True
            if sn is None:
                return False
            return used.get(tid, 0.0) + sn <= SHARE_MARGIN * cap

        chosen = next((r for r in pool if fits(r)), pool[0])
        tid = str(chosen["trafo_id"])
        used[tid] = used.get(tid, 0.0) + (sn or 0.0)
        count[tid] = count.get(tid, 0) + 1
        out.append(
            StepUpEquivalence(
                unit_id=str(u["unit_id"]),
                trafo_id=tid,
                method=method,
                curated=False,
                valid_from=valid_from,
                note=f"propuesta automática ({chosen['_kind']})",
            )
        )
    order = {str(uid): i for i, uid in enumerate(sync["unit_id"])}
    return sorted(out, key=lambda e: order.get(e.unit_id, 0))


SINGLE_UNIT_MARGIN = 1.5
"""Una unidad sola puede pasar los MVA de su elevador (se dimensiona por P); más de 1,5 veces no."""


def _row_of(df: pd.DataFrame | None, key: str) -> pd.Series | None:
    """Fila de `df` por índice (la primera si se repite), o `None`."""
    if df is None or key not in df.index:
        return None
    row = df.loc[key]
    return row.iloc[0] if isinstance(row, pd.DataFrame) else row


@dataclass(frozen=True)
class StepUpCheck:
    """Chequeo de coherencia de una fila de `elevadores.csv` contra PARATEC."""

    unit_id: str
    trafo_id: str
    method: str
    curated: bool
    issues: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.issues


def review_step_ups(
    rows: Iterable[Any],
    units: pd.DataFrame,
    trafos2w: pd.DataFrame,
    trafos3w: pd.DataFrame,
    *,
    aliases: Mapping[str, str],
    class_of: Callable[[float], float],
) -> list[StepUpCheck]:
    """Revisa cada fila (`unit_id`, `trafo_id`, `method`, `curated`) con datos de PARATEC solamente.

    Chequea que el transformador nombre a la planta o a la unidad, que su devanado de baja sea la
    tensión de la unidad, que su alta sea la clase de la barra, que esté en la misma subestación,
    que sus MVA alcancen para las unidades que lo comparten y que no lleve la marca de otra unidad.
    Una fila sin problemas no queda curada por eso: el chequeo solo prioriza qué revisar a mano.
    """

    def canon(sub: object) -> str:
        s = str(sub or "")
        return aliases.get(s, s)

    rows = list(rows)
    by_unit = units.set_index("unit_id") if not units.empty else units
    frames = [df for df in (trafos2w, trafos3w) if not df.empty]
    trafos = (
        pd.concat(frames, ignore_index=True, sort=False).set_index("trafo_id") if frames else None
    )
    sharing: dict[str, list[str]] = {}
    for r in rows:
        sharing.setdefault(r.trafo_id, []).append(r.unit_id)

    out: list[StepUpCheck] = []
    for r in rows:
        issues: list[str] = []
        unit = _row_of(by_unit, r.unit_id)
        trafo = _row_of(trafos, r.trafo_id)
        if unit is None:
            issues.append("unidad: no está en el snapshot")
        if trafo is None:
            issues.append("transformador: no está en el snapshot")
        if unit is not None and trafo is not None:
            desig = designation(trafo.get("name"))
            numbers = unit_numbers(unit.get("unit"))
            rank = _mark_rank(
                desig, numbers, three_winding=_positive(trafo.get("vn_mv_kv")) is not None
            )
            rated_u = _positive(unit.get("vn_gen_kv"))
            lv = _lv_windings(trafo)
            # La marca de la unidad sustituye al nombre de la planta solo con la tensión de baja
            # correcta, como en la propuesta (`marca+tension`).
            marked = rank is not None and rank < 2 and _voltage_matches(lv, rated_u)
            if not _name_matches(desig, plant_words(unit.get("plant"))) and not marked:
                issues.append(
                    f"nombre: ni «{unit.get('plant')}» ni la marca de la unidad están "
                    "en el transformador"
                )
            if _marked_for_another(desig, numbers):
                issues.append("marca: el transformador lleva la marca de otra unidad")
            if _other_cycle(unit.get("unit"), desig):
                issues.append(
                    "ciclo: la unidad y el transformador son de turbinas distintas (gas/vapor)"
                )
            if rated_u is None:
                issues.append("baja: la unidad no publica su tensión nominal")
            elif not any(abs(v - rated_u) <= max(LV_TOLERANCE_KV, 0.05 * rated_u) for v in lv):
                issues.append(
                    f"baja: la unidad es de {rated_u:g} kV y el transformador de "
                    f"{'/'.join(f'{v:g}' for v in lv)} kV"
                )
            bus_kv, hv = _positive(unit.get("vn_kv")), _positive(trafo.get("vn_hv_kv"))
            if bus_kv is not None and hv is not None and not hv_matches(hv, bus_kv, class_of):
                issues.append(f"alta: el transformador es de {hv:g} kV y la barra de {bus_kv:g} kV")
            if canon(trafo.get("substation")) != canon(unit.get("substation")):
                issues.append(f"subestación: {trafo.get('substation')} y {unit.get('substation')}")
            cap = _trafo_sn(trafo)
            peers = sharing[r.trafo_id]
            sns = [
                unit_sn_mva(p_row) if (p_row := _row_of(by_unit, p)) is not None else None
                for p in peers
            ]
            known = [v for v in sns if v is not None]
            margin = SHARE_MARGIN if len(peers) > 1 else SINGLE_UNIT_MARGIN
            if cap is not None and len(known) == len(sns) and sum(known) > margin * cap:
                issues.append(
                    f"capacidad: {len(peers)} unidad(es) suman {sum(known):.0f} MVA "
                    f"y el transformador tiene {cap:g}"
                )
        out.append(
            StepUpCheck(
                unit_id=r.unit_id,
                trafo_id=r.trafo_id,
                method=str(r.method),
                curated=bool(r.curated),
                issues=tuple(issues),
            )
        )
    return out


# --- Resultados por barra (FR-063, S26) ----------------------------------------------------


def to_nominal(
    ikss_ka: float, skss_mva: float, base_kv: float, nominal_kv: float
) -> tuple[float, float]:
    """Refiere Ikss y Sk de la base por clase del modelo a la tensión nominal de PARATEC (S26).

    Para una misma impedancia de Thevenin, `Ikss = c·U_n/(√3·Z)` es proporcional a U_n y
    `Sk = √3·U_n·Ikss` a U_n²: una barra de 220 kV calculada en base 230 kV tiene 4,3 % menos
    corriente y 8,5 % menos potencia que lo que reporta pandapower. Rk y Xk en Ω no cambian.
    """
    if base_kv <= 0 or nominal_kv <= 0:
        return ikss_ka, skss_mva
    ratio = nominal_kv / base_kv
    return ikss_ka * ratio, skss_mva * ratio**2


def x_over_r(rk_ohm: float | None, xk_ohm: float | None) -> float | None:
    """Relación X/R; `None` si no hay impedancia o la resistencia es nula."""
    if rk_ohm is None or xk_ohm is None or rk_ohm <= 0:
        return None
    return xk_ohm / rk_ohm


def summarize(
    buses: Iterable[ScBusResult],
    sources: Iterable[ScSource],
    quality: ScQuality,
    *,
    duration_s: float,
) -> ScSummary:
    """Resumen del cálculo (data-model §7)."""
    bus_list = list(buses)
    src_list = list(sources)
    with_source = [b for b in bus_list if not b.no_source]
    max_ikss = max(with_source, key=lambda b: b.ikss_ka, default=None)
    min_skss = min(with_source, key=lambda b: b.skss_mva, default=None)
    return ScSummary(
        n_buses=len(bus_list),
        max_ikss=ScExtreme(bus_id=max_ikss.bus_id, value=max_ikss.ikss_ka) if max_ikss else None,
        min_skss=ScExtreme(bus_id=min_skss.bus_id, value=min_skss.skss_mva) if min_skss else None,
        n_sources_sync=sum(1 for s in src_list if s.kind == "sincrona"),
        n_sources_converter=sum(1 for s in src_list if s.kind == "convertidor"),
        n_imputed_units=len({i.unit_id for i in quality.imputed}),
        n_without_step_up=len(quality.generators_without_step_up),
        n_no_source=sum(1 for b in bus_list if b.no_source),
        duration_s=duration_s,
    )


def config_hash(config: Mapping[str, Any], equivalences_sha256: str, units_sha256: str) -> str:
    """Hash de todo lo que, además del caso, determina el resultado (FR-071)."""
    payload = json.dumps(
        {"config": dict(config), "equivalences": equivalences_sha256, "units": units_sha256},
        sort_keys=True,
        ensure_ascii=False,
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def units_sha256(units: pd.DataFrame) -> str:
    """Hash de los parámetros de máquina de las unidades, en orden de `unit_id`."""
    cols = [
        c
        for c in (
            "unit_id",
            "tech",
            "state",
            "bus",
            "p_max_mw",
            "sn_mva",
            "vn_gen_kv",
            "cos_phi",
            "xdss_pu",
            "rdss_pu",
        )
        if c in units.columns
    ]
    if units.empty:
        return hashlib.sha256(b"").hexdigest()
    text = units[cols].sort_values("unit_id").to_csv(index=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def assumptions(config: Mapping[str, Any]) -> list[ScAssumption]:
    """Supuestos S26 a S31 con su texto y su fuente (FR-072)."""
    return [
        ScAssumption(
            id="S26",
            text="Los resultados se refieren a la tensión nominal de PARATEC de cada barra, "
            "no a la base por clase del modelo (S14).",
            source=str(config.get("voltage_reference_source", "")),
        ),
        ScAssumption(
            id="S27",
            text="La reactancia subtransitoria usada es la no saturada; una resistencia de "
            "armadura o una reactancia publicadas como 0 se tratan como no publicadas.",
            source="Decisión del agente, 2026-10-25 (specs/004-cortocircuito/).",
        ),
        ScAssumption(
            id="S28",
            text="Resistencia de armadura no publicada: relación R_G/X''_d de IEC 60909-0 "
            "§6.6.1 por tamaño y tensión de la máquina.",
            source=str(config.get("rg_ratio_source", "")),
        ),
        ScAssumption(
            id="S29",
            text="Los enlaces internacionales no aportan corriente de cortocircuito; la "
            "corriente en Nariño y Norte de Santander queda subestimada.",
            source=str(config.get("international_links_source", "")),
        ),
        ScAssumption(
            id="S30",
            text="Las plantas solares y eólicas aportan k veces su corriente nominal como "
            "fuentes de convertidor pleno.",
            source=str(config.get("converter_k_source", "")),
        ),
        ScAssumption(
            id="S31",
            text="Las unidades sin transformador elevador casado entran en su barra de alta "
            "despreciando la reactancia del elevador, lo que sobreestima la corriente cerca de "
            "ellas; quedan listadas para curar `elevadores.csv`.",
            source="Decisión del usuario, 2026-10-25 (specs/004-cortocircuito/).",
        ),
    ]


__all__ = [
    "CONVERTER_TECHS",
    "MACHINE_PARAMS",
    "SDL_MAX_KV",
    "SYNC_TECHS",
    "RgRatios",
    "SourceParams",
    "assumptions",
    "config_hash",
    "medians_by_tech",
    "normalize_name",
    "propose_step_ups",
    "source_parameters",
    "summarize",
    "to_nominal",
    "units_sha256",
    "x_over_r",
]

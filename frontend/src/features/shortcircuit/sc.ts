import type { CSSProperties } from "react";

import type { ScBusResult, ScMethod } from "../../api/types";
import { fmtNum } from "../../lib/format";

/** Corriente en kA con dos decimales: «35,87 kA». */
export const formatKa = (v: number): string => `${fmtNum(v, 2)} kA`;

/** Potencia de cortocircuito en MVA sin decimales: «14.939 MVA». */
export const formatMva = (v: number): string => `${fmtNum(v, 0)} MVA`;

/** Impedancia en Ω con tres decimales: «0,254 Ω». */
export const formatOhm = (v: number | null): string => (v === null ? "—" : `${fmtNum(v, 3)} Ω`);

/** Relación X/R con dos decimales; «—» sin resistencia. */
export const formatXr = (v: number | null): string => (v === null ? "—" : fmtNum(v, 2));

/** Tensión nominal de PARATEC: «220 kV». */
export const formatKv = (v: number): string => `${fmtNum(v, v % 1 === 0 ? 0 : 1)} kV`;

/** Duración del cálculo: «4,9 s». */
export const formatDuration = (s: number): string => `${fmtNum(s, 1)} s`;

/** Textos en español de los orígenes de un parámetro (FR-073). */
export const METHOD_LABELS: Record<ScMethod, string> = {
  publicado: "publicado por PARATEC",
  mediana: "mediana de la tecnología",
  relacion_iec: "relación R/X de IEC 60909",
  derivado_p_cosphi: "derivado de P y cos φ",
  tension_elevador: "tensión de baja del elevador",
  tension_barra: "tensión de la barra de alta",
};

export const methodLabel = (m: ScMethod): string => METHOD_LABELS[m] ?? m;

/** Nombre legible de una unidad: «hidráulica:GUATAPE 1» → «GUATAPE 1 (hidráulica)». */
export function unitLabel(unitId: string): string {
  const i = unitId.indexOf(":");
  return i < 0 ? unitId : `${unitId.slice(i + 1)} (${unitId.slice(0, i)})`;
}

// --- Color por intensidad (HU-9, hallazgo A1): de 0 kA al máximo del caso ----------------------

const RED = "220, 38, 38";
const MIN_ALPHA = 0.08;
const MAX_ALPHA = 0.85;

/** Más corriente, más rojo; la intensidad va de 0 kA al máximo Ikss del caso. Gris sin fuente. */
export function ikssStyle(ikss: number, maxIkss: number, noSource = false): CSSProperties {
  if (noSource) return { background: "rgba(118, 123, 128, 0.25)", color: undefined };
  const t = maxIkss > 0 ? Math.min(1, Math.max(0, ikss / maxIkss)) : 0;
  const alpha = MIN_ALPHA + (MAX_ALPHA - MIN_ALPHA) * t;
  return { background: `rgba(${RED}, ${alpha.toFixed(2)})`, color: alpha >= 0.5 ? "#fff" : undefined };
}

/** Máximo Ikss del caso entre las barras con fuente; 0 si no hay. */
export function maxIkss(buses: ScBusResult[]): number {
  return buses.reduce((m, b) => (b.no_source ? m : Math.max(m, b.ikss_ka)), 0);
}

// --- Orden y búsqueda de la tabla -----------------------------------------------------------

export type ScColumn = "bus_id" | "nominal_kv" | "ikss_ka" | "skss_mva" | "x_r" | "rk_ohm" | "xk_ohm";
export type SortDir = "asc" | "desc";

function value(b: ScBusResult, column: ScColumn): string | number | null {
  return b[column];
}

/** Ordena sin mutar; los nulos (sin fuente) van siempre al final. */
export function sortBuses(buses: ScBusResult[], column: ScColumn, dir: SortDir): ScBusResult[] {
  const sign = dir === "asc" ? 1 : -1;
  return [...buses].sort((a, b) => {
    const va = value(a, column);
    const vb = value(b, column);
    if (va === null && vb === null) return a.bus_id.localeCompare(b.bus_id);
    if (va === null) return 1;
    if (vb === null) return -1;
    if (typeof va === "string" && typeof vb === "string") return sign * va.localeCompare(vb, "es");
    return sign * (Number(va) - Number(vb));
  });
}

/** Filtra por texto (sin distinguir mayúsculas ni tildes) en el nombre de la barra y su subárea. */
export function filterBuses(buses: ScBusResult[], text: string): ScBusResult[] {
  const q = normalize(text);
  if (!q) return buses;
  return buses.filter((b) => normalize(b.bus_id).includes(q) || normalize(b.subarea ?? "").includes(q));
}

function normalize(s: string): string {
  return s
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .trim();
}

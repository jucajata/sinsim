import { useMemo, useState } from "react";

import { ProblemError } from "../../api/client";
import { useCalculateSc, useSc } from "../../api/hooks";
import type { Run, ScQuality, ShortCircuitAnalysis } from "../../api/types";
import { fmtNum } from "../../lib/format";
import {
  type ScColumn,
  type SortDir,
  filterBuses,
  formatDuration,
  formatKa,
  formatKv,
  formatMva,
  formatOhm,
  formatXr,
  ikssStyle,
  maxIkss,
  methodLabel,
  sortBuses,
  unitLabel,
} from "./sc";

interface Props {
  run: Run;
}

function Kpi({ label, value, testId }: { label: string; value: string; testId?: string }): JSX.Element {
  return (
    <div className="kpi">
      <span className="kpi__label">{label}</span>
      <span className="kpi__value" data-testid={testId}>
        {value}
      </span>
    </div>
  );
}

const COLUMNS: { key: ScColumn; label: string; num: boolean }[] = [
  { key: "bus_id", label: "Barra", num: false },
  { key: "nominal_kv", label: "kV nominal", num: true },
  { key: "ikss_ka", label: "Ikss", num: true },
  { key: "skss_mva", label: "Sk", num: true },
  { key: "x_r", label: "X/R", num: true },
  { key: "rk_ohm", label: "Rk", num: true },
  { key: "xk_ohm", label: "Xk", num: true },
];

function BusTable({ analysis }: { analysis: ShortCircuitAnalysis }): JSX.Element {
  const [column, setColumn] = useState<ScColumn>("ikss_ka");
  const [dir, setDir] = useState<SortDir>("desc");
  const [text, setText] = useState("");
  const max = useMemo(() => maxIkss(analysis.buses), [analysis.buses]);
  const rows = useMemo(() => sortBuses(filterBuses(analysis.buses, text), column, dir), [analysis.buses, text, column, dir]);

  function sortBy(key: ScColumn): void {
    if (key === column) setDir(dir === "asc" ? "desc" : "asc");
    else {
      setColumn(key);
      setDir(key === "bus_id" ? "asc" : "desc");
    }
  }

  return (
    <div className="sc__table" data-testid="sc-table">
      <div className="sc__bar">
        <h3>Barras</h3>
        <span className="muted small">Más corriente, más rojo (pleno en el máximo del caso). Referido a la tensión nominal de PARATEC (S26).</span>
        <span className="spacer" />
        <input
          type="search"
          className="input"
          placeholder="Buscar barra o subárea…"
          value={text}
          onChange={(e) => setText(e.target.value)}
          data-testid="sc-search"
          aria-label="Buscar barra"
        />
      </div>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              {COLUMNS.map((c) => (
                <th key={c.key} className={c.num ? "num sortable" : "sortable"} onClick={() => sortBy(c.key)} aria-sort={column === c.key ? (dir === "asc" ? "ascending" : "descending") : "none"}>
                  {c.label}
                  {column === c.key ? (dir === "asc" ? " ▲" : " ▼") : ""}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((b) => (
              <tr key={b.bus_id} title={b.no_source ? "sin camino a ninguna fuente" : `base del modelo ${formatKv(b.base_kv)}${b.subarea ? ` · ${b.subarea}` : ""}`}>
                <td>{b.bus_id}</td>
                <td className="num">{formatKv(b.nominal_kv)}</td>
                <td className="num" style={ikssStyle(b.ikss_ka, max, b.no_source)}>
                  <strong>{b.no_source ? "sin fuente" : formatKa(b.ikss_ka)}</strong>
                </td>
                <td className="num">{b.no_source ? "—" : formatMva(b.skss_mva)}</td>
                <td className="num">{formatXr(b.x_r)}</td>
                <td className="num">{formatOhm(b.rk_ohm)}</td>
                <td className="num">{formatOhm(b.xk_ohm)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {rows.length === 0 && <p className="muted">Ninguna barra coincide con la búsqueda.</p>}
    </div>
  );
}

function QualityBlock({ quality, analysis }: { quality: ScQuality; analysis: ShortCircuitAnalysis }): JSX.Element {
  const busOf = useMemo(() => new Map(analysis.sources.map((s) => [s.unit_id, s.bus_id])), [analysis.sources]);
  const eq = quality.step_up_equivalences;
  return (
    <details className="section" data-testid="sc-quality">
      <summary>
        Calidad e imputaciones <span className="count">{quality.imputed.length + quality.generators_without_step_up.length + quality.sc_zero_sources.length + quality.excluded.length}</span>
      </summary>
      <p className="muted small">
        Elevadores casados: {eq.matched} ({eq.uncurated} sin curar
        {Object.entries(eq.by_method)
          .map(([m, n]) => `; ${m}: ${n}`)
          .join("")}
        ). Cada parámetro que no publica PARATEC se imputa de forma visible (constitución III.5).
      </p>
      <div className="sc__quality">
        <details open={quality.imputed.length > 0}>
          <summary>
            Imputados <span className="count">{quality.imputed.length}</span>
          </summary>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Unidad</th>
                  <th>Parámetro</th>
                  <th className="num">Valor</th>
                  <th>Método</th>
                </tr>
              </thead>
              <tbody>
                {quality.imputed.map((i) => (
                  <tr key={`${i.unit_id}:${i.parameter}`}>
                    <td>{unitLabel(i.unit_id)}</td>
                    <td>{i.parameter}</td>
                    <td className="num">{fmtNum(i.value, 4)}</td>
                    <td>{methodLabel(i.method)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
        <details>
          <summary>
            Sin elevador <span className="count">{quality.generators_without_step_up.length}</span>
          </summary>
          <p className="muted small">Entran en su barra de alta despreciando la reactancia del elevador (S31); cura `elevadores.csv` para incluirlos.</p>
          <ul className="small">
            {quality.generators_without_step_up.map((u) => (
              <li key={u}>
                {unitLabel(u)} → {busOf.get(u) ?? "—"}
              </li>
            ))}
          </ul>
        </details>
        <details>
          <summary>
            Sin aporte <span className="count">{quality.sc_zero_sources.length}</span>
          </summary>
          <ul className="small">
            {quality.sc_zero_sources.map((z) => (
              <li key={z.resource}>
                {z.resource} en {z.bus_id}: {z.reason}
              </li>
            ))}
          </ul>
        </details>
        <details>
          <summary>
            Excluidos <span className="count">{quality.excluded.length}</span>
          </summary>
          <ul className="small">
            {quality.excluded.map((e) => (
              <li key={e.unit_id}>
                {e.unit_id}: {e.reason}
              </li>
            ))}
          </ul>
        </details>
      </div>
      <details>
        <summary>Supuestos aplicados (S26 a S31)</summary>
        <ul className="small">
          {analysis.assumptions.map((a) => (
            <li key={a.id}>
              <strong>{a.id}</strong>: {a.text} <span className="muted">— {a.source}</span>
            </li>
          ))}
        </ul>
      </details>
    </details>
  );
}

function AnalysisView({ analysis }: { analysis: ShortCircuitAnalysis }): JSX.Element {
  const s = analysis.summary;
  const t = analysis.trace;
  return (
    <>
      <div className="kpis" data-testid="sc-summary">
        <Kpi label="Barras" value={String(s.n_buses)} testId="sc-buses" />
        <Kpi label="Mayor Ikss" value={s.max_ikss ? `${formatKa(s.max_ikss.value)} · ${s.max_ikss.bus_id}` : "—"} testId="sc-max" />
        <Kpi label="Menor Sk" value={s.min_skss ? `${formatMva(s.min_skss.value)} · ${s.min_skss.bus_id}` : "—"} />
        <Kpi label="Fuentes" value={`${s.n_sources_sync} síncronas · ${s.n_sources_converter} convertidores`} />
        <Kpi label="Con imputaciones" value={String(s.n_imputed_units)} />
        <Kpi label="Sin elevador" value={String(s.n_without_step_up)} />
        <Kpi label="Duración" value={formatDuration(s.duration_s)} />
      </div>
      <p className="trace small muted" data-testid="sc-trace">
        {analysis.norm.standard} · falla trifásica máxima · c = {fmtNum(analysis.norm.c_max, 2)} · snapshot <code>{t.snapshot_date}</code> · pandapower <code>{t.pandapower_version}</code> · caso{" "}
        <code>{analysis.case_id.slice(0, 12)}…</code> · {new Date(analysis.calculated_at).toLocaleString("es-CO")}
      </p>
      <BusTable analysis={analysis} />
      <QualityBlock quality={analysis.quality} analysis={analysis} />
    </>
  );
}

/** Cortocircuito IEC 60909 (HU-9, HU-11): botón, resumen, tabla por barra y calidad. */
export function ScPanel({ run }: Props): JSX.Element {
  const saved = useSc(run.run_id);
  const calculate = useCalculateSc();
  const analysis = calculate.data ?? saved.data ?? null;
  const running = calculate.isPending;
  const error = calculate.error instanceof ProblemError ? calculate.error.problem.user_message : calculate.error ? "Ocurrió un error no previsto." : null;

  return (
    <section className="sc card card--padded stack" data-testid="sc">
      <div className="sc__bar">
        <h2>Cortocircuito</h2>
        <span className="muted small">IEC 60909, trifásico máximo, red completa y toda la generación en servicio. No depende del flujo.</span>
        <span className="spacer" />
        <button type="button" className="button" onClick={() => calculate.mutate(run.run_id)} disabled={running} data-testid="sc-start">
          {running ? "Calculando…" : analysis ? "Recalcular" : "Cortocircuito"}
        </button>
      </div>
      {running && (
        <p className="muted" data-testid="sc-progress">
          Calculando el cortocircuito de todas las barras…
        </p>
      )}
      {error && (
        <p className="notice notice--error" role="alert" data-testid="sc-error">
          {error}
        </p>
      )}
      {saved.isLoading && !analysis && <p className="muted small">Buscando un cálculo guardado…</p>}
      {analysis && <AnalysisView analysis={analysis} />}
    </section>
  );
}

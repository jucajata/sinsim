import { useState } from "react";

import { ProblemError } from "../../api/client";
import { useN1Job, useStartN1 } from "../../api/hooks";
import type { Isolation, IsolationRow, LoadingRow, N1Analysis, Outage, Run, UnsolvedRow, VoltageRow } from "../../api/types";
import { fmtNum } from "../../lib/format";
import { KIND_LABELS, fmtDeviation, fmtDuration, fmtLoading, fmtVm, isRunning, isolationText, outageLabel, progressText } from "./n1";

interface Props {
  run: Run;
}

function Kpi({ label, value, alert = false, testId }: { label: string; value: string; alert?: boolean; testId?: string }): JSX.Element {
  return (
    <div className="kpi">
      <span className="kpi__label">{label}</span>
      <span className={alert ? "kpi__value kpi__value--alert" : "kpi__value"} data-testid={testId}>
        {value}
      </span>
    </div>
  );
}

function OutageCell({ outage, isolation = null }: { outage: Outage; isolation?: Isolation | null }): JSX.Element {
  return (
    <td>
      <span className="chip chip--outline">{KIND_LABELS[outage.kind]}</span> {outageLabel(outage.element_id)}
      {outage.angle_ref_moved_to && <div className="muted small">referencia de ángulo → {outage.angle_ref_moved_to}</div>}
      {isolation && <div className="muted small">{isolationText(isolation)}</div>}
    </td>
  );
}

function LoadingList({ rows }: { rows: LoadingRow[] }): JSX.Element {
  return (
    <div className="n1__list" data-testid="n1-loading">
      <h3>
        Cargabilidad <span className={rows.length > 0 ? "count count--alert" : "count"}>{rows.length}</span>
      </h3>
      <p className="muted small">De mayor a menor cargabilidad provocada en cualquier línea o transformador.</p>
      {rows.length === 0 ? (
        <p className="muted">Ninguna contingencia empeora una cargabilidad por encima del límite.</p>
      ) : (
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th className="num">#</th>
                <th className="num">Con N-1</th>
                <th>Activo fuera</th>
                <th>Elemento más cargado</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.outage.element_id} title={`caso base ${fmtLoading(r.loading_base_percent)} · ${r.n_elements} elemento(s) cuentan`}>
                  <td className="num">{r.rank}</td>
                  <td className="num">
                    <strong>{fmtLoading(r.loading_percent)}</strong>
                  </td>
                  <OutageCell outage={r.outage} isolation={r.isolation} />
                  <td>{outageLabel(r.element_id)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function VoltageList({ rows }: { rows: VoltageRow[] }): JSX.Element {
  return (
    <div className="n1__list" data-testid="n1-voltage">
      <h3>
        Tensiones <span className={rows.length > 0 ? "count count--alert" : "count"}>{rows.length}</span>
      </h3>
      <p className="muted small">De mayor a menor distancia fuera de la banda de tensión, por debajo o por encima.</p>
      {rows.length === 0 ? (
        <p className="muted">Ninguna contingencia saca una barra de su banda más de lo que ya estaba.</p>
      ) : (
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th className="num">#</th>
                <th className="num">Fuera de banda</th>
                <th className="num">V (pu)</th>
                <th>Activo fuera</th>
                <th>Barra más afectada</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.outage.element_id} title={`caso base ${fmtVm(r.vm_base_pu)} · ${r.n_buses} barra(s) cuentan`}>
                  <td className="num">{r.rank}</td>
                  <td className="num">
                    <strong>{fmtDeviation(r.deviation_pu)}</strong>
                  </td>
                  <td className="num">{fmtVm(r.vm_pu)}</td>
                  <OutageCell outage={r.outage} isolation={r.isolation} />
                  <td>{r.bus_id}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function IsolationBlock({ rows }: { rows: IsolationRow[] }): JSX.Element {
  return (
    <details className="section" open={rows.length > 0} data-testid="n1-isolation">
      <summary>
        Aíslan demanda <span className={rows.length > 0 ? "count count--alert" : "count"}>{rows.length}</span>
      </summary>
      {rows.length === 0 ? (
        <p className="muted">Ninguna contingencia deja demanda sin servicio.</p>
      ) : (
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th className="num">#</th>
                <th>Activo fuera</th>
                <th className="num">Barras aisladas</th>
                <th className="num">Demanda sin servicio</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.outage.element_id}>
                  <td className="num">{r.rank}</td>
                  <OutageCell outage={r.outage} />
                  <td className="num">{r.n_buses}</td>
                  <td className="num">
                    <strong>{fmtNum(r.p_demand_lost_mw, 1)} MW</strong>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </details>
  );
}

function UnsolvedBlock({ rows }: { rows: UnsolvedRow[] }): JSX.Element {
  return (
    <details className="section" open={rows.length > 0} data-testid="n1-unsolved">
      <summary>
        Sin solución <span className={rows.length > 0 ? "count count--alert" : "count"}>{rows.length}</span>
      </summary>
      <p className="muted small">El flujo no converge con el activo fuera, ni partiendo de un flujo DC. No es un resultado válido; se muestra con su diagnóstico.</p>
      {rows.length === 0 ? (
        <p className="muted">Todas las contingencias tienen solución.</p>
      ) : (
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Activo fuera</th>
                <th className="num">Iteraciones</th>
                <th className="num">Desbalance máx.</th>
                <th>Barras problemáticas</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.outage.element_id} className="violation">
                  <OutageCell outage={r.outage} />
                  <td className="num">{r.diagnostics.iterations}</td>
                  <td className="num">{fmtNum(r.diagnostics.max_mismatch_mva, 2)} MVA</td>
                  <td>{r.diagnostics.worst_buses.slice(0, 3).map((b) => b.bus).join(", ")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </details>
  );
}

function AnalysisView({ analysis }: { analysis: N1Analysis }): JSX.Element {
  const s = analysis.summary;
  const t = analysis.trace;
  return (
    <>
      <div className="kpis" data-testid="n1-summary">
        <Kpi label="Contingencias" value={String(s.n_total)} testId="n1-total" />
        <Kpi label="Cargabilidad" value={String(s.n_loading)} alert={s.n_loading > 0} />
        <Kpi label="Tensiones" value={String(s.n_voltage)} alert={s.n_voltage > 0} />
        <Kpi label="Aíslan demanda" value={String(s.n_isolation)} alert={s.n_isolation > 0} />
        <Kpi label="Sin solución" value={String(s.n_unsolved)} alert={s.n_unsolved > 0} />
        <Kpi label="Sin impacto" value={String(s.n_no_impact)} />
        <Kpi label="Duración" value={fmtDuration(s.duration_s)} />
      </div>
      <p className="trace small muted" data-testid="n1-trace">
        Snapshot <code>{t.snapshot_date}</code> · periodo <code>{t.period}</code> · pandapower <code>{t.pandapower_version}</code> · solver{" "}
        <code>{t.solver.algorithm}</code> · caso <code>{t.case_id.slice(0, 12)}…</code> · {analysis.workers} proceso(s) · {new Date(analysis.analyzed_at).toLocaleString("es-CO")}
      </p>
      <details className="section">
        <summary>Límites aplicados (con fuente)</summary>
        <ul className="small">
          {analysis.limits.map((l) => (
            <li key={l.name}>
              {l.name}: {l.value} — {l.source}
            </li>
          ))}
        </ul>
      </details>
      <div className="n1__lists">
        <LoadingList rows={analysis.loading} />
        <VoltageList rows={analysis.voltage} />
      </div>
      <IsolationBlock rows={analysis.isolation} />
      <UnsolvedBlock rows={analysis.unsolved} />
    </>
  );
}

/** Análisis de contingencias N-1 (HU-7): botón, avance, resumen y los listados lado a lado. */
export function N1Panel({ run }: Props): JSX.Element {
  const start = useStartN1();
  const [jobId, setJobId] = useState<string | null>(null);
  const job = useN1Job(jobId);

  const canStart = run.flow_type === "ac" && run.status === "convergio" && run.result !== null;
  const running = start.isPending || isRunning(job.data);
  const analysis = job.data?.status === "listo" ? job.data.result : null;
  const error =
    start.error instanceof ProblemError
      ? start.error.problem.user_message
      : start.error
        ? "Ocurrió un error no previsto."
        : job.data?.status === "error"
          ? (job.data.error?.user_message ?? "El análisis falló.")
          : null;

  async function launch(): Promise<void> {
    setJobId(null);
    try {
      const started = await start.mutateAsync(run.run_id);
      setJobId(started.job_id);
    } catch {
      // start.error ya trae el Problem Details (por ejemplo N1_IN_PROGRESS).
    }
  }

  return (
    <section className="n1 card card--padded stack" data-testid="n1" data-job-id={jobId ?? ""}>
      <div className="n1__bar">
        <h2>Contingencias N-1</h2>
        <span className="spacer" />
        <button type="button" className="button" onClick={() => void launch()} disabled={!canStart || running} data-testid="n1-start">
          {running ? "Analizando…" : "Analizar N-1"}
        </button>
      </div>
      <p className="muted small">
        Saca de servicio cada línea, transformador y generador, uno a la vez, corre el flujo AC y compara con el caso base: solo cuenta lo que empeora.
      </p>
      {!canStart && (
        <p className="notice notice--info" data-testid="n1-unavailable">
          El análisis N-1 se hace sobre un flujo AC que convergió.{" "}
          {run.flow_type === "dc" ? "Este flujo es la aproximación DC: corre el flujo AC primero." : "Este flujo no convergió."}
        </p>
      )}
      {running && (
        <p className="muted" data-testid="n1-progress" aria-live="polite">
          Analizando… {progressText(job.data)}
        </p>
      )}
      {error && (
        <p className="notice notice--error" role="alert" data-testid="n1-error">
          {error}
        </p>
      )}
      {analysis && <AnalysisView analysis={analysis} />}
    </section>
  );
}

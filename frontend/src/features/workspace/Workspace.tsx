import { useMemo, useState } from "react";

import { ProblemError, api } from "../../api/client";
import { useCreateCase, useRunCase, useSc } from "../../api/hooks";
import type { Run, StudyCase } from "../../api/types";
import { CaseQuality } from "../case-quality/CaseQuality";
import { N1Panel } from "../contingencies/N1Panel";
import { ResultsTables } from "../results-tables/ResultsTables";
import { RunPicker, type RunRequest } from "../run-picker/RunPicker";
import { ScPanel } from "../shortcircuit/ScPanel";
import { maxIkss } from "../shortcircuit/sc";
import { TopologyView } from "../topology/TopologyView";
import { ViolationsReport } from "../violations/ViolationsReport";

const ATTRIBUTION = "Información proporcionada por XM S.A. E.S.P. – PARATEC y archivos públicos de despacho";
const SCOPE = "Flujo sobre despacho programado (no es el estado real del SIN)";

/** Flujo completo: picker → calidad del caso → ejecución → resultados, topología y exportación. */
export function Workspace(): JSX.Element {
  const createCase = useCreateCase();
  const runCase = useRunCase();
  const [studyCase, setStudyCase] = useState<StudyCase | null>(null);
  const [run, setRun] = useState<Run | null>(null);
  const [error, setError] = useState<string | null>(null);

  const busy = createCase.isPending || runCase.isPending;
  // Cortocircuito guardado del caso (spec 004): colorea el mapa cuando existe.
  const sc = useSc(run?.run_id ?? null);
  const scByBus = useMemo(() => (sc.data ? new Map(sc.data.buses.filter((b) => !b.no_source).map((b) => [b.bus_id, b.ikss_ka])) : undefined), [sc.data]);
  const scMax = useMemo(() => (sc.data ? maxIkss(sc.data.buses) : 0), [sc.data]);

  async function execute(req: RunRequest): Promise<void> {
    setError(null);
    setRun(null);
    try {
      const built = await createCase.mutateAsync({ snapshot_date: req.snapshotDate, period: req.period });
      setStudyCase(built);
      const result = await runCase.mutateAsync({ caseId: built.case_id, flowType: req.flowType });
      setRun(result);
    } catch (e) {
      setError(e instanceof ProblemError ? e.problem.user_message : "Ocurrió un error no previsto.");
    }
  }

  return (
    <>
      <header className="app-header">
        <div className="app-header__row">
          <h1>sinsim</h1>
          <p className="label chip chip--accent" data-testid="label">
            {run ? run.label : SCOPE}
          </p>
          <span className="spacer" />
          {run && (
            <a className="button button--secondary" href={api.exportUrl(run.run_id)} download data-testid="export-link">
              Exportar .zip
            </a>
          )}
        </div>
        {run && (
          <p className="trace app-header__trace">
            <span>
              Snapshot <code>{run.trace.snapshot_date}</code>
            </span>
            <span>
              Despacho <code>{run.trace.dispatch_date}</code> · periodo <code>{run.trace.period}</code>
            </span>
            <span>
              Flujo <code>{run.trace.flow_type}</code>
            </span>
            <span>
              pandapower <code>{run.trace.pandapower_version}</code> · sinsim <code>{run.trace.sinsim_version}</code>
            </span>
            <span>
              Caso <code>{run.trace.case_id.slice(0, 12)}…</code>
            </span>
          </p>
        )}
      </header>
      <main>
        <RunPicker busy={busy} onSubmit={(r) => void execute(r)} />
        {error && (
          <p className="notice notice--error" role="alert" data-testid="error">
            {error}
          </p>
        )}
        {busy && <p className="muted">Construyendo el caso y corriendo el flujo…</p>}
        {run && run.result && <TopologyView run={run} scByBus={scByBus} scMax={scMax} />}
        {run && <ResultsTables run={run} />}
        {run && <N1Panel key={run.run_id} run={run} />}
        {run && <ScPanel key={`sc-${run.run_id}`} run={run} />}
        {studyCase && (
          <div className="reports">
            <CaseQuality studyCase={studyCase} />
            {run && <ViolationsReport run={run} />}
          </div>
        )}
      </main>
      <footer>
        <div className="footer__row">
          <span>{ATTRIBUTION}</span>
          <span className="spacer" />
          <span>Todo resultado describe el programa publicado por XM, nunca el estado real del SIN.</span>
        </div>
      </footer>
    </>
  );
}

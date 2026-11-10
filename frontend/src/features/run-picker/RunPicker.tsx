import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { ProblemError } from "../../api/client";
import { useScrapeJob, useSnapshots, useStartScrape, useSuggestedDate } from "../../api/hooks";
import type { FlowType } from "../../api/types";
import { STEP_LABELS, availabilityOf, incompleteReason, latestAllowed, type Availability } from "./availability";

export interface RunRequest {
  snapshotDate: string;
  period: number;
  flowType: FlowType;
}

interface Props {
  busy: boolean;
  onSubmit: (request: RunRequest) => void;
}

function statusText(a: Availability): string {
  switch (a.kind) {
    case "empty":
      return "Escribe una fecha.";
    case "invalid":
      return "La fecha debe tener el formato AAAA-MM-DD.";
    case "too_late":
      return `Solo se admite hasta ${a.latest}: XM publica el despacho programado la víspera.`;
    case "available":
      return "Disponible.";
    case "incomplete":
      return `Snapshot inutilizable (${a.reason}). Los snapshots no se sobrescriben; restáuralo desde git.`;
    case "missing":
      return "Sin descargar.";
  }
}

function errorMessage(e: unknown): string {
  return e instanceof ProblemError ? e.problem.user_message : "Ocurrió un error no previsto.";
}

/** Fecha, periodo y tipo de flujo; descarga la fecha si no tiene snapshot (FR-038, FR-039). */
export function RunPicker({ busy, onSubmit }: Props): JSX.Element {
  const queryClient = useQueryClient();
  const snapshots = useSnapshots();
  const suggested = useSuggestedDate();
  const startScrape = useStartScrape();
  const [date, setDate] = useState<string>("");
  const [period, setPeriod] = useState<number>(19);
  const [flowType, setFlowType] = useState<FlowType>("ac");
  const [jobId, setJobId] = useState<string | null>(null);
  const job = useScrapeJob(jobId);

  const today = new Date();
  const rows = snapshots.data ?? [];
  const selectable = rows.filter((s) => incompleteReason(s) === null);
  // Por defecto, la fecha sugerida (mañana desde que XM suele publicar el despacho, hoy antes); si
  // la API no la da, la última fecha ya descargada y completa.
  const effectiveDate = date || suggested.data?.date || selectable[selectable.length - 1]?.date || "";
  const availability = availabilityOf(effectiveDate, rows, today);
  const periodValid = Number.isInteger(period) && period >= 1 && period <= 24;
  const scraping = startScrape.isPending || (job.data !== undefined && job.data.status !== "listo" && job.data.status !== "error");
  const canRun = availability.kind === "available" && periodValid && !busy && !scraping;
  const jobStatus = job.data?.status;

  // Al terminar una descarga, la lista de fechas cambia: se vuelve a pedir (FR-038).
  useEffect(() => {
    if (jobStatus === "listo") void queryClient.invalidateQueries({ queryKey: ["snapshots"] });
  }, [jobStatus, queryClient]);

  async function download(): Promise<void> {
    setJobId(null);
    try {
      const started = await startScrape.mutateAsync(effectiveDate);
      setDate(started.date);
      setJobId(started.job_id);
    } catch {
      // startScrape.error ya trae el Problem Details.
    }
  }

  const showsJob = job.data !== undefined && job.data.date === effectiveDate;

  return (
    <form
      className="picker"
      onSubmit={(e) => {
        e.preventDefault();
        if (canRun) onSubmit({ snapshotDate: effectiveDate, period, flowType });
      }}
    >
      <label>
        Fecha del snapshot
        <input
          type="date"
          list="snapshot-dates"
          value={effectiveDate}
          max={latestAllowed(today)}
          onChange={(e) => setDate(e.target.value)}
          disabled={snapshots.isLoading || scraping}
          data-testid="snapshot-date"
        />
        <datalist id="snapshot-dates">
          {rows.map((s) => {
            const reason = incompleteReason(s);
            return <option key={s.date} value={s.date} label={reason ? `${s.date} — ${reason}` : s.date} />;
          })}
        </datalist>
      </label>
      <label>
        Periodo (1–24)
        <input
          type="number"
          min={1}
          max={24}
          value={period}
          onChange={(e) => setPeriod(Number(e.target.value))}
          data-testid="period"
        />
      </label>
      <label>
        Tipo de flujo
        <select value={flowType} onChange={(e) => setFlowType(e.target.value as FlowType)} data-testid="flow-type">
          <option value="ac">AC</option>
          <option value="dc">DC (aproximación)</option>
        </select>
      </label>
      <button type="submit" disabled={!canRun} data-testid="run-button">
        {busy ? "Calculando…" : "Ejecutar"}
      </button>
      <div className="snapshot-status" data-testid="snapshot-status" data-kind={availability.kind}>
        <span className={`status-chip status-chip--${availability.kind}`}>
          {availability.kind === "available" ? "Disponible" : availability.kind === "missing" ? "Sin descargar" : "Revisa la fecha"}
        </span>
        {availability.kind !== "available" && <span>{statusText(availability)}</span>}
        {availability.kind === "missing" && !scraping && (
          <button type="button" onClick={() => void download()} data-testid="scrape-button">
            Descargar datos de esta fecha
          </button>
        )}
        {scraping && (
          <span className="muted" data-testid="scrape-progress">
            {STEP_LABELS[job.data?.step ?? "en_cola"] ?? "Descargando…"}
          </span>
        )}
        {showsJob && job.data?.status === "listo" && (
          <span className="muted" data-testid="scrape-done">
            Descarga terminada: la fecha ya está disponible.
          </span>
        )}
        {showsJob && job.data?.status === "error" && job.data.error && (
          <span className="error" role="alert" data-testid="scrape-error">
            {job.data.error.user_message}
          </span>
        )}
        {startScrape.isError && (
          <span className="error" role="alert" data-testid="scrape-error">
            {errorMessage(startScrape.error)}
          </span>
        )}
        {job.isError && (
          <span className="error" role="alert" data-testid="scrape-error">
            {errorMessage(job.error)}
          </span>
        )}
      </div>
      <p className="muted notice">
        PARATEC no tiene histórico: al descargar una fecha, el despacho y la demanda son los de ese día, pero los
        parámetros técnicos son los vigentes en el momento de la descarga (el manifiesto lo registra en{" "}
        <code>extracted_at</code>).
      </p>
      {snapshots.isError && <p className="error">No se pudo leer la lista de snapshots.</p>}
      {!snapshots.isLoading && rows.length === 0 && !scraping && (
        <p className="muted">No hay snapshots en data/paratec/. Escribe una fecha y descárgala, o ejecuta `sinsim scrape`.</p>
      )}
      {!periodValid && <p className="error">El periodo debe estar entre 1 y 24.</p>}
    </form>
  );
}

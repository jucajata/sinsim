import type { CSSProperties } from "react";

import type { Isolation, N1Job, OutageKind } from "../../api/types";
import { fmtNum } from "../../lib/format";

/** Etiqueta del tipo de activo que sale (FR-049). */
export const KIND_LABELS: Record<OutageKind, string> = {
  line: "Línea",
  trafo2w: "Transformador",
  gen: "Generador",
  compensador: "Compensador",
};

/** Marca «aísla N barras, X MW sin servicio» (FR-055); vacía si no aísla nada. */
export function isolationText(isolation: Isolation | null): string {
  if (isolation === null) return "";
  const buses = isolation.n_buses === 1 ? "1 barra" : `${isolation.n_buses} barras`;
  return `aísla ${buses}, ${fmtNum(isolation.p_demand_lost_mw, 1)} MW sin servicio`;
}

/** Cargabilidad con un decimal: «201,4 %». */
export const fmtLoading = (v: number): string => `${fmtNum(v, 1)} %`;

/** Tensión en pu con tres decimales: «0,842 pu». */
export const fmtVm = (v: number): string => `${fmtNum(v, 3)} pu`;

/** Distancia fuera de banda con signo explícito: «−0,058 pu» o «+0,031 pu». */
export function fmtDeviation(v: number): string {
  const sign = v > 0 ? "+" : v < 0 ? "−" : "";
  return `${sign}${fmtNum(Math.abs(v), 3)} pu`;
}

/** Duración del análisis: «1 min 16 s» o «48 s». */
export function fmtDuration(seconds: number): string {
  const s = Math.round(seconds);
  return s >= 60 ? `${Math.floor(s / 60)} min ${s % 60} s` : `${s} s`;
}

/** Texto del avance (FR-058): «640 / 1261 contingencias (50 %)». */
export function progressText(job: N1Job | undefined): string {
  if (job === undefined || job.status === "en_cola") return "En cola…";
  const pct = job.total > 0 ? ` (${Math.floor((100 * job.done) / job.total)} %)` : "";
  return `${job.done} / ${job.total} contingencias${pct}`;
}

/** El análisis sigue corriendo (en cola o calculando). */
export function isRunning(job: N1Job | undefined): boolean {
  return job !== undefined && job.status !== "listo" && job.status !== "error";
}

/** Nombre legible del activo: sin el prefijo «line:», «trafo:», «svc:» o «statcom:». */
export function outageLabel(elementId: string): string {
  return elementId.replace(/^(line|trafo|svc|statcom):/, "");
}

// --- Color por intensidad (decisión del usuario, 2026-10-24) ---------------------------------

const RED = "220, 38, 38";
const BLUE = "37, 99, 235";
const MIN_ALPHA = 0.12;
const MAX_ALPHA = 0.85;

function cellStyle(rgb: string, t: number): CSSProperties {
  const alpha = MIN_ALPHA + (MAX_ALPHA - MIN_ALPHA) * Math.min(1, Math.max(0, t));
  return {
    background: `rgba(${rgb}, ${alpha.toFixed(2)})`,
    color: alpha >= 0.5 ? "#fff" : undefined,
  };
}

/** Más cargado, más rojo: de claro en el límite a rojo pleno al doble del límite. */
export function loadingStyle(loadingPercent: number, limitPercent = 100): CSSProperties {
  return cellStyle(RED, (loadingPercent - limitPercent) / limitPercent);
}

/** Sobretensión en rojo, subtensión en azul; más intenso cuanto más lejos de la banda (pleno a `full` pu). */
export function voltageStyle(deviationPu: number, full = 0.1): CSSProperties {
  return cellStyle(deviationPu < 0 ? BLUE : RED, Math.abs(deviationPu) / full);
}

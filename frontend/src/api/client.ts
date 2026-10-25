import type {
  Basemap,
  CaseRequest,
  FlowType,
  N1Job,
  Problem,
  Run,
  ScrapeJob,
  ShortCircuitAnalysis,
  SnapshotSummary,
  StudyCase,
  Topology,
} from "./types";

/** Error de la API en formato Problem Details (constitución V). */
export class ProblemError extends Error {
  readonly problem: Problem;

  constructor(problem: Problem) {
    super(problem.user_message);
    this.name = "ProblemError";
    this.problem = problem;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!response.ok) {
    let problem: Problem;
    try {
      problem = (await response.json()) as Problem;
    } catch {
      problem = {
        type: "about:blank",
        title: "Error",
        status: response.status,
        detail: response.statusText,
        code: "HTTP_ERROR",
        user_message: `La API respondió ${response.status}.`,
        trace_id: response.headers.get("X-Trace-Id") ?? "",
      };
    }
    throw new ProblemError(problem);
  }
  return (await response.json()) as T;
}

export const api = {
  snapshots: () => request<SnapshotSummary[]>("/snapshots"),
  startScrape: (date: string) => request<ScrapeJob>(`/snapshots/${date}/descarga`, { method: "POST" }),
  scrapeJob: (jobId: string) => request<ScrapeJob>(`/snapshots/descargas/${jobId}`),
  createCase: (body: CaseRequest) =>
    request<StudyCase>("/cases", { method: "POST", body: JSON.stringify(body) }),
  getCase: (caseId: string) => request<StudyCase>(`/cases/${caseId}`),
  runCase: (caseId: string, flowType: FlowType) =>
    request<Run>(`/cases/${caseId}/runs`, {
      method: "POST",
      body: JSON.stringify({ flow_type: flowType }),
    }),
  getRun: (runId: string) => request<Run>(`/runs/${runId}`),
  topology: (runId: string) => request<Topology>(`/runs/${runId}/topology`),
  basemap: () => request<Basemap>(`/geo/basemap`),
  exportUrl: (runId: string) => `/api/runs/${runId}/export`,
  startN1: (runId: string) => request<N1Job>(`/runs/${runId}/n1`, { method: "POST" }),
  n1Job: (jobId: string) => request<N1Job>(`/n1/${jobId}`),
  sc: (runId: string) => request<ShortCircuitAnalysis>(`/runs/${runId}/sc`),
  calculateSc: (runId: string) => request<ShortCircuitAnalysis>(`/runs/${runId}/sc`, { method: "POST" }),
};

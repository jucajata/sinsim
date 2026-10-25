import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { ProblemError, api } from "./client";
import type { CaseRequest, FlowType, N1Job, ScrapeJob, ShortCircuitAnalysis } from "./types";

export function useSnapshots() {
  return useQuery({ queryKey: ["snapshots"], queryFn: api.snapshots });
}

/** Inicia la descarga de una fecha (FR-038). */
export function useStartScrape() {
  return useMutation({ mutationFn: (date: string) => api.startScrape(date) });
}

const SCRAPE_POLL_MS = 1000;

function isRunning(job: ScrapeJob | undefined): boolean {
  return job !== undefined && job.status !== "listo" && job.status !== "error";
}

/** Estado de una descarga; sondea cada segundo mientras corre (FR-038). */
export function useScrapeJob(jobId: string | null) {
  return useQuery({
    queryKey: ["scrape", jobId],
    queryFn: () => api.scrapeJob(jobId as string),
    enabled: jobId !== null,
    staleTime: 0,
    refetchInterval: (query) => (isRunning(query.state.data) || query.state.data === undefined ? SCRAPE_POLL_MS : false),
  });
}

export function useCreateCase() {
  return useMutation({ mutationFn: (body: CaseRequest) => api.createCase(body) });
}

export function useCase(caseId: string | null) {
  return useQuery({
    queryKey: ["case", caseId],
    queryFn: () => api.getCase(caseId as string),
    enabled: caseId !== null,
  });
}

export function useRunCase() {
  return useMutation({
    mutationFn: ({ caseId, flowType }: { caseId: string; flowType: FlowType }) =>
      api.runCase(caseId, flowType),
  });
}

export function useRun(runId: string | null) {
  return useQuery({
    queryKey: ["run", runId],
    queryFn: () => api.getRun(runId as string),
    enabled: runId !== null,
  });
}

export function useTopology(runId: string | null) {
  return useQuery({
    queryKey: ["topology", runId],
    queryFn: () => api.topology(runId as string),
    enabled: runId !== null,
  });
}

/** Mapa base para la disposición geográfica (FR-035); no cambia, así que no se refresca. */
export function useBasemap(enabled: boolean) {
  return useQuery({ queryKey: ["basemap"], queryFn: () => api.basemap(), enabled, staleTime: Infinity });
}

/** Lanza el análisis N-1 sobre una ejecución (FR-058). */
export function useStartN1() {
  return useMutation({ mutationFn: (runId: string) => api.startN1(runId) });
}

const N1_POLL_MS = 1000;

function isN1Running(job: N1Job | undefined): boolean {
  return job !== undefined && job.status !== "listo" && job.status !== "error";
}

/** Estado del análisis N-1; sondea cada segundo mientras corre (FR-058). */
export function useN1Job(jobId: string | null) {
  return useQuery({
    queryKey: ["n1", jobId],
    queryFn: () => api.n1Job(jobId as string),
    enabled: jobId !== null,
    staleTime: 0,
    refetchInterval: (query) => (isN1Running(query.state.data) || query.state.data === undefined ? N1_POLL_MS : false),
  });
}

/** Cortocircuito guardado de la ejecución (FR-071); un 404 significa «no calculado», no un error. */
export function useSc(runId: string | null) {
  return useQuery<ShortCircuitAnalysis | null>({
    queryKey: ["sc", runId],
    queryFn: async () => {
      try {
        return await api.sc(runId as string);
      } catch (e) {
        if (e instanceof ProblemError && e.problem.code === "SC_NOT_FOUND") return null;
        throw e;
      }
    },
    enabled: runId !== null,
    retry: false,
    staleTime: Infinity,
  });
}

/** Lanza el cálculo (FR-069) y deja el resultado en la caché de `useSc`. */
export function useCalculateSc() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (runId: string) => api.calculateSc(runId),
    onSuccess: (analysis, runId) => client.setQueryData(["sc", runId], analysis),
  });
}

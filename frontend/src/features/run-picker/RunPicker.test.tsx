import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import { ProblemError } from "../../api/client";
import type { Problem, ScrapeJob, SnapshotSummary, SuggestedDate } from "../../api/types";
import { isoDate } from "./availability";
import { RunPicker } from "./RunPicker";

const ok: SnapshotSummary = { date: "2026-10-20", has_paratec: true, has_dispatch: true, has_demand: true, intact: true };
const newer: SnapshotSummary = { ...ok, date: "2026-10-15" };

const mocks = vi.hoisted(() => ({
  snapshots: vi.fn<() => Promise<SnapshotSummary[]>>(),
  startScrape: vi.fn<(date: string) => Promise<ScrapeJob>>(),
  scrapeJob: vi.fn<(id: string) => Promise<ScrapeJob>>(),
  suggestedDate: vi.fn<() => Promise<SuggestedDate>>(),
}));

vi.mock("../../api/client", async (importOriginal) => {
  const original = await importOriginal<typeof import("../../api/client")>();
  return { ...original, api: { ...original.api, ...mocks } };
});

function job(partial: Partial<ScrapeJob>): ScrapeJob {
  return {
    job_id: "j1",
    date: "2026-10-15",
    status: "en_cola",
    step: "en_cola",
    started_at: "2026-10-21T10:00:00Z",
    finished_at: null,
    snapshot: null,
    error: null,
    notice: "PARATEC no tiene histórico",
    ...partial,
  };
}

function problem(code: string, user_message: string): Problem {
  return { type: "x", title: code, status: 409, detail: "", code, user_message, trace_id: "t" };
}

function renderPicker(onSubmit = vi.fn()) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <RunPicker busy={false} onSubmit={onSubmit} />
    </QueryClientProvider>,
  );
  return onSubmit;
}

beforeEach(() => {
  mocks.snapshots.mockReset();
  mocks.startScrape.mockReset();
  mocks.scrapeJob.mockReset();
  mocks.suggestedDate.mockReset();
  // Sin fecha sugerida (API caída): se usa la última fecha disponible.
  mocks.suggestedDate.mockRejectedValue(new Error("sin red"));
});

describe("RunPicker", () => {
  it("elige por defecto la última fecha disponible y permite ejecutar", async () => {
    mocks.snapshots.mockResolvedValue([ok]);
    const onSubmit = renderPicker();
    await waitFor(() => expect(screen.getByTestId("snapshot-date")).toHaveValue("2026-10-20"));
    expect(screen.getByTestId("snapshot-status")).toHaveAttribute("data-kind", "available");
    expect(screen.getByTestId("run-button")).toBeEnabled();
    fireEvent.click(screen.getByTestId("run-button"));
    expect(onSubmit).toHaveBeenCalledWith({ snapshotDate: "2026-10-20", period: 19, flowType: "ac" });
  });

  it("propone por defecto la fecha sugerida aunque no esté descargada y ofrece descargarla (FR-039)", async () => {
    const tomorrow = isoDate(new Date(), 1);
    mocks.snapshots.mockResolvedValue([ok]);
    mocks.suggestedDate.mockResolvedValue({ date: tomorrow, published_at: "15:00", timezone: "America/Bogota" });
    renderPicker();
    await waitFor(() => expect(screen.getByTestId("snapshot-date")).toHaveValue(tomorrow));
    expect(screen.getByTestId("snapshot-status")).toHaveAttribute("data-kind", "missing");
    expect(screen.getByTestId("scrape-button")).toBeVisible();
    expect(screen.getByTestId("run-button")).toBeDisabled();
  });

  it("ofrece descargar una fecha sin snapshot y la deja lista al terminar (FR-038)", async () => {
    mocks.snapshots.mockResolvedValueOnce([ok]).mockResolvedValue([newer, ok]);
    mocks.startScrape.mockResolvedValue(job({}));
    mocks.scrapeJob.mockResolvedValue(job({ status: "listo", step: "listo", snapshot: newer, finished_at: "2026-10-21T10:01:00Z" }));
    renderPicker();
    await waitFor(() => expect(screen.getByTestId("snapshot-date")).toHaveValue("2026-10-20"));
    fireEvent.change(screen.getByTestId("snapshot-date"), { target: { value: "2026-10-15" } });
    expect(screen.getByTestId("snapshot-status")).toHaveAttribute("data-kind", "missing");
    expect(screen.getByTestId("run-button")).toBeDisabled();
    fireEvent.click(screen.getByTestId("scrape-button"));
    await waitFor(() => expect(mocks.startScrape).toHaveBeenCalledWith("2026-10-15"));
    await waitFor(() => expect(screen.getByTestId("scrape-done")).toBeVisible());
    await waitFor(() => expect(screen.getByTestId("snapshot-status")).toHaveAttribute("data-kind", "available"));
    expect(screen.getByTestId("snapshot-date")).toHaveValue("2026-10-15");
    expect(screen.getByTestId("run-button")).toBeEnabled();
  });

  it("muestra el error de la descarga con el mensaje del catálogo", async () => {
    mocks.snapshots.mockResolvedValue([ok]);
    mocks.startScrape.mockResolvedValue(job({ date: "2026-10-18" }));
    mocks.scrapeJob.mockResolvedValue(
      job({ date: "2026-10-18", status: "error", step: "error", error: problem("XM_FILE_NOT_FOUND", "XM no tiene publicado ese archivo.") }),
    );
    renderPicker();
    await waitFor(() => expect(screen.getByTestId("snapshot-date")).toHaveValue("2026-10-20"));
    fireEvent.change(screen.getByTestId("snapshot-date"), { target: { value: "2026-10-18" } });
    fireEvent.click(screen.getByTestId("scrape-button"));
    await waitFor(() => expect(screen.getByTestId("scrape-error")).toHaveTextContent("XM no tiene publicado"));
    expect(screen.getByTestId("scrape-button")).toBeVisible(); // se puede reintentar
  });

  it("rechaza fechas posteriores a mañana e informa si ya hay una descarga en curso", async () => {
    mocks.snapshots.mockResolvedValue([ok]);
    mocks.startScrape.mockRejectedValue(new ProblemError(problem("SCRAPE_IN_PROGRESS", "Ya se está descargando la fecha 2026-10-10.")));
    renderPicker();
    await waitFor(() => expect(screen.getByTestId("snapshot-date")).toHaveValue("2026-10-20"));
    fireEvent.change(screen.getByTestId("snapshot-date"), { target: { value: "2099-01-01" } });
    expect(screen.getByTestId("snapshot-status")).toHaveAttribute("data-kind", "too_late");
    expect(screen.queryByTestId("scrape-button")).toBeNull();
    fireEvent.change(screen.getByTestId("snapshot-date"), { target: { value: "2026-10-18" } });
    fireEvent.click(screen.getByTestId("scrape-button"));
    await waitFor(() => expect(screen.getByTestId("scrape-error")).toHaveTextContent("2026-10-10"));
  });
});

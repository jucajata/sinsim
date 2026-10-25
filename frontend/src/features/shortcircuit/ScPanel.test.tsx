import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";

import { ProblemError } from "../../api/client";
import type { Problem, Run, ShortCircuitAnalysis } from "../../api/types";
import { ScPanel } from "./ScPanel";

const mocks = vi.hoisted(() => ({
  sc: vi.fn<(runId: string) => Promise<ShortCircuitAnalysis>>(),
  calculateSc: vi.fn<(runId: string) => Promise<ShortCircuitAnalysis>>(),
}));

vi.mock("../../api/client", async (importOriginal) => {
  const original = await importOriginal<typeof import("../../api/client")>();
  return { ...original, api: { ...original.api, ...mocks } };
});

const run = { run_id: "r1", case_id: "c1", flow_type: "ac", status: "no_convergio", result: null, diagnostics: null } as unknown as Run;

const notFound: Problem = {
  type: "about:blank",
  title: "Cortocircuito no calculado",
  status: 404,
  detail: "",
  code: "SC_NOT_FOUND",
  user_message: "No hay un cálculo guardado.",
  trace_id: "t",
};

const analysis: ShortCircuitAnalysis = {
  case_id: "c1c1c1c1c1c1c1c1",
  run_id: "r1",
  case_hash: "c1",
  sc_config_hash: "h1",
  trace: {
    snapshot_date: "2026-10-20",
    dispatch_date: "2026-10-20",
    period: 19,
    flow_type: "ac",
    pandapower_version: "3.5.6",
    sinsim_version: "0.7.0",
    solver: { algorithm: "nr", tolerance_mva: 1e-8, max_iteration: 30, init: "dc", enforce_q_lims: true, distributed_slack: true },
    case_id: "c1c1c1c1c1c1c1c1",
  },
  norm: { standard: "IEC 60909-0:2016", fault: "3ph", case: "max", c_max: 1.1 },
  config: {},
  assumptions: [{ id: "S26", text: "Tensión nominal de PARATEC.", source: "Decisión del agente" }],
  calculated_at: "2026-10-25T20:00:00Z",
  summary: {
    n_buses: 3,
    max_ikss: { bus_id: "SAN CARLOS|230", value: 52.62 },
    min_skss: { bus_id: "GUAVIARE|115", value: 109 },
    n_sources_sync: 2,
    n_sources_converter: 1,
    n_imputed_units: 1,
    n_without_step_up: 1,
    n_no_source: 1,
    duration_s: 4.9,
  },
  buses: [
    { bus_id: "GUAVIARE|115", substation: "GUAVIARE", subarea: "Meta", nominal_kv: 115, base_kv: 115, ikss_ka: 0.55, skss_mva: 109, rk_ohm: 20, xk_ohm: 110, x_r: 5.5, no_source: false },
    { bus_id: "SAN CARLOS|230", substation: "SAN CARLOS", subarea: "Antioquia", nominal_kv: 230, base_kv: 230, ikss_ka: 52.62, skss_mva: 20964, rk_ohm: 0.13, xk_ohm: 1.9, x_r: 14.5, no_source: false },
    { bus_id: "AISLADA|115", substation: "AISLADA", subarea: null, nominal_kv: 115, base_kv: 115, ikss_ka: 0, skss_mva: 0, rk_ohm: null, xk_ohm: null, x_r: null, no_source: true },
  ],
  sources: [
    { unit_id: "hidráulica:SAN CARLOS 1", kind: "sincrona", bus_id: "SAN CARLOS|230", step_up_trafo_id: null, sn_mva: 160, vn_kv: 230, cos_phi: 0.9, xdss_pu: 0.2, rdss_ohm: 0.1, k: null, origins: { sn_mva: "publicado" } },
  ],
  quality: {
    imputed: [{ unit_id: "hidráulica:SAN CARLOS 1", parameter: "rdss_pu", value: 0.01, method: "relacion_iec" }],
    generators_without_step_up: ["hidráulica:SAN CARLOS 1"],
    sc_zero_sources: [{ resource: "ECUADOR230_1", bus_id: "JAMONDINO|230", reason: "S29" }],
    excluded: [{ unit_id: "svc:CHINU", reason: "compensador" }],
    step_up_equivalences: { matched: 0, by_method: {}, curated: 0, uncurated: 0 },
  },
  attribution: "Información proporcionada por XM S.A. E.S.P.",
};

function renderPanel(): void {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <ScPanel run={run} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  mocks.sc.mockReset();
  mocks.calculateSc.mockReset();
});

describe("ScPanel", () => {
  it("ofrece el botón aunque el flujo no haya convergido y muestra «Calculando…» (FR-069)", async () => {
    mocks.sc.mockRejectedValue(new ProblemError(notFound));
    let resolve: (a: ShortCircuitAnalysis) => void = () => {};
    mocks.calculateSc.mockReturnValue(new Promise((r) => (resolve = r)));
    renderPanel();
    await waitFor(() => expect(mocks.sc).toHaveBeenCalledWith("r1"));
    const button = screen.getByTestId("sc-start");
    expect(button).toBeEnabled();
    expect(button).toHaveTextContent("Cortocircuito");
    fireEvent.click(button);
    await screen.findByTestId("sc-progress");
    expect(screen.getByTestId("sc-start")).toBeDisabled();
    resolve(analysis);
    await screen.findByTestId("sc-summary");
    expect(screen.getByTestId("sc-buses")).toHaveTextContent("3");
    expect(screen.getByTestId("sc-max")).toHaveTextContent("52,62 kA · SAN CARLOS|230");
    expect(screen.getByTestId("sc-start")).toHaveTextContent("Recalcular");
  });

  it("muestra el resultado guardado sin pulsar el botón (FR-071)", async () => {
    mocks.sc.mockResolvedValue(analysis);
    renderPanel();
    await screen.findByTestId("sc-summary");
    expect(mocks.calculateSc).not.toHaveBeenCalled();
    const table = screen.getByTestId("sc-table");
    const rows = within(table).getAllByRole("row").slice(1);
    // Orden por defecto: Ikss descendente; la barra sin fuente al final y en gris.
    const first = rows[0] as HTMLElement;
    expect(first).toHaveTextContent("SAN CARLOS|230");
    expect(rows[2]).toHaveTextContent("sin fuente");
    const cells = within(first).getAllByRole("cell");
    expect((cells[2] as HTMLElement).style.background).toContain("rgba(220, 38, 38, 0.85)");
    expect(cells[1]).toHaveTextContent("230 kV");
  });

  it("ordena al pulsar una cabecera y filtra con la búsqueda", async () => {
    mocks.sc.mockResolvedValue(analysis);
    renderPanel();
    const table = await screen.findByTestId("sc-table");
    fireEvent.click(within(table).getByRole("columnheader", { name: /^Barra/ }));
    let rows = within(table).getAllByRole("row").slice(1);
    expect(rows[0]).toHaveTextContent("AISLADA|115");
    fireEvent.change(screen.getByTestId("sc-search"), { target: { value: "antioquia" } });
    rows = within(table).getAllByRole("row").slice(1);
    expect(rows).toHaveLength(1);
    expect(rows[0]).toHaveTextContent("SAN CARLOS|230");
  });

  it("lista imputaciones, unidades sin elevador, enlaces sin aporte, excluidos y supuestos (HU-11)", async () => {
    mocks.sc.mockResolvedValue(analysis);
    renderPanel();
    const quality = await screen.findByTestId("sc-quality");
    expect(quality).toHaveTextContent("relación R/X de IEC 60909");
    expect(quality).toHaveTextContent("SAN CARLOS 1 (hidráulica) → SAN CARLOS|230");
    expect(quality).toHaveTextContent("ECUADOR230_1 en JAMONDINO|230");
    expect(quality).toHaveTextContent("svc:CHINU: compensador");
    expect(quality).toHaveTextContent("S26");
  });

  it("muestra el mensaje del Problem Details si el cálculo falla", async () => {
    mocks.sc.mockRejectedValue(new ProblemError(notFound));
    mocks.calculateSc.mockRejectedValue(new ProblemError({ ...notFound, code: "SC_NO_SOURCES", user_message: "Ninguna unidad tiene parámetros." }));
    renderPanel();
    await waitFor(() => expect(mocks.sc).toHaveBeenCalled());
    fireEvent.click(screen.getByTestId("sc-start"));
    expect(await screen.findByTestId("sc-error")).toHaveTextContent("Ninguna unidad tiene parámetros.");
  });
});

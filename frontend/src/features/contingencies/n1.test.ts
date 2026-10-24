import type { N1Job } from "../../api/types";
import { KIND_LABELS, fmtDeviation, fmtDuration, fmtLoading, fmtVm, isRunning, isolationText, loadingStyle, outageLabel, progressText, voltageStyle } from "./n1";

function job(partial: Partial<N1Job>): N1Job {
  return {
    job_id: "j1",
    run_id: "r1",
    status: "en_cola",
    done: 0,
    total: 0,
    started_at: "2026-10-24T10:00:00Z",
    finished_at: null,
    result: null,
    error: null,
    ...partial,
  };
}

describe("n1", () => {
  it("etiqueta los cuatro tipos de activo", () => {
    expect(KIND_LABELS).toEqual({ line: "Línea", trafo2w: "Transformador", gen: "Generador", compensador: "Compensador" });
  });

  it("arma la marca de aislamiento con singular y plural (FR-055)", () => {
    expect(isolationText(null)).toBe("");
    expect(isolationText({ n_buses: 1, p_demand_lost_mw: 33.3 })).toBe("aísla 1 barra, 33,3 MW sin servicio");
    expect(isolationText({ n_buses: 4, p_demand_lost_mw: 0 })).toBe("aísla 4 barras, 0,0 MW sin servicio");
  });

  it("formatea cargabilidad, tensión y distancia fuera de banda con signo", () => {
    expect(fmtLoading(201.37)).toBe("201,4 %");
    expect(fmtVm(0.8421)).toBe("0,842 pu");
    expect(fmtDeviation(-0.0579)).toBe("−0,058 pu");
    expect(fmtDeviation(0.0312)).toBe("+0,031 pu");
    expect(fmtDeviation(0)).toBe("0,000 pu");
  });

  it("formatea la duración", () => {
    expect(fmtDuration(48.4)).toBe("48 s");
    expect(fmtDuration(76)).toBe("1 min 16 s");
  });

  it("describe el avance y sabe cuándo sigue corriendo (FR-058)", () => {
    expect(progressText(undefined)).toBe("En cola…");
    expect(progressText(job({ status: "calculando", done: 640, total: 1261 }))).toBe("640 / 1261 contingencias (50 %)");
    expect(progressText(job({ status: "calculando", done: 0, total: 1261 }))).toBe("0 / 1261 contingencias (0 %)");
    expect(isRunning(undefined)).toBe(false);
    expect(isRunning(job({ status: "calculando" }))).toBe(true);
    expect(isRunning(job({ status: "listo" }))).toBe(false);
    expect(isRunning(job({ status: "error" }))).toBe(false);
  });

  it("colorea más rojo cuanto más cargado, saturando al doble del límite", () => {
    expect(loadingStyle(100)).toEqual({ background: "rgba(220, 38, 38, 0.12)", color: undefined });
    expect(loadingStyle(160)).toEqual({ background: "rgba(220, 38, 38, 0.56)", color: "#fff" });
    expect(loadingStyle(200)).toEqual({ background: "rgba(220, 38, 38, 0.85)", color: "#fff" });
    expect(loadingStyle(300).background).toBe("rgba(220, 38, 38, 0.85)");
    expect(loadingStyle(120, 110).background).toBe(loadingStyle(120, 110).background);
  });

  it("colorea la sobretensión en rojo y la subtensión en azul, más intenso cuanto más lejos", () => {
    expect(voltageStyle(-0.1)).toEqual({ background: "rgba(37, 99, 235, 0.85)", color: "#fff" });
    expect(voltageStyle(-0.02).background).toBe("rgba(37, 99, 235, 0.27)");
    expect(voltageStyle(0.1).background).toBe("rgba(220, 38, 38, 0.85)");
    expect(voltageStyle(0.03).background).toBe("rgba(220, 38, 38, 0.34)");
  });

  it("quita el prefijo técnico del nombre del activo", () => {
    expect(outageLabel("line:GUAVIO - MAMBITA 1 115 kV")).toBe("GUAVIO - MAMBITA 1 115 kV");
    expect(outageLabel("svc:CHINU COMPENSADOR ESTATICO SVC")).toBe("CHINU COMPENSADOR ESTATICO SVC");
    expect(outageLabel("ALBAN@ALTO ANCHICAYA|230")).toBe("ALBAN@ALTO ANCHICAYA|230");
  });
});

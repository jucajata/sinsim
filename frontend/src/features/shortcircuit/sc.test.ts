import type { ScBusResult } from "../../api/types";
import { filterBuses, formatKa, formatKv, formatMva, formatOhm, formatXr, ikssStyle, maxIkss, methodLabel, sortBuses, unitLabel } from "./sc";

function bus(partial: Partial<ScBusResult>): ScBusResult {
  return {
    bus_id: "A|230",
    substation: "A",
    subarea: "Caribe",
    nominal_kv: 220,
    base_kv: 230,
    ikss_ka: 10,
    skss_mva: 3810,
    rk_ohm: 1,
    xk_ohm: 10,
    x_r: 10,
    no_source: false,
    ...partial,
  };
}

describe("sc", () => {
  it("formatea kA, MVA, Ω, X/R y kV en español", () => {
    expect(formatKa(35.871)).toBe("35,87 kA");
    expect(formatMva(14939.4)).toBe("14.939 MVA");
    expect(formatOhm(0.2539)).toBe("0,254 Ω");
    expect(formatOhm(null)).toBe("—");
    expect(formatXr(11.789)).toBe("11,79");
    expect(formatXr(null)).toBe("—");
    expect(formatKv(220)).toBe("220 kV");
    expect(formatKv(34.5)).toBe("34,5 kV");
  });

  it("colorea de 0 kA al máximo del caso y en gris sin fuente (A1)", () => {
    expect(ikssStyle(0, 50).background).toBe("rgba(220, 38, 38, 0.08)");
    expect(ikssStyle(50, 50).background).toBe("rgba(220, 38, 38, 0.85)");
    expect(ikssStyle(50, 50).color).toBe("#fff");
    expect(ikssStyle(25, 50).color).toBeUndefined();
    expect(ikssStyle(80, 50).background).toBe("rgba(220, 38, 38, 0.85)");
    expect(ikssStyle(0, 0).background).toBe("rgba(220, 38, 38, 0.08)");
    expect(ikssStyle(0, 50, true).background).toContain("118, 123, 128");
  });

  it("calcula el máximo Ikss ignorando barras sin fuente", () => {
    expect(maxIkss([bus({ ikss_ka: 10 }), bus({ ikss_ka: 40 }), bus({ ikss_ka: 99, no_source: true })])).toBe(40);
    expect(maxIkss([])).toBe(0);
  });

  it("ordena por columna y deja los nulos al final", () => {
    const rows = [bus({ bus_id: "B|115", x_r: null, no_source: true }), bus({ bus_id: "A|230", x_r: 5 }), bus({ bus_id: "C|500", x_r: 20 })];
    expect(sortBuses(rows, "x_r", "desc").map((b) => b.bus_id)).toEqual(["C|500", "A|230", "B|115"]);
    expect(sortBuses(rows, "x_r", "asc").map((b) => b.bus_id)).toEqual(["A|230", "C|500", "B|115"]);
    expect(sortBuses(rows, "bus_id", "asc").map((b) => b.bus_id)).toEqual(["A|230", "B|115", "C|500"]);
    expect(rows[0]?.bus_id).toBe("B|115"); // no muta
  });

  it("filtra por nombre o subárea sin tildes ni mayúsculas", () => {
    const rows = [bus({ bus_id: "SABANALARGA|230", subarea: "Atlántico" }), bus({ bus_id: "GUAVIO|230", subarea: "Bogotá" })];
    expect(filterBuses(rows, "sabana").map((b) => b.bus_id)).toEqual(["SABANALARGA|230"]);
    expect(filterBuses(rows, "BOGOTA").map((b) => b.bus_id)).toEqual(["GUAVIO|230"]);
    expect(filterBuses(rows, "  ")).toHaveLength(2);
  });

  it("etiqueta métodos y unidades", () => {
    expect(methodLabel("relacion_iec")).toBe("relación R/X de IEC 60909");
    expect(unitLabel("hidráulica:GUATAPE 1")).toBe("GUATAPE 1 (hidráulica)");
    expect(unitLabel("sin prefijo")).toBe("sin prefijo");
  });
});

import cytoscape, { type EdgeSingular, type NodeSingular } from "cytoscape";
import { useEffect, useMemo, useRef, useState } from "react";

import { useBasemap, useTopology } from "../../api/hooks";
import type { Run, TopologyNode } from "../../api/types";
import { BusDetail } from "./BusDetail";
import { busDetail, type BusDetailData } from "./busModel";
import { angleColor, ikssColor, loadingColor, voltageColor } from "./colors";
import {
  BRANCH_FONT_PX,
  BUS_FONT_PX,
  PARALLEL_GAP_PX,
  arrowScale,
  branchLabelBox,
  branchWidthPx,
  busDiameterPx,
  busLabelBoxes,
  LABEL_OFFSET_PX,
  LABEL_POSITIONS,
  overlaps,
  placeLabels,
  ringRadius,
  screenGrowth,
  type Box,
  type LabelCandidate,
  type Obstacle,
} from "./declutter";
import { MAX_SUBSTATION_RADIUS, SAME_SUBSTATION_RADIUS, type BasemapGeometry, geoLayout, geometryPath } from "./geo";
import {
  BRANCH_LABELS,
  BRANCH_LABEL_TEXT,
  BUS_LABELS,
  BUS_LABEL_TEXT,
  type BranchLabel,
  type BusLabel,
  type LabelSelection,
  branchCaption,
  busCaption,
  loadLabelSelection,
  saveLabelSelection,
} from "./labels";
import { STR_ZOOM, busVisible } from "./lod";
import { NO_SUBAREA_COLOR, filterBySubarea, subareaColor } from "./subareas";

type ColorBy = "voltage" | "loading" | "subarea" | "angle" | "shortcircuit";

/** Lee un token de color de la hoja de estilos para que Cytoscape siga el tema (claro u oscuro). */
function cssVar(name: string, fallback: string): string {
  if (typeof window === "undefined") return fallback;
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return v || fallback;
}


function storage(): Storage | null {
  try {
    return typeof window !== "undefined" ? window.localStorage : null;
  } catch {
    return null;
  }
}
type Layout = "logical" | "geo";

interface Props {
  run: Run;
  /** Ikss por barra del cortocircuito (spec 004, HU-9); sin él no se ofrece el modo. */
  scByBus?: Map<string, number> | undefined;
  scMax?: number | undefined;
}

/** Zoom a partir del cual se leen las etiquetas de barras y de flujos (FR-036). */
const LABEL_ZOOM = 2.5;
/** Espera tras el último zoom o desplazamiento antes de recolocar etiquetas y subestaciones. */
const SETTLE_MS = 140;


export function TopologyView({ run, scByBus, scMax = 0 }: Props): JSX.Element {
  const runId = run.run_id;
  const topology = useTopology(runId);
  const [selectedBus, setSelectedBus] = useState<string | null>(null);
  const cyRef = useRef<cytoscape.Core | null>(null);
  // Recoloca las etiquetas sin solapes; la define el efecto que crea el grafo.
  const declutterRef = useRef<(() => void) | null>(null);
  const selectedBusRef = useRef<string | null>(null);
  const busIds = useMemo(
    () => (topology.data?.nodes ?? []).filter((n) => n.in_service).map((n) => n.id).sort(),
    [topology.data],
  );

  /** Selecciona una barra por nombre y centra la vista en ella (FR-036). */
  function focusBus(id: string): void {
    if (!busIds.includes(id)) return;
    setSelectedBus(id);
    const cy = cyRef.current;
    const node = cy?.getElementById(id);
    if (cy && node && node.nonempty()) {
      cy.animate({ center: { eles: node }, zoom: Math.max(cy.zoom(), LABEL_ZOOM * 1.5) }, { duration: 300 });
      cy.nodes().unselect();
      node.select();
    }
  }
  const container = useRef<HTMLDivElement>(null);
  const [colorBy, setColorBy] = useState<ColorBy>("voltage");
  const [subarea, setSubarea] = useState<string | null>(null);
  const [layout, setLayout] = useState<Layout>("geo");
  const [hover, setHover] = useState<string>("");
  const [unplaced, setUnplaced] = useState<string[]>([]);
  const [strVisible, setStrVisible] = useState(false);
  const [labels, setLabels] = useState<LabelSelection>(() => loadLabelSelection(storage()));
  // Reiniciar el mapa reconstruye el grafo (vista, selección y, en la lógica, posiciones).
  const [resetCount, setResetCount] = useState(0);
  // El coloreado se lee por referencia desde los estilos: cambiarlo no reconstruye el grafo.
  const colorByRef = useRef<ColorBy>(colorBy);
  function toggleBusLabel(l: BusLabel): void {
    const bus = labels.bus.includes(l) ? labels.bus.filter((x) => x !== l) : [...labels.bus, l];
    const next = { ...labels, bus };
    setLabels(next);
    saveLabelSelection(storage(), next);
  }
  function toggleBranchLabel(l: BranchLabel): void {
    const branch = labels.branch.includes(l) ? labels.branch.filter((x) => x !== l) : [...labels.branch, l];
    const next = { ...labels, branch };
    setLabels(next);
    saveLabelSelection(storage(), next);
  }
  const basemap = useBasemap(layout === "geo");
  const basemapLayer = useRef<SVGGElement>(null);
  const basemapPaths = useMemo(
    () =>
      (basemap.data?.features ?? []).map((f) => ({
        key: `${f.properties.kind}:${f.properties.name}`,
        kind: f.properties.kind,
        d: geometryPath(f.geometry as BasemapGeometry),
      })),
    [basemap.data],
  );

  const subareas = useMemo(() => topology.data?.subareas ?? [], [topology.data]);
  const allNames = useMemo(() => subareas.map((s) => s.name), [subareas]);
  const selected = subareas.find((s) => s.name === subarea) ?? null;
  const detail: BusDetailData | null = useMemo(() => {
    const data = topology.data;
    if (!data || !selectedBus) return null;
    const node = data.nodes.find((n: TopologyNode) => n.id === selectedBus);
    return node ? busDetail(node, data.edges, run.result?.generators ?? []) : null;
  }, [topology.data, selectedBus, run.result]);

  // Cambiar las etiquetas solo actualiza los textos del grafo existente: conserva zoom y posición.
  useEffect(() => {
    const cy = cyRef.current;
    const data = topology.data;
    if (!cy || !data) return;
    const nodes = new Map(data.nodes.map((n) => [n.id, n]));
    const edges = new Map(data.edges.map((e) => [e.id, e]));
    cy.batch(() => {
      cy.nodes().forEach((ele) => {
        const n = nodes.get(ele.id());
        if (n) ele.data("caption", busCaption(n, labels.bus));
      });
      cy.edges().forEach((ele) => {
        const e = edges.get(ele.id());
        if (e) ele.data("flow_label", branchCaption(e, labels.branch));
      });
    });
    declutterRef.current?.();
  }, [labels, topology.data]);

  // La barra seleccionada siempre muestra su etiqueta.
  useEffect(() => {
    selectedBusRef.current = selectedBus;
    declutterRef.current?.();
  }, [selectedBus]);

  useEffect(() => {
    colorByRef.current = colorBy;
    cyRef.current?.style().update();
  }, [colorBy]);

  // El cortocircuito llega después del grafo: se escribe en los nodos sin reconstruirlo.
  const scByBusRef = useRef<Map<string, number> | undefined>(scByBus);
  const scMaxRef = useRef<number>(scMax);
  useEffect(() => {
    scByBusRef.current = scByBus;
    scMaxRef.current = scMax;
    const cy = cyRef.current;
    if (!cy) return;
    cy.batch(() => {
      cy.nodes().forEach((ele) => {
        ele.data("ikss", scByBus?.get(ele.id()) ?? null);
      });
    });
    cy.style().update();
    if (!scByBus && colorBy === "shortcircuit") setColorBy("voltage");
  }, [scByBus, scMax, colorBy]);

  useEffect(() => {
    const data = topology.data;
    const el = container.current;
    if (!data || !el) return;
    const inService = data.nodes.filter((n) => n.in_service);
    const ids = new Set(inService.map((n) => n.id));
    const view = filterBySubarea(
      inService,
      data.edges.filter((e) => ids.has(e.source) && ids.has(e.target)),
      subarea,
    );
    const geo = layout === "geo" ? geoLayout(view.nodes) : null;
    setUnplaced(geo ? geo.unplaced : []);
    const unplacedIds = new Set(geo ? geo.unplaced : []);
    let zoom = 1;
    // Tamaños en unidades de modelo calculados desde su tamaño en pantalla, que crece con el
    // zoom solo hasta un tope: al acercarse las barras se separan sin crecer sin límite.
    const busSize = (ele: NodeSingular) => busDiameterPx(Number(ele.data("vn_kv")) || 0, zoom) / zoom;
    const edgeWidth = (ele: EdgeSingular) => branchWidthPx(String(ele.data("kind")), zoom) / zoom;
    const stroke = (px: number) => (px * screenGrowth(zoom)) / zoom;
    const labelsVisible = () => zoom >= LABEL_ZOOM;
    const flowArrow = (ele: EdgeSingular, sign: 1 | -1) =>
      labelsVisible() && typeof ele.data("p_from") === "number" && Math.sign(ele.data("p_from")) === sign ? "triangle" : "none";
    const theme = {
      node: cssVar("--graph-node", "#5f6368"),
      border: cssVar("--graph-node-border", "#000000"),
      accent: cssVar("--accent", "#0b5fff"),
      edge: cssVar("--graph-edge", "#8b949e"),
      labelBg: cssVar("--graph-label-bg", "#ffffff"),
      fg: cssVar("--fg", "#1f2328"),
    };
    const cy = cytoscape({
      container: el,
      elements: [
        ...view.nodes.map((n) => ({
          data: {
            id: n.id,
            label: n.label,
            vn_kv: n.vn_kv,
            vm_pu: n.vm_pu,
            violation: n.violation,
            subarea: n.subarea,
            frontier: n.frontier,
            p_gen: n.p_gen_mw ?? 0,
            p_load: n.p_load_mw ?? 0,
            va: n.va_degree ?? null,
            ikss: scByBusRef.current?.get(n.id) ?? null,
            caption: busCaption(n, labels.bus),
          },
        })),
        ...view.edges.map((e) => ({
          data: {
            id: e.id,
            source: e.source,
            target: e.target,
            kind: e.kind,
            loading: e.loading_percent,
            overload: e.overload,
            frontier: e.frontier,
            // Ramas hacia barras sin coordenadas: se atenúan para no cruzar el mapa con trazos falsos.
            unplaced: unplacedIds.has(e.source) || unplacedIds.has(e.target),
            // Flujo con el signo de pandapower: positivo sale de source (FR-036).
            p_from: e.p_from_mw ?? null,
            flow_label: branchCaption(e, labels.branch),
          },
        })),
      ],
      // Factor de tamaño según el zoom actual; se recalcula en cada cambio de zoom.
      // Barras fijas en el mapa (sus coordenadas son datos); arrastrables en la disposición lógica.
      autoungrabify: layout === "geo",
      boxSelectionEnabled: false,
      // Mientras se desplaza o hace zoom no se dibujan las ramas: se repintan al soltar.
      hideEdgesOnViewport: true,
      style: [
        {
          selector: "node",
          style: {
            // Nivel de detalle: con poco zoom solo el STN; Cytoscape oculta también sus ramas.
            display: (ele: NodeSingular) => (busVisible(Number(ele.data("vn_kv")) || 0, zoom) ? "element" : "none"),
            width: busSize,
            height: busSize,
            "background-color": (ele: NodeSingular) => {
              const by = colorByRef.current;
              if (by === "voltage") return voltageColor(ele.data("vm_pu") as number | null);
              if (by === "subarea") return subareaColor(ele.data("subarea") as string | null, allNames);
              if (by === "angle") return angleColor(ele.data("va") as number | null);
              if (by === "shortcircuit") return ikssColor(ele.data("ikss") as number | null, scMaxRef.current);
              return theme.node;
            },
            "background-opacity": (ele: NodeSingular) => (ele.data("frontier") ? 0.35 : 1),
            "border-width": (ele: NodeSingular) => (ele.data("violation") ? stroke(2) : 0),
            "border-color": theme.border,
            // Solo las etiquetas que caben sin solaparse (placeLabels), o la de la barra bajo el cursor.
            label: (ele: NodeSingular) =>
              labelsVisible() && (ele.data("showLabel") || ele.data("hover")) ? String(ele.data("caption")) : "",
            color: theme.fg,
            "text-wrap": "wrap",
            "text-max-width": () => `${400 / zoom}px`,
            "font-size": () => BUS_FONT_PX / zoom,
            // Posición elegida por placeLabels: debajo, encima, a la derecha o a la izquierda.
            "text-valign": (ele: NodeSingular) => {
              const pos = ele.data("labelPos");
              return pos === "top" ? "top" : pos === "right" || pos === "left" ? "center" : "bottom";
            },
            "text-halign": (ele: NodeSingular) => {
              const pos = ele.data("labelPos");
              return pos === "right" ? "right" : pos === "left" ? "left" : "center";
            },
            "text-justification": (ele: NodeSingular) => {
              const pos = ele.data("labelPos");
              return pos === "right" ? "left" : pos === "left" ? "right" : "center";
            },
            "text-margin-y": (ele: NodeSingular) => {
              const pos = ele.data("labelPos");
              return pos === "top" ? -LABEL_OFFSET_PX / zoom : pos === "right" || pos === "left" ? 0 : LABEL_OFFSET_PX / zoom;
            },
            "text-margin-x": (ele: NodeSingular) => {
              const pos = ele.data("labelPos");
              return pos === "right" ? LABEL_OFFSET_PX / zoom : pos === "left" ? -LABEL_OFFSET_PX / zoom : 0;
            },
            // Halo del color del fondo en vez de recuadro: no tapa el mapa ni las ramas vecinas.
            "text-outline-color": theme.labelBg,
            "text-outline-width": () => 2.5 / zoom,
            "text-outline-opacity": 0.9,
            // Las barras rotuladas por encima de las demás, para que ningún disco tape su etiqueta.
            "z-index": (ele: NodeSingular) => (ele.data("hover") ? 10 : ele.data("showLabel") ? 5 : 1),
          },
        },
        {
          selector: "node:selected",
          style: { "border-width": () => stroke(3), "border-color": theme.accent, "z-index": 11 },
        },
        {
          selector: "edge",
          style: {
            width: edgeWidth,
            "line-style": (ele: EdgeSingular) => (ele.data("kind") === "line" ? "solid" : "dashed"),
            "line-color": (ele: EdgeSingular) =>
              colorByRef.current === "loading" ? loadingColor(ele.data("loading") as number | null) : theme.edge,
            "line-opacity": (ele: EdgeSingular) => (ele.data("unplaced") ? 0.12 : ele.data("frontier") ? 0.45 : 1),
            // Rectas, salvo los dobles circuitos, que se separan en curvas para no superponerse.
            "curve-style": "bezier",
            "control-point-step-size": () => PARALLEL_GAP_PX / zoom,
            // Flecha a mitad de la rama, en el sentido del flujo de P: lejos de las barras, donde
            // se amontonan las ramas. Hacia target si p_from > 0, hacia source si < 0.
            "mid-target-arrow-shape": (ele: EdgeSingular) => flowArrow(ele, 1),
            "mid-source-arrow-shape": (ele: EdgeSingular) => flowArrow(ele, -1),
            "mid-target-arrow-color": theme.node,
            "mid-source-arrow-color": theme.node,
            // Tamaño fijo en pantalla con cualquier zoom (ver arrowScale).
            "arrow-scale": (ele: EdgeSingular) => arrowScale(edgeWidth(ele), zoom),
            label: (ele: EdgeSingular) => (labelsVisible() && ele.data("showLabel") ? String(ele.data("flow_label")) : ""),
            color: theme.fg,
            "font-size": () => BRANCH_FONT_PX / zoom,
            "text-rotation": "autorotate",
            "text-outline-color": theme.labelBg,
            "text-outline-width": () => 2.5 / zoom,
            "text-outline-opacity": 0.9,
          },
        },
      ],
      layout: geo
        ? {
            name: "preset",
            positions: Object.fromEntries(geo.positions),
            fit: true,
            padding: 20,
          }
        : { name: "cose", animate: false, numIter: 400, nodeRepulsion: () => 8000, idealEdgeLength: () => 40 },
      wheelSensitivity: 0.2,
    });
    // El mapa base vive en coordenadas de modelo: se mueve con el pan y el zoom del grafo.
    const syncBasemap = () => {
      const g = basemapLayer.current;
      if (!g) return;
      const { x, y } = cy.pan();
      g.setAttribute("transform", `translate(${x},${y}) scale(${cy.zoom()})`);
    };
    cyRef.current = cy;
    cy.on("viewport", syncBasemap);
    syncBasemap();
    zoom = cy.zoom();

    // Reparte las barras visibles de cada subestación en un círculo cuyo tamaño en pantalla
    // evita que se tapen. El centro es la coordenada de PARATEC: no se mueve.
    const spreadSubstations = () => {
      if (!geo) return;
      cy.batch(() => {
        for (const g of geo.groups) {
          const members = g.members.map((id) => cy.getElementById(id)).filter((n) => n.nonempty());
          const shown = members.filter((n) => busVisible(Number(n.data("vn_kv")) || 0, zoom));
          if (shown.length === 0) continue;
          const d = Math.max(...shown.map((n) => busDiameterPx(Number(n.data("vn_kv")) || 0, zoom)));
          const r = ringRadius(shown.length, d, zoom, SAME_SUBSTATION_RADIUS, MAX_SUBSTATION_RADIUS);
          shown.forEach((n, i) => {
            const angle = (2 * Math.PI * i) / shown.length - Math.PI / 2;
            n.position({ x: g.center.x + r * Math.cos(angle), y: g.center.y + r * Math.sin(angle) });
          });
        }
      });
    };

    // Decide qué etiquetas caben sin solaparse ni tapar otras barras, en el orden de prioridad:
    // seleccionada, fuera de límite, mayor tensión, más potencia. Solo mira lo que está en pantalla.
    const declutter = () => {
      if (!labelsVisible()) return;
      const view: Box = { x1: -40, y1: -40, x2: el.clientWidth + 40, y2: el.clientHeight + 40 };
      const discs = new Map<string, { x: number; y: number; d: number }>();
      const obstacles: Obstacle[] = [];
      const busCandidates: LabelCandidate[] = [];
      cy.nodes().forEach((n) => {
        if (!n.visible()) return;
        const p = n.renderedPosition();
        const d = n.renderedWidth();
        const box = { x1: p.x - d / 2, y1: p.y - d / 2, x2: p.x + d / 2, y2: p.y + d / 2 };
        if (!overlaps(box, view)) return;
        discs.set(n.id(), { x: p.x, y: p.y, d });
        obstacles.push({ owner: n.id(), box });
        const text = String(n.data("caption") ?? "");
        if (!text) return;
        const priority =
          (n.data("violation") ? 1e7 : 0) +
          (Number(n.data("vn_kv")) || 0) * 1e4 +
          Math.abs(Number(n.data("p_gen")) || 0) +
          Math.abs(Number(n.data("p_load")) || 0);
        busCandidates.push({ id: n.id(), boxes: busLabelBoxes(p.x, p.y, d, text), priority, force: n.id() === selectedBusRef.current });
      });
      const placed: Box[] = [];
      const busShown = placeLabels(busCandidates, obstacles, placed);
      const branchCandidates: LabelCandidate[] = [];
      cy.edges().forEach((e) => {
        if (!e.visible()) return;
        const a = discs.get(e.source().id());
        const b = discs.get(e.target().id());
        const text = String(e.data("flow_label") ?? "");
        if (!a || !b || !text) return;
        const box = branchLabelBox(a, b, e.renderedMidpoint(), text);
        if (box) branchCandidates.push({ id: e.id(), boxes: [box], priority: (e.data("overload") ? 1e7 : 0) + Math.abs(Number(e.data("p_from")) || 0) });
      });
      const branchShown = placeLabels(branchCandidates, obstacles, placed);
      cy.batch(() => {
        cy.nodes().forEach((n) => {
          const index = busShown.get(n.id());
          const show = index !== undefined;
          if (n.data("showLabel") !== show) n.data("showLabel", show);
          const pos = LABEL_POSITIONS[index ?? 0];
          if (n.data("labelPos") !== pos) n.data("labelPos", pos);
        });
        cy.edges().forEach((e) => {
          const show = branchShown.has(e.id());
          if (e.data("showLabel") !== show) e.data("showLabel", show);
        });
      });
    };
    declutterRef.current = declutter;

    // Tras cada zoom o desplazamiento: subestaciones repartidas, estilos y etiquetas al día.
    let settleTimer = 0;
    const settle = () => {
      spreadSubstations();
      cy.style().update();
      declutter();
    };
    const scheduleSettle = () => {
      window.clearTimeout(settleTimer);
      settleTimer = window.setTimeout(settle, SETTLE_MS);
    };
    cy.on("viewport", scheduleSettle);
    settle();
    let frame = 0;
    let strShown = zoom >= STR_ZOOM;
    setStrVisible(strShown);
    cy.on("zoom", () => {
      zoom = cy.zoom();
      // Un recálculo por cuadro basta: los estilos leen `zoom` al evaluarse.
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => cy.style().update());
      if ((zoom >= STR_ZOOM) !== strShown) {
        strShown = zoom >= STR_ZOOM;
        setStrVisible(strShown);
      }
    });
    cy.on("tap", "node", (evt) => setSelectedBus(String(evt.target.id())));
    cy.on("tap", (evt) => {
      if (evt.target === cy) setSelectedBus(null);
    });
    cy.on("mouseover", "node", (evt) => {
      evt.target.data("hover", true);
      const d = evt.target.data();
      const vm = d.vm_pu !== null ? ` · ${Number(d.vm_pu).toFixed(3)} pu` : "";
      const sa = d.subarea ? ` · ${d.subarea}${d.frontier ? " (vecina)" : ""}` : " · sin subárea";
      const sc = typeof d.ikss === "number" ? ` · Ikss ${Number(d.ikss).toFixed(2)} kA · Sk ${(Math.sqrt(3) * Number(d.vn_kv) * Number(d.ikss)).toFixed(0)} MVA` : "";
      setHover(`${d.label} · ${d.vn_kv} kV${vm}${sa}${sc}`);
    });
    cy.on("mouseover", "edge", (evt) => {
      const d = evt.target.data();
      const ld = d.loading !== null ? ` · ${Number(d.loading).toFixed(1)} %` : "";
      setHover(`${d.id}${ld}${d.frontier ? " · frontera entre subáreas" : ""}`);
    });
    cy.on("mouseout", "node", (evt) => evt.target.data("hover", false));
    cy.on("mouseout", () => setHover(""));
    return () => {
      cancelAnimationFrame(frame);
      window.clearTimeout(settleTimer);
      declutterRef.current = null;
      cyRef.current = null;
      cy.destroy();
    };
    // `labels` y `colorBy` no están en las dependencias a propósito: los aplican los efectos de
    // arriba sin reconstruir el grafo. `resetCount` fuerza la reconstrucción (botón Reiniciar).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [topology.data, subarea, allNames, layout, resetCount]);

  return (
    <section className="topology stack" data-testid="topology">
      <div className="section-head">
        <h2>Topología {layout === "geo" ? "geográfica" : "lógica"}</h2>
        <span className="muted small">
          {strVisible ? "STN y STR visibles" : "solo STN: acerca para ver el STR"} · clic en una barra para su detalle
        </span>
      </div>
      <div className="toolbar">
        <label>
          Colorear por
          <select value={colorBy} onChange={(e) => setColorBy(e.target.value as ColorBy)} data-testid="color-by">
            <option value="voltage">tensión (pu)</option>
            <option value="loading">cargabilidad (%)</option>
            <option value="subarea">subárea</option>
            <option value="angle">ángulo (°)</option>
            {scByBus && <option value="shortcircuit">cortocircuito (kA)</option>}
          </select>
        </label>
        <label>
          Disposición
          <select value={layout} onChange={(e) => setLayout(e.target.value as Layout)} data-testid="layout">
            <option value="logical">lógica</option>
            <option value="geo">geográfica</option>
          </select>
        </label>
        <label>
          Subárea
          <select
            value={subarea ?? ""}
            onChange={(e) => setSubarea(e.target.value === "" ? null : e.target.value)}
            data-testid="subarea-filter"
          >
            <option value="">todas</option>
            {subareas.map((s) => (
              <option key={s.name} value={s.name}>
                {s.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Barra
          <input
            list="bus-ids"
            placeholder="buscar y centrar"
            data-testid="bus-search"
            onChange={(e) => focusBus(e.target.value)}
          />
          <datalist id="bus-ids">
            {busIds.map((id) => (
              <option key={id} value={id} />
            ))}
          </datalist>
        </label>
        {selected &&
          (selected.unifilar_url ? (
            <a href={selected.unifilar_url} target="_blank" rel="noreferrer" data-testid="unifilar-link">
              Ver unifilar de XM ({selected.name})
            </a>
          ) : (
            <span className="muted small">XM no publica unifilar de esta subárea.</span>
          ))}
        <span className="spacer" />
        <button
          type="button"
          onClick={() => {
            setSelectedBus(null);
            setResetCount((c) => c + 1);
          }}
          data-testid="reset-map"
        >
          Reiniciar mapa
        </button>
      </div>
      <div className="toolbar labels" data-testid="label-selectors">
        <span className="muted small">Etiquetas de barra:</span>
        {BUS_LABELS.map((l) => (
          <label key={l} className="inline-check">
            <input type="checkbox" checked={labels.bus.includes(l)} onChange={() => toggleBusLabel(l)} data-testid={`bus-label-${l}`} />
            {BUS_LABEL_TEXT[l]}
          </label>
        ))}
        <span className="muted small">· de rama:</span>
        {BRANCH_LABELS.map((l) => (
          <label key={l} className="inline-check">
            <input type="checkbox" checked={labels.branch.includes(l)} onChange={() => toggleBranchLabel(l)} data-testid={`branch-label-${l}`} />
            {BRANCH_LABEL_TEXT[l]}
          </label>
        ))}
      </div>
      {topology.isLoading && <p className="muted">Cargando topología…</p>}
      {topology.isError && <p className="notice notice--error">No se pudo cargar la topología.</p>}
      {layout === "geo" && basemap.isError && (
        <p className="notice notice--error">No se pudo cargar el mapa base; las barras siguen en su ubicación.</p>
      )}
      <div className="graph-area">
        <div className="graph-wrap">
          <svg className="basemap" aria-hidden="true" style={{ display: layout === "geo" ? "block" : "none" }} data-testid="basemap">
            <g ref={basemapLayer}>
              {basemapPaths.map((p) => (
                <path key={p.key} d={p.d} className={p.kind === "departamento" ? "department" : "neighbor"} />
              ))}
            </g>
          </svg>
          <div ref={container} className="graph" />
          <span className="graph-overlay graph-overlay--hover hover" data-testid="hover">
            {hover}
          </span>
          <span className="graph-overlay graph-overlay--legend legend">
            {colorBy === "voltage" && (
              <>
                <i style={{ background: voltageColor(0.9) }} /> 0,90 pu <i style={{ background: voltageColor(1.0) }} /> 1,00 pu{" "}
                <i style={{ background: voltageColor(1.1) }} /> 1,10 pu
              </>
            )}
            {colorBy === "loading" && (
              <>
                <i style={{ background: loadingColor(0) }} /> 0 % <i style={{ background: loadingColor(50) }} /> 50 %{" "}
                <i style={{ background: loadingColor(100) }} /> ≥ 100 %
              </>
            )}
            {colorBy === "angle" && (
              <>
                <i style={{ background: angleColor(-30) }} /> −30° <i style={{ background: angleColor(0) }} /> 0°{" "}
                <i style={{ background: angleColor(30) }} /> +30°
              </>
            )}
            {colorBy === "shortcircuit" && (
              <span data-testid="sc-legend">
                <i style={{ background: ikssColor(0, scMax || 1) }} /> 0 kA <i style={{ background: ikssColor(scMax / 2, scMax || 1) }} /> {(scMax / 2).toFixed(1)} kA{" "}
                <i style={{ background: ikssColor(scMax, scMax || 1) }} /> {scMax.toFixed(1)} kA (máx. del caso)
              </span>
            )}
            {colorBy === "subarea" && (
              <span data-testid="subarea-legend">
                {subareas.map((s) => (
                  <span key={s.name}>
                    <i style={{ background: subareaColor(s.name, allNames) }} /> {s.name}{" "}
                  </span>
                ))}
                <i style={{ background: NO_SUBAREA_COLOR }} /> sin subárea
              </span>
            )}
          </span>
        </div>
        {detail && <BusDetail detail={detail} onClose={() => setSelectedBus(null)} />}
      </div>
      {layout === "geo" && basemap.data && <p className="hint attribution">{basemap.data.attribution}</p>}
      <p className="hint">
        Líneas continuas, transformadores discontinuos · acerca más para ver G, C y flujos · las etiquetas que no caben se
        ocultan: pasa el cursor por una barra para verla
        {layout === "geo" ? " · barras fijas en su ubicación" : " · barras arrastrables"}
        {subarea && " · barras y ramas de frontera atenuadas"}
        {layout === "geo" && unplaced.length > 0 && (
          <span data-testid="unplaced">
            {" · "}
            {unplaced.length} barras sin coordenadas en PARATEC, en la columna izquierda
          </span>
        )}
      </p>
    </section>
  );
}

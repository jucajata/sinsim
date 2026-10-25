// Tipos escritos a mano que reflejan specs/001-flujo-potencia-despacho/contracts/openapi.yaml.

export interface Problem {
  type: string;
  title: string;
  status: number;
  detail: string;
  code: string;
  user_message: string;
  trace_id: string;
}

export interface SnapshotSummary {
  date: string;
  has_paratec: boolean;
  has_dispatch: boolean;
  has_demand: boolean;
  intact: boolean;
}

export type ScrapeStatus = "en_cola" | "descargando" | "listo" | "error";
export type ScrapeStep = "en_cola" | "paratec" | "despacho_y_demanda" | "normalizacion" | "listo" | "error";

/** Descarga de una fecha pedida desde la interfaz (FR-038); vive en memoria de la API. */
export interface ScrapeJob {
  job_id: string;
  date: string;
  status: ScrapeStatus;
  step: ScrapeStep;
  started_at: string;
  finished_at: string | null;
  snapshot: SnapshotSummary | null;
  error: Problem | null;
  notice: string;
}

export type FlowType = "ac" | "dc";
export type RunStatus = "convergio" | "no_convergio";

export interface CaseRequest {
  snapshot_date: string;
  dispatch_date?: string;
  period: number;
}

export interface Balance {
  p_scheduled_total_mw: number;
  p_located_mw: number;
  p_unlocated_mw: number;
  coverage_pct: number;
  p_demand_mw: number;
  p_demand_unlocated_mw: number;
  difference_mw: number;
}

export interface UnlocatedResource {
  resource: string;
  p_mw: number;
  reason: string;
}

export interface UnlocatedDemand {
  node: string;
  vn_kv: number;
  p_mw: number;
  q_mvar: number;
  reason: string;
}

export interface Transfer {
  element: string;
  kind: "gen" | "demand";
  from_bus: string;
  to_bus: string;
  p_mw: number;
  q_mvar: number;
}

export interface ExcludedElement {
  element: string;
  kind: string;
  missing_params: string[];
}

export interface ImputedValue {
  element: string;
  kind: string;
  param: string;
  method: string;
  value: number;
}

export interface NotModeled {
  element: string;
  kind: string;
  reason: string;
}

export interface Island {
  island_id: number;
  n_buses: number;
  buses: string[];
  p_gen_lost_mw: number;
  p_demand_lost_mw: number;
  energized: boolean;
}

export interface QualityReport {
  unlocated_resources: UnlocatedResource[];
  unlocated_demand: UnlocatedDemand[];
  transfers: Transfer[];
  excluded: ExcludedElement[];
  imputed: ImputedValue[];
  not_modeled: NotModeled[];
  islands: Island[];
  physical_issues: string[];
  /** Barras del modelo sin subárea en PARATEC (FR-034); ausente en casos anteriores. */
  buses_without_subarea?: string[];
  /** Barras del modelo sin coordenadas en PARATEC (FR-035); ausente en casos anteriores. */
  buses_without_coordinates?: string[];
  balance: Balance;
}

export interface CaseInputs {
  snapshot_date: string;
  dispatch_date: string;
  period: number;
  snapshot_manifest_sha256: string;
  equivalences_sha256: string;
  config_sha256: string;
  sinsim_version: string;
}

export interface StudyCase {
  case_id: string;
  inputs: CaseInputs;
  quality: QualityReport;
  assumptions: Record<string, unknown>;
  warnings: string[];
  created_at: string;
}

export interface SolverSettings {
  algorithm: string;
  tolerance_mva: number;
  max_iteration: number;
  init: string;
  enforce_q_lims: boolean;
  distributed_slack: boolean;
}

export interface Trace {
  snapshot_date: string;
  dispatch_date: string;
  period: number;
  flow_type: FlowType;
  pandapower_version: string;
  sinsim_version: string;
  solver: SolverSettings;
  case_id: string;
}

export interface BusMismatch {
  bus: string;
  mismatch_mva: number;
}

export interface Diagnostics {
  iterations: number;
  max_mismatch_mva: number;
  worst_buses: BusMismatch[];
  basis: string;
}

export interface BusResult {
  bus_id: string;
  vn_kv: number;
  vm_pu: number;
  vm_kv: number;
  va_degree: number;
  violation: "low" | "high" | null;
  /** Subárea de PARATEC (FR-034); nula si la subestación no la tiene. */
  subarea?: string | null;
}

export interface BranchResult {
  element_id: string;
  kind: "line" | "trafo2w" | "trafo3w";
  from_bus: string;
  to_bus: string;
  p_from_mw: number;
  q_from_mvar: number;
  p_to_mw: number;
  q_to_mvar: number;
  i_ka: number;
  loading_percent: number;
  pl_mw: number;
  ql_mvar: number;
  overload: boolean;
  subarea_from?: string | null;
  subarea_to?: string | null;
}

export interface GeneratorResult {
  gen_id: string;
  resource: string;
  bus: string;
  p_scheduled_mw: number;
  p_mw: number;
  q_mvar: number;
  slack_adjust_mw: number;
}

export interface LimitInfo {
  name: string;
  value: string;
  source: string;
}

export interface ResultSummary {
  p_gen_mw: number;
  p_load_mw: number;
  p_losses_mw: number;
  slack_adjust_total_mw: number;
  n_voltage_violations: number;
  n_overloads: number;
  limits: LimitInfo[];
  warnings: string[];
  /** Reporte de violaciones (FR-037); ausente en ejecuciones anteriores. */
  violations?: Violation[];
}

/** Violación de límite en el resultado (FR-037). */
export interface Violation {
  kind: "tension_baja" | "tension_alta" | "sobrecarga";
  element: string;
  subarea: string | null;
  value: number;
  limit: number;
  deviation: number;
  unit: "pu" | "%";
  source: string;
}

export interface RunResult {
  buses: BusResult[];
  lines: BranchResult[];
  trafos: BranchResult[];
  generators: GeneratorResult[];
  summary: ResultSummary;
}

export interface Run {
  run_id: string;
  case_id: string;
  flow_type: FlowType;
  status: RunStatus;
  label: string;
  solver: SolverSettings;
  trace: Trace;
  diagnostics: Diagnostics | null;
  result: RunResult | null;
  created_at: string;
}

export interface TopologyNode {
  id: string;
  label: string;
  vn_kv: number;
  vm_pu: number | null;
  violation: "low" | "high" | null;
  in_service: boolean;
  subarea: string | null;
  /** Latitud y longitud WGS84 de la subestación en PARATEC (FR-035); nulas si faltan. */
  lat?: number | null;
  lon?: number | null;
  /** Generación y carga resultantes en la barra (FR-036); 0 si no hay. */
  p_gen_mw?: number;
  q_gen_mvar?: number;
  p_load_mw?: number;
  q_load_mvar?: number;
  /** Componentes de la carga activa (FR-014); nulos en casos anteriores. */
  p_load_act_mw?: number | null;
  p_load_pstr_mw?: number | null;
  vm_kv?: number | null;
  va_degree?: number | null;
  slack_adjust_mw?: number;
}

export interface TopologyEdge {
  id: string;
  source: string;
  target: string;
  kind: "line" | "trafo2w" | "trafo3w";
  loading_percent: number | null;
  overload: boolean;
  /** Flujo con el signo de pandapower: positivo sale de `source` (FR-036); nulo sin resultado. */
  p_from_mw?: number | null;
  q_from_mvar?: number | null;
  p_to_mw?: number | null;
  q_to_mvar?: number | null;
  i_ka?: number | null;
  pl_mw?: number | null;
  ql_mvar?: number | null;
}

/** Subárea presente en la red, con el enlace al unifilar oficial de XM si existe (FR-034). */
export interface SubareaLink {
  name: string;
  unifilar_url: string | null;
}

export interface Topology {
  nodes: TopologyNode[];
  edges: TopologyEdge[];
  subareas: SubareaLink[];
}

/** Supuesto por generador (FR-018): consigna y límites de reactiva asignados, con su fuente. */
export interface GeneratorAssumption {
  gen_id: string;
  barra: string;
  vm_pu: number;
  fuente_vm: string;
  q_min_mvar: number | null;
  q_max_mvar: number | null;
  fuente_q: string;
}

/** Demanda activa de una barra con sus dos componentes conservados (FR-014). */
export interface DemandByBus {
  barra: string;
  p_act_mw: number;
  p_pstr_mw: number;
  q_mvar: number;
}

/** Mapa base vectorial (FR-035): GeoJSON de departamentos de Colombia y países vecinos. */
export interface BasemapFeature {
  type: "Feature";
  properties: { kind: "departamento" | "pais_vecino"; name: string };
  geometry: { type: "Polygon" | "MultiPolygon"; coordinates: number[][][] | number[][][][] };
}

export interface Basemap {
  type: "FeatureCollection";
  attribution: string;
  features: BasemapFeature[];
}

// --- Contingencias N-1 (specs/003-contingencias-n1/contracts/openapi-n1.yaml) ---

export type OutageKind = "line" | "trafo2w" | "gen" | "compensador";
export type N1Status = "en_cola" | "calculando" | "listo" | "error";

export interface Outage {
  element_id: string;
  kind: OutageKind;
  subarea: string | null;
  angle_ref_moved_to: string | null;
}

export interface Isolation {
  n_buses: number;
  p_demand_lost_mw: number;
}

export interface LoadingRow {
  rank: number;
  outage: Outage;
  element_id: string;
  loading_base_percent: number;
  loading_percent: number;
  n_elements: number;
  isolation: Isolation | null;
}

export interface VoltageRow {
  rank: number;
  outage: Outage;
  bus_id: string;
  vm_base_pu: number;
  vm_pu: number;
  /** Negativa en subtensión, positiva en sobretensión. */
  deviation_pu: number;
  n_buses: number;
  isolation: Isolation | null;
}

export interface IsolationRow {
  rank: number;
  outage: Outage;
  n_buses: number;
  p_demand_lost_mw: number;
}

export interface UnsolvedRow {
  outage: Outage;
  diagnostics: Diagnostics;
}

export interface N1Summary {
  n_total: number;
  n_loading: number;
  n_voltage: number;
  n_isolation: number;
  n_unsolved: number;
  n_no_impact: number;
  duration_s: number;
}

export interface N1Analysis {
  run_id: string;
  trace: Trace;
  limits: LimitInfo[];
  analyzed_at: string;
  workers: number;
  summary: N1Summary;
  loading: LoadingRow[];
  voltage: VoltageRow[];
  isolation: IsolationRow[];
  unsolved: UnsolvedRow[];
}

export interface N1Job {
  job_id: string;
  run_id: string;
  status: N1Status;
  done: number;
  total: number;
  started_at: string;
  finished_at: string | null;
  result: N1Analysis | null;
  error: Problem | null;
}

// --- Cortocircuito IEC 60909 (spec 004, contracts/openapi-sc.yaml) ----------------------------

export type ScSourceKind = "sincrona" | "convertidor";
export type ScMethod = "publicado" | "mediana" | "relacion_iec" | "derivado_p_cosphi" | "tension_elevador" | "tension_barra";

export interface ScBusResult {
  bus_id: string;
  substation: string | null;
  subarea: string | null;
  nominal_kv: number;
  base_kv: number;
  ikss_ka: number;
  skss_mva: number;
  rk_ohm: number | null;
  xk_ohm: number | null;
  x_r: number | null;
  no_source: boolean;
}

export interface ScSource {
  unit_id: string;
  kind: ScSourceKind;
  bus_id: string;
  step_up_trafo_id: string | null;
  sn_mva: number;
  vn_kv: number;
  cos_phi: number | null;
  xdss_pu: number | null;
  rdss_ohm: number | null;
  k: number | null;
  origins: Record<string, ScMethod>;
}

export interface ScImputed {
  unit_id: string;
  parameter: string;
  value: number;
  method: ScMethod;
}

export interface ScZeroSource {
  resource: string;
  bus_id: string;
  reason: string;
}

export interface ScExcluded {
  unit_id: string;
  reason: string;
}

export interface StepUpStats {
  matched: number;
  by_method: Record<string, number>;
  curated: number;
  uncurated: number;
}

export interface ScQuality {
  imputed: ScImputed[];
  generators_without_step_up: string[];
  sc_zero_sources: ScZeroSource[];
  excluded: ScExcluded[];
  step_up_equivalences: StepUpStats;
}

export interface ScExtreme {
  bus_id: string;
  value: number;
}

export interface ScSummary {
  n_buses: number;
  max_ikss: ScExtreme | null;
  min_skss: ScExtreme | null;
  n_sources_sync: number;
  n_sources_converter: number;
  n_imputed_units: number;
  n_without_step_up: number;
  n_no_source: number;
  duration_s: number;
}

export interface ScAssumption {
  id: string;
  text: string;
  source: string;
}

export interface ShortCircuitAnalysis {
  case_id: string;
  run_id: string;
  case_hash: string;
  sc_config_hash: string;
  trace: Trace;
  norm: { standard: string; fault: "3ph"; case: "max"; c_max: number };
  config: Record<string, unknown>;
  assumptions: ScAssumption[];
  calculated_at: string;
  summary: ScSummary;
  buses: ScBusResult[];
  sources: ScSource[];
  quality: ScQuality;
  attribution: string;
}

export type Origin =
  | "archive"
  | "current_snapshot"
  | "synthetic"
  | "public_sensor";
export type Execution = "real_provider" | "mock" | "unavailable";
export interface Provenance {
  source_url: string;
  captured_at: string | null;
  processed_at: string;
  data_origin: Origin;
  execution_mode: Execution;
  freshness: "fresh" | "stale" | "unknown";
  notes: string[];
}
export interface Camera {
  id: string;
  name: string;
  borough: string | null;
  corridor: string | null;
  lat: number | null;
  lon: number | null;
  coordinate_precision: string;
  coordinate_source: string;
  capability: string;
  status: string;
  snapshot_url: string | null;
  source_url: string;
  provenance: Provenance;
}
export interface MediaAsset {
  id: string;
  name: string;
  camera_id: string | null;
  location: string;
  coordinate_precision: string;
  lat: number | null;
  lon: number | null;
  source_uri: string | null;
  original_video: string | null;
  duration_sec: number;
  playback_url: string | null;
  capability: string;
  provenance: Provenance;
}
export interface EvidenceSpan {
  reasoning_model?: string;
  id: string;
  asset_id: string;
  source_uri: string | null;
  start_sec: number;
  end_sec: number;
  summary: string;
  provenance: Provenance;
}
export interface Detection {
  id: string;
  evidence_id: string;
  class_name: string;
  confidence: number;
  timestamp_sec: number;
  bbox: [number, number, number, number];
  bbox_units: "normalized" | "pixels";
  track_id: string | null;
  model: string;
  execution_mode: Execution;
}
export interface Track {
  id: string;
  detection_ids: string[];
  method: string;
  source: string;
  calibrated: boolean;
}
export interface Incident {
  id: string;
  title: string;
  description: string;
  severity: "high" | "medium" | "low";
  status: string;
  camera_id: string | null;
  asset_id?: string | null;
  road_id: string | null;
  evidence_ids: string[];
  timestamp: string;
  confidence: number | null;
  data_origin: Origin;
  recommendation: string | null;
}
export interface RoadSegment {
  id: string;
  name: string;
  geometry: { type: "LineString"; coordinates: number[][] };
  length_m: number;
  lanes: number;
  speed_limit_kph: number;
  provenance: Provenance;
}
export interface RiskCell {
  id: string;
  road_id: string;
  score: number | null;
  level: "high" | "medium" | "low" | "unknown" | "stale";
  confidence: number;
  coverage: number;
  factors: unknown[];
  evidence_ids: string[];
  observed_at: string | null;
  data_origin: Origin;
}
export interface ProviderStatus {
  id: string;
  name: string;
  status: string;
  detail: string;
  checked_at: string | null;
  latency_ms: number | null;
  model: string | null;
}
export interface AgentActivity {
  id: string;
  agent: string;
  status: string;
  message: string;
  timestamp: string;
  evidence_ids: string[];
  execution_mode: Execution;
  latency_ms: number | null;
}
export interface Overview {
  mode: "demo" | "connected";
  updated_at: string;
  cameras: Camera[];
  assets: MediaAsset[];
  incidents: Incident[];
  roads: RoadSegment[];
  risk: RiskCell[];
  integrations: ProviderStatus[];
  activity: AgentActivity[];
  metrics: {
    cameras: number;
    assets: number;
    open_incidents: number;
    observations: number;
  };
  notes: string[];
}
export interface EvidenceBundle {
  reasoning_models?: string[];
  asset: MediaAsset;
  evidence: EvidenceSpan[];
  detections: Detection[];
  tracks: Track[];
  reasoning: string;
  availability: { detections: unknown; tracking: unknown; reasoning: unknown };
  provenance: Provenance;
}
export interface SearchHit {
  id: string;
  asset_id: string;
  evidence_id: string;
  source_uri: string;
  original_video: string;
  start_sec: number;
  end_sec: number;
  summary: string;
  score: number;
  camera_id: string | null;
  location: string;
  provenance: Provenance;
}
export interface SearchResponse {
  query: string;
  results: SearchHit[];
  chunk_results: Record<string, unknown>[];
  engine: string;
  execution_mode: Execution;
  notes: string[];
}
export interface ForecastRun {
  id: string;
  state: string;
  road_id: string;
  issued_at: string;
  mode: string;
  data_origin: Origin;
  execution_mode: Execution;
  horizons: {
    minutes: number;
    speed_kph: number | null;
    travel_time_sec: number | null;
    lower_kph: number | null;
    upper_kph: number | null;
  }[];
  evaluation: Record<string, unknown>;
  assumptions: string[];
  provenance: Provenance;
}
export interface SimulationScenario {
  name: string;
  network_id: string;
  duration_sec: number;
  demand_vph: number;
  blockage_start_sec: number;
  early_clearance_sec: number;
  late_clearance_sec: number;
  seeds: number[];
}
export interface SimulationRun {
  id: string;
  job_id: string;
  state: string;
  scenario: SimulationScenario;
  engine: string;
  data_origin: Origin;
  execution_mode: Execution;
  baseline: Record<string, unknown>;
  early: Record<string, unknown>;
  late: Record<string, unknown>;
  comparison: Record<string, unknown>;
  assumptions: string[];
  playback_url: string | null;
  created_at: string;
}
export interface VehicleState {
  id: string;
  lon: number;
  lat: number;
  speed_kph: number;
}
export interface Playback {
  network_id: string;
  frame_interval_sec: number;
  frames: {
    time_sec: number;
    baseline: VehicleState[];
    early: VehicleState[];
    late: VehicleState[];
  }[];
  data_origin: "synthetic";
}
export interface Job {
  id: string;
  kind: string;
  state: "queued" | "running" | "succeeded" | "failed" | "cancelled";
  progress: number;
  created_at: string;
  updated_at: string;
  result: SimulationRun | Record<string, unknown> | null;
  error: unknown;
}
export interface Answer {
  answer: string;
  evidence_ids: string[];
  provider: string;
  model: string;
  execution_mode: Execution;
  latency_ms: number | null;
  notes: string[];
}
export type Workspace = "context" | "archive" | "scenario";
export interface Layers {
  cameras: boolean;
  risk: boolean;
  forecast: boolean;
  simulation: boolean;
  buildings: boolean;
}

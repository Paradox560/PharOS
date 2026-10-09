"""Canonical application entities and bounded API inputs (UTC, WGS84, SI units)."""
from datetime import datetime, timezone
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


Origin = Literal['archive', 'current_snapshot', 'synthetic', 'public_sensor']
Execution = Literal['real_provider', 'mock', 'unavailable']
JobState = Literal['queued', 'running', 'succeeded', 'failed', 'cancelled']


class Entity(BaseModel):
    model_config = ConfigDict(extra='allow')


class Provenance(Entity):
    source_url: str
    captured_at: str | None = None
    processed_at: str = Field(default_factory=utcnow)
    data_origin: Origin
    execution_mode: Execution
    freshness: Literal['fresh', 'stale', 'unknown'] = 'unknown'
    notes: list[str] = Field(default_factory=list)


class Camera(Entity):
    id: str
    name: str
    borough: str | None = None
    corridor: str | None = None
    lat: float | None = Field(None, ge=-90, le=90)
    lon: float | None = Field(None, ge=-180, le=180)
    coordinate_precision: str = 'unlocated'
    coordinate_source: str = ''
    capability: Literal['public_snapshot', 'indexed_archive', 'approved_video', 'approved_stream']
    status: str
    snapshot_url: str | None = None
    source_url: str
    provenance: Provenance


class MediaAsset(Entity):
    id: str
    name: str
    camera_id: str | None = None
    location: str = 'Unlocated'
    coordinate_precision: str = 'unlocated'
    lat: float | None = None
    lon: float | None = None
    source_uri: str | None = None
    original_video: str | None = None
    duration_sec: float = Field(0, ge=0)
    playback_url: str | None = None
    capability: str
    provenance: Provenance


class EvidenceSpan(Entity):
    id: str
    asset_id: str
    source_uri: str | None = None
    start_sec: float = Field(ge=0)
    end_sec: float = Field(ge=0)
    summary: str
    provenance: Provenance

    @model_validator(mode='after')
    def valid_interval(self):
        if self.end_sec < self.start_sec:
            raise ValueError('Evidence end must follow start')
        return self


class Detection(Entity):
    id: str
    evidence_id: str
    class_name: str
    confidence: float = Field(ge=0, le=1)
    timestamp_sec: float = Field(ge=0)
    bbox: tuple[float, float, float, float]
    bbox_units: Literal['normalized', 'pixels']
    track_id: str | None = None
    model: str
    execution_mode: Execution


class Track(Entity):
    id: str
    detection_ids: list[str]
    method: str
    source: Literal['upstream', 'application']
    calibrated: bool = False


class Observation(Entity):
    id: str
    evidence_id: str
    road_id: str | None = None
    kind: str
    summary: str
    confidence: float = Field(ge=0, le=1)
    observed_at: str
    factors: dict[str, Any] = Field(default_factory=dict)
    provenance: Provenance


class Incident(Entity):
    id: str
    title: str
    description: str
    severity: Literal['high', 'medium', 'low']
    status: Literal['open', 'acknowledged'] = 'open'
    camera_id: str | None = None
    asset_id: str | None = None
    road_id: str | None = None
    evidence_ids: list[str]
    timestamp: str
    confidence: float | None = Field(None, ge=0, le=1)
    data_origin: Origin
    recommendation: str | None = None


class RoadSegment(Entity):
    id: str
    name: str
    geometry: dict[str, Any]
    length_m: float = Field(gt=0)
    lanes: int = Field(gt=0)
    speed_limit_kph: float = Field(gt=0)
    provenance: Provenance


class RiskCell(Entity):
    id: str
    road_id: str
    score: float | None = Field(None, ge=0, le=100)
    level: Literal['high', 'medium', 'low', 'unknown', 'stale']
    confidence: float = Field(ge=0, le=1)
    coverage: float = Field(ge=0, le=1)
    factors: list[dict[str, Any]]
    evidence_ids: list[str]
    observed_at: str | None
    data_origin: Origin


class SearchHit(Entity):
    id: str
    asset_id: str
    evidence_id: str
    source_uri: str | None
    original_video: str | None
    start_sec: float
    end_sec: float
    summary: str
    score: float
    camera_id: str | None
    location: str
    provenance: Provenance


class ForecastRun(Entity):
    id: str
    state: str
    road_id: str
    issued_at: str
    mode: str
    data_origin: Origin
    execution_mode: Execution
    horizons: list[dict[str, Any]]
    evaluation: dict[str, Any]
    assumptions: list[str]
    provenance: Provenance


class Input(BaseModel):
    model_config = ConfigDict(extra='forbid')


class SimulationScenario(Input):
    name: str = Field('Earlier vs later clearance', min_length=1, max_length=120)
    network_id: Literal['nyc-demo-corridor'] = 'nyc-demo-corridor'
    duration_sec: int = Field(600, ge=300, le=1800)
    demand_vph: int = Field(900, ge=100, le=2400)
    blockage_start_sec: int = Field(60, ge=0)
    early_clearance_sec: int = Field(180, gt=0)
    late_clearance_sec: int = Field(420, gt=0)
    seeds: list[int] = Field(default_factory=lambda: [42], min_length=1, max_length=3)

    @model_validator(mode='after')
    def timeline(self):
        if not self.blockage_start_sec < self.early_clearance_sec < self.late_clearance_sec < self.duration_sec:
            raise ValueError('Require blockage_start < early_clearance < late_clearance < duration')
        if len(set(self.seeds)) != len(self.seeds) or any(s < 0 or s > 2147483647 for s in self.seeds):
            raise ValueError('Seeds must be unique integers in [0, 2147483647]')
        return self


class SimulationRun(Entity):
    id: str
    job_id: str
    state: JobState
    scenario: SimulationScenario
    engine: str
    data_origin: Literal['synthetic'] = 'synthetic'
    execution_mode: Execution
    baseline: dict[str, Any]
    early: dict[str, Any]
    late: dict[str, Any]
    comparison: dict[str, Any]
    assumptions: list[str]
    playback_url: str
    created_at: str


class AgentActivity(Entity):
    id: str
    agent: str
    status: str
    message: str
    timestamp: str
    evidence_ids: list[str] = Field(default_factory=list)
    execution_mode: Execution
    latency_ms: float | None = None


class ProviderStatus(Entity):
    id: str
    name: str
    status: Literal['ready', 'unverified', 'unavailable', 'error', 'demo']
    detail: str
    checked_at: str | None = None
    latency_ms: float | None = None
    model: str | None = None


class Job(Entity):
    id: str
    kind: str
    state: JobState
    progress: float = Field(ge=0, le=1)
    created_at: str
    updated_at: str
    result: dict[str, Any] | None = None
    error: dict[str, Any] | None = None


class SearchRequest(Input):
    query: str = Field(min_length=1, max_length=1000)
    top_k: int = Field(10, ge=1, le=100)
    time_filter: Literal['all', '5m', '15m', '1h', '24h', '7d'] = 'all'
    metadata_filters: dict[str, str] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list, max_length=20)


class AskRequest(Input):
    question: str = Field(min_length=1, max_length=2000)
    asset_id: str | None = None
    incident_id: str | None = None
    simulation_id: str | None = None
    forecast_id: str | None = None


class AnalysisRequest(Input):
    asset_id: str = Field(min_length=1, max_length=200)


class ForecastRequest(Input):
    road_id: str
    horizons: list[Literal[5, 15, 30]] = Field(default_factory=lambda: [5, 15, 30], min_length=1, max_length=3)
    mode: Literal['illustrative', 'persistence'] = 'illustrative'


class ReingestPreviewRequest(Input):
    asset_id: str
    prompt: str = Field(min_length=1, max_length=800)
    keep_metadata: Literal[True] = True


class ReingestRequest(Input):
    preview_id: str
    confirmed: Literal[True]

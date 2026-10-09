# PharOS shared build contract v1

PHAROS_BUILD_PROMPT.txt is authoritative. Root owns this contract and backend/models.py; workers propose changes.

## Runtime and provenance
FastAPI (Python 3.12), SQLite local state, React/TypeScript/Vite, MapLibre GL JS. All JSON snake_case. Internal routes `/api`; frontend computes relative base from document URL (including `/app/`). Ingress strips `/app`; backend serves compiled frontend. UTC ISO8601 with Z; coordinates WGS84 [longitude, latitude]; seconds, metres, km/h. `data_origin` = archive | current_snapshot | synthetic | public_sensor. `execution_mode` = real_provider | mock | unavailable. Staleness independent. Unknown coordinate = null, never a guessed point. Demo fixture metrics deterministic and explicitly synthetic.

## Canonical entities (additional documented fields permitted)
- Provenance: source_url, captured_at|null, processed_at, data_origin, execution_mode, freshness (fresh|stale|unknown), notes[].
- Camera: id, name, borough|null, corridor|null, lat|null, lon|null, coordinate_precision (catalog|road|approximate|unlocated), coordinate_source, capability (public_snapshot|indexed_archive|approved_video|approved_stream), status (available|cached|unavailable|demo), snapshot_url|null, source_url, provenance.
- MediaAsset: id, name, camera_id|null, location, coordinate_precision, lat|null, lon|null, source_uri|null, original_video|null, duration_sec, playback_url|null, capability, provenance.
- EvidenceSpan: id, asset_id, source_uri|null, start_sec, end_sec, summary, provenance.
- Detection: id, evidence_id, class_name, confidence, timestamp_sec, bbox [x1,y1,x2,y2], bbox_units (normalized|pixels), track_id|null, model, execution_mode.
- Track: id, detection_ids[], method, source (upstream|application), calibrated=false. Only valid temporal input supports tracks.
- Observation: id, evidence_id, road_id|null, kind, summary, confidence, observed_at, factors{}, provenance.
- Incident: id, title, description, severity (high|medium|low), status (open|acknowledged), camera_id|null, road_id|null, evidence_ids[], timestamp, confidence, data_origin, recommendation|null.
- RoadSegment: id, name, geometry GeoJSON LineString, length_m, lanes, speed_limit_kph, provenance.
- RiskCell: id, road_id, score|null, level (high|medium|low|unknown|stale), confidence, coverage, factors[], evidence_ids[], observed_at|null, data_origin. Score is priority, never collision probability.
- SearchHit: id, asset_id, evidence_id, source_uri, original_video, start_sec, end_sec, summary, score, camera_id|null, location, provenance.
- ForecastRun: id, state, road_id, issued_at, mode (persistence|historical|regression|illustrative), data_origin, execution_mode, horizons[{minutes,speed_kph,travel_time_sec,lower_kph,upper_kph}], evaluation{}, assumptions[], provenance.
- SimulationScenario: name, network_id='nyc-demo-corridor', duration_sec (300..1800 default 600), demand_vph (100..2400 default 900), blockage_start_sec=60, early_clearance_sec=180, late_clearance_sec=420, seeds=[42]. Immutable. Synthetic demand, separate from archive.
- SimulationRun: id, job_id, state, scenario, engine, data_origin=synthetic, execution_mode, baseline{}, early{}, late{}, comparison{}, assumptions[], playback_url, created_at.
- AgentActivity: id, agent (perception|context|retrieval|forecast|simulation|operations), status, message, timestamp, evidence_ids[], execution_mode, latency_ms|null.
- ProviderStatus: id, name, status (ready|unverified|unavailable|error|demo), detail, checked_at|null, latency_ms|null, model|null. Credentials alone yield unverified.
- Job: id, kind, state (queued|running|succeeded|failed|cancelled), progress (0..1), created_at, updated_at, result|null, error|null. Cancellation terminal; restart fails interrupted work explicitly.
- Error envelope: {error:{code,message,details?}}. No secrets/upstream credential URLs.

## API
- GET /api/health -> {status,version,mode}
- GET /api/overview -> {mode:'demo'|'connected',updated_at,cameras:Camera[],assets:MediaAsset[],incidents:Incident[],roads:RoadSegment[],risk:RiskCell[],integrations:ProviderStatus[],activity:AgentActivity[],metrics:{cameras,assets,open_incidents,observations},notes:string[]}
- GET /api/integrations -> {integrations}; POST /api/integrations/check -> same (actual diagnostics)
- GET /api/cameras?borough=&q= -> {cameras,source,status}; GET /api/cameras/{id}/snapshot -> image bytes from verified catalog only
- POST /api/sources/refresh -> {cameras,sources,records,status}; GET /api/context -> {sources,records}
- GET /api/archive?limit=24&offset=0 -> {assets,mode,status,total}; GET /api/assets/{id}/evidence -> {asset,evidence:EvidenceSpan[],detections:Detection[],tracks:Track[],reasoning:string,availability:{detections,tracking,reasoning},provenance}
- GET /api/assets/{id}/media -> seekable bytes via same-origin proxy; IDs registered from archive/search; no arbitrary URL.
- GET /api/metadata -> discovered upstream schema; POST /api/search {query,top_k=10,time_filter='all',metadata_filters={},tags=[]} -> {query,results:SearchHit[],chunk_results:dict[],engine,execution_mode,notes[]}. Explicit demo keyword fallback never semantic.
- POST /api/ask {question,asset_id?,incident_id?,simulation_id?,forecast_id?} -> {answer,evidence_ids[],provider,model,execution_mode,latency_ms,notes[]}. Demo deterministic brief clearly identified; live W&B gets structured evidence.
- POST /api/analysis/jobs {asset_id} -> Job; loads stored evidence, does not pretend to run new pipeline inference.
- POST /api/reingest/preview {asset_id,prompt,keep_metadata:true} -> {preview_id,target,prompt,metadata,chunk_count:1,requires_confirmation:true}; POST /api/reingest/jobs {preview_id,confirmed:true} -> Job (feature flag disabled by default, exact preview confirmation).
- GET /api/jobs/{id} -> Job; POST /api/jobs/{id}/cancel -> Job
- GET /api/incidents -> {incidents}; POST /api/incidents/{id}/acknowledge -> Incident
- GET /api/roads -> {roads}; GET /api/risk -> {cells,legend,notes}
- POST /api/forecasts {road_id,horizons:[5,15,30],mode:'illustrative'|'persistence'} -> ForecastRun; GET /api/forecasts/{id} -> ForecastRun
- POST /api/simulations SimulationScenario -> Job; Job.result -> SimulationRun. GET /api/simulations/{id} -> SimulationRun; GET /api/simulations/{id}/playback -> {network_id,frame_interval_sec,frames:[{time_sec,baseline:[{id,lon,lat,speed_kph}],early:[],late:[]}],data_origin:'synthetic'}
- GET /api/events -> SSE job/activity updates; POST /api/demo -> overview (idempotent seed, never deletes real state)
- POST /api/clips -> 403 uploads_disabled. No arbitrary Internet ingestion.

## Worker interfaces / ownership
Root: config.py Settings frozen dataclass lowercase env attributes; errors.py ProviderError(code,message,status_code=503); models.py; fixtures.py; store.py; jobs.py; app.py; shared Python manifests; deploy/; scripts except discovery; tests/test_api.py; README.
Worker A: frontend/** including package.json/lock (React 19, Vite 7, TypeScript 5, MapLibre 5 pinned exact versions). Consumes contract; filters, selection, seek, layers/time/scenarios functional. No root/backend edits.
Worker B wave 1: backend/data_adapters/**, backend/ingestion/**, scripts/discover_sources*, tests/ingestion/**, docs/FEEDS.md. `PublicSources(settings)` async cameras()->dict, context()->dict, snapshot(camera)->(bytes,content_type), refresh()->dict. Include a checked catalog sample in own dir for no-network cold start, truthful captured_at. `ArchiveAdapter(client)` async inventory(limit,offset)->dict and metadata()->dict. `ReingestionAdapter(client)` async preview(asset,prompt,keep_metadata)->dict, submit(preview)->dict, status(upstream_id)->dict. Client injected, root owns actual mutations. No config, app, requirements, frontend edits.
Worker C wave 1: backend/retrieval/**, backend/inference/**, services/tracking/**, tests/inference/**, docs/INTEGRATIONS.md. `VSSClient(settings, transport=None)` async request(method,path,json=None,params=None), close(); handles JWT cache/401 once, safe errors, prefix /api/v1. `RetrievalAdapter(client)` async search(payload)->dict, evidence(asset)->dict, ask(payload)->dict, media(asset,range_header=None)->httpx.Response streaming with cleanup owned by caller, synthesize(payload)->dict. `OperationsAgent(settings,transport=None)` async recommend(question,context)->dict, diagnostics()->ProviderStatus; `diagnostics(settings,client)` returns ProviderStatus list. Settings fields lowercase actual env names; ask root for additions. Normalize canonical schema, never invent location. No config, app, manifests, frontend edits.
Wave 2 B: backend/forecasting/**, backend/risk/**, tests/forecasting/**, docs/FORECASTING.md. C: backend/simulation/**, simulation/**, tests/simulation/**, docs/SIMULATION.md. Interfaces agreed with root before wave.

## Verification
Fixtures do not establish live integrations. Preserve exact URIs/timings and segment vs parent distinction. Real provider failure explicit, never silently replaced by fixtures. Include meaningful protocol/failure tests. Return files, commands/results, assumptions, blocked access, limitations. Do not commit/push/deploy. Shared archive changes root only after exact request and authorization.

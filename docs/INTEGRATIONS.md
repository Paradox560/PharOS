# Model evidence and provider integration

Implemented 2026-10-09 against the [official workshop retrieval skills](https://github.com/vast-data/vast-builders-challenge/tree/main/.cursor/skills/retrieval) and [architecture reference](https://github.com/vast-data/vast-builders-challenge/blob/main/ARCHITECTURE_REFERENCE.md). Protocol tests are local mock-transport verification; they do not establish live provider usage.

## VSS transport and evidence

`backend.retrieval.VSSClient(settings, transport=None)` provides async `request(method,path,json=None,params=None)` returning parsed JSON, `stream(path,params=None,headers=None)` returning an open `httpx.Response`, and `close()`. All paths remain under the configured INGRESS_URL `/api/v1`. JWT login is cached; a 401 causes exactly one refresh and retry. Concurrent refreshes share a lock. Errors use fixed, redacted messages. The proxy caller must close the stream and forward only media headers: Content-Type, Content-Length, Content-Range, Accept-Ranges. Never serialize a Response or its request URL: upstream playback puts JWT in the query string.

`RetrievalAdapter(client)` implements `search`, `evidence`, `ask`, `synthesize`, and `media`. Parent and segment URIs are preserved exactly, including URI escaping; parents are identified with `stable_id(original_video)`. Search retains separate segment `results` and parent `chunk_results`; no local embedding index exists. Metadata filters are validated against schema/values endpoints. Search disables upstream optional synthesis (`llm_top_n=0`), while archive Q&A and parent reports use their documented endpoints explicitly. PharOS operational advice uses W&B separately.

Evidence inspects up to 12 returned timeline segments or the preview segment. It fetches stored metadata/Cosmos reasoning and YOLO sidecars. A missing 404 sidecar produces unavailable detections/tracks. It never starts fresh pipeline inference. Unknown geography remains unlocated. A current retrieval timestamp does not mean the footage is current.

Supported sidecars are `frames[]` containing timestamp_sec/time_sec/timestamp plus detections/objects, or timestamped flat detections. Bounding boxes require xyxy, class, confidence, and valid timestamp. Aggregate counts and untimed detections cannot create trajectories. Segment timestamps are shifted by the segment start; an explicit `time_reference: parent` bypasses that offset. This convention and the exact live sidecar schema must be checked against the assigned team's response before calling frame alignment verified.

Upstream track IDs are displayed only with detections at multiple timestamps. Otherwise a separate application image-space IoU association can group same-class overlapping boxes within one second. Tracks have source=application and calibrated=false. This is a limited overlap tracker, not a physical velocity estimate, world-coordinate projection, or validated identity tracker. Sparse public snapshots never enter it.

## W&B agent

`backend.inference.OperationsAgent(settings,transport=None)` exposes async `recommend(question,context)`, `diagnostics()`, and `close()`. Required settings are WANDB_API_KEY, WANDB_TEAM, WANDB_PROJECT, WANDB_MODEL. WANDB_BASE_URL defaults to `https://api.inference.wandb.ai/v1`. Usage attribution is `OpenAI-Project: team/project`.

The [official W&B inference page](https://wandb.ai/site/inference/) still publishes that OpenAI-compatible endpoint and an example with `moonshotai/Kimi-K2-Instruct`; the [official W&B tutorial](https://forge.coreweave.com/wandb/wandb_fc/genai-research/reports/Tutorial-Running-inference-with-Llama-3-3-70B-using-W-B-Inference--VmlldzoxNDI0Mzg3Nw) demonstrates `meta-llama/Llama-3.3-70B-Instruct`. Models change, so PharOS requires an explicit configured model and checks `/models` instead of silently selecting a model. The old docs.wandb.ai/inference URL currently redirects to CoreWeave documentation. A successful catalog call stays unverified for actual recommendation inference.

The agent receives structured context and an allowlist of entity IDs. Each returned claim/recommendation must cite known IDs; invalid or absent citations reject the response rather than publish unsupported output. This validates citation membership, not semantic entailment; human review remains necessary. The prompt separates historical archive evidence, sensors, forecasts, and synthetic scenarios, and prohibits invented numerical forecasts or infrastructure control. Outputs record provider/model, measured latency, usage, and limitations.

Optional `WANDB_WEAVE_ENABLED=true` plus the Weave package enables tracing around the inference operation. The traced closure records the prompt/response without serializing settings, HTTP clients, or bearer keys. Missing/failed optional tracing initialization is explicit in notes; it does not turn a failed provider request into a demo result.

## Diagnostics and verification

`backend.inference.diagnostics(settings,client)` checks VSS auth/me + dashboard/stats, W&B model access, and configured model endpoints. GPU hosts are never derived from one another. If GPU_BEARER_TOKEN is present it is used; the discrepancy between the official architecture (no auth) and GPU examples (bearer) is not resolved by inventing a token. YOLO uses `/healthz` with ok/model_loaded. Cosmos3-Reason and Embed1 use `/v1/models`, `/v1/health/ready`, `/v1/health/live` and verify the configured model. A health response is not proof of processing footage.

Run: `.venv/bin/python -m unittest discover -s tests/inference -v` (13 tests pass). Tests cover one JWT retry, cache reuse, persistent authorization failure, secret concealment, Range forwarding/stream close, URI/timing retention, filter discovery, missing sidecars, W&B project/citations, hallucinated citation rejection, aggregated detections, one-frame limitations, and temporal image-space association.

Remaining live proof: Team 8 authentication, discovered schema/inventory, real search and seekable playback, exact sidecar/timing inspection, Cosmos stored reasoning, W&B evidence-backed call, optional telemetry, and a separately confirmed narrow re-ingestion run with pipeline traces. Existing archive retrieval alone cannot establish a new DataEngine run. No GPU workers, pipeline graph, VastDB rows, or ingestion buckets are created/modified by these adapters.

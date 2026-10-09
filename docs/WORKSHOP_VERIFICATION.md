# Assigned Team8 workshop verification

The assigned existing desktop was opened through the workshop on 2026-10-09.
Local Playwright with the already-authenticated browser profile controlled its
remote Xfce terminal. No additional VM was launched. Browser Use's native control
tool remained unavailable, while the local Playwright fallback worked.

**The actual PharOS archive, retrieval, evidence, tracking, media transport and W&B
operations adapters passed a read-only Team8 run at 2026-10-09T16:40:59.923721Z.**
This establishes application-code integration with the existing archive. No new
pipeline execution, workshop deployment, or current road condition is established.

The remote terminal explicitly confirmed `USERNAME=team-8`. Environment-presence
checks found `INGRESS_URL`, `PASSWORD` and `WANDB_API_KEY`. `WANDB_MODEL` and direct
GPU URL variables were absent from the terminal's initial environment. Values of
passwords, tokens and API keys were not printed or copied off the VM.

`scripts/workshop_readonly_probe.py` is a standard-library diagnostic runner for
this assigned VM. It requires Team8 identity, inspects only the exact
`/config/team-8.config` when filling missing known variables, and keeps credentials
inside its process. It queries login/session, metadata, archive Explore, semantic
search, stored reasoning, YOLO sidecars, a 1 KiB media Range request, and one bounded
W&B recommendation when available. Its POST allowlist contains only authentication,
semantic search and W&B chat completion. It cannot submit re-ingestion, uploads,
deployment or other shared mutations.

The script writes a redacted `/tmp/pharos-readonly-proof.json` on the VM with HTTP
statuses, elapsed times, schema keys and selected evidence. A successful archive
read establishes retrieval only. It does not prove a new YOLO → Cosmos Reason →
Cosmos Embed → VastDB processing run; that requires an explicitly confirmed
re-ingestion and DataEngine trace review.

## Observed execution

The read-only vertical slice completed at **2026-10-09T16:29:06Z** in Team8:

| Check | Result | Latency |
| --- | --- | ---: |
| VSS login / authenticated session | HTTP 200 / 200 | 1,481 / 4 ms |
| Metadata schema / ingest config | HTTP 200 / 200 | 371 / 3 ms |
| Archive Explore | HTTP 200; 612 parent chunks | 463 ms |
| Hybrid semantic search | HTTP 200; 3 segment and 3 parent results | 2,852 ms |
| Stored segment metadata | HTTP 200; reasoning present | 212 ms |
| YOLO detections sidecar | HTTP 200; 100 temporal frames | 283 ms |
| Seekable evidence bytes | HTTP 206; bytes 0–1023 of 4,095,058 | 22 ms |
| W&B model discovery | HTTP 200 | 1,310 ms |
| W&B evidence-linked inference | HTTP 200; `openai/gpt-oss-120b` | 6,081 ms |

The query “stopped vehicles obstructing a lane” returned a neighborhood-camera
segment with broad `location=neighborhood`, source camera `neighborhood_cam-1`,
span 0–5 seconds and similarity 0.2803085804. Its stored reasoning said only
“A car is driving on the road.” The W&B response cited the supplied evidence ID and
correctly said the material **does not establish an obstruction**. The first
300-token verification response was truncated, so it establishes provider/citation
execution rather than a complete operator brief. No exact map coordinates are
inferred from that broad location label.

The first Explore page also exposed broad `new_york` labels. This is actual index
metadata, separate from the source corpus described in the challenge reference;
neither city label establishes exact camera coordinates.

## Live contract differences

The deployed search schema rejects `llm_top_n=0` with HTTP 422:
`body.llm_top_n`, `greater_than_equal`, “Input should be greater than or equal to 1”.
Retrying `llm_top_n=1` succeeded. The zero-valued example in the reference
re-ingestion skill is therefore incompatible with this deployed version.

Explore returns `chunks[]` and `chunk_duration_sec` on each parent. Metadata's
filterable fields are `camera_id`, `capture_type`, `location`, `object_classes`.
Segment metadata includes `segment_start_sec`, `segment_end_sec`, `cosmos_model`,
`perception_source`, `reasoning_content` and sidecar metadata. YOLO's wrapper has
`frames[]`; each frame contains `frame_index`, `time_sec`, `shape`, `detections`.
Object count must be read from per-frame detections or the reported wrapper count,
not a nonexistent top-level detections array. Media responded with
`Content-Type: binary/octet-stream` despite returning valid seekable MP4 bytes.

## Traffic-specific confirmation

A second pass completed at **2026-10-09T16:31:34Z** after discovering valid camera
filter values. Query “dense highway traffic with vehicles”, filtered to returned
`camera_id=i24_cam-1`, retrieved three segments/parents in 2,381 ms. The selected
Nashville parent was
`s3://team-8-vss-chunks/team-8/20261001_055340_scene1_p1c1_chunk_0002.mp4`,
segment 6, spanning **25–30 seconds**. Its stored reasoning describes steady highway
flow without disruption. Location remains broadly Nashville and unlocated on the
map.

The metadata reports **`cosmos_model=nvidia/cosmos3-nano-reasoner`** and
**`perception_source=yolo11_coco`**. The reported Cosmos model ID differs from the
reference configuration's `nvidia/cosmos3-reason`; the observed ID takes precedence
when describing this archived result. It is not proof of the identity of a newly
executed model or a currently accessible direct endpoint.

The real sidecar contains **150 frames and 2,138 per-frame detection boxes**. One
sample at frame 0 / time 0.0 seconds has `shape=[1080,1920]` and detection
`{label:car, confidence:0.7349, bbox:[1364,797,1455,865]}`. The sampled object has no
upstream track ID. This establishes temporal detections, not application tracking.
The evidence Range request returned HTTP 206, bytes 0–1023 of 7,156,921, in 30 ms.

W&B `openai/gpt-oss-120b` completed a full evidence-linked brief in **13,601 ms**
(`finish_reason=stop`). It cited `readonly-hit-1`, described the supplied Nashville
observations, declined to claim an obstruction, and recommended further monitoring
for human review. Source statements remain model-generated interpretations requiring
visual review.

## Actual application adapter run

After matching the live schema, the exact current adapter source bundle was copied
through the workshop clipboard to `/tmp/pharos-adapter-source` in the assigned VM.
The VM's system Python is 3.12.3. A separate `/tmp/pharos-adapter-venv` was created;
because system ensurepip was absent, pip was bootstrapped from the official PyPA
bootstrap site into that environment. Dependencies were pinned to the app versions:
httpx 0.28.1, pydantic 2.12.0, python-dotenv 1.1.1. No sudo or system package changes
were used. W&B team/project/key were already in the VM environment; their values
were neither printed nor exported.

`scripts/workshop_adapter_probe.py` ran the actual `VSSClient`, `ArchiveAdapter`,
`RetrievalAdapter`, detection parser, application tracking and `OperationsAgent`.
All nine checks succeeded:

| Actual code path | Measured latency |
| --- | ---: |
| Authenticated session | 225.8 ms |
| Metadata discovery | 409.0 ms |
| Normalized archive inventory | 95.3 ms |
| Hybrid search adapter | 2,362.6 ms |
| Evidence parser and tracking | 420.6 ms |
| Sidecar schema sample | 195.7 ms |
| Media adapter Range transport | 11.9 ms |
| W&B operations agent | 9,459.8 ms |
| Index health | 613.7 ms |

The parser returned all **2,138 detections** and **125 application tracks** from the
150-frame I24 sidecar. Tracks have `source=application`, use image-space IoU
association, and are uncalibrated; this is not an upstream stable identity or a
validated physical trajectory. The first detection's source time 0.0 was correctly
offset to parent time 25.0 seconds. Its normalized box retained the original pixel
box and source image dimensions for review. The actual media adapter streamed the
parent with HTTP 206, 1,024 bytes and `Content-Range: bytes 0-1023/31931650`.
This called the media adapter inside the VM. The local API/browser tests separately
cover PharOS proxy playback; workshop browser/ingress playback is not yet verified.

The actual operations agent produced three structured claims citing registered
evidence and asset IDs. It described smooth archived traffic, explained that capture
time/current conditions are unknown, and recommended obtaining recent evidence
before acting. It used W&B `openai/gpt-oss-120b`, `execution_mode=real_provider`.
Citation validation verifies known evidence IDs; it does not prove factual entailment.
W&B/Weave observability was disabled, so no tracing/experiment claim is made.

Live ingest configuration confirmed an 800-character custom-prompt limit. Read-only
dashboard diagnostics showed **3,537 indexed clips**, **612 fully indexed videos**,
**zero duplicate segment slots**, **zero pending-index count**, and healthy pipeline
alignment. This measures existing index consistency; it does not show a new
DataEngine run. Direct GPU URLs remain absent even after checking the exact assigned
config, so direct model health diagnostics are not claimed. No deployment or shared
archive mutation was performed.

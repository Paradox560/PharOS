# Verification and delivery status

Verified on **2026-10-09**. The local application is ready for review. Team 8's
existing archive and W&B adapters were exercised successfully inside the assigned
VM. A fresh DataEngine run and a workshop `/app` deployment are **not verified**.

The subsequent [design refinement](DESIGN_REVIEW.md) passes **12 frontend tests**,
the complete browser workflow and seven focused accessibility checks. It includes
a [54-second updated recording](demo/pharos-design-demo.webm). The tables below
retain the original build verification; no backend provider behavior changed.

## Automated and browser checks

| Check | Observed result |
| --- | --- |
| `.venv/bin/python -m pytest -q` | **86 passed** in 25.41 seconds; one upstream Starlette/AnyIO deprecation warning |
| Subsequent `pytest -q tests/test_deploy.py` | **5 passed**, including the additional regression proving changed code triggers a new pod; **87 distinct Python tests** pass across these checks |
| `cd frontend && npm test` | **8 passed**, including dense 30 fps frame alignment and `/app` client paths |
| `cd frontend && npm run build` | TypeScript and production Vite build passed; dedicated MapLibre worker asset emitted |
| `cd frontend && npm audit --audit-level=low` | **0 vulnerabilities** reported by the registry audit |
| `.venv/bin/python scripts/browser_smoke.py` | Full console workflow passed with **0 page errors** |
| Responsive browser checks | Desktop, tablet 768×1024 and mobile 390×844; map interaction, evidence, forecast, provider dialog and horizontal overflow checked |
| [Recorded local workflow](demo/pharos-local-demo.webm) | 38.92 seconds, 1440×900 VP8/25 fps, zero page errors; full video decode passed |
| `scripts/prepare_deploy.py --team team-8` | Reviewable manifests generated; **279,888 encoded bytes**, below the 900,000-byte guard; no apply performed |

Python coverage includes authenticated VSS transport and 401 refresh, evidence
provenance, missing sidecars, citation ID validation, source cache/freshness,
deduplicated risk, chronological forecasts, job lifecycle, persistent results,
operator authentication, Range playback, body validation, and deployment packaging.
The suite executes SUMO/TraCI processes rather than substituting scenario metrics.

The end-to-end browser run inspected 3D buildings, video seeking and detection
toggles, exact search spans, forecasts, SUMO comparison and replay, cited briefs,
provider details and mobile layout. Its [result](verification/browser-verification.json)
and [screenshots](screenshots/01-console.png) are committed. Browser automation used
local Playwright/Chrome because the native Browser Use controller failed to start
with a sandbox `TIOCSTI` error.

## Observed live providers

The [redacted application proof](verification/team8-adapter-proof.json) completed
at **2026-10-09T16:40:59.923721Z**. Credentials remained inside Team 8. The local
preview remains a clearly labeled deterministic demo; it is not a tunnel to those
services. See [the detailed live record](WORKSHOP_VERIFICATION.md).

| Capability | What actually ran |
| --- | --- |
| Browser source discovery | Rendered NYC camera page/network responses; 982 catalog records discovered; 16 verified Midtown locations seed the local view |
| VSS semantic retrieval | Actual PharOS adapter searched Team 8's existing Cosmos Embed1/VastDB-backed archive; 3 segments and 3 parents returned in 2,362.6 ms |
| Stored Cosmos analysis | Selected I24/Nashville clip, parent span 25–30 seconds; metadata reports **`nvidia/cosmos3-nano-reasoner`** |
| YOLO sidecar parsing | Actual `yolo11_coco` sidecar, 150 frames and **2,138 detections**, source dimensions retained and times aligned to the parent |
| Application tracking | **125 image-space IoU tracks** produced by PharOS; uncalibrated, no upstream stable IDs or physical speeds claimed |
| Evidence media transport | Actual parent media returned HTTP **206**, bytes 0–1023/31931650 |
| W&B synthesis | **`openai/gpt-oss-120b`**, 9,459.7 ms; 3 structured claims with registered evidence/asset citations |
| Existing index consistency | 3,537 clips, 612 fully indexed videos, zero duplicate slots, zero pending-index count |

The live stored description reports smooth traffic, so the recommendation does
**not** invent an obstruction. The camera's broad Nashville metadata is retained;
no exact coordinates or relationship to the NYC scenario are inferred. The observed
Cosmos ID differs from the reference `nvidia/cosmos3-reason` and takes precedence in
the UI. Existing stored output does not prove a fresh call to either model.

## Numerical outputs

The committed [SUMO comparison](../simulation/scenarios/clearance-metrics.json)
used the connected First Avenue OSM network, synthetic 900 vehicles/hour demand,
600 seconds and seed 42. Baseline/early/late completed 60/54/0 of 150 scheduled
vehicles; 90/96/150 remained unfinished. Early clearance accumulated 7,599.48 fewer
vehicle-seconds of delay than late clearance within the observation window.
Completed-only means and censored unfinished journeys are reported separately;
these numbers are **not calibrated predictions of NYC traffic**.

Forecasts implement persistence and historical time-of-week baselines with a
chronological evaluation path. The illustrative dataset is synthetic. The inspected
DOT speed feed was stale and its units were unconfirmed, so it does not establish
a validated live forecast. Unknown roads remain unknown rather than normal.

## Remaining delivery requirements

- **Fresh shared processing:** the one-chunk preview/confirmation flow is implemented,
  but no re-ingestion was submitted. The exact target, prompt, preserved metadata
  and chunk count must be confirmed before the shared archive changes. Completion
  then needs DataEngine traces and post-run index/search verification.
- **Workshop deployment:** manifests are prepared under `deploy/generated/`, but
  have not been applied. Deployment authorization, a private operator password,
  and cluster checks for runtime images, dependency downloads, quotas and storage
  are still required. Default `emptyDir` output storage is ephemeral; use an existing
  approved PVC when persistence across pod replacement is required.
- **Direct GPU and observability:** direct GPU URLs were absent in the assigned
  environment; new model execution/CoreWeave traces were not verified. W&B inference
  worked, but Weave tracing was disabled.
- **NYC media and measured forecasts:** camera developer-feed access and any
  challenge-media exception are unresolved. No public NYC images were uploaded.
  Fresh, associated and unit-confirmed sensors are needed to validate live forecasts.

These boundaries follow the [build prompt](PHAROS_BUILD_PROMPT.txt), including its
explicit authorization requirements. No public deployment, shared archive mutation,
extra VM, GPU provisioning or hackathon submission was performed.

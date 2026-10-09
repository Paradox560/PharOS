# Five-minute local demonstration

Start `bash scripts/start.sh`, then open `http://127.0.0.1:8765`.

**0:00 — Scope.** Point to the persistent Demo banner. NYC camera coordinates are real catalog metadata; the traffic illustration is generated. Workshop archive locations remain whatever the live index reports, with unknown coordinates left unlocated.

**0:30 — Inspect.** Select the obstruction review item. Seek to 00:08 and toggle the bounding-box overlay. The visible truck annotation is a deterministic UI fixture, not claimed YOLO inference. Open provenance and the 00:08–00:22 span. Review stored evidence; this retrieves annotations/reasoning and does not silently start shared processing.

**1:15 — Search.** Search “lane obstruction,” select a matching span and observe the seek position. The demo engine explicitly says keyword fallback. With the workshop connected, the same route uses VSS hybrid search and preserves parent and segment IDs/time ranges.

**1:45 — Forecast.** Open Forecast, choose a road, and use illustrative mode. Inspect 5-, 15- and 30-minute speeds, uncertainty and chronological baseline evaluation. The measurements are synthetic and have no causal link to the selected clip. Persistence mode correctly rejects missing/stale/unverified sensor inputs.

**2:30 — Simulate.** Run the default clearance comparison: 600 seconds, 900 vehicles/hour, seed 42, obstruction beginning at 60 seconds, early clearance at 180 and late at 420. The actual SUMO engine uses the imported First Avenue OSM network. Read throughput, unfinished vehicles, elapsed journey time and delay together. Change replay time and switch baseline+early versus baseline+late.

**3:45 — Review.** Generate a brief with evidence, forecast and scenario context. In local demo mode the deterministic template is labeled; when connected W&B executes the synthesis. Click an evidence reference to return to the corresponding span.

**4:30 — Status.** Open connection details. A successful source browser audit and an actual SUMO execution are distinct from unverified workshop providers. Explain any remaining live pipeline/deployment checks from WORKSHOP_VERIFICATION.md. Do not label a successful archived retrieval as a fresh inference run.

Automated replay: `.venv/bin/python scripts/browser_smoke.py`. Screenshots are saved under `artifacts/`. A [54-second recording](demo/pharos-design-demo.webm) shows the actual local workflow, including a fresh SUMO run. Re-record it with `.venv/bin/python frontend/tests/record_demo.py`; output goes to ignored `artifacts/pharos-design-demo.webm`. The included VP8 video is 1440×900 at 25 fps, was fully decoded without errors, and had zero browser page errors.

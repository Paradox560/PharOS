# Reproducible Manhattan SUMO comparison

PharOS executes the actual Eclipse SUMO 1.27.1 simulator through TraCI. There is no simulated-SUMO fallback. Demand and obstruction inputs are synthetic; execution_mode=real_provider refers to executing the real simulator, not to calibration against current traffic.

## Geography, network and attribution

`simulation/networks/manhattan-source.osm.xml` is a road-only extract retrieved from the [OpenStreetMap map API](https://api.openstreetmap.org/api/0.6/map?bbox=-73.986,40.730,-73.976,40.741) on 2026-10-09. The original downloaded response SHA256 was `4d3f5113c524371596b905ec38c1314872b926ba1f3c08ca253e0a47df9e5369`. Reduction preserves 191 drivable road ways, 824 referenced nodes, and included turn restrictions. Buildings and unrelated paths were omitted. OSM entity IDs, versions, timestamps, and road tags remain inspectable; contributor account identifiers were removed.

© OpenStreetMap contributors, [ODbL 1.0](https://www.openstreetmap.org/copyright). The source extract and derived network are redistributed with this attribution. SUMO is a separate installed dependency under EPL 2.0/GPL 2.0-or-later; no SUMO source is copied into PharOS.

The generated network has 203 road edges. The selected route follows 27 connected passenger-accessible northbound 1st Avenue edges for 1,005.71 metres, from approximately `[-73.9835031,40.7300634]` to `[-73.9759825,40.7403908]`. Source geometry is from OSM; no archive footage is positioned on this road. `manifest.json` records the exact route, source/network checksums, blockage link (`420598230#0`), assumptions and lane-connectivity validation. `roads.json` supplies WGS84 road geometry without requiring projection libraries at application runtime.

The network is an OSM import, not a surveyed traffic model. Nearby streets are retained for network continuity but have no background traffic in this demonstration. OSM lane/speed/one-way tags are retained where present; netconvert fills missing attributes and guesses lane connections. Signal locations/timing use imported or guessed SUMO static plans. No observed NYC signal coordination, turns, bus operations, cyclists, pedestrians or real demand calibration is claimed. These assumptions explain the congested baseline and constrain interpretation.

## Rebuild

The tested dependency set is `eclipse-sumo==1.27.1`, `sumo-data==1.27.1`, `sumolib==1.27.1`, `traci==1.27.1`; rebuilding map geometry also uses `pyproj==3.7.2`. Pinning the SUMO companion packages matters: the initially resolved sumo-data 1.28.0 broke the 1.27.1 macOS native binary's shared-library paths.

```sh
.venv/bin/python simulation/networks/prepare_network.py .venv/bin/netconvert
.venv/bin/python simulation/networks/build_manifest.py
```

The scripts use [SUMO's native OSM importer](https://sumo.dlr.de/docs/Networks/Import/OpenStreetMap.html). The compressed `.net.xml.gz` is supported directly by [SUMO input handling](https://sumo.dlr.de/docs/Simulation/Output/Binary.html). It keeps the runtime network small enough for the workshop code-package strategy; do not include the downloaded source extract, virtual environment, run outputs, or rebuild-only dependencies in a ConfigMap. Actual namespace mounts and runtime package downloads remain deployment checks.

## Scenario and metrics

`simulation/scenarios/clearance-comparison.json` specifies 600 seconds, 900 vehicles/hour, obstruction at 60 seconds, clearance at 180 versus 420 seconds, and seed 42. All three alternatives receive the identical 150 scheduled vehicle arrivals and the same seed. Baseline has no obstruction. The blockage is a severe capacity reduction: every lane of one selected road link is capped at 0.1 m/s until clearance. It is not a calibrated representation of a particular incident. No rerouting is modeled. Teleporting is disabled so blocked vehicles cannot disappear.

The runner supports 300–1,800 seconds, 100–2,400 vehicles/hour and one to three unique seeds. Numeric metrics are arithmetic means across paired seeds except `mean_completed_travel_time_sec`: it divides the total completed journey durations by the total completed vehicle count across all seeds. It is null only when no seed completes a trip. This weights vehicles correctly when seeds have different completion counts; `per_seed` retains every result and `total_completed_travel_time_sec`. Replay uses the first seed, every ten seconds. Repeated seeds measure simulation sensitivity, not real-world prediction accuracy.

Completed-only travel time is explicitly named `mean_completed_travel_time_sec`. Separate elapsed-journey metrics include unfinished vehicles and those still waiting to enter, as a censored lower bound at the simulation horizon. Delay includes SUMO timeLoss, insertion delay and remaining insertion backlog. Waiting likewise includes both network waiting and insertion backlog. Queue size counts stopped vehicles plus pending insertion. [SUMO tripinfo output](https://sumo.dlr.de/docs/Simulation/Output/TripInfo.html) is configured to write unfinished vehicles. Throughput + unfinished + insertion backlog must equal scheduled demand.

Measured local reference results are stored in `simulation/scenarios/clearance-metrics.json`. Completed-duration totals were regenerated from the original saved SUMO tripinfo after the aggregation fix; every previously reported metric and trajectory remains unchanged:

| 600-second scenario | Completed | Unfinished | Insertion backlog | Total accrued delay (s) | Peak queue |
|---|---:|---:|---:|---:|---:|
| Baseline | 60 | 90 | 0 | 25,876.40 | 87 |
| Early clearance | 54 | 96 | 0 | 28,233.90 | 101 |
| Late clearance | 0 | 150 | 0 | 35,833.38 | 136 |

Early clearance reduced accrued delay by 7,599.48 vehicle-seconds relative to late clearance in this one synthetic scenario. The late run has zero completed trips by the finite horizon; its eventual total journey times are unknown. These values are not an estimate for a real incident. Extending the horizon changes the censoring and must be compared with the same inputs across alternatives.

## Worker interface and lifecycle

`from backend.simulation import SimulationRunner, get_roads`

`SimulationRunner(settings).run(scenario,run_id,cancel_event,progress)` is synchronous for `asyncio.to_thread`. Root owns job records, cancellation state and persisted application results. The worker writes immutable scenario inputs, route demand, per-alternative SUMO logs/tripinfo and result JSON beneath settings.output_dir/run_id. Existing run identifiers cannot overwrite outputs. Local output storage remains the approved default until a separate VAST artifact prefix is confirmed.

`run()` returns the canonical SimulationRun fields plus `playback`, network hashes, and assumptions. Root assigns job_id and persists playback. `get_roads()` returns the canonical OSM RoadSegments. Callback progress lies in [0,1]. Each SUMO alternative uses a private TraCI connection and independent subprocess group; no global TraCI connection state is shared. The worker checks cancellation every simulated second and has a separate watchdog that terminates the subprocess group on cancellation or deadline. The simulation deadline is the smaller of settings.job_timeout_seconds and 180 seconds. Runtime discovery has a separate ten-second subprocess limit; the application job timeout wraps the entire worker call. Failures are explicit ProviderErrors; cancelled work never receives a successful result file.

Run outputs include `baseline`, `early`, `late` metrics, and comparison keys `delay_saved_sec`, `additional_completed_vehicles`, `queue_reduction_vehicles`, `elapsed_journey_time_saved_sec`. Playback includes WGS84 vehicle locations/speeds and road IDs for baseline/early/late at each common time. It is always labeled synthetic.

## Verification

`.venv/bin/python -m pytest tests/simulation -q` passed all 13 tests in 24.10 seconds, including actual SUMO through the application API. Checks cover deterministic replay/metrics; paired-seed aggregation with zero-completion runs; default 600-second and two-seed 300-second jobs; persisted run/replay responses; video Range requests while the worker runs; plausible longer-blockage effects; complete demand accounting; terminal in-flight/pre-start cancellation; invalid and duplicate seeds; unavailable runtime; and connected WGS84 OSM geometry. The only warning was an existing AnyIO TestClient deprecation. TraCI requires a local socket; the desktop sandbox required an approved execution context for these tests. No external workshop service or shared archive was mutated.

Not yet verified: calibration to sensors; observed signal/lane correctness; approved VAST artifact storage; team namespace runtime/mounts; workshop deployment execution. This scenario must remain separate from Nashville/Toronto archive evidence.

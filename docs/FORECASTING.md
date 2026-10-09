# Road priority and traffic baselines

`backend.forecasting.forecast(road, horizons, mode, records=None, now=None)` returns
the shared `ForecastRun`; the root application persists it. Valid horizons are
5, 15 and 30 minutes. The road provides its stable ID and positive length in metres.

`illustrative` creates four weeks of deterministic five-minute synthetic values
with a repeated weekday/UTC-hour profile and fixed road-specific variation. It
predicts using historical time-of-week means. Every output is labeled
`data_origin=synthetic`, `execution_mode=mock`, and `mode=illustrative`. These values
have no measured connection to NYC cameras, workshop footage, or the SUMO demand.
Their purpose is to exercise the numerical evaluation and UI path without secrets.

`persistence` requires at least three actual sensor records spanning ten minutes,
with the latest observation no older than 15 minutes, confirmed `speed_kph`,
`public_sensor/real_provider` provenance, and explicit road or configured sensor
association. The last measured speed is held constant. Missing units, stale data,
future values, synthetic data, and unreviewed associations cannot produce a live
forecast. The current DOT adapter deliberately retains native speed with unknown
units until a source contract establishes conversion, so it cannot yet supply this
mode. A rejected live forecast never silently becomes illustrative.

Association accepts `record.road_id == road.id` or a `sensor_id` in the road's
configured `sensor_ids`. Geometric matching returns a reviewable candidate only:
within 60 metres of the road midpoint and direction cosine at least 0.85. Opposite
directions and distant/empty/invalid geometry are rejected. It does not establish
physical calibration, full overlap, lane mapping or road-network connectivity.
The candidate must be reviewed and assigned an explicit ID before numerical use.

## Evaluation and uncertainty

At least 72 samples permit chronological 60% training / 20% validation / 20% test
evaluation. Historical weekday/hour/five-minute means are learned solely from
training; unseen slots use the training mean. Persistence at each test origin uses
only the already-observed value. Targets must exist at the exact horizon timestamp;
gaps are never filled with future observations. Both methods report test MAE per
horizon, target sample count, and held-out empirical interval coverage.

Intervals use the 90th-percentile absolute residual from validation only. Test
targets never tune them. Forecast bands are empirical baseline residual bands,
not claims of calibrated coverage. When history/pairs are insufficient, interval
bounds and metrics stay null. Synthetic evaluation is explicitly labeled
`scope=synthetic_only`; no real-world model superiority or accuracy is claimed.
No regression is fit because representative measured history is not established.

The checked `backend/forecasting/evaluation-example.json` uses issue time
2026-10-09 15:00 UTC and an independent illustrative road ID. At 5/15/30 minutes,
persistence test MAE was 1.131/2.173/1.716 km/h and historical MAE was
1.977/1.978/1.978 km/h. Historical held-out interval coverage was about 78%, below
the nominal 90%; this demonstrates why coverage must be measured. These are
synthetic fixture results, not NYC forecast validation or a general improvement
claim.

Each result retains issue time, input window, training/validation/test windows,
feature definitions, model version, source provenance and assumptions. Numerical
travel time is road length divided by mean predicted speed; zero speed yields
null finite travel time rather than a guessed cap. The local application stores
these artifacts; no new VAST write destination is assumed.

## Explainable road priority

`backend.risk.score_roads(roads, observations, now=None)` returns cells, legend and
notes. Inputs are shared `Observation` records with road ID, timestamp, confidence,
evidence ID, provenance and normalized factors:

| Factor | Weight |
| --- | ---: |
| Obstruction | 0.35 |
| Persistence | 0.20 |
| Slowdown | 0.20 |
| Severity | 0.15 |
| Corroboration | 0.10 |

Score is the weighted mean of supported factors multiplied by 100. Missing
factors are omitted, not assumed normal. Coverage is the sum of supported factor
weights; confidence combines source confidence and observation age separately.
Thresholds stay fixed: high at 70, medium at 35, otherwise low. This is a disruption
priority index, never a collision probability.

Evidence/factor pairs deduplicate first; repeated camera observations cannot add
score or confidence. Each factor uses its strongest fresh supported value, with a
stale value retained only when no fresh value exists for that factor. Any retained
stale factor marks the cell stale, so an old obstruction cannot turn green merely
because a different current factor is low. Freshness threshold is 15 minutes.
Unknown timestamps/future timestamps and zero-confidence claims do not establish
coverage. Unsupported roads are gray with null score. No spatial spreading occurs
to adjoining streets. If real evidence exists for a road, synthetic observations
are excluded, including when real coverage is stale or unknown.

Tests cover chronological leakage, deterministic fixtures, insufficient history,
unknown units, future and stale input, zero speed, road association, score factors,
missing coverage, repeated evidence and mixed fresh/stale conditions:

```sh
.venv/bin/python -m pytest tests/forecasting -q
```

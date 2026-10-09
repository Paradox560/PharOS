# Public sources and licensed archive

The NYC context and workshop video archive are separate datasets. The public catalog
does not create NYC archive footage or grant media ingestion rights. Public camera
images never enter the VAST pipeline.

## Verified public discovery

On 2026-10-09 local Playwright Chromium rendered the NYC DOT camera list and map,
captured the public GraphQL responses, and wrote
`backend/data_adapters/data/discovery/audit.json` plus `camera-list.png`. The audit
includes request queries, response bodies, SHA-256 hashes, timestamps, page URL and
rendered text. Browser Use's environment tool could not launch its kernel. Local
Chromium also failed inside the process sandbox but succeeded with permitted browser
process access. No credentials, image streams, or video were collected.

The site's public browser bundle and observed network calls identify
`https://webcams.nyctmc.org/cameras/graphql`. A bounded query of camera ID, name,
area, latitude, longitude and online state returned 982 records. The checked-in
16-camera Midtown sample preserves exact source coordinates/IDs and verification
time. Camera `captured_at` stays null: catalog retrieval is not image capture.

Run browser discovery with Node and Playwright installed:

```sh
node scripts/discover_sources.mjs data/source-discovery
```

`PLAYWRIGHT_MODULE` can select a local playwright-core module, and
`CHROMIUM_EXECUTABLE` an existing Chromium executable. The output directory is the
only write destination. The runner blocks camera image requests and records public
metadata network responses only. This is an audit/discovery tool; routine refresh
uses HTTP APIs without an LLM browsing each frame.

The implemented adapter also passed a live read-only smoke check at
2026-10-09T16:12:58Z: 982 catalog cameras, 500 speed records, 100 DOT service reports
and one NWS observation. `backend/data_adapters/data/context-verification.json`
retains bounded normalized examples and source freshness. The retrieved speed
timestamps were already stale despite the successful API call; they were not
relabelled current.

## Routine source contracts

| Source | API | Limit | Freshness policy |
| --- | --- | --- | --- |
| NYC DOT cameras | `/cameras/graphql` on webcams.nyctmc.org | 1,500 records; single request | Catalog verification retained; image capture time unknown |
| DOT speed | [i4gi-tjb9](https://data.cityofnewyork.us/Transportation/DOT-Traffic-Speeds/i4gi-tjb9) | Latest 500 rows | Source observation older than 15 minutes is stale |
| NYC 311 | [erm2-nwe9](https://data.cityofnewyork.us/Social-Services/311-Service-Requests-from-2020-to-Present/erm2-nwe9) | Latest 100 DOT reports; only selected non-contact fields | Creation older than 48 hours is stale; reports are unverified |
| NWS Central Park | [KNYC latest observation](https://api.weather.gov/stations/KNYC/observations/latest) | One observation | Source timestamp older than two hours is stale |

Each source has an independent lock, timeout, disk/in-memory cache and minimum
request interval (60–3,600 seconds; default 300). Failure retains source times and
labels cached data; no successful camera request masks a failed weather request.
Cold start uses the verified camera metadata sample. No synthetic records are
silently substituted for live context failures.

Socrata floating timestamps are interpreted as America/New_York and converted to
UTC. This timezone assumption is explicit in provenance. `link_points` are source
latitude/longitude pairs, converted to GeoJSON longitude/latitude; incomplete pairs
are skipped. This sometimes truncated geometry is not a validated road network.
The [DOT metadata PDF](https://www.nyc.gov/html/dot/downloads/pdf/metadata-trafficspeeds.pdf)
defines Speed and TravelTime but does not specify speed units. Native speed is
preserved as `speed_native`; `speed_unit=source_unspecified`, `speed_kph=null`.
Forecasts must not use those records as km/h until source units are established.
NWS values are accepted only with expected unit codes; missing measurements stay
null. A Central Park observation is not extrapolated into a measurement at every
camera, and 311 report time is not a confirmed incident time.

NYC DOT says developer camera-feed access requires a data-sharing agreement on its
[data feeds page](https://www.nyc.gov/html/dot/html/about/datafeeds.shtml). Therefore
`NYC_CAMERA_SNAPSHOTS_ENABLED` defaults false. Once the deployment operator has
appropriate permission, the same-origin proxy accepts verified catalog IDs only,
enforces image types and an 8 MB limit, and caches up to 32 images for 30 seconds.
It accepts no arbitrary URL. The public source page remains available independently.

NYC DOT attribution: this application uses information originally compiled by the
New York City Department of Transportation for governmental purposes and may
transform it. NYC DOT and the City make no representation about its accuracy,
usefulness or suitability and disclaim liability for omissions/errors. Observe
posted signage. See the linked DOT page and NYC Open Data terms for the original
required disclaimer. This application is not a DOT product.

## VAST archive and re-ingestion

`ArchiveAdapter(client)` calls `/videos/explore?scope=all&limit=&offset=` through
the authenticated VSS client. It preserves parent `original_video`, preview
segment `source`, timeline, camera, capture type and location. Stable IDs are hashes
of exact parent URIs. Broad labels such as Nashville remain unlocated; no guessed
map coordinates. Metadata discovery calls `/metadata/schema` and
`/metadata/ingest-config`; filter names must come from that schema.

`ReingestionAdapter(client)` accepts only a parent verified in connected Explore.
It shows exact parent URI, prompt, metadata, segment count and `chunk_count:1` in a
10-minute preview. The root API owns explicit confirmation and the disabled-by-
default feature flag. Submit compares the full preview to its retained copy and
sends only `original_video`, `chunk_count:1`, and `custom_prompt` (1–800 characters).
Omitting camera/capture/location overrides preserves upstream metadata. It never
submits stream IDs, new uploads, or constructed S3 keys. Duplicate confirmed
submissions reuse the result. An uncertain submission cannot auto-retry: inspect
the upstream dashboard before starting another run. Preview state expires on app
restart, so a fresh preview and confirmation are required.

This implements the official [reingest-chunk skill](https://github.com/vast-data/vast-builders-challenge/blob/main/.cursor/skills/ingest/reingest-chunk/SKILL.md).
Archive and re-ingestion contract tests use fake responses; they do not establish
live VAST/YOLO/Cosmos execution. Actual shared mutations remain root-owned and
require selection and confirmation of the exact preview. No mutations were run
while implementing this adapter.

Verification: `.venv/bin/python -m pytest tests/ingestion -q`.

# Sources and third-party notices

## Architecture references

- [VAST Builders Challenge](https://github.com/vast-data/vast-builders-challenge): official architecture, documented VSS interfaces, team configuration and `/app` deployment pattern. The supplied running DataEngine graph is not copied, rebuilt or redeployed.
- [OlympusOS](https://github.com/NevineAKF/OlympusOS): inspected `agents/orchestrator.py`, `agents/base_agent.py` and MIT license (copyright 2026 Nevine Fakhreddin). Inspiration is limited to clear specialist roles and structured coordination. No source code was copied into PharOS.
- [Workshop resources](https://workshop.thecosmoslabs.com/labs/builders-challenge): assigned Team 8 desktop; session credentials are excluded from repository artifacts.

## Geographic and public context data

- © [OpenStreetMap contributors](https://www.openstreetmap.org/copyright), ODbL 1.0. The bounded OSM extract, reduced source XML, compiled network, geometry and provenance manifest are in `simulation/networks/`. Preserve this attribution and applicable ODbL obligations when redistributing adapted map databases. Original source URL, retrieval date and SHA256 hashes are recorded in the manifest.
- [OpenFreeMap](https://openfreemap.org/quick_start/) vector tiles / OpenMapTiles, with source attribution displayed on the interactive map. No public OSM standard tile endpoint is used as an application backend.
- [NYC DOT cameras](https://webcams.nyctmc.org/cameras-list) and rendered public GraphQL discovery. Catalog metadata and source URLs are retained; no NYC media is uploaded into VSS. Developer feed access requirements: [NYC DOT data feeds](https://www.nyc.gov/html/dot/html/about/datafeeds.shtml).
- NYC Open Data source records for [DOT traffic speeds](https://data.cityofnewyork.us/resource/i4gi-tjb9.json) and [311 reports](https://data.cityofnewyork.us/resource/erm2-nwe9.json). The exact queried resource URLs and provenance are in FEEDS.md; a report is not a verified current incident.
- [National Weather Service API](https://www.weather.gov/documentation/services-web-api): timestamped KNYC observation. Weather context does not establish a camera's conditions at an unrelated time.

## Runtime dependencies

React, Vite, TypeScript, Lucide, MapLibre, FastAPI, HTTPX, Uvicorn, Pydantic, Playwright and their dependencies retain their distribution licenses/notices in the installed packages. Exact versions are in `frontend/package-lock.json` and `requirements.lock`. SUMO is distributed under EPL-2.0 / GPL-2.0-or-later; see [SUMO licensing](https://sumo.dlr.de/docs/License.html). The repository ships the attributed network and application integration, not a copied SUMO binary.

The generated local traffic illustration is original procedural demo media produced by `scripts/generate_demo_media.py`. It contains no downloaded footage, camera snapshots or real detections. Workshop archive licensing is controlled by the organizers; PharOS only queries the assigned authorized archive and preserves its source metadata.

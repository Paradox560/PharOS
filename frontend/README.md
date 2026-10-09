# PharOS console

React/TypeScript/Vite client for the shared contract in `../docs/API_CONTRACT.md`. The runtime contains no private provider credentials and no fallback fixture dataset. It consumes the API's explicit demo or connected mode.

## Development and build

```sh
npm ci
npm run dev
npm run typecheck
npm test
npm run build
```

The development proxy targets `127.0.0.1:8000`. Production output is `dist/`, served by the PharOS API. For the workshop ingress, build with `npm run build -- --base=/app/`; API and media URLs preserve both `/app` and `/app/`. Local builds retain relative assets.

## Behavior and boundaries

- OpenFreeMap vector map, camera clustering, extruded buildings, road priority, forecast road, and synchronized baseline/scenario vehicles are implemented behind `MapAdapter` in `src/map-adapter.ts`.
- NYC camera context, archive footage, and synthetic scenario inputs stay separate. Unknown archive coordinates are never plotted. Scenario framing includes the entire corridor.
- Evidence spans seek the source video. Detection boxes appear only within 0.26 seconds of their recorded frame timestamp. Pixel boxes require source video dimensions. Sparse boxes are never described as tracks.
- Stored-evidence review and simulation use asynchronous jobs. Simulation supports cancellation, immutable input inspection and shared-time baseline/early/late playback. A provider failure remains an error.
- Forecast panels show returned mode, provenance, horizon, uncertainty, evaluation and assumptions. Missing observations remain unknown.
- The connection center invokes real API diagnostics and distinguishes ready, unverified, unavailable and demo states.
- Keyboard controls, visible focus, native modal focus handling, responsive source/map/inspector views and reduced motion are included.

## Verification

`npm test` checks deployment/media paths, error propagation, sparse detection alignment and box validation. `tests/browser_smoke.py` uses the repository's Python Playwright dependency and installed Chrome to exercise mobile/tablet views against a local API at port 8765. Run from the repository root:

```sh
.venv/bin/python frontend/tests/browser_smoke.py
```

That smoke run waits for vector tiles, seeks the synthetic evidence to 8 seconds, checks its box, requests an illustrative forecast and opens the connection dialog. It writes screenshots into ignored `frontend/artifacts/`. The root browser suite covers the complete SUMO workflow.

## Map references and attribution

The implementation follows [MapLibre's 3D building example](https://maplibre.org/maplibre-gl-js/docs/examples/display-buildings-in-3d/) and the [OpenFreeMap quick start](https://openfreemap.org/quick_start/). Map data credits are kept visible through the MapLibre attribution control: OpenFreeMap, OpenMapTiles and OpenStreetMap contributors. The [MapLibre migration guide](https://maplibre.org/maplibre-gl-js/docs/guides/v5-to-v6-migration-guide/) documents the ESM worker and WebGL2 requirements for version 6.

Fonts are DM Sans and IBM Plex Mono via Google Fonts with local system fallbacks. Dependencies are exact direct pins with `package-lock.json` covering transitive versions. Library licenses remain in their packages; no OlympusOS code was reused in this client.

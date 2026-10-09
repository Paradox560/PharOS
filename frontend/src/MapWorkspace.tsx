import { useEffect, useRef, useState } from "react";
import {
  Building2,
  Crosshair,
  Layers3,
  Navigation,
  MapPin,
  CircleAlert,
} from "lucide-react";
import { MapLibreAdapter, type MapAdapter, type MapData } from "./map-adapter";
import type { Layers, Workspace } from "./types";
import "maplibre-gl/dist/maplibre-gl.css";

interface Props extends MapData {
  workspace: Workspace;
  onWorkspace: (value: Workspace) => void;
  focusPoints: [number, number][];
  focusKey: string;
  onSelect: (kind: "camera" | "road", id: string) => void;
  onLayers: (value: Layers) => void;
  reducedMotion: boolean;
}
export default function MapWorkspace(props: Props) {
  const container = useRef<HTMLDivElement>(null);
  const adapter = useRef<MapAdapter | null>(null);
  const propsRef = useRef(props);
  propsRef.current = props;
  const [status, setStatus] = useState("Connecting to vector map…");
  const [loaded, setLoaded] = useState(false);
  const [showLayers, setShowLayers] = useState(false);
  useEffect(() => {
    if (!container.current) return;
    try {
      adapter.current = new MapLibreAdapter(
        container.current,
        (kind, id) => propsRef.current.onSelect(kind, id),
        (value, ready) => {
          setStatus(value);
          setLoaded(ready);
        },
      );
    } catch (error) {
      setStatus(
        `3D map unavailable: ${error instanceof Error ? error.message : "WebGL initialization failed"}`,
      );
    }
    const observer = new ResizeObserver(() => adapter.current?.resize());
    observer.observe(container.current);
    return () => {
      observer.disconnect();
      adapter.current?.destroy();
      adapter.current = null;
    };
  }, []);
  useEffect(() => {
    adapter.current?.update(props);
  }, [
    props.cameras,
    props.roads,
    props.risk,
    props.forecast,
    props.vehicles,
    props.selectedCamera,
    props.layers,
    loaded,
  ]);
  useEffect(() => {
    adapter.current?.focus(props.focusPoints, props.reducedMotion);
  }, [props.focusKey, loaded, props.reducedMotion]);
  return (
    <section className="map-workspace" aria-label="Geospatial workspace">
      <div
        className="map-canvas"
        ref={container}
        aria-label="Interactive map. Use arrow keys to pan, plus and minus to zoom; drag with control to rotate."
      />
      <div className="map-topbar">
        <div className="workspace-tabs" aria-label="Dataset">
          {(
            [
              ["context", "NYC context"],
              ["archive", "Evidence archive"],
              ["scenario", "Scenario lab"],
            ] as const
          ).map(([value, label]) => (
            <button
              key={value}
              className={props.workspace === value ? "active" : ""}
              onClick={() => props.onWorkspace(value)}
              aria-pressed={props.workspace === value}
            >
              {label}
            </button>
          ))}
        </div>
        <button
          className="map-icon"
          aria-label="Toggle map layers"
          aria-expanded={showLayers}
          onClick={() => setShowLayers(!showLayers)}
        >
          <Layers3 size={17} />
        </button>
      </div>
      {showLayers && (
        <div className="layers-panel panel-surface">
          <span className="eyebrow">MAP LAYERS</span>
          {(
            Object.entries({
              cameras: "Public camera locations",
              risk: "Operational priority",
              forecast: "Forecast road",
              simulation: "Simulated vehicles",
              buildings: "3D buildings",
            }) as [keyof Layers, string][]
          ).map(([key, label]) => (
            <label key={key}>
              <input
                type="checkbox"
                checked={props.layers[key]}
                onChange={(event) =>
                  props.onLayers({
                    ...props.layers,
                    [key]: event.target.checked,
                  })
                }
              />
              {label}
            </label>
          ))}
          <p>
            Gray roads have no observations. Priority is not collision
            probability.
          </p>
        </div>
      )}
      <div className="map-location panel-surface">
        <MapPin size={14} />
        <div>
          <strong>
            {props.workspace === "context"
              ? "New York City"
              : props.workspace === "scenario"
                ? "Synthetic corridor scenario"
                : props.focusPoints.length
                  ? "Selected archive location"
                  : "Archive · location unverified"}
          </strong>
          <span>
            {props.workspace === "context"
              ? "Public snapshots · separate from archive"
              : props.workspace === "scenario"
                ? "Generated demand · no inferred link to footage"
                : props.focusPoints.length
                  ? "Position from source metadata"
                  : "No exact position plotted for this footage"}
          </span>
        </div>
      </div>
      <div className="map-controls">
        <button
          className="map-icon"
          title="Fit selected coverage"
          aria-label="Fit selected coverage"
          onClick={() =>
            adapter.current?.focus(
              props.focusPoints.length
                ? props.focusPoints
                : props.cameras
                    .filter(
                      (camera) => camera.lat != null && camera.lon != null,
                    )
                    .map((camera) => [camera.lon!, camera.lat!]),
              props.reducedMotion,
            )
          }
        >
          <Crosshair size={17} />
        </button>
        <button
          className="map-icon"
          title="Reset north"
          aria-label="Reset north"
          onClick={() => adapter.current?.reset()}
        >
          <Navigation size={17} />
        </button>
        <button
          className="map-icon"
          title="Toggle 2D / 3D tilt"
          aria-label="Toggle 2D / 3D tilt"
          onClick={() => adapter.current?.tilt()}
        >
          <Building2 size={17} />
        </button>
      </div>
      {!loaded && (
        <div className="map-unavailable">
          <CircleAlert size={22} />
          <strong>{status}</strong>
          <p>
            Source lists and evidence remain available. This map requires WebGL2
            and access to OpenFreeMap tiles.
          </p>
        </div>
      )}
      <div className="map-legend panel-surface">
        <span className="eyebrow">ROAD PRIORITY</span>
        <span>
          <i className="dot lime" />
          Low
        </span>
        <span>
          <i className="dot amber" />
          Medium
        </span>
        <span>
          <i className="dot orange" />
          High
        </span>
        <span>
          <i className="dot gray" />
          Unknown
        </span>
        <span>
          <i className="dot purple" />
          Stale
        </span>
      </div>
      <div
        className={`map-status ${status.includes("unavailable") ? "warning" : ""}`}
        title={status}
      >
        {status.includes("unavailable")
          ? "Some map resources unavailable"
          : status}
      </div>
    </section>
  );
}

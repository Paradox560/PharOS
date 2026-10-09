import { useEffect, useRef, useState } from "react";
import {
  Building2,
  Camera,
  Crosshair,
  Layers3,
  Navigation,
  MapPin,
  CircleAlert,
  Plus,
  Minus,
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
  const layerButton = useRef<HTMLButtonElement>(null);
  const layerPanel = useRef<HTMLDivElement>(null);
  const keyboardInput = useRef(true);
  const propsRef = useRef(props);
  propsRef.current = props;
  const [status, setStatus] = useState("Connecting to vector map…");
  const [loaded, setLoaded] = useState(false);
  const [showLayers, setShowLayers] = useState(false);
  const unlocatedArchive = props.workspace === "archive" && !props.focusPoints.length;
  const visibleCameras = props.cameras.filter((camera) => camera.lat != null && camera.lon != null);
  // Archive media and the separate NYC scenario must never share implied geography.
  const layers = props.workspace === "archive"
    ? { ...props.layers, cameras: false, risk: false, forecast: false, simulation: false }
    : props.layers;
  const cameraLegend = layers.cameras && visibleCameras.length > 0;
  const riskLegend = layers.risk && props.roads.length > 0;
  const forecastLegend = layers.forecast && props.forecast && props.roads.some((road) => road.id === props.forecast?.road_id);
  const vehicleScenarios = layers.simulation ? [...new Set(props.vehicles.map((item) => item.scenario))] : [];

  useEffect(() => {
    const onKeyboard = () => { keyboardInput.current = true; };
    const onPointer = () => { keyboardInput.current = false; };
    document.addEventListener("keydown", onKeyboard, true);
    document.addEventListener("pointerdown", onPointer, true);
    return () => {
      document.removeEventListener("keydown", onKeyboard, true);
      document.removeEventListener("pointerdown", onPointer, true);
    };
  }, []);
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
    adapter.current?.update({ ...props, layers });
  }, [
    props.cameras,
    props.roads,
    props.risk,
    props.forecast,
    props.vehicles,
    props.selectedCamera,
    props.layers,
    props.workspace,
    props.reducedMotion,
    loaded,
  ]);
  useEffect(() => {
    adapter.current?.focus(
      props.focusPoints,
      props.reducedMotion || keyboardInput.current,
      unlocatedArchive,
    );
  }, [props.focusKey, loaded, props.reducedMotion]);
  useEffect(() => {
    if (!showLayers) return;
    layerPanel.current?.querySelector<HTMLInputElement>("input:not(:disabled)")?.focus();
    const close = () => {
      setShowLayers(false);
      layerButton.current?.focus();
    };
    const onEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        close();
      }
    };
    const onOutside = (event: PointerEvent) => {
      const target = event.target as Node;
      if (!layerPanel.current?.contains(target) && !layerButton.current?.contains(target)) {
        setShowLayers(false);
        requestAnimationFrame(() => {
          if (document.activeElement === document.body) layerButton.current?.focus();
        });
      }
    };
    document.addEventListener("keydown", onEscape);
    document.addEventListener("pointerdown", onOutside);
    return () => {
      document.removeEventListener("keydown", onEscape);
      document.removeEventListener("pointerdown", onOutside);
    };
  }, [showLayers]);
  const immediate = (event: { detail: number }) => props.reducedMotion || event.detail === 0;
  const locationTitle = props.workspace === "context"
    ? "New York City"
    : props.workspace === "scenario"
      ? "Simulation corridor"
      : unlocatedArchive ? "Footage location unavailable" : "Archive location";
  const locationDetail = props.workspace === "context"
    ? `${visibleCameras.length} public camera locations`
    : props.workspace === "scenario"
      ? "Generated demand · independent of footage"
      : unlocatedArchive ? "No verified coordinates for this footage" : "Position from source metadata";
  return (
    <section className="map-workspace" aria-label="Geospatial workspace">
      <div
        className="map-canvas"
        ref={container}
        aria-label="Interactive map. Use arrow keys to pan, plus and minus to zoom; hold Shift with arrow keys to rotate or tilt."
      />
      <div className="map-topbar">
        <div className="map-location panel-surface">
          <MapPin size={16} aria-hidden="true" />
          <div className="map-context-copy">
            <strong>{locationTitle}</strong>
            <span>{locationDetail}</span>
          </div>
        </div>
        <button
          ref={layerButton}
          className="map-layers-button panel-surface"
          aria-label="Toggle map layers"
          aria-expanded={showLayers}
          aria-controls="map-layer-options"
          onClick={() => setShowLayers(!showLayers)}
        >
          <Layers3 size={17} aria-hidden="true" />
          Layers
        </button>
      </div>
      {showLayers && (
        <div ref={layerPanel} id="map-layer-options" className="layers-panel panel-surface" role="group" aria-label="Map layers">
          <span className="eyebrow">MAP LAYERS</span>
          {(
            Object.entries({
              cameras: "Public camera locations",
              risk: "Road priority",
              forecast: "Forecast road",
              simulation: "Simulated vehicles",
              buildings: "3D buildings",
            }) as [keyof Layers, string][]
          ).map(([key, label]) => (
            <label key={key}>
              <input
                type="checkbox"
                checked={layers[key]}
                disabled={props.workspace === "archive" && key !== "buildings"}
                onChange={(event) => props.onLayers({ ...props.layers, [key]: event.target.checked })}
              />
              {label}
            </label>
          ))}
          <p>{props.workspace === "archive"
            ? "NYC context and simulation layers are available in their own workspaces."
            : "Camera markers show locations. Road priority summarizes available observations; gray means no coverage."}</p>
        </div>
      )}
      <div className="map-controls">
        <button className="map-icon" title="Zoom in" aria-label="Zoom in" onClick={(event) => adapter.current?.zoom(1, immediate(event))}>
          <Plus size={17} />
        </button>
        <button className="map-icon" title="Zoom out" aria-label="Zoom out" onClick={(event) => adapter.current?.zoom(-1, immediate(event))}>
          <Minus size={17} />
        </button>
        <button
          className="map-icon"
          title={unlocatedArchive ? "No verified footage location to fit" : "Fit selected coverage"}
          aria-label="Fit selected coverage"
          disabled={unlocatedArchive}
          onClick={(event) => adapter.current?.focus(
            props.focusPoints.length ? props.focusPoints : visibleCameras.map((camera) => [camera.lon!, camera.lat!]),
            immediate(event),
          )}
        >
          <Crosshair size={17} />
        </button>
        <button className="map-icon" title="Reset north" aria-label="Reset north" onClick={(event) => adapter.current?.reset(immediate(event))}>
          <Navigation size={17} />
        </button>
        <button className="map-icon" title="Toggle 2D / 3D tilt" aria-label="Toggle 2D / 3D tilt" onClick={(event) => adapter.current?.tilt(immediate(event))}>
          <Building2 size={17} />
        </button>
      </div>
      {!loaded && (
        <div className="map-unavailable">
          <CircleAlert size={22} />
          <strong>{status}</strong>
          <p>Source lists and evidence remain available. This map requires WebGL2 and access to OpenFreeMap tiles.</p>
        </div>
      )}
      {loaded && unlocatedArchive && (
        <div className="map-location-empty panel-surface" role="status">
          <MapPin size={20} aria-hidden="true" />
          <strong>This footage has no verified map position.</strong>
          <p>Review its video and evidence in the inspector.</p>
        </div>
      )}
      {(cameraLegend || riskLegend || forecastLegend || vehicleScenarios.length > 0) && (
        <div className="map-legend panel-surface" aria-label="Visible map layers">
          {cameraLegend && <div className="legend-group legend-camera"><Camera size={15} aria-hidden="true" /><span>Camera locations</span></div>}
          {riskLegend && <div className="legend-group">
            <span className="eyebrow">ROAD PRIORITY</span>
            <span><i className="dot lime" />Low</span>
            <span><i className="dot amber" />Medium</span>
            <span><i className="dot orange" />High</span>
            <span><i className="dot gray" />Unknown</span>
            <span><i className="dot purple" />Stale</span>
          </div>}
          {forecastLegend && <div className="legend-group"><i className="legend-line" style={{ borderColor: "#9fa8ff" }} /><span>Forecast road</span></div>}
          {vehicleScenarios.length > 0 && <div className="legend-group">
            <span className="eyebrow">SIMULATED</span>
            {vehicleScenarios.map((scenario) => <span key={scenario}>
              <i className="dot" style={{ background: scenario === "baseline" ? "#e2e8e0" : scenario === "early" ? "#c5ef8c" : "#fa8c66" }} />
              {scenario === "baseline" ? "Baseline" : scenario === "early" ? "Early clearance" : "Late clearance"}
            </span>)}
          </div>}
        </div>
      )}
      <div className={`map-status ${status.includes("unavailable") ? "warning" : ""}`} title={status}>
        {status.includes("unavailable") ? "Some map resources unavailable" : status}
      </div>
    </section>
  );
}

import * as maplibregl from "maplibre-gl";
import type {
  GeoJSONSource,
  Map as LibreMap,
  ExpressionSpecification,
} from "maplibre-gl";
import workerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url";
import type {
  Camera,
  ForecastRun,
  Layers,
  RoadSegment,
  RiskCell,
  VehicleState,
} from "./types";

const empty = { type: "FeatureCollection" as const, features: [] };
maplibregl.setWorkerUrl(workerUrl);
export interface MapData {
  cameras: Camera[];
  roads: RoadSegment[];
  risk: RiskCell[];
  forecast: ForecastRun | null;
  vehicles: { vehicle: VehicleState; scenario: string }[];
  selectedCamera: string | null;
  layers: Layers;
}
export interface MapAdapter {
  update(data: MapData): void;
  focus(points: [number, number][], reducedMotion: boolean): void;
  reset(): void;
  tilt(): void;
  resize(): void;
  destroy(): void;
}

/** Provider-specific rendering is isolated here; the console passes WGS84 data only. */
export class MapLibreAdapter implements MapAdapter {
  private map: LibreMap;
  private ready = false;
  private reducedMotion = matchMedia("(prefers-reduced-motion: reduce)")
    .matches;
  private pending: MapData | null = null;
  constructor(
    container: HTMLDivElement,
    onSelect: (kind: "camera" | "road", id: string) => void,
    onStatus: (status: string, ready: boolean) => void,
  ) {
    this.map = new maplibregl.Map({
      container,
      style: "https://tiles.openfreemap.org/styles/dark",
      center: [-73.9851, 40.7538],
      zoom: 14.1,
      pitch: 52,
      bearing: -27,
      maxPitch: 75,
      attributionControl: false,
      canvasContextAttributes: { antialias: true },
    });
    this.map.addControl(
      new maplibregl.NavigationControl({ visualizePitch: true }),
      "bottom-right",
    );
    this.map.addControl(
      new maplibregl.AttributionControl({ compact: true }),
      "bottom-left",
    );
    this.map.addControl(
      new maplibregl.ScaleControl({ maxWidth: 100, unit: "metric" }),
      "bottom-left",
    );
    this.map.on("error", (event) =>
      onStatus(
        `Map resource unavailable: ${event.error.message.slice(0, 130)}`,
        this.ready,
      ),
    );
    this.map.on("load", () => {
      this.map.addSource("pharos-buildings", {
        type: "vector",
        url: "https://tiles.openfreemap.org/planet",
      });
      const labels = this.map
        .getStyle()
        .layers.find((layer) => layer.type === "symbol")?.id;
      this.map.addLayer(
        {
          id: "pharos-buildings",
          type: "fill-extrusion",
          source: "pharos-buildings",
          "source-layer": "building",
          minzoom: 14,
          filter: ["!=", ["get", "hide_3d"], true],
          paint: {
            "fill-extrusion-color": [
              "interpolate",
              ["linear"],
              ["coalesce", ["get", "render_height"], 0],
              0,
              "#252e2d",
              100,
              "#3a4542",
              350,
              "#4e5a51",
            ],
            "fill-extrusion-height": ["coalesce", ["get", "render_height"], 6],
            "fill-extrusion-base": [
              "coalesce",
              ["get", "render_min_height"],
              0,
            ],
            "fill-extrusion-opacity": 0.83,
          },
        },
        labels,
      );
      this.map.addSource("pharos-roads", { type: "geojson", data: empty });
      this.map.addSource("pharos-forecast", { type: "geojson", data: empty });
      this.map.addSource("pharos-cameras", {
        type: "geojson",
        data: empty,
        cluster: true,
        clusterMaxZoom: 12,
        clusterRadius: 42,
      });
      this.map.addSource("pharos-vehicles", { type: "geojson", data: empty });
      const riskColor: ExpressionSpecification = [
        "match",
        ["get", "level"],
        "high",
        "#fa8c66",
        "medium",
        "#dfc779",
        "low",
        "#b6d978",
        "stale",
        "#957fad",
        "#697773",
      ];
      this.map.addLayer({
        id: "pharos-roads-glow",
        type: "line",
        source: "pharos-roads",
        paint: {
          "line-color": riskColor,
          "line-width": 16,
          "line-opacity": 0.14,
          "line-blur": 6,
        },
      });
      this.map.addLayer({
        id: "pharos-roads",
        type: "line",
        source: "pharos-roads",
        layout: { "line-cap": "round", "line-join": "round" },
        paint: {
          "line-color": riskColor,
          "line-width": 5,
          "line-opacity": 0.9,
        },
      });
      this.map.addLayer({
        id: "pharos-forecast",
        type: "line",
        source: "pharos-forecast",
        paint: {
          "line-color": "#9fa8ff",
          "line-width": 8,
          "line-dasharray": [1, 2],
          "line-opacity": 0.9,
        },
      });
      this.map.addLayer({
        id: "pharos-clusters",
        type: "circle",
        source: "pharos-cameras",
        filter: ["has", "point_count"],
        paint: {
          "circle-color": "#b6df7d",
          "circle-radius": 16,
          "circle-stroke-width": 4,
          "circle-stroke-color": "#202b20",
        },
      });
      this.map.addLayer({
        id: "pharos-cluster-count",
        type: "symbol",
        source: "pharos-cameras",
        filter: ["has", "point_count"],
        layout: {
          "text-field": ["get", "point_count_abbreviated"],
          "text-font": ["Noto Sans Regular"],
          "text-size": 11,
        },
        paint: { "text-color": "#102014" },
      });
      this.map.addLayer({
        id: "pharos-camera-halo",
        type: "circle",
        source: "pharos-cameras",
        filter: ["!", ["has", "point_count"]],
        paint: {
          "circle-radius": ["case", ["get", "selected"], 18, 11],
          "circle-color": "#bfe18b",
          "circle-opacity": 0.13,
        },
      });
      this.map.addLayer({
        id: "pharos-cameras",
        type: "circle",
        source: "pharos-cameras",
        filter: ["!", ["has", "point_count"]],
        paint: {
          "circle-radius": ["case", ["get", "selected"], 7, 5],
          "circle-color": [
            "match",
            ["get", "status"],
            "unavailable",
            "#6a746c",
            "demo",
            "#d9be77",
            "cached",
            "#d9be77",
            "#c5ef8c",
          ],
          "circle-stroke-color": "#18221c",
          "circle-stroke-width": 2,
        },
      });
      this.map.addLayer({
        id: "pharos-camera-labels",
        type: "symbol",
        source: "pharos-cameras",
        minzoom: 14,
        filter: ["!", ["has", "point_count"]],
        layout: {
          "text-field": ["get", "name"],
          "text-font": ["Noto Sans Regular"],
          "text-size": 10,
          "text-offset": [0, 1.7],
          "text-max-width": 14,
        },
        paint: {
          "text-color": "#dbe6d8",
          "text-halo-color": "#0a100e",
          "text-halo-width": 2,
        },
      });
      this.map.addLayer({
        id: "pharos-vehicles",
        type: "circle",
        source: "pharos-vehicles",
        paint: {
          "circle-color": [
            "match",
            ["get", "scenario"],
            "baseline",
            "#e2e8e0",
            "early",
            "#c5ef8c",
            "#fa8c66",
          ],
          "circle-radius": 4,
          "circle-stroke-color": "#172119",
          "circle-stroke-width": 1,
        },
      });
      this.map.on("click", "pharos-cameras", (event) => {
        const id = event.features?.[0]?.properties?.id;
        if (id) onSelect("camera", id);
      });
      this.map.on("click", "pharos-roads", (event) => {
        const id = event.features?.[0]?.properties?.id;
        if (id) onSelect("road", id);
      });
      this.map.on("click", "pharos-clusters", async (event) => {
        const feature = event.features?.[0];
        if (!feature || feature.geometry.type !== "Point") return;
        const zoom = await (
          this.map.getSource("pharos-cameras") as GeoJSONSource
        ).getClusterExpansionZoom(feature.properties.cluster_id);
        this.map.easeTo({
          center: feature.geometry.coordinates as [number, number],
          zoom,
          duration: this.reducedMotion ? 0 : 700,
        });
      });
      for (const layer of [
        "pharos-cameras",
        "pharos-roads",
        "pharos-clusters",
      ]) {
        this.map.on("mouseenter", layer, () => {
          this.map.getCanvas().style.cursor = "pointer";
        });
        this.map.on("mouseleave", layer, () => {
          this.map.getCanvas().style.cursor = "";
        });
      }
      this.ready = true;
      if (this.pending) this.update(this.pending);
      onStatus("OpenFreeMap · vector map", true);
    });
  }
  update(data: MapData) {
    this.pending = data;
    if (!this.ready) return;
    const cameras = data.cameras.filter(
      (camera) => camera.lat != null && camera.lon != null,
    );
    (this.map.getSource("pharos-cameras") as GeoJSONSource).setData({
      type: "FeatureCollection",
      features: cameras.map((camera) => ({
        type: "Feature",
        properties: {
          id: camera.id,
          name: camera.name,
          status: camera.status,
          selected: camera.id === data.selectedCamera,
        },
        geometry: { type: "Point", coordinates: [camera.lon!, camera.lat!] },
      })),
    });
    (this.map.getSource("pharos-roads") as GeoJSONSource).setData({
      type: "FeatureCollection",
      features: data.roads.map((road) => ({
        type: "Feature",
        properties: {
          id: road.id,
          level:
            data.risk.find((risk) => risk.road_id === road.id)?.level ||
            "unknown",
        },
        geometry: road.geometry,
      })),
    });
    (this.map.getSource("pharos-forecast") as GeoJSONSource).setData({
      type: "FeatureCollection",
      features: data.forecast
        ? data.roads
            .filter((road) => road.id === data.forecast?.road_id)
            .map((road) => ({
              type: "Feature",
              properties: { id: road.id },
              geometry: road.geometry,
            }))
        : [],
    });
    (this.map.getSource("pharos-vehicles") as GeoJSONSource).setData({
      type: "FeatureCollection",
      features: data.vehicles.map(({ vehicle, scenario }) => ({
        type: "Feature",
        properties: { id: vehicle.id, scenario },
        geometry: { type: "Point", coordinates: [vehicle.lon, vehicle.lat] },
      })),
    });
    for (const [key, ids] of Object.entries({
      cameras: [
        "pharos-cameras",
        "pharos-camera-halo",
        "pharos-camera-labels",
        "pharos-clusters",
        "pharos-cluster-count",
      ],
      risk: ["pharos-roads", "pharos-roads-glow"],
      forecast: ["pharos-forecast"],
      simulation: ["pharos-vehicles"],
      buildings: ["pharos-buildings"],
    })) {
      for (const id of ids)
        this.map.setLayoutProperty(
          id,
          "visibility",
          data.layers[key as keyof Layers] ? "visible" : "none",
        );
    }
  }
  focus(points: [number, number][], reducedMotion: boolean) {
    this.reducedMotion = reducedMotion;
    if (!points.length) return;
    if (points.length === 1)
      this.map.easeTo({
        center: points[0],
        zoom: 15.4,
        duration: reducedMotion ? 0 : 700,
      });
    else
      this.map.fitBounds(
        points.reduce(
          (bounds, point) => bounds.extend(point),
          new maplibregl.LngLatBounds(points[0], points[0]),
        ),
        { padding: 70, maxZoom: 15.5, duration: reducedMotion ? 0 : 700 },
      );
  }
  reset() {
    this.map.easeTo({ bearing: 0, duration: this.reducedMotion ? 0 : 450 });
  }
  tilt() {
    this.map.easeTo({
      pitch: this.map.getPitch() > 15 ? 0 : 55,
      duration: this.reducedMotion ? 0 : 450,
    });
  }
  resize() {
    this.map.resize();
  }
  destroy() {
    this.map.remove();
  }
}

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Activity,
  ArrowDownToLine,
  ArrowRight,
  Camera as CameraIcon,
  ChartNoAxesCombined,
  Check,
  ChevronRight,
  Command,
  FileVideo2,
  FlaskConical,
  Layers3,
  MapPin,
  Radio,
  RefreshCw,
  Search,
  Settings2,
  ShieldCheck,
  FileText,
  X,
} from "lucide-react";
import type {
  Answer,
  Camera,
  EvidenceBundle,
  ForecastRun,
  Incident,
  Job,
  Layers,
  MediaAsset,
  Overview,
  Playback,
  ProviderStatus,
  SearchHit,
  SearchResponse,
  SimulationRun,
  SimulationScenario,
  Workspace,
} from "./types";
import { humanize, request, timecode, timestamp } from "./api";
import { Badge, Empty, ErrorMessage, Loading, OriginBadge } from "./ui";
import MapWorkspace from "./MapWorkspace";
import EvidencePanel from "./EvidencePanel";
import ForecastPanel from "./ForecastPanel";
import ScenarioPanel from "./ScenarioPanel";

type Panel = "evidence" | "forecast" | "scenario" | "brief";
type SourceTab = "incidents" | "sources" | "search";
const defaultLayers: Layers = {
  cameras: true,
  risk: true,
  forecast: true,
  simulation: true,
  buildings: true,
};
const defaultQuestion =
  "Summarize the obstruction evidence, uncertainty, and next steps for an operator. Cite evidence IDs and clearly separate any forecast and synthetic simulation from the archive.";

export default function App() {
  const [overview, setOverview] = useState<Overview | null>(null);
  const [initialLoading, setInitialLoading] = useState(true);
  const [globalError, setGlobalError] = useState<string | null>(null);
  const [apiConnected, setApiConnected] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [workspace, setWorkspace] = useState<Workspace>("context");
  const [sourceTab, setSourceTab] = useState<SourceTab>("incidents");
  const [panel, setPanel] = useState<Panel>("evidence");
  const [layers, setLayers] = useState(defaultLayers);
  const [cameraId, setCameraId] = useState<string | null>(null);
  const [assetId, setAssetId] = useState<string | null>(null);
  const [incidentId, setIncidentId] = useState<string | null>(null);
  const [roadId, setRoadId] = useState("");
  const [bundle, setBundle] = useState<EvidenceBundle | null>(null);
  const [evidenceLoading, setEvidenceLoading] = useState(false);
  const [evidenceError, setEvidenceError] = useState<string | null>(null);
  const [evidenceVersion, setEvidenceVersion] = useState(0);
  const [seek, setSeek] = useState({ seconds: 0, key: 0 });
  const [cameraQuery, setCameraQuery] = useState("");
  const [borough, setBorough] = useState("all");
  const [corridor, setCorridor] = useState("all");
  const [searchQuery, setSearchQuery] = useState("");
  const [search, setSearch] = useState<SearchResponse | null>(null);
  const [searchLoading, setSearchLoading] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [archiveLoading, setArchiveLoading] = useState(false);
  const [archiveError, setArchiveError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [forecast, setForecast] = useState<ForecastRun | null>(null);
  const [forecastLoading, setForecastLoading] = useState(false);
  const [forecastError, setForecastError] = useState<string | null>(null);
  const [job, setJob] = useState<Job | null>(null);
  const [analysisJob, setAnalysisJob] = useState<Job | null>(null);
  const [analysisStarting, setAnalysisStarting] = useState(false);
  const completedAnalysis = useRef<string | null>(null);
  const completedSimulation = useRef<string | null>(null);
  const [simulation, setSimulation] = useState<SimulationRun | null>(null);
  const [simulationError, setSimulationError] = useState<string | null>(null);
  const [simulationStarting, setSimulationStarting] = useState(false);
  const [playback, setPlayback] = useState<Playback | null>(null);
  const [frame, setFrame] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [comparison, setComparison] = useState<"early" | "late">("early");
  const [question, setQuestion] = useState(defaultQuestion);
  const [answer, setAnswer] = useState<Answer | null>(null);
  const [answerLoading, setAnswerLoading] = useState(false);
  const [answerError, setAnswerError] = useState<string | null>(null);
  const [providerOpen, setProviderOpen] = useState(false);
  const [checking, setChecking] = useState(false);
  const [checkError, setCheckError] = useState<string | null>(null);
  const [reducedMotion, setReducedMotion] = useState(
    () => window.matchMedia("(prefers-reduced-motion: reduce)").matches,
  );
  const providerDialog = useRef<HTMLDialogElement>(null);
  const searchInput = useRef<HTMLInputElement>(null);
  const inspectorHeading = useRef<HTMLHeadingElement>(null);
  const inspectorScroll = useRef<HTMLDivElement>(null);
  const [mobileView, setMobileView] = useState<"sources" | "map" | "details">(
    "map",
  );

  useEffect(() => {
    const keyboard = (event: KeyboardEvent) => {
      if (["Tab", "Enter", " ", "ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(event.key))
        document.documentElement.dataset.input = "keyboard";
    };
    const pointer = () => { document.documentElement.dataset.input = "pointer"; };
    window.addEventListener("keydown", keyboard, true);
    window.addEventListener("pointerdown", pointer, true);
    return () => { window.removeEventListener("keydown", keyboard, true); window.removeEventListener("pointerdown", pointer, true); };
  }, []);
  useEffect(() => {
    if (mobileView === "details" && window.matchMedia("(max-width: 1000px)").matches)
      {
        const heading = inspectorScroll.current?.querySelector<HTMLHeadingElement>("h2");
        if (heading) { heading.tabIndex = -1; heading.focus({ preventScroll: true }); }
        else inspectorHeading.current?.focus({ preventScroll: true });
      }
  }, [mobileView, panel]);

  useEffect(() => { inspectorScroll.current?.scrollTo({ top: 0, behavior: "instant" }); }, [panel, assetId, cameraId]);

  const loadOverview = useCallback(async () => {
    setGlobalError(null);
    try {
      const data = await request<Overview>("/overview");
      setOverview(data);
      setApiConnected(true);
      setAssetId((current) => current || data.assets[0]?.id || null);
      setRoadId((current) => current || data.roads[0]?.id || "");
    } catch (error) {
      setGlobalError((error as Error).message);
      setApiConnected(false);
    } finally {
      setInitialLoading(false);
    }
  }, []);
  useEffect(() => {
    void loadOverview();
  }, [loadOverview]);
  useEffect(() => {
    if (!assetId) {
      setBundle(null);
      return;
    }
    const controller = new AbortController();
    setEvidenceLoading(true);
    setEvidenceError(null);
    setBundle(null);
    request<EvidenceBundle>(
      `/assets/${encodeURIComponent(assetId)}/evidence`,
      undefined,
      controller.signal,
    )
      .then(setBundle)
      .catch((error: Error) => {
        if (error.name !== "AbortError") setEvidenceError(error.message);
      })
      .finally(() => {
        if (!controller.signal.aborted) setEvidenceLoading(false);
      });
    return () => controller.abort();
  }, [assetId, evidenceVersion]);
  useEffect(() => {
    if (providerOpen) providerDialog.current?.showModal();
    else providerDialog.current?.close();
  }, [providerOpen]);
  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key === "k") {
        event.preventDefault();
        searchInput.current?.focus();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);
  useEffect(() => {
    if (!job || !["queued", "running"].includes(job.state)) return;
    const timer = window.setTimeout(async () => {
      try {
        const next = await request<Job>(`/jobs/${encodeURIComponent(job.id)}`);
        setSimulationError(null);
        setJob((current) =>
          current?.state === "cancelled" || current?.id !== next.id
            ? current
            : next,
        );
      } catch (error) {
        setSimulationError(
          `Job status unavailable; retrying. ${(error as Error).message}`,
        );
        setJob((current) => (current ? { ...current } : current));
      }
    }, 1100);
    return () => window.clearTimeout(timer);
  }, [job]);
  useEffect(() => {
    if (
      job?.state !== "succeeded" ||
      !job.result ||
      completedSimulation.current === job.id
    )
      return;
    completedSimulation.current = job.id;
    const run = job.result as SimulationRun;
    setSimulation(run);
    setWorkspace("scenario");
    void loadOverview();
    request<Playback>(`/simulations/${encodeURIComponent(run.id)}/playback`)
      .then((replay) => {
        setPlayback(replay);
        setFrame(0);
      })
      .catch((error: Error) =>
        setSimulationError(
          `Simulation completed; playback unavailable. ${error.message}`,
        ),
      );
  }, [job, loadOverview]);
  useEffect(() => {
    if (!analysisJob) return;
    if (
      analysisJob.state === "succeeded" &&
      completedAnalysis.current !== analysisJob.id
    ) {
      completedAnalysis.current = analysisJob.id;
      setEvidenceVersion((value) => value + 1);
      void loadOverview();
      setNotice(
        "Stored evidence review completed. No new pipeline inference was performed.",
      );
      return;
    }
    if (analysisJob.state === "failed" || analysisJob.state === "cancelled") {
      setEvidenceError(
        `Stored evidence review ${analysisJob.state}: ${typeof analysisJob.error === "string" ? analysisJob.error : "No updated evidence available."}`,
      );
      return;
    }
    if (!["queued", "running"].includes(analysisJob.state)) return;
    const timer = window.setTimeout(() => {
      request<Job>(`/jobs/${encodeURIComponent(analysisJob.id)}`)
        .then(setAnalysisJob)
        .catch((error: Error) => {
          setNotice(`Review status unavailable; retrying. ${error.message}`);
          setAnalysisJob((value) => (value ? { ...value } : value));
        });
    }, 1200);
    return () => window.clearTimeout(timer);
  }, [analysisJob, loadOverview]);
  useEffect(() => {
    if (!playing || !playback?.frames.length) return;
    const timer = window.setInterval(
      () =>
        setFrame((current) => {
          if (current >= playback.frames.length - 1) {
            setPlaying(false);
            return current;
          }
          return current + 1;
        }),
      350,
    );
    return () => window.clearInterval(timer);
  }, [playing, playback]);

  const selectedCamera =
    overview?.cameras.find((camera) => camera.id === cameraId) || null;
  const selectedIncident =
    overview?.incidents.find((incident) => incident.id === incidentId) || null;
  const filteredCameras = useMemo(
    () =>
      (overview?.cameras || []).filter(
        (camera) =>
          (borough === "all" || camera.borough === borough) &&
          (corridor === "all" || camera.corridor === corridor) &&
          `${camera.name} ${camera.corridor || ""}`
            .toLowerCase()
            .includes(cameraQuery.toLowerCase()),
      ),
    [overview?.cameras, borough, corridor, cameraQuery],
  );
  const focusPoints = useMemo<[number, number][]>(() => {
    if (panel === "forecast") return overview?.roads.find((road) => road.id === roadId)?.geometry.coordinates.map((point) => [point[0], point[1]] as [number, number]) || [];
    if (workspace === "scenario")
      return (overview?.roads || []).flatMap((road) =>
        road.geometry.coordinates.map(
          (point) => [point[0], point[1]] as [number, number],
        ),
      );
    if (workspace === "archive")
      return bundle?.asset.lat != null && bundle.asset.lon != null
        ? [[bundle.asset.lon, bundle.asset.lat]]
        : [];
    if (selectedCamera?.lat != null && selectedCamera.lon != null)
      return [[selectedCamera.lon, selectedCamera.lat]];
    return filteredCameras
      .filter((camera) => camera.lat != null && camera.lon != null)
      .map((camera) => [camera.lon!, camera.lat!]);
  }, [
    workspace,
    panel,
    roadId,
    overview?.roads,
    bundle?.asset,
    selectedCamera,
    filteredCameras,
  ]);
  const vehicles = useMemo(() => {
    const current = playback?.frames[frame];
    return current
      ? [
          ...current.baseline.map((vehicle) => ({
            vehicle,
            scenario: "baseline",
          })),
          ...current[comparison].map((vehicle) => ({
            vehicle,
            scenario: comparison,
          })),
        ]
      : [];
  }, [playback, frame, comparison]);
  const readyProviders =
    overview?.integrations.filter((provider) => provider.status === "ready")
      .length || 0;
  const selectCamera = (camera: Camera) => {
    setCameraId(camera.id);
    setIncidentId(null);
    setEvidenceError(null);
    setPanel("evidence");
    setWorkspace("context");
    setMobileView("details");
  };
  const selectAsset = (asset: MediaAsset | string, seconds = 0) => {
    setAssetId(typeof asset === "string" ? asset : asset.id);
    setCameraId(null);
    setIncidentId(null);
    setSeek({ seconds, key: Date.now() });
    setPanel("evidence");
    setWorkspace("archive");
    setMobileView("details");
  };
  const selectIncident = (incident: Incident) => {
    setIncidentId(incident.id);
    setPanel("evidence");
    setCameraId(null);
    setMobileView("details");
    const asset =
      incident.asset_id ||
      overview?.assets.find(
        (candidate) =>
          incident.camera_id != null &&
          candidate.camera_id === incident.camera_id,
      )?.id;
    if (asset) {
      setAssetId(asset);
      setSeek({ seconds: 0, key: Date.now() });
      setWorkspace("archive");
    } else {
      setAssetId(null);
      setEvidenceError(
        "This incident has no linked playable archive asset. Its listed evidence IDs remain available in the incident queue.",
      );
    }
    if (incident.road_id) setRoadId(incident.road_id);
  };
  const chooseWorkspace = (next: Workspace) => {
    setWorkspace(next);
    if (next === "archive") {
      setPanel("evidence");
      setCameraId(null);
      setSourceTab("sources");
      void loadArchive();
    }
    if (next === "context") setSourceTab("sources");
    if (next === "scenario") {
      setPanel("scenario");
      setCameraId(null);
    }
  };
  const doSearch = async (query: string) => {
    if (!query.trim()) return;
    setSearchQuery(query);
    setSourceTab("search");
    setSearchLoading(true);
    setSearchError(null);
    setMobileView("sources");
    try {
      setSearch(
        await request<SearchResponse>("/search", {
          query: query.trim(),
          top_k: 10,
          time_filter: "all",
          metadata_filters: {},
          tags: [],
        }),
      );
    } catch (error) {
      setSearchError((error as Error).message);
    } finally {
      setSearchLoading(false);
    }
  };
  const loadArchive = async () => {
    setArchiveLoading(true);
    setArchiveError(null);
    try {
      const data = await request<{ assets: MediaAsset[] }>(
        "/archive?limit=24&offset=0",
      );
      setOverview((current) =>
        current ? { ...current, assets: data.assets } : current,
      );
    } catch (error) {
      setArchiveError((error as Error).message);
    } finally {
      setArchiveLoading(false);
    }
  };
  const refreshSources = async () => {
    setRefreshing(true);
    setGlobalError(null);
    try {
      const result = await request<{ status?: string }>("/sources/refresh", {});
      await loadOverview();
      setNotice(
        `Source refresh finished: ${humanize(result.status || "check complete")}. Check provider status and source timestamps for availability and freshness.`,
      );
    } catch (error) {
      setGlobalError((error as Error).message);
    } finally {
      setRefreshing(false);
    }
  };
  const runForecast = async (mode: string) => {
    setForecastLoading(true);
    setForecastError(null);
    try {
      setForecast(
        await request<ForecastRun>("/forecasts", {
          road_id: roadId,
          horizons: [5, 15, 30],
          mode,
        }),
      );
      void loadOverview();
    } catch (error) {
      setForecastError((error as Error).message);
    } finally {
      setForecastLoading(false);
    }
  };
  const runSimulation = async (scenario: SimulationScenario) => {
    if (
      simulationStarting ||
      (job && ["queued", "running"].includes(job.state))
    )
      return;
    setSimulationStarting(true);
    setSimulationError(null);
    setSimulation(null);
    setPlayback(null);
    setPlaying(false);
    try {
      setJob(await request<Job>("/simulations", scenario));
    } catch (error) {
      setSimulationError((error as Error).message);
    } finally {
      setSimulationStarting(false);
    }
  };
  const cancelSimulation = async () => {
    if (job)
      try {
        setJob(
          await request<Job>(`/jobs/${encodeURIComponent(job.id)}/cancel`, {}),
        );
      } catch (error) {
        setSimulationError((error as Error).message);
      }
  };
  const generateBrief = async () => {
    setPanel("brief");
    setMobileView("details");
    setAnswerLoading(true);
    setAnswerError(null);
    try {
      setAnswer(
        await request<Answer>("/ask", {
          question,
          ...(assetId ? { asset_id: assetId } : {}),
          ...(incidentId ? { incident_id: incidentId } : {}),
          ...(simulation ? { simulation_id: simulation.id } : {}),
          ...(forecast ? { forecast_id: forecast.id } : {}),
        }),
      );
      void loadOverview();
    } catch (error) {
      setAnswerError((error as Error).message);
    } finally {
      setAnswerLoading(false);
    }
  };
  const analyze = async () => {
    if (
      !assetId ||
      analysisStarting ||
      (analysisJob && ["queued", "running"].includes(analysisJob.state))
    )
      return;
    setEvidenceError(null);
    setAnalysisStarting(true);
    try {
      const analysis = await request<Job>("/analysis/jobs", {
        asset_id: assetId,
      });
      setAnalysisJob(analysis);
      setNotice(
        `Stored evidence review ${analysis.state}. This action does not run new pipeline inference.`,
      );
    } catch (error) {
      setEvidenceError((error as Error).message);
    } finally {
      setAnalysisStarting(false);
    }
  };
  const acknowledge = async () => {
    if (!incidentId) return;
    try {
      const updated = await request<Incident>(
        `/incidents/${encodeURIComponent(incidentId)}/acknowledge`,
        {},
      );
      setOverview((current) =>
        current
          ? {
              ...current,
              incidents: current.incidents.map((incident) =>
                incident.id === updated.id ? updated : incident,
              ),
              metrics: {
                ...current.metrics,
                open_incidents: current.incidents.filter(
                  (incident) =>
                    incident.id !== updated.id && incident.status === "open",
                ).length,
              },
            }
          : current,
      );
    } catch (error) {
      setEvidenceError((error as Error).message);
    }
  };
  const checkProviders = async () => {
    setChecking(true);
    setCheckError(null);
    try {
      const data = await request<{ integrations: ProviderStatus[] }>(
        "/integrations/check",
        {},
      );
      setOverview((current) =>
        current ? { ...current, integrations: data.integrations } : current,
      );
    } catch (error) {
      setCheckError((error as Error).message);
    } finally {
      setChecking(false);
    }
  };
  const seedDemo = async () => {
    setGlobalError(null);
    try {
      const data = await request<Overview>("/demo", {});
      setOverview(data);
      setAssetId(data.assets[0]?.id || null);
      setEvidenceVersion((value) => value + 1);
      setRoadId(data.roads[0]?.id || "");
      setNotice(
        "Deterministic demo loaded. Synthetic evidence and outputs are labeled throughout.",
      );
    } catch (error) {
      setGlobalError((error as Error).message);
    }
  };

  return (
    <div className={`app-shell ${reducedMotion ? "reduced-motion" : ""}`}>
      <a className="skip-link" href="#main-workspace">
        Skip to workspace
      </a>
      <nav className="nav-rail" aria-label="Primary">
        <button
          className="brand-symbol"
          aria-label="PharOS overview"
          onClick={() => {
            setWorkspace("context");
            setSourceTab("incidents");
            setPanel("evidence");
            setMobileView("map");
          }}
        >
          <span />
        </button>
        <div className="rail-links">
          <button
            className={
              workspace === "context" && sourceTab !== "search" && panel === "evidence" ? "active" : ""
            }
            aria-current={workspace === "context" && sourceTab !== "search" && panel === "evidence" ? "page" : undefined}
            aria-label="City operations"
            title="City operations"
            onClick={() => {
              setWorkspace("context");
              setSourceTab("incidents");
              setPanel("evidence");
              setMobileView("map");
            }}
          >
            <Layers3 size={21} /><span>Overview</span>
          </button>
          <button
            className={
              workspace === "archive" && sourceTab !== "search" && panel === "evidence" ? "active" : ""
            }
            aria-current={workspace === "archive" && sourceTab !== "search" && panel === "evidence" ? "page" : undefined}
            aria-label="Footage archive"
            title="Footage archive"
            onClick={() => { chooseWorkspace("archive"); setMobileView("sources"); }}
          >
            <FileVideo2 size={20} /><span>Footage</span>
          </button>
          <button
            className={sourceTab === "search" ? "active" : ""}
            aria-current={sourceTab === "search" ? "page" : undefined}
            aria-label="Search footage"
            title="Search footage"
            onClick={() => {
              setSourceTab("search");
              setMobileView("sources");
              searchInput.current?.focus();
            }}
          >
            <Search size={20} /><span>Search</span>
          </button>
          <span className="rail-divider" />
          <button
            className={panel === "forecast" ? "active" : ""}
            aria-current={panel === "forecast" ? "page" : undefined}
            aria-label="Traffic forecasts"
            title="Traffic forecasts"
            onClick={() => {
              setPanel("forecast");
              setWorkspace("context");
              setMobileView("details");
            }}
          >
            <ChartNoAxesCombined size={21} /><span>Forecast</span>
          </button>
          <button
            className={panel === "scenario" ? "active" : ""}
            aria-current={panel === "scenario" ? "page" : undefined}
            aria-label="Scenario lab"
            title="Scenario lab"
            onClick={() => {
              chooseWorkspace("scenario");
              setMobileView("details");
            }}
          >
            <FlaskConical size={21} /><span>Simulate</span>
          </button>
        </div>
        <div className="rail-bottom">
          <button
            aria-label="Connection details and preferences"
            title="Connection details and preferences"
            onClick={() => setProviderOpen(true)}
          >
            <Settings2 size={19} /><span>Settings</span>
          </button>
          <div className="operator-avatar" title="Local operator">
            OP
          </div>
        </div>
      </nav>
      <div className="console-shell">
        <header className="header">
          <div className="wordmark">
            phar<span>OS</span>
            <span className="wordmark-divider" />
            <span className="product-name">ROAD OPERATIONS</span>
          </div>
          <form
            className="global-search"
            role="search"
            onSubmit={(event) => {
              event.preventDefault();
              void doSearch(searchQuery);
            }}
          >
            <Search size={16} />
            <input
              ref={searchInput}
              value={searchQuery}
              onChange={(event) => setSearchQuery(event.target.value)}
              placeholder="Search footage by what happened"
              aria-label="Search archive footage"
            />
            <kbd><Command size={10} /> K</kbd>
            <button className="search-submit" type="submit" aria-label="Submit footage search" disabled={!searchQuery.trim() || searchLoading}><ArrowRight size={16} /></button>
          </form>
          <button
            className="connection-button"
            aria-label="Workspace connections"
            onClick={() => setProviderOpen(true)}
          >
            <i className={`dot ${readyProviders ? "lime" : "amber"}`} />
            <span>
              {overview?.mode === "demo" ? "Demo workspace" : "Connections"}
            </span>
            <ChevronRight size={13} />
          </button>
        </header>
        <div className="workspace-header">
          <div>
            <div className="breadcrumb">
              <span className="beacon-mark" /> FIELD DESK <span className="breadcrumb-separator">/</span> {workspace === "scenario" ? "FIRST AVENUE" : workspace === "archive" ? "FOOTAGE LIBRARY" : "NEW YORK CITY"}
            </div>
            <h1>
              {panel === "forecast" ? "Traffic outlook" : panel === "scenario" ? "Clearance scenarios" : panel === "brief" ? "Operator brief" : workspace === "archive" ? "Evidence review" : "Road operations"}
            </h1>
          </div>
          <div className="header-actions">
            <div className="last-sync">
              <span>Workspace updated</span>
              <strong>
                {overview ? timestamp(overview.updated_at) : "Connecting…"}
              </strong>
            </div>
            <button
              className="button secondary compact"
              disabled={refreshing}
              onClick={() => void refreshSources()}
            >
              <RefreshCw size={14} className={refreshing ? "spin" : ""} />
              <span>Refresh sources</span>
            </button>
          </div>
        </div>
        <div className="data-banner">
          <span>
            <i className="dot amber" />
            {overview?.mode === "demo"
              ? "DEMO"
              : "SOURCE NOTES"}
          </span>
          <p>
            <span className="desktop-source-note">{overview?.mode === "demo"
              ? "Explore with sample footage and simulated traffic. NYC camera locations are real; the demo is separate."
              : "Recorded footage, public cameras and simulated traffic are separate sources."}</span>
            <span className="mobile-source-note">{overview?.mode === "demo" ? "Sample footage & traffic. NYC camera locations are real." : "Footage, public cameras & simulations are separate sources."}</span>
          </p>
          <button onClick={() => setProviderOpen(true)}>
            About this workspace <ArrowRight size={13} />
          </button>
        </div>
        {globalError && (
          <div className="global-error">
            <ErrorMessage error={globalError} />
            <button className="text-button" onClick={() => void loadOverview()}>
              Retry API
            </button>
          </div>
        )}
        <div className="mobile-switcher">
          {(["sources", "map", "details"] as const).map((view) => (
            <button
              key={view}
              className={view === mobileView ? "active" : ""}
              aria-pressed={view === mobileView}
              onClick={() => setMobileView(view)}
            >
              {view === "details" ? "Analysis" : view === "sources" ? "Browse" : "Map"}
            </button>
          ))}
        </div>
        <main
          id="main-workspace"
          className={`main-workspace mobile-${mobileView} ${workspace === "archive" && panel === "evidence" && bundle?.asset.coordinate_precision === "unlocated" ? "unlocated-workspace" : ""}`}
        >
          <aside
            className="source-panel"
            aria-label="Sources and incident queue"
          >
            <div className="source-heading">
              <h2>
                {sourceTab === "search"
                  ? "Search results"
                  : sourceTab === "incidents"
                    ? "Review queue"
                    : workspace === "archive" ? "Footage library" : "Camera directory"}
              </h2>
              <span className="desk-index">01</span>
            </div>
            <p className="source-intro">{sourceTab === "incidents" ? "Choose an item to inspect its evidence." : sourceTab === "search" ? "Describe the moment you want to find." : "Select a source to see what is available."}</p>
            <div className="source-tabs" aria-label="Browse sources">
              <button
                className={sourceTab === "incidents" ? "active" : ""}
                aria-pressed={sourceTab === "incidents"}
                onClick={() => setSourceTab("incidents")}
              >
                Review <span>{overview?.metrics.open_incidents ?? "—"}</span>
              </button>
              <button
                className={sourceTab === "sources" ? "active" : ""}
                aria-pressed={sourceTab === "sources"}
                onClick={() => setSourceTab("sources")}
              >
                Browse
              </button>
              <button
                className={sourceTab === "search" ? "active" : ""}
                aria-pressed={sourceTab === "search"}
                onClick={() => setSourceTab("search")}
              >
                Search
              </button>
            </div>
            <div className="source-scroll">
              {initialLoading ? (
                <Loading label="Loading workspace…" />
              ) : !overview ? (
                <Empty title="API not connected">
                  Start the PharOS API, then retry the connection. No local data
                  is substituted.
                </Empty>
              ) : sourceTab === "incidents" ? (
                <>
                  <div className="list-label">
                    NEEDS REVIEW <span>{overview.incidents.length} {overview.incidents.length === 1 ? "item" : "items"}</span>
                  </div>
                  {overview.incidents.length ? (
                    overview.incidents.map((incident) => (
                      <button
                        key={incident.id}
                        className={`incident-card ${incident.id === incidentId ? "selected" : ""}`}
                        aria-pressed={incident.id === incidentId}
                        onClick={() => selectIncident(incident)}
                      >
                        <div className="split">
                          <span
                            className={`incident-priority ${incident.severity}`}
                          >
                            <i className="dot" />
                            {incident.severity} priority
                          </span>
                          <span className="tiny mono">
                            {new Date(incident.timestamp).toLocaleTimeString(
                              "en-US",
                              {
                                hour: "2-digit",
                                minute: "2-digit",
                                hour12: false,
                                timeZone: "UTC",
                              },
                            )}{" "}
                            UTC
                          </span>
                        </div>
                        <h3>{incident.title}</h3>
                        <p>{incident.data_origin === "synthetic" ? "A sample lane obstruction. Open the clip to review the marked moments." : incident.description}</p>
                        <div className="incident-footer">
                          <OriginBadge value={incident.data_origin} />
                          <span>
                            {incident.status === "acknowledged" ? (
                              <Check size={12} />
                            ) : (
                              <span className="open-dot" />
                            )}{" "}
                            {incident.status}
                          </span>
                          <ChevronRight size={13} />
                        </div>
                      </button>
                    ))
                  ) : (
                    <Empty title="No incidents to review">
                      No confirmed normal conditions are implied by an empty
                      queue.
                    </Empty>
                  )}
                  <div className="section-divider" />
                  <div className="list-label">
                    AVAILABLE FOOTAGE <span>{overview.assets.length}</span>
                  </div>
                  {overview.assets.slice(0, 4).map((asset) => (
                    <AssetCard
                      key={asset.id}
                      asset={asset}
                      selected={asset.id === assetId && !cameraId}
                      onClick={() => selectAsset(asset)}
                    />
                  ))}
                </>
              ) : sourceTab === "sources" ? (
                <>
                  <div className="source-dataset-switch">
                    <button
                      className={workspace !== "archive" ? "active" : ""}
                      aria-pressed={workspace !== "archive"}
                      onClick={() => setWorkspace("context")}
                    >
                      <CameraIcon size={13} />
                      NYC cameras
                    </button>
                    <button
                      className={workspace === "archive" ? "active" : ""}
                      aria-pressed={workspace === "archive"}
                      onClick={() => {
                        setWorkspace("archive");
                        void loadArchive();
                      }}
                    >
                      <FileVideo2 size={13} />
                      Archive
                    </button>
                  </div>
                  {workspace === "archive" ? (
                    <>
                      <div className="list-label">
                        INDEXED ASSETS
                        <button
                          className="text-button"
                          onClick={() => void loadArchive()}
                          aria-label="Refresh archive"
                        >
                          <RefreshCw size={12} />
                        </button>
                      </div>
                      <ErrorMessage error={archiveError} />
                      {archiveLoading ? (
                        <Loading label="Querying archive…" />
                      ) : overview.assets.length ? (
                        overview.assets.map((asset) => (
                          <AssetCard
                            key={asset.id}
                            asset={asset}
                            selected={asset.id === assetId}
                            onClick={() => selectAsset(asset)}
                          />
                        ))
                      ) : (
                        <Empty title="No indexed assets returned">
                          Connect the workshop archive or load the explicitly
                          labeled local demo.
                        </Empty>
                      )}
                      <p className="source-footnote">
                        Source locations come from archive metadata. Unlocated
                        footage is listed without a map marker.
                      </p>
                    </>
                  ) : (
                    <>
                      <label className="filter-search">
                        <Search size={14} />
                        <input
                          aria-label="Filter cameras"
                          placeholder="Filter cameras…"
                          value={cameraQuery}
                          onChange={(event) =>
                            setCameraQuery(event.target.value)
                          }
                        />
                      </label>
                      <div className="filter-row">
                        <select
                          aria-label="Filter borough"
                          value={borough}
                          onChange={(event) => {
                            setBorough(event.target.value);
                            setCorridor("all");
                          }}
                        >
                          <option value="all">All boroughs</option>
                          {[
                            ...new Set(
                              overview.cameras
                                .map((camera) => camera.borough)
                                .filter(Boolean),
                            ),
                          ]
                            .sort()
                            .map((value) => (
                              <option key={value} value={value!}>
                                {value}
                              </option>
                            ))}
                        </select>
                        <select
                          aria-label="Filter corridor"
                          value={corridor}
                          onChange={(event) => setCorridor(event.target.value)}
                        >
                          <option value="all">All corridors</option>
                          {[
                            ...new Set(
                              overview.cameras
                                .filter(
                                  (camera) =>
                                    borough === "all" ||
                                    camera.borough === borough,
                                )
                                .map((camera) => camera.corridor)
                                .filter(Boolean),
                            ),
                          ]
                            .sort()
                            .map((value) => (
                              <option key={value} value={value!}>
                                {value}
                              </option>
                            ))}
                        </select>
                      </div>
                      <div className="list-label">
                        CAMERA CATALOG <span>{filteredCameras.length}</span>
                      </div>
                      {filteredCameras.length ? (
                        filteredCameras.slice(0, 150).map((camera) => (
                          <button
                            className={`camera-card ${camera.id === cameraId ? "selected" : ""}`}
                            aria-pressed={camera.id === cameraId}
                            key={camera.id}
                            onClick={() => selectCamera(camera)}
                          >
                            <span className="camera-card-icon">
                              <CameraIcon size={17} />
                            </span>
                            <div>
                              <strong>{camera.name}</strong>
                              <span>
                                {camera.borough || "Borough unknown"} ·{" "}
                                {camera.status} · {camera.provenance.freshness}
                              </span>
                            </div>
                            <i
                              className={`dot ${camera.status === "unavailable" ? "gray" : camera.status === "demo" || camera.status === "cached" ? "amber" : "lime"}`}
                            />
                          </button>
                        ))
                      ) : (
                        <Empty title="No matching cameras">
                          Try a different name, borough, or corridor.
                        </Empty>
                      )}
                      {filteredCameras.length > 150 && (
                        <p className="caption">
                          Showing the first 150 cameras. Narrow the filters for
                          more specific coverage.
                        </p>
                      )}
                    </>
                  )}
                </>
              ) : (
                <>
                  <form
                    className="search-form"
                    onSubmit={(event) => {
                      event.preventDefault();
                      void doSearch(searchQuery);
                    }}
                  >
                    <label className="field">
                      Describe a moment
                      <textarea
                        value={searchQuery}
                        rows={3}
                        onChange={(event) => setSearchQuery(event.target.value)}
                        placeholder="Stopped vehicles obstructing a lane"
                      />
                    </label>
                    <button
                      className="button primary full"
                      disabled={searchLoading || !searchQuery.trim()}
                      type="submit"
                    >
                      {searchLoading ? "Searching…" : "Search footage"}
                      <Search size={14} />
                    </button>
                  </form>
                  <div className="query-suggestions">
                    {[
                      "stopped vehicles obstructing a lane",
                      "traffic slowing near this obstruction",
                    ].map((query) => (
                      <button key={query} onClick={() => void doSearch(query)}>
                        {query}
                        <ArrowRight size={12} />
                      </button>
                    ))}
                  </div>
                  <ErrorMessage error={searchError} />
                  {searchLoading ? (
                    <Loading label="Retrieving matching moments…" />
                  ) : search ? (
                    <>
                      <div className="search-engine">
                        <Badge
                          tone={search.execution_mode === "mock" ? "amber" : ""}
                        >
                          {search.engine}
                        </Badge>
                        <OriginBadge value={search.execution_mode} />
                      </div>
                      {search.notes.map((note, index) => (
                        <p className="caption" key={index}>
                          {note}
                        </p>
                      ))}
                      <div className="list-label">
                        SEGMENT MATCHES <span>{search.results.length}</span>
                      </div>
                      {search.results.length ? (
                        search.results.map((hit) => (
                          <SearchCard
                            key={hit.id}
                            hit={hit}
                            onClick={() =>
                              selectAsset(hit.asset_id, hit.start_sec)
                            }
                          />
                        ))
                      ) : (
                        <Empty title="No matching moments">
                          Try a broader description. Search quality depends on
                          the indexed evidence.
                        </Empty>
                      )}
                      {search.chunk_results.length > 0 && (
                        <details className="provenance">
                          <summary>
                            Parent chunks ({search.chunk_results.length})
                          </summary>
                          {search.chunk_results.map((chunk, index) => (
                            <pre key={index}>
                              {JSON.stringify(chunk, null, 2)}
                            </pre>
                          ))}
                        </details>
                      )}
                    </>
                  ) : (
                    <Empty title="A question, then the evidence">
                      Search indexed footage by the conditions you want to
                      investigate. Demo search is labeled as keyword fallback.
                    </Empty>
                  )}
                </>
              )}
            </div>
            <div className="source-summary">
              <div>
                <strong>{overview?.metrics.cameras ?? "—"}</strong>
                <span>cameras in catalog</span>
              </div>
              <div>
                <strong>{overview?.metrics.assets ?? "—"}</strong>
                <span>available assets</span>
              </div>
            </div>
          </aside>
          <div className="center-panel">
            <MapWorkspace
              workspace={workspace}
              onWorkspace={chooseWorkspace}
              cameras={workspace === "context" ? filteredCameras : []}
              roads={overview?.roads || []}
              risk={overview?.risk || []}
              forecast={forecast}
              vehicles={workspace === "scenario" ? vehicles : []}
              selectedCamera={cameraId}
              layers={layers}
              onLayers={setLayers}
              focusPoints={focusPoints}
              focusKey={`${workspace}:${panel}:${roadId}:${cameraId}:${workspace === "archive" ? bundle?.asset.id : ""}:${workspace === "scenario" ? roadId : ""}:${borough}:${corridor}`}
              reducedMotion={reducedMotion}
              onSelect={(kind, id) => {
                if (kind === "camera") {
                  const camera = overview?.cameras.find(
                    (item) => item.id === id,
                  );
                  if (camera) selectCamera(camera);
                } else {
                  setRoadId(id);
                  setPanel("forecast");
                  setMobileView("details");
                }
              }}
            />
            <div className="map-caption">
              <div><span className="eyebrow">{workspace === "scenario" ? "SCENARIO MAP" : workspace === "archive" ? "FOOTAGE LOCATION" : "CAMERA COVERAGE"}</span>
                <p>{workspace === "scenario" ? "First Avenue · assumed traffic, actual SUMO replay" : workspace === "archive" ? bundle?.asset.coordinate_precision === "unlocated" ? "This clip has no verified map position." : "Map position follows the source metadata." : `${filteredCameras.length} catalog locations · select a marker for source details`}</p></div>
              {workspace === "context" && <button className="text-button" onClick={() => { setSourceTab("sources"); setMobileView("sources"); }}>Browse cameras <ArrowRight size={15} /></button>}
            </div>
            <div className="activity-strip">
              <div>
                <Activity size={14} />
                <span>LATEST ACTIVITY</span>
              </div>
              {overview?.activity[0] ? (
                <p>
                  <strong>{humanize(overview.activity[0].agent)}</strong>
                  {overview.activity[0].message}
                </p>
              ) : (
                <p>Waiting for source-backed activity.</p>
              )}
              <span className="activity-mode">
                {overview?.activity[0]
                  ? humanize(overview.activity[0].execution_mode)
                  : "No execution"}
              </span>
            </div>
          </div>
          <aside className="inspector-panel" aria-label="Evidence and analysis">
            <div className="report-heading"><div><span className="eyebrow">ANALYSIS DESK</span><h2 ref={inspectorHeading} tabIndex={-1}>{panel === "evidence" ? "Inspect the evidence" : panel === "forecast" ? "Understand the outlook" : panel === "scenario" ? "Compare the options" : "Prepare a recommendation"}</h2></div><span className="desk-index">{panel === "evidence" ? "01" : panel === "forecast" ? "02" : panel === "scenario" ? "03" : "04"}</span></div>
            <div className="inspector-tabs" aria-label="Analysis steps">
              {(["evidence", "forecast", "scenario", "brief"] as const).map(
                (item) => (
                  <button
                    key={item}
                    className={panel === item ? "active" : ""}
                    aria-pressed={panel === item}
                    onClick={() => {
                      setPanel(item);
                      if (item === "scenario") setWorkspace("scenario");
                      if (item === "forecast") setWorkspace("context");
                    }}
                  >
                    {item === "brief" ? (
                      <>
                        <FileText size={12} /> Brief
                      </>
                    ) : (
                      item === "evidence" ? "Evidence" : item === "forecast" ? "Forecast" : "Scenario"
                    )}
                  </button>
                ),
              )}
            </div>
            <div className="inspector-scroll" ref={inspectorScroll}>
              {panel === "evidence" && (
                <EvidencePanel
                  bundle={bundle}
                  camera={selectedCamera}
                  incident={selectedIncident}
                  loading={!selectedCamera && evidenceLoading}
                  error={evidenceError}
                  seek={seek}
                  analyzing={
                    analysisStarting ||
                    !!(
                      analysisJob &&
                      ["queued", "running"].includes(analysisJob.state)
                    )
                  }
                  onSearch={(query) => void doSearch(query)}
                  onAnalyze={() => void analyze()}
                  onBrief={() => void generateBrief()}
                  onAcknowledge={() => void acknowledge()}
                />
              )}
              {panel === "forecast" && (
                <ForecastPanel
                  roads={overview?.roads || []}
                  roadId={roadId}
                  onRoad={setRoadId}
                  risk={
                    overview?.risk.find((cell) => cell.road_id === roadId) ||
                    null
                  }
                  forecast={forecast?.road_id === roadId ? forecast : null}
                  loading={forecastLoading}
                  error={forecastError}
                  onRun={(mode) => void runForecast(mode)}
                />
              )}
              {panel === "scenario" && (
                <ScenarioPanel
                  starting={simulationStarting}
                  job={job}
                  result={simulation}
                  playback={playback}
                  frame={frame}
                  onFrame={setFrame}
                  playing={playing}
                  onPlaying={(value) => {
                    if (
                      value &&
                      playback &&
                      frame >= playback.frames.length - 1
                    )
                      setFrame(0);
                    setPlaying(value);
                  }}
                  comparison={comparison}
                  onComparison={setComparison}
                  onRun={(scenario) => void runSimulation(scenario)}
                  onCancel={() => void cancelSimulation()}
                  error={simulationError}
                />
              )}
              {panel === "brief" && (
                <div className="inspector-content">
                  <div className="section-kicker">
                    <FileText size={14} />
                    RECOMMENDATION
                  </div>
                  <h2>Operator brief</h2>
                  <p className="subtitle">
                    Turn the selected evidence into a recommendation. Review the sources before acting.
                  </p>
                  <details className="report-disclosure"><summary>Customize the question</summary><label className="field">
                    Operator question
                    <textarea
                      rows={4}
                      value={question}
                      onChange={(event) => setQuestion(event.target.value)}
                    />
                  </label></details>
                  <div className="brief-context">
                    <span className="eyebrow">INCLUDED CONTEXT</span>
                    <span>
                      <FileVideo2 size={12} />
                      {bundle?.asset.name || "No selected archive asset"}
                    </span>
                    <span>
                      <ChartNoAxesCombined size={12} />
                      {forecast
                        ? `${humanize(forecast.mode)} forecast`
                        : "No forecast run"}
                    </span>
                    <span>
                      <FlaskConical size={12} />
                      {simulation
                        ? `${simulation.engine} · synthetic scenario`
                        : "No simulation result"}
                    </span>
                  </div>
                  <button
                    className="button primary full"
                    disabled={answerLoading || !question.trim()}
                    onClick={() => void generateBrief()}
                  >
                    {answerLoading
                      ? "Preparing brief…"
                      : "Generate operator brief"}
                    <FileText size={15} />
                  </button>
                  <ErrorMessage error={answerError} />
                  {answerLoading ? (
                    <Loading label="Synthesizing available evidence…" />
                  ) : answer ? (
                    <div className="answer-block">
                      <div className="badge-row">
                        <OriginBadge value={answer.execution_mode} />
                        <Badge>{answer.provider}</Badge>
                      </div>
                      <p>{answer.answer}</p>
                      <div className="caption">
                        {answer.model || "Model not supplied"}{" "}
                        {answer.latency_ms == null
                          ? ""
                          : `· ${answer.latency_ms} ms`}
                      </div>
                      <div className="evidence-references">
                        <span className="eyebrow">SUPPORTING EVIDENCE</span>
                        {answer.evidence_ids.length ? (
                          answer.evidence_ids.map((id) => (
                            <button
                              className="micro-button"
                              key={id}
                              onClick={() => {
                                const span = bundle?.evidence.find(
                                  (item) => item.id === id,
                                );
                                if (span) {
                                  setCameraId(null);
                                  setSeek({
                                    seconds: span.start_sec,
                                    key: Date.now(),
                                  });
                                  setPanel("evidence");
                                } else
                                  setNotice(
                                    `Evidence ${id} is referenced by the returned brief, but is not in the currently loaded asset.`,
                                  );
                              }}
                            >
                              {id}
                              <ChevronRight size={11} />
                            </button>
                          ))
                        ) : (
                          <p className="caption">
                            No evidence references returned.
                          </p>
                        )}
                      </div>
                      {answer.notes.map((note, index) => (
                        <p key={index} className="caption">
                          {note}
                        </p>
                      ))}
                    </div>
                  ) : (
                    <Empty title="Evidence before action">
                      The agent explains available evidence and scenario
                      tradeoffs. Recommendations are reviewed by a person.
                    </Empty>
                  )}
                </div>
              )}
            </div>
          </aside>
        </main>
        <footer className="status-footer">
          <span>
            <span
              className={`status-square ${apiConnected ? "connected" : ""}`}
            />
            {apiConnected ? "PharOS API connected" : "API unavailable"}
          </span>
          <span>Evidence stays linked to its source</span>
          <button onClick={() => setProviderOpen(true)}>
            {readyProviders} / {overview?.integrations.length || 0} providers
            verified <ChevronRight size={11} />
          </button>
        </footer>
      </div>
      {notice && (
        <div className="toast" role="status">
          <ShieldCheck size={17} />
          <p>{notice}</p>
          <button
            className="icon-button"
            aria-label="Dismiss notification"
            onClick={() => setNotice(null)}
          >
            <X size={16} />
          </button>
        </div>
      )}
      <dialog
        ref={providerDialog}
        className="provider-dialog"
        aria-labelledby="connections-title"
        onCancel={() => setProviderOpen(false)}
        onClick={(event) => {
          if (event.target === event.currentTarget) setProviderOpen(false);
        }}
      >
        <div className="dialog-inner">
          <div className="dialog-heading">
            <div>
              <div className="section-kicker">
                <Radio size={14} />
                CONNECTION CENTER
              </div>
              <h2 id="connections-title">Connections & preferences</h2>
            </div>
            <button
              className="icon-button"
              aria-label="Close connection center"
              onClick={() => setProviderOpen(false)}
            >
              <X size={19} />
            </button>
          </div>
          <p className="subtitle">
            Availability in this workspace. Run a check to refresh connection status.
          </p>
          <div className="provider-list">
            {overview?.integrations.map((provider) => (
              <div className="provider-card" key={provider.id}>
                <div className="provider-icon">
                  <Radio size={17} />
                </div>
                <div>
                  <div className="split">
                    <strong>{provider.name}</strong>
                    <Badge
                      tone={
                        provider.status === "ready"
                          ? "lime"
                          : provider.status === "error"
                            ? "orange"
                            : "amber"
                      }
                    >
                      {provider.status}
                    </Badge>
                  </div>
                  <p>{provider.detail}</p>
                  <span className="caption">
                    {provider.model || "No verified model"} ·{" "}
                    {provider.checked_at
                      ? timestamp(provider.checked_at)
                      : "Not checked"}
                    {provider.latency_ms == null
                      ? ""
                      : ` · ${provider.latency_ms} ms`}
                  </span>
                </div>
              </div>
            ))}
          </div>
          {overview?.notes.map((note, index) => (
            <p key={index} className="caption">
              {note}
            </p>
          ))}
          <ErrorMessage error={checkError} />
          <button
            className="button primary full"
            disabled={checking}
            onClick={() => void checkProviders()}
          >
            <RefreshCw size={14} className={checking ? "spin" : ""} />
            {checking
              ? "Checking configured providers…"
              : "Run connection diagnostics"}
          </button>
          <div className="dialog-options">
            <label>
              <input
                type="checkbox"
                checked={reducedMotion}
                onChange={(event) => setReducedMotion(event.target.checked)}
              />
              Reduce interface motion
            </label>
            <button
              className="text-button"
              onClick={() => {
                void seedDemo();
                setProviderOpen(false);
              }}
            >
              <ArrowDownToLine size={14} />
              Load deterministic demo
            </button>
          </div>
          <p className="caption">
            Map data: OpenStreetMap / OpenMapTiles, served by{" "}
            <a href="https://openfreemap.org" target="_blank" rel="noreferrer">
              OpenFreeMap
            </a>
            . No map API key required.
          </p>
        </div>
      </dialog>
    </div>
  );
}

function AssetCard({
  asset,
  selected,
  onClick,
}: {
  asset: MediaAsset;
  selected: boolean;
  onClick: () => void;
}) {
  return (
    <button
      className={`asset-card ${selected ? "selected" : ""}`}
      aria-pressed={selected}
      onClick={onClick}
    >
      <div className="asset-icon">
        <FileVideo2 size={22} />
        <span className="mono">{timecode(asset.duration_sec)}</span>
      </div>
      <div>
        <strong>{asset.provenance.data_origin === "synthetic" ? "Lane obstruction · sample clip" : asset.name}</strong>
        <span>{asset.coordinate_precision === "unlocated" ? "No verified map location" : asset.location || "Unlocated footage"}</span>
        <OriginBadge value={asset.provenance.data_origin} />
      </div>
      <ChevronRight size={13} />
    </button>
  );
}
function SearchCard({ hit, onClick }: { hit: SearchHit; onClick: () => void }) {
  return (
    <button className="search-card" onClick={onClick}>
      <div className="split">
        <span className="mono">
          {timecode(hit.start_sec)}—{timecode(hit.end_sec)}
        </span>
        <span className="caption">score {hit.score.toFixed(3)}</span>
      </div>
      <p>{hit.summary}</p>
      <div className="split">
        <span>
          <MapPin size={11} />
          {hit.location || "Unlocated footage"}
        </span>
        <ChevronRight size={13} />
      </div>
      <OriginBadge value={hit.provenance.data_origin} />
    </button>
  );
}

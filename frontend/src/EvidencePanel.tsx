import { useEffect, useRef, useState } from "react";
import {
  Box,
  Camera as CameraIcon,
  ChevronRight,
  ExternalLink,
  Eye,
  FileVideo2,
  Pause,
  Play,
  ScanLine,
  Sparkles,
} from "lucide-react";
import type { Camera, EvidenceBundle, Incident } from "./types";
import { apiBase, humanize, mediaUrl, pct, timecode, timestamp } from "./api";
import { boxesAtTime, normalizedBox } from "./evidence";
import {
  Badge,
  Empty,
  ErrorMessage,
  Loading,
  OriginBadge,
  SafeLink,
} from "./ui";

export default function EvidencePanel({
  bundle,
  camera,
  incident,
  loading,
  error,
  seek,
  analyzing,
  onSearch,
  onAnalyze,
  onBrief,
  onAcknowledge,
}: {
  bundle: EvidenceBundle | null;
  camera: Camera | null;
  incident: Incident | null;
  loading: boolean;
  error: string | null;
  seek: { seconds: number; key: number };
  analyzing: boolean;
  onSearch: (query: string) => void;
  onAnalyze: () => void;
  onBrief: () => void;
  onAcknowledge: () => void;
}) {
  const video = useRef<HTMLVideoElement>(null);
  const [time, setTime] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [showBoxes, setShowBoxes] = useState(true);
  const [dimensions, setDimensions] = useState([0, 0]);
  const [mediaError, setMediaError] = useState(false);
  const [snapshotVersion, setSnapshotVersion] = useState(0);
  const [snapshotLoading, setSnapshotLoading] = useState(false);
  const duration = Math.max(
    bundle?.asset.duration_sec || 0,
    ...(bundle?.evidence || []).map((span) => span.end_sec),
    1,
  );
  const source = mediaUrl(bundle?.asset.playback_url);
  const seekTo = (seconds: number) => {
    setTime(seconds);
    if (video.current) video.current.currentTime = seconds;
  };
  useEffect(() => {
    setTime(0);
    setPlaying(false);
    setMediaError(false);
    setDimensions([0, 0]);
  }, [bundle?.asset.id, camera?.id]);
  useEffect(() => {
    seekTo(seek.seconds);
  }, [seek.key, bundle?.asset.id]);
  const detections = boxesAtTime(bundle?.detections || [], time);
  if (loading) return <Loading />;
  if (error && !camera) return <ErrorMessage error={error} />;
  if (camera)
    return (
      <div className="inspector-content">
        <div className="section-kicker">
          <CameraIcon size={14} />
          PUBLIC CAMERA
        </div>
        <h2>{camera.name}</h2>
        <p className="subtitle">
          {[camera.borough, camera.corridor].filter(Boolean).join(" · ") ||
            "Source location metadata"}
        </p>
        <div className="badge-row">
          <OriginBadge value={camera.provenance.data_origin} />
          <Badge tone={camera.provenance.freshness === "stale" ? "amber" : ""}>
            {camera.provenance.freshness}
          </Badge>
          <Badge>{humanize(camera.capability)}</Badge>
        </div>
        <div className="snapshot-frame">
          {camera.snapshot_url && !mediaError ? (
            <>
              <img
                key={`${camera.id}-${snapshotVersion}`}
                src={`${mediaUrl(camera.snapshot_url) || `${apiBase()}/cameras/${encodeURIComponent(camera.id)}/snapshot`}${snapshotVersion ? `?refresh=${snapshotVersion}` : ""}`}
                alt={`Public snapshot from ${camera.name}`}
                onLoad={() => setSnapshotLoading(false)}
                onError={() => {
                  setMediaError(true);
                  setSnapshotLoading(false);
                }}
              />
              {snapshotLoading && <Loading label="Requesting snapshot…" />}
            </>
          ) : (
            <Empty
              title={
                mediaError
                  ? "Snapshot currently unavailable"
                  : "No snapshot available"
              }
            >
              The catalog location remains available. An unavailable image is
              never replaced with unrelated footage.
            </Empty>
          )}
        </div>
        <p className="caption">
          {timestamp(camera.provenance.captured_at)} · Single image, not a
          continuous stream.
        </p>
        <button
          className="button secondary full"
          disabled={snapshotLoading || !camera.snapshot_url}
          onClick={() => {
            if (!camera.snapshot_url) return;
            setMediaError(false);
            setSnapshotLoading(true);
            setSnapshotVersion(Date.now());
          }}
        >
          {camera.snapshot_url
            ? "Refresh public snapshot"
            : "Snapshot access unavailable"}
        </button>
        <div className="detail-block">
          <h3>Source details</h3>
          <dl>
            <dt>Availability</dt>
            <dd>{humanize(camera.status)}</dd>
            <dt>Coordinates</dt>
            <dd>
              {camera.lat != null && camera.lon != null
                ? `${camera.lat.toFixed(5)}, ${camera.lon.toFixed(5)}`
                : "Unlocated"}
            </dd>
            <dt>Precision</dt>
            <dd>{camera.coordinate_precision}</dd>
            <dt>Coordinate source</dt>
            <dd>{camera.coordinate_source || "Not provided"}</dd>
          </dl>
          <SafeLink href={camera.source_url}>
            Open public source <ExternalLink size={11} />
          </SafeLink>
        </div>
        <div className="notice">
          NYC snapshots provide context. They are separate from the licensed
          archive and are not ingested into the shared pipeline.
        </div>
        {camera.provenance.notes?.map((note, index) => (
          <p className="caption" key={index}>
            {note}
          </p>
        ))}
      </div>
    );
  if (!bundle)
    return (
      <Empty title="Choose a source to investigate">
        Select an archive clip or a public camera. Evidence, source timestamps,
        and analysis will appear here.
      </Empty>
    );
  return (
    <div className="inspector-content">
      <div className="section-kicker">
        <FileVideo2 size={14} />
        EVIDENCE INSPECTOR <span className="mono">{bundle.asset.id}</span>
      </div>
      <h2>{incident?.title || bundle.asset.name}</h2>
      <p className="subtitle">
        {bundle.asset.location || "Location not established"} ·{" "}
        {bundle.asset.coordinate_precision === "unlocated"
          ? "No verified map position"
          : `${bundle.asset.coordinate_precision} coordinates`}
      </p>
      <div className="badge-row">
        <OriginBadge value={bundle.provenance.data_origin} />
        <OriginBadge value={bundle.provenance.execution_mode} />
        <Badge>{bundle.provenance.freshness}</Badge>
      </div>
      <div
        className="media-frame"
        style={{
          aspectRatio: dimensions[0]
            ? `${dimensions[0]}/${dimensions[1]}`
            : "16/9",
        }}
      >
        {source && !mediaError ? (
          <video
            ref={video}
            src={source}
            preload="metadata"
            playsInline
            aria-label={bundle.asset.name}
            onError={() => setMediaError(true)}
            onTimeUpdate={(event) => setTime(event.currentTarget.currentTime)}
            onPlay={() => setPlaying(true)}
            onPause={() => setPlaying(false)}
            onEnded={() => setPlaying(false)}
            onLoadedMetadata={(event) => {
              setDimensions([
                event.currentTarget.videoWidth,
                event.currentTarget.videoHeight,
              ]);
              event.currentTarget.currentTime = seek.seconds;
            }}
          />
        ) : (
          <Empty
            title={mediaError ? "Playback unavailable" : "Media not available"}
          >
            Evidence metadata remains inspectable. No source video is
            substituted.
          </Empty>
        )}
        {source && !mediaError && showBoxes && dimensions[0] > 0 && (
          <div className="detection-layer" aria-hidden="true">
            {detections.map((detection) => {
              const box = normalizedBox(
                detection,
                dimensions[0],
                dimensions[1],
              );
              return box ? (
                <div
                  className="detection-box"
                  key={detection.id}
                  style={{
                    left: `${box[0] * 100}%`,
                    top: `${box[1] * 100}%`,
                    width: `${(box[2] - box[0]) * 100}%`,
                    height: `${(box[3] - box[1]) * 100}%`,
                  }}
                >
                  <span>
                    {detection.class_name} {pct(detection.confidence)}
                  </span>
                </div>
              ) : null;
            })}
          </div>
        )}
        {bundle.provenance.data_origin === "synthetic" && (
          <div className="media-label">SYNTHETIC DEMO</div>
        )}
      </div>
      <div className="media-controls">
        <button
          className="icon-button"
          disabled={!source || mediaError}
          aria-label={playing ? "Pause evidence" : "Play evidence"}
          onClick={() => {
            if (video.current) {
              if (playing) video.current.pause();
              else video.current.play().catch(() => setMediaError(true));
            }
          }}
        >
          {playing ? <Pause size={16} /> : <Play size={16} />}
        </button>
        <input
          aria-label="Evidence time"
          type="range"
          min="0"
          max={duration}
          step="0.1"
          value={Math.min(time, duration)}
          onChange={(event) => seekTo(Number(event.target.value))}
        />
        <span className="mono">
          {timecode(time)} / {timecode(duration)}
        </span>
        <button
          className={`icon-button ${showBoxes ? "selected" : ""}`}
          aria-pressed={showBoxes}
          aria-label="Toggle detection boxes"
          onClick={() => setShowBoxes(!showBoxes)}
        >
          <ScanLine size={17} />
        </button>
      </div>
      <p className="caption">
        {timestamp(bundle.provenance.captured_at)} · {detections.length}{" "}
        detection{detections.length === 1 ? "" : "s"} at this frame
      </p>
      {incident && (
        <div className="incident-context">
          <div className="split">
            <Badge tone={incident.severity === "high" ? "orange" : "amber"}>
              {incident.severity} priority
            </Badge>
            <span className="caption">
              {pct(incident.confidence)} confidence
            </span>
          </div>
          <p>{incident.description}</p>
          <button
            className="text-button"
            disabled={incident.status === "acknowledged"}
            onClick={onAcknowledge}
          >
            {incident.status === "acknowledged"
              ? "Acknowledged"
              : "Acknowledge incident"}{" "}
            <ChevronRight size={13} />
          </button>
        </div>
      )}
      <div className="detail-block">
        <div className="split">
          <h3>
            <Eye size={15} /> Evidence spans
          </h3>
          <span className="count">{bundle.evidence.length}</span>
        </div>
        <div className="evidence-spans">
          {bundle.evidence.length ? (
            bundle.evidence.map((span) => (
              <button
                key={span.id}
                className={
                  time >= span.start_sec && time <= span.end_sec ? "active" : ""
                }
                onClick={() => seekTo(span.start_sec)}
              >
                <span className="mono">
                  {timecode(span.start_sec)}—{timecode(span.end_sec)}
                </span>
                <p>{span.summary}</p>
                <ChevronRight size={14} />
              </button>
            ))
          ) : (
            <p className="caption">
              No evidence spans returned for this asset.
            </p>
          )}
        </div>
      </div>
      <div className="detail-block">
        <div className="split">
          <h3>
            <Box size={15} /> Perception
          </h3>
          <button
            className="text-button"
            disabled={analyzing}
            onClick={onAnalyze}
          >
            {analyzing ? "Reviewing…" : "Review stored evidence"}
          </button>
        </div>
        <div className="perception-stats">
          <div>
            <strong>{bundle.detections.length}</strong>
            <span>stored detections</span>
          </div>
          <div>
            <strong>{bundle.tracks.length}</strong>
            <span>
              {bundle.tracks.length ? "temporal tracks" : "tracks available"}
            </span>
          </div>
        </div>
        <p className="caption">
          {bundle.detections.length
            ? [
                ...new Set(
                  bundle.detections.map((detection) => detection.model),
                ),
              ].join(" · ")
            : "No detector results returned."}{" "}
          {bundle.tracks.length
            ? [
                ...new Set(
                  bundle.tracks.map(
                    (track) => `${track.source} / ${track.method}`,
                  ),
                ),
              ].join("; ")
            : "Individual detections do not establish tracking."}
        </p>
        {bundle.detections.length > 0 && (
          <div className="detection-moments">
            {[
              ...new Set(
                bundle.detections.map((detection) => detection.timestamp_sec),
              ),
            ]
              .slice(0, 16)
              .map((seconds) => (
                <button
                  key={seconds}
                  className="micro-button"
                  onClick={() => seekTo(seconds)}
                >
                  {timecode(seconds)}
                </button>
              ))}
          </div>
        )}
      </div>
      <div className="detail-block">
        <h3>
          <Sparkles size={15} /> Cosmos reasoning
        </h3>
        {bundle.reasoning ? (
          <p className="reasoning">{bundle.reasoning}</p>
        ) : (
          <p className="caption">
            Stored reasoning is unavailable. No model inference is implied.
          </p>
        )}
        <div className="badge-row">
          <OriginBadge value={bundle.provenance.execution_mode} />
        </div>
      </div>
      <div className="action-stack">
        <button
          className="button secondary"
          onClick={() => onSearch("stopped vehicles obstructing a lane")}
        >
          Find related footage <ChevronRight size={16} />
        </button>
        <button className="button primary" onClick={onBrief}>
          Generate operator brief <Sparkles size={15} />
        </button>
      </div>
      <details className="provenance">
        <summary>Provenance & source</summary>
        <dl>
          <dt>Asset</dt>
          <dd>{bundle.asset.id}</dd>
          <dt>Original video</dt>
          <dd>{bundle.asset.original_video || "Not supplied"}</dd>
          <dt>Source URI</dt>
          <dd>{bundle.asset.source_uri || "Not supplied"}</dd>
          <dt>Processed</dt>
          <dd>{timestamp(bundle.provenance.processed_at)}</dd>
        </dl>
        {bundle.provenance.notes?.map((note, index) => (
          <p key={index}>{note}</p>
        ))}
        <SafeLink href={bundle.provenance.source_url}>
          Source reference <ExternalLink size={11} />
        </SafeLink>
      </details>
    </div>
  );
}

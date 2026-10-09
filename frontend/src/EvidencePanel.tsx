import { useEffect, useRef, useState } from "react";
import {
  ArrowRight,
  Camera as CameraIcon,
  Check,
  ChevronRight,
  ExternalLink,
  FileVideo2,
  Pause,
  Play,
  ScanLine,
} from "lucide-react";
import type { Camera, EvidenceBundle, Incident } from "./types";
import { apiBase, humanize, mediaUrl, pct, timecode, timestamp } from "./api";
import { boxesAtTime, normalizedBox } from "./evidence";
import { Empty, ErrorMessage, Loading, SafeLink } from "./ui";

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
    const next = Math.min(duration, Math.max(0, seconds));
    setTime(next);
    if (video.current) video.current.currentTime = next;
  };
  useEffect(() => {
    setTime(0);
    setPlaying(false);
    setMediaError(false);
    setDimensions([0, 0]);
    setSnapshotLoading(false);
  }, [bundle?.asset.id, camera?.id]);
  useEffect(() => {
    seekTo(seek.seconds);
  }, [seek.key, bundle?.asset.id]);

  const detections = boxesAtTime(bundle?.detections || [], time);
  const reasoningModels = [
    ...new Set([
      ...(bundle?.reasoning_models || []),
      ...(bundle?.evidence.flatMap((span) =>
        span.reasoning_model ? [span.reasoning_model] : [],
      ) || []),
    ]),
  ];
  const selectedMoment = [...(bundle?.evidence || [])]
    .sort((a, b) => b.start_sec - a.start_sec)
    .find(
      (span) =>
        time >= span.start_sec &&
        (time < span.end_sec ||
          (time === duration && span.end_sec === duration)),
    );

  if (loading) return <Loading />;
  if (error && !camera) return <ErrorMessage error={error} />;
  if (camera) {
    const snapshotSource =
      mediaUrl(camera.snapshot_url) ||
      `${apiBase()}/cameras/${encodeURIComponent(camera.id)}/snapshot`;
    return (
      <article className="inspector-content evidence-report camera-report">
        <header className="report-heading">
          <div className="report-kicker">
            <CameraIcon size={15} /> Public camera
          </div>
          <h2>{camera.name}</h2>
          <p className="report-location">
            {[camera.borough, camera.corridor].filter(Boolean).join(" · ") ||
              "Location described by the public catalog"}
          </p>
          <p className="report-source-note">
            A single public snapshot. This camera is separate from the footage
            archive.
          </p>
        </header>

        <figure className="evidence-player snapshot-player">
          <div className="snapshot-frame">
            {camera.snapshot_url && !mediaError ? (
              <>
                <img
                  key={`${camera.id}-${snapshotVersion}`}
                  src={`${snapshotSource}${snapshotVersion ? `${snapshotSource.includes("?") ? "&" : "?"}refresh=${snapshotVersion}` : ""}`}
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
                This camera has a catalog location, but an image is not
                currently accessible.
              </Empty>
            )}
          </div>
          <figcaption className="report-media-caption">
            <span>{timestamp(camera.provenance.captured_at)}</span>
            {camera.provenance.freshness === "stale" && (
              <strong>Capture may be outdated</strong>
            )}
          </figcaption>
        </figure>

        <div className="camera-source-actions">
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
            {snapshotLoading
              ? "Refreshing snapshot…"
              : camera.snapshot_url
                ? "Refresh public snapshot"
                : "Snapshot access unavailable"}
          </button>
          <SafeLink href={camera.source_url} className="report-source-link">
            Open public source <ExternalLink size={13} />
          </SafeLink>
        </div>

        <details className="provenance report-disclosure">
          <summary>Source details</summary>
          <dl className="report-facts">
            <dt>Availability</dt>
            <dd>{humanize(camera.status)}</dd>
            <dt>Source type</dt>
            <dd>{humanize(camera.capability)}</dd>
            <dt>Capture freshness</dt>
            <dd>
              {camera.provenance.freshness === "unknown"
                ? "Not verified"
                : humanize(camera.provenance.freshness)}
            </dd>
            <dt>Coordinates</dt>
            <dd>
              {camera.lat != null && camera.lon != null
                ? `${camera.lat.toFixed(5)}, ${camera.lon.toFixed(5)}`
                : "No verified map position"}
            </dd>
            <dt>Position precision</dt>
            <dd>{humanize(camera.coordinate_precision)}</dd>
            <dt>Position source</dt>
            <dd>{camera.coordinate_source || "Not supplied"}</dd>
          </dl>
          {camera.provenance.notes?.map((note, index) => (
            <p className="report-note" key={index}>
              {note}
            </p>
          ))}
          <p className="report-note">
            Public snapshots provide context and are not ingested into the
            shared archive pipeline.
          </p>
        </details>
      </article>
    );
  }
  if (!bundle) {
    return (
      <Empty title="Choose footage to review">
        Select a clip or a public camera to see its evidence and source
        information.
      </Empty>
    );
  }

  const isDemo = bundle.provenance.data_origin === "synthetic";
  const isArchive = bundle.provenance.data_origin === "archive";
  const isFixtureOutput = isDemo && bundle.provenance.execution_mode === "mock";
  const isUnlocated =
    bundle.asset.coordinate_precision === "unlocated" ||
    bundle.asset.lat == null ||
    bundle.asset.lon == null;
  const detectorModels = [
    ...new Set(bundle.detections.map((detection) => detection.model)),
  ];
  const frameTimes = [
    ...new Set(bundle.detections.map((detection) => detection.timestamp_sec)),
  ].sort((a, b) => a - b);
  // A small set of frame shortcuts remains usable for both sparse annotations and 30fps sidecars.
  const sampleTimes =
    frameTimes.length <= 8
      ? frameTimes
      : Array.from(
          { length: 8 },
          (_, index) =>
            frameTimes[Math.round((index * (frameTimes.length - 1)) / 7)],
        );

  return (
    <article className="inspector-content evidence-report">
      <header className="report-heading">
        <div className="report-kicker">
          <FileVideo2 size={15} />{" "}
          {isDemo
            ? "Demonstration footage"
            : isArchive
              ? "Archive footage"
              : "Evidence report"}
        </div>
        <h2>{incident?.title || (isDemo ? "Sample lane obstruction" : bundle.asset.name)}</h2>
        <p className="report-location">
          {isDemo && isUnlocated
            ? "Generated scene · no map location"
            : bundle.asset.location || "Location not established"}
        </p>
        {!isDemo && isUnlocated && (
          <p className="report-position-note">
            Exact location unverified. No map pin is assigned.
          </p>
        )}
        <p className={`report-source-note ${isDemo ? "is-demo" : ""}`}>
          {isDemo
            ? "An illustrated example for review, not a recording of a real incident."
            : isArchive
              ? "Recorded footage, not a current camera view."
              : humanize(bundle.asset.capability)}
        </p>
      </header>

      <figure className="evidence-player">
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
                event.currentTarget.currentTime = Math.min(
                  duration,
                  Math.max(0, seek.seconds),
                );
              }}
            />
          ) : (
            <Empty
              title={
                mediaError ? "Playback unavailable" : "Media not available"
              }
            >
              You can still read the recorded evidence and review its source
              below.
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
          {isDemo && <div className="media-label">DEMO FOOTAGE</div>}
        </div>

        <div className="media-controls evidence-transport">
          <button
            className="icon-button evidence-play"
            disabled={!source || mediaError}
            aria-label={playing ? "Pause evidence" : "Play evidence"}
            onClick={() => {
              if (!video.current) return;
              if (playing) video.current.pause();
              else video.current.play().catch(() => setMediaError(true));
            }}
          >
            {playing ? <Pause size={18} /> : <Play size={18} />}
          </button>
          <div className="evidence-scrubber">
            <div className="evidence-coverage" aria-hidden="true">
              {bundle.evidence.map((span) => (
                <span
                  key={span.id}
                  className={selectedMoment?.id === span.id ? "active" : ""}
                  style={{
                    left: `${(Math.max(0, span.start_sec) / duration) * 100}%`,
                    width: `${(Math.max(0, Math.min(duration, span.end_sec) - Math.max(0, span.start_sec)) / duration) * 100}%`,
                  }}
                />
              ))}
            </div>
            <input
              aria-label="Evidence time"
              aria-valuetext={`${timecode(time)} of ${timecode(duration)}`}
              type="range"
              min="0"
              max={duration}
              step="0.1"
              value={Math.min(time, duration)}
              onChange={(event) => seekTo(Number(event.target.value))}
            />
          </div>
          <output className="mono evidence-clock">
            {timecode(time)} <span>/ {timecode(duration)}</span>
          </output>
          <button
            className={`icon-button evidence-overlay-toggle ${showBoxes ? "selected" : ""}`}
            aria-pressed={showBoxes}
            aria-label="Toggle detection boxes"
            title={showBoxes ? "Hide frame boxes" : "Show frame boxes"}
            onClick={() => setShowBoxes(!showBoxes)}
          >
            <ScanLine size={18} />
          </button>
        </div>
        <figcaption className="report-media-caption">
          <span>
            {bundle.provenance.captured_at
              ? `${isDemo ? "Demo dated" : "Recorded"} ${timestamp(bundle.provenance.captured_at)}`
              : "Capture time not supplied"}
          </span>
          <span>
            {detections.length}{" "}
            {isDemo
              ? detections.length === 1
                ? "annotation"
                : "annotations"
              : detections.length === 1
                ? "box"
                : "boxes"}{" "}
            on this frame
          </span>
        </figcaption>
      </figure>

      <section
        className="report-section evidence-moments"
        aria-labelledby="evidence-moments-heading"
      >
        <div className="report-section-heading">
          <h3 id="evidence-moments-heading">Moments to review</h3>
          <span>
            {bundle.evidence.length}{" "}
            {bundle.evidence.length === 1 ? "moment" : "moments"}
          </span>
        </div>
        <div className="evidence-spans">
          {bundle.evidence.length ? (
            bundle.evidence.map((span, index) => (
              <button
                key={span.id}
                className={`evidence-moment ${selectedMoment?.id === span.id ? "active" : ""}`}
                aria-pressed={selectedMoment?.id === span.id}
                onClick={() => seekTo(span.start_sec)}
              >
                <span className="moment-index">
                  {String(index + 1).padStart(2, "0")}
                </span>
                <span className="moment-content">
                  <span className="moment-time mono">
                    {timecode(span.start_sec)}—{timecode(span.end_sec)}
                  </span>
                  <span className="moment-summary">{span.summary}</span>
                  <span className="moment-action">
                    {selectedMoment?.id === span.id
                      ? "Selected moment"
                      : "Jump to moment"}
                  </span>
                </span>
                <ChevronRight size={16} />
              </button>
            ))
          ) : (
            <p className="report-note">
              No timed moments have been returned for this clip.
            </p>
          )}
        </div>
      </section>

      {incident && (
        <section className="report-section incident-review">
          <div className="report-section-heading">
            <h3>Review note</h3>
            <span className={`report-priority ${incident.severity}`}>
              {humanize(incident.severity)} priority
            </span>
          </div>
          <p className="report-body">{incident.description}</p>
          <button
            className="text-button incident-acknowledge"
            disabled={incident.status === "acknowledged"}
            onClick={onAcknowledge}
          >
            {incident.status === "acknowledged" ? (
              <>
                <Check size={15} /> Acknowledged
              </>
            ) : (
              <>
                Acknowledge incident <ChevronRight size={15} />
              </>
            )}
          </button>
        </section>
      )}

      <section className="report-section evidence-findings">
        <div className="report-section-heading">
          <h3>{isDemo ? "Illustration notes" : "Recorded interpretation"}</h3>
        </div>
        {bundle.reasoning ? (
          <p className="reasoning report-body">{bundle.reasoning}</p>
        ) : (
          <p className="report-note">
            No stored interpretation is available for this clip.
          </p>
        )}
      </section>

      <div className="action-stack report-actions">
        <button className="button primary" onClick={onBrief}>
          Generate operator brief <ArrowRight size={16} />
        </button>
        <button
          className="button secondary"
          onClick={() => onSearch("stopped vehicles obstructing a lane")}
        >
          Find related footage <ChevronRight size={16} />
        </button>
      </div>

      <details className="provenance report-disclosure analysis-disclosure">
        <summary>
          Detection & analysis details{" "}
          <span>
            {bundle.detections.length} {isDemo ? "annotations" : "boxes"} ·{" "}
            {bundle.tracks.length} tracks
          </span>
        </summary>
        <p className="report-note">
          {isFixtureOutput
            ? "The illustration uses fixture annotations. No detector or reasoning model is claimed to have analyzed it."
            : "Boxes mark objects in a recorded frame. They are distinct from temporal tracks and do not establish physical speed."}
        </p>
        <dl className="report-facts">
          <dt>Frame detections</dt>
          <dd>
            {bundle.detections.length} across {frameTimes.length}{" "}
            {frameTimes.length === 1 ? "timestamp" : "timestamps"}
          </dd>
          <dt>{isFixtureOutput ? "Annotation source" : "Detector model"}</dt>
          <dd>{detectorModels.join(" · ") || "Not supplied"}</dd>
          <dt>Temporal tracks</dt>
          <dd>
            {bundle.tracks.length
              ? `${bundle.tracks.length} returned`
              : "Not available"}
          </dd>
          {bundle.tracks.length > 0 && (
            <>
              <dt>Tracking method</dt>
              <dd>
                {[
                  ...new Set(
                    bundle.tracks.map(
                      (track) => `${humanize(track.source)} / ${track.method}`,
                    ),
                  ),
                ].join("; ")}
              </dd>
              <dt>Calibration</dt>
              <dd>
                {bundle.tracks.every((track) => track.calibrated)
                  ? "Reported calibrated by the source"
                  : "No physical calibration established"}
              </dd>
            </>
          )}
          <dt>Cosmos reasoning model</dt>
          <dd>
            {reasoningModels.join(" · ") ||
              (isFixtureOutput
                ? "Not run for this demonstration"
                : "Not supplied")}
          </dd>
          <dt>Execution</dt>
          <dd>
            {bundle.provenance.execution_mode === "mock"
              ? "Demo output"
              : bundle.provenance.execution_mode === "real_provider"
                ? "Retrieved through the configured provider"
                : "Unavailable"}
          </dd>
          {incident?.confidence != null && (
            <>
              <dt>Reported confidence</dt>
              <dd>
                {pct(incident.confidence)} · not a calibrated risk probability
              </dd>
            </>
          )}
        </dl>
        {sampleTimes.length > 0 && (
          <div className="frame-shortcuts">
            <p className="report-note">Inspect a recorded frame</p>
            <div className="detection-moments">
              {sampleTimes.map((seconds) => (
                <button
                  key={seconds}
                  className="micro-button"
                  aria-label={`Inspect detection frame at ${seconds.toFixed(2)} seconds`}
                  onClick={() => seekTo(seconds)}
                >
                  {timecode(seconds)}
                  <span>
                    .
                    {Math.floor((seconds % 1) * 100)
                      .toString()
                      .padStart(2, "0")}
                  </span>
                </button>
              ))}
            </div>
          </div>
        )}
        <button
          className="text-button evidence-refresh"
          disabled={analyzing}
          onClick={onAnalyze}
        >
          {analyzing ? "Reviewing…" : "Review stored evidence"}{" "}
          <ChevronRight size={14} />
        </button>
        <p className="report-note">
          Reloads stored evidence. It does not start a new shared processing
          run.
        </p>
      </details>

      <details className="provenance report-disclosure">
        <summary>Provenance & source</summary>
        <dl className="report-facts">
          <dt>Asset</dt>
          <dd>{bundle.asset.id}</dd>
          <dt>Original video</dt>
          <dd>{bundle.asset.original_video || "Not supplied"}</dd>
          <dt>Source URI</dt>
          <dd>{bundle.asset.source_uri || "Not supplied"}</dd>
          <dt>Source type</dt>
          <dd>{humanize(bundle.asset.capability)}</dd>
          <dt>Data origin</dt>
          <dd>
            {isDemo
              ? "Generated demonstration"
              : humanize(bundle.provenance.data_origin)}
          </dd>
          <dt>Position precision</dt>
          <dd>
            {isUnlocated
              ? "Unlocated"
              : humanize(bundle.asset.coordinate_precision)}
          </dd>
          <dt>Capture freshness</dt>
          <dd>
            {bundle.provenance.freshness === "unknown"
              ? "Not verified"
              : humanize(bundle.provenance.freshness)}
          </dd>
          <dt>Processed</dt>
          <dd>{timestamp(bundle.provenance.processed_at)}</dd>
        </dl>
        {bundle.provenance.notes?.map((note, index) => (
          <p className="report-note" key={index}>
            {note}
          </p>
        ))}
        <SafeLink
          href={bundle.provenance.source_url}
          className="report-source-link"
        >
          Source reference <ExternalLink size={13} />
        </SafeLink>
      </details>
    </article>
  );
}

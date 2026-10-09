import { useState } from "react";
import {
  FlaskConical,
  Play,
  Pause,
  Route,
  Square,
  ArrowRight,
} from "lucide-react";
import type { Job, Playback, SimulationRun, SimulationScenario } from "./types";
import { humanize, timecode } from "./api";
import { Badge, Empty, ErrorMessage, OriginBadge } from "./ui";

const defaults: SimulationScenario = {
  name: "Earlier clearance comparison",
  network_id: "nyc-demo-corridor",
  duration_sec: 600,
  demand_vph: 900,
  blockage_start_sec: 60,
  early_clearance_sec: 180,
  late_clearance_sec: 420,
  seeds: [42],
};
export default function ScenarioPanel({
  starting,
  job,
  result,
  playback,
  frame,
  onFrame,
  playing,
  onPlaying,
  comparison,
  onComparison,
  onRun,
  onCancel,
  error,
}: {
  starting: boolean;
  job: Job | null;
  result: SimulationRun | null;
  playback: Playback | null;
  frame: number;
  onFrame: (frame: number) => void;
  playing: boolean;
  onPlaying: (playing: boolean) => void;
  comparison: "early" | "late";
  onComparison: (value: "early" | "late") => void;
  onRun: (scenario: SimulationScenario) => void;
  onCancel: () => void;
  error: string | null;
}) {
  const [scenario, setScenario] = useState(defaults);
  const active =
    starting || (job && (job.state === "running" || job.state === "queued"));
  const valid =
    scenario.early_clearance_sec > scenario.blockage_start_sec &&
    scenario.late_clearance_sec > scenario.early_clearance_sec &&
    scenario.late_clearance_sec < scenario.duration_sec;
  const metrics = result
    ? [
        ...new Set([
          ...Object.keys(result.baseline),
          ...Object.keys(result.early),
          ...Object.keys(result.late),
        ]),
      ].filter(
        (key) =>
          typeof result.baseline[key] === "number" ||
          typeof result.early[key] === "number" ||
          typeof result.late[key] === "number",
      )
    : [];
  const set = (key: keyof SimulationScenario, value: number) =>
    setScenario({ ...scenario, [key]: value });
  return (
    <div className="inspector-content">
      <div className="section-kicker">
        <FlaskConical size={14} />
        SCENARIO LAB
      </div>
      <h2>What if we clear it sooner?</h2>
      <p className="subtitle">
        Compare baseline, earlier and later clearance under the same demand and
        seed.
      </p>
      <div className="badge-row">
        <Badge tone="amber">Synthetic demand</Badge>
        <Badge>SUMO scenario</Badge>
      </div>
      <div className="notice">
        This NYC demonstration network is separate from archive footage. Inputs
        are assumptions, not inferred measurements.
      </div>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          if (valid) onRun({ ...scenario, seeds: [...scenario.seeds] });
        }}
      >
        <label className="field">
          Scenario name
          <input
            value={scenario.name}
            required
            maxLength={80}
            onChange={(event) =>
              setScenario({ ...scenario, name: event.target.value })
            }
          />
        </label>
        <label className="field">
          Traffic demand{" "}
          <span>{scenario.demand_vph.toLocaleString()} vehicles / hour</span>
          <input
            type="range"
            min="100"
            max="2400"
            step="100"
            value={scenario.demand_vph}
            onChange={(event) => set("demand_vph", Number(event.target.value))}
          />
        </label>
        <div className="form-grid">
          <label className="field">
            Run duration
            <select
              value={scenario.duration_sec}
              onChange={(event) =>
                set("duration_sec", Number(event.target.value))
              }
            >
              <option value={600}>10 minutes</option>
              <option value={900}>15 minutes</option>
              <option value={1800}>30 minutes</option>
            </select>
          </label>
          <label className="field">
            Random seed
            <input
              type="number"
              min="0"
              max="2147483647"
              value={scenario.seeds[0]}
              onChange={(event) =>
                setScenario({
                  ...scenario,
                  seeds: [Number(event.target.value)],
                })
              }
            />
          </label>
        </div>
        <div className="scenario-schedule">
          <span>
            <i className="dot orange" />
            Blockage starts{" "}
            <strong>{timecode(scenario.blockage_start_sec)}</strong>
          </span>
          <ArrowRight size={14} />
          <span>
            <i className="dot lime" />
            Compare clearance
          </span>
        </div>
        <div className="form-grid">
          <label className="field">
            Earlier clearance (sec)
            <input
              type="number"
              min="61"
              max={scenario.duration_sec - 2}
              value={scenario.early_clearance_sec}
              onChange={(event) =>
                set("early_clearance_sec", Number(event.target.value))
              }
            />
          </label>
          <label className="field">
            Later clearance (sec)
            <input
              type="number"
              min={scenario.early_clearance_sec + 1}
              max={scenario.duration_sec - 1}
              value={scenario.late_clearance_sec}
              onChange={(event) =>
                set("late_clearance_sec", Number(event.target.value))
              }
            />
          </label>
        </div>
        {!valid && (
          <p className="field-error">
            Clearance must follow the blockage, with earlier clearance before
            later clearance and both within the run.
          </p>
        )}
        <button
          className="button primary full"
          type="submit"
          disabled={!!active || !valid}
        >
          {active ? "Simulation running…" : "Run comparison"}
          <Play size={15} />
        </button>
      </form>
      <ErrorMessage error={error} />
      {job && (
        <div className="job-card" aria-live="polite">
          <div className="split">
            <span>{humanize(job.state)}</span>
            <span className="mono">{Math.round(job.progress * 100)}%</span>
          </div>
          <progress max="1" value={job.progress} />
          <div className="split">
            <span className="caption mono">{job.id}</span>
            {active && (
              <button className="text-button" onClick={onCancel}>
                <Square size={11} /> Cancel
              </button>
            )}
          </div>
          {job.error != null && (
            <p className="field-error">
              {typeof job.error === "string"
                ? job.error
                : JSON.stringify(job.error)}
            </p>
          )}
        </div>
      )}
      {result ? (
        <>
          <div className="detail-block">
            <div className="split">
              <h3>
                <Route size={15} /> Scenario results
              </h3>
              <OriginBadge value={result.execution_mode} />
            </div>
            <p className="caption">
              {result.engine} · {result.scenario.demand_vph} veh/h · seeds{" "}
              {result.scenario.seeds.join(", ")}
            </p>
            {metrics.length ? (
              <div className="comparison-table">
                <table>
                  <thead>
                    <tr>
                      <th>Metric</th>
                      <th>Base</th>
                      <th>Early</th>
                      <th>Late</th>
                    </tr>
                  </thead>
                  <tbody>
                    {metrics.map((key) => (
                      <tr key={key}>
                        <th>{humanize(key)}</th>
                        {[result.baseline, result.early, result.late].map(
                          (values, index) => (
                            <td key={index}>
                              {typeof values[key] === "number"
                                ? Number(values[key]).toLocaleString(
                                    undefined,
                                    { maximumFractionDigits: 1 },
                                  )
                                : "—"}
                            </td>
                          ),
                        )}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="caption">
                The engine returned no numeric comparison metrics.
              </p>
            )}
            <p className="caption">
              Compare unfinished vehicles alongside travel times; unfinished
              trips are not successful completions.
            </p>
          </div>
          {playback && playback.frames.length > 0 ? (
            <div className="detail-block">
              <h3>Synchronized map replay</h3>
              <div className="segmented">
                <button
                  className={comparison === "early" ? "active" : ""}
                  onClick={() => onComparison("early")}
                >
                  Baseline + early
                </button>
                <button
                  className={comparison === "late" ? "active" : ""}
                  onClick={() => onComparison("late")}
                >
                  Baseline + late
                </button>
              </div>
              <div className="simulation-legend">
                <span>
                  <i className="dot white" />
                  Baseline
                </span>
                <span>
                  <i
                    className={`dot ${comparison === "early" ? "lime" : "orange"}`}
                  />
                  {comparison === "early" ? "Earlier" : "Later"} clearance
                </span>
              </div>
              <div className="media-controls">
                <button
                  className="icon-button"
                  aria-label={
                    playing
                      ? "Pause simulation replay"
                      : "Play simulation replay"
                  }
                  onClick={() => onPlaying(!playing)}
                >
                  {playing ? <Pause size={16} /> : <Play size={16} />}
                </button>
                <input
                  type="range"
                  aria-label="Simulation replay time"
                  min="0"
                  max={playback.frames.length - 1}
                  step="1"
                  value={frame}
                  onChange={(event) => onFrame(Number(event.target.value))}
                />
                <span className="mono">
                  {timecode(playback.frames[frame]?.time_sec || 0)}
                </span>
              </div>
              <p className="caption">
                White and colored markers use the same simulation time. All
                vehicles are simulated.
              </p>
            </div>
          ) : (
            <p className="caption">No replay frames available for this run.</p>
          )}
          <details className="provenance">
            <summary>Immutable inputs & assumptions</summary>
            <pre>{JSON.stringify(result.scenario, null, 2)}</pre>
            {result.assumptions.map((assumption, index) => (
              <p key={index}>{assumption}</p>
            ))}
          </details>
        </>
      ) : (
        <Empty title="Test a response before acting">
          Run a reproducible clearance comparison. Results appear only after the
          configured simulation engine completes.
        </Empty>
      )}
    </div>
  );
}

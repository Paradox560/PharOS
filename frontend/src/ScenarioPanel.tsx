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
import { comparisonOutcome, durationText, formatNumber, metricLabel, metricValue } from "./reportFormatting";

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
  const validTiming =
    Number.isInteger(scenario.early_clearance_sec) && Number.isInteger(scenario.late_clearance_sec) &&
    scenario.early_clearance_sec > scenario.blockage_start_sec &&
    scenario.late_clearance_sec > scenario.early_clearance_sec &&
    scenario.late_clearance_sec < scenario.duration_sec;
  const valid = validTiming && scenario.name.trim().length > 0 &&
    Number.isInteger(scenario.seeds[0]) && scenario.seeds[0] >= 0 && scenario.seeds[0] <= 2147483647;
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
          typeof result.late[key] === "number" || key === "mean_completed_travel_time_sec",
      )
    : [];
  const set = (key: keyof SimulationScenario, value: number) =>
    setScenario({ ...scenario, [key]: value });
  const outcomes = result ? [
    comparisonOutcome("delay", result.comparison.delay_saved_sec),
    comparisonOutcome("completed", result.comparison.additional_completed_vehicles),
    comparisonOutcome("queue", result.comparison.queue_reduction_vehicles),
  ] : [];
  return (
    <div className="inspector-content report-panel">
      <div className="section-kicker">
        <FlaskConical size={14} />
        SCENARIO LAB
      </div>
      <h2>Compare clearance times</h2>
      <p className="subtitle">
        Compare two clearance times against a road with no blockage, using the same traffic demand.
      </p>
      <div className="badge-row">
        <Badge tone="amber">Synthetic demand</Badge>
        <Badge>SUMO scenario</Badge>
      </div>
      <p className="report-note">A simulated 1st Avenue corridor in Manhattan. Demand and blockage are assumptions; this scenario is separate from archive footage.</p>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          if (valid && !active) onRun({ ...scenario, seeds: [...scenario.seeds] });
        }}
      >
        <p className="report-context">Blockage begins after {durationText(scenario.blockage_start_sec)}. Clearance times below are measured from the start of the run.</p>
        <div className="form-grid clearance-inputs">
          <label className="field">
            Earlier clearance (sec)
            <input
              type="number"
              required
              min={scenario.blockage_start_sec + 1}
              max={scenario.duration_sec - 2}
              value={scenario.early_clearance_sec}
              onChange={(event) => set("early_clearance_sec", Number(event.target.value))}
            />
            <small className="input-hint">{durationText(scenario.early_clearance_sec)} into the run</small>
          </label>
          <label className="field">
            Later clearance (sec)
            <input
              type="number"
              required
              min={scenario.early_clearance_sec + 1}
              max={scenario.duration_sec - 1}
              value={scenario.late_clearance_sec}
              onChange={(event) => set("late_clearance_sec", Number(event.target.value))}
            />
            <small className="input-hint">{durationText(scenario.late_clearance_sec)} into the run</small>
          </label>
        </div>
        <div className="scenario-schedule" aria-label="Clearance comparison timing">
          <span>Earlier <strong>{timecode(scenario.early_clearance_sec)}</strong></span>
          <ArrowRight size={14} aria-hidden="true" />
          <span>Later <strong>{timecode(scenario.late_clearance_sec)}</strong></span>
        </div>
        <label className="field">
          Traffic demand <span>{scenario.demand_vph.toLocaleString()} vehicles / hour</span>
          <input
            type="range" min="100" max="2400" step="100"
            value={scenario.demand_vph}
            onChange={(event) => set("demand_vph", Number(event.target.value))}
          />
        </label>
        <label className="field">
          Run duration
          <select value={scenario.duration_sec} onChange={(event) => set("duration_sec", Number(event.target.value))}>
            <option value={600}>10 minutes</option>
            <option value={900}>15 minutes</option>
            <option value={1800}>30 minutes</option>
          </select>
        </label>
        <details className="report-disclosure">
          <summary>Advanced settings</summary>
          <label className="field">
            Scenario name
            <input value={scenario.name} required maxLength={80}
              onChange={(event) => setScenario({ ...scenario, name: event.target.value })} />
          </label>
          <label className="field">
            Random seed
            <input type="number" required min="0" max="2147483647" value={scenario.seeds[0]}
              onChange={(event) => setScenario({ ...scenario, seeds: [Number(event.target.value)] })} />
          </label>
          <p className="report-note">All three alternatives use the same demand and seed so the comparison is reproducible.</p>
        </details>
        {!valid && <p className="field-error" role="alert">
          {!validTiming
            ? "Clearance must follow the blockage, with earlier clearance before later clearance and both within the run."
            : "Check advanced settings: give the scenario a name and use a whole-number seed between 0 and 2,147,483,647."}
        </p>}
        <button className="button primary full" type="submit" disabled={!!active || !valid}>
          {active ? "Simulation running…" : "Run comparison"}<Play size={15} />
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
            <span className="caption">{active ? "Computing all three alternatives" : "Comparison job finished"}</span>
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
                : typeof job.error === "object" && "message" in job.error && typeof job.error.message === "string"
                  ? job.error.message : "The simulation could not complete. Check the connection status and try again."}
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
            <p className="report-context">Earlier clearance at {durationText(result.scenario.early_clearance_sec)} versus later clearance at {durationText(result.scenario.late_clearance_sec)}.</p>
            <p className="report-note">Measured over {durationText(result.scenario.duration_sec)} with {formatNumber(result.scenario.demand_vph, 0)} vehicles per hour. These are simulated outcomes, not a forecast of current traffic.</p>
            <div className="report-outcomes" aria-label="Earlier versus later clearance outcomes">
              {outcomes.map((outcome, index) => <div className="outcome-card" key={index}>
                <strong>{outcome.value}</strong><span>{outcome.label}</span><small>Earlier compared with later</small>
              </div>)}
            </div>
            <dl className="report-facts">
              {(["early", "late"] as const).map((alternative) => <div key={alternative}>
                <dt>{alternative === "early" ? "Earlier" : "Later"}: at run end</dt>
                <dd>{metricValue("unfinished_vehicles", result[alternative].unfinished_vehicles)} still on the road; {metricValue("insertion_backlog", result[alternative].insertion_backlog)} waiting to enter</dd>
              </div>)}
            </dl>
            <p className="report-note">Delay and journey time stop accumulating when the run ends. They are lower bounds for trips still unfinished, including vehicles waiting to enter. A completed-trip average excludes those vehicles.</p>
            {result.scenario.seeds.length > 1 && <p className="report-note">Results average {result.scenario.seeds.length} paired seeds. Completed-trip time is weighted by the number of completed vehicles. Map replay shows the first seed.</p>}
          </div>
          <details className="report-disclosure">
            <summary>All comparison metrics</summary>
            <p className="metric-help">The baseline has no blockage. One vehicle-minute is one minute accumulated by one vehicle; totals add time across all vehicles. If no trips finish, completed-trip time is unavailable.</p>
            {metrics.length ? (
              <div className="comparison-table">
                <table>
                  <thead>
                    <tr>
                      <th>Metric</th>
                      <th>No blockage</th>
                      <th>Earlier</th>
                      <th>Later</th>
                    </tr>
                  </thead>
                  <tbody>
                    {metrics.map((key) => (
                      <tr key={key}>
                        <th>{metricLabel(key)}</th>
                        {[result.baseline, result.early, result.late].map(
                          (values, index) => (
                            <td key={index}>
                              {metricValue(key, values[key])}
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
          </details>
          {playback && playback.frames.length > 0 ? (
            <div className="detail-block">
              <h3>Synchronized map replay</h3>
              <div className="segmented">
                <button
                  className={comparison === "early" ? "active" : ""}
                  aria-pressed={comparison === "early"}
                  onClick={() => onComparison("early")}
                >
                  Baseline + early
                </button>
                <button
                  className={comparison === "late" ? "active" : ""}
                  aria-pressed={comparison === "late"}
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
            <dl className="report-facts">
              <div><dt>Simulation engine</dt><dd>{result.engine}</dd></div>
              <div><dt>Saved scenario</dt><dd>{result.scenario.name}</dd></div>
              <div><dt>Random seeds</dt><dd>{result.scenario.seeds.join(", ")}</dd></div>
              <div><dt>Demand</dt><dd>{formatNumber(result.scenario.demand_vph, 0)} vehicles / hour</dd></div>
            </dl>
            {result.assumptions.map((assumption, index) => (
              <p key={index}>{assumption}</p>
            ))}
            <details><summary>Exact run inputs</summary><pre>{JSON.stringify(result.scenario, null, 2)}</pre></details>
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

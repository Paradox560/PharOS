import { useState } from "react";
import { ArrowUpRight, ChartNoAxesCombined, Info } from "lucide-react";
import type { ForecastRun, RiskCell, RoadSegment } from "./types";
import { humanize, pct, timestamp } from "./api";
import { Badge, Empty, ErrorMessage, OriginBadge } from "./ui";
import { describeFactor, durationText, finiteNumber, formatNumber } from "./reportFormatting";

export default function ForecastPanel({
  roads,
  roadId,
  onRoad,
  risk,
  forecast,
  loading,
  error,
  onRun,
}: {
  roads: RoadSegment[];
  roadId: string;
  onRoad: (id: string) => void;
  risk: RiskCell | null;
  forecast: ForecastRun | null;
  loading: boolean;
  error: string | null;
  onRun: (mode: string) => void;
}) {
  const [mode, setMode] = useState("illustrative");
  const [horizon, setHorizon] = useState(15);
  const current = forecast?.horizons.find((item) => item.minutes === horizon) || forecast?.horizons[0];
  const road = roads.find((item) => item.id === roadId);
  const resultRoad = roads.find((item) => item.id === forecast?.road_id);
  const modelVersion = forecast && "model_version" in forecast && typeof forecast.model_version === "string" ? forecast.model_version : null;
  const evaluationRows = Array.isArray(forecast?.evaluation.by_horizon)
    ? forecast.evaluation.by_horizon.filter((row): row is Record<string, unknown> => !!row && typeof row === "object") : [];
  const maxSpeed = Math.max(
    60,
    ...(forecast?.horizons.flatMap((item) => [
      item.speed_kph || 0,
      item.upper_kph || 0,
    ]) || []),
  );
  const y = (speed: number) => 130 - (speed / maxSpeed) * 95;
  const x = (index: number) => 45 + index * (220 / Math.max(1, (forecast?.horizons.length || 1) - 1));
  const points = forecast?.horizons.every((item) => item.speed_kph != null)
    ? forecast.horizons.map((item, index) => `${x(index)},${y(item.speed_kph!)}`).join(" ") : undefined;
  return (
    <div className="inspector-content report-panel">
      <div className="section-kicker">
        <ChartNoAxesCombined size={14} />
        FORECAST & PRIORITY
      </div>
      <h2>Traffic forecast</h2>
      <p className="subtitle">
        Choose a road and an outlook method. Review the evidence behind each estimate.
      </p>
      <label className="field">
        Road segment
        <select value={roadId} onChange={(event) => onRoad(event.target.value)}>
          {roads.length ? (
            roads.map((road) => (
              <option key={road.id} value={road.id}>
                {road.name}
              </option>
            ))
          ) : (
            <option value="">No road segments available</option>
          )}
        </select>
      </label>
      {road && <p className="report-context">{formatNumber(road.length_m)} m segment · {road.lanes} {road.lanes === 1 ? "lane" : "lanes"}</p>}
      <label className="field">
        Forecast method
        <select value={mode} onChange={(event) => setMode(event.target.value)}>
          <option value="illustrative">Illustrative demo</option>
          <option value="persistence">Persistence from latest sensor</option>
        </select>
      </label>
      <p className="report-note">
        {mode === "illustrative"
          ? "Uses a synthetic traffic pattern to demonstrate the forecast. It does not describe current road conditions."
          : "Holds the latest measured speed steady. Requires recent sensor history explicitly linked to this road."}
      </p>
      <button className="button primary full" disabled={loading || !roadId} onClick={() => onRun(mode)}>
        {loading ? "Computing forecast…" : "Run forecast"}<ArrowUpRight size={15} />
      </button>
      <ErrorMessage error={error} />
      {forecast ? (
        <>
          <div className="detail-block">
            <div className="split">
              <h3>Speed outlook</h3>
              <Badge>{humanize(forecast.mode)}</Badge>
            </div>
            <div className="badge-row">
              <OriginBadge value={forecast.data_origin} />
              <OriginBadge value={forecast.execution_mode} />
            </div>
            <p className="report-context">{resultRoad?.name || "Road in the saved forecast"} · issued {timestamp(forecast.issued_at)}</p>
            {(forecast.road_id !== roadId || forecast.mode !== mode) && <p className="notice">Showing the last completed forecast. Run again to apply your current road and method.</p>}
            <p className="report-note">{forecast.data_origin === "synthetic" ? "Illustrative estimates from synthetic history. Their accuracy on real traffic is unknown." : "A baseline estimate from associated sensors, not a guarantee of future conditions."}</p>
            <svg
              className="forecast-chart"
              viewBox="0 0 310 165"
              role="img"
              aria-label="Forecast speeds at five, fifteen and thirty minute horizons"
            >
              {[0, 0.5, 1].map((value) => (
                <g key={value}>
                  <line
                    x1="38"
                    x2="292"
                    y1={y(value * maxSpeed)}
                    y2={y(value * maxSpeed)}
                    stroke="var(--report-chart-grid, #c6c8bb)"
                    strokeDasharray="3 4"
                  />
                  <text x="4" y={y(value * maxSpeed) + 4}>
                    {Math.round(value * maxSpeed)}
                  </text>
                </g>
              ))}
              <text x="5" y="15">
                km/h
              </text>
              {forecast.horizons.map((item, index) => (
                <g key={item.minutes}>
                  {item.lower_kph != null && item.upper_kph != null && (
                    <line
                      x1={x(index)}
                      x2={x(index)}
                      y1={y(item.lower_kph)}
                      y2={y(item.upper_kph)}
                      stroke="var(--report-chart-line, #496444)"
                      strokeWidth="18"
                      opacity=".13"
                    />
                  )}
                  {item.speed_kph != null && (
                    <circle
                      cx={x(index)}
                      cy={y(item.speed_kph)}
                      r="4"
                      fill="var(--report-chart-line, #496444)"
                    />
                  )}
                  <text x={x(index)} y="154" textAnchor="middle">
                    +{item.minutes}m
                  </text>
                </g>
              ))}
              <polyline
                points={points}
                stroke="var(--report-chart-line, #496444)"
                strokeWidth="2"
                fill="none"
              />
            </svg>
            <div className="segmented">
              {forecast.horizons.map((item) => (
                <button
                  className={current?.minutes === item.minutes ? "active" : ""}
                  aria-pressed={current?.minutes === item.minutes}
                  key={item.minutes}
                  onClick={() => setHorizon(item.minutes)}
                >
                  +{item.minutes} min
                </button>
              ))}
            </div>
            {current && (
              <div className="forecast-values">
                <div>
                  <strong>
                    {current.speed_kph == null
                      ? "—"
                      : current.speed_kph.toFixed(1)}
                    <small> km/h</small>
                  </strong>
                  <span>Estimated speed</span>
                </div>
                <div>
                  <strong>
                    {durationText(current.travel_time_sec)}
                  </strong>
                  <span>Across this road segment</span>
                </div>
              </div>
            )}
            <p className="caption">
              Estimated speed range:{" "}
              {current?.lower_kph == null || current?.upper_kph == null
                ? "Uncertainty not available"
                : `${current.lower_kph.toFixed(1)}–${current.upper_kph.toFixed(1)} km/h`}{" "}
            </p>
            <p className="report-note">The range reflects errors in the available history. It is not a guaranteed range. Travel time uses this segment’s length and estimated speed.</p>
          </div>
          <details className="report-disclosure">
            <summary><Info size={15} /> Method, assumptions & evaluation</summary>
            {forecast.assumptions.map((assumption, index) => (
              <p className="caption" key={index}>
                {assumption}
              </p>
            ))}
            <dl className="report-facts">
              <div><dt>Method</dt><dd>{forecast.mode === "illustrative" ? "Historical time-of-week baseline" : "Latest-speed persistence"}</dd></div>
              {modelVersion && <div><dt>Model version</dt><dd>{modelVersion}</dd></div>}
              <div><dt>Evaluation</dt><dd>{typeof forecast.evaluation.status === "string" ? humanize(forecast.evaluation.status) : "Unavailable"}</dd></div>
              <div><dt>History samples</dt><dd>{finiteNumber(forecast.evaluation.sample_count) == null ? "Unavailable" : formatNumber(forecast.evaluation.sample_count as number, 0)}</dd></div>
              <div><dt>Evaluation data</dt><dd>{forecast.data_origin === "synthetic" ? "Synthetic examples only" : "Associated sensor history"}</dd></div>
            </dl>
            {evaluationRows.length ? <>
              <p className="report-note">Average speed error on later, held-out observations. Lower is better. Synthetic test results do not establish real-world accuracy.</p>
              <div className="comparison-table evaluation-table"><table>
                <thead><tr><th>Look ahead</th><th>Latest speed</th><th>Historical pattern</th></tr></thead>
                <tbody>{evaluationRows.map((row, index) => <tr key={index}>
                  <th>{finiteNumber(row.minutes) == null ? "Unavailable" : `${row.minutes} min`}</th>
                  {["persistence", "historical"].map((method) => {
                    const metrics = row[method];
                    const error = metrics && typeof metrics === "object" ? finiteNumber((metrics as Record<string, unknown>).mae_kph) : null;
                    return <td key={method}>{error == null ? "Unavailable" : `${formatNumber(error)} km/h`}</td>;
                  })}
                </tr>)}</tbody>
              </table></div>
            </> : (
              <p className="caption">
                No evaluation data returned. This forecast has no demonstrated
                accuracy improvement.
              </p>
            )}
            <details className="provenance"><summary>Detailed evaluation record</summary><pre>{JSON.stringify(forecast.evaluation, null, 2)}</pre></details>
          </details>
        </>
      ) : (
        <Empty title="A forecast starts with evidence">
          Choose a road and method. Illustrative outputs remain explicitly
          separate from observed traffic.
        </Empty>
      )}
      {risk ? (
        <div className="risk-card">
          <div className="split">
            <span className="eyebrow">OPERATIONAL PRIORITY</span>
            <Badge tone={risk.level === "high" ? "orange" : "amber"}>
              {risk.level}
            </Badge>
          </div>
          <p className="report-context">{road?.name || "Selected road"}</p>
          <div className="risk-score">
            {risk.score == null ? "—" : Math.round(risk.score)}
            <span>{risk.score == null ? "Unknown" : "/ 100"}</span>
          </div>
          <p className="report-note">Priority for reviewing a road disruption. This score is not a crash probability. Missing observations do not mean conditions are normal.</p>
          <div className="risk-meta">
            <span>
              Confidence <strong>{pct(risk.confidence)}</strong>
            </span>
            <span>
              Coverage <strong>{pct(risk.coverage)}</strong>
            </span>
          </div>
          <p className="caption">
            {timestamp(risk.observed_at)} ·{" "}
            <OriginBadge value={risk.data_origin} />
          </p>
          {risk.factors.length > 0 && <ul className="factor-list">
            {risk.factors.map((factor, index) => {
              const item = describeFactor(factor);
              return <li key={index}><div><span>{item.label}</span><strong>{item.value}</strong></div>{item.detail && <small>{item.detail}</small>}</li>;
            })}
          </ul>}
          <details className="report-disclosure">
            <summary>Scoring method & evidence</summary>
            <p className="report-note">Factor scores describe disruption strength. Coverage is the share of scoring weights with observations; confidence reflects evidence quality and age.</p>
            <p className="caption">
              Evidence references: {risk.evidence_ids.join(", ") || "None available"}
            </p>
          </details>
        </div>
      ) : (
        <div className="notice">
          No priority observations for this road. Missing coverage is not a
          normal-conditions signal.
        </div>
      )}
    </div>
  );
}

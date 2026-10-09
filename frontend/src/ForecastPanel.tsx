import { useState } from "react";
import { ArrowUpRight, ChartNoAxesCombined, Info } from "lucide-react";
import type { ForecastRun, RiskCell, RoadSegment } from "./types";
import { humanize, pct, timestamp } from "./api";
import { Badge, Empty, ErrorMessage, OriginBadge } from "./ui";

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
  const current = forecast?.horizons.find((item) => item.minutes === horizon);
  const maxSpeed = Math.max(
    60,
    ...(forecast?.horizons.flatMap((item) => [
      item.speed_kph || 0,
      item.upper_kph || 0,
    ]) || []),
  );
  const y = (speed: number) => 130 - (speed / maxSpeed) * 95;
  const points = forecast?.horizons
    .filter((item) => item.speed_kph != null)
    .map((item, index) => `${45 + index * 110},${y(item.speed_kph!)}`)
    .join(" ");
  return (
    <div className="inspector-content">
      <div className="section-kicker">
        <ChartNoAxesCombined size={14} />
        FORECAST & PRIORITY
      </div>
      <h2>Look ahead.</h2>
      <p className="subtitle">
        Road speed and travel-time outlook, with its assumptions in view.
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
      {risk ? (
        <div className="risk-card">
          <div className="split">
            <span className="eyebrow">OPERATIONAL PRIORITY</span>
            <Badge tone={risk.level === "high" ? "orange" : "amber"}>
              {risk.level}
            </Badge>
          </div>
          <div className="risk-score">
            {risk.score == null ? "—" : Math.round(risk.score)}
            <span>/ 100</span>
          </div>
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
          <details>
            <summary>Scoring factors & evidence</summary>
            {risk.factors.length ? (
              risk.factors.map((factor, index) => (
                <p className="caption" key={index}>
                  {typeof factor === "string" ? factor : JSON.stringify(factor)}
                </p>
              ))
            ) : (
              <p className="caption">No contributing observations.</p>
            )}
            <p className="caption">
              Evidence: {risk.evidence_ids.join(", ") || "None available"}
            </p>
          </details>
        </div>
      ) : (
        <div className="notice">
          No priority observations for this road. Missing coverage is not a
          normal-conditions signal.
        </div>
      )}
      <label className="field">
        Forecast method
        <select value={mode} onChange={(event) => setMode(event.target.value)}>
          <option value="illustrative">Illustrative demo</option>
          <option value="persistence">Persistence from latest sensor</option>
        </select>
      </label>
      <button
        className="button primary full"
        disabled={loading || !roadId}
        onClick={() => onRun(mode)}
      >
        {loading ? "Computing forecast…" : "Run forecast"}
        <ArrowUpRight size={15} />
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
                    stroke="#303a31"
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
                      x1={45 + index * 110}
                      x2={45 + index * 110}
                      y1={y(item.lower_kph)}
                      y2={y(item.upper_kph)}
                      stroke="#a8be8b"
                      strokeWidth="18"
                      opacity=".13"
                    />
                  )}
                  {item.speed_kph != null && (
                    <circle
                      cx={45 + index * 110}
                      cy={y(item.speed_kph)}
                      r="4"
                      fill="#c9ec95"
                    />
                  )}
                  <text x={45 + index * 110} y="154" textAnchor="middle">
                    +{item.minutes}m
                  </text>
                </g>
              ))}
              <polyline
                points={points}
                stroke="#c9ec95"
                strokeWidth="2"
                fill="none"
              />
            </svg>
            <div className="segmented">
              {forecast.horizons.map((item) => (
                <button
                  className={horizon === item.minutes ? "active" : ""}
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
                    {current.travel_time_sec == null
                      ? "—"
                      : Math.round(current.travel_time_sec)}
                    <small> sec</small>
                  </strong>
                  <span>Road travel time</span>
                </div>
              </div>
            )}
            <p className="caption">
              Range:{" "}
              {current?.lower_kph == null || current?.upper_kph == null
                ? "Uncertainty not available"
                : `${current.lower_kph.toFixed(1)}–${current.upper_kph.toFixed(1)} km/h`}{" "}
              · issued {timestamp(forecast.issued_at)}
            </p>
          </div>
          <div className="detail-block">
            <h3>
              <Info size={15} /> Assumptions & evaluation
            </h3>
            {forecast.assumptions.map((assumption, index) => (
              <p className="caption" key={index}>
                {assumption}
              </p>
            ))}
            {Object.keys(forecast.evaluation).length ? (
              <dl>
                {Object.entries(forecast.evaluation).map(([key, value]) => (
                  <div key={key}>
                    <dt>{humanize(key)}</dt>
                    <dd>
                      {typeof value === "object"
                        ? JSON.stringify(value)
                        : String(value)}
                    </dd>
                  </div>
                ))}
              </dl>
            ) : (
              <p className="caption">
                No evaluation data returned. This forecast has no demonstrated
                accuracy improvement.
              </p>
            )}
          </div>
        </>
      ) : (
        <Empty title="A forecast starts with evidence">
          Choose a road and method. Illustrative outputs remain explicitly
          separate from observed traffic.
        </Empty>
      )}
    </div>
  );
}

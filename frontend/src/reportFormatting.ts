export function finiteNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

export function formatNumber(value: number, digits = 1): string {
  return value.toLocaleString("en-US", { maximumFractionDigits: digits });
}

export function durationText(value: unknown): string {
  const seconds = finiteNumber(value);
  if (seconds == null) return "Unavailable";
  return seconds >= 60
    ? `${formatNumber(seconds / 60)} min`
    : `${formatNumber(seconds)} sec`;
}

const metricLabels: Record<string, string> = {
  scheduled_vehicles: "Vehicles scheduled",
  departed_vehicles: "Vehicles that entered",
  throughput: "Completed trips",
  unfinished_vehicles: "Trips still on the road",
  insertion_backlog: "Vehicles waiting to enter",
  completion_rate: "Share of trips completed",
  mean_completed_travel_time_sec: "Average completed trip",
  total_completed_travel_time_sec: "Time spent on completed trips",
  mean_elapsed_journey_time_sec: "Average journey time so far",
  total_elapsed_journey_time_sec: "Total journey time so far",
  total_waiting_time_sec: "Time stopped or waiting to enter",
  total_delay_sec: "Total delay so far",
  mean_delay_sec: "Average delay so far",
  peak_queue_vehicles: "Largest queue",
  mean_queue_vehicles: "Average queue",
};

export function metricLabel(key: string): string {
  return metricLabels[key] || key.replaceAll("_", " ");
}

export function metricValue(key: string, value: unknown): string {
  const number = finiteNumber(value);
  if (number == null) return "Unavailable";
  if (key === "completion_rate") return `${formatNumber(number * 100)}%`;
  if (key.startsWith("total_") && key.endsWith("_sec"))
    return `${formatNumber(number / 60)} vehicle-min`;
  if (key.endsWith("_sec")) return durationText(number);
  return key in metricLabels ? `${formatNumber(number)} vehicles` : formatNumber(number);
}

export function comparisonOutcome(
  kind: "delay" | "completed" | "queue",
  value: unknown,
): { value: string; label: string } {
  const number = finiteNumber(value);
  const names = { delay: "delay", completed: "completed trips", queue: "peak queue" };
  if (number == null) return { value: "Unavailable", label: `${names[kind]} comparison` };
  if (number === 0) return { value: "No change", label: `in ${names[kind]}` };
  if (kind === "delay") return {
    value: `${formatNumber(Math.abs(number) / 60)} vehicle-min`,
    label: number > 0 ? "less delay accumulated" : "more delay accumulated",
  };
  if (kind === "completed") return {
    value: formatNumber(Math.abs(number)),
    label: number > 0 ? "more completed trips" : "fewer completed trips",
  };
  return {
    value: `${formatNumber(Math.abs(number))} vehicles`,
    label: number > 0 ? "smaller peak queue" : "larger peak queue",
  };
}

export function describeFactor(factor: unknown): { label: string; value: string; detail: string } {
  if (typeof factor === "string") return { label: factor, value: "", detail: "" };
  if (!factor || typeof factor !== "object")
    return { label: "Observation", value: "Unavailable", detail: "No factor details were supplied." };
  const row = factor as Record<string, unknown>;
  const labels: Record<string, string> = {
    obstruction: "Obstruction", persistence: "Duration of disruption",
    slowdown: "Traffic slowdown", severity: "Reported severity",
    corroboration: "Supporting observations",
  };
  const name = typeof row.name === "string" ? row.name : "Observation";
  const value = finiteNumber(row.value);
  const weight = finiteNumber(row.weight);
  const detail = [
    weight == null ? "" : `${formatNumber(weight * 100, 0)}% of scoring weight`,
    row.freshness === "stale" ? "older evidence" : "",
    row.data_origin === "synthetic" ? "synthetic example" : "",
  ].filter(Boolean).join(" · ");
  return { label: labels[name] || name.replaceAll("_", " "),
    value: value == null ? "Unavailable" : `${formatNumber(value * 100, 0)} / 100`, detail };
}

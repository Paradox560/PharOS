export function apiBase(pathname = window.location.pathname): string {
  return /^\/app(?:\/|$)/.test(pathname) ? "/app/api" : "/api";
}

export function mediaUrl(value: string | null | undefined): string | undefined {
  if (!value) return undefined;
  if (value.startsWith("/api/")) return `${apiBase()}${value.slice(4)}`;
  if (value.startsWith("/app/api/")) return `${apiBase()}${value.slice(8)}`;
  // Playback is served by registered same-origin media IDs; do not leak upstream signed URLs.
  if (value.startsWith("/") && !value.startsWith("//")) return value;
  return undefined;
}

export async function request<T>(
  path: string,
  body?: unknown,
  signal?: AbortSignal,
): Promise<T> {
  const response = await fetch(`${apiBase()}${path}`, {
    method: body === undefined ? "GET" : "POST",
    headers:
      body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
    signal,
  });
  let data: unknown;
  try {
    data = await response.json();
  } catch {
    throw new Error(
      `API returned ${response.status}; a JSON response was expected.`,
    );
  }
  if (!response.ok) {
    const detail = data as { error?: { message?: string }; detail?: string };
    throw new Error(
      detail.error?.message ||
        (typeof detail.detail === "string"
          ? detail.detail
          : `Request failed (${response.status})`),
    );
  }
  return data as T;
}

export function timecode(seconds: number): string {
  const value = Math.max(0, Math.floor(seconds));
  return `${Math.floor(value / 60)
    .toString()
    .padStart(2, "0")}:${(value % 60).toString().padStart(2, "0")}`;
}
export function humanize(value: string): string {
  return value.replaceAll("_", " ");
}
export function timestamp(value: string | null | undefined): string {
  if (!value) return "Capture time unknown";
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? "Time unavailable"
    : `${date.toLocaleString("en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", hour12: false, timeZone: "UTC" })} UTC`;
}
export function pct(value: number | undefined | null): string {
  return value == null ? "Unknown" : `${Math.round(value * 100)}%`;
}

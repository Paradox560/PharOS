import type { Detection } from "./types";
export function boxesAtTime(
  detections: Detection[],
  seconds: number,
): Detection[] {
  // Show one recorded frame, preserving all of its boxes. A tolerance window
  // alone would stack many adjacent frames from dense sidecars (for example 30fps).
  // Keep the time bound so sparse detections cannot imply continuous tracking.
  let nearestTimestamp: number | null = null;
  let nearestDistance = Infinity;
  for (const detection of detections) {
    const distance = Math.abs(detection.timestamp_sec - seconds);
    if (!Number.isFinite(distance) || distance > 0.26) continue;
    if (
      distance < nearestDistance - 1e-9 ||
      (Math.abs(distance - nearestDistance) <= 1e-9 &&
        (nearestTimestamp === null || detection.timestamp_sec < nearestTimestamp))
    ) {
      nearestTimestamp = detection.timestamp_sec;
      nearestDistance = distance;
    }
  }
  return nearestTimestamp === null
    ? []
    : detections.filter((detection) => detection.timestamp_sec === nearestTimestamp);
}
export function normalizedBox(
  detection: Detection,
  width: number,
  height: number,
): [number, number, number, number] | null {
  if (detection.bbox_units === "pixels" && (!width || !height)) return null;
  const box = detection.bbox.map((value, index) =>
    detection.bbox_units === "pixels"
      ? value / (index % 2 === 0 ? width : height)
      : value,
  );
  if (
    box.some((value) => !Number.isFinite(value)) ||
    box[2] <= box[0] ||
    box[3] <= box[1]
  )
    return null;
  const clamped = box.map((value) => Math.min(1, Math.max(0, value)));
  return clamped[2] > clamped[0] && clamped[3] > clamped[1]
    ? (clamped as [number, number, number, number])
    : null;
}

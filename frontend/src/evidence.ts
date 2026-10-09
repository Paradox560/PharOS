import type { Detection } from "./types";
export function boxesAtTime(
  detections: Detection[],
  seconds: number,
): Detection[] {
  // Never hold a detection across an unknown interval or imply a continuous track.
  return detections.filter(
    (detection) => Math.abs(detection.timestamp_sec - seconds) <= 0.26,
  );
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

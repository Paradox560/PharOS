import { describe, expect, it } from "vitest";
import { boxesAtTime, normalizedBox } from "./evidence";
import type { Detection } from "./types";
const detection: Detection = {
  id: "a",
  evidence_id: "e",
  class_name: "truck",
  confidence: 0.8,
  timestamp_sec: 8,
  bbox: [10, 20, 30, 60],
  bbox_units: "pixels",
  track_id: null,
  model: "test",
  execution_mode: "mock",
};
describe("evidence alignment", () => {
  it("does not carry sparse detections into unobserved video times", () => {
    expect(boxesAtTime([detection], 8)).toEqual([detection]);
    expect(boxesAtTime([detection], 9)).toEqual([]);
    expect(boxesAtTime([detection], 7)).toEqual([]);
  });
  it("normalizes pixel boxes only with known source dimensions", () => {
    expect(normalizedBox(detection, 100, 200)).toEqual([0.1, 0.1, 0.3, 0.3]);
    expect(normalizedBox(detection, 0, 0)).toBeNull();
  });
  it("rejects malformed and wholly out-of-frame boxes", () => {
    expect(
      normalizedBox({ ...detection, bbox: [30, 20, 10, 60] }, 100, 200),
    ).toBeNull();
    expect(
      normalizedBox(
        { ...detection, bbox_units: "normalized", bbox: [2, 2, 3, 3] },
        100,
        200,
      ),
    ).toBeNull();
    expect(
      normalizedBox({ ...detection, bbox: [0, 0, NaN, 2] }, 100, 200),
    ).toBeNull();
  });
});

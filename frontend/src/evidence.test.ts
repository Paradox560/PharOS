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
    expect(boxesAtTime([detection], 8.25)).toEqual([detection]);
    expect(boxesAtTime([detection], 8.27)).toEqual([]);
    expect(boxesAtTime([detection], 9)).toEqual([]);
    expect(boxesAtTime([detection], 7)).toEqual([]);
  });
  it("shows only the nearest frame of a dense 30fps sidecar, keeping every box in that frame", () => {
    const dense = Array.from({ length: 150 }, (_, frame) =>
      Array.from({ length: 14 }, (_, object) => ({
        ...detection,
        id: `${frame}:${object}`,
        timestamp_sec: frame / 30,
      })),
    ).flat();
    const selected = boxesAtTime(dense, 2.413);
    expect(selected).toHaveLength(14);
    expect(selected.map((box) => box.id)).toEqual(
      Array.from({ length: 14 }, (_, object) => `72:${object}`),
    );
  });
  it("selects the earlier frame on a tie regardless of input order", () => {
    const later = { ...detection, id: "later", timestamp_sec: 1.25 };
    const earlier = { ...detection, id: "earlier", timestamp_sec: 1 };
    expect(boxesAtTime([later, earlier], 1.125)).toEqual([earlier]);
    expect(boxesAtTime([earlier, later], 1.125)).toEqual([earlier]);
    expect(boxesAtTime([], 1.125)).toEqual([]);
    expect(boxesAtTime([earlier], NaN)).toEqual([]);
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

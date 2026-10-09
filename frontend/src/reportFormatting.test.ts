import { describe, expect, it } from "vitest";
import { comparisonOutcome, describeFactor, metricValue } from "./reportFormatting";

describe("operator report formatting", () => {
  it("keeps missing completed trips distinct from zero duration", () => {
    expect(metricValue("mean_completed_travel_time_sec", null)).toBe("Unavailable");
    expect(metricValue("mean_completed_travel_time_sec", 0)).toBe("0 sec");
    expect(metricValue("completion_rate", 0)).toBe("0%");
  });
  it("converts accumulated vehicle seconds without presenting clock time", () => {
    expect(metricValue("total_delay_sec", 7599.48)).toBe("126.7 vehicle-min");
    expect(metricValue("mean_completed_travel_time_sec", 370.68)).toBe("6.2 min");
  });
  it("never labels a worse scenario as an improvement", () => {
    expect(comparisonOutcome("delay", -60)).toEqual({ value: "1 vehicle-min", label: "more delay accumulated" });
    expect(comparisonOutcome("completed", -4).label).toBe("fewer completed trips");
    expect(comparisonOutcome("queue", -10).label).toBe("larger peak queue");
    expect(comparisonOutcome("delay", 0).value).toBe("No change");
    expect(comparisonOutcome("delay", null).value).toBe("Unavailable");
  });
  it("makes a risk factor readable while retaining age and synthetic origin", () => {
    expect(describeFactor({ name: "slowdown", value: .7, weight: .2, freshness: "stale", data_origin: "synthetic" }))
      .toEqual({ label: "Traffic slowdown", value: "70 / 100", detail: "20% of scoring weight · older evidence · synthetic example" });
  });
});

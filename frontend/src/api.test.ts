import { afterEach, describe, expect, it, vi } from "vitest";
import { apiBase, mediaUrl, request } from "./api";
afterEach(() => vi.unstubAllGlobals());
describe("deployment paths and provider errors", () => {
  it("preserves the external app prefix with and without a trailing slash", () => {
    expect(apiBase("/")).toBe("/api");
    expect(apiBase("/app")).toBe("/app/api");
    expect(apiBase("/app/")).toBe("/app/api");
    expect(apiBase("/application")).toBe("/api");
  });
  it("rewrites registered media through the app API without exposing remote signed URLs", () => {
    vi.stubGlobal("window", { location: { pathname: "/app/" } });
    expect(mediaUrl("/api/assets/a/media")).toBe("/app/api/assets/a/media");
    expect(mediaUrl("/app/api/assets/a/media")).toBe("/app/api/assets/a/media");
    expect(mediaUrl("https://s3.example/a?credential=secret")).toBeUndefined();
    expect(mediaUrl("//external.example/media")).toBeUndefined();
  });
  it("surfaces explicit provider errors without substituting demo data", async () => {
    vi.stubGlobal("window", { location: { pathname: "/" } });
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue({
          ok: false,
          status: 503,
          json: async () => ({
            error: { code: "vss_unavailable", message: "VSS is unavailable" },
          }),
        }),
    );
    await expect(
      request("/search", { query: "stopped vehicles" }),
    ).rejects.toThrow("VSS is unavailable");
  });
});

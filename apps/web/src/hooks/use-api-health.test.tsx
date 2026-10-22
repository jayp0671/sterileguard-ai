import { ApiError } from "@sg/contracts";
import { renderHook, waitFor } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";
import { API, server } from "@/test/msw";
import { Providers } from "@/test/render";
import { useApiHealth } from "./use-api-health";

describe("useApiHealth", () => {
  it("returns the API version from /health", async () => {
    const { result } = renderHook(() => useApiHealth(), { wrapper: Providers });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.version).toBe("test-1");
  });

  it("surfaces problem+json errors as ApiError", async () => {
    server.use(
      http.get(`${API}/health`, () =>
        HttpResponse.json(
          { type: "about:blank", title: "Service Unavailable", status: 503, request_id: "r1" },
          { status: 503, headers: { "content-type": "application/problem+json" } },
        ),
      ),
    );
    const { result } = renderHook(() => useApiHealth(), { wrapper: Providers });
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error).toBeInstanceOf(ApiError);
    expect((result.current.error as ApiError).requestId).toBe("r1");
  });
});

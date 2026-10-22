import { describe, expect, it, vi } from "vitest";
import { ApiError, createApiClient, toApiError } from "./index";

const problem = {
  type: "about:blank",
  title: "Not Found",
  status: 404,
  detail: "no such plan",
  request_id: "rid-1",
};

describe("toApiError", () => {
  it("maps a problem+json body", async () => {
    const res = new Response(JSON.stringify(problem), {
      status: 404,
      headers: { "content-type": "application/problem+json" },
    });
    const err = await toApiError(res);
    expect(err).toBeInstanceOf(ApiError);
    expect(err.status).toBe(404);
    expect(err.detail).toBe("no such plan");
    expect(err.requestId).toBe("rid-1");
    expect(err.message).toBe("no such plan");
  });

  it("falls back for non-problem bodies", async () => {
    const res = new Response("oops", {
      status: 502,
      statusText: "Bad Gateway",
      headers: { "X-Request-ID": "rid-2" },
    });
    const err = await toApiError(res);
    expect(err.status).toBe(502);
    expect(err.title).toBe("Bad Gateway");
    expect(err.requestId).toBe("rid-2");
  });
});

describe("createApiClient", () => {
  it("adds bearer token and request id, and throws ApiError on failure", async () => {
    const seen: Request[] = [];
    const fetchMock = vi.fn(async (input: Request) => {
      seen.push(input);
      return new Response(JSON.stringify(problem), { status: 404 });
    });
    vi.stubGlobal("fetch", fetchMock);
    const client = createApiClient("http://api.test", () => "tok");
    await expect(client.GET("/health")).rejects.toBeInstanceOf(ApiError);
    const req = seen[0];
    expect(req?.headers.get("Authorization")).toBe("Bearer tok");
    expect(req?.headers.get("X-Request-ID")).toMatch(/^[0-9a-f-]{36}$/);
    vi.unstubAllGlobals();
  });

  it("returns typed data on success", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => Response.json({ status: "ok", version: "1" })),
    );
    const client = createApiClient("http://api.test");
    const { data } = await client.GET("/health");
    expect(data?.version).toBe("1");
    vi.unstubAllGlobals();
  });
});

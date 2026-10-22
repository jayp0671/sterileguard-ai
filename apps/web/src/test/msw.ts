import { HttpResponse, http } from "msw";
import { setupServer } from "msw/node";

/** Base URL the API client uses in tests (see vitest.config.ts env). */
export const API = "http://api.test";

export const handlers = [
  http.get(`${API}/health`, () => HttpResponse.json({ status: "ok", version: "test-1" })),
];

export const server = setupServer(...handlers);

import createClient, { type Middleware } from "openapi-fetch";
import type { components, paths } from "./schema";

export type { components, paths };
export type Problem = components["schemas"]["Problem"];

/** A failed API call, mapped from an RFC 9457 problem+json body. */
export class ApiError extends Error {
  readonly status: number;
  readonly title: string;
  readonly type: string;
  readonly detail: string | undefined;
  readonly requestId: string | undefined;
  readonly errors: Problem["errors"];

  constructor(problem: Problem) {
    super(problem.detail ?? problem.title);
    this.name = "ApiError";
    this.status = problem.status;
    this.title = problem.title;
    this.type = problem.type ?? "about:blank";
    this.detail = problem.detail ?? undefined;
    this.requestId = problem.request_id ?? undefined;
    this.errors = problem.errors;
  }
}

function isProblem(value: unknown): value is Problem {
  return (
    typeof value === "object" &&
    value !== null &&
    typeof (value as Problem).status === "number" &&
    typeof (value as Problem).title === "string"
  );
}

/** Turn any error response into an ApiError, even when the body is not problem+json. */
export async function toApiError(response: Response): Promise<ApiError> {
  let body: unknown;
  try {
    body = await response.clone().json();
  } catch {
    body = undefined;
  }
  if (isProblem(body)) return new ApiError(body);
  return new ApiError({
    type: "about:blank",
    title: response.statusText || "Error",
    status: response.status,
    detail: undefined,
    request_id: response.headers.get("X-Request-ID") ?? undefined,
  });
}

function newRequestId(): string {
  return globalThis.crypto.randomUUID();
}

export type GetAccessToken = () => string | null | undefined | Promise<string | null | undefined>;

/**
 * Typed client for the SterileGuard API. Adds the bearer token and a fresh X-Request-ID to
 * every request, and throws ApiError for any non-2xx response.
 */
export function createApiClient(baseUrl: string, getAccessToken?: GetAccessToken) {
  const client = createClient<paths>({ baseUrl });
  const middleware: Middleware = {
    async onRequest({ request }) {
      request.headers.set("X-Request-ID", newRequestId());
      const token = await getAccessToken?.();
      if (token) request.headers.set("Authorization", `Bearer ${token}`);
      return request;
    },
    async onResponse({ response }) {
      if (!response.ok) throw await toApiError(response);
      return response;
    },
  };
  client.use(middleware);
  return client;
}

export type ApiClient = ReturnType<typeof createApiClient>;

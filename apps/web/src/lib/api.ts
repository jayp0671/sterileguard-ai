import { createApiClient, type GetAccessToken } from "@sg/contracts";
import { env } from "@/lib/env";

/** The only way the web app talks to the API: typed from the generated OpenAPI contract. */
export function api(getAccessToken?: GetAccessToken) {
  return createApiClient(env.apiUrl, getAccessToken);
}

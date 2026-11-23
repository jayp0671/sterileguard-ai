"use client";

import { type components, createApiClient } from "@sg/contracts";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { accessToken } from "@/hooks/use-me";
import { retryNetworkOnly } from "@/hooks/use-plan";
import { api } from "@/lib/api";
import { env } from "@/lib/env";

export type Performance = components["schemas"]["Performance"];
export type ModelCardView = components["schemas"]["ModelCardView"];
export type LiveMetrics = components["schemas"]["LiveMetrics"];

export const performanceKey = (departmentId: string | undefined, window: number) =>
  ["model-performance", departmentId, window] as const;

export function usePerformance(departmentId: string | undefined, window = 30) {
  return useQuery({
    queryKey: performanceKey(departmentId, window),
    enabled: Boolean(departmentId),
    retry: retryNetworkOnly,
    queryFn: async (): Promise<Performance> => {
      const { data } = await api(accessToken).GET("/v1/models/performance", {
        params: { query: { department_id: departmentId ?? "", window } },
      });
      if (!data) throw new Error("empty performance response");
      return data;
    },
  });
}

/** Activate or roll back with the fresh token from the re-auth dialog (TOTP < 5 minutes). */
export function useRegistryAction() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({
      action,
      version,
      featureSet,
      freshToken,
    }: {
      action: "activate" | "rollback";
      version?: string;
      featureSet: "full" | "core";
      freshToken: string;
    }) => {
      const client = createApiClient(env.apiUrl, async () => freshToken);
      if (action === "activate") {
        const { data } = await client.POST("/v1/models/{version}/activate", {
          params: { path: { version: version ?? "" } },
        });
        return data;
      }
      const { data } = await client.POST("/v1/models/rollback", {
        body: { feature_set: featureSet },
      });
      return data;
    },
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["model-performance"] }),
  });
}

/** "Covered 11 of 14 real days (79%); target 80%." */
export function coverageText(live: LiveMetrics): string {
  if (!live.days || live.coverage_80 === null || live.coverage_80 === undefined) return "";
  const inside = Math.round(live.coverage_80 * live.days);
  const pct = Math.round(live.coverage_80 * 100);
  return `The 80% range covered ${inside} of ${live.days} real days (${pct}%); target ${Math.round(
    (live.coverage_target ?? 0.8) * 100,
  )}%.`;
}

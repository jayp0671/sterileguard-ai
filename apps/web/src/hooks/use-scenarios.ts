"use client";

import { ApiError, type components } from "@sg/contracts";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { forecastKey } from "@/hooks/use-forecast";
import { accessToken } from "@/hooks/use-me";
import { planKey, retryNetworkOnly } from "@/hooks/use-plan";
import { api } from "@/lib/api";

export type ScenarioOut = components["schemas"]["ScenarioOut"];
export type OptionOut = components["schemas"]["OptionOut"];
export type AppliedOut = components["schemas"]["AppliedOut"];

export const scenarioKey = (departmentId: string | undefined, date: string) =>
  ["scenario", "latest", departmentId, date] as const;

/** The latest run for a date; `null` when none exists yet (404). */
export function useLatestScenario(departmentId: string | undefined, date: string) {
  return useQuery({
    queryKey: scenarioKey(departmentId, date),
    enabled: Boolean(departmentId),
    retry: retryNetworkOnly,
    queryFn: async (): Promise<ScenarioOut | null> => {
      try {
        const { data } = await api(accessToken).GET("/v1/scenarios/latest", {
          params: { query: { department_id: departmentId ?? "", target_date: date } },
        });
        return data ?? null;
      } catch (err) {
        if (err instanceof ApiError && err.status === 404) return null;
        throw err;
      }
    },
  });
}

/** POST /v1/scenarios with the default bounds and target. */
export function useRunScenario() {
  const qc = useQueryClient();
  return useMutation({
    retry: retryNetworkOnly,
    mutationFn: async ({ departmentId, date }: { departmentId: string; date: string }) => {
      const { data } = await api(accessToken).POST("/v1/scenarios", {
        body: { department_id: departmentId, target_date: date },
      });
      if (!data) throw new Error("empty scenario response");
      return data;
    },
    onSuccess: (scenario, { departmentId, date }) => {
      qc.setQueryData(scenarioKey(departmentId, date), scenario);
    },
  });
}

/** Apply an option: the plan changes and the forecast is recomputed. */
export function useApplyScenario() {
  const qc = useQueryClient();
  return useMutation({
    retry: retryNetworkOnly,
    mutationFn: async ({
      departmentId,
      scenarioId,
      optionId,
    }: {
      departmentId: string;
      date: string;
      scenarioId: string;
      optionId: string;
    }) => {
      const { data } = await api(accessToken).POST("/v1/scenarios/{scenario_id}/apply", {
        params: { path: { scenario_id: scenarioId } },
        body: { department_id: departmentId, option_id: optionId },
      });
      if (!data) throw new Error("empty apply response");
      return data;
    },
    onSuccess: (applied, { departmentId, date }) => {
      qc.setQueryData(scenarioKey(departmentId, date), applied.scenario);
      qc.setQueryData(forecastKey(departmentId), applied.forecast);
      void qc.invalidateQueries({ queryKey: planKey(departmentId, date) });
      void qc.invalidateQueries({ queryKey: ["forecast", "history", departmentId] });
    },
  });
}

"use client";

import { ApiError, type components } from "@sg/contracts";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { accessToken } from "@/hooks/use-me";
import { retryNetworkOnly } from "@/hooks/use-plan";
import { api } from "@/lib/api";

export type ForecastOut = components["schemas"]["ForecastOut"];
export type DriverOut = components["schemas"]["DriverOut"];
export type HistoryPoint = components["schemas"]["HistoryPoint"];

export const forecastKey = (departmentId: string | undefined) =>
  ["forecast", "next-day", departmentId] as const;
export const historyKey = (departmentId: string | undefined, days: number) =>
  ["forecast", "history", departmentId, days] as const;

/** Latest forecast for the next workday; `null` when none has been computed yet (404). */
export function useNextDayForecast(departmentId: string | undefined) {
  return useQuery({
    queryKey: forecastKey(departmentId),
    enabled: Boolean(departmentId),
    retry: retryNetworkOnly,
    queryFn: async (): Promise<ForecastOut | null> => {
      try {
        const { data } = await api(accessToken).GET("/v1/forecasts/next-day", {
          params: { query: { department_id: departmentId ?? "" } },
        });
        return data ?? null;
      } catch (err) {
        if (err instanceof ApiError && err.status === 404) return null;
        throw err;
      }
    },
  });
}

export function useForecastHistory(departmentId: string | undefined, days = 14) {
  return useQuery({
    queryKey: historyKey(departmentId, days),
    enabled: Boolean(departmentId),
    retry: retryNetworkOnly,
    queryFn: async (): Promise<HistoryPoint[]> => {
      const { data } = await api(accessToken).GET("/v1/forecasts/history", {
        params: { query: { department_id: departmentId ?? "", days } },
      });
      return data ?? [];
    },
  });
}

/** POST /v1/forecasts for a date; the new forecast replaces the cached next-day one. */
export function useComputeForecast() {
  const qc = useQueryClient();
  return useMutation({
    retry: retryNetworkOnly,
    mutationFn: async ({ departmentId, date }: { departmentId: string; date: string }) => {
      const { data } = await api(accessToken).POST("/v1/forecasts", {
        body: { department_id: departmentId, target_date: date },
      });
      if (!data) throw new Error("empty forecast response");
      return data;
    },
    onSuccess: (forecast, { departmentId }) => {
      qc.setQueryData(forecastKey(departmentId), forecast);
      void qc.invalidateQueries({ queryKey: ["forecast", "history", departmentId] });
    },
  });
}

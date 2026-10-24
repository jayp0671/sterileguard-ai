"use client";

import { ApiError, type components } from "@sg/contracts";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { accessToken } from "@/hooks/use-me";
import { api } from "@/lib/api";

export type PlanOut = components["schemas"]["PlanOut"];
export type PlanPut = components["schemas"]["PlanPut"];

/** Retry only network failures; an ApiError is the server's answer and retrying won't help. */
export function retryNetworkOnly(count: number, error: unknown): boolean {
  return count < 2 && !(error instanceof ApiError);
}

export const planKey = (departmentId: string | undefined, date: string) =>
  ["plan", departmentId, date] as const;

export function usePlan(departmentId: string | undefined, date: string) {
  return useQuery({
    queryKey: planKey(departmentId, date),
    enabled: Boolean(departmentId && date),
    retry: retryNetworkOnly,
    queryFn: async (): Promise<PlanOut> => {
      const { data } = await api(accessToken).GET("/v1/plans/{plan_date}", {
        params: { path: { plan_date: date }, query: { department_id: departmentId ?? "" } },
      });
      if (!data) throw new Error("empty plan response");
      return data;
    },
  });
}

export type SavePlanArgs = {
  departmentId: string;
  date: string;
  body: PlanPut;
  /** Same key for retries of the same save, new key for a new save. */
  idempotencyKey: string;
};

export function useSavePlan() {
  const qc = useQueryClient();
  return useMutation({
    retry: retryNetworkOnly,
    mutationFn: async ({ departmentId, date, body, idempotencyKey }: SavePlanArgs) => {
      const { data } = await api(accessToken).PUT("/v1/plans/{plan_date}", {
        params: { path: { plan_date: date }, query: { department_id: departmentId } },
        body,
        headers: { "Idempotency-Key": idempotencyKey },
      });
      if (!data) throw new Error("empty plan response");
      return data;
    },
    onSuccess: (plan, { departmentId, date }) => {
      qc.setQueryData(planKey(departmentId, date), plan);
    },
  });
}

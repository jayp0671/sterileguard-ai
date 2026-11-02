"use client";

import { type components, createApiClient } from "@sg/contracts";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { accessToken } from "@/hooks/use-me";
import { retryNetworkOnly } from "@/hooks/use-plan";
import { api } from "@/lib/api";
import { env } from "@/lib/env";

export type ShiftOut = components["schemas"]["ShiftOut"];
export type ShiftDetail = components["schemas"]["ShiftDetail"];
export type ShiftPage = components["schemas"]["ShiftPage"];
export type ShiftStatus = ShiftOut["status"];
export type ShiftFields = Omit<
  components["schemas"]["ShiftCreate"],
  "department_id" | "shift_date"
>;

export type ShiftFilters = { status?: ShiftStatus; from?: string; to?: string };

export const shiftsKey = (departmentId: string | undefined, filters: ShiftFilters = {}) =>
  ["shifts", departmentId, filters] as const;

const PAGE = 100;

/** Every row matching the filters (pages of 100, newest first). */
export function useShifts(departmentId: string | undefined, filters: ShiftFilters) {
  return useQuery({
    queryKey: shiftsKey(departmentId, filters),
    enabled: Boolean(departmentId),
    retry: retryNetworkOnly,
    queryFn: async (): Promise<ShiftOut[]> => {
      const out: ShiftOut[] = [];
      let offset: number | null | undefined = 0;
      while (offset !== null && offset !== undefined) {
        const { data }: { data?: ShiftPage } = await api(accessToken).GET("/v1/shifts", {
          params: {
            query: { department_id: departmentId ?? "", limit: PAGE, offset, ...filters },
          },
        });
        out.push(...(data?.items ?? []));
        offset = data?.next_offset;
      }
      return out;
    },
  });
}

export function useShift(departmentId: string | undefined, id: string | null) {
  return useQuery({
    queryKey: ["shift", departmentId, id],
    enabled: Boolean(departmentId && id),
    retry: retryNetworkOnly,
    queryFn: async (): Promise<ShiftDetail> => {
      const { data } = await api(accessToken).GET("/v1/shifts/{shift_id}", {
        params: { path: { shift_id: id ?? "" }, query: { department_id: departmentId ?? "" } },
      });
      if (!data) throw new Error("empty shift response");
      return data;
    },
  });
}

function useInvalidate(departmentId: string) {
  const qc = useQueryClient();
  return () => {
    void qc.invalidateQueries({ queryKey: ["shifts", departmentId] });
    void qc.invalidateQueries({ queryKey: ["shift", departmentId] });
    void qc.invalidateQueries({ queryKey: ["forecast", "history", departmentId] });
  };
}

/** Create the server draft (POST) or update it (PATCH). */
export function useSaveShift(departmentId: string) {
  const invalidate = useInvalidate(departmentId);
  return useMutation({
    mutationFn: async ({
      id,
      shiftDate,
      fields,
      plan,
    }: {
      id: string | null;
      shiftDate: string;
      fields: ShiftFields;
      plan?: Record<string, unknown> | null;
    }): Promise<ShiftOut> => {
      if (id) {
        const { data } = await api(accessToken).PATCH("/v1/shifts/{shift_id}", {
          params: { path: { shift_id: id } },
          body: { department_id: departmentId, ...fields },
        });
        if (!data) throw new Error("empty shift response");
        return data;
      }
      const { data } = await api(accessToken).POST("/v1/shifts", {
        body: {
          department_id: departmentId,
          shift_date: shiftDate,
          ...fields,
          plan: (plan ?? null) as components["schemas"]["ShiftCreate"]["plan"],
        },
      });
      if (!data) throw new Error("empty shift response");
      return data;
    },
    onSuccess: invalidate,
  });
}

export type Transition = "submit" | "approve" | "reopen";

export function useTransition(departmentId: string) {
  const invalidate = useInvalidate(departmentId);
  return useMutation({
    retry: retryNetworkOnly,
    mutationFn: async ({
      id,
      action,
      reason,
    }: {
      id: string;
      action: Transition;
      reason?: string;
    }): Promise<ShiftOut> => {
      const client = api(accessToken);
      const path = { params: { path: { shift_id: id } } };
      const body = { department_id: departmentId };
      const { data } =
        action === "submit"
          ? await client.POST("/v1/shifts/{shift_id}/submit", { ...path, body })
          : action === "approve"
            ? await client.POST("/v1/shifts/{shift_id}/approve", { ...path, body })
            : await client.POST("/v1/shifts/{shift_id}/reopen", {
                ...path,
                body: { ...body, reason: reason ?? "" },
              });
      if (!data) throw new Error("empty shift response");
      return data;
    },
    onSuccess: invalidate,
  });
}

/** CSV export with the token from a fresh two-factor check (the API refuses older ones). */
export async function exportShiftsCsv(
  departmentId: string,
  from: string,
  to: string,
  freshToken: string,
): Promise<Blob> {
  const { response } = await createApiClient(env.apiUrl, async () => freshToken).GET(
    "/v1/shifts/export",
    {
      params: { query: { department_id: departmentId, from, to } },
      parseAs: "blob",
    },
  );
  return response.blob();
}

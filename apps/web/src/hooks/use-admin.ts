"use client";

import { type components, createApiClient } from "@sg/contracts";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { accessToken } from "@/hooks/use-me";
import { retryNetworkOnly } from "@/hooks/use-plan";
import { api } from "@/lib/api";
import { env } from "@/lib/env";

export type Member = components["schemas"]["Member"];
export type InviteRow = components["schemas"]["InviteRow"];
export type DepartmentSettings = components["schemas"]["DepartmentSettings"];
export type AuditRow = components["schemas"]["AuditRow"];
export type AuditPage = components["schemas"]["AuditPage"];
export type Role = Member["roles"][number];
export type AuditFilters = {
  from?: string;
  to?: string;
  actor?: string;
  action?: "insert" | "update" | "delete";
  entity?: string;
};

/** A client that sends the fresh token from the re-auth dialog (TOTP < 5 minutes). */
const fresh = (token: string) => createApiClient(env.apiUrl, async () => token);

export function useMembers(dept: string) {
  return useQuery({
    queryKey: ["admin", "members", dept],
    retry: retryNetworkOnly,
    queryFn: async (): Promise<Member[]> => {
      const { data } = await api(accessToken).GET("/v1/admin/members", {
        params: { query: { department_id: dept } },
      });
      return data ?? [];
    },
  });
}

export function useInvites(dept: string) {
  return useQuery({
    queryKey: ["admin", "invites", dept],
    retry: retryNetworkOnly,
    queryFn: async (): Promise<InviteRow[]> => {
      const { data } = await api(accessToken).GET("/v1/admin/invites", {
        params: { query: { department_id: dept } },
      });
      return data ?? [];
    },
  });
}

export function useAdminMutations(dept: string) {
  const qc = useQueryClient();
  const refresh = () => void qc.invalidateQueries({ queryKey: ["admin"] });
  return {
    setRoles: useMutation({
      mutationFn: async (v: { userId: string; roles: Role[]; token: string }) =>
        fresh(v.token).PUT("/v1/admin/members/{user_id}/roles", {
          params: { path: { user_id: v.userId } },
          body: { department_id: dept, roles: v.roles },
        }),
      onSuccess: refresh,
    }),
    remove: useMutation({
      mutationFn: async (v: { userId: string; token: string }) =>
        fresh(v.token).DELETE("/v1/admin/members/{user_id}", {
          params: { path: { user_id: v.userId }, query: { department_id: dept } },
        }),
      onSuccess: refresh,
    }),
    resetMfa: useMutation({
      mutationFn: async (v: { userId: string; token: string }) => {
        const { data } = await fresh(v.token).POST("/v1/admin/members/{user_id}/mfa-reset", {
          params: { path: { user_id: v.userId } },
          body: { department_id: dept },
        });
        return data;
      },
      onSuccess: refresh,
    }),
    invite: useMutation({
      mutationFn: async (v: { email: string; role: Role }) =>
        api(accessToken).POST("/v1/admin/invites", {
          body: { email: v.email, role: v.role, department_id: dept },
        }),
      onSuccess: refresh,
    }),
    resend: useMutation({
      mutationFn: async (id: string) =>
        api(accessToken).POST("/v1/admin/invites/{invite_id}/resend", {
          params: { path: { invite_id: id } },
        }),
      onSuccess: refresh,
    }),
    revoke: useMutation({
      mutationFn: async (id: string) =>
        api(accessToken).POST("/v1/admin/invites/{invite_id}/revoke", {
          params: { path: { invite_id: id } },
        }),
      onSuccess: refresh,
    }),
  };
}

export function useDeptSettings(dept: string) {
  return useQuery({
    queryKey: ["admin", "settings", dept],
    retry: retryNetworkOnly,
    queryFn: async (): Promise<DepartmentSettings> => {
      const { data } = await api(accessToken).GET("/v1/admin/settings", {
        params: { query: { department_id: dept } },
      });
      if (!data) throw new Error("empty settings");
      return data;
    },
  });
}

export function useSaveSettings(dept: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (settings: DepartmentSettings) => {
      const { data } = await api(accessToken).PUT("/v1/admin/settings", {
        body: { department_id: dept, settings },
      });
      return data;
    },
    onSuccess: (data) => qc.setQueryData(["admin", "settings", dept], data),
  });
}

export function useAudit(dept: string, filters: AuditFilters, beforeId: number | null) {
  return useQuery({
    queryKey: ["admin", "audit", dept, filters, beforeId],
    retry: retryNetworkOnly,
    queryFn: async (): Promise<AuditPage> => {
      const { data } = await api(accessToken).GET("/v1/admin/audit", {
        params: {
          query: {
            department_id: dept,
            limit: 50,
            ...filters,
            ...(beforeId ? { before_id: beforeId } : {}),
          },
        },
      });
      return data ?? { items: [], next_cursor: null };
    },
  });
}

export async function exportAudit(
  dept: string,
  filters: AuditFilters,
  token: string,
): Promise<Blob> {
  const { response } = await fresh(token).GET("/v1/admin/audit/export.csv", {
    params: { query: { department_id: dept, ...filters } },
    parseAs: "blob",
  });
  return response.blob();
}

/** Keys whose value changed between before and after (for the detail drawer). */
export function diffKeys(
  before: Record<string, unknown> | null | undefined,
  after: Record<string, unknown> | null | undefined,
) {
  const keys = new Set([...Object.keys(before ?? {}), ...Object.keys(after ?? {})]);
  return [...keys].filter((k) => JSON.stringify(before?.[k]) !== JSON.stringify(after?.[k])).sort();
}

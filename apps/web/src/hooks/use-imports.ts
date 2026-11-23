"use client";

import { type components, toApiError } from "@sg/contracts";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { accessToken } from "@/hooks/use-me";
import { retryNetworkOnly } from "@/hooks/use-plan";
import { api } from "@/lib/api";
import { env } from "@/lib/env";

export type ImportJob = components["schemas"]["ImportJob"];
export type ImportSummary = components["schemas"]["ImportSummary"];
export type ImportColumn = components["schemas"]["ImportColumn"];
export type FieldOption = components["schemas"]["FieldOption"];
export type CommitOut = components["schemas"]["CommitOut"];

export const MAX_UPLOAD_BYTES = 10 * 1024 * 1024;
export const ACCEPTED = [".csv", ".xlsx", ".xls"] as const;
const PROCESSING = new Set(["uploaded", "parsed", "mapped"]);

/** Client-side type and size check; the API checks magic bytes again. */
export function checkUpload(file: File): string | null {
  const name = file.name.toLowerCase();
  if (!ACCEPTED.some((ext) => name.endsWith(ext))) return "Use a .csv, .xlsx or .xls file.";
  if (file.size === 0) return "This file is empty.";
  if (file.size > MAX_UPLOAD_BYTES) return "This file is larger than 10 MB.";
  return null;
}

export function useImportHistory(departmentId: string | undefined) {
  return useQuery({
    queryKey: ["imports", departmentId],
    enabled: Boolean(departmentId),
    retry: retryNetworkOnly,
    queryFn: async (): Promise<ImportSummary[]> => {
      const { data } = await api(accessToken).GET("/v1/imports", {
        params: { query: { department_id: departmentId ?? "" } },
      });
      return data ?? [];
    },
  });
}

/** One job; polls every 2 seconds while the file is still being processed. */
export function useImportJob(departmentId: string | undefined, id: string | null) {
  return useQuery({
    queryKey: ["import", departmentId, id],
    enabled: Boolean(departmentId && id),
    retry: retryNetworkOnly,
    refetchInterval: (q) => (q.state.data && PROCESSING.has(q.state.data.status) ? 2000 : false),
    queryFn: async (): Promise<ImportJob> => {
      const { data } = await api(accessToken).GET("/v1/imports/{job_id}", {
        params: { path: { job_id: id ?? "" }, query: { department_id: departmentId ?? "" } },
      });
      if (!data) throw new Error("empty import response");
      return data;
    },
  });
}

export function useImportFields(departmentId: string | undefined) {
  return useQuery({
    queryKey: ["import-fields", departmentId],
    enabled: Boolean(departmentId),
    staleTime: Number.POSITIVE_INFINITY,
    queryFn: async (): Promise<FieldOption[]> => {
      const { data } = await api(accessToken).GET("/v1/imports/fields", {
        params: { query: { department_id: departmentId ?? "" } },
      });
      return data ?? [];
    },
  });
}

/** Multipart upload with progress (XMLHttpRequest reports upload progress; fetch does not). */
export async function uploadImport(
  departmentId: string,
  file: File,
  onProgress: (fraction: number) => void,
): Promise<ImportJob> {
  const token = await accessToken();
  const form = new FormData();
  form.append("file", file, file.name);
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    const url = `${env.apiUrl}/v1/imports?department_id=${encodeURIComponent(departmentId)}`;
    xhr.open("POST", url);
    if (token) xhr.setRequestHeader("Authorization", `Bearer ${token}`);
    xhr.setRequestHeader("X-Request-ID", globalThis.crypto.randomUUID());
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) onProgress(e.loaded / e.total);
    };
    xhr.onerror = () => reject(new Error("The upload failed. Check your connection."));
    xhr.onload = async () => {
      const response = new Response(xhr.responseText, {
        status: xhr.status,
        headers: { "Content-Type": xhr.getResponseHeader("Content-Type") ?? "application/json" },
      });
      if (xhr.status >= 400) return reject(await toApiError(response));
      resolve((await response.json()) as ImportJob);
    };
    xhr.send(form);
  });
}

function useRefresh(departmentId: string) {
  const qc = useQueryClient();
  return (job?: { id: string }) => {
    void qc.invalidateQueries({ queryKey: ["imports", departmentId] });
    if (job) void qc.invalidateQueries({ queryKey: ["import", departmentId, job.id] });
  };
}

export function useRemap(departmentId: string, jobId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (mapping: Record<string, string | null>): Promise<ImportJob> => {
      const { data } = await api(accessToken).PATCH("/v1/imports/{job_id}/mapping", {
        params: { path: { job_id: jobId } },
        body: { department_id: departmentId, mapping },
      });
      if (!data) throw new Error("empty response");
      return data;
    },
    onSuccess: (job) => qc.setQueryData(["import", departmentId, jobId], job),
  });
}

export function useCommitImport(departmentId: string, jobId: string) {
  const refresh = useRefresh(departmentId);
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (overwrite: boolean): Promise<CommitOut> => {
      const { data } = await api(accessToken).POST("/v1/imports/{job_id}/commit", {
        params: { path: { job_id: jobId } },
        body: { department_id: departmentId, overwrite },
      });
      if (!data) throw new Error("empty response");
      return data;
    },
    onSuccess: () => {
      refresh({ id: jobId });
      void qc.invalidateQueries({ queryKey: ["shifts", departmentId] });
    },
  });
}

export function useCancelImport(departmentId: string, jobId: string) {
  const refresh = useRefresh(departmentId);
  return useMutation({
    mutationFn: async () => {
      await api(accessToken).POST("/v1/imports/{job_id}/cancel", {
        params: { path: { job_id: jobId } },
        body: { department_id: departmentId },
      });
    },
    onSuccess: () => refresh({ id: jobId }),
  });
}

export function useSaveTemplate(departmentId: string, jobId: string) {
  return useMutation({
    mutationFn: async () => {
      await api(accessToken).POST("/v1/imports/{job_id}/template", {
        params: { path: { job_id: jobId } },
        body: { department_id: departmentId },
      });
    },
  });
}

export async function downloadRejected(departmentId: string, jobId: string): Promise<Blob> {
  const { response } = await api(accessToken).GET("/v1/imports/{job_id}/rejected.csv", {
    params: { path: { job_id: jobId }, query: { department_id: departmentId } },
    parseAs: "blob",
  });
  if (!response.ok) throw await toApiError(response);
  return response.blob();
}

/** "2 columns were removed because they looked like names or IDs. 3 cells were blocked." */
export function phiBannerText(phi: ImportJob["phi"]): string | null {
  const parts: string[] = [];
  if (phi.columns_removed > 0) {
    const n = phi.columns_removed;
    parts.push(
      `${n} ${n === 1 ? "column was" : "columns were"} removed because ${
        n === 1 ? "it" : "they"
      } looked like names or IDs.`,
    );
  }
  if (phi.cells_blocked > 0) {
    const n = phi.cells_blocked;
    parts.push(`${n} ${n === 1 ? "cell was" : "cells were"} blocked.`);
  }
  return parts.length ? parts.join(" ") : null;
}

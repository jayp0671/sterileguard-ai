"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";

/** Liveness of the API (the free Hugging Face Space sleeps when idle). */
export function useApiHealth() {
  return useQuery({
    queryKey: ["health"],
    queryFn: async () => {
      const { data } = await api().GET("/health");
      if (!data) throw new Error("empty health response");
      return data;
    },
    staleTime: 30_000,
  });
}

"use client";

import type { components } from "@sg/contracts";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { createClient } from "@/lib/supabase/client";

export type Me = components["schemas"]["Me"];

export async function accessToken(): Promise<string | undefined> {
  const { data } = await createClient().auth.getSession();
  return data.session?.access_token;
}

/** GET /v1/me: the caller, their departments and roles. Drives the sidebar and switcher. */
export function useMe() {
  return useQuery({
    queryKey: ["me"],
    queryFn: async (): Promise<Me> => {
      const { data } = await api(accessToken).GET("/v1/me");
      if (!data) throw new Error("empty /v1/me response");
      return data;
    },
    staleTime: 60_000,
    retry: (count, err) => count < 2 && !(err instanceof Error && "status" in err),
  });
}

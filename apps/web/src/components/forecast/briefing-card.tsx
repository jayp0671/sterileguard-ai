"use client";

import type { components } from "@sg/contracts";
import { useQuery } from "@tanstack/react-query";
import { Info, Sparkles } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { accessToken } from "@/hooks/use-me";
import { api } from "@/lib/api";

export type BriefingOut = components["schemas"]["BriefingOut"];

export function useBriefing(departmentId: string, forecastId: string, locale: "en" | "es" = "en") {
  return useQuery({
    queryKey: ["briefing", departmentId, forecastId, locale],
    staleTime: Number.POSITIVE_INFINITY,
    retry: false,
    queryFn: async (): Promise<BriefingOut> => {
      const { data } = await api(accessToken).POST("/v1/agents/briefing", {
        body: { department_id: departmentId, forecast_id: forecastId, locale },
      });
      if (!data) throw new Error("empty briefing");
      return data;
    },
  });
}

/** The evening briefing (SG-23). Labeled "AI-generated summary" only when the LLM wrote it. */
export function BriefingCard({
  departmentId,
  forecastId,
}: {
  departmentId: string;
  forecastId: string;
}) {
  const q = useBriefing(departmentId, forecastId);
  if (q.isPending) return <Skeleton className="h-28" aria-label="Loading the summary" />;
  if (q.isError || !q.data) return null; // the page works without it
  return <BriefingView briefing={q.data} />;
}

export function BriefingView({ briefing }: { briefing: BriefingOut }) {
  const ai = briefing.source === "llm";
  return (
    <section
      aria-labelledby="briefing-heading"
      className="flex flex-col gap-2 rounded-lg border bg-card p-4"
    >
      <div className="flex items-center gap-2">
        {ai ? <Sparkles className="size-4 text-muted-foreground" aria-hidden /> : null}
        <h2 id="briefing-heading" className="engraved">
          {ai ? "AI-generated summary" : "Summary"}
        </h2>
        <TooltipProvider>
          <Tooltip>
            <TooltipTrigger asChild>
              <button
                type="button"
                className="ml-auto inline-flex size-8 items-center justify-center rounded-md hover:bg-accent"
                aria-label="What does the AI do here?"
              >
                <Info className="size-4" aria-hidden />
              </button>
            </TooltipTrigger>
            <TooltipContent className="max-w-xs">
              {ai
                ? briefing.ai_note
                : "Written from a fixed template using the forecast numbers. No AI was used for this summary."}
            </TooltipContent>
          </Tooltip>
        </TooltipProvider>
      </div>
      <p className="text-sm leading-relaxed">{briefing.text}</p>
      <p className="engraved">{briefing.disclaimer}</p>
    </section>
  );
}

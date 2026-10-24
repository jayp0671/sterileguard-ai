"use client";

import { BarChart3, Table2 } from "lucide-react";
import { type ReactNode, useId, useState } from "react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

/**
 * Every chart gets a title, a one-sentence description and a "View as table" toggle, so the
 * data always has an accessible alternative.
 */
export function ChartFrame({
  title,
  description,
  columns,
  rows,
  children,
  className,
}: {
  title: string;
  description: string;
  columns: string[];
  rows: (string | number)[][];
  children: ReactNode;
  className?: string;
}) {
  const [asTable, setAsTable] = useState(false);
  const descId = useId();
  return (
    <figure
      aria-describedby={descId}
      className={cn("flex flex-col gap-3 rounded-lg border bg-card p-4", className)}
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <figcaption className="font-medium">{title}</figcaption>
          <p id={descId} className="text-13 text-muted-foreground">
            {description}
          </p>
        </div>
        <Button
          variant="ghost"
          size="sm"
          className="min-h-11 shrink-0"
          aria-pressed={asTable}
          onClick={() => setAsTable((v) => !v)}
        >
          {asTable ? <BarChart3 aria-hidden /> : <Table2 aria-hidden />}
          {asTable ? "View as chart" : "View as table"}
        </Button>
      </div>
      {asTable ? (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <caption className="sr-only">{title}</caption>
            <thead>
              <tr className="border-b">
                {columns.map((c) => (
                  <th key={c} scope="col" className="engraved px-2 py-2 text-start">
                    {c}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.join("|")} className="border-b last:border-0">
                  {r.map((v, i) => (
                    <td
                      key={columns[i] ?? i}
                      className={cn("px-2 py-2", typeof v === "number" && "tabular text-end")}
                    >
                      {v}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        children
      )}
    </figure>
  );
}

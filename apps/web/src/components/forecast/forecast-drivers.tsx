"use client";

import { HelpCircle } from "lucide-react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { type Driver, DriverList } from "@/components/driver-list";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import type { DriverOut } from "@/hooks/use-forecast";

/** API drivers -> translated sentences (drivers.<feature>.<pos|neg>), default English fallback. */
export function useDriverSentences(drivers: DriverOut[]): Driver[] {
  const t = useTranslations("drivers");
  return drivers.map((d) => {
    const key = d.text_key.replace(/^drivers\./, "");
    const params = d.text_params as Record<string, string | number>;
    return {
      sentence: t.has(key) ? t(key, params) : d.default_text,
      hours: d.contribution_hours,
    };
  });
}

/** Top drivers of tomorrow's estimate, the "other factors" remainder last. */
export function ForecastDrivers({ drivers }: { drivers: DriverOut[] }) {
  const sentences = useDriverSentences(drivers);
  return (
    <section aria-labelledby="drivers-heading" className="flex flex-col gap-3">
      <div className="flex items-end justify-between gap-3">
        <div>
          <h2 id="drivers-heading" className="engraved">
            What is driving tomorrow
          </h2>
          <p className="text-13 text-muted-foreground">
            Hours each factor adds to or removes from the estimate.
          </p>
        </div>
        <WhyDrawer />
      </div>
      <DriverList drivers={sentences} />
    </section>
  );
}

export function WhyDrawer() {
  return (
    <Sheet>
      <SheetTrigger asChild>
        <Button variant="ghost" size="sm" className="min-h-11 shrink-0">
          <HelpCircle aria-hidden />
          Why these factors?
        </Button>
      </SheetTrigger>
      <SheetContent side="right" className="flex flex-col gap-4">
        <SheetHeader>
          <SheetTitle>Why these factors?</SheetTitle>
          <SheetDescription>How the drivers are calculated</SheetDescription>
        </SheetHeader>
        <div className="flex flex-col gap-3 px-4 text-sm">
          <p>
            Each factor shows how many hours it moves tomorrow&apos;s estimate up or down compared
            with a typical day in the training data. The factors and the typical day add up to the
            estimate exactly.
          </p>
          <p>
            These are explanations of the model, not causes: the model learned them from simulated
            days and checks them against real days as they are logged.
          </p>
          <Link href="/app/model" className="font-medium text-primary underline">
            Model performance
          </Link>
        </div>
      </SheetContent>
    </Sheet>
  );
}

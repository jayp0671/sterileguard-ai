"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { maybeLoadAnalytics } from "@/lib/analytics";
import { api } from "@/lib/api";
import {
  anonId,
  CONSENT_VERSION,
  currentConsent,
  gpcEnabled,
  OPEN_SETTINGS_EVENT,
  writeConsent,
} from "@/lib/consent";

async function log(analytics: boolean) {
  try {
    await api().POST("/v1/consents", {
      body: { anon_id: anonId(), version: CONSENT_VERSION, analytics, gpc: gpcEnabled() },
    });
  } catch {
    // The choice is stored in the cookie either way; logging is best effort.
  }
}

/** First-visit banner and preference center. "Essential only" is the default. */
export function CookieBanner() {
  const [show, setShow] = useState(false);
  const [prefs, setPrefs] = useState(false);
  const [analytics, setAnalytics] = useState(false);
  const gpc = typeof navigator !== "undefined" && gpcEnabled();

  useEffect(() => {
    const existing = currentConsent();
    if (existing) {
      setAnalytics(existing.analytics);
      maybeLoadAnalytics();
    } else if (gpcEnabled()) {
      // Global Privacy Control is an opt-out: record essential only, no banner needed.
      writeConsent(false);
      void log(false);
    } else {
      setShow(true);
    }
    const open = () => {
      setAnalytics(Boolean(currentConsent()?.analytics));
      setPrefs(true);
    };
    window.addEventListener(OPEN_SETTINGS_EVENT, open);
    return () => window.removeEventListener(OPEN_SETTINGS_EVENT, open);
  }, []);

  function choose(value: boolean) {
    const saved = writeConsent(value);
    setAnalytics(saved.analytics);
    setShow(false);
    setPrefs(false);
    void log(saved.analytics);
    if (saved.analytics) maybeLoadAnalytics();
  }

  return (
    <>
      {show ? (
        <section
          aria-label="Cookie choices"
          className="fixed inset-x-0 bottom-0 z-50 border-t bg-background/95 p-4 shadow-lg backdrop-blur"
        >
          <div className="mx-auto flex max-w-5xl flex-col gap-3 sm:flex-row sm:items-center">
            <p className="flex-1 text-sm">
              We use essential cookies to keep you signed in. Optional analytics stay off unless you
              accept them. See the{" "}
              <a href="/trust/cookies" className="underline underline-offset-4">
                Cookie Policy
              </a>
              .
            </p>
            <div className="flex flex-wrap gap-2">
              <Button className="min-h-11" onClick={() => choose(false)}>
                Essential only
              </Button>
              <Button variant="outline" className="min-h-11" onClick={() => choose(true)}>
                Accept analytics
              </Button>
              <Button variant="ghost" className="min-h-11" onClick={() => setPrefs(true)}>
                Preferences
              </Button>
            </div>
          </div>
        </section>
      ) : null}
      <Dialog open={prefs} onOpenChange={setPrefs}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Cookie settings</DialogTitle>
            <DialogDescription>
              Choices are saved for this browser and logged with the policy version.
            </DialogDescription>
          </DialogHeader>
          <div className="flex flex-col gap-3 text-sm">
            <label className="flex items-start gap-3 rounded-md border p-3">
              <input
                type="checkbox"
                checked
                disabled
                className="mt-1 size-4"
                aria-describedby="essential-desc"
              />
              <span>
                <span className="font-medium">Essential (always on)</span>
                <span id="essential-desc" className="block text-13 text-muted-foreground">
                  Supabase sign-in, session limit, theme and this choice.
                </span>
              </span>
            </label>
            <label className="flex items-start gap-3 rounded-md border p-3">
              <input
                type="checkbox"
                className="mt-1 size-4"
                checked={analytics && !gpc}
                disabled={gpc}
                onChange={(e) => setAnalytics(e.target.checked)}
                aria-describedby="analytics-desc"
              />
              <span>
                <span className="font-medium">Analytics (PostHog)</span>
                <span id="analytics-desc" className="block text-13 text-muted-foreground">
                  {gpc
                    ? "Off: your browser sends Global Privacy Control."
                    : "Counts which screens are used. Off by default."}
                </span>
              </span>
            </label>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => choose(false)}>
              Essential only
            </Button>
            <Button onClick={() => choose(analytics)}>Save choices</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}

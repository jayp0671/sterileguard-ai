"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { signOut } from "@/lib/auth/session";

export default function SettingsPage() {
  const [busy, setBusy] = useState(false);
  return (
    <main className="mx-auto max-w-2xl px-4 py-12">
      <h1 className="text-2xl font-semibold">Settings</h1>
      <section aria-labelledby="sessions" className="mt-8 flex flex-col gap-3">
        <h2 id="sessions" className="font-medium">
          Sessions
        </h2>
        <p className="text-sm text-muted-foreground">
          Sign out everywhere, including other tablets and browsers.
        </p>
        <div className="flex gap-3">
          <Button variant="secondary" onClick={() => void signOut("user")}>
            Sign out
          </Button>
          <Button
            variant="destructive"
            disabled={busy}
            onClick={() => {
              setBusy(true);
              void signOut("user", "global");
            }}
          >
            Sign out of all devices
          </Button>
        </div>
      </section>
    </main>
  );
}

"use client";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { useIdleTimeout } from "@/hooks/use-idle-timeout";
import { signOut } from "@/lib/auth/session";
import { createClient } from "@/lib/supabase/client";

/** Shared-tablet safety: warn at 14 minutes idle, sign out at 15 (plan §9.2). */
export function IdleTimeoutGuard() {
  const { warning, secondsLeft, stay } = useIdleTimeout(() => void signOut("idle"));

  async function staySignedIn() {
    stay();
    await createClient().auth.refreshSession();
  }

  return (
    <Dialog open={warning} onOpenChange={(open) => !open && void staySignedIn()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Still there?</DialogTitle>
          <DialogDescription aria-live="assertive">
            For safety on shared devices you will be signed out in {secondsLeft} seconds.
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button variant="secondary" onClick={() => void signOut("user")}>
            Sign out now
          </Button>
          <Button onClick={() => void staySignedIn()}>Stay signed in</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

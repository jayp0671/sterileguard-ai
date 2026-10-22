"use client";

import { useState } from "react";
import { FormError } from "@/components/auth/auth-card";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { createClient } from "@/lib/supabase/client";

/**
 * Re-authentication for sensitive actions (role change, data export, model activation).
 * A fresh TOTP verification adds a new `totp` entry to the JWT `amr` claim; the API accepts the
 * action only if that entry is less than 5 minutes old (sg_api.core.auth.require_recent_totp).
 */
export function ReauthDialog({
  open,
  onOpenChange,
  onVerified,
  action,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onVerified: (accessToken: string) => void;
  action: string;
}) {
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function verify(e: React.FormEvent) {
    e.preventDefault();
    const supabase = createClient();
    const { data: factors } = await supabase.auth.mfa.listFactors();
    const factor = factors?.totp[0];
    if (!factor) return setError("No authenticator is enrolled.");
    const { error: err } = await supabase.auth.mfa.challengeAndVerify({
      factorId: factor.id,
      code: code.trim(),
    });
    if (err) return setError("That code did not match.");
    const { data } = await supabase.auth.getSession();
    setCode("");
    setError(null);
    if (data.session) onVerified(data.session.access_token);
    onOpenChange(false);
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Confirm it&apos;s you</DialogTitle>
          <DialogDescription>Enter a two-factor code to {action}.</DialogDescription>
        </DialogHeader>
        <form onSubmit={verify} className="flex flex-col gap-4">
          <Label htmlFor="reauth-code">6-digit code</Label>
          <Input
            id="reauth-code"
            inputMode="numeric"
            autoComplete="one-time-code"
            maxLength={6}
            required
            value={code}
            onChange={(e) => setCode(e.target.value)}
          />
          <FormError message={error} />
          <Button type="submit">Confirm</Button>
        </form>
      </DialogContent>
    </Dialog>
  );
}

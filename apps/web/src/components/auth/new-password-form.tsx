"use client";

import { useMemo, useState } from "react";
import { FormError } from "@/components/auth/auth-card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { checkPassword, MIN_PASSWORD_LENGTH } from "@/lib/auth/password";

const LABELS = ["Very weak", "Weak", "Fair", "Strong", "Very strong"];

/** Set-a-password form with a zxcvbn strength meter (score >= 3 and 12+ characters). */
export function NewPasswordForm({
  submitLabel,
  onSubmit,
}: {
  submitLabel: string;
  onSubmit: (password: string) => Promise<string | null>;
}) {
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const check = useMemo(() => checkPassword(password), [password]);

  async function handle(e: React.FormEvent) {
    e.preventDefault();
    if (!check.ok) return setError("Choose a longer or less common password.");
    if (password !== confirm) return setError("The passwords do not match.");
    setBusy(true);
    setError(await onSubmit(password));
    setBusy(false);
  }

  return (
    <form onSubmit={handle} className="flex flex-col gap-4" noValidate>
      <div className="flex flex-col gap-2">
        <Label htmlFor="new-password">New password</Label>
        <Input
          id="new-password"
          type="password"
          autoComplete="new-password"
          minLength={MIN_PASSWORD_LENGTH}
          required
          aria-describedby="password-strength"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
        <div id="password-strength" aria-live="polite" className="text-sm">
          <meter min={0} max={4} value={password ? check.score : 0} className="w-full" />
          <p>
            {password ? LABELS[check.score] : `At least ${MIN_PASSWORD_LENGTH} characters.`}
            {check.tooShort && password ? ` Needs ${MIN_PASSWORD_LENGTH}+ characters.` : ""}
          </p>
          {password && !check.ok && check.feedback[0] ? <p>{check.feedback[0]}</p> : null}
        </div>
      </div>
      <div className="flex flex-col gap-2">
        <Label htmlFor="confirm-password">Confirm password</Label>
        <Input
          id="confirm-password"
          type="password"
          autoComplete="new-password"
          required
          value={confirm}
          onChange={(e) => setConfirm(e.target.value)}
        />
      </div>
      <FormError message={error} />
      <Button type="submit" disabled={busy || !check.ok}>
        {submitLabel}
      </Button>
    </form>
  );
}

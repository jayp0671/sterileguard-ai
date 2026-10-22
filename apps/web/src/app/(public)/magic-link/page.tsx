"use client";

import Link from "next/link";
import { useState } from "react";
import { AuthCard, FormError } from "@/components/auth/auth-card";
import { Turnstile } from "@/components/auth/turnstile";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { createClient } from "@/lib/supabase/client";

export default function MagicLinkPage() {
  const [email, setEmail] = useState("");
  const [captcha, setCaptcha] = useState<string | null>(null);
  const [resetKey, setResetKey] = useState(0);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!captcha) return setError("Please complete the security check.");
    setError(null);
    const { error: err } = await createClient().auth.signInWithOtp({
      email,
      // Invite-only: never create an account from this form.
      options: { shouldCreateUser: false, captchaToken: captcha },
    });
    setResetKey((k) => k + 1);
    // Same message either way, so the form does not reveal which emails have accounts.
    if (err && err.status !== 400 && err.status !== 422) {
      return setError("Could not send the link. Try again in a minute.");
    }
    setSent(true);
  }

  return (
    <AuthCard title="Email me a sign-in link">
      {sent ? (
        <p role="status">If that email has an account, a sign-in link is on its way.</p>
      ) : (
        <form onSubmit={onSubmit} className="flex flex-col gap-4" noValidate>
          <div className="flex flex-col gap-2">
            <Label htmlFor="email">Email</Label>
            <Input
              id="email"
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </div>
          <Turnstile onToken={setCaptcha} resetKey={resetKey} />
          <FormError message={error} />
          <Button type="submit">Send link</Button>
        </form>
      )}
      <Link href="/sign-in" className="text-sm underline">
        Back to sign in
      </Link>
    </AuthCard>
  );
}

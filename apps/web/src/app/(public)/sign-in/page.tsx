"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { AuthCard, FormError } from "@/components/auth/auth-card";
import { Turnstile } from "@/components/auth/turnstile";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { postAuthEvent } from "@/lib/auth/audit";
import { safeNext } from "@/lib/auth/route-guard";
import { markSessionStarted } from "@/lib/auth/session";
import { createClient } from "@/lib/supabase/client";

const REASONS: Record<string, string> = {
  idle: "You were signed out after 15 minutes without activity.",
  expired: "Your session reached the 12-hour limit. Please sign in again.",
  link: "That sign-in link is invalid or has expired.",
};

function SignInForm() {
  const router = useRouter();
  const params = useSearchParams();
  const next = safeNext(params.get("next"));
  const reason = REASONS[params.get("reason") ?? ""];
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [captcha, setCaptcha] = useState<string | null>(null);
  const [resetKey, setResetKey] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!captcha) return setError("Please complete the security check.");
    setBusy(true);
    setError(null);
    const supabase = createClient();
    const { error: err } = await supabase.auth.signInWithPassword({
      email,
      password,
      options: { captchaToken: captcha },
    });
    setResetKey((k) => k + 1);
    if (err) {
      setBusy(false);
      await postAuthEvent("sign_in_failure");
      return setError("Email or password is incorrect.");
    }
    markSessionStarted();
    const { data } = await supabase.auth.mfa.getAuthenticatorAssuranceLevel();
    const target = data?.nextLevel === "aal2" ? "/mfa/challenge" : "/mfa/enroll";
    router.replace(`${target}?next=${encodeURIComponent(next)}`);
  }

  return (
    <AuthCard title="Sign in" description="Invite-only. Two-factor authentication is required.">
      {reason ? (
        <p role="status" className="text-sm">
          {reason}
        </p>
      ) : null}
      <form onSubmit={onSubmit} className="flex flex-col gap-4" noValidate>
        <div className="flex flex-col gap-2">
          <Label htmlFor="email">Email</Label>
          <Input
            id="email"
            type="email"
            autoComplete="username"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </div>
        <div className="flex flex-col gap-2">
          <Label htmlFor="password">Password</Label>
          <Input
            id="password"
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </div>
        <Turnstile onToken={setCaptcha} resetKey={resetKey} />
        <FormError message={error} />
        <Button type="submit" disabled={busy}>
          {busy ? "Signing in..." : "Sign in"}
        </Button>
      </form>
      <nav className="flex justify-between text-sm">
        <Link href="/magic-link" className="underline">
          Email me a sign-in link
        </Link>
        <Link href="/reset-password" className="underline">
          Forgot password?
        </Link>
      </nav>
    </AuthCard>
  );
}

export default function SignInPage() {
  return (
    <Suspense>
      <SignInForm />
    </Suspense>
  );
}

"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { AuthCard, FormError } from "@/components/auth/auth-card";
import { NewPasswordForm } from "@/components/auth/new-password-form";
import { Turnstile } from "@/components/auth/turnstile";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { createClient } from "@/lib/supabase/client";

function RequestStep() {
  const [email, setEmail] = useState("");
  const [captcha, setCaptcha] = useState<string | null>(null);
  const [resetKey, setResetKey] = useState(0);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!captcha) return setError("Please complete the security check.");
    const { error: err } = await createClient().auth.resetPasswordForEmail(email, {
      captchaToken: captcha,
    });
    setResetKey((k) => k + 1);
    if (err && err.status === 429) return setError("Too many requests. Try again later.");
    setSent(true);
  }

  if (sent) return <p role="status">If that email has an account, a reset link is on its way.</p>;
  return (
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
      <Button type="submit">Send reset link</Button>
    </form>
  );
}

function ResetPassword() {
  const router = useRouter();
  const confirmStep = useSearchParams().get("step") === "confirm";

  async function setPassword(password: string) {
    const { error } = await createClient().auth.updateUser({ password });
    if (error) return "Could not update the password. The link may have expired.";
    router.replace("/mfa/challenge?next=%2Fapp");
    return null;
  }

  return (
    <AuthCard title={confirmStep ? "Choose a new password" : "Reset your password"}>
      {confirmStep ? (
        <NewPasswordForm submitLabel="Update password" onSubmit={setPassword} />
      ) : (
        <RequestStep />
      )}
      <Link href="/sign-in" className="text-sm underline">
        Back to sign in
      </Link>
    </AuthCard>
  );
}

export default function ResetPasswordPage() {
  return (
    <Suspense>
      <ResetPassword />
    </Suspense>
  );
}

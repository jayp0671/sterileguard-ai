"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useState } from "react";
import { AuthCard, FormError } from "@/components/auth/auth-card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { postAuthEvent } from "@/lib/auth/audit";
import { safeNext } from "@/lib/auth/route-guard";
import { onAal2Reached } from "@/lib/auth/session";
import { createClient } from "@/lib/supabase/client";

type Enrollment = { factorId: string; qr: string; secret: string };

function Enroll() {
  const router = useRouter();
  const next = safeNext(useSearchParams().get("next"));
  const [enrollment, setEnrollment] = useState<Enrollment | null>(null);
  const [verifiedCount, setVerifiedCount] = useState(0);
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  const start = useCallback(async () => {
    setError(null);
    setCode("");
    const supabase = createClient();
    const { data: user } = await supabase.auth.getUser();
    if (!user.user) return router.replace("/sign-in");
    const { data: factors } = await supabase.auth.mfa.listFactors();
    // Remove abandoned, never-verified factors so they do not pile up.
    for (const f of factors?.all ?? []) {
      if (f.status === "unverified") await supabase.auth.mfa.unenroll({ factorId: f.id });
    }
    const verified = factors?.totp.length ?? 0;
    setVerifiedCount(verified);
    const { data, error: err } = await supabase.auth.mfa.enroll({
      factorType: "totp",
      friendlyName: `Authenticator ${verified + 1} (${new Date().toISOString().slice(0, 10)})`,
    });
    if (err || !data) return setError("Could not start two-factor setup. Reload to try again.");
    setEnrollment({ factorId: data.id, qr: data.totp.qr_code, secret: data.totp.secret });
  }, [router]);

  useEffect(() => {
    void start();
  }, [start]);

  async function verify(e: React.FormEvent) {
    e.preventDefault();
    if (!enrollment) return;
    const supabase = createClient();
    const { error: err } = await supabase.auth.mfa.challengeAndVerify({
      factorId: enrollment.factorId,
      code: code.trim(),
    });
    if (err) return setError("That code did not match. Check the time on your device and retry.");
    const { data } = await supabase.auth.getSession();
    await postAuthEvent("mfa_enroll", data.session?.access_token);
    if (verifiedCount === 0) await onAal2Reached();
    setVerifiedCount((n) => n + 1);
    setEnrollment(null);
    setDone(true);
  }

  if (done) {
    return (
      <AuthCard title="Two-factor is on">
        <p>
          <strong>Add a second authenticator now.</strong> Supabase has no recovery codes. If you
          lose your only authenticator, a department admin must reset it for you.
        </p>
        <p className="text-sm">Authenticators enrolled: {verifiedCount}</p>
        <Button
          variant="secondary"
          onClick={() => {
            setDone(false);
            void start();
          }}
        >
          Add a backup authenticator
        </Button>
        <Button onClick={() => router.replace(next)}>Continue</Button>
      </AuthCard>
    );
  }

  return (
    <AuthCard
      title="Set up two-factor authentication"
      description="Required for every account. Scan the code with an authenticator app."
    >
      {enrollment ? (
        <>
          <img src={enrollment.qr} alt="QR code for your authenticator app" className="size-48" />
          <p className="text-sm">
            Can&apos;t scan? Enter this key: <code className="break-all">{enrollment.secret}</code>
          </p>
          <form onSubmit={verify} className="flex flex-col gap-4">
            <div className="flex flex-col gap-2">
              <Label htmlFor="code">6-digit code</Label>
              <Input
                id="code"
                inputMode="numeric"
                autoComplete="one-time-code"
                pattern="[0-9]{6}"
                maxLength={6}
                required
                value={code}
                onChange={(e) => setCode(e.target.value)}
              />
            </div>
            <FormError message={error} />
            <Button type="submit">Verify</Button>
          </form>
        </>
      ) : (
        <>
          <FormError message={error} />
          {!error ? <p>Preparing...</p> : null}
        </>
      )}
      <Link href="/sign-in" className="text-sm underline">
        Use a different account
      </Link>
    </AuthCard>
  );
}

export default function EnrollPage() {
  return (
    <Suspense>
      <Enroll />
    </Suspense>
  );
}

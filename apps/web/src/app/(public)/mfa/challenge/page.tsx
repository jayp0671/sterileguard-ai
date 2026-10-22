"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { AuthCard, FormError } from "@/components/auth/auth-card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { postAuthEvent } from "@/lib/auth/audit";
import { safeNext } from "@/lib/auth/route-guard";
import { onAal2Reached, signOut } from "@/lib/auth/session";
import { createClient } from "@/lib/supabase/client";

type Factor = { id: string; friendly_name?: string | null };

function Challenge() {
  const router = useRouter();
  const next = safeNext(useSearchParams().get("next"));
  const [factors, setFactors] = useState<Factor[]>([]);
  const [factorId, setFactorId] = useState<string>("");
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const supabase = createClient();
    void (async () => {
      const { data: user } = await supabase.auth.getUser();
      if (!user.user) return router.replace("/sign-in");
      const { data } = await supabase.auth.mfa.listFactors();
      const totp = data?.totp ?? [];
      if (totp.length === 0) return router.replace(`/mfa/enroll?next=${encodeURIComponent(next)}`);
      setFactors(totp);
      setFactorId(totp[0]?.id ?? "");
    })();
  }, [router, next]);

  async function verify(e: React.FormEvent) {
    e.preventDefault();
    const { error: err } = await createClient().auth.mfa.challengeAndVerify({
      factorId,
      code: code.trim(),
    });
    if (err) {
      await postAuthEvent("mfa_challenge_failure");
      return setError("That code did not match. Try the newest code from your app.");
    }
    await onAal2Reached();
    router.replace(next);
  }

  return (
    <AuthCard
      title="Two-factor check"
      description="Enter the 6-digit code from your authenticator."
    >
      <form onSubmit={verify} className="flex flex-col gap-4">
        {factors.length > 1 ? (
          <div className="flex flex-col gap-2">
            <Label htmlFor="factor">Authenticator</Label>
            <select
              id="factor"
              className="h-10 rounded-md border px-2"
              value={factorId}
              onChange={(e) => setFactorId(e.target.value)}
            >
              {factors.map((f) => (
                <option key={f.id} value={f.id}>
                  {f.friendly_name || "Authenticator"}
                </option>
              ))}
            </select>
          </div>
        ) : null}
        <div className="flex flex-col gap-2">
          <Label htmlFor="code">6-digit code</Label>
          <Input
            id="code"
            inputMode="numeric"
            autoComplete="one-time-code"
            pattern="[0-9]{6}"
            maxLength={6}
            required
            autoFocus
            value={code}
            onChange={(e) => setCode(e.target.value)}
          />
        </div>
        <FormError message={error} />
        <Button type="submit" disabled={!factorId}>
          Verify
        </Button>
      </form>
      <p className="text-sm">
        Lost your authenticator? Ask your department admin to reset two-factor for your account.
      </p>
      <Button variant="ghost" onClick={() => void signOut("user")}>
        Sign out
      </Button>
    </AuthCard>
  );
}

export default function ChallengePage() {
  return (
    <Suspense>
      <Challenge />
    </Suspense>
  );
}

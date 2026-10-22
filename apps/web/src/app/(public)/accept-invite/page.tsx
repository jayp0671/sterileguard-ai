"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { AuthCard } from "@/components/auth/auth-card";
import { NewPasswordForm } from "@/components/auth/new-password-form";
import { markSessionStarted } from "@/lib/auth/session";
import { createClient } from "@/lib/supabase/client";

/** Reached from the invite email via /auth/confirm, which has already started a session. */
export default function AcceptInvitePage() {
  const router = useRouter();
  const [hasSession, setHasSession] = useState<boolean | null>(null);

  useEffect(() => {
    createClient()
      .auth.getUser()
      .then(({ data }) => setHasSession(Boolean(data.user)));
  }, []);

  async function setPassword(password: string) {
    const { error } = await createClient().auth.updateUser({ password });
    if (error) return "Could not set the password. Try a different one.";
    markSessionStarted();
    router.replace("/mfa/enroll?next=%2Fapp");
    return null;
  }

  return (
    <AuthCard
      title="Accept your invite"
      description="Set a password, then set up two-factor authentication."
    >
      {hasSession === false ? (
        <p role="alert">
          Open this page from the link in your invite email. Links expire after 7 days; ask your
          department admin to resend it. <Link href="/sign-in">Sign in</Link>
        </p>
      ) : (
        <NewPasswordForm submitLabel="Set password" onSubmit={setPassword} />
      )}
    </AuthCard>
  );
}

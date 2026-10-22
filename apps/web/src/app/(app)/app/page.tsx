import Link from "next/link";
import { createClient } from "@/lib/supabase/server";

export const dynamic = "force-dynamic";

/** Placeholder home until the Forecast page (SG-15). Proves an aal2 session reads tenancy data. */
export default async function AppHome() {
  const supabase = await createClient();
  const { data: departments } = await supabase.from("departments").select("id, name, slug");
  return (
    <main className="mx-auto max-w-2xl px-4 py-12">
      <h1 className="text-2xl font-semibold">Forecast</h1>
      <p className="mt-2 text-muted-foreground">Coming in SG-15.</p>
      <h2 className="mt-8 font-medium">Your departments</h2>
      <ul className="mt-2 list-disc ps-6">
        {(departments ?? []).map((d) => (
          <li key={d.id}>{d.name}</li>
        ))}
      </ul>
      <Link href="/app/settings" className="mt-8 inline-block underline">
        Settings
      </Link>
    </main>
  );
}

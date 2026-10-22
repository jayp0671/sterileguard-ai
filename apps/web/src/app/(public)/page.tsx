import { getTranslations } from "next-intl/server";
import { api } from "@/lib/api";

export const dynamic = "force-dynamic";

async function apiHealth(): Promise<{ ok: boolean; version?: string }> {
  try {
    const { data } = await api().GET("/health", { cache: "no-store" });
    return { ok: data?.status === "ok", version: data?.version };
  } catch {
    return { ok: false };
  }
}

export default async function HomePage() {
  const t = await getTranslations("home");
  const health = await apiHealth();
  return (
    <main className="mx-auto flex min-h-dvh max-w-2xl flex-col justify-center gap-6 px-4 py-16">
      <h1 className="text-3xl font-semibold tracking-tight">SterileGuard AI</h1>
      <p className="text-muted-foreground">{t("tagline")}</p>
      <section aria-labelledby="api-status" className="rounded-lg border p-4">
        <h2 id="api-status" className="text-sm font-medium">
          {t("apiStatus")}
        </h2>
        <p className="mt-2 font-mono text-sm tabular-nums" data-testid="api-health">
          {health.ok ? t("apiUp", { version: health.version ?? "?" }) : t("apiDown")}
        </p>
      </section>
    </main>
  );
}

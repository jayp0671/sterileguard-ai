import type { Metadata } from "next";
import Link from "next/link";
import { legalIndex } from "@/lib/legal";

export const metadata: Metadata = { title: "Trust Center · SterileGuard AI" };

export default function TrustIndex() {
  const pages = legalIndex();
  return (
    <main id="main" className="mx-auto flex w-full max-w-4xl flex-col gap-6 px-4 py-8">
      <header className="flex flex-col gap-2 border-b pb-4">
        <p className="engraved">SterileGuard AI</p>
        <h1 className="text-2xl font-semibold tracking-tight">Trust Center</h1>
        <p className="max-w-prose text-sm text-muted-foreground">
          How this academic prototype handles data, security, accessibility and AI. It uses
          HIPAA-style safeguards but is not HIPAA compliant, and it stores no patient information.
        </p>
      </header>
      <ul className="grid gap-3 sm:grid-cols-2">
        {pages.map((p) => (
          <li key={p.slug}>
            <Link
              href={`/trust/${p.slug}`}
              className="flex min-h-11 flex-col rounded-lg border bg-card p-4 hover:bg-accent"
            >
              <span className="font-medium">{p.title}</span>
              <span className="text-13 text-muted-foreground">Version {p.version}</span>
            </Link>
          </li>
        ))}
      </ul>
    </main>
  );
}

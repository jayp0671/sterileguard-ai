"use client";

import Link from "next/link";
import { openCookieSettings } from "@/lib/consent";

export const FOOTER_NOTICE =
  "Academic prototype. Not for clinical use. Do not enter patient information.";

const LINKS = [
  { href: "/trust/privacy", label: "Privacy" },
  { href: "/trust/terms", label: "Terms" },
  { href: "/trust/hipaa-notice", label: "HIPAA Notice" },
  { href: "/trust/cookies", label: "Cookies" },
  { href: "/trust/accessibility", label: "Accessibility" },
  { href: "/trust", label: "Trust Center" },
];

/** Every page's footer (SG-25). `sg compliance check` looks for the notice in the layout. */
export function SiteFooter({ notice = FOOTER_NOTICE }: { notice?: string }) {
  return (
    <footer className="flex flex-col items-center gap-2 border-t px-4 py-3 text-center text-xs text-muted-foreground">
      <p>{notice}</p>
      <nav aria-label="Legal" className="flex flex-wrap justify-center gap-x-4 gap-y-1">
        {LINKS.map((l) => (
          <Link key={l.href} href={l.href} className="underline-offset-4 hover:underline">
            {l.label}
          </Link>
        ))}
        <button
          type="button"
          onClick={openCookieSettings}
          className="underline-offset-4 hover:underline"
        >
          Cookie settings
        </button>
      </nav>
    </footer>
  );
}

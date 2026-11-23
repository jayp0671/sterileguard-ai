import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { LegalBody } from "@/components/legal/legal-body";
import { LEGAL_ORDER, legalIndex, readLegal } from "@/lib/legal";

export const dynamicParams = false;

export function generateStaticParams() {
  return LEGAL_ORDER.map((slug) => ({ slug }));
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string }>;
}): Promise<Metadata> {
  const page = readLegal((await params).slug);
  return { title: page ? `${page.meta.title} · SterileGuard AI` : "Trust Center" };
}

const longDate = (iso: string) =>
  new Date(`${iso}T12:00:00Z`).toLocaleDateString("en-US", {
    year: "numeric",
    month: "long",
    day: "numeric",
    timeZone: "UTC",
  });

export default async function LegalPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const page = readLegal(slug);
  if (!page) notFound();
  const toc = page.blocks.flatMap((b) => (b.t === "h2" ? [b] : []));
  const others = legalIndex();
  return (
    <main
      id="main"
      className="mx-auto grid w-full max-w-6xl gap-8 px-4 py-8 lg:grid-cols-[14rem_minmax(0,1fr)]"
    >
      <nav aria-label="Trust Center" className="flex flex-col gap-1 text-sm">
        <Link href="/trust" className="engraved mb-2">
          Trust Center
        </Link>
        {others.map((o) => (
          <Link
            key={o.slug}
            href={`/trust/${o.slug}`}
            aria-current={o.slug === slug ? "page" : undefined}
            className={
              o.slug === slug
                ? "rounded-md bg-accent px-2 py-1.5 font-medium"
                : "rounded-md px-2 py-1.5 hover:bg-accent"
            }
          >
            {o.title}
          </Link>
        ))}
      </nav>
      <article className="flex flex-col gap-4">
        <header className="flex flex-col gap-2 border-b pb-4">
          <p className="engraved">Trust Center</p>
          <h1 className="text-2xl font-semibold tracking-tight">{page.meta.title}</h1>
          <p className="text-13 text-muted-foreground">
            Last updated {longDate(page.meta.effective_date)} · Version {page.meta.version}
          </p>
          <p className="rounded-md border border-status-info-border bg-status-info-bg px-3 py-2 text-13 text-status-info">
            Template for an academic prototype. Not legal advice.
          </p>
        </header>
        {toc.length > 2 ? (
          <nav aria-label="On this page" className="text-sm">
            <p className="engraved mb-1">On this page</p>
            <ul className="flex flex-wrap gap-x-4 gap-y-1">
              {toc.map((h) => (
                <li key={h.id}>
                  <a href={`#${h.id}`} className="underline underline-offset-4">
                    {h.text}
                  </a>
                </li>
              ))}
            </ul>
          </nav>
        ) : null}
        <LegalBody blocks={page.blocks} />
      </article>
    </main>
  );
}

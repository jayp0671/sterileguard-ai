import Link from "next/link";
import type { Block, Inline } from "@/lib/legal";

function Inlines({ parts }: { parts: Inline[] }) {
  return (
    <>
      {parts.map((p, i) => {
        const key = `${p.t}-${i}`;
        if (p.t === "bold") return <strong key={key}>{p.v}</strong>;
        if (p.t === "code")
          return (
            <code key={key} className="rounded bg-muted px-1 font-mono text-13">
              {p.v}
            </code>
          );
        if (p.t === "link")
          return p.href.startsWith("/") ? (
            <Link key={key} href={p.href} className="underline underline-offset-4">
              {p.v}
            </Link>
          ) : (
            <a key={key} href={p.href} className="underline underline-offset-4" rel="noreferrer">
              {p.v}
            </a>
          );
        return <span key={key}>{p.v}</span>;
      })}
    </>
  );
}

/** Renders parsed legal Markdown as React elements; no HTML from the content is trusted. */
export function LegalBody({ blocks }: { blocks: Block[] }) {
  return (
    <div className="flex flex-col gap-4 text-sm leading-relaxed">
      {blocks.map((b, i) => {
        const key = `${b.t}-${i}`;
        switch (b.t) {
          case "h2":
            return (
              <h2 key={key} id={b.id} className="mt-4 scroll-mt-20 text-lg font-semibold">
                {b.text}
              </h2>
            );
          case "h3":
            return (
              <h3 key={key} className="font-semibold">
                {b.text}
              </h3>
            );
          case "p":
            return (
              <p key={key} className="max-w-prose">
                <Inlines parts={b.parts} />
              </p>
            );
          case "ul":
            return (
              <ul key={key} className="flex max-w-prose list-disc flex-col gap-1 pl-5">
                {b.items.map((item, j) => (
                  <li key={j}>
                    <Inlines parts={item} />
                  </li>
                ))}
              </ul>
            );
          case "table":
            return (
              <div key={key} className="overflow-x-auto rounded-lg border">
                <table className="w-full text-left text-13">
                  <thead className="bg-muted">
                    <tr>
                      {b.head.map((h, j) => (
                        <th key={j} scope="col" className="px-3 py-2 font-medium">
                          <Inlines parts={h} />
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {b.rows.map((r, j) => (
                      <tr key={j} className="border-t">
                        {r.map((c, k) => (
                          <td key={k} className="px-3 py-2 align-top">
                            <Inlines parts={c} />
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            );
          default:
            return null;
        }
      })}
    </div>
  );
}

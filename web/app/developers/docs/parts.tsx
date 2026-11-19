import { headers } from "next/headers";
import { env } from "@/lib/env";
import { Copy } from "../shared";

/** Where a page links to: the site itself, and where the portal's pages start on this host ("" on its own, /developers on the site's). */
export async function places() {
  const ownHost = ((await headers()).get("host") ?? "").startsWith("developers.");
  return { site: env.publicUrl(), base: ownHost ? "" : "/developers" };
}

export function Code({ children }: { children: string }) {
  return (
    <div className="dp-code">
      {/* focusable, so a long line can be scrolled from the keyboard */}
      <pre tabIndex={0}>
        <code>{children}</code>
      </pre>
      <Copy text={children} />
    </div>
  );
}

/** A reference table. The first cell of a row is the thing being described, so it is set as code. */
export function Table({ head, rows, label }: { head: string[]; rows: React.ReactNode[][]; label: string }) {
  return (
    <div className="dp-table" role="region" aria-label={label} tabIndex={0}>
      <table>
        <thead>
          <tr>
            {head.map((name) => (
              <th key={name} scope="col">{name}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, at) => (
            <tr key={at}>
              {row.map((cell, column) =>
                column === 0 ? (
                  <th key={column} scope="row">{typeof cell === "string" ? <code>{cell}</code> : cell}</th>
                ) : (
                  <td key={column}>{cell}</td>
                ),
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

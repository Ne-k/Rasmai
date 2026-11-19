"use client";

import { usePathname } from "next/navigation";

const PAGES: [group: string, pages: [slug: string, title: string][]][] = [
  ["Start", [["", "Getting started"]]],
  ["OAuth2", [["oauth2", "Reference"], ["sign-in", "Using the sign-in"]]],
  ["Extension", [["extension", "Linking without OAuth"]]],
];

/** The pages of the documentation. `base` is where the portal's pages start on this host: "" on its own, /developers on the site's. */
export function Nav({ base }: { base: string }) {
  const here = usePathname().replace(/\/$/, "");
  return (
    <nav className="dp-side dp-docs" aria-label="Documentation">
      {PAGES.map(([group, pages]) => (
        <div key={group}>
          <strong>{group}</strong>
          {pages.map(([slug, title]) => {
            const path = `/docs${slug && `/${slug}`}`;
            return (
              <a key={slug} href={`${base}${path}/`} aria-current={here.endsWith(path) ? "page" : undefined}>
                {title}
              </a>
            );
          })}
        </div>
      ))}
    </nav>
  );
}

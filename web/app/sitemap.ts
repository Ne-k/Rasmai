import type { MetadataRoute } from "next";
import { env } from "@/lib/env";

export const dynamic = "force-dynamic";

// only the pages that mean something to a stranger. The dashboard, a shared profile and a
// developer's own applications are all behind a link or a sign-in and are marked noindex, so none belong here.
const PAGES: { path: string; changeFrequency: MetadataRoute.Sitemap[number]["changeFrequency"]; priority: number }[] = [
  { path: "/", changeFrequency: "weekly", priority: 1 },
  { path: "/link/", changeFrequency: "monthly", priority: 0.8 },
  { path: "/extension/", changeFrequency: "monthly", priority: 0.6 },
  { path: "/feedback/", changeFrequency: "yearly", priority: 0.3 },
  { path: "/privacy/", changeFrequency: "yearly", priority: 0.3 },
  { path: "/terms/", changeFrequency: "yearly", priority: 0.3 },
];
// the developer portal's front page and documentation, on its own host. Its robots.txt names this sitemap, which is what
// lets one host's sitemap list another's pages
const PORTAL = ["/", "/docs/", "/docs/oauth2/", "/docs/sign-in/", "/docs/extension/"];

export default function sitemap(): MetadataRoute.Sitemap {
  const site = env.publicUrl();
  const now = new Date();
  return [
    ...PAGES.map(({ path, changeFrequency, priority }) => ({ url: `${site}${path}`, lastModified: now, changeFrequency, priority })),
    ...PORTAL.map((path) => ({ url: `${site.replace("//", "//developers.")}${path}`, lastModified: now, changeFrequency: "monthly" as const, priority: 0.5 })),
  ];
}

import path from "node:path";
import type { NextConfig } from "next";

// next dev evaluates code at runtime; the production build never does, so eval is only allowed there
const dev = process.env.NODE_ENV !== "production";

const CSP = [
  "default-src 'self'",
  // wasm-unsafe-eval compiles WebAssembly only (not JS): the chart player's AAC encoder for browsers without one (Firefox)
  `script-src 'self' 'unsafe-inline' 'wasm-unsafe-eval'${dev ? " 'unsafe-eval'" : ""} https://challenges.cloudflare.com https://static.cloudflareinsights.com`,
  "style-src 'self' 'unsafe-inline'",
  "font-src 'self'",
  // blob: is the chart player's own jackets and songs, read from the visitor's device
  "img-src 'self' data: blob: https://cdn.discordapp.com",
  "media-src 'self' blob:",
  "connect-src 'self' https://challenges.cloudflare.com https://cloudflareinsights.com",
  "frame-src https://challenges.cloudflare.com",
  // blob: is that AAC encoder's worker, which it builds from its own bundled script
  "worker-src 'self' blob:",
  "manifest-src 'self'",
  "frame-ancestors 'none'",
  "base-uri 'none'",
  "form-action 'self' https://discord.com https://accounts.google.com",
  // a year of HSTS means the browser refuses http for this site outright. Anything still written
  // as http is fetched over https instead of failing, so one stale link cannot break a page.
  "upgrade-insecure-requests",
].join("; ");

const secure = (process.env.MAIMAI_PUBLIC_URL ?? "https://rasmai.lol").startsWith("https://");

// Twelve months, and every subdomain with it. The bare domain is the only host served directly;
// www is redirected, and a redirect carries no headers of its own, so www is covered by this
// header's includeSubDomains once a browser has seen the bare domain even once.
const HSTS = "max-age=31536000; includeSubDomains";

const SECURITY_HEADERS = [
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=(), payment=(), usb=()" },
  { key: "Cross-Origin-Opener-Policy", value: "same-origin" },
  { key: "Content-Security-Policy", value: CSP },
  ...(secure ? [{ key: "Strict-Transport-Security", value: HSTS }] : []),
];

// stamped into the client at build time: the service worker is registered under it, so every deploy is a new worker
const buildId = (process.env.GITHUB_SHA ?? "").slice(0, 10) || String(Date.now());

const nextConfig: NextConfig = {
  env: { NEXT_PUBLIC_BUILD_ID: buildId },
  output: "standalone",
  trailingSlash: true,
  skipTrailingSlashRedirect: true,
  poweredByHeader: false,
  images: { unoptimized: true },
  // www goes to the bare domain with the path intact. The host is read off the request rather than
  // named here, so this follows the domain wherever it moves and stays out of the way in development.
  async redirects() {
    return [
      // the short addresses the link instructions give for the Aime sign-in helper, one a browser. /extension, the first one given
      // out and in /login cards already sent, is a page of its own that lists both
      { source: "/chromeextension", destination: "https://chromewebstore.google.com/detail/aime-sign-in-helper/neekcgoeopejbnccgepdbakgojojicpm", permanent: false },
      { source: "/firefoxextension", destination: "https://addons.mozilla.org/firefox/addon/aime-sign-in-helper/", permanent: false },
      { source: "/extensions", destination: "/extension/", permanent: false },
      // the portal's host serves the portal: the site's own pages, its sign-in (whose cookies are the site host's) and the
      // consent page (the only place the extension acts) are passed on to the site, query and all
      ...[
        "/:section(c|commands|connect|connected|error|extension|feedback|invite|link|me|merge|p|play|privacy|support|terms|welcome)/:rest*",
        "/:section(auth)/:rest(accept|callback|discord|google|merge)/:more*",
        "/:section(oauth)/:rest(authorize|done)/:more*",
      ].map((source) => ({
        source,
        has: [{ type: "host" as const, value: "developers\\.(?<site>.+)" }],
        destination: `https://:site${source.replace(/\([^)]*\)/g, "")}`,
        permanent: false,
      })),
      {
        source: "/:path*",
        has: [{ type: "host", value: "www\.(?<bare>.+)" }],
        destination: "https://:bare/:path*",
        statusCode: 301,
      },
    ];
  },
  // the developer portal has a host of its own, developers.<the site>, where its pages sit at the root. Before the files,
  // because / is a page of the site's own; /api, /auth, /oauth and the rest are the same on both hosts
  async rewrites() {
    const has = [{ type: "host" as const, value: "developers\\..+" }];
    return {
      beforeFiles: [
        { source: "/", has, destination: "/developers/" },
        { source: "/applications", has, destination: "/developers/applications/" },
        { source: "/applications/:id", has, destination: "/developers/applications/:id/" },
        { source: "/docs", has, destination: "/developers/docs/" },
        { source: "/docs/:page", has, destination: "/developers/docs/:page/" },
      ],
    };
  },
  async headers() {
    return [
      { source: "/:path*", headers: SECURITY_HEADERS },
      // the browser must see a new service worker as soon as one is deployed
      { source: "/sw.js", headers: [{ key: "Cache-Control", value: "no-cache, max-age=0, must-revalidate" }] },
      { source: "/manifest.webmanifest", headers: [{ key: "Cache-Control", value: "public, max-age=3600" }] },
      // previewers get an embed page at this address instead (proxy.ts), so a shared cache must not keep either answer
      {
        source: "/whitepaper.pdf",
        headers: [
          { key: "Cache-Control", value: "private, max-age=3600" },
          { key: "Vary", value: "User-Agent" },
        ],
      },
      // the sign-in script is the one thing SEGA's gateway page may load from here
      { source: "/:path((?!api/login\\.js$).*)", headers: [{ key: "Cross-Origin-Resource-Policy", value: "same-origin" }] },
    ];
  },
};

// next-intl's plugin loads the SWC native addon, which refuses a cache folder when any folder above it grants
// rights to another app (a packaged app's entry on %LOCALAPPDATA%, for one). Unless a cache is chosen already,
// it gets one inside the project, which is also out of the way of other tools. It has to be set before the plugin
// loads, so the plugin is imported here rather than at the top.
export default async function config() {
  process.env.SWC_NATIVE_BINDING_CACHE ??= path.join(process.cwd(), ".next", "cache", "swc");
  const { default: createNextIntlPlugin } = await import("next-intl/plugin");
  return createNextIntlPlugin()(nextConfig);
}

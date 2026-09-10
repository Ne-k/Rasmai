import type { MetadataRoute } from "next";

/** The home-screen app: the dashboard, opened without browser chrome. */
export default function manifest(): MetadataRoute.Manifest {
  return {
    id: "/me/",
    name: "Rasmai",
    short_name: "Rasmai",
    description: "Your maimai DX scores, best 50 and what to play next.",
    start_url: "/me/?source=app",
    scope: "/",
    display: "standalone",
    background_color: "#1d1a2f",
    theme_color: "#fbf6ec",
    lang: "en",
    categories: ["games", "utilities"],
    icons: [
      { src: "/app/icon-192.png", sizes: "192x192", type: "image/png" },
      { src: "/app/icon-512.png", sizes: "512x512", type: "image/png" },
      { src: "/app/icon-maskable-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
    ],
    shortcuts: [
      { name: "What to play", url: "/me/?source=app#picks", icons: [{ src: "/app/icon-192.png", sizes: "192x192" }] },
      { name: "Best 50", url: "/me/?source=app#best50", icons: [{ src: "/app/icon-192.png", sizes: "192x192" }] },
      { name: "Recent plays", url: "/me/?source=app#recent", icons: [{ src: "/app/icon-192.png", sizes: "192x192" }] },
      { name: "Traits", url: "/me/?source=app#traits", icons: [{ src: "/app/icon-192.png", sizes: "192x192" }] },
    ],
  };
}

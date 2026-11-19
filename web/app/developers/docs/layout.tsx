import type { Metadata } from "next";
import { headers } from "next/headers";
import { Nav } from "./Nav";

export const metadata: Metadata = {
  // unlike a developer's own applications, the documentation is for anyone to find
  robots: { index: true, follow: true },
  title: "Documentation",
  description: "How to use Rasmai's maimai sign-in in your own app: OAuth2, the sign-in itself and the extension.",
};

export default async function DocsLayout({ children }: { children: React.ReactNode }) {
  const ownHost = ((await headers()).get("host") ?? "").startsWith("developers.");
  return (
    <div className="dp-body">
      <Nav base={ownHost ? "" : "/developers"} />
      <article className="dp-doc">{children}</article>
    </div>
  );
}

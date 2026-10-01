import type { Metadata } from "next";
import { Doc } from "@/components/Doc";
import { getI18n } from "@/lib/i18n/server";

export async function generateMetadata(): Promise<Metadata> {
  const { m } = await getI18n();
  return {
    title: m.terms.metaTitle,
    description: m.terms.metaDescription,
    alternates: { canonical: "/terms/" },
    openGraph: { title: `${m.terms.metaTitle} · Rasmai`, description: m.terms.metaDescription, url: "/terms/", images: ["/opengraph-image"] },
  };
}

export default async function TermsPage() {
  const { m } = await getI18n();
  return (
    <Doc tag="terms" title={m.terms.title} intro={m.terms.intro}>
      {m.docs.terms()}
    </Doc>
  );
}

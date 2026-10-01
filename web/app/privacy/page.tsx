import type { Metadata } from "next";
import { Doc } from "@/components/Doc";
import { getI18n } from "@/lib/i18n/server";

export async function generateMetadata(): Promise<Metadata> {
  const { m } = await getI18n();
  return {
    title: m.privacy.metaTitle,
    description: m.privacy.metaDescription,
    alternates: { canonical: "/privacy/" },
    openGraph: { title: `${m.privacy.metaTitle} · Rasmai`, description: m.privacy.metaDescription, url: "/privacy/", images: ["/opengraph-image"] },
  };
}

export default async function PrivacyPage() {
  const { m } = await getI18n();
  return (
    <Doc tag="privacy" title={m.privacy.title} intro={m.privacy.intro}>
      {m.docs.privacy()}
    </Doc>
  );
}

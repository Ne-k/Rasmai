import type { Metadata } from "next";
import { Doc } from "@/components/Doc";
import { docBody } from "@/components/DocBody";
import { getTranslations } from "next-intl/server";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("privacy");
  return {
    title: t("metaTitle"),
    description: t("metaDescription"),
    alternates: { canonical: "/privacy/" },
    openGraph: { title: `${t("metaTitle")} · Rasmai`, description: t("metaDescription"), url: "/privacy/", images: ["/opengraph-image"] },
  };
}

export default async function PrivacyPage() {
  const t = await getTranslations("privacy");
  return (
    <Doc tag="privacy" title={t.rich("title", { em: (c) => <em>{c}</em> })} intro={t("intro")}>
      {await docBody("privacy")}
    </Doc>
  );
}

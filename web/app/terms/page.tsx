import type { Metadata } from "next";
import { Doc } from "@/components/Doc";
import { docBody } from "@/components/DocBody";
import { getTranslations } from "next-intl/server";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("terms");
  return {
    title: t("metaTitle"),
    description: t("metaDescription"),
    alternates: { canonical: "/terms/" },
    openGraph: { title: `${t("metaTitle")} · Rasmai`, description: t("metaDescription"), url: "/terms/", images: ["/opengraph-image"] },
  };
}

export default async function TermsPage() {
  const t = await getTranslations("terms");
  return (
    <Doc tag="terms" title={t.rich("title", { em: (c) => <em>{c}</em> })} intro={t("intro")}>
      {await docBody("terms")}
    </Doc>
  );
}

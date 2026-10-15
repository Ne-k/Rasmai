import type { Metadata } from "next";
import { Doc } from "@/components/Doc";
import { FeedbackForm } from "@/components/FeedbackForm";
import { env, turnstileReady } from "@/lib/env";
import { getTranslations } from "next-intl/server";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("feedback");
  return {
    title: t("metaTitle"),
    description: t("metaDescription"),
    alternates: { canonical: "/feedback/" },
    openGraph: { title: `${t("metaTitle")} · Rasmai`, description: t("metaDescription"), url: "/feedback/", images: ["/opengraph-image"] },
  };
}

export default async function FeedbackPage() {
  const t = await getTranslations("feedback");
  // matches the route: with no human check set up in production it takes nothing, so the page does not offer a form
  const off = !turnstileReady() && process.env.NODE_ENV === "production";
  return (
    <Doc tag="feedback" title={t.rich("title", { em: (c) => <em>{c}</em> })} intro={t("intro")} dated={false}>
      {off ? <p>{t("off")}</p> : <FeedbackForm siteKey={turnstileReady() ? env.turnstileSiteKey() : ""} />}
    </Doc>
  );
}

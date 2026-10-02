import type { Metadata } from "next";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { getTranslations } from "next-intl/server";
import { Shell } from "@/components/Shell";
import { readPending } from "@/lib/pending";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("welcome");
  return { title: t("metaTitle"), description: t("metaDescription"), robots: { index: false } };
}

const MEANS = ["i01", "i02", "i03", "i04", "i05", "i06"] as const;

export default async function WelcomePage() {
  const pending = readPending(await cookies());
  if (!pending) redirect("/me/");
  if (pending.merge) redirect("/merge/");
  const t = await getTranslations("welcome");
  const footer = await getTranslations("footer");
  const hasDiscord = pending.identities.some((i) => i.provider === "discord");
  const tab = { target: "_blank", rel: "noopener noreferrer" } as const;

  return (
    <Shell tag="welcome" lit={2} footLeft={t("nothingCreated")} footRight={footer("notAffiliated")}>
      <h1>{t.rich("title", { em: (c) => <em>{c}</em> })}</h1>
      <p className="lede">{t("lede")}</p>
      {pending.identities.map((i) => (
        <p key={i.provider} className="lede" style={{ marginTop: -14 }}>
          {i.name
            ? t.rich("signingIn", { provider: t(`providers.${i.provider}`), name: i.name, b: (c) => <b>{c}</b> })
            : t("signingInNoName", { provider: t(`providers.${i.provider}`) })}
        </p>
      ))}

      <h2 className="subhead">{t("meansTitle")}</h2>
      <ul className="cmds">
        {MEANS.map((key) => (
          <li key={key}>{t(`means.${key}`)}</li>
        ))}
      </ul>

      <p className="hint" style={{ marginTop: 18 }}>
        {t.rich("readDocs", {
          privacy: (c) => <a href="/privacy/" {...tab}>{c}</a>,
          terms: (c) => <a href="/terms/" {...tab}>{c}</a>,
        })}
      </p>

      <form className="signin" method="post" action="/auth/accept" style={{ maxWidth: 560 }}>
        <label className="remember">
          <input type="checkbox" name="terms" required />
          <span>{t("agree")}</span>
        </label>
        <div className="btn-row">
          <button className="button pink" type="submit">{t("create")}</button>
        </div>
        <p className="hint">{t("expires")}</p>
      </form>

      {!hasDiscord && (
        <div className="aside">
          <b>{t("alreadyTitle")}</b> {t("alreadyBody")}
          <div className="btn-row" style={{ marginTop: 12 }}>
            <a className="button ghost" href="/auth/discord?keep=pending">{t("already")}</a>
          </div>
        </div>
      )}
    </Shell>
  );
}

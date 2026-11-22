import type { Metadata } from "next";
import { Shell } from "@/components/Shell";
import { getTranslations } from "next-intl/server";

const CHROME_STORE = "https://chromewebstore.google.com/detail/aime-sign-in-helper/neekcgoeopejbnccgepdbakgojojicpm";
const FIREFOX_STORE = "https://addons.mozilla.org/firefox/addon/aime-sign-in-helper/";

// the browsers' marks from Simple Icons, one path each, drawn in the text's colour so they follow the theme and the greyed button
const CHROME_MARK =
  "M12 0C8.21 0 4.831 1.757 2.632 4.501l3.953 6.848A5.454 5.454 0 0 1 12 6.545h10.691A12 12 0 0 0 12 0zM1.931 5.47A11.943 11.943 0 0 0 0 12c0 6.012 4.42 10.991 10.189 11.864l3.953-6.847a5.45 5.45 0 0 1-6.865-2.29zm13.342 2.166a5.446 5.446 0 0 1 1.45 7.09l.002.001h-.002l-5.344 9.257c.206.01.413.016.621.016 6.627 0 12-5.373 12-12 0-1.54-.29-3.011-.818-4.364zM12 16.364a4.364 4.364 0 1 1 0-8.728 4.364 4.364 0 0 1 0 8.728Z";
const FIREFOX_MARK =
  "M8.824 7.287c.008 0 .004 0 0 0zm-2.8-1.4c.006 0 .003 0 0 0zm16.754 2.161c-.505-1.215-1.53-2.528-2.333-2.943.654 1.283 1.033 2.57 1.177 3.53l.002.02c-1.314-3.278-3.544-4.6-5.366-7.477-.091-.147-.184-.292-.273-.446a3.545 3.545 0 01-.13-.24 2.118 2.118 0 01-.172-.46.03.03 0 00-.027-.03.038.038 0 00-.021 0l-.006.001a.037.037 0 00-.01.005L15.624 0c-2.585 1.515-3.657 4.168-3.932 5.856a6.197 6.197 0 00-2.305.587.297.297 0 00-.147.37c.057.162.24.24.396.17a5.622 5.622 0 012.008-.523l.067-.005a5.847 5.847 0 011.957.222l.095.03a5.816 5.816 0 01.616.228c.08.036.16.073.238.112l.107.055a5.835 5.835 0 01.368.211 5.953 5.953 0 012.034 2.104c-.62-.437-1.733-.868-2.803-.681 4.183 2.09 3.06 9.292-2.737 9.02a5.164 5.164 0 01-1.513-.292 4.42 4.42 0 01-.538-.232c-1.42-.735-2.593-2.121-2.74-3.806 0 0 .537-2 3.845-2 .357 0 1.38-.998 1.398-1.287-.005-.095-2.029-.9-2.817-1.677-.422-.416-.622-.616-.8-.767a3.47 3.47 0 00-.301-.227 5.388 5.388 0 01-.032-2.842c-1.195.544-2.124 1.403-2.8 2.163h-.006c-.46-.584-.428-2.51-.402-2.913-.006-.025-.343.176-.389.206-.406.29-.787.616-1.136.974-.397.403-.76.839-1.085 1.303a9.816 9.816 0 00-1.562 3.52c-.003.013-.11.487-.19 1.073-.013.09-.026.181-.037.272a7.8 7.8 0 00-.069.667l-.002.034-.023.387-.001.06C.386 18.795 5.593 24 12.016 24c5.752 0 10.527-4.176 11.463-9.661.02-.149.035-.298.052-.448.232-1.994-.025-4.09-.753-5.844z";

const SHOTS = [
  ["popup-page", 284, 282, "shotPage"],
  ["popup-linked", 284, 311, "shotLinked"],
  ["approval", 420, 340, "shotApproval"],
] as const;

const Mark = ({ d }: { d: string }) => (
  <svg viewBox="0 0 24 24" width={32} height={32} aria-hidden="true">
    <path d={d} />
  </svg>
);

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("extension");
  return {
    title: t("metaTitle"),
    description: t("metaDescription"),
    alternates: { canonical: "/extension/" },
    openGraph: { title: `${t("metaTitle")} · Rasmai`, description: t("metaDescription"), url: "/extension/", images: ["/opengraph-image"] },
  };
}

export default async function ExtensionPage() {
  const t = await getTranslations("extension");
  const footer = await getTranslations("footer");
  const tags = {
    em: (c: React.ReactNode) => <em>{c}</em>,
    b: (c: React.ReactNode) => <b>{c}</b>,
    link: (c: React.ReactNode) => <a href="/link/">{c}</a>,
  };
  return (
    <Shell tag="extension" lit={1} steps={[t("steps.add"), t("steps.signIn"), t("steps.link")]} footLeft={footer("notAffiliated")}>
      <h1>{t.rich("title", tags)}</h1>
      <p className="lede">{t("lede")}</p>

      <ul className="browsers">
        <li>
          <a className="button browser" href={CHROME_STORE} target="_blank" rel="noopener noreferrer">
            <Mark d={CHROME_MARK} />
            <span>
              {t("chrome")}
              <small>{t("chromeNote")}</small>
            </span>
          </a>
        </li>
        <li>
          <a className="button browser" href={FIREFOX_STORE} target="_blank" rel="noopener noreferrer">
            <Mark d={FIREFOX_MARK} />
            <span>
              {t("firefox")}
              <small>{t("firefoxNote")}</small>
            </span>
          </a>
        </li>
      </ul>
      <div className="aside">{t.rich("android", tags)}</div>

      <p>{t.rich("how", tags)}</p>

      <h2 className="subhead">{t("shotsTitle")}</h2>
      {/* 2x pictures at their real size; the caption under each says what it is, so the picture itself has no alt */}
      <div className="shots">
        {SHOTS.map(([file, width, height, caption]) => (
          <figure key={file}>
            <img src={`/helper/${file}.png`} width={width} height={height} alt="" loading="lazy" decoding="async" />
            <figcaption>{t(caption)}</figcaption>
          </figure>
        ))}
      </div>
    </Shell>
  );
}

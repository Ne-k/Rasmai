"use client";

import { useEffect, useMemo, useState } from "react";
import { Ring } from "@/components/Ring";
import { ThemeToggle } from "@/components/Theme";
import { useTranslations } from "next-intl";
import { LangToggle, useLocale } from "@/components/I18n";
import { traitName } from "@/lib/i18n/traits";
import { Chip, Empty, Jacket, Label, num, pct, when } from "./dash/bits";
import { RatingPlate } from "./dash/RatingPlate";
import { Radar, radarAxes, twoSides } from "./dash/traits";

type Chart = {
  title: string; difficulty: string; type: string; level: string; constant: number;
  accuracy: number; rank: string; rating: number; fc: string; fs: string; cover: string;
};
type SharedTrait = {
  label: string; offset: number; count: number; plays: number; kind: string;
  // the wheel and the two lists are built from these, the same way the dashboard builds them
  dimension: string; verified: boolean; leaning: boolean; p: number; english: string;
};
type Shared = {
  name: string; title: string; dan: string; region: string; rating: number; plays: number; charts: number;
  updatedAt: string;
  nameplate?: string;
  shows: { best50: boolean; traits: boolean; recent: boolean; areas: boolean };
  best50?: { new: Chart[]; old: Chart[] };
  recent?: { title: string; difficulty: string; type: string; achievement: number; rank: string; day: string; cover: string }[];
  traits?: SharedTrait[];
  traitAxes?: SharedTrait[];
  traitFamilies?: { key: string; label: string; note: string; offset: number; charts: number;
                    traits: number; plays: number; verified: boolean }[];
  areas?: { name: string; english: string; distance: number; state: string }[];
  history?: { recordedAt: string; rating: number }[];
};
type Panel = "overview" | "best50" | "traits" | "recent" | "areas";

function Shell({ children, name }: { children: React.ReactNode; name?: string }) {
  return (
    <div className="frame dash">
      <header className="masthead">
        <a className="home" href="/">
          <Ring lit={0} size={34} />
        </a>
        <div className="wordmark">
          Ras<span>mai</span>
        </div>
        {name ? <span className="masthead-tag mono">{name}</span> : null}
        <LangToggle />
        <ThemeToggle />
      </header>
      {children}
    </div>
  );
}

function RatingLine({ points }: { points: { recordedAt: string; rating: number }[] }) {
  const t = useTranslations("profile");
  if (points.length < 2) return null;
  const values = points.map((p) => p.rating);
  const low = Math.min(...values);
  const high = Math.max(...values);
  const span = Math.max(1, high - low);
  const path = points.map((p, i) => `${(100 * i) / (points.length - 1)},${30 - (28 * (p.rating - low)) / span}`).join(" ");
  return (
    <>
      <svg className="share-spark" viewBox="0 0 100 32" preserveAspectRatio="none" role="img" aria-label={t("ratingRange", { low, high })}>
        <polyline points={path} fill="none" stroke="var(--pink)" strokeWidth="1.4" vectorEffect="non-scaling-stroke" />
      </svg>
      <div className="admin-axis mono">
        <span>{num(low)}</span>
        <span className="dim">{t("readings", { n: points.length })}</span>
        <span>{num(high)}</span>
      </div>
    </>
  );
}

function Pool({ title, rows, size }: { title: string; rows: Chart[]; size: number }) {
  const t = useTranslations("profile");
  return (
    <section className="ledger">
      <div className="ledger-head">
        <Label>
          {title} · {rows.length}/{size}
        </Label>
        <span className="mono hint">{t("poolRating", { n: num(rows.reduce((sum, r) => sum + r.rating, 0)) })}</span>
      </div>
      {rows.length === 0 ? (
        <Empty>{t("emptyPool")}</Empty>
      ) : (
        <div className="scroll">
          <table className="tbl compact b50 keep">
            <tbody>
              {rows.map((r, i) => (
                <tr key={`${r.title}|${r.type}|${r.difficulty}`}>
                  <td className="c-n">{i + 1}</td>
                  <td className="c-jacket">
                    <Jacket cover={r.cover} size={32} />
                  </td>
                  <td className="c-title">
                    <span className="title">{r.title}</span>
                    <Chip difficulty={r.difficulty} level={r.level} constant={r.constant} type={r.type} />
                  </td>
                  <td className="c-num mono c-acc">
                    {pct(r.accuracy)} <b>{r.rank}</b>
                  </td>
                  <td className="c-num mono strong c-rating">{r.rating}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

export function PublicProfile({ slug }: { slug: string }) {
  const t = useTranslations("profile");
  const dash = useTranslations("dash");
  const best50 = useTranslations("best50Tab");
  const areas = useTranslations("areasTab");
  const locale = useLocale();
  const [data, setData] = useState<Shared | null>(null);
  const [gone, setGone] = useState(false);
  const [panel, setPanel] = useState<Panel>("overview");

  useEffect(() => {
    fetch(`/api/public/${encodeURIComponent(slug)}`)
      .then(async (r) => {
        if (!r.ok) throw new Error(String(r.status));
        setData((await r.json()) as Shared);
      })
      .catch(() => setGone(true));
  }, [slug]);

  const panels = useMemo(() => {
    if (!data) return [];
    const out: Panel[] = ["overview"];
    if (data.best50) out.push("best50");
    if (data.traits?.length) out.push("traits");
    if (data.recent) out.push("recent");
    if (data.areas?.length) out.push("areas");
    return out;
  }, [data]);

  if (gone) {
    return (
      <Shell>
        <div className="gate">
          <h1>{t.rich("goneTitle", { em: (c) => <em>{c}</em> })}</h1>
          <p className="lede">{t("goneLede")}</p>
          <a className="button" href="/">
            {t("whatRasmai")}
          </a>
        </div>
      </Shell>
    );
  }
  if (!data) {
    return (
      <Shell>
        <div className="gate">
          <p className="hint">{dash("loading")}</p>
        </div>
      </Shell>
    );
  }

  // every axis the player has, ranked the way the dashboard ranks them, so a profile reads the same
  // on both pages
  const axes = (data.traitAxes ?? []) as never[];
  const { weak, strong } = twoSides((data.traits ?? []) as never[], axes);
  const best = data.best50 ? [...data.best50.new, ...data.best50.old].sort((a, b) => b.rating - a.rating)[0] : undefined;
  // the wheel is drawn on the families where there are enough of them, as the dashboard draws it,
  // and falls back to single traits otherwise
  const onFamilies = (data.traitFamilies ?? []).map((f) => ({
    dimension: "family", label: f.label, english: f.label, offset: f.offset,
    count: f.charts, plays: f.plays, p: 0, verified: f.verified, leaning: !f.verified,
  })) as never[];
  const wheel = onFamilies.length >= 3 ? onFamilies : radarAxes(axes);

  return (
    <Shell name={data.name}>
      <section className="ident">
        <div className="ident-who">
          <div className="label">{data.region.toUpperCase()} · {t("shared")}</div>
          <h1>{data.name}</h1>
          <div className="ident-sub mono">
            {t("sub", { titles: [data.dan, data.title].filter(Boolean).join(" · ") || dash("noTitle"), plays: num(data.plays), read: when(data.updatedAt) })}
          </div>
          {data.nameplate ? (
            <img className="nameplate" src={data.nameplate} alt="" width={360} height={58}
                 onError={(e) => { e.currentTarget.hidden = true; }} />
          ) : null}
        </div>
        <div className="readout big">
          <span className="lbl">{dash("rating")}</span>
          <span className="val"><RatingPlate rating={data.rating} /></span>
          <span className="lbl">{t("charts")}</span>
          <span className="val">{num(data.charts)}</span>
        </div>
      </section>

      {panels.length > 1 && (
        <nav className="tabs" aria-label={t("shares")}>
          {panels.map((p) => (
            <button key={p} type="button" className={panel === p ? "on" : ""} onClick={() => setPanel(p)}>
              {t(`tabs.${p}`)}
            </button>
          ))}
        </nav>
      )}

      <main className="panel">
        {panel === "overview" && (
          <>
            {data.history && data.history.length > 1 && (
              <section className="ledger">
                <div className="ledger-head">
                  <Label>{t("overTime")}</Label>
                  <span className="mono hint">{t("fromChecks")}</span>
                </div>
                <RatingLine points={data.history} />
              </section>
            )}
            <section className="ledger">
              <div className="ledger-head">
                <Label>{t("glance")}</Label>
              </div>
              <dl className="facts">
                <dt>{dash("rating")}</dt>
                <dd className="mono">{num(data.rating)}</dd>
                <dt>{t("scored")}</dt>
                <dd className="mono">{num(data.charts)}</dd>
                <dt>{t("totalPlays")}</dt>
                <dd className="mono">{num(data.plays)}</dd>
                {best ? (
                  <>
                    <dt>{t("bestChart")}</dt>
                    <dd className="mono">
                      {best.title} · {best.rating}
                    </dd>
                  </>
                ) : null}
                <dt>{t("lastRead")}</dt>
                <dd className="mono">{when(data.updatedAt)}</dd>
              </dl>
              <p className="hint">
                {panels.length > 1
                  ? t("sharesTabs")
                  : t("onlyRating")}
              </p>
            </section>
          </>
        )}

        {panel === "best50" && data.best50 && (
          <div className="two-up wide-right">
            <Pool title={best50("newVersion")} rows={data.best50.new} size={15} />
            <Pool title={best50("older")} rows={data.best50.old} size={35} />
          </div>
        )}

        {panel === "traits" && (
          <section className="ledger">
            <div className="ledger-head">
              <Label>{t("how")}</Label>
              <span className="mono hint">{t("ownCurve")}</span>
            </div>
            <div className="two-up radar-split">
              <div className="radar-wrap">{wheel.length >= 3 ? <Radar axes={wheel} /> : null}</div>
              <div>
                <div className="ledger-head">
                  <Label>{t("weak")}</Label>
                </div>
                {weak.length ? (
                  <ul className="traits">
                    {weak.map((x) => (
                      <li key={`w${x.label}`}>
                        <span className="mono trait-offset down">{x.offset.toFixed(2)}</span>
                        <span className="trait-label">{traitName(x.label, x.english, locale)}</span>
                        <span className="mono dim">{x.count}</span>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="hint">{t("noWeak")}</p>
                )}
                <div className="ledger-head">
                  <Label>{t("strong")}</Label>
                </div>
                {strong.length ? (
                  <ul className="traits">
                    {strong.map((x) => (
                      <li key={`s${x.label}`}>
                        <span className="mono trait-offset up">+{x.offset.toFixed(2)}</span>
                        <span className="trait-label">{traitName(x.label, x.english, locale)}</span>
                        <span className="mono dim">{x.count}</span>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="hint">{t("noStrong")}</p>
                )}
              </div>
            </div>
          </section>
        )}

        {panel === "recent" && data.recent && (
          <section className="ledger">
            <div className="ledger-head">
              <Label>{t("recent")}</Label>
              <span className="mono hint">{t("newest")}</span>
            </div>
            {data.recent.length === 0 ? (
              <Empty>{t("noPlays")}</Empty>
            ) : (
              <table className="tbl compact">
                <tbody>
                  {data.recent.map((p, i) => (
                    <tr key={`${p.title}${p.day}${i}`}>
                      <td className="c-jacket">
                        <Jacket cover={p.cover} size={32} />
                      </td>
                      <td className="c-title">
                        <span className="title">{p.title}</span>
                        <Chip difficulty={p.difficulty} type={p.type} />
                      </td>
                      <td className="c-num mono strong">
                        {pct(p.achievement, 4)} <b>{p.rank}</b>
                      </td>
                      <td className="c-num mono dim">{p.day}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </section>
        )}

        {panel === "areas" && data.areas && (
          <section className="ledger">
            <div className="ledger-head">
              <Label>{areas("travel")}</Label>
              <span className="mono hint">{t("inProgress", { n: data.areas.length })}</span>
            </div>
            <ul className="areas compact">
              {data.areas.map((a) => (
                <li key={a.name} className="area">
                  <span className="area-name">
                    {a.name}
                    {a.english ? <span className="area-english">{a.english}</span> : null}
                  </span>
                  <span className="mono dim">
                    {num(a.distance)} km{a.state === "completed" ? t("done") : ""}
                  </span>
                </li>
              ))}
            </ul>
          </section>
        )}

        <footer className="foot">
          <span>{t.rich("footLeft", { link: (c) => <a href="/">{c}</a> })}</span>
          <span>{t("footRight")}</span>
        </footer>
      </main>
    </Shell>
  );
}

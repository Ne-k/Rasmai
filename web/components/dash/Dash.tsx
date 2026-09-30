"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Turnstile } from "@/components/Turnstile";
import { InstallHint } from "@/components/Pwa";
import { ApiError, QUEUE_EVENT, SIGNED_OUT_EVENT, getJSON, postJSON, type ChartRow, type LookupTarget, type Overview, type QueueSpot, type RecentPlay, type RefreshStatus } from "./api";
import { Lookup } from "./Lookup";
import { Ago, Empty, LoadError, day, num, type OpenChart } from "./bits";
import { Areas } from "./Areas";
import { JudgementProfile, Traits } from "./traits";
import { Charts } from "./Charts";
import { NewCharts } from "./NewCharts";
import { Picks } from "./Picks";
import { Account } from "./Account";
import { AdminPanel } from "./admin/Panel";
import { Best50 } from "./Best50";
import { ratingBand } from "./band";
import { RatingPlate } from "./RatingPlate";
import { Frame } from "./Frame";
import { OverviewTab } from "./OverviewTab";
import { Recent } from "./Recent";
import { type Tab, TABS, Tabs, RefreshBar, tabsFor } from "./Tabs";
import { SaveImage, type ImageKind } from "./bits";

// the tabs the bot already draws a picture of, and which of its commands draws it
const IMAGE_FOR: Partial<Record<Tab, ImageKind[]>> = {
  overview: ["profile", "progress"],
  picks: ["analyze"],
  new: ["new"],
  traits: ["traits"],
  best50: ["best50"],
  recent: ["recent"],
};

function QueueNote({ spot }: { spot: NonNullable<QueueSpot> }) {
  const wait = spot.eta < 60 ? `${Math.max(1, spot.eta)}s` : `${Math.round(spot.eta / 60)} min`;
  return (
    <div className="notice" role="status" aria-live="polite">
      {spot.position <= 1
        ? "Building your analysis now…"
        : `It's busy right now. You're #${spot.position} in the queue, about ${wait} left. The page will update when it's done.`}
    </div>
  );
}

export function Dash() {
  const [me, setMe] = useState<Overview | null>(null);
  const [signedOut, setSignedOut] = useState(false);
  const [oauth, setOauth] = useState(true);
  const [turnstile, setTurnstile] = useState("");
  const [human, setHuman] = useState("");
  const [error, setError] = useState("");
  const [tab, setTab] = useState<Tab>("overview");
  const [charts, setCharts] = useState<ChartRow[] | null>(null);
  const [chartsError, setChartsError] = useState("");
  const [recent, setRecent] = useState<RecentPlay[] | null>(null);
  const [recentError, setRecentError] = useState("");
  const [refresh, setRefresh] = useState<RefreshStatus | null>(null);
  const [lookup, setLookup] = useState<LookupTarget | null>(null);
  const [areaFocus, setAreaFocus] = useState("");
  // tabs stay mounted once opened, so filters, paging and fetched data survive a trip to another tab
  const [visited, setVisited] = useState<Set<Tab>>(() => new Set(["overview"]));
  const pollFailures = useRef(0);

  const load = useCallback(() => {
    getJSON<Overview>("/api/me")
      .then((data) => {
        setMe(data);
        setSignedOut(false);
        setRefresh(data.refresh ?? null);
      })
      .catch((e: ApiError) => {
        if (e.status === 401) {
          setSignedOut(true);
          setOauth(Boolean(e.body?.oauth));
          setTurnstile(String(e.body?.turnstile ?? ""));
        } else setError(e.message);
      });
  }, []);

  // while the bot builds this person's analysis behind other people's, the page says where they are in line
  const [queued, setQueued] = useState<QueueSpot>(null);
  useEffect(() => {
    const onQueue = (event: Event) => setQueued(((event as CustomEvent).detail ?? null) as QueueSpot);
    window.addEventListener(QUEUE_EVENT, onQueue);
    return () => window.removeEventListener(QUEUE_EVENT, onQueue);
  }, []);

  // any API call that answers 401 sends the dashboard back to the sign-in gate, whichever tab made it
  useEffect(() => {
    const onSignedOut = (event: Event) => {
      const body = ((event as CustomEvent).detail ?? {}) as Record<string, unknown>;
      setSignedOut(true);
      if ("oauth" in body) setOauth(Boolean(body.oauth));
      if ("turnstile" in body) setTurnstile(String(body.turnstile ?? ""));
    };
    window.addEventListener(SIGNED_OUT_EVENT, onSignedOut);
    return () => window.removeEventListener(SIGNED_OUT_EVENT, onSignedOut);
  }, []);

  // the address carries the tab and the chart on show, so Back and Forward move between them
  const applyLocation = useCallback(() => {
    const params = new URLSearchParams(window.location.search);
    const hash = window.location.hash.replace("#", "") as Tab;
    const wanted = params.get("chart");
    const cover = params.get("cover");
    if (wanted || cover) {
      setLookup({ title: wanted ?? "", cover: cover ?? undefined, type: params.get("type") ?? undefined, difficulty: params.get("difficulty") ?? undefined });
      setTab("chart");
      setVisited((v) => new Set(v).add("chart"));
      return;
    }
    const area = params.get("area");
    if (area) {
      setAreaFocus(area);
      setTab("areas");
      setVisited((v) => new Set(v).add("areas"));
      return;
    }
    const next: Tab = tabsFor(true).some((t) => t.key === hash) ? hash : "overview";
    setTab(next);
    setVisited((v) => new Set(v).add(next));
  }, []);

  useEffect(() => {
    window.addEventListener("popstate", applyLocation);
    return () => window.removeEventListener("popstate", applyLocation);
  }, [applyLocation]);

  useEffect(() => {
    load();
    const params = new URLSearchParams(window.location.search);
    const kind = params.get("error");
    if (kind === "discord") setError("Discord didn't confirm the sign-in. Try again.");
    if (kind === "state") setError("That sign-in link expired. Try again.");
    if (kind === "oauth_unconfigured") setError("Sign-in isn't set up on this server yet.");
    if (kind === "verify") setError("The human check failed. Try again.");
    applyLocation();
  }, [load, applyLocation]);

  const loadCharts = useCallback(() => {
    setChartsError("");
    getJSON<{ charts: ChartRow[] }>("/api/me/charts")
      .then((d) => setCharts(d.charts))
      .catch((e: ApiError) => setChartsError(e.message));
  }, []);
  useEffect(() => {
    if (!me?.linked || charts !== null || chartsError) return;
    loadCharts();
  }, [me, charts, chartsError, loadCharts]);

  const loadRecent = useCallback(() => {
    setRecentError("");
    getJSON<{ plays: RecentPlay[] }>("/api/me/recent")
      .then((d) => setRecent(d.plays))
      .catch((e: ApiError) => setRecentError(e.message));
  }, []);
  useEffect(() => {
    if (tab !== "recent" || !me?.linked || recent !== null || recentError) return;
    loadRecent();
  }, [tab, me, recent, recentError, loadRecent]);

  // follow a running refresh, then reload everything once it lands; a bot that stops answering ends the wait
  useEffect(() => {
    if (!refresh?.running) return;
    pollFailures.current = 0;
    const timer = setInterval(() => {
      getJSON<RefreshStatus>("/api/me/refresh")
        .then((s) => {
          pollFailures.current = 0;
          setRefresh(s);
          if (!s.running) {
            setCharts(null);
            setRecent(null);
            load();
          }
        })
        .catch((e: ApiError) => {
          pollFailures.current += 1;
          if (pollFailures.current >= 5 || e.status === 401) {
            setRefresh({ running: false, stage: "failed", error: "lost connection to the bot. Reload the page or try again in a minute." });
          }
        });
    }, 1500);
    return () => clearInterval(timer);
  }, [refresh, load]);

  const show = (t: Tab) => {
    setTab(t);
    setVisited((v) => (v.has(t) ? v : new Set(v).add(t)));
    if (t !== tab) window.scrollTo({ top: 0 });
  };
  // the chart tab's address names the chart on show, and only that: an area link's query must not ride along
  const chartAddress = (target: LookupTarget) => {
    const params = new URLSearchParams(target.cover ? { cover: target.cover } : { chart: target.title });
    if (target.type) params.set("type", target.type);
    if (target.difficulty) params.set("difficulty", target.difficulty);
    return `${window.location.pathname}?${params}#chart`;
  };
  const pick = (t: Tab) => {
    if (t === tab) return;
    show(t);
    window.history.pushState(null, "", t === "chart" && lookup ? chartAddress(lookup) : `${window.location.pathname}#${t}`);
  };
  const openChart: OpenChart = (title, type, difficulty) => {
    setLookup({ title, type, difficulty });
    show("chart");
    window.history.pushState(null, "", `${window.location.pathname}?chart=${encodeURIComponent(title)}&type=${type}&difficulty=${difficulty}#chart`);
  };
  const signOut = () => postJSON("/auth/logout").then(() => window.location.assign("/"));

  if (signedOut) {
    return (
      <Frame>
        <div className="gate">
          <h1>
            Your scores, <em>on the web</em>.
          </h1>
          <p className="lede">
            See your best 50, all your charts, your rating history and what to play next.
            Sign in with the Discord account you use the bot with.
          </p>
          {oauth && turnstile ? (
            <form method="post" action="/auth/discord" className="signin">
              <Turnstile siteKey={turnstile} action="dashboard" onToken={setHuman} onError={() => setError("The human check didn't load. Reload the page.")} />
              <input type="hidden" name="cf-turnstile-response" value={human} />
              <button className="button pink" type="submit" disabled={!human}>
                sign in with Discord
              </button>
            </form>
          ) : oauth ? (
            <a className="button pink" href="/auth/discord">
              sign in with Discord
            </a>
          ) : (
            <p className="hint">Sign-in isn&apos;t set up on this server yet. The owner needs to add a Discord client ID and secret.</p>
          )}
          {error && <p className="hint">{error}</p>}
          <div className="aside">We only read your Discord ID and name. We don&apos;t post anything or ask for your server list.</div>
          <InstallHint />
        </div>
      </Frame>
    );
  }
  if (!me) {
    return (
      <Frame>
        <div className="gate">{error ? <p className="hint">{error}</p> : queued ? <QueueNote spot={queued} /> : <p className="hint">Loading…</p>}</div>
      </Frame>
    );
  }
  if (!me.linked) {
    return (
      <Frame user={me.user} onSignOut={signOut}>
        <div className="gate">
          <h1>
            No maimai account <em>linked yet</em>.
          </h1>
          <p className="lede">
            You&apos;re signed in, but this Discord account has no maimai account linked. Run <code>/login</code> in Discord, follow the
            link, then come back here.
          </p>
          <a className="button" href="/">
            how linking works →
          </a>
        </div>
      </Frame>
    );
  }

  const p = me.profile!;
  const s = me.snapshot!;
  return (
    <Frame user={me.user} onSignOut={signOut}>
      {me.sessionExpired ? <SessionExpired since={me.sessionExpired} deletesAt={me.sessionDeletesAt} /> : null}
      <section className="ident">
        <div className="ident-who">
          <div className="label">
            {me.region?.toUpperCase()} · <Ago iso={p.updatedAt} prefix="updated " />
          </div>
          <h1>{p.name || "—"}</h1>
          <div className="ident-sub mono">
            {[...new Set([p.dan, p.title].filter(Boolean))].join(" · ") || "no title read yet"} · {num(p.totalPlayCount)} plays
          </div>
          {p.nameplate ? (
            <img className="nameplate" src={p.nameplate} alt="" width={360} height={58}
                 onError={(e) => { e.currentTarget.hidden = true; }} />
          ) : null}
          {me.sinceLast && (me.sinceLast.plays > 0 || me.sinceLast.ratingDelta !== 0) && (
            <div className="since mono">
              since {day(me.sinceLast.since)}: {me.sinceLast.ratingDelta ? `rating ${me.sinceLast.ratingDelta > 0 ? "+" : ""}${me.sinceLast.ratingDelta}` : "rating unchanged"}
              {me.sinceLast.plays ? ` · ${num(me.sinceLast.plays)} play${me.sinceLast.plays === 1 ? "" : "s"}` : ""}
              {me.sinceLast.newBests ? ` · ${me.sinceLast.newBests} new best${me.sinceLast.newBests === 1 ? "" : "s"}` : ""}
            </div>
          )}
        </div>
        <div className="readout big">
          <span className="lbl">rating · {ratingBand(p.rating).key}</span>
          <span className="val">
            <RatingPlate rating={p.rating} />
          </span>
          <span className="lbl">best 50</span>
          <span className="val">{num(s.best50)}</span>
          <span className="lbl">new · old</span>
          <span className="val pair">
            <span>{num(s.newTotal)}</span>
            <span className="sep">·</span>
            <span>{num(s.oldTotal)}</span>
          </span>
        </div>
      </section>

      <Tabs current={tab} onPick={pick} admin={me.admin} />

      {IMAGE_FOR[tab] && (
        <div className="tab-tools">
          {IMAGE_FOR[tab]!.map((kind) => (
            <SaveImage key={kind} kind={kind} />
          ))}
        </div>
      )}

      {refresh?.running && <RefreshBar status={refresh} />}
      {queued && <QueueNote spot={queued} />}

      <main className="panel">
        <div hidden={tab !== "overview"}>
          <OverviewTab me={me} charts={charts} chartsError={chartsError} onRetry={loadCharts} />
        </div>
        {visited.has("picks") && (
          <div hidden={tab !== "picks"}>
            <Picks initial={String(me.settings?.challenge ?? "balanced")} onOpen={openChart} />
          </div>
        )}
        {visited.has("new") && (
          <div hidden={tab !== "new"}>
            <NewCharts
              initialChallenge={String(me.settings?.challenge ?? "balanced")}
              initialDifficulty={String(me.settings?.new_difficulty ?? "any")}
              onOpen={openChart}
            />
          </div>
        )}
        {visited.has("best50") && (
          <div hidden={tab !== "best50"}>
            {chartsError ? <LoadError what="your charts" message={chartsError} onRetry={loadCharts} /> : <Best50 charts={charts} cutoffs={me.analysis?.best50} onOpen={openChart} />}
          </div>
        )}
        {visited.has("charts") && (
          <div hidden={tab !== "charts"}>
            {chartsError ? <LoadError what="your charts" message={chartsError} onRetry={loadCharts} /> : charts ? <Charts rows={charts} onOpen={openChart} /> : <Empty>Loading charts…</Empty>}
          </div>
        )}
        {visited.has("chart") && (
          <div hidden={tab !== "chart"}>
            <Lookup target={lookup} />
          </div>
        )}
        {visited.has("recent") && (
          <div hidden={tab !== "recent"}>
            {recentError ? <LoadError what="your play history" message={recentError} onRetry={loadRecent} /> : <Recent plays={recent} total={me.playHistory ?? 0} onOpen={openChart} />}
          </div>
        )}
        {visited.has("traits") && (
          <div hidden={tab !== "traits"}>
            <Traits
              traits={me.analysis?.profile?.traits ?? []}
              axes={me.analysis?.profile?.traitAxes ?? []}
              families={me.analysis?.profile?.traitFamilies ?? []}
              charts={Number(me.analysis?.profile?.sampleSize ?? 0)}
              practice={me.analysis?.traitPractice ?? []}
              onOpen={openChart}
            />
            <JudgementProfile data={me.judgements ?? null} />
          </div>
        )}
        {visited.has("areas") && (
          <div hidden={tab !== "areas"}>
            <Areas key={me.profile?.updatedAt ?? ""} focus={areaFocus} />
          </div>
        )}
        {visited.has("account") && (
          <div hidden={tab !== "account"}>
            <Account me={me} refresh={refresh} onRefresh={(st) => setRefresh(st)} />
          </div>
        )}
        {me.admin && visited.has("admin") && (
          <div hidden={tab !== "admin"}>
            <AdminPanel />
          </div>
        )}
      </main>
    </Frame>
  );
}

/** Shown above everything when maimai DX NET has refused the saved sign-in: reads stop until it is linked again. */
function SessionExpired({ since, deletesAt }: { since: string; deletesAt?: string }) {
  const when = new Date(since);
  const on = Number.isNaN(when.getTime())
    ? ""
    : ` on ${when.toLocaleDateString(undefined, { day: "numeric", month: "short" })}`;
  const gone = deletesAt ? new Date(deletesAt) : null;
  const until = gone && !Number.isNaN(gone.getTime())
    ? gone.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" })
    : "";
  return (
    <aside className="expired" role="status">
      <b>Your maimai session expired.</b> maimai DX NET stopped accepting your login{on}, so your scores aren&apos;t updating.
      Everything below is from your last refresh. Run <code>/login</code> in Discord to link again.
      {until ? <> If it isn&apos;t linked again by <b>{until}</b>, everything stored for this account is deleted.</> : null}
    </aside>
  );
}

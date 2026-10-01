import { Cmd } from "@/components/Cmd";
import { CONTACT_DISCORD, CONTACT_EMAIL, SITE_URL } from "@/components/Contact";
import { Term } from "@/components/Term";

// Every word the site shows in English, in one place. ja.tsx holds the same keys in Japanese and is
// checked against this file, so a key added here and forgotten there fails the build.

export type ErrorCopy = { headline: [string, string]; detail: string; hint: string };

const contact = (
  <>
    <a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a>, or <b>{CONTACT_DISCORD}</b> on Discord
  </>
);

const errors: Record<string, ErrorCopy> = {
  expired: {
    headline: ["That link has ", "expired"],
    detail: "Login links work once and last about ten minutes.",
    hint: "Run /login in Discord again for a fresh link.",
  },
  invalid_user: {
    headline: ["This link isn't ", "valid"],
    detail: "It's missing your Discord account info, or it was changed.",
    hint: "Run /login in Discord and use the link it gives you as-is.",
  },
  maintenance: {
    headline: ["maimai DX NET is ", "down"],
    detail: "Your Aime sign-in worked, but the maimai DX NET score site is down right now, so your session can't be checked yet.",
    hint: "Your login link still works. Press the bookmark again once the servers are back. The bar at the top shows when.",
  },
  no_login: {
    headline: ["Couldn't read your ", "session"],
    detail: "You may not be signed in to the SEGA gateway yet, or the sign-in didn't stick.",
    hint: "Sign out of the gateway, sign back in, then press the bookmark again. A Japan account links with its SEGA ID instead: run /login region:Japan in Discord.",
  },
  region: {
    headline: ["China accounts can't be linked ", "yet"],
    detail: "China's maimai DX NET only opens inside WeChat, and Rasmai has no way to sign in there yet, so this login can't finish however many times you try.",
    hint: "International and Japan accounts can be linked. If you also play on one of those, run /login in Discord and pick its region.",
  },
  credentials: {
    headline: ["maimaidx.jp said ", "no"],
    detail: "maimaidx.jp didn't accept that SEGA ID, password or Aime card.",
    hint: "Check them on maimaidx.jp, then try again. Your login link still works.",
  },
  rate_limited: {
    headline: ["Too many ", "attempts"],
    detail: "Sign-in attempts from your connection are paused for a few minutes.",
    hint: "Wait ten minutes, then run /login in Discord for a fresh link.",
  },
  upstream: {
    headline: ["maimai said ", "no"],
    detail: "The sign-in was read correctly, but the maimai site rejected it.",
    hint: "The session probably expired partway through. Your login link still works, so sign in to the gateway again and press the bookmark.",
  },
  verify: {
    headline: ["One check was ", "skipped"],
    detail: "You need to pass the human check on the connect page before signing in.",
    hint: "Go back to the connect page, pass the check, then press the bookmark again.",
  },
  unknown: {
    headline: ["Something went ", "wrong"],
    detail: "The connection couldn't be completed.",
    hint: "Run /login in Discord to start over.",
  },
};

export const en = {
  // ---- common
  meta: {
    title: "Rasmai · maimai DX rating bot for Discord",
    tagline: "Rasmai looks at your maimai DX NET scores and tells you which charts to play to raise your rating.",
  },
  common: {
    switchLanguage: "日本語に切り替え",
    themeToggle: "Switch between light and dark",
    themeTitle: "Light / dark",
    dismiss: "Dismiss",
    more: "more",
    period: ".",
  },
  nav: { home: "home", link: "link", commands: "commands", dashboard: "dashboard", invite: "invite" },
  shell: { steps: ["Get your link", "Sign in", "Connect"] },
  footer: {
    createdBy: (
      <>
        Created by <b>nek_ng</b>
      </>
    ),
    notAffiliated: "not affiliated with SEGA",
    privacy: "privacy",
    terms: "terms",
    invite: "invite the bot",
  },
  doc: { effective: (date: string) => `Effective ${date}` },
  servers: {
    anyMinute: "any minute now",
    inMinutes: (n: number) => `in ${n} min`,
    inHours: (n: number) => `in ${n} h`,
    maintenance: "maimai DX NET is in maintenance.",
    down: "maimai DX NET isn't responding right now.",
    back: (when: string, clock: string) => ` Back ${when}, at ${clock} your time.`,
    rest: " Scores here are from the last check. You can't refresh or link an account until it's back.",
  },
  pwa: {
    updated: "A newer version of the site is ready.",
    reload: "reload",
    later: "later",
    hide: "Don't show this again",
    heading: "Add Rasmai to your home screen.",
    prompt: "The dashboard opens full screen like an app.",
    install: "install the app",
    ios: (
      <>
        In Safari tap <b>Share</b> <span className="glyph">⎙</span>, then <b>Add to Home Screen</b>. It opens full screen like an app.
      </>
    ),
    android: (
      <>
        In Chrome open the <b>⋮</b> menu and choose <b>Install app</b> or <b>Add to Home screen</b>. It opens full screen like an app.
      </>
    ),
    other: "You can install this page as an app from your browser's menu. It opens full screen.",
  },
  // ---- home
  home: {
    metaTitle: "maimai DX rating bot for Discord",
    eyebrow: "A Discord bot for maimai DX",
    title: (
      <>
        See which charts to <em>play next</em>.
      </>
    ),
    lede: "Rasmai looks at your maimai DX NET scores and tells you which charts to play to raise your rating. You get the results as images in Discord or on the web dashboard, and you can look up any chart's patterns before you play it.",
    addToDiscord: "add to Discord",
    openDashboard: "open your dashboard",
    demoLabel: "What a result looks like",
    demoEyebrow: "what to play next",
    demoName: "your name here",
    demoTotal: "total gain",
    columns: { chart: "Chart", achievement: "Achievement", rank: "Rank", odds: "Odds", gain: "Gain" },
    demoFoot: "example · yours uses your scores",
    features: [
      { mark: "rank_sssp", title: "What to grind for rating", body: "Goes through your scores and lists the charts where a better score would raise your rating the most.", command: "/analyze" },
      { mark: "up", title: "Pick how hard you want it", body: "Easier gives safer targets and Balanced gives the best expected gain. Challenging goes for bigger gains that are still doable. You can switch it from a dropdown on the reply.", command: "/analyze challenge" },
      { mark: "best50", title: "Plan your next thousand", body: "A list of targets that add up to your next rating milestone, with the odds for each and a running total.", command: "/plan" },
      { mark: "plays", title: "Plan a session", body: "Tell it how many credits you have and it plans each one, warm-ups first. A chart only repeats if you missed it the first time, and you can see how much rating the session could get you.", command: "/session" },
      { mark: "new", title: "New charts to try", body: "Charts you haven't played yet that fit your level, with a guess at what you'd score first try. Add a focus to lean toward patterns you're weak or strong at.", command: "/new focus" },
      { mark: "pb", title: "Where you lose points", body: "Your scores grouped by chart pattern and compared to your own curve. It also shows how well the predictions have matched your new bests.", command: "/profile" },
      { mark: "diff_master", title: "Look up a chart", body: "Shows your score, the predicted score, what each rank is worth and the chart's patterns. The song's other difficulties and a score history graph are a button away. You can also browse every chart with a given pattern.", command: "/chart  /charts" },
      { mark: "rasmai", title: "Track your rating", body: "Your rating over time, how fast it's going up, when you'd hit each milestone at that pace, and how many credits the route would take.", command: "/progress" },
      { mark: "festival", title: "Check your plays", body: "Pattern tags show what's in a chart before you play it. After a play, the play log shows every judgement so you can see where you lost points.", command: "/charts  /recent play:1" },
    ],
    linkingTitle: "Linking your account",
    linking: (
      <>
        Run <code>/login</code> in Discord and follow the link. For an International account you sign in at my-aime.net, open the Aime
        authentication, then press a bookmark once, and Rasmai only gets the session it needs and never sees your password. A Japan account
        links with its SEGA ID and password on the next page instead, kept encrypted. <code>/delete-account</code> deletes everything Rasmai
        has on you.
      </>
    ),
    linkingButton: "how linking works →",
    dashboardTitle: "The dashboard",
    dashboard: "Sign in with Discord to see your rating over time, how you play, your best 50, all your scores with filters, the same picks as the bot, and 40 unplayed charts to try.",
    dashboardButton: "open the dashboard →",
    phoneHint: "On a phone, add the dashboard to your home screen and it opens like an app.",
    commandsTitle: "Commands",
    commands: [
      ["/login", "link your maimai DX NET account"],
      ["/analyze", "what to grind, at the difficulty you pick"],
      ["/plan", "a route to your next rating milestone"],
      ["/session", "plan your credits for a session"],
      ["/new", "unplayed charts at your level, with an option to focus on weak spots"],
      ["/chart  /charts", "look up one chart, or list charts by pattern or level"],
      ["/b50  /dxscore", "your best 50 (also /top) and DX score stars"],
      ["/recent", "your recent plays, or one play in detail with play:1"],
      ["/progress", "your rating over time and when you'll hit the next thousand"],
      ["/compare  /leaderboard", "you vs a friend, or a server leaderboard (opt-in)"],
      ["/random  /profile  /export", "a random chart, how you play, a copy of your data"],
      ["/settings  /invite", "your defaults and daily score check, and the invite link"],
    ] as [string, string][],
  },
  // ---- link
  link: {
    metaTitle: "Link your maimai account",
    metaDescription: "How to link your maimai DX NET account to Rasmai on a computer or iPhone, with a video.",
    title: (
      <>
        Link your <em>maimai</em> account.
      </>
    ),
    lede: "Once you're linked, Rasmai checks your scores and tells you which charts to play to raise your rating.",
    videoTitle: "Watch the video first",
    videoBody: "Pick your device. It's about a minute long with no sound.",
    step1Title: "Get your link",
    step1: (
      <>
        Run <code>/login</code> in Discord. You&apos;ll get a private link to this site with your login code already filled in.
      </>
    ),
    step2Title: "Sign in at my-aime, then authenticate",
    step2: (
      <>
        Sign in at <a href="https://my-aime.net/en/">my-aime.net</a> with the account you play on, then open the Aime authentication from the
        setup page. That takes you to the gateway page.
      </>
    ),
    step3Title: "Start grinding",
    step3: (
      <>
        Back in Discord, run <code>/analyze</code> to see what to play or <code>/plan</code> to plan your next thousand.
      </>
    ),
    japan: (
      <>
        <b>Playing on a Japan account?</b> Run <code>/login region:Japan</code> instead. The link opens a page where you enter the SEGA ID
        and password you use on maimaidx.jp, so steps 2 and the video don&apos;t apply.
      </>
    ),
    already: (
      <>
        <b>Already linked?</b> Your scores are on the web too. <a href="/me/">Open your dashboard</a> and sign in with Discord.
      </>
    ),
  },
  walkthrough: {
    desktop: "On a computer",
    desktopNote: "Works the same in Chrome, Edge and Firefox.",
    ios: "On iPhone",
    iosNote: "Safari on iOS. Android works the same way in Chrome.",
    videoLabel: (device: string) => `${device}: the full linking process`,
    tabs: "which device you are linking on",
  },
  // ---- flow
  errors,
  flow: {
    loading: "Loading…",
    period: ".",
    nothingSaved: "nothing was saved",
    validUntil: (time: string) => `link valid until ${time}`,
    labelValidUntil: "link valid until",
    labelRegion: "region",
    connectedAs: (name: string) => `Connected as ${name}.`,
    connected: "Connected.",
    waiting: "Waiting for the sign-in…",
    stopped: "Stopped checking. Reload to keep waiting.",
    neverSeesPassword: "Rasmai never sees your password",
    segaIdEncrypted: "your SEGA ID is stored encrypted",
    // the human check
    checkTitle: (
      <>
        One quick <em>check</em>.
      </>
    ),
    checkLedeJapan: "Pass the human check to get the sign-in form.",
    checkLede: "Pass the human check to get your link and the connect bookmark.",
    checkFailed: "The check failed. Reload the page and try again.",
    checkWhy: (japan: boolean) => (
      <>
        <b>Why?</b> The next screen gives Rasmai {japan ? "your maimaidx.jp sign-in" : "your maimai session"}, and the check stops bots from
        grabbing it.
      </>
    ),
    // the International bookmark
    device: "Your device",
    devices: { desktop: "Computer", ios: "iPhone / iPad", android: "Android" },
    titleMobile: (
      <>
        Set up the <em>bookmark</em>, then sign in.
      </>
    ),
    titleDesktop: (
      <>
        Drag in the <em>bookmark</em>, then sign in.
      </>
    ),
    ledeMobile: "Set up the bookmark, sign in at my-aime and open the Aime authentication. Then run the bookmark there. This page updates when you're connected.",
    ledeDesktop: "Keep this tab open. It updates when you're connected.",
    dragTitle: "Drag this to your bookmarks bar",
    drag: (
      <>
        Grab the pink button and drop it on your browser&apos;s bookmarks bar. If the bar is hidden, press <code>Ctrl+Shift+B</code> (
        <code>⌘+Shift+B</code> on a Mac) first.
      </>
    ),
    copyInstead: "copy instead",
    copiedHint: "Copied. Paste it as a bookmark's address.",
    makeTitle: "Make the connect bookmark",
    makeBody: "Copy the bookmark code, then save it as a bookmark like this.",
    copied: "✓ copied",
    copyCode: "copy bookmark code",
    ios: [
      <>
        Tap <b>Share</b> <span className="glyph">⎙</span> → <b>Add Bookmark</b> → <b>Save</b>. Name it <b>maimai connect</b>.
      </>,
      <>
        Open <b>Bookmarks</b> <span className="glyph">📖</span> → <b>Edit</b> → tap the new bookmark.
      </>,
      <>
        Replace its <b>address</b> with what you copied → <b>Done</b>.
      </>,
    ],
    android: [
      <>
        Tap <b>⋮</b> → <b>☆</b> to bookmark this page.
      </>,
      <>
        Tap <b>⋮</b> → <b>Bookmarks</b>, then <b>⋮</b> on the new bookmark → <b>Edit</b>.
      </>,
      <>
        Name it <b>maimai connect</b>, replace the <b>URL</b> with what you copied, and go back to save.
      </>,
    ],
    signInTitle: "Sign in at my-aime, then authenticate",
    signIn: (mobile: boolean) =>
      `First sign in at my-aime.net with the account you play on${mobile ? "" : " (opens in a new tab)"}. Then open the Aime authentication, which takes you to the gateway page.`,
    signInButton: "1 · sign in at my-aime →",
    authButton: "2 · open the Aime authentication →",
    runTitle: "Run the bookmark on the AIME page",
    runDesktop: (
      <>
        When you&apos;re on the gateway page, click the <b>maimai connect</b> bookmark. This page updates once it&apos;s done.
      </>
    ),
    runIos: (
      <>
        When you&apos;re on the gateway page, open <b>Bookmarks</b> <span className="glyph">📖</span> and tap <b>maimai connect</b>. Then come
        back to this tab.
      </>
    ),
    runAndroid: (
      <>
        When you&apos;re on the gateway page, tap the <b>address bar</b>, type <b>maimai connect</b> and pick the bookmark from the suggestions.
        Pasting the code into the address bar won&apos;t work in Chrome. Then come back to this tab.
      </>
    ),
    stuck: (
      <>
        <b>Stuck?</b> If the bookmark says it can&apos;t read your login, sign out of the gateway, sign in again, then run it again. If the link
        expired, run <code>/login</code> in Discord for a new one. This bookmark is for International accounts. A Japan account links with its
        SEGA ID instead: run <code>/login region:Japan</code>. Accounts from the Chinese version can&apos;t be linked yet.
      </>
    ),
    // the Japan sign-in
    jpTitle: (
      <>
        Sign in with your <em>SEGA ID</em>.
      </>
    ),
    jpLede: "maimaidx.jp has no sign-in Rasmai can borrow the way the international site does, so Rasmai signs in there with your SEGA ID whenever it reads your scores.",
    jpStepTitle: "Your maimaidx.jp sign-in",
    jpStep: (
      <>
        The SEGA ID and password you use on{" "}
        <a href="https://maimaidx.jp/maimai-mobile/" target="_blank" rel="noopener noreferrer">
          maimaidx.jp
        </a>
        .
      </>
    ),
    segaId: "SEGA ID",
    password: "Password",
    aimeCard: "Aime card",
    aimeHint: "One SEGA ID can hold several Aime cards, each its own player. Leave this at 1 unless yours has more than one.",
    remember: "Save my login for next time",
    rememberHint: "Remembers your SEGA ID and card on this device only. Your password is never saved here; your browser can offer to save it.",
    signingIn: "signing in…",
    signInAndLink: "sign in and link",
    signingInJp: "Signing in to maimaidx.jp…",
    unreachableJp: "Rasmai couldn't reach maimaidx.jp just now. Try again in a few minutes. Your login link still works.",
    failed: "The sign-in didn't work. Try again in a moment.",
    offline: "Couldn't reach Rasmai. Check your connection and try again.",
    keeps: (
      <>
        <b>What Rasmai keeps.</b> Your SEGA ID and password are encrypted before they&apos;re stored, and they&apos;re used only to sign in to
        maimaidx.jp and read your scores. They&apos;re deleted when you run <code>/logout</code> or <code>/delete-account</code>. If you change the
        password, run <code>/login</code> again.
      </>
    ),
    // done
    linkedTitle: (
      <>
        You&apos;re <em>linked</em>.
      </>
    ),
    signedInAs: (name: string) => (
      <>
        Signed in as <b>{name}</b>. Rasmai can check your scores now.
      </>
    ),
    linkedGeneric: "Your maimai account is now linked to your Discord account.",
    rating: "rating",
    backInDiscord: "Back in Discord",
    nextCommands: [
      ["/analyze", "what to grind, biggest gains first"],
      ["/plan", "a plan for your next thousand"],
      ["/new", "charts you haven't played that fit your level"],
      ["/profile", "how you play and where you lose points"],
    ] as [string, string][],
    closeTab: "You can close this tab.",
  },
  // ---- pages
  privacy: {
    metaTitle: "Privacy",
    metaDescription: "What Rasmai stores about you and how to delete it.",
    title: (
      <>
        What Rasmai <em>stores</em> about you.
      </>
    ),
    intro: "Rasmai is a Discord bot that checks your maimai DX scores and tells you what to grind. This page lists what it stores, how long it keeps it and how to delete it. There's no tracking, analytics or ads.",
  },
  terms: {
    metaTitle: "Terms",
    metaDescription: "What you agree to when you use Rasmai.",
    title: (
      <>
        Terms of <em>use</em>.
      </>
    ),
    intro: "Rasmai is a free, fan-made tool. By using the bot or this site you agree to the terms below.",
  },
  notFound: {
    metaTitle: "not found",
    metaDescription: "This page doesn't exist.",
    foot: "404 · nothing was saved",
    title: (
      <>
        Page not <em>found</em>.
      </>
    ),
    lede: "This page doesn't exist or it moved. Here are some pages that do.",
    whereTitle: "Where to go",
    home: (
      <>
        <a href="/">Home</a> to see what Rasmai does and how to add it.
      </>
    ),
    link: (
      <>
        <a href="/link/">Link your account</a> if you came here from <code>/login</code>. If your link expired, run the command again in
        Discord for a new one.
      </>
    ),
    dashboard: (
      <>
        <a href="/me/">Your dashboard</a>, after signing in with Discord.
      </>
    ),
    bookmark: (
      <>
        <b>Came from the bookmark?</b> Connect links work once and last about ten minutes. Run the bookmark on the SEGA gateway page, not on
        this site.
      </>
    ),
  },
  commands: {
    metaTitle: "Commands",
    metaDescription: "Every Rasmai command and what it does, with the maimai terms explained.",
    title: (
      <>
        Commands and <em>what they do</em>.
      </>
    ),
    intro: "Hover or tap a word with a dotted underline to see what it means. Commands work in servers and DMs, or anywhere if you add Rasmai to your account.",
  },
  // ---- dash
  dash: {
    metaTitle: "dashboard",
    metaDescription: "Your maimai scores, best 50 and what to play next.",
    chartConstant: "chart constant",
    never: "never",
    justNow: "just now",
    minAgo: (n: number) => `${n} min ago`,
    hAgo: (n: number) => `${n} h ago`,
    daysAgo: (n: number) => `${n} days ago`,
    couldntLoad: (what: string, message: string) => `Couldn't load ${what}. ${message}`,
    tryAgain: "try again",
    moreInfo: "more info",
    images: {
      analyze: "what to play",
      profile: "play profile",
      new: "new charts",
      traits: "traits",
      progress: "rating over time",
      best50: "best 50",
      recent: "recent plays",
    },
    saveTitle: (what: string) => `Save the ${what} image the bot posts in Discord`,
    makingImage: "making image…",
    noImageData: "no data for this yet",
    imageFailed: "couldn't make the image",
    saveImage: (what: string) => `save ${what}`,
    signOut: "sign out",
    footRight: "scores update from maimai DX NET when you run a command or refresh here",
    sections: "Sections",
    tabs: {
      overview: "Overview",
      picks: "What to play",
      new: "New charts",
      traits: "Traits",
      best50: "Best 50",
      charts: "All charts",
      recent: "Recent",
      chart: "Look up",
      areas: "Areas",
      account: "Account",
      admin: "Developer",
    },
    stages: {
      queued: "Waiting for a free slot",
      login: "Signing in to maimai DX NET",
      scores: "Reading score pages",
      recent: "Recent plays",
      extras: "Albums and events",
      plays: "Play counts",
      analysis: "Picking charts for you",
      done: "Done",
      failed: "Failed",
    } as Record<string, string>,
    readingScores: (what: string) => `Reading your scores from maimai · ${what}`,
    queueNow: "Building your analysis now…",
    queueBusy: (position: number, wait: string) =>
      `It's busy right now. You're #${position} in the queue, about ${wait} left. The page will update when it's done.`,
    seconds: (n: number) => `${n}s`,
    minutes: (n: number) => `${n} min`,
    signInErrors: {
      discord: "Discord didn't confirm the sign-in. Try again.",
      state: "That sign-in link expired. Try again.",
      oauth_unconfigured: "Sign-in isn't set up on this server yet.",
      verify: "The human check failed. Try again.",
    } as Record<string, string>,
    turnstileFailed: "The human check didn't load. Reload the page.",
    lostConnection: "lost connection to the bot. Reload the page or try again in a minute.",
    gateTitle: (
      <>
        Your scores, <em>on the web</em>.
      </>
    ),
    gateLede: "See your best 50, all your charts, your rating history and what to play next. Sign in with the Discord account you use the bot with.",
    signInDiscord: "sign in with Discord",
    notSetUp: "Sign-in isn't set up on this server yet. The owner needs to add a Discord client ID and secret.",
    gatePrivacy: "We only read your Discord ID and name. We don't post anything or ask for your server list.",
    loading: "Loading…",
    loadingCharts: "Loading charts…",
    notLinkedTitle: (
      <>
        No maimai account <em>linked yet</em>.
      </>
    ),
    notLinkedLede: (
      <>
        You&apos;re signed in, but this Discord account has no maimai account linked. Run <code>/login</code> in Discord, follow the link,
        then come back here.
      </>
    ),
    howLinking: "how linking works →",
    updated: "updated ",
    noTitle: "no title read yet",
    plays: (n: string) => `${n} plays`,
    since: (day: string, delta: number, plays: number, newBests: number, fmt: (n: number) => string) =>
      `since ${day}: ${delta ? `rating ${delta > 0 ? "+" : ""}${delta}` : "rating unchanged"}` +
      (plays ? ` · ${fmt(plays)} play${plays === 1 ? "" : "s"}` : "") +
      (newBests ? ` · ${newBests} new best${newBests === 1 ? "" : "s"}` : ""),
    rating: "rating",
    best50: "best 50",
    newOld: "new · old",
    bands: {
      white: "white", blue: "blue", green: "green", yellow: "yellow", red: "red", purple: "purple",
      bronze: "bronze", silver: "silver", gold: "gold", platinum: "platinum", rainbow: "rainbow", kiwami: "kiwami",
    } as Record<string, string>,
    yourCharts: "your charts",
    yourHistory: "your play history",
    expired: (on: string, until: string) => (
      <>
        <b>Your maimai session expired.</b> maimai DX NET stopped accepting your login{on ? ` on ${on}` : ""}, so your scores aren&apos;t
        updating. Everything below is from your last refresh. Run <code>/login</code> in Discord to link again.
        {until ? (
          <>
            {" "}
            If it isn&apos;t linked again by <b>{until}</b>, everything stored for this account is deleted.
          </>
        ) : null}
      </>
    ),
    api: {
      bot_unreachable: "Can't reach the bot right now. It might be restarting, so try again in a minute.",
      rate_limited: "Too many requests. Wait a moment and try again.",
      signed_out: "Your sign-in expired. Sign in again.",
      bad_response: "Couldn't read the server's response.",
      not_linked: "No maimai account is linked to this Discord account yet.",
      notFound: "Not found.",
      server: "Something went wrong on the server. Try again in a moment.",
      network: "Couldn't connect. Check your internet and try again.",
      generic: (status: number) => `Something went wrong (${status}).`,
    },
  },
  // ---- dashboard: overview tab
  overviewTab: {
    howInfo: "Comfortable up to is the highest constant you score well on every time. S expected up to is the highest constant you should S on your first try.",
    how: "how you play",
    comfort: "comfortable up to",
    reach: "S expected up to",
    hardestS: "hardest S",
    age: "charts you pick",
    ageValue: (years: string, fresh: number) => `${years} yr old · ${fresh}% under a year`,
    rerates: "from re-rating",
    reratesValue: (rating: string, charts: number) => `${rating} over ${charts} charts`,
    notes: "notes hit",
    warmUp: "first track of a credit",
    warmUpValue: (gap: string, colder: boolean) => `${gap}% ${colder ? "under" : "over"} the rest`,
    scored: "charts scored",
    upper: "expert and up",
    fullCombos: "full combos",
    fullCombosValue: (all: string, ap: string) => `${all} (${ap} all perfect)`,
    fullSync: "full sync+",
    reachable: "reachable from your picks",
    cutoffsInfo: "Your rating is your 15 best charts from the current version plus your 35 best from older ones. Enters at is the chart rating you need to get in.",
    cutoffs: "best 50 cutoffs",
    newPool: "new pool (15)",
    oldPool: "old pool (35)",
    entersAt: (total: string, cutoff: number) => `${total} · enters at ${cutoff}`,
    open: (n: number) => ` · ${n} open`,
    ranksInfo: "How many of your Expert, Master and Re:Master scores are at each rank.",
    ranks: "ranks · expert and up",
    levelsInfo: "Your average achievement at each level, Expert and up. The bar goes from 80% to 100%.",
    levels: "average achievement by level · expert and up",
    charts: (n: number) => `${n} charts`,
  },
  // ---- dashboard: best 50 tab
  best50Tab: {
    newInfo: "Your 15 best chart ratings on current version songs. Enters at is the chart rating you need to get in.",
    oldInfo: "Your 35 best chart ratings on older songs. Enters at is the chart rating you need to get in.",
    total: (n: string) => `${n} total`,
    entersAt: (n: number) => ` · enters at ${n}`,
    jacket: "jacket",
    chart: "chart",
    achievement: "achievement",
    constRating: "const → rating",
    averages: (n: number) => `averages over the ${n} charts in your best 50`,
    avgConstant: "avg constant",
    avgAchievement: "avg achievement",
    avgRating: "avg rating",
    newVersion: "new version",
    older: "older versions",
  },
  // ---- dashboard: account tab
  accountTab: {
    accountInfo: "The maimai DX NET account linked to your Discord. History points are the saved ratings behind the graph on Overview.",
    account: "maimai account",
    player: "player",
    region: "region",
    lastRead: "last read",
    historyPoints: "history points",
    refreshing: "refreshing…",
    refresh: "refresh scores",
    download: "download JSON",
    import: "import JSON",
    failed: (why: string) => `Refresh failed: ${why}`,
    refreshed: "Refreshed ",
    imported: (plays: number, bests: number, points: number, counts: number) =>
      `Imported ${plays} plays, ${bests} bests, ${points} rating points and ${counts} play counts. Reloading…`,
    notJson: "That file isn't JSON.",
    takes: "Takes about a minute. It's the same refresh the Discord commands do, and your picks update after.",
    importHint: "You can import an export back in. It won't overwrite anything. Import your oldest file first so each best keeps the date you set it.",
    settingsInfo: "Your defaults for the Discord commands.",
    settings: "bot settings",
    layout: "default layout",
    layouts: { both: "image and text", embed: "text only", image: "image only" } as Record<string, string>,
    targets: "default targets",
    challenges: { easy: "easier", balanced: "balanced", hard: "challenging", extreme: "long shots" } as Record<string, string>,
    newDifficulty: "default /new difficulty",
    any: { any: "any" } as Record<string, string>,
    compare: "open to /compare",
    leaderboard: "server leaderboards",
    history: "daily history read",
    notify: "daily note by DM",
    on: "on",
    off: "off",
    change: (
      <>
        Change these with <code>/settings</code> in Discord.
      </>
    ),
    unlink: "unlink",
    unlinkHint: "Deletes your maimai session, scores, history and play counts. You stay signed in with Discord here.",
    unlinkYes: "yes, unlink and delete",
    keep: "keep it",
    unlinkAsk: "unlink maimai account…",
  },
  list: { sep: ", " },
  // ---- dashboard: table columns, shared by the tabs (they also label each cell on a phone)
  cols: {
    chart: "Chart", now: "Now", target: "Target", rank: "Rank", odds: "Odds", plays: "Plays", gain: "Gain", total: "Total",
    aimFor: "Aim for", firstPass: "First pass", oddsS: "Odds of S", usually: "Usually", needs: "Needs", genre: "Genre",
    constant: "Const", worth: "Worth", achievement: "Achievement", lamp: "Lamp", dx: "DX score", rating: "Rating", time: "Time",
    jacket: "jacket",
  },
  // ---- dashboard: the target levels the picks and new charts share
  challenge: {
    label: { easy: "Easier", balanced: "Balanced", hard: "Challenging", extreme: "Long shots" } as Record<string, string>,
    picksNote: {
      easy: "safest targets, about 50/50 odds",
      balanced: "best gain for the effort, about 1 in 4",
      hard: "harder targets, about 1 in 6",
      extreme: "biggest gains, about 1 in 10",
    } as Record<string, string>,
    newNote: {
      easy: "charts you'll almost surely S",
      balanced: "best value right under your S limit",
      hard: "the hardest charts you can still S",
      extreme: "above your S limit, first try is a gamble",
    } as Record<string, string>,
  },
  // ---- dashboard: what to play tab
  picksTab: {
    howHard: "How hard the targets are",
    filtered: (scope: string) => ` · picks and new charts filtered to ${scope}. The road isn't filtered.`,
    onlyLevel: "Only this level",
    anyLevel: "any level",
    level: (l: string) => `level ${l}`,
    constantPlaceholder: "or a constant like 13.2 or 13.0-13.4",
    onlyConstant: "Only this constant or range",
    scopeHint: "Use a level like 13+, a constant like 13.2, or a range like 13.0-13.4.",
    thePicks: "the picks",
    finding: "Finding charts for you…",
    nothing: (scope: string, level: string) => `Nothing at ${scope || "this level"} would raise your best 50 on ${level}. Try a harder setting or clear the filter.`,
    fallback: (from: string) => `Nothing on ${from} would raise your best 50 yet, so here are the Balanced picks.`,
    grindInfo: "Charts you've played where a better score raises your rating the most. Target is a score you have a fair shot at, and Gain is the rating you'd get from it.",
    grind: (n: number) => `grind these · ${n} charts · `,
    everyTarget: " if you hit every target",
    noMovers: "None of your played charts would raise your best 50 here. Try another setting or check the new charts below.",
    estimated: "not in the chart database yet · constant guessed from its level · ",
    neverExpect: (n: string) => `never played · expect ~${n}% first try`,
    usually: (n: string) => `you usually score ~${n}% here`,
    dropped: " · your only play here was way under that, so it counts as a dropped run",
    new: "new",
    triesInfo: "Unplayed charts, shown because the grind list is short. Some could add rating on a good first run, and some are practice for patterns you lose points on.",
    tries: (n: number) => `worth a first run · ${n} charts`,
    banks: "banks",
    roadInfo: "Targets that together get you to the next rating milestone. The % is how far above your usual score they are, so lower is easier.",
    road: (goal: string) => `road to ${goal}`,
    covers: (n: number) => `covers all +${n}`,
    partway: (total: number, needed: number, short: number) => `+${total} of the +${needed} needed · ${short} short`,
    stretch: (n: string) => `${n}% above your usual score`,
    noRoute: "No route at this setting yet. Try a different one.",
    neverPlayed: "never played",
    plays: (n: number) => `${n} plays`,
    playsUnknown: "plays unknown",
    newInfo: "Unplayed charts where a first try could get into your best 50. Banks means the score counts but won't raise your rating yet.",
    newCharts: (from: string, to: string) => `new charts to try · ${from}–${to}`,
    noNew: "No unplayed charts in this range.",
    nearInfo: "Charts that would get into your best 50 if you score your usual at their level. Needs is the score it takes to get in.",
    near: "within reach of your best 50",
    noNear: "No charts are close to your best 50 right now.",
  },
  // ---- dashboard: new charts tab
  newTab: {
    howHard: "How hard to look",
    difficulty: "Difficulty",
    expertUp: "Expert and up",
    level: "Level",
    lean: "Lean toward a trait",
    anyTrait: "any trait",
    weak: "your weak spots",
    strong: "your strengths",
    leaning: (weak: boolean) => `Leaning toward ${weak ? "your weak spots" : "your strengths"}: `,
    anyNote: (note: string) => `${note}. Charts you haven't played on this account in this constant range. First pass is a bit under what you usually score at that constant.`,
    levelNote: (level: string, mode: string) => `Every level ${level} chart you haven't played on this account, sorted for ${mode}. First pass is a bit under what you usually score at that constant.`,
    theNew: "the new charts",
    looking: "Looking for charts…",
    headInfo: "First pass is your expected score on a first try. Worth is the rating an S would add.",
    head: (n: number, level: string, from: string, to: string) => `${n} charts · ${level !== "any" ? `level ${level} · ` : ""}constants ${from}–${to}`,
    sorted: (mode: string) => `sorted for ${mode}`,
    allPlayed: (level: string) => `You've played every level ${level} chart at this difficulty, or there aren't any.`,
    noneHere: "No unplayed charts in this range.",
    tryAnother: " Try another level or difficulty.",
    thisVersion: "this version",
    banks: (n: number) => `banks ${n}`,
  },
  // ---- dashboard: all charts tab
  chartsTab: {
    sorts: {
      "rating|d": "rating, high first", "bestMatch|d": "best search match", "constant|d": "constant, high first", "constant|a": "constant, low first",
      "accuracy|a": "weakest first", "accuracy|d": "strongest first", "dx|d": "DX score, high first", "plays|d": "most played", "title|a": "title, A to Z",
    } as Record<string, string>,
    search: "title, artist, level 13+ or constant 13.8",
    allDiffs: "all difficulties",
    type: "Chart type",
    bothTypes: "DX and standard",
    dxOnly: "DX only",
    stdOnly: "standard only",
    anyRank: "any rank",
    belowA: "below A",
    pool: "Pool",
    allCharts: "all charts",
    inBest50: "in my best 50",
    current: "current version",
    older: "older versions",
    sort: "Sort",
    countInfo: "Every chart you have a score on. Lamp shows your FC and FS marks.",
    count: (shown: string, all: string) => `${shown} of ${all} charts`,
    totalRating: (n: string) => `${n} total rating`,
    noMatch: "Nothing matches those filters.",
    best50: "best 50",
    estimatedTitle: "Not in the chart database yet, so the constant and rating are guesses based on its level. The database updates when a refresh finds a new song.",
    estimated: "new song · constant estimated",
    more: (n: number) => `show ${n} more`,
  },
  // ---- dashboard: recent tab
  recentTab: {
    judgements: "judgements",
    fastLate: (fast: number, late: number, combo: string, max: string) => `fast ${fast} · late ${late} · combo ${combo} / ${max}`,
    sync: (n: string, max: string) => ` · sync ${n} / ${max}`,
    notes: "notes",
    lost: "lost",
    all: "all",
    pointsLost: "points lost",
    couldntLoad: "couldn't load this play",
    none: (
      <>
        No plays saved yet. Hit refresh on the Account tab or run any command in Discord. Turn on the daily refresh with <code>/settings history</code> so
        plays don&apos;t fall off maimai&apos;s 50-play list between refreshes.
      </>
    ),
    saved: (n: string, since: string) => `${n} plays saved since ${since}`,
    linking: "linking",
    latest: (n: string) => `, showing the latest ${n}`,
    stay: ". Plays stay here as long as your account is linked.",
    day: (n: number, bests: number) => `${n} plays · ${bests} new bests`,
    newBest: "new best",
    loadingPlay: "loading the play from maimai DX NET…",
    more: (n: number) => `show ${n} more`,
  },
  // ---- dashboard: look up tab
  lookupTab: {
    notInDb: (title: string, yours: string, one: boolean) =>
      `"${title}" isn't in the chart database yet. The song is newer than the database, so the jacket, constants and this page will show up once it's added. For now your score${one ? "" : "s"} (${yours}) count${one ? "s" : ""} with a constant guessed from the level.`,
    yourRow: (difficulty: string, level: string, accuracy: string) => `${difficulty} ${level} at ${accuracy}%`,
    noSong: (title: string) => `No song in the chart database matches "${title}".`,
    placeholder: "title, artist or charter",
    label: "Search for a song",
    searchFailed: (why: string) => `Search failed. ${why}`,
    noMatches: "No matches. Try part of the title, the romaji reading, or the artist or charter.",
    chartedBy: (who: string) => `charted by ${who}`,
    neverPlayed: "never played",
    looking: "Looking it up…",
    intro: "Search for a song to see your scores, your odds for each rank, your score history and the chart video. Clicking a song title on any other tab opens it here too.",
  },
  // ---- dashboard: one chart, in the look up tab
  detail: {
    constNote: (n: string) => ` · const ${n} when first recorded`,
    stars: (n: number) => `${n} of 5 DX stars`,
    regions: { jp: "Japan", intl: "International", cn: "China" } as Record<string, string>,
    regionsTitle: "regions that have this chart",
    everywhere: "every region",
    only: " only",
    tier: { basic: "Basic", advanced: "Advanced", expert: "Expert", master: "Master", remaster: "Re:Master" } as Record<string, string>,
    bpm: (n: number | string) => `BPM ${n}`,
    currentVersion: "current version",
    artistUnknown: "artist unknown",
    charts: "Charts of this song",
    constant: (n: string) => ` · constant ${n}`,
    notes: (n: string) => ` · ${n} notes`,
    chartedBy: (who: string) => ` · charted by ${who}`,
    added: (when: string) => ` · added ${when}`,
    removed: "removed from the game",
    tagged: "tagged by maiノーツ editors",
    measured: "measured from the chart's notes",
    clickTrait: " · click to see every chart with this",
    clickOne: "Click one to see every chart with it. ",
    communityNote: "Solid tags come from maiノーツ editors. Dashed ones are measured from the chart's notes, BPM and density.",
    measuredNote: "These are measured from the chart's notes, BPM and density. maiノーツ editors haven't tagged this one. They mostly tag Master charts.",
    offsetNote: " The number is how your scores on it compare to your curve.",
    yourScore: "your score",
    rating: (n: number) => `rating ${n}`,
    lamp: "lamp",
    dx: "DX score",
    of: (n: string) => `of ${n} · `,
    maxUnknown: "max unknown",
    plays: "plays",
    fromNet: "from maimai DX NET",
    playsUnknown: "unknown until the next refresh",
    best50: "best-50",
    neverPlayed: "never played",
    usual: (n: string) => `you'd usually get ~${n}% here`,
    prediction: "prediction",
    range: (low: string, high: string) => `${low} to ${high} on a good run`,
    newBest: (n: number) => `${n}% chance the next run is a new best`,
    firstTry: "first try, based on how you play this level",
    tierOffset: (tier: string, n: string) => ` · your ${tier} scores are ${n} vs your curve`,
    ladderInfo: "What each rank needs, the rating it gives, what it adds to your best 50 and your odds of getting it. Highlighted rows are realistic.",
    ladderPlayed: "what each rank is worth",
    ladderNew: "what each rank would be worth",
    ladderHintPlayed: "gain is what it adds to your best 50 · odds are how often you score that here",
    ladderHintNew: "odds are for a first try",
    need: "Need",
    unlockInfo: "Unlock condition from SilentBlue RemyWiki. If it's an area, your distance there is shown too.",
    unlock: "how to unlock",
    fromWiki: "from SilentBlue RemyWiki",
    loadingWiki: "Loading from the wiki…",
    areaProgress: (title: string, where: string) => `your ${title} progress: ${where}`,
    notStarted: "not started",
    completed: ", completed",
    nextAt: (km: string) => `, next reward at ${km} km`,
    noUnlock: "No unlock condition on the wiki, so it should be unlocked by default.",
    noPage: "The wiki has no page for this song yet.",
    historyInfo: "Every play of this chart the bot has saved. Dots are plays and the line is your best.",
    history: "score history",
    points: (n: number) => `${n} points`,
    watch: "watch the chart on YouTube",
    searchYoutube: "search YouTube for the chart",
  },
  // ---- dashboard: browse charts by trait
  patterns: {
    open: "or browse charts by trait",
    placeholder: "Search traits (streams, 乱打, slide-heavy…)",
    label: "Search traits",
    anyDifficulty: "any difficulty",
    close: "close",
    noMatch: (find: string) => `No traits match “${find}”.`,
    taggedTitle: (n: number) => `tagged by maiノーツ · ${n} charts`,
    measuredTitle: (n: number) => `measured from each chart · ${n} charts`,
    intro: "Solid traits are tagged by maiノーツ editors, who've covered a third of Master charts. Dashed ones are measured from the chart. Pick one to see every chart with it, hardest first.",
    measured: " · measured from each chart",
    charts: (n: number) => ` · ${n} charts`,
    played: (n: number) => `, ${n} played`,
    updating: " · updating…",
    none: "No charts with this trait at that level or difficulty. Try a different filter.",
    neverPlayed: "never played",
    also: (tags: string) => ` · also ${tags}`,
  },
  // ---- dashboard: areas tab
  areasTab: {
    km: (n: string) => `${n} km`,
    ended: (when: string) => `ended ${when}`,
    endsToday: "ends today",
    endsTomorrow: "ends tomorrow",
    endsIn: (days: number, when: string) => `ends in ${days} days · ${when}`,
    ready: "ready to collect",
    toGo: (km: string) => `${km} to go`,
    playsAtPace: (n: number) => ` · about ${n} play${n === 1 ? "" : "s"} at your pace`,
    nextReward: "next reward",
    notListed: "not listed for this area",
    completed: "completed",
    everyReward: "every reward collected",
    firstPlay: "first play",
    gift: "you get a gift",
    totalDistance: "total distance",
    since: (km: string, when: string) => `+${km} since ${when}`,
    pace: (n: number, own: boolean) => `${n} km per play${own ? "" : ", based on your other areas"}`,
    plays: (n: number) => ` · ~${n} plays`,
    states: { in_progress: "in progress", completed: "completed", not_started: "not started" } as Record<string, string>,
    yourAreas: "your areas",
    loading: "Loading areas…",
    none: "No area data yet. Hit refresh on the Account tab or run any command in Discord.",
    travelInfo: "Every play moves you further in your current area, and rewards unlock at set distances. This is from your last refresh.",
    travel: "area travel",
    updated: (when: string) => `updated ${when}`,
    lastRefresh: "from your last refresh",
    underWay: "under way",
    notStarted: "not started",
    perPlay: "distance per play",
    paceValue: (pace: number, readings: number) => `${pace} km · from ${readings} reading${readings === 1 ? "" : "s"}`,
    notMeasured: "not measured yet",
    hint: "maimai DX NET only shows total distance, so plays left shows up once your distance changes between two refreshes. Area names are from SilentBlue RemyWiki.",
    progressInfo: "Areas you're partway through, with the distance and plays left to the next reward.",
    progress: "in progress",
    eventsInfo: "Limited-time areas. You can only get their rewards while they're running.",
    events: "event areas",
    untouchedInfo: "Areas you haven't started. Pick one on the cab and play once to get its first gift.",
    untouched: (n: number) => `not started · ${n}`,
    firstGift: "the first play in each gives a gift",
    waitingInfo: "Event areas you haven't started and when each one ends.",
    waiting: "events not started",
    endedInfo: "Events that are over. maimai DX NET doesn't show your distance for these anymore.",
    endedEvents: (n: number) => `ended events · ${n}`,
    namesOnly: "names and dates only",
    doneInfo: "Areas you've finished and the distance each one took.",
    done: (n: number) => `completed · ${n}`,
  },
  // ---- dashboard: public profile settings
  sharing: {
    sections: {
      best50: ["Best 50", "the 50 charts that make up your rating"],
      traits: ["Traits", "your strengths and weak spots"],
      recent: ["Recent plays", "your last 20 plays"],
      areas: ["Areas", "your progress in each area"],
    } as Record<string, [string, string]>,
    couldntSave: "couldn't save that",
    couldntCopy: "couldn't copy. Select the link and copy it yourself.",
    info: "Anyone with the link can see it. Your Discord account isn't on it and search engines won't list it.",
    title: "public profile",
    shared: "shared",
    private: "private",
    intro: "Off by default. Shows your name, rating, play count and any sections you turn on.",
    stop: "stop sharing",
    create: "create a public link",
    newLink: "new link",
    copied: "copied",
    copy: "copy",
    customise: "customise the Discord card",
    breaks: "Making a new link breaks the old one.",
  },
  // ---- dashboard: the Discord card window
  embedCard: {
    picture: {
      chart: ["Rating over time", "the graph along the bottom"],
      gain: ["Rating gain", "how much your rating went up and since when"],
      charts: ["Charts scored", "how many charts you've scored"],
      plays: ["Play count", "how many credits you've played"],
    } as Record<string, [string, string]>,
    visuals: {
      curve: ["Rating over time", "your rating history"],
      best50: ["Your best 50", "the 50 charts in your rating, highest first"],
      traits: ["How you play", "your traits wheel"],
      figures: ["Numbers only", "no graph, only your stats"],
    } as Record<string, [string, string]>,
    text: {
      region: ["Region", "International or Japan, next to your rating"],
      charts: ["Charts scored", "the count, next to your rating"],
    } as Record<string, [string, string]>,
    label: "the card your link shows in Discord",
    title: "Discord card",
    close: "close",
    intro: "What Discord shows when someone posts your link. Your name and rating are always on it, and you can change the rest.",
    looks: "what the card looks like",
    imageAlt: "your card image",
    notReady: "The image isn't ready yet. It'll be there when Discord loads the card.",
    image: "image",
    needs: (section: string) => `turn ${section} on above first`,
    colour: "colour",
    custom: "custom",
    showImage: "Show an image",
    showImageNote: "when off, only your name, rating and button show",
    onImage: "on the image",
    underName: "under your name",
    cache: "Discord caches cards for about half an hour. Changes show up the next time you post your link, and links you already sent keep the old card.",
  },
  // ---- dashboard: beta features
  beta: {
    lessThanMinute: "less than a minute left",
    minutesLeft: (n: number) => `about ${n} minute${n === 1 ? "" : "s"} left`,
    hoursLeft: (h: number, m: number) => `about ${h}h${m ? ` ${m}m` : ""} left`,
    readSoFar: "charts read so far",
    charts: (done: string, total: string, percent: string) => `${done} / ${total} charts · ${percent}%`,
    verdicts: { better: "Better", same: "No difference", worse: "Worse" } as Record<string, string>,
    couldntSend: "couldn't send that",
    compared: "Compared to having it off:",
    editNote: "Edit note",
    addNote: "Add a note",
    placeholder: "What changed?",
    save: "Save",
    pickFirst: "Pick an option first.",
    youSaid: (verdict: string) => `You said ${verdict}`,
    off: "Turns off on your next refresh.",
    notReady: "Turned on, but the bot can't run it yet, so nothing changes for now.",
    on: "Turns on with your next refresh. Hit refresh above to see it now.",
    couldntSave: "couldn't save that",
    info: "Features that work but aren't finished yet. Turning one off puts things back to normal.",
    title: "beta",
    count: (n: number) => `${n} on`,
    none: "none on",
    hint: "These can change your traits and picks. Tell us what you think so we know whether to keep them.",
  },
  // ---- dashboard: graphs
  graphs: {
    curveInfo: "The line is your expected score at each constant, based on your results. The band is how much your scores vary, and each dot is a chart.",
    curve: "your curve",
    fromCharts: (n: number) => `from ${n} charts`,
    curveLabel: "your scores by chart constant",
    recentBest: "best set in recent plays",
    comfortable: "comfortable",
    sExpected: "S expected",
    hardestPlayed: "hardest played",
    constantAxis: "chart constant →",
    achievementAxis: "achievement",
    curveHint: "Dots below the band are where your picks come from. The band is wider where you've played less.",
    onlyOne: (score: string, on: string) => `Only one score so far: ${score} on ${on}.`,
    noScores: "No saved scores for this chart yet.",
    afterRefresh: " New plays show up here after each refresh.",
    historyLabel: "score history",
    point: (score: string, on: string, constant: string, rating: number) => `${score} on ${on} · const ${constant} · rating ${rating}`,
    ratingOverTime: "rating over time",
    oneRating: (n: number) => `Only one rating saved so far: ${n}.`,
    noRating: "No rating history yet.",
    eachRefresh: " Each refresh adds a point.",
    since: (gain: string, when: string) => `${gain} since ${when}`,
    ratingLabel: "rating history",
  },
  // ---- dashboard: traits tab
  traitsTab: {
    gate: "Confirmed traits beat 1 in 50 odds and hold up on both halves of your charts, and only those affect your picks. Leaning ones beat 1 in 20, so treat them as hints.",
    info: (gate: string) => `How your scores on charts with the same pattern, note mix or BPM compare to your curve. ${gate}`,
    tagsFrom: " Pattern tags are from maiノーツ.",
    how: "how you play",
    measured: (groups: number, charts: number) => `${groups} groups measured · ${charts} scored charts`,
    noClear: "No clear traits yet. Every group is too close to your usual score or doesn't have enough charts. All your saved plays count, so more plays will help.",
    gapsInfo: "The 4 groups furthest from your usual score. None are confirmed, so take them with a grain of salt.",
    gaps: "biggest gaps, none confirmed",
    counts: (confirmed: number, leaning: number) => `${confirmed} confirmed · ${leaning} leaning`,
    byChance: (n: number) => ` (about ${n} by chance)`,
    rest: (watch: number, even: number, charts: number) => ` · ${watch} worth watching · ${even} about even · ${charts} scored charts`,
    wheelInfo: "The middle ring is your average. Further out is better, further in is worse, and points with a ? aren't confirmed.",
    wheelLater: "The wheel shows up once 3 or more traits have enough charts.",
    weakInfo: "Traits where you score below your curve. The big number is the achievement gap and the small one is the chart count.",
    weak: "where you lose points",
    noWeak: "Nothing below your average yet.",
    strongInfo: "Traits where you score above your curve.",
    strong: "where you're strong",
    noStrong: "Nothing above your average yet.",
    groupsInfo: "Your traits grouped by type, weighted by how many charts each one has. Click a group to see its traits.",
    groups: "trait groups",
    practiceInfo: "A few charts at your level for each pattern you're weak on. Ones you've played come first so you can see if you improve.",
    practice: "what to work on",
    measuredTitle: "measured from the chart's notes",
    notes: "notes",
    leaning: "leaning",
    watching: "worth watching",
    countTitle: (charts: number, plays: number) => `${charts} charts${plays ? `, ${plays} plays` : ""}`,
    oneIn: (n: number) => `1 in ${n} · `,
    plays: (n: number) => ` · ${n} plays`,
    charts: (n: number) => `${n} charts`,
    notPlayed: "not played yet",
    oldScore: (n: string) => `old score ${n}%`,
    youHave: (n: string) => `you have ${n}%`,
    familyCount: (traits: number, charts: string) => `${traits} traits · ${charts} charts`,
    aboutEven: "About even:",
    andMore: (n: number) => ` and ${n} more`,
    evenNote: (lean: string) => `. These are within ±${lean} of your usual score on enough charts to count.`,
    chance: (n: number) => `1 in ${n} by chance`,
    radarLabel: "your traits vs your average",
  },
  // ---- dashboard: judgements, under the traits
  judgeTab: {
    late: (n: number) => `${n}% of your off-timing hits are late, so you're a bit behind the beat.`,
    early: (n: number) => `${n}% of your off-timing hits are early, so you're a bit ahead of the beat.`,
    even: "Your off-timing hits are about half fast, half late.",
    info: "From the judgement pages of your recent plays. Shows what each note type costs you and whether you hit early or late.",
    title: "judgements",
    summary: (plays: number, lost: string) => `${plays} plays · ${lost} points lost per play`,
    needs: "Needs judgement data from 3 plays. Open a play's judgements on the Recent tab, hit refresh on the Account tab, or run any command in Discord.",
    notes: "notes",
    ofNotes: "of the notes",
    worth: "worth",
    ofLoss: "of the loss",
    per100: "lost per 100",
    clean: "clean",
    weak: (kind: string, loss: number, worth: number) => `${kind} notes are ${loss}% of your lost points but only worth ${worth}%, so they cost you the most.`,
    noWeak: "No note type costs you more than it's worth. A break counts as five taps here.",
    bonus: (per: string, share: number) => `Missed break bonus costs you ${per} per play, ${share}% of your loss. Only critical breaks get it, so this comes from missing criticals. It isn't counted in the table.`,
    fast: "fast",
    lateBar: "late",
  },
  // ---- a shared profile, at /p/...
  profile: {
    readings: (n: number) => `${n} readings`,
    ratingRange: (low: number, high: number) => `rating from ${low} to ${high}`,
    poolRating: (n: string) => `${n} rating`,
    emptyPool: "Nothing in this pool yet.",
    tabs: { overview: "Overview", best50: "Best 50", traits: "Traits", recent: "Recent", areas: "Areas" } as Record<string, string>,
    goneTitle: (
      <>
        This profile is <em>not shared</em>.
      </>
    ),
    goneLede: "The link may have been turned off or replaced with a new one. Ask whoever sent it for the current link.",
    whatRasmai: "what Rasmai does →",
    shared: "shared profile",
    sub: (titles: string, plays: string, read: string) => `${titles} · ${plays} plays · read ${read}`,
    charts: "charts",
    shares: "what this profile shares",
    overTime: "rating over time",
    fromChecks: "from saved checks",
    glance: "at a glance",
    scored: "charts scored",
    totalPlays: "total plays",
    bestChart: "best single chart",
    lastRead: "last read",
    sharesTabs: "The tabs above are what this player shares. Everything else is private.",
    onlyRating: "This player only shares their rating.",
    how: "how they play",
    ownCurve: "against their own curve",
    weak: "where they lose points",
    noWeak: "No weak spots found.",
    strong: "what they're good at",
    noStrong: "No strong spots found yet.",
    recent: "recent plays",
    newest: "newest first",
    noPlays: "No plays recorded yet.",
    inProgress: (n: number) => `${n} in progress or done`,
    done: " · done",
    footLeft: (
      <>
        Shared with Rasmai · <a href="/">what this is</a> · not affiliated with SEGA
      </>
    ),
    footRight: "this page only shows what the player chose to share",
  },
  // ---- trait names: English shows the bot's own words, so there is nothing to map
  traitNames: {} as Record<string, string>,
  noteKinds: { tap: "tap", hold: "hold", slide: "slide", touch: "touch", break: "break" } as Record<string, string>,
  chartsBy: (designer: string) => `charts by ${designer}`,
  noteTrait: (kind: string) => `${kind} notes`,
  // ---- long pages, set out as the page shows them
  docs: {
    commands: () => (
    <>
    <h2>Start here</h2>
    <div className="cmds">
      <Cmd name="/login">
        Links your maimai account. You get a link, sign in at maimai DX NET and press one button. It takes about a
        minute and you only do it once. You need to do this before any other command works. International
        accounts link with a bookmark; for a Japan account, run <code>/login region:Japan</code> and sign in with your SEGA
        ID. Accounts from the Chinese version can&apos;t be linked yet.
      </Cmd>
      <Cmd name="/help">A short version of this page in Discord.</Cmd>
      <Cmd name="/invite">Add Rasmai to a server or to your account, and get the dashboard link.</Cmd>
    </div>
  
    <h2>What to play</h2>
    <p>
      Picks are ranked by how much{" "}
      <Term word="rating" means="The number next to your name in maimai, which is the total of your best 50 charts." />{" "}
      you&apos;d gain.
    </p>
    <div className="cmds">
      <Cmd name="/analyze" args="[challenge] [level]">
        Your grind list. Each row has a chart, the score to aim for and your{" "}
        <Term word="odds" means="Your chance of hitting the target in one play, based on how much your scores vary." />{" "}
        of getting it. <code>challenge</code> changes the targets. Easier lands about half the time, balanced one in
        four, challenging one in six and long shots one in ten. <code>level</code> limits it to a level like{" "}
        <code>13+</code>, a{" "}
        <Term
          word="constant"
          means="The exact difficulty behind a level like 13+, such as 13.2, which rating is calculated from."
        />{" "}
        like <code>13.2</code>, or a range like <code>13.0-13.4</code>.
      </Cmd>
      <Cmd name="/plan" args="[target] [difficulty] [min_level]">
        Plans a route to a rating you pick. You get a list of targets that add up to it, with the odds for each and a
        running total.
      </Cmd>
      <Cmd name="/session" args="[credits]">
        Tell it how many credits you have. Each one goes where gain times odds is highest, with warm-ups first. A
        chart only repeats if you missed it the first time.
      </Cmd>
      <Cmd name="/new" args="[difficulty] [level] [focus]">
        Charts you&apos;ve never played that fit your level, with a guess at what you&apos;d score first try.{" "}
        <code>focus</code> leans the list toward a{" "}
        <Term word="trait" means="A kind of pattern in a chart, like streams, jacks, slide chains or tempo changes." />{" "}
        you&apos;re weak or strong at.
      </Cmd>
      <Cmd name="/random" args="[level] [difficulty] [unplayed]">
        Gives you a random chart around your level.
      </Cmd>
    </div>
  
    <h2>Your scores</h2>
    <div className="cmds">
      <Cmd name="/b50" args="or /top">
        The 50 charts that make up your rating, 15 from the{" "}
        <Term word="new pool" means="Charts from the current version, where 15 count toward your rating." /> and 35
        from the <Term word="old pool" means="Charts from older versions, where 35 count toward your rating." />.
      </Cmd>
      <Cmd name="/chart" args="<title> [difficulty]">
        One chart in detail. It shows your score, your predicted score, what each rank is worth, the chart&apos;s
        patterns, how to unlock it and a video. You can search in Japanese, romaji or English.
      </Cmd>
      <Cmd name="/charts" args="[pattern] [level] [difficulty]">
        Browse charts by pattern or level, with your scores next to each one. Good for practising something
        you&apos;re weak at.
      </Cmd>
      <Cmd name="/recent" args="[play]">
        Your recent sessions, every play, your new bests and what counted for rating. <code>play:1</code> opens one
        play with every{" "}
        <Term word="judgement" means="How each note was hit: critical perfect, perfect, great, good or miss." /> and
        how much it cost you.
      </Cmd>
      <Cmd name="/dxscore">
        Your{" "}
        <Term
          word="DX score"
          means="A separate score for how many notes you hit with the best timing, which doesn't affect rating."
        />{" "}
        stars and the charts closest to the next star.
      </Cmd>
      <Cmd name="/progress">
        Your rating over time, how fast it&apos;s going up, and when you&apos;ll hit the next thousand at that pace.
      </Cmd>
      <Cmd name="/area">
        Your progress in each area of area travel, the next reward and how many plays until you get it.
      </Cmd>
    </div>
  
    <h2>How you play</h2>
    <div className="cmds">
      <Cmd name="/profile">
        Your skill level based on your own results. It shows your{" "}
        <Term word="curve" means="Your scores plotted against chart constant, with a line showing what you'd be expected to score." />
        , the constant you&apos;re comfortable at, the hardest chart you&apos;ve gotten an S on, and how accurate the
        predictions have been lately.
      </Cmd>
      <Cmd name="/profile" args="then the Traits button">
        What you&apos;re good at and where you lose points. Each trait is checked against your own curve, taking play
        count and difficulty into account, then tested against shuffled tags a few hundred times. A trait is only
        marked{" "}
        <Term
          word="confirmed"
          means="Shuffled tags beat it less than 1 time in 50, and it held up in both halves of your charts."
        />{" "}
        when it&apos;s unlikely to be chance. Most tags come from{" "}
        <Term
          word="maiノーツ"
          means="A community site where people tag charts by pattern, covering about 1 in 10 charts, mostly Master and up."
        />{" "}
        editors. For untagged charts, Rasmai measures the patterns from the chart&apos;s{" "}
        <Term word="notation" means="The chart file itself, note by note." />.
      </Cmd>
    </div>
  
    <h2>Reading and sharing</h2>
    <div className="cmds">
      <Cmd name="/compare" args="@user">
        Compare your scores with another player who has sharing turned on.
      </Cmd>
      <Cmd name="/leaderboard">
        Rating leaderboard for this server. It&apos;s opt-in, and server owners can turn it off.
      </Cmd>
      <Cmd name="/settings">
        Your defaults, whether Rasmai checks your recent plays once a day, whether it DMs you the results, and who can
        see your scores. You can also turn on a public profile page here.
      </Cmd>
      <Cmd name="/server">
        For server managers. Turns <code>/leaderboard</code> on or off for the server.
      </Cmd>
    </div>
  
    <h2>Your data</h2>
    <div className="cmds">
      <Cmd name="/refresh">
        Gets your scores from maimai DX NET right now instead of using the saved copy. You rarely need this, since
        Rasmai checks for new plays whenever you run a command.
      </Cmd>
      <Cmd name="/export" args="[json|csv]">
        All your stored scores as a file. You can import it again from the Account tab on the site.
      </Cmd>
      <Cmd name="/delete-account">
        Deletes everything stored about you, including your account, scores and history. There&apos;s no
        confirmation email or waiting period.
      </Cmd>
    </div>
  
    <h2>The website</h2>
    <p>
      <a href="/me/">The dashboard</a> has everything the commands have, with more room. You sign in with Discord, and
      it only gets your ID and name.
    </p>
    <ul>
      <li>
        <b>Overview</b> shows your rating over time and your curve with every chart you&apos;ve scored.
      </li>
      <li>
        <b>What to play</b> and <b>New charts</b> are <code>/analyze</code> and <code>/new</code>, with filters so
        you don&apos;t have to retype them.
      </li>
      <li>
        <b>Traits</b> shows what you lose points on, what you&apos;re good at, how sure it is about each, and charts
        at your level to practise the weak ones.
      </li>
      <li>
        <b>Best 50</b>, <b>All charts</b> and <b>Recent</b> are your scores with filters, sorting and search in
        Japanese, romaji or English.
      </li>
      <li>
        <b>Look up</b> is <code>/chart</code> with a pattern browser, so you can find every chart with a certain
        pattern and practise it.
      </li>
      <li>
        <b>Areas</b> and <b>Account</b> cover area travel, your settings, importing an old export and deleting your
        account.
      </li>
    </ul>
    <p>
      You can install it on your phone as an app. Open <a href="/me/">rasmai.lol/me</a> in Safari or Chrome and add
      it to your home screen. The icon shortcuts go to What to play, Best 50, Recent and Traits.
    </p>
  
    <h2>Good to know</h2>
    <ul>
      <li>
        Rasmai only pulls from maimai DX NET when something changed. Each command checks your profile and recent
        plays, and uses the saved copy unless there&apos;s a new play.
      </li>
      <li>
        Charts your{" "}
        <Term
          word="region"
          means="The version of the game you play, where International is usually about a version behind Japan."
        />{" "}
        doesn&apos;t have yet are left out of suggestions. Look up still finds them and shows where they&apos;re
        playable.
      </li>
      <li>
        If your score on a chart looks like one bad run, Rasmai suggests it again based on what you&apos;d normally
        score and treats it like a first play.
      </li>
      <li>
        Targets never ask for a rank you haven&apos;t gotten at that level before, so a 12,000 player won&apos;t be
        told to{" "}
        <Term word="SSS" means="An achievement of 100.0% or more, one rank below SSS+ at 100.5%." /> a 14.
      </li>
    </ul>
    </>
    ),
    privacy: () => (
    <>
      <h2>What is stored</h2>
      <p>
        When you link an account with <code>/login</code>, Rasmai keeps the following in one database file on the server it runs on:
      </p>
      <ul>
        <li>
          <b>Your Discord user ID</b>, so Rasmai knows which maimai account is yours when you run a command.
        </li>
        <li>
          <b>Your maimai region</b> (international, Japan or China).
        </li>
        <li>
          <b>International accounts: a maimai DX NET session key.</b> This is the <code>clal</code> cookie the official site
          issues after you sign in on SEGA&apos;s page. It is <b>not your password</b>, and for an International account Rasmai
          never sees your SEGA ID or password. The key is encrypted with AES-256-GCM before it is written to disk.
        </li>
        <li>
          <b>Japan accounts: your SEGA ID, password and Aime card number.</b> Japan&apos;s maimai DX NET has no session key
          Rasmai can borrow, so you enter these on Rasmai&apos;s connect page and Rasmai signs in to maimaidx.jp with them each
          time it reads your scores. They are encrypted with AES-256-GCM before they are written to disk, are only ever sent
          to maimaidx.jp, and are never shown, logged or included in an export.
        </li>
        <li>
          <b>Your player profile</b> as shown on maimai DX NET: player name, rating, title, dan and avatar, refreshed each time
          your scores are read.
        </li>
        <li>
          <b>A compact copy of your scores</b> (chart, achievement, rank, rating, lamps and DX score) from your most recent
          read. It powers the dashboard, <code>/compare</code> and <code>/export</code> without re-reading the official site,
          and is replaced on every read.
        </li>
        <li>
          <b>Your play history.</b> Every play Rasmai finds on the recent-plays page (chart, achievement, DX score, lamps, track
          and the time it was played), and each new best it finds on a read. maimai DX NET only shows your last 50
          plays, so this copy lets the score graphs, <code>/progress</code>, the dashboard&apos;s Recent tab and the
          prediction accuracy check look further back. It grows for as long as your account is linked and is not trimmed.
        </li>
        <li>
          <b>Rating readings over time</b> (rating, best-50 totals, chart and play counts, timestamp), one per read where
          something moved, so <code>/progress</code> can draw your rating over time.
        </li>
        <li>
          <b>Per-chart play counts</b>, cached for 12 hours, or until you play the chart again, so Rasmai doesn&apos;t have to
          re-load hundreds of pages every time.
        </li>
        <li>
          <b>Judgement details and area progress.</b> For plays whose judgement page Rasmai reads, the note counts and the
          fast/late split. For your map areas, how far you have got and when it was recorded.
        </li>
        <li>
          <b>Beta feedback.</b> If you tell Rasmai whether a beta feature was better, the same or worse, it keeps that answer
          and the short note you may add (500 characters at most). The site&apos;s owner can read it, and it is not shown
          to anyone else.
        </li>
        <li>
          <b>Your settings</b> from <code>/settings</code>: default layout, default targets and difficulty, and opt-ins
          that are <b>off unless you turn them on</b>: letting other people run <code>/compare</code> against your stored
          scores, appearing on <code>/leaderboard</code> in servers you share with the bot, a public profile link (below),
          a daily read of your recent-plays page (below) and a Discord message about what that read found. With the
          compare, leaderboard and profile options off, nobody else can see anything about your account through Rasmai.
        </li>
        <li>
          <b>One-time login codes</b>, stored only as hashes. They work once, expire after 10 minutes and are deleted within a
          day.
        </li>
      </ul>
      <p>
        Scores are read when you run a command, press the read-now button on the dashboard, or, if you turned on{" "}
        <code>/settings history</code>, once a day in the background. That daily read signs in with your stored session key
        (for a Japan account, your stored SEGA ID) and loads only the recent-plays page, so plays aren&apos;t lost between commands. <code>/settings</code> shows when it last ran and how many plays it
        found.
      </p>

      <h2>Public profile</h2>
      <p>
        Only if you turn it on in the dashboard&apos;s Account tab, Rasmai gives you a link to a page at{" "}
        <code>{SITE_URL.replace("https://", "")}/p/&hellip;</code> that anyone holding the link can open. The link is a random
        code, not your Discord ID, and nothing on the page identifies your Discord account. It always shows your maimai player
        name, title, dan, name plate, region, rating, play count and rating history. Your best 50, recent plays, play style
        and area progress appear only if you switch each one on. The link also produces a preview picture and Discord
        embed built from the same data. Turning the profile off makes the link stop working, and asking for a new link
        replaces the old one at once. The name plate image is copied from maimai DX NET and cached on the server.
      </p>

      <h2>The website</h2>
      <ul>
        <li>
          <b>Dashboard sign-in.</b> Signing in with Discord sets one cookie holding a signed copy of your Discord ID, name and
          avatar address, valid for 30 days, plus a short-lived cookie during the sign-in handshake. Only your Discord ID and
          name are requested. Rasmai doesn&apos;t ask for your server list and doesn&apos;t post anything. Signing out clears the cookie.
        </li>
        <li>
          <b>Human check.</b> The sign-in and account-connect pages show a Cloudflare Turnstile check, which loads a script
          from Cloudflare. Cloudflare also fronts this site, so it handles requests to it the way any content network does.
          Both are covered by{" "}
          <a href="https://www.cloudflare.com/privacypolicy/" rel="noopener noreferrer">
            Cloudflare&apos;s privacy policy
          </a>
          .
        </li>
        <li>
          <b>Saved login (Japan accounts, optional).</b> If you tick <b>Save my login for next time</b> on the SEGA ID
          sign-in, your browser keeps your SEGA ID and Aime card number in its local storage so the form is filled in next
          time. It stays on your device and is never sent anywhere until you sign in. Your password is never saved there.
          Unticking the box removes it.
        </li>
        <li>
          <b>Home-screen app.</b> The site can be installed on a phone. Its service worker caches only the site&apos;s own static
          files (scripts, styles, fonts and icons) so the site opens offline. Scores, sign-in and API responses are
          never cached on the device.
        </li>
        <li>No analytics, no advertising and no other third-party scripts.</li>
      </ul>

      <h2>What is not stored</h2>
      <ul>
        <li>
          Payment details. For an International account, also your SEGA ID, password and Aime card number: sign-in happens
          on SEGA&apos;s own site.
        </li>
        <li>
          Your IP address. Sign-in attempts and reads are rate-limited with a short-lived in-memory counter that is never
          written to disk.
        </li>
        <li>Messages you send in Discord. Rasmai only responds to its own slash commands and doesn&apos;t read chat.</li>
        <li>Anything about people who have not linked an account.</li>
      </ul>

      <h2>Who else sees it</h2>
      <ul>
        <li>
          <b>SEGA (maimai DX NET).</b> Rasmai uses your session key, or for a Japan account your SEGA ID, to load your score
          pages from the official site, the same pages you see when you sign in yourself.
        </li>
        <li>
          <b>Discord.</b> Rasmai&apos;s replies, including the images it makes from your scores, are posted to Discord in the
          channel where you ran the command, and are subject to{" "}
          <a href="https://discord.com/privacy" rel="noopener noreferrer">
            Discord&apos;s privacy policy
          </a>
          . Use commands in a private channel if you would rather other members did not see your results.
        </li>
        <li>
          <b>Cloudflare</b>, as the network in front of the website and the provider of the human check, as described above.
        </li>
        <li>
          <b>Nobody else.</b> Data is not sold, shared or used for advertising, and there is no analytics or telemetry.
        </li>
      </ul>

      <h2>How long it is kept, and how to delete it</h2>
      <p>
        Your linked account, its scores and its play history stay until you remove them, with one exception: if maimai DX NET
        stops accepting your session key (for a Japan account, your SEGA ID and password) and you don&apos;t link again with <code>/login</code> within 30 days, everything listed
        under <b>Yourself, at once</b> below is deleted automatically. The dashboard shows the date while your session is expired,
        and two days before it Rasmai sends you a Discord message saying so, with a button to link again, if Discord lets it
        message you. Apart from that, nothing expires on its own except the session key, which stops working when SEGA expires
        it, and the caches listed above.
      </p>
      <ul>
        <li>
          <b>Yourself, at once.</b> Run <code>/delete-account</code> in Discord, or press <b>unlink</b> on the dashboard&apos;s Account
          tab. Either deletes your session key or SEGA ID sign-in, profile, profile link, stored scores, play history, judgement details, area
          progress, rating readings, settings, beta feedback, play-count cache and any login codes immediately. Your dashboard sign-in cookie stays until you sign out or it expires, and it only holds
          your Discord ID and name.
        </li>
        <li>
          <b>How it is deleted.</b> The same way however it happens: by you, by the operator, or automatically after 30 days. Every
          row stored under your Discord account is removed and its space in the database file is overwritten, so it can&apos;t
          be read back out of the file, and the database&apos;s change log is written back and emptied straight after. Any copy
          the bot is holding in memory is dropped at the same moment, and so is your data in the one backup copy the server
          keeps from a past database upgrade, and in any debugging copies the operator has switched on. Once it is gone it
          can&apos;t be restored.
        </li>
        <li>
          <b>By contact.</b> If you cannot use either, for example because you no longer have access to the Discord account, or
          you want everything about you removed including any record that you were ever linked, write to{" "}
          {contact}. Say which Discord account or maimai player name the data belongs to. It&apos;s deleted by hand,
          normally within a few days, and you get a reply when it is done. The same address handles a request for a copy of
          what is stored, though <code>/export</code> and the dashboard&apos;s <b>download JSON</b> button give you that at any
          time.
        </li>
      </ul>
      <p>
        Replies Rasmai posted in Discord stay in Discord. Delete them there if you want them
        gone.
      </p>

      <h2>Security</h2>
      <ul>
        <li>
          Stored sign-ins (session keys, and Japan accounts&apos; SEGA IDs and passwords) are encrypted with AES-256-GCM, which
          also detects any change to a stored value. The 256-bit key is derived with scrypt from a secret that lives only on
          the server, never in the database. Each sign-in is tied to its own account, so a copy moved onto another account
          can&apos;t be opened.
        </li>
        <li>
          When a sign-in is replaced or deleted, the old copy is overwritten in the database file, not just marked free. Sign-ins
          stored under the older encryption were re-encrypted the same way.
        </li>
        <li>
          A Japan account&apos;s SEGA ID and password are only ever sent to maimaidx.jp, over HTTPS, to sign in. They are never
          shown back to you or anyone else, never written to a log and never included in <code>/export</code>.
        </li>
        <li>Login links are single-use, tied to your Discord account, and expire after ten minutes.</li>
        <li>All connections to this site and to maimai DX NET use HTTPS with certificate verification.</li>
        <li>Sign-in attempts are rate-limited and gated by a human check.</li>
      </ul>

      <h2>Age</h2>
      <p>Rasmai is used through Discord, so Discord&apos;s minimum age applies. It is not directed at children.</p>

      <h2>Changes and contact</h2>
      <p>
        If this policy changes, the effective date above changes with it. Questions and deletion requests go to {contact}.
        This policy applies to the bot and to <code>{SITE_URL.replace("https://", "")}</code>.
      </p>
    </>
    ),
    terms: () => (
    <>
      <h2>What Rasmai is</h2>
      <p>
        Rasmai is a Discord bot that signs in to maimai DX NET on your behalf, reads your scores, and suggests which charts to
        play for the most rating. It is an independent hobby project. It is <b>not affiliated with, endorsed by or supported
        by SEGA</b>. maimai and maimai DX are trademarks of SEGA.
      </p>

      <h2>Your account</h2>
      <ul>
        <li>
          You may only link a maimai account that is yours. Attempting to link, access or interfere with anyone else&apos;s
          account is prohibited.
        </li>
        <li>
          By linking, you authorise Rasmai to read maimai DX NET using your session, or for a Japan account to sign in to
          maimaidx.jp with the SEGA ID you give it, in the same way you would in a browser. You are responsible for deciding whether that is acceptable to you under SEGA&apos;s own terms for maimai
          DX NET.
        </li>
        <li>
          Keep your login link to yourself. Anyone who has it before it expires can link their maimai account to your
          Discord account.
        </li>
        <li>
          You can delete your account at any time with <code>/delete-account</code>, which removes what the bot holds about you. See the{" "}
          <a href="/privacy/">privacy page</a> for exactly what that is.
        </li>
      </ul>

      <h2>What you share</h2>
      <ul>
        <li>
          If you turn on a public profile, <code>/compare</code> or <code>/leaderboard</code>, you choose what other people can
          see. Anyone with your profile link can see it, so only share the link with people you are happy to show it to.
        </li>
        <li>
          Beta feedback you send is kept with your account and read by the operator to improve Rasmai. Keep notes free of
          anything you would not want read.
        </li>
      </ul>

      <h2>Fair use</h2>
      <ul>
        <li>Do not use the bot or site to probe, overload or attack the service, maimai DX NET, or Discord.</li>
        <li>Commands are rate-limited per user. Working around those limits, or running automated clients against the bot, is not allowed.</li>
        <li>Do not misrepresent Rasmai as an official SEGA service.</li>
      </ul>

      <h2>No guarantees</h2>
      <ul>
        <li>
          <b>Recommendations are estimates.</b> Rating maths follows the game&apos;s public formula, but chart constants come
          from a community database and may lag behind or differ from your region. Odds and targets are predictions based on
          your own history and aren&apos;t guaranteed.
        </li>
        <li>
          <b>The service is provided as is</b>, with no warranty of any kind. It may be unavailable, change, or stop at any
          time, including if maimai DX NET changes in a way that breaks it.
        </li>
        <li>
          <b>Liability is limited</b> to the fullest extent the law allows. The operator is not liable for any loss arising from
          use of, or inability to use, the bot or site, including anything that happens to your SEGA account.
        </li>
      </ul>

      <h2>Stopping</h2>
      <p>
        You can stop using Rasmai whenever you like. <code>/delete-account</code> removes your data, and an account whose maimai session stays expired for 30 days
        without being linked again is deleted automatically. The operator may remove linked
        accounts or restrict access, for example in response to abuse, without notice.
      </p>

      <h2>Changes and contact</h2>
      <p>
        These terms may be updated. The effective date above marks the current version. Continued use after a change means
        you accept it. Questions go to {contact}.
      </p>
    </>
    ),
  },
};

export type Messages = typeof en;

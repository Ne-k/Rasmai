import { Cmd } from "@/components/Cmd";
import { CONTACT_DISCORD, CONTACT_EMAIL, SITE_URL } from "@/components/Contact";
import { Term } from "@/components/Term";
import type { ErrorCopy, Messages } from "./en";

// Every word the site shows in Japanese, in one place: the same keys as en.tsx, which this file is checked against.

const contact = (
  <>
    <a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a>、または Discord の <b>{CONTACT_DISCORD}</b>
  </>
);

const errors: Record<string, ErrorCopy> = {
  expired: {
    headline: ["リンクの有効期限が", "切れています"],
    detail: "ログインリンクは1回限りで、有効期限は約10分です。",
    hint: "Discord でもう一度 /login を実行して、新しいリンクを取得してください。",
  },
  invalid_user: {
    headline: ["このリンクは", "無効です"],
    detail: "Discord アカウントの情報が含まれていないか、リンクが書き換えられています。",
    hint: "Discord で /login を実行し、表示されたリンクをそのまま開いてください。",
  },
  maintenance: {
    headline: ["maimaiでらっくすNET が", "停止中です"],
    detail: "Aime へのログインはできましたが、maimaiでらっくすNET のスコアサイトが現在停止しているため、まだセッションを確認できません。",
    hint: "ログインリンクはまだ使えます。サーバーが復旧したら、もう一度ブックマークを押してください。復旧予定は上部の帯に表示されます。",
  },
  no_login: {
    headline: ["セッションを", "読み取れませんでした"],
    detail: "SEGA のゲートウェイにまだログインしていないか、ログインが保持されていない可能性があります。",
    hint: "ゲートウェイからログアウトして再度ログインし、もう一度ブックマークを押してください。日本版アカウントは SEGA ID で連携します：Discord で /login region:Japan を実行してください。",
  },
  region: {
    headline: ["中国版アカウントは", "まだ連携できません"],
    detail: "中国版の maimai DX NET は WeChat 内でしか開けず、Rasmai はまだそこにログインする手段を持っていないため、何度試してもこのログインは完了しません。",
    hint: "海外版と日本版のアカウントは連携できます。どちらかでも遊んでいる場合は、Discord で /login を実行して地域を選んでください。",
  },
  credentials: {
    headline: ["maimaidx.jp に", "拒否されました"],
    detail: "maimaidx.jp がその SEGA ID・パスワード・Aime カードを受け付けませんでした。",
    hint: "maimaidx.jp で確認してから、もう一度お試しください。ログインリンクはまだ使えます。",
  },
  rate_limited: {
    headline: ["試行回数が", "多すぎます"],
    detail: "お使いの接続からのログインを数分間停止しています。",
    hint: "10分ほど待ってから、Discord で /login を実行して新しいリンクを取得してください。",
  },
  upstream: {
    headline: ["maimai に", "拒否されました"],
    detail: "ログイン情報は正しく読み取れましたが、maimai のサイトに拒否されました。",
    hint: "途中でセッションが切れた可能性があります。ログインリンクはまだ使えるので、ゲートウェイに再度ログインしてブックマークを押してください。",
  },
  verify: {
    headline: ["確認が", "済んでいません"],
    detail: "ログインの前に、連携ページで人間であることの確認を完了する必要があります。",
    hint: "連携ページに戻って確認を完了し、もう一度ブックマークを押してください。",
  },
  unknown: {
    headline: ["問題が", "発生しました"],
    detail: "連携を完了できませんでした。",
    hint: "Discord で /login を実行して、最初からやり直してください。",
  },
};

export const ja: Messages = {
  // ---- common
  meta: {
    title: "Rasmai · Discord で使える maimai DX レーティングbot",
    tagline: "Rasmai は maimaiでらっくすNET のスコアを読み取り、レーティングを上げるために遊ぶべき譜面を教えてくれます。",
  },
  common: {
    switchLanguage: "Switch to English",
    themeToggle: "ライト／ダークを切り替え",
    themeTitle: "ライト／ダーク",
    dismiss: "閉じる",
    more: "詳しく",
    period: "。",
  },
  nav: { home: "ホーム", link: "連携", commands: "コマンド", dashboard: "ダッシュボード", invite: "招待" },
  shell: { steps: ["リンクを取得", "ログイン", "連携"] },
  footer: {
    createdBy: (
      <>
        制作 <b>nek_ng</b>
      </>
    ),
    notAffiliated: "SEGA とは無関係の非公式ツールです",
    privacy: "プライバシー",
    terms: "利用規約",
    invite: "bot を招待",
  },
  doc: { effective: (date: string) => `施行日：${date}` },
  servers: {
    anyMinute: "まもなく",
    inMinutes: (n: number) => `あと${n}分`,
    inHours: (n: number) => `あと${n}時間`,
    maintenance: "maimaiでらっくすNET はメンテナンス中です。",
    down: "maimaiでらっくすNET が現在応答していません。",
    back: (when: string, clock: string) => `復旧予定：${when}（お使いの時刻で${clock}）。`,
    rest: "ここに表示されているスコアは最後に確認した時点のものです。復旧するまで、スコアの更新やアカウントの連携はできません。",
  },
  pwa: {
    updated: "サイトの新しいバージョンが利用できます。",
    reload: "再読み込み",
    later: "あとで",
    hide: "今後表示しない",
    heading: "Rasmai をホーム画面に追加しましょう。",
    prompt: "ダッシュボードがアプリのように全画面で開きます。",
    install: "アプリをインストール",
    ios: (
      <>
        Safari で <b>共有</b> <span className="glyph">⎙</span> をタップし、<b>ホーム画面に追加</b> を選んでください。アプリのように全画面で開きます。
      </>
    ),
    android: (
      <>
        Chrome の <b>⋮</b> メニューから <b>アプリをインストール</b> または <b>ホーム画面に追加</b> を選んでください。アプリのように全画面で開きます。
      </>
    ),
    other: "ブラウザのメニューから、このページをアプリとしてインストールできます。全画面で開きます。",
  },
  // ---- home
  home: {
    metaTitle: "Discord で使える maimai DX レーティングbot",
    eyebrow: "maimai DX のための Discord bot",
    title: (
      <>
        <em>次に遊ぶ譜面</em>がわかる。
      </>
    ),
    lede: "Rasmai は maimaiでらっくすNET のスコアを読み取り、レーティングを上げるために遊ぶべき譜面を教えてくれます。結果は Discord の画像やWebダッシュボードで確認でき、遊ぶ前にどんな譜面の配置かも調べられます。",
    addToDiscord: "Discord に追加",
    openDashboard: "ダッシュボードを開く",
    demoLabel: "結果の表示例",
    demoEyebrow: "次に遊ぶ譜面",
    demoName: "あなたの名前",
    demoTotal: "合計上昇",
    columns: { chart: "譜面", achievement: "達成率", rank: "ランク", odds: "確率", gain: "上昇" },
    demoFoot: "表示例・実際はあなたのスコアから作られます",
    features: [
      { mark: "rank_sssp", title: "レート上げに詰める譜面", body: "スコアをひと通り調べて、スコアを伸ばしたときにレーティングが一番上がる譜面を並べます。", command: "/analyze" },
      { mark: "up", title: "目標の難しさを選べる", body: "「Easier」は堅実な目標、「Balanced」は期待値が最も高い目標、「Challenging」は届く範囲で大きく伸びる目標を選びます。返信のメニューからいつでも切り替えられます。", command: "/analyze challenge" },
      { mark: "best50", title: "次の1000に向けた計画", body: "次のレーティングの節目まで届く目標を、それぞれの達成確率と累計つきで並べます。", command: "/plan" },
      { mark: "plays", title: "1回の来店を計画", body: "使えるクレジット数を伝えると、ウォームアップから順に1曲ずつ計画します。同じ譜面を繰り返すのは外したときだけで、そのセッションでどれだけレートが上がりうるかもわかります。", command: "/session" },
      { mark: "new", title: "新しく挑戦する譜面", body: "まだ遊んでいない、あなたのレベルに合った譜面を、初見での予想スコアつきで紹介します。focus を付ければ、苦手・得意な配置の譜面に寄せられます。", command: "/new focus" },
      { mark: "pb", title: "どこで点を落としているか", body: "スコアを譜面の配置ごとにまとめ、あなた自身のカーブと比べます。予測が自己ベスト更新にどれだけ合っていたかも表示します。", command: "/profile" },
      { mark: "diff_master", title: "譜面を調べる", body: "あなたのスコア、予想スコア、各ランクの価値、譜面の配置を表示します。同じ曲の他の難易度やスコア推移グラフもボタンひとつ。配置ごとに全譜面を一覧することもできます。", command: "/chart  /charts" },
      { mark: "rasmai", title: "レーティングの推移", body: "レーティングの推移と上がるペース、そのペースで各節目に届く日、そこまでに必要なクレジット数を表示します。", command: "/progress" },
      { mark: "festival", title: "プレイを振り返る", body: "配置タグで遊ぶ前に譜面の中身がわかります。プレイ後はプレイ履歴ですべての判定を確認でき、どこで点を落としたかがわかります。", command: "/charts  /recent play:1" },
    ],
    linkingTitle: "アカウントの連携",
    linking: (
      <>
        Discord で <code>/login</code> を実行し、表示されたリンクを開きます。海外版アカウントは my-aime.net でログインして Aime
        認証を開き、ブックマークを1回押すだけ。Rasmai が受け取るのはスコアを読むためのセッションだけで、パスワードは見ません。日本版アカウントは次のページで
        SEGA ID とパスワードを入力して連携し、暗号化して保存します。<code>/delete-account</code> で Rasmai が持つあなたのデータをすべて削除できます。
      </>
    ),
    linkingButton: "連携のしくみ →",
    dashboardTitle: "ダッシュボード",
    dashboard: "Discord でログインすると、レーティングの推移、プレイの傾向、ベスト50、絞り込みできる全スコア、bot と同じおすすめ、まだ遊んでいない譜面40曲が見られます。",
    dashboardButton: "ダッシュボードを開く →",
    phoneHint: "スマートフォンではダッシュボードをホーム画面に追加すると、アプリのように開けます。",
    commandsTitle: "コマンド",
    commands: [
      ["/login", "maimaiでらっくすNET のアカウントを連携"],
      ["/analyze", "選んだ難しさで、詰めるべき譜面"],
      ["/plan", "次のレーティングの節目までのルート"],
      ["/session", "1回の来店のクレジットを計画"],
      ["/new", "あなたのレベルの未プレイ譜面（苦手な配置に絞ることも可）"],
      ["/chart  /charts", "譜面を1つ調べる、または配置やレベルで一覧"],
      ["/b50  /dxscore", "ベスト50（/top でも可）とでらっくスコアの星"],
      ["/recent", "最近のプレイ、または play:1 で1プレイの詳細"],
      ["/progress", "レーティングの推移と次の1000に届く時期"],
      ["/compare  /leaderboard", "フレンドとの比較、またはサーバーのランキング（任意参加）"],
      ["/random  /profile  /export", "ランダムな譜面、プレイの傾向、データのコピー"],
      ["/settings  /invite", "初期設定と毎日のスコア確認、招待リンク"],
    ],
  },
  // ---- link
  link: {
    metaTitle: "maimai アカウントを連携する",
    metaDescription: "maimaiでらっくすNET のアカウントを Rasmai に連携する方法（パソコン・iPhone、動画つき）。",
    title: (
      <>
        <em>maimai</em> アカウントを連携しよう。
      </>
    ),
    lede: "連携すると、Rasmai があなたのスコアを確認し、レーティングを上げるために遊ぶべき譜面を教えてくれます。",
    videoTitle: "まずは動画をどうぞ",
    videoBody: "お使いの端末を選んでください。音声なしの約1分の動画です。",
    step1Title: "リンクを取得する",
    step1: (
      <>
        Discord で <code>/login</code> を実行します。ログインコードが入った、あなた専用のこのサイトへのリンクが届きます。
      </>
    ),
    step2Title: "my-aime にログインして認証する",
    step2: (
      <>
        普段遊んでいるアカウントで <a href="https://my-aime.net/en/">my-aime.net</a> にログインし、設定ページから Aime
        認証を開きます。するとゲートウェイのページに移ります。
      </>
    ),
    step3Title: "さあ、詰めよう",
    step3: (
      <>
        Discord に戻って <code>/analyze</code> で遊ぶ譜面を確認するか、<code>/plan</code> で次の1000までの計画を立てましょう。
      </>
    ),
    japan: (
      <>
        <b>日本版のアカウントですか？</b> その場合は <code>/login region:Japan</code> を実行してください。リンク先のページで maimaidx.jp
        の SEGA ID とパスワードを入力するだけなので、手順2と動画は不要です。
      </>
    ),
    already: (
      <>
        <b>連携済みですか？</b> スコアはWebでも見られます。<a href="/me/">ダッシュボードを開いて</a> Discord でログインしてください。
      </>
    ),
  },
  walkthrough: {
    desktop: "パソコン",
    desktopNote: "Chrome・Edge・Firefox のどれでも同じ手順です。",
    ios: "iPhone",
    iosNote: "iOS の Safari です。Android の Chrome でも同じ手順です。",
    videoLabel: (device: string) => `${device}：連携の全手順`,
    tabs: "連携に使う端末",
  },
  // ---- flow
  errors,
  flow: {
    loading: "読み込み中…",
    period: "。",
    nothingSaved: "何も保存されていません",
    validUntil: (time: string) => `リンクの有効期限 ${time}`,
    labelValidUntil: "有効期限",
    labelRegion: "地域",
    connectedAs: (name: string) => `${name} として連携しました。`,
    connected: "連携しました。",
    waiting: "ログインを待っています…",
    stopped: "確認を停止しました。待ち続けるにはページを再読み込みしてください。",
    neverSeesPassword: "Rasmai はパスワードを見ません",
    segaIdEncrypted: "SEGA ID は暗号化して保存されます",
    checkTitle: (
      <>
        簡単な<em>確認</em>をお願いします。
      </>
    ),
    checkLedeJapan: "人間であることの確認を完了すると、ログインフォームが表示されます。",
    checkLede: "人間であることの確認を完了すると、リンクと連携用ブックマークが表示されます。",
    checkFailed: "確認に失敗しました。ページを再読み込みしてもう一度お試しください。",
    checkWhy: (japan: boolean) => (
      <>
        <b>なぜ必要？</b> 次の画面で Rasmai は{japan ? " maimaidx.jp のログイン情報" : " maimai のセッション"}を受け取ります。この確認は bot
        による悪用を防ぐためのものです。
      </>
    ),
    device: "お使いの端末",
    devices: { desktop: "パソコン", ios: "iPhone / iPad", android: "Android" },
    titleMobile: (
      <>
        <em>ブックマーク</em>を用意して、ログインしよう。
      </>
    ),
    titleDesktop: (
      <>
        <em>ブックマーク</em>をドラッグして、ログインしよう。
      </>
    ),
    ledeMobile: "ブックマークを用意して my-aime にログインし、Aime 認証を開いたら、そのページでブックマークを実行します。連携が完了するとこのページが更新されます。",
    ledeDesktop: "このタブは開いたままにしてください。連携が完了すると更新されます。",
    dragTitle: "これをブックマークバーにドラッグ",
    drag: (
      <>
        ピンクのボタンをつかんで、ブラウザのブックマークバーにドロップしてください。バーが表示されていない場合は、先に <code>Ctrl+Shift+B</code>（Mac
        は <code>⌘+Shift+B</code>）を押してください。
      </>
    ),
    copyInstead: "代わりにコピー",
    copiedHint: "コピーしました。ブックマークのアドレスとして貼り付けてください。",
    makeTitle: "連携用ブックマークを作る",
    makeBody: "ブックマーク用のコードをコピーして、次の手順でブックマークとして保存してください。",
    copied: "✓ コピーしました",
    copyCode: "ブックマーク用コードをコピー",
    ios: [
      <>
        <b>共有</b> <span className="glyph">⎙</span> → <b>ブックマークを追加</b> → <b>保存</b> の順にタップ。名前は <b>maimai connect</b> にします。
      </>,
      <>
        <b>ブックマーク</b> <span className="glyph">📖</span> → <b>編集</b> を開き、作ったブックマークをタップします。
      </>,
      <>
        <b>アドレス</b>をコピーした内容に置き換えて → <b>完了</b>。
      </>,
    ],
    android: [
      <>
        <b>⋮</b> → <b>☆</b> をタップして、このページをブックマークします。
      </>,
      <>
        <b>⋮</b> → <b>ブックマーク</b> を開き、作ったブックマークの <b>⋮</b> → <b>編集</b> をタップします。
      </>,
      <>
        名前を <b>maimai connect</b> にし、<b>URL</b> をコピーした内容に置き換えて、戻って保存します。
      </>,
    ],
    signInTitle: "my-aime にログインして認証する",
    signIn: (mobile: boolean) =>
      `まず、普段遊んでいるアカウントで my-aime.net にログインします${mobile ? "" : "（新しいタブで開きます）"}。次に Aime 認証を開くと、ゲートウェイのページに移ります。`,
    signInButton: "1・my-aime にログイン →",
    authButton: "2・Aime 認証を開く →",
    runTitle: "AIME のページでブックマークを実行",
    runDesktop: (
      <>
        ゲートウェイのページを開いたら、<b>maimai connect</b> ブックマークをクリックします。完了するとこのページが更新されます。
      </>
    ),
    runIos: (
      <>
        ゲートウェイのページを開いたら、<b>ブックマーク</b> <span className="glyph">📖</span> を開いて <b>maimai connect</b>{" "}
        をタップし、このタブに戻ってきてください。
      </>
    ),
    runAndroid: (
      <>
        ゲートウェイのページを開いたら、<b>アドレスバー</b>をタップして <b>maimai connect</b> と入力し、候補からブックマークを選びます。Chrome
        ではアドレスバーにコードを貼り付けても動きません。その後このタブに戻ってきてください。
      </>
    ),
    stuck: (
      <>
        <b>うまくいかない？</b> ブックマークが「ログインを読み取れない」と表示する場合は、ゲートウェイからログアウトして再度ログインし、もう一度実行してください。リンクの期限が切れた場合は、Discord
        で <code>/login</code> を実行して新しいリンクを取得してください。このブックマークは海外版アカウント用です。日本版アカウントは SEGA ID
        で連携します：<code>/login region:Japan</code> を実行してください。中国版のアカウントはまだ連携できません。
      </>
    ),
    jpTitle: (
      <>
        <em>SEGA ID</em> でログイン。
      </>
    ),
    jpLede: "maimaidx.jp には海外版のように借りられるログインがないため、Rasmai はスコアを読むたびにあなたの SEGA ID でログインします。",
    jpStepTitle: "maimaidx.jp のログイン情報",
    jpStep: (
      <>
        <a href="https://maimaidx.jp/maimai-mobile/" target="_blank" rel="noopener noreferrer">
          maimaidx.jp
        </a>{" "}
        で使っている SEGA ID とパスワードを入力してください。
      </>
    ),
    segaId: "SEGA ID",
    password: "パスワード",
    aimeCard: "Aime カード",
    aimeHint: "1つの SEGA ID には複数の Aime カード（それぞれ別のプレイヤー）を登録できます。複数ない場合は 1 のままで構いません。",
    remember: "次回のためにログイン情報を保存",
    rememberHint: "SEGA ID とカード番号をこの端末にだけ保存します。パスワードはここには保存されません（ブラウザの保存機能は使えます）。",
    signingIn: "ログイン中…",
    signInAndLink: "ログインして連携",
    signingInJp: "maimaidx.jp にログインしています…",
    unreachableJp: "現在 maimaidx.jp に接続できませんでした。数分後にもう一度お試しください。ログインリンクはまだ使えます。",
    failed: "ログインできませんでした。少し待ってからもう一度お試しください。",
    offline: "Rasmai に接続できませんでした。接続を確認して、もう一度お試しください。",
    keeps: (
      <>
        <b>Rasmai が保存するもの。</b> SEGA ID とパスワードは暗号化してから保存し、maimaidx.jp へのログインとスコアの読み取りにだけ使います。
        <code>/logout</code> または <code>/delete-account</code> を実行すると削除されます。パスワードを変更した場合は、もう一度 <code>/login</code>{" "}
        を実行してください。
      </>
    ),
    linkedTitle: (
      <>
        <em>連携</em>できました。
      </>
    ),
    signedInAs: (name: string) => (
      <>
        <b>{name}</b> としてログインしました。Rasmai がスコアを確認できるようになりました。
      </>
    ),
    linkedGeneric: "maimai アカウントが Discord アカウントに連携されました。",
    rating: "レーティング",
    backInDiscord: "Discord に戻って",
    nextCommands: [
      ["/analyze", "伸びが大きい順に、詰めるべき譜面"],
      ["/plan", "次の1000までの計画"],
      ["/new", "あなたのレベルに合った未プレイ譜面"],
      ["/profile", "プレイの傾向と点を落としている所"],
    ],
    closeTab: "このタブは閉じて構いません。",
  },
  // ---- pages
  privacy: {
    metaTitle: "プライバシー",
    metaDescription: "Rasmai が保存するあなたの情報と、その削除方法。",
    title: (
      <>
        Rasmai が<em>保存する</em>情報。
      </>
    ),
    intro: "Rasmai は maimai DX のスコアを確認し、詰めるべき譜面を教えてくれる Discord bot です。このページでは、何を保存するか、どれくらいの期間保存するか、どう削除できるかを説明します。トラッキング、アクセス解析、広告はありません。",
  },
  terms: {
    metaTitle: "利用規約",
    metaDescription: "Rasmai を利用するときに同意していただく内容。",
    title: (
      <>
        <em>利用</em>規約。
      </>
    ),
    intro: "Rasmai は無料の、ファンによる非公式ツールです。bot またはこのサイトを利用することで、以下の規約に同意したものとみなされます。",
  },
  notFound: {
    metaTitle: "ページが見つかりません",
    metaDescription: "このページは存在しません。",
    foot: "404・何も保存されていません",
    title: (
      <>
        ページが<em>見つかりません</em>。
      </>
    ),
    lede: "このページは存在しないか、移動しました。代わりに次のページをどうぞ。",
    whereTitle: "行き先",
    home: (
      <>
        <a href="/">ホーム</a>：Rasmai でできることと追加方法。
      </>
    ),
    link: (
      <>
        <code>/login</code> から来た場合は<a href="/link/">アカウントの連携</a>へ。リンクの期限が切れていたら、Discord でもう一度コマンドを実行して新しいリンクを取得してください。
      </>
    ),
    dashboard: (
      <>
        Discord でログインして<a href="/me/">ダッシュボード</a>へ。
      </>
    ),
    bookmark: (
      <>
        <b>ブックマークから来ましたか？</b> 連携リンクは1回限りで、有効期限は約10分です。ブックマークはこのサイトではなく、SEGA のゲートウェイのページで実行してください。
      </>
    ),
  },
  commands: {
    metaTitle: "コマンド",
    metaDescription: "Rasmai のすべてのコマンドとその働き、maimai の用語の解説つき。",
    title: (
      <>
        コマンドと<em>その働き</em>。
      </>
    ),
    intro: "点線の下線がある言葉にカーソルを合わせるかタップすると、意味が表示されます。コマンドはサーバーと DM で使えます。Rasmai を自分のアカウントに追加すれば、どこでも使えます。",
  },
  // ---- dash
  dash: {
    metaTitle: "ダッシュボード",
    metaDescription: "あなたの maimai のスコア、ベスト50、次に遊ぶ譜面。",
    chartConstant: "譜面定数",
    never: "未取得",
    justNow: "たった今",
    minAgo: (n: number) => `${n}分前`,
    hAgo: (n: number) => `${n}時間前`,
    daysAgo: (n: number) => `${n}日前`,
    couldntLoad: (what: string, message: string) => `${what}を読み込めませんでした。${message}`,
    tryAgain: "再試行",
    moreInfo: "詳細",
    images: {
      analyze: "遊ぶ譜面",
      profile: "プレイの傾向",
      new: "新しい譜面",
      traits: "特性",
      progress: "レーティングの推移",
      best50: "ベスト50",
      recent: "最近のプレイ",
    },
    saveTitle: (what: string) => `bot が Discord に投稿する「${what}」の画像を保存`,
    makingImage: "画像を作成中…",
    noImageData: "まだデータがありません",
    imageFailed: "画像を作成できませんでした",
    saveImage: (what: string) => `「${what}」を保存`,
    signOut: "ログアウト",
    footRight: "スコアはコマンドの実行時やここでの更新時に maimaiでらっくすNET から更新されます",
    sections: "セクション",
    tabs: {
      overview: "概要",
      picks: "遊ぶ譜面",
      new: "新しい譜面",
      traits: "特性",
      best50: "ベスト50",
      charts: "全譜面",
      recent: "最近",
      chart: "検索",
      areas: "エリア",
      account: "アカウント",
      admin: "開発者",
    },
    stages: {
      queued: "空きを待っています",
      login: "maimaiでらっくすNET にログイン中",
      scores: "スコアのページを読み込み中",
      recent: "最近のプレイ",
      extras: "アルバムとイベント",
      plays: "プレイ回数",
      analysis: "あなたに合う譜面を選んでいます",
      done: "完了",
      failed: "失敗",
    },
    readingScores: (what: string) => `maimai からスコアを読み込み中・${what}`,
    queueNow: "分析を作成しています…",
    queueBusy: (position: number, wait: string) =>
      `現在混み合っています。あなたは${position}番目で、あと約${wait}です。完了するとページが更新されます。`,
    seconds: (n: number) => `${n}秒`,
    minutes: (n: number) => `${n}分`,
    signInErrors: {
      discord: "Discord がログインを確認しませんでした。もう一度お試しください。",
      state: "ログインリンクの期限が切れました。もう一度お試しください。",
      oauth_unconfigured: "このサーバーではまだログインが設定されていません。",
      verify: "人間であることの確認に失敗しました。もう一度お試しください。",
    },
    turnstileFailed: "人間であることの確認を読み込めませんでした。ページを再読み込みしてください。",
    lostConnection: "bot との接続が切れました。ページを再読み込みするか、1分ほどしてからもう一度お試しください。",
    gateTitle: (
      <>
        スコアを<em>Webで</em>。
      </>
    ),
    gateLede: "ベスト50、全譜面、レーティングの推移、次に遊ぶ譜面が見られます。bot で使っている Discord アカウントでログインしてください。",
    signInDiscord: "Discord でログイン",
    notSetUp: "このサーバーではまだログインが設定されていません。運営者が Discord のクライアントIDとシークレットを設定する必要があります。",
    gatePrivacy: "読み取るのは Discord ID と名前だけです。何かを投稿したり、サーバーの一覧を求めたりすることはありません。",
    loading: "読み込み中…",
    loadingCharts: "譜面を読み込み中…",
    notLinkedTitle: (
      <>
        maimai アカウントが<em>まだ連携されていません</em>。
      </>
    ),
    notLinkedLede: (
      <>
        ログインはできていますが、この Discord アカウントには maimai アカウントが連携されていません。Discord で <code>/login</code>{" "}
        を実行してリンクを開き、ここに戻ってきてください。
      </>
    ),
    howLinking: "連携のしくみ →",
    updated: "更新 ",
    noTitle: "称号はまだ読み取っていません",
    plays: (n: string) => `${n}プレイ`,
    since: (day: string, delta: number, plays: number, newBests: number, fmt: (n: number) => string) =>
      `${day}から：${delta ? `レート ${delta > 0 ? "+" : ""}${delta}` : "レート変化なし"}` +
      (plays ? `・${fmt(plays)}プレイ` : "") +
      (newBests ? `・自己ベスト更新${newBests}件` : ""),
    rating: "レーティング",
    best50: "ベスト50",
    newOld: "新曲・旧曲",
    bands: {
      white: "白", blue: "青", green: "緑", yellow: "黄", red: "赤", purple: "紫",
      bronze: "銅", silver: "銀", gold: "金", platinum: "白金", rainbow: "虹", kiwami: "極",
    },
    yourCharts: "譜面",
    yourHistory: "プレイ履歴",
    expired: (on: string, until: string) => (
      <>
        <b>maimai のセッションが期限切れです。</b> maimaiでらっくすNET が{on ? `${on}に` : ""}ログインを受け付けなくなったため、スコアが更新されていません。以下は最後に更新した時点のものです。Discord
        で <code>/login</code> を実行して再連携してください。
        {until ? (
          <>
            <b>{until}</b>までに再連携しないと、このアカウントについて保存されているものはすべて削除されます。
          </>
        ) : null}
      </>
    ),
    api: {
      bot_unreachable: "現在 bot に接続できません。再起動中かもしれないので、1分ほどしてからもう一度お試しください。",
      rate_limited: "リクエストが多すぎます。少し待ってからもう一度お試しください。",
      signed_out: "ログインの期限が切れました。もう一度ログインしてください。",
      bad_response: "サーバーの応答を読み取れませんでした。",
      not_linked: "この Discord アカウントにはまだ maimai アカウントが連携されていません。",
      notFound: "見つかりませんでした。",
      server: "サーバーで問題が発生しました。少し待ってからもう一度お試しください。",
      network: "接続できませんでした。インターネット接続を確認して、もう一度お試しください。",
      generic: (status: number) => `問題が発生しました（${status}）。`,
    },
  },
  // ---- dashboard: overview tab
  overviewTab: {
    howInfo: "「安定して出せる上限」は毎回しっかりスコアを出せる最も高い譜面定数、「初見で S が見込める上限」は初めて遊んでも S が取れるはずの最も高い譜面定数です。",
    how: "プレイの傾向",
    comfort: "安定して出せる上限",
    reach: "初見で S が見込める上限",
    hardestS: "S を取った最高定数",
    age: "よく選ぶ譜面",
    ageValue: (years: string, fresh: number) => `平均 ${years} 年前の曲 · ${fresh}% が1年以内`,
    rerates: "定数変更による増減",
    reratesValue: (rating: string, charts: number) => `${charts} 譜面で ${rating}`,
    notes: "叩いたノーツ数",
    warmUp: "クレジットの1曲目",
    warmUpValue: (gap: string, colder: boolean) => `ほかの曲より ${gap}% ${colder ? "低い" : "高い"}`,
    scored: "スコアのある譜面",
    upper: "EXPERT 以上",
    fullCombos: "フルコンボ",
    fullCombosValue: (all: string, ap: string) => `${all}（うちオールパーフェクト ${ap}）`,
    fullSync: "フルシンク+",
    reachable: "おすすめ譜面で上げられる分",
    cutoffsInfo: "レーティングは、現行バージョンの曲のベスト15と、旧バージョンの曲のベスト35の合計です。「ボーダー」は枠に入るのに必要な単曲レートです。",
    cutoffs: "ベスト50のボーダー",
    newPool: "新曲枠（15）",
    oldPool: "旧曲枠（35）",
    entersAt: (total: string, cutoff: number) => `${total} · ボーダー ${cutoff}`,
    open: (n: number) => ` · 空き ${n}`,
    ranksInfo: "EXPERT・MASTER・Re:MASTER のスコアが、各ランクにいくつあるか。",
    ranks: "ランク · EXPERT 以上",
    levelsInfo: "EXPERT 以上の、レベルごとの平均達成率。バーは 80% から 100% までです。",
    levels: "レベル別の平均達成率 · EXPERT 以上",
    charts: (n: number) => `${n} 譜面`,
  },
  // ---- dashboard: best 50 tab
  best50Tab: {
    newInfo: "現行バージョンの曲での単曲レート上位15譜面。「ボーダー」は枠に入るのに必要な単曲レートです。",
    oldInfo: "旧バージョンの曲での単曲レート上位35譜面。「ボーダー」は枠に入るのに必要な単曲レートです。",
    total: (n: string) => `合計 ${n}`,
    entersAt: (n: number) => ` · ボーダー ${n}`,
    jacket: "ジャケット",
    chart: "譜面",
    achievement: "達成率",
    constRating: "定数 → レート",
    averages: (n: number) => `ベスト50の ${n} 譜面の平均`,
    avgConstant: "平均定数",
    avgAchievement: "平均達成率",
    avgRating: "平均レート",
    newVersion: "新曲枠",
    older: "旧曲枠",
  },
  // ---- dashboard: account tab
  accountTab: {
    accountInfo: "Discord に連携されている maimaiでらっくすNET のアカウントです。「履歴ポイント」は、概要のグラフのもとになっている保存済みのレーティングです。",
    account: "maimai アカウント",
    player: "プレイヤー",
    region: "地域",
    lastRead: "最終読み取り",
    historyPoints: "履歴ポイント",
    refreshing: "読み取り中…",
    refresh: "今すぐ読み取る",
    download: "JSON をダウンロード",
    import: "JSON を取り込む",
    failed: (why: string) => `読み取りに失敗しました：${why}`,
    refreshed: "読み取り完了 ",
    imported: (plays: number, bests: number, points: number, counts: number) =>
      `${plays} プレイ、${bests} 件のベスト、${points} 件のレーティング、${counts} 件のプレイ回数を取り込みました。再読み込みします…`,
    notJson: "このファイルは JSON ではありません。",
    takes: "1分ほどかかります。Discord のコマンドと同じ読み取りで、終わるとおすすめ譜面も更新されます。",
    importHint: "エクスポートしたファイルを取り込めます。既存のデータは上書きされません。各ベストの日付が保たれるよう、古いファイルから順に取り込んでください。",
    settingsInfo: "Discord コマンドの既定の設定です。",
    settings: "bot の設定",
    layout: "既定の表示",
    layouts: { both: "画像とテキスト", embed: "テキストのみ", image: "画像のみ" } as Record<string, string>,
    targets: "既定の目標",
    challenges: { easy: "やさしめ", balanced: "バランス", hard: "挑戦的", extreme: "大穴" } as Record<string, string>,
    newDifficulty: "/new の既定の難易度",
    any: { any: "指定なし" } as Record<string, string>,
    compare: "/compare を許可",
    leaderboard: "サーバーのランキング",
    history: "毎日の履歴読み取り",
    notify: "毎日の DM 通知",
    on: "オン",
    off: "オフ",
    change: (
      <>
        Discord の <code>/settings</code> で変更できます。
      </>
    ),
    unlink: "連携解除",
    unlinkHint: "maimai のセッション、スコア、履歴、プレイ回数を削除します。このサイトへの Discord ログインはそのまま残ります。",
    unlinkYes: "連携を解除して削除する",
    keep: "やめる",
    unlinkAsk: "maimai アカウントの連携を解除…",
  },
  list: { sep: "、" },
  // ---- dashboard: table columns, shared by the tabs (they also label each cell on a phone)
  cols: {
    chart: "譜面", now: "現在", target: "目標", rank: "ランク", odds: "確率", plays: "プレイ数", gain: "上昇", total: "累計",
    aimFor: "目標", firstPass: "初見予想", oddsS: "S 確率", usually: "普段", needs: "必要", genre: "ジャンル",
    constant: "定数", worth: "価値", achievement: "達成率", lamp: "ランプ", dx: "でらっくスコア", rating: "レート", time: "時刻",
    jacket: "ジャケット",
  },
  // ---- dashboard: the target levels the picks and new charts share
  challenge: {
    label: { easy: "やさしめ", balanced: "バランス", hard: "挑戦的", extreme: "大穴" } as Record<string, string>,
    picksNote: {
      easy: "最も確実な目標、成功率はおよそ五分五分",
      balanced: "手間に対して最も伸びる、成功率はおよそ4回に1回",
      hard: "難しめの目標、成功率はおよそ6回に1回",
      extreme: "最も大きく伸びる、成功率はおよそ10回に1回",
    } as Record<string, string>,
    newNote: {
      easy: "ほぼ確実に S が取れる譜面",
      balanced: "S が取れる上限のすぐ下で、最もお得な譜面",
      hard: "S が取れる中で最も難しい譜面",
      extreme: "S の上限より上、初見は賭け",
    } as Record<string, string>,
  },
  // ---- dashboard: what to play tab
  picksTab: {
    howHard: "目標の難しさ",
    filtered: (scope: string) => ` · おすすめと新しい譜面を ${scope} に絞り込み中。ロードマップは絞り込まれません。`,
    onlyLevel: "このレベルだけ",
    anyLevel: "全レベル",
    level: (l: string) => `レベル ${l}`,
    constantPlaceholder: "または定数（13.2、13.0-13.4 など）",
    onlyConstant: "この定数・範囲だけ",
    scopeHint: "13+ のようなレベル、13.2 のような定数、13.0-13.4 のような範囲で指定してください。",
    thePicks: "おすすめ譜面",
    finding: "譜面を探しています…",
    nothing: (scope: string, level: string) => `「${level}」では、${scope || "このレベル"} にベスト50を上げられる譜面がありません。難しめの設定にするか、絞り込みを解除してください。`,
    fallback: (from: string) => `「${from}」ではまだベスト50を上げられる譜面がないため、「バランス」のおすすめを表示しています。`,
    grindInfo: "遊んだことのある譜面のうち、スコアを上げるとレーティングが最も伸びるもの。「目標」は十分に狙えるスコア、「上昇」はそれで得られるレーティングです。",
    grind: (n: number) => `詰める譜面 · ${n} 譜面 · `,
    everyTarget: "（すべての目標を達成した場合）",
    noMovers: "この設定では、遊んだ譜面でベスト50を上げられるものがありません。別の設定を試すか、下の新しい譜面を見てください。",
    estimated: "譜面データベース未登録 · 定数はレベルからの推定 · ",
    neverExpect: (n: string) => `未プレイ · 初見で約 ${n}% の見込み`,
    usually: (n: string) => `普段は約 ${n}%`,
    dropped: " · この譜面の唯一のプレイはそれを大きく下回っていたため、失敗プレイとして扱っています",
    new: "未プレイ",
    triesInfo: "詰める譜面が少ないため表示している未プレイ譜面。初見でレーティングが上がるものもあれば、苦手な配置の練習になるものもあります。",
    tries: (n: number) => `初見で遊ぶ価値あり · ${n} 譜面`,
    banks: "保留",
    roadInfo: "合わせて次のレーティングの節目に届く目標。% は普段のスコアをどれだけ上回る必要があるかで、低いほど簡単です。",
    road: (goal: string) => `${goal} へのロードマップ`,
    covers: (n: number) => `必要な +${n} をすべてカバー`,
    partway: (total: number, needed: number, short: number) => `必要な +${needed} のうち +${total} · あと ${short}`,
    stretch: (n: string) => `普段のスコアより ${n}%`,
    noRoute: "この設定ではまだルートがありません。別の設定を試してください。",
    neverPlayed: "未プレイ",
    plays: (n: number) => `${n} プレイ`,
    playsUnknown: "プレイ数不明",
    newInfo: "初見でベスト50に入る可能性がある未プレイ譜面。「保留」はスコアとしては記録されますが、まだレーティングは上がりません。",
    newCharts: (from: string, to: string) => `試したい新しい譜面 · ${from}–${to}`,
    noNew: "この範囲に未プレイの譜面はありません。",
    nearInfo: "そのレベルで普段どおりのスコアを出せばベスト50に入る譜面。「必要」は入るのに必要なスコアです。",
    near: "ベスト50にあと少し",
    noNear: "今はベスト50に近い譜面はありません。",
  },
  // ---- dashboard: new charts tab
  newTab: {
    howHard: "探す難しさ",
    difficulty: "難易度",
    expertUp: "EXPERT 以上",
    level: "レベル",
    lean: "特性で絞る",
    anyTrait: "特性を問わない",
    weak: "苦手なところ",
    strong: "得意なところ",
    leaning: (weak: boolean) => `${weak ? "苦手なところ" : "得意なところ"}を優先：`,
    anyNote: (note: string) => `${note}。このアカウントで未プレイの、この定数範囲の譜面です。「初見予想」は、その定数での普段のスコアより少し低めです。`,
    levelNote: (level: string, mode: string) => `このアカウントで未プレイのレベル ${level} の譜面すべてを「${mode}」向けに並べています。「初見予想」は、その定数での普段のスコアより少し低めです。`,
    theNew: "新しい譜面",
    looking: "譜面を探しています…",
    headInfo: "「初見予想」は初めて遊んだときに予想されるスコア、「価値」は S を取ったときに増えるレーティングです。",
    head: (n: number, level: string, from: string, to: string) => `${n} 譜面 · ${level !== "any" ? `レベル ${level} · ` : ""}定数 ${from}–${to}`,
    sorted: (mode: string) => `「${mode}」向けの並び`,
    allPlayed: (level: string) => `この難易度のレベル ${level} の譜面はすべてプレイ済みか、該当する譜面がありません。`,
    noneHere: "この範囲に未プレイの譜面はありません。",
    tryAnother: "別のレベルや難易度を試してください。",
    thisVersion: "現行バージョン",
    banks: (n: number) => `保留 ${n}`,
  },
  // ---- dashboard: all charts tab
  chartsTab: {
    sorts: {
      "rating|d": "レートの高い順", "bestMatch|d": "検索に近い順", "constant|d": "定数の高い順", "constant|a": "定数の低い順",
      "accuracy|a": "苦手な順", "accuracy|d": "得意な順", "dx|d": "でらっくスコアの高い順", "plays|d": "プレイ数の多い順", "title|a": "曲名順",
    } as Record<string, string>,
    search: "曲名、アーティスト、レベル 13+、定数 13.8",
    allDiffs: "全難易度",
    type: "譜面の種類",
    bothTypes: "でらっくす・スタンダード",
    dxOnly: "でらっくすのみ",
    stdOnly: "スタンダードのみ",
    anyRank: "全ランク",
    belowA: "A 未満",
    pool: "枠",
    allCharts: "全譜面",
    inBest50: "ベスト50に入っている",
    current: "現行バージョン",
    older: "旧バージョン",
    sort: "並び順",
    countInfo: "スコアのある全譜面。「ランプ」は FC と FS の記録です。",
    count: (shown: string, all: string) => `${all} 譜面中 ${shown} 譜面`,
    totalRating: (n: string) => `レート合計 ${n}`,
    noMatch: "条件に合う譜面がありません。",
    best50: "ベスト50",
    estimatedTitle: "譜面データベースにまだ登録されていないため、定数とレートはレベルからの推定です。読み取りで新曲が見つかるとデータベースが更新されます。",
    estimated: "新曲 · 定数は推定",
    more: (n: number) => `さらに ${n} 件表示`,
  },
  // ---- dashboard: recent tab
  recentTab: {
    judgements: "判定",
    fastLate: (fast: number, late: number, combo: string, max: string) => `FAST ${fast} · LATE ${late} · コンボ ${combo} / ${max}`,
    sync: (n: string, max: string) => ` · シンク ${n} / ${max}`,
    notes: "ノーツ",
    lost: "減点",
    all: "合計",
    pointsLost: "減点の内訳",
    couldntLoad: "このプレイを読み込めませんでした",
    none: (
      <>
        保存されたプレイはまだありません。「アカウント」タブで読み取るか、Discord でいずれかのコマンドを実行してください。<code>/settings history</code>{" "}
        で毎日の読み取りをオンにすると、読み取りの間にプレイが maimai の直近50プレイから消えてしまうのを防げます。
      </>
    ),
    saved: (n: string, since: string) => `${since} から ${n} プレイを保存`,
    linking: "連携時",
    latest: (n: string) => `（最新の ${n} 件を表示）`,
    stay: "。アカウントが連携されている間、プレイはここに残ります。",
    day: (n: number, bests: number) => `${n} プレイ · ベスト更新 ${bests}`,
    newBest: "ベスト更新",
    loadingPlay: "maimaiでらっくすNET からプレイを読み込んでいます…",
    more: (n: number) => `さらに ${n} 件表示`,
  },
  // ---- dashboard: look up tab
  lookupTab: {
    notInDb: (title: string, yours: string, one: boolean) =>
      `「${title}」はまだ譜面データベースに登録されていません。データベースより新しい曲のため、ジャケット・定数・このページは登録後に表示されます。それまでは、あなたのスコア（${yours}）はレベルから推定した定数で計算されます。`,
    yourRow: (difficulty: string, level: string, accuracy: string) => `${difficulty} ${level}：${accuracy}%`,
    noSong: (title: string) => `「${title}」に一致する曲は譜面データベースにありません。`,
    placeholder: "曲名、アーティスト、譜面作者",
    label: "曲を検索",
    searchFailed: (why: string) => `検索に失敗しました。${why}`,
    noMatches: "見つかりませんでした。曲名の一部、ローマ字読み、アーティスト名や譜面作者名で試してください。",
    chartedBy: (who: string) => `譜面作者：${who}`,
    neverPlayed: "未プレイ",
    looking: "検索しています…",
    intro: "曲を検索すると、スコア、各ランクの達成見込み、スコアの推移、譜面動画が見られます。ほかのタブで曲名を押しても、ここに表示されます。",
  },
  // ---- dashboard: one chart, in the look up tab
  detail: {
    constNote: (n: string) => ` · 初記録時の定数は ${n}`,
    stars: (n: number) => `でらっくスター 5 個中 ${n} 個`,
    regions: { jp: "日本", intl: "海外", cn: "中国" } as Record<string, string>,
    regionsTitle: "この譜面がある地域",
    everywhere: "全地域",
    only: "のみ",
    tier: { basic: "BASIC", advanced: "ADVANCED", expert: "EXPERT", master: "MASTER", remaster: "Re:MASTER" } as Record<string, string>,
    bpm: (n: number | string) => `BPM ${n}`,
    currentVersion: "現行バージョン",
    artistUnknown: "アーティスト不明",
    charts: "この曲の譜面",
    constant: (n: string) => ` · 定数 ${n}`,
    notes: (n: string) => ` · ${n} ノーツ`,
    chartedBy: (who: string) => ` · 譜面作者：${who}`,
    added: (when: string) => ` · 追加日 ${when}`,
    removed: "削除済み",
    tagged: "maiノーツ の編集者によるタグ",
    measured: "譜面のノーツから算出",
    clickTrait: " · クリックするとこの特性を持つ譜面をすべて表示",
    clickOne: "押すと、その特性を持つ譜面をすべて表示します。",
    communityNote: "実線のタグは maiノーツ の編集者によるもの、点線のタグは譜面のノーツ・BPM・密度から算出したものです。",
    measuredNote: "これらは譜面のノーツ・BPM・密度から算出したものです。この譜面には maiノーツ の編集者によるタグがまだありません（主に MASTER 譜面にタグが付けられています）。",
    offsetNote: "数値は、この特性を持つ譜面でのスコアが、あなたの曲線と比べてどうかを示します。",
    yourScore: "あなたのスコア",
    rating: (n: number) => `レート ${n}`,
    lamp: "ランプ",
    dx: "でらっくスコア",
    of: (n: string) => `/ ${n} · `,
    maxUnknown: "最大値不明",
    plays: "プレイ数",
    fromNet: "maimaiでらっくすNET より",
    playsUnknown: "次の読み取りまで不明",
    best50: "ベスト50",
    neverPlayed: "未プレイ",
    usual: (n: string) => `普段なら約 ${n}%`,
    prediction: "予測",
    range: (low: string, high: string) => `調子が良ければ ${low}〜${high}`,
    newBest: (n: number) => `次のプレイでベストを更新する確率 ${n}%`,
    firstTry: "初見、このレベルでのプレイ傾向から予測",
    tierOffset: (tier: string, n: string) => ` · ${tier} のスコアは曲線より ${n}`,
    ladderInfo: "各ランクに必要な達成率、得られるレート、ベスト50への上昇分、達成できる確率。強調された行は現実的な目標です。",
    ladderPlayed: "各ランクの価値",
    ladderNew: "各ランクを取った場合の価値",
    ladderHintPlayed: "「上昇」はベスト50に加わる分 · 「確率」はこの譜面でそのスコアを出せる頻度",
    ladderHintNew: "確率は初見の場合",
    need: "必要",
    unlockInfo: "SilentBlue RemyWiki に載っている解禁条件。エリアの場合は、そこでのあなたの距離も表示します。",
    unlock: "解禁方法",
    fromWiki: "SilentBlue RemyWiki より",
    loadingWiki: "Wiki から読み込んでいます…",
    areaProgress: (title: string, where: string) => `${title} の進み具合：${where}`,
    notStarted: "未開始",
    completed: "、達成済み",
    nextAt: (km: string) => `、次の報酬は ${km} km`,
    noUnlock: "Wiki に解禁条件がないため、最初から解禁されているはずです。",
    noPage: "Wiki にはまだこの曲のページがありません。",
    historyInfo: "bot が保存したこの譜面のすべてのプレイ。点がプレイ、線がベストです。",
    history: "スコアの推移",
    points: (n: number) => `${n} 件`,
    watch: "YouTube で譜面を見る",
    searchYoutube: "YouTube で譜面を検索",
  },
  // ---- dashboard: browse charts by trait
  patterns: {
    open: "または特性から譜面を探す",
    placeholder: "特性を検索（縦連、乱打、スライド多め…）",
    label: "特性を検索",
    anyDifficulty: "全難易度",
    close: "閉じる",
    noMatch: (find: string) => `「${find}」に一致する特性はありません。`,
    taggedTitle: (n: number) => `maiノーツ のタグ · ${n} 譜面`,
    measuredTitle: (n: number) => `各譜面から算出 · ${n} 譜面`,
    intro: "実線の特性は maiノーツ の編集者によるタグで、MASTER 譜面の約3分の1に付いています。点線の特性は譜面から算出したものです。選ぶと、その特性を持つ譜面を難しい順にすべて表示します。",
    measured: " · 各譜面から算出",
    charts: (n: number) => ` · ${n} 譜面`,
    played: (n: number) => `、うち ${n} 譜面プレイ済み`,
    updating: " · 更新中…",
    none: "このレベル・難易度には、この特性を持つ譜面がありません。別の条件を試してください。",
    neverPlayed: "未プレイ",
    also: (tags: string) => ` · ほかに ${tags}`,
  },
  // ---- dashboard: areas tab
  areasTab: {
    km: (n: string) => `${n} km`,
    ended: (when: string) => `${when} に終了`,
    endsToday: "今日まで",
    endsTomorrow: "明日まで",
    endsIn: (days: number, when: string) => `あと ${days} 日 · ${when} まで`,
    ready: "受け取れます",
    toGo: (km: string) => `あと ${km}`,
    playsAtPace: (n: number) => ` · 今のペースで約 ${n} プレイ`,
    nextReward: "次の報酬",
    notListed: "このエリアの情報はありません",
    completed: "達成済み",
    everyReward: "すべての報酬を獲得",
    firstPlay: "初回プレイ",
    gift: "プレゼントがもらえます",
    totalDistance: "総距離",
    since: (km: string, when: string) => `${when} から +${km}`,
    pace: (n: number, own: boolean) => `1プレイあたり ${n} km${own ? "" : "（ほかのエリアから推定）"}`,
    plays: (n: number) => ` · 約 ${n} プレイ`,
    states: { in_progress: "進行中", completed: "達成済み", not_started: "未開始" } as Record<string, string>,
    yourAreas: "エリア",
    loading: "エリアを読み込んでいます…",
    none: "エリアのデータはまだありません。「アカウント」タブで読み取るか、Discord でいずれかのコマンドを実行してください。",
    travelInfo: "プレイするたびに今いるエリアを進み、決まった距離で報酬が解放されます。最後の読み取り時点の情報です。",
    travel: "エリアの旅",
    updated: (when: string) => `更新：${when}`,
    lastRefresh: "最後の読み取り時点",
    underWay: "進行中",
    notStarted: "未開始",
    perPlay: "1プレイあたりの距離",
    paceValue: (pace: number, readings: number) => `${pace} km · ${readings} 回の読み取りから`,
    notMeasured: "まだ計測されていません",
    hint: "maimaiでらっくすNET には総距離しか表示されないため、残りプレイ数は2回の読み取りの間に距離が変わってから表示されます。エリア名は SilentBlue RemyWiki のものです。",
    progressInfo: "途中まで進んだエリアと、次の報酬までの距離・プレイ数。",
    progress: "進行中",
    eventsInfo: "期間限定のエリア。開催中にしか報酬はもらえません。",
    events: "イベントエリア",
    untouchedInfo: "まだ始めていないエリア。筐体で選んで1回プレイすると、最初のプレゼントがもらえます。",
    untouched: (n: number) => `未開始 · ${n}`,
    firstGift: "それぞれ初回プレイでプレゼントがもらえます",
    waitingInfo: "まだ始めていないイベントエリアと、それぞれの終了日。",
    waiting: "未開始のイベント",
    endedInfo: "終了したイベント。maimaiでらっくすNET にはもう距離が表示されません。",
    endedEvents: (n: number) => `終了したイベント · ${n}`,
    namesOnly: "名前と日付のみ",
    doneInfo: "達成したエリアと、それぞれにかかった距離。",
    done: (n: number) => `達成済み · ${n}`,
  },
  // ---- dashboard: public profile settings
  sharing: {
    sections: {
      best50: ["ベスト50", "レーティングを構成する50譜面"],
      traits: ["特性", "得意なところと苦手なところ"],
      recent: ["最近のプレイ", "直近20プレイ"],
      areas: ["エリア", "各エリアの進み具合"],
    } as Record<string, [string, string]>,
    couldntSave: "保存できませんでした",
    couldntCopy: "コピーできませんでした。リンクを選択して手動でコピーしてください。",
    info: "リンクを知っている人なら誰でも見られます。Discord アカウントは表示されず、検索エンジンにも載りません。",
    title: "公開プロフィール",
    shared: "公開中",
    private: "非公開",
    intro: "初期状態はオフです。名前、レーティング、プレイ回数と、オンにした項目が表示されます。",
    stop: "公開をやめる",
    create: "公開リンクを作る",
    newLink: "リンクを作り直す",
    copied: "コピーしました",
    copy: "コピー",
    customise: "Discord のカードをカスタマイズ",
    breaks: "リンクを作り直すと、古いリンクは使えなくなります。",
  },
  // ---- dashboard: the Discord card window
  embedCard: {
    picture: {
      chart: ["レーティングの推移", "下部のグラフ"],
      gain: ["レーティングの上昇", "いつからどれだけ上がったか"],
      charts: ["スコアのある譜面数", "スコアを記録した譜面の数"],
      plays: ["プレイ回数", "遊んだクレジット数"],
    } as Record<string, [string, string]>,
    visuals: {
      curve: ["レーティングの推移", "レーティングの履歴"],
      best50: ["ベスト50", "レーティングを構成する50譜面（高い順）"],
      traits: ["プレイの傾向", "特性のチャート"],
      figures: ["数値のみ", "グラフなし、数値だけ"],
    } as Record<string, [string, string]>,
    text: {
      region: ["地域", "レーティングの横に、海外版か日本版か"],
      charts: ["スコアのある譜面数", "レーティングの横に、その数"],
    } as Record<string, [string, string]>,
    label: "リンクを貼ったときに Discord に表示されるカード",
    title: "Discord のカード",
    close: "閉じる",
    intro: "誰かがあなたのリンクを貼ったときに Discord に表示されるものです。名前とレーティングは常に表示され、それ以外は変更できます。",
    looks: "カードの見た目",
    imageAlt: "カードの画像",
    notReady: "画像はまだ準備中です。Discord がカードを読み込むときには表示されます。",
    image: "画像",
    needs: (section: string) => `先に上で「${section}」をオンにしてください`,
    colour: "色",
    custom: "カスタム",
    showImage: "画像を表示",
    showImageNote: "オフにすると、名前・レーティング・ボタンだけが表示されます",
    onImage: "画像に載せるもの",
    underName: "名前の下",
    cache: "Discord はカードを30分ほどキャッシュします。変更は次にリンクを貼ったときに反映され、すでに送ったリンクは古いカードのままです。",
  },
  // ---- dashboard: beta features
  beta: {
    lessThanMinute: "残り1分未満",
    minutesLeft: (n: number) => `残り約 ${n} 分`,
    hoursLeft: (h: number, m: number) => `残り約 ${h} 時間${m ? ` ${m} 分` : ""}`,
    readSoFar: "これまでに読み取った譜面",
    charts: (done: string, total: string, percent: string) => `${done} / ${total} 譜面 · ${percent}%`,
    verdicts: { better: "良くなった", same: "変わらない", worse: "悪くなった" } as Record<string, string>,
    couldntSend: "送信できませんでした",
    compared: "オフのときと比べて：",
    editNote: "メモを編集",
    addNote: "メモを追加",
    placeholder: "何が変わりましたか？",
    save: "保存",
    pickFirst: "先にどれかを選んでください。",
    youSaid: (verdict: string) => `あなたの回答：${verdict}`,
    off: "次の読み取りでオフになります。",
    notReady: "オンにしましたが、bot はまだこれを実行できないため、今のところ変化はありません。",
    on: "次の読み取りでオンになります。上の読み取りボタンを押すとすぐに確認できます。",
    couldntSave: "保存できませんでした",
    info: "動作はするものの、まだ完成していない機能です。オフにすれば元に戻ります。",
    title: "ベータ版",
    count: (n: number) => `${n} 件オン`,
    none: "オンなし",
    hint: "これらは特性やおすすめ譜面を変えることがあります。残すかどうかの判断のため、感想を教えてください。",
  },
  // ---- dashboard: graphs
  graphs: {
    curveInfo: "線は、あなたの結果から求めた各定数での予想スコアです。帯はスコアのばらつき、点はそれぞれの譜面です。",
    curve: "あなたの曲線",
    fromCharts: (n: number) => `${n} 譜面から`,
    curveLabel: "譜面定数ごとのスコア",
    recentBest: "最近のプレイで出したベスト",
    comfortable: "安定",
    sExpected: "S 見込み",
    hardestPlayed: "最高プレイ",
    constantAxis: "譜面定数 →",
    achievementAxis: "達成率",
    curveHint: "帯より下の点が、おすすめ譜面の候補になります。あまり遊んでいない範囲ほど帯は広くなります。",
    onlyOne: (score: string, on: string) => `スコアはまだ1件だけです：${on} に ${score}。`,
    noScores: "この譜面の保存されたスコアはまだありません。",
    afterRefresh: "新しいプレイは読み取りのたびにここに表示されます。",
    historyLabel: "スコアの推移",
    point: (score: string, on: string, constant: string, rating: number) => `${on} に ${score} · 定数 ${constant} · レート ${rating}`,
    ratingOverTime: "レーティングの推移",
    oneRating: (n: number) => `保存されたレーティングはまだ1件だけです：${n}。`,
    noRating: "レーティングの履歴はまだありません。",
    eachRefresh: "読み取るたびに1点ずつ増えます。",
    since: (gain: string, when: string) => `${when} から ${gain}`,
    ratingLabel: "レーティングの履歴",
  },
  // ---- dashboard: traits tab
  traitsTab: {
    gate: "「確定」の特性は偶然では50回に1回未満しか起きない差で、譜面を半分に分けてもどちらでも成り立つものです。おすすめ譜面に影響するのはこれだけです。「傾向」は20回に1回未満のもので、ヒント程度に見てください。",
    info: (gate: string) => `同じ配置・ノーツ構成・BPM の譜面でのスコアが、あなたの曲線と比べてどうか。${gate}`,
    tagsFrom: "配置のタグは maiノーツ のものです。",
    how: "プレイの傾向",
    measured: (groups: number, charts: number) => `${groups} グループを計測 · スコアのある譜面 ${charts}`,
    noClear: "はっきりした特性はまだありません。どのグループも普段のスコアに近すぎるか、譜面が足りません。保存されたプレイはすべて使われるので、遊ぶほどはっきりします。",
    gapsInfo: "普段のスコアから最も離れている4グループ。どれも確定ではないので、参考程度に見てください。",
    gaps: "差が大きいもの（未確定）",
    counts: (confirmed: number, leaning: number) => `確定 ${confirmed} · 傾向 ${leaning}`,
    byChance: (n: number) => `（うち約 ${n} は偶然）`,
    rest: (watch: number, even: number, charts: number) => ` · 要観察 ${watch} · 平均並み ${even} · スコアのある譜面 ${charts}`,
    wheelInfo: "真ん中の輪があなたの平均です。外側ほど得意、内側ほど苦手で、? が付いた点は未確定です。",
    wheelLater: "十分な譜面がある特性が3つ以上になると、チャートが表示されます。",
    weakInfo: "曲線より低いスコアになる特性。大きい数字は達成率の差、小さい数字は譜面数です。",
    weak: "点を落としているところ",
    noWeak: "平均を下回るものはまだありません。",
    strongInfo: "曲線より高いスコアになる特性。",
    strong: "得意なところ",
    noStrong: "平均を上回るものはまだありません。",
    groupsInfo: "特性を種類ごとにまとめ、それぞれの譜面数で重み付けしたもの。グループを押すと中の特性が見られます。",
    groups: "特性のグループ",
    practiceInfo: "苦手な配置ごとに、あなたのレベルに合った譜面をいくつか。上達を確かめられるよう、遊んだことのある譜面を先に並べています。",
    practice: "練習するとよいもの",
    measuredTitle: "譜面のノーツから算出",
    notes: "ノーツ",
    leaning: "傾向",
    watching: "要観察",
    countTitle: (charts: number, plays: number) => `${charts} 譜面${plays ? `、${plays} プレイ` : ""}`,
    oneIn: (n: number) => `${n} 回に1回 · `,
    plays: (n: number) => ` · ${n} プレイ`,
    charts: (n: number) => `${n} 譜面`,
    notPlayed: "未プレイ",
    oldScore: (n: string) => `以前のスコア ${n}%`,
    youHave: (n: string) => `現在 ${n}%`,
    familyCount: (traits: number, charts: string) => `${traits} 特性 · ${charts} 譜面`,
    aboutEven: "平均並み：",
    andMore: (n: number) => ` ほか ${n} 件`,
    evenNote: (lean: string) => `。十分な譜面数があり、普段のスコアとの差が ±${lean} 以内のものです。`,
    chance: (n: number) => `偶然なら ${n} 回に1回`,
    radarLabel: "平均と比べたあなたの特性",
  },
  // ---- dashboard: judgements, under the traits
  judgeTab: {
    late: (n: number) => `ずれた判定の ${n}% が LATE で、少しリズムに遅れ気味です。`,
    early: (n: number) => `ずれた判定の ${n}% が FAST で、少しリズムより早め気味です。`,
    even: "ずれた判定は FAST と LATE がほぼ半々です。",
    info: "最近のプレイの判定ページから。ノーツの種類ごとにどれだけ点を落としているか、早めか遅めかを示します。",
    title: "判定",
    summary: (plays: number, lost: string) => `${plays} プレイ · 1プレイあたり ${lost} 点の減点`,
    needs: "3プレイ分の判定データが必要です。「最近」タブでプレイの判定を開くか、「アカウント」タブで読み取るか、Discord でいずれかのコマンドを実行してください。",
    notes: "ノーツ",
    ofNotes: "ノーツの割合",
    worth: "配点",
    ofLoss: "減点の割合",
    per100: "100 ノーツあたり",
    clean: "CRITICAL 率",
    weak: (kind: string, loss: number, worth: number) => `${kind}ノーツは配点が ${worth}% なのに減点の ${loss}% を占めていて、最も点を落としています。`,
    noWeak: "配点以上に点を落としているノーツの種類はありません（ここでは BREAK を TAP 5個分として数えています）。",
    bonus: (per: string, share: number) => `BREAK のボーナスの取りこぼしで1プレイあたり ${per}、減点の ${share}% を失っています。ボーナスは CRITICAL の BREAK でしか得られないため、CRITICAL を逃していることが原因です。表には含まれていません。`,
    fast: "FAST",
    lateBar: "LATE",
  },
  // ---- a shared profile, at /p/...
  profile: {
    readings: (n: number) => `${n} 回の記録`,
    ratingRange: (low: number, high: number) => `レーティング ${low} から ${high}`,
    poolRating: (n: string) => `レート ${n}`,
    emptyPool: "この枠にはまだ譜面がありません。",
    tabs: { overview: "概要", best50: "ベスト50", traits: "特性", recent: "最近", areas: "エリア" } as Record<string, string>,
    goneTitle: (
      <>
        このプロフィールは<em>公開されていません</em>。
      </>
    ),
    goneLede: "リンクが無効にされたか、新しいリンクに置き換えられた可能性があります。送ってくれた人に最新のリンクを聞いてください。",
    whatRasmai: "Rasmai とは →",
    shared: "公開プロフィール",
    sub: (titles: string, plays: string, read: string) => `${titles} · ${plays} プレイ · ${read} 読み取り`,
    charts: "譜面数",
    shares: "このプロフィールで公開されているもの",
    overTime: "レーティングの推移",
    fromChecks: "保存された記録から",
    glance: "ひと目でわかる情報",
    scored: "スコアのある譜面",
    totalPlays: "総プレイ回数",
    bestChart: "最高単曲レート",
    lastRead: "最終読み取り",
    sharesTabs: "上のタブが、このプレイヤーの公開しているものです。それ以外は非公開です。",
    onlyRating: "このプレイヤーはレーティングだけを公開しています。",
    how: "プレイの傾向",
    ownCurve: "本人の曲線と比べて",
    weak: "点を落としているところ",
    noWeak: "苦手なところは見つかりませんでした。",
    strong: "得意なところ",
    noStrong: "得意なところはまだ見つかっていません。",
    recent: "最近のプレイ",
    newest: "新しい順",
    noPlays: "記録されたプレイはまだありません。",
    inProgress: (n: number) => `進行中・達成済み ${n}`,
    done: " · 達成済み",
    footLeft: (
      <>
        Rasmai で公開 · <a href="/">Rasmai とは</a> · SEGA とは無関係です
      </>
    ),
    footRight: "このページには、プレイヤーが公開を選んだものだけが表示されます",
  },
  // ---- trait names: the editors' tags arrive in Japanese already; these are the ones the bot names in English
  traitNames: {
  // measured from the notation
  "fast slides": "速いスライド",
  "multi-touch": "タッチの同時押し",
  "both hands at once": "拘束中の処理",
  bursts: "瞬間密度",
  "reaching across the screen": "大きな移動",
  "tempo changes": "ソフラン",
  "long streams": "長い乱打",
  trills: "トリル",
  jacks: "縦連",
  "touch sweeps": "タッチの流し",
  "spinning round the ring": "回転",
  "delayed slides": "ウミユリ",
  "trills on the spot": "その場トリル",
  "trills across the screen": "離れたトリル",
  "trills against a held button": "軸押しトリル",
  "fan slides": "扇スライド",
  "a bouncing rhythm": "ハネリズム",
  "chained slides": "連結スライド",
  "touch clusters": "タッチ複合",
  "a trill over a slide": "スライド中のトリル",
  "overlapping loop slides": "重なる回転スライド",
  "slides at different speeds": "速度違いスライド",
  "slides fired from one spot": "同始点の連続スライド",
  "a slide traced straight back": "往復スライド",
  // note mix, tempo and size
  "slide-heavy": "スライドが多い",
  "hold-heavy": "ホールドが多い",
  "break-heavy": "ブレイクが多い",
  "touch-heavy": "タッチが多い",
  "slow songs (under 130 BPM)": "遅い曲（BPM130未満）",
  "very fast (over 210 BPM)": "とても速い曲（BPM210超）",
  "light charts (under 620 notes)": "ノーツが少ない譜面（620未満）",
  "a lot of notes (890+)": "物量譜面（890ノーツ以上）",
  // what a chart is
  "DX charts": "でらっくす譜面",
  "standard charts": "スタンダード譜面",
  "maimai-era songs (before DX)": "旧筐体時代の曲（DX以前）",
  "DX to FESTiVAL songs": "DX〜FESTiVAL の曲",
  "BUDDiES and newer songs": "BUDDiES 以降の曲",
  // the families the wheel is drawn on
  "slide control": "スライド処理",
  rotation: "回転",
  "hand management": "手の運び",
  "speed and density": "速さと物量",
  touch: "タッチ",
  reading: "読み",
  // the editors' tags that are about the chart rather than a technique
  notorious: "地雷",
  "good to practice on": "練習向き",
  "a maimai standard": "定番",
  "one hard section": "局所難",
  "hard throughout": "全体難",
  "hard to score": "スコアが伸びにくい",
  },
  chartsBy: (designer: string) => `${designer} の譜面`,
  noteTrait: (kind: string) => `${kind}ノーツ`,
  noteKinds: { tap: "タップ", hold: "ホールド", slide: "スライド", touch: "タッチ", break: "ブレイク" },
  // ---- long pages, set out as the page shows them
  docs: {
    commands: () => (
    <>
      <h2>はじめに</h2>
      <div className="cmds">
        <Cmd name="/login">
          maimai アカウントを連携します。届いたリンクから maimaiでらっくすNET にログインし、ボタンを1回押すだけ。約1分で、最初に1回やれば済みます。ほかのコマンドを使う前に必要です。海外版アカウントはブックマークで連携し、日本版アカウントは{" "}
          <code>/login region:Japan</code> を実行して SEGA ID でログインします。中国版のアカウントはまだ連携できません。
        </Cmd>
        <Cmd name="/help">このページの短い版を Discord で表示します。</Cmd>
        <Cmd name="/invite">Rasmai をサーバーや自分のアカウントに追加し、ダッシュボードへのリンクを表示します。</Cmd>
      </div>

      <h2>遊ぶ譜面を決める</h2>
      <p>
        おすすめは、上がる
        <Term word="レーティング" means="maimai で名前の横に表示される数値。ベスト50の譜面のレートの合計です。" />
        が大きい順に並びます。
      </p>
      <div className="cmds">
        <Cmd name="/analyze" args="[challenge] [level]">
          詰めるべき譜面のリスト。各行に譜面、目標スコア、それを取れる
          <Term word="確率" means="スコアのばらつきから計算した、1回のプレイで目標に届く確率です。" />
          が表示されます。<code>challenge</code> で目標の難しさが変わります。Easier はおよそ2回に1回、Balanced は4回に1回、Challenging は6回に1回、Long
          shots は10回に1回届く目標です。<code>level</code> では <code>13+</code> のようなレベル、<code>13.2</code> のような
          <Term word="譜面定数" means="13+ のようなレベルの裏にある、13.2 などの正確な難易度。レーティングはこの値から計算されます。" />
          、<code>13.0-13.4</code> のような範囲で絞り込めます。
        </Cmd>
        <Cmd name="/plan" args="[target] [difficulty] [min_level]">
          指定したレーティングまでのルートを計画します。合計がそこに届く目標のリストを、それぞれの確率と累計つきで表示します。
        </Cmd>
        <Cmd name="/session" args="[credits]">
          使えるクレジット数を伝えると、1クレずつ「上昇×確率」が最も大きい所に割り振ります。ウォームアップが先で、同じ譜面を繰り返すのは外したときだけです。
        </Cmd>
        <Cmd name="/new" args="[difficulty] [level] [focus]">
          まだ遊んだことのない、あなたのレベルに合った譜面を、初見での予想スコアつきで紹介します。<code>focus</code> を付けると、苦手または得意な
          <Term word="特性" means="縦連・乱打・スライドの連結・ソフランなど、譜面に含まれる配置の種類です。" />
          の譜面に寄せます。
        </Cmd>
        <Cmd name="/random" args="[level] [difficulty] [unplayed]">
          あなたのレベル付近からランダムに譜面を選びます。
        </Cmd>
      </div>

      <h2>スコア</h2>
      <div className="cmds">
        <Cmd name="/b50" args="または /top">
          レーティングを構成する50譜面。
          <Term word="新曲枠" means="現行バージョンの譜面。上位15曲がレーティングに入ります。" />
          から15曲、
          <Term word="旧曲枠" means="過去バージョンの譜面。上位35曲がレーティングに入ります。" />
          から35曲です。
        </Cmd>
        <Cmd name="/chart" args="<title> [difficulty]">
          1つの譜面の詳細。あなたのスコア、予想スコア、各ランクの価値、譜面の配置、解禁方法、動画を表示します。日本語・ローマ字・英語で検索できます。
        </Cmd>
        <Cmd name="/charts" args="[pattern] [level] [difficulty]">
          配置やレベルで譜面を一覧し、それぞれにあなたのスコアを並べます。苦手な配置の練習にぴったりです。
        </Cmd>
        <Cmd name="/recent" args="[play]">
          最近のセッション、すべてのプレイ、自己ベスト更新、レートに入った譜面。<code>play:1</code> で1プレイを開くと、すべての
          <Term word="判定" means="各ノーツの叩き方：CRITICAL PERFECT・PERFECT・GREAT・GOOD・MISS。" />
          と、それで失った点数がわかります。
        </Cmd>
        <Cmd name="/dxscore">
          <Term word="でらっくスコア" means="最良のタイミングで叩けたノーツの多さを表す別のスコア。レーティングには影響しません。" />
          の星と、次の星に最も近い譜面を表示します。
        </Cmd>
        <Cmd name="/progress">レーティングの推移と上がるペース、そのペースで次の1000に届く時期を表示します。</Cmd>
        <Cmd name="/area">エリアごとの進み具合、次の報酬、それを手に入れるまでのプレイ数を表示します。</Cmd>
      </div>

      <h2>プレイの傾向</h2>
      <div className="cmds">
        <Cmd name="/profile">
          あなた自身の結果から見た実力。
          <Term word="カーブ" means="譜面定数ごとのスコアと、そこで期待されるスコアを示す線です。" />
          、安定して遊べる定数、Sを取った最難の譜面、最近の予測の当たり具合を表示します。
        </Cmd>
        <Cmd name="/profile" args="の Traits ボタン">
          得意なことと点を落としている所。各特性をあなた自身のカーブと比べ、プレイ回数と難易度を考慮したうえで、タグをシャッフルした場合と数百回比べて検定します。偶然では起こりにくいときだけ
          <Term word="確定" means="シャッフルしたタグが上回ったのが50回に1回未満で、譜面を半分に分けたどちらでも同じ結果になったもの。" />
          と表示されます。タグの多くは
          <Term word="maiノーツ" means="有志が譜面に配置のタグを付けているコミュニティサイト。全譜面の約1割、主に MASTER 以上をカバーしています。" />
          の編集者によるものです。タグのない譜面は、Rasmai が
          <Term word="譜面データ" means="ノーツ1つずつが書かれた譜面ファイルそのもの。" />
          から配置を測ります。
        </Cmd>
      </div>

      <h2>比較と共有</h2>
      <div className="cmds">
        <Cmd name="/compare" args="@user">共有をオンにしている別のプレイヤーとスコアを比べます。</Cmd>
        <Cmd name="/leaderboard">このサーバーのレーティングランキング。参加は任意で、サーバーの管理者はオフにできます。</Cmd>
        <Cmd name="/settings">
          初期設定、毎日1回最近のプレイを確認するか、結果を DM で受け取るか、誰がスコアを見られるかを設定します。公開プロフィールページもここでオンにできます。
        </Cmd>
        <Cmd name="/server">サーバー管理者向け。サーバーの <code>/leaderboard</code> をオン・オフします。</Cmd>
      </div>

      <h2>データ</h2>
      <div className="cmds">
        <Cmd name="/refresh">
          保存済みのコピーを使わず、今すぐ maimaiでらっくすNET からスコアを取得します。コマンドを実行するたびに新しいプレイを確認するので、使うことはほとんどありません。
        </Cmd>
        <Cmd name="/export" args="[json|csv]">保存されているスコアをすべてファイルで出力します。サイトの「アカウント」タブから再び取り込めます。</Cmd>
        <Cmd name="/delete-account">
          アカウント、スコア、履歴を含め、あなたについて保存されているものをすべて削除します。確認メールや待機期間はありません。
        </Cmd>
      </div>

      <h2>Webサイト</h2>
      <p>
        <a href="/me/">ダッシュボード</a>
        では、コマンドでできることをすべて、広い画面で使えます。Discord でログインし、受け取るのはあなたの ID と名前だけです。
      </p>
      <ul>
        <li>
          <b>概要</b>：レーティングの推移と、スコアのある全譜面を載せたカーブ。
        </li>
        <li>
          <b>遊ぶ譜面</b>と<b>新しい譜面</b>：<code>/analyze</code> と <code>/new</code> を、打ち直さずに絞り込めます。
        </li>
        <li>
          <b>特性</b>：点を落としている所、得意な所、それぞれの確からしさ、苦手を練習できるあなたのレベルの譜面。
        </li>
        <li>
          <b>ベスト50</b>・<b>全譜面</b>・<b>最近</b>：絞り込み・並べ替え・日本語／ローマ字／英語の検索つきでスコアを表示。
        </li>
        <li>
          <b>検索</b>：配置ブラウザつきの <code>/chart</code>。特定の配置を持つ譜面をすべて探して練習できます。
        </li>
        <li>
          <b>エリア</b>と<b>アカウント</b>：エリアの進み具合、設定、過去のエクスポートの取り込み、アカウントの削除。
        </li>
      </ul>
      <p>
        スマートフォンにアプリとしてインストールできます。Safari か Chrome で <a href="/me/">rasmai.lol/me</a>{" "}
        を開いてホーム画面に追加してください。アイコンのショートカットから「遊ぶ譜面」「ベスト50」「最近」「特性」に移動できます。
      </p>

      <h2>知っておくと便利なこと</h2>
      <ul>
        <li>
          Rasmai が maimaiでらっくすNET からデータを取るのは、何か変化があったときだけです。コマンドのたびにプロフィールと最近のプレイを確認し、新しいプレイがなければ保存済みのコピーを使います。
        </li>
        <li>
          あなたの
          <Term word="地域" means="遊んでいるゲームのバージョン。海外版はたいてい日本版より1バージョンほど遅れています。" />
          にまだない譜面は、おすすめから外れます。検索では見つかり、どこで遊べるかも表示されます。
        </li>
        <li>
          ある譜面のスコアが1回失敗しただけのように見える場合、Rasmai は普段のスコアを基準にもう一度おすすめし、初見と同じように扱います。
        </li>
        <li>
          そのレベルでまだ取ったことのないランクを目標にすることはありません。たとえばレート12,000のプレイヤーに、14で
          <Term word="SSS" means="達成率100.0%以上。100.5%の SSS+ の1つ下のランクです。" />
          を取れとは言いません。
        </li>
      </ul>
    </>
    ),
    privacy: () => (
    <>
      <h2>この日本語版について</h2>
      <p>
        このページは英語版プライバシーポリシーの参考訳です。日本語版と英語版の内容が異なる場合は、<b>英語版が優先されます</b>。英語版は上部の「EN」ボタンで表示できます。
      </p>

      <h2>保存するもの</h2>
      <p>
        <code>/login</code> でアカウントを連携すると、Rasmai は稼働しているサーバー上の1つのデータベースファイルに、次のものを保存します。
      </p>
      <ul>
        <li>
          <b>Discord のユーザーID</b>：コマンドを実行したときに、どの maimai アカウントがあなたのものかを判別するため。
        </li>
        <li>
          <b>maimai の地域</b>（海外版・日本版・中国版）。
        </li>
        <li>
          <b>海外版アカウント：maimaiでらっくすNET のセッションキー。</b> SEGA のページでログインした後に公式サイトが発行する <code>clal</code>{" "}
          クッキーです。これは<b>パスワードではありません</b>。海外版アカウントの場合、Rasmai が SEGA ID やパスワードを見ることはありません。キーはディスクに書き込む前に
          AES-256-GCM で暗号化されます。
        </li>
        <li>
          <b>日本版アカウント：SEGA ID、パスワード、Aime カード番号。</b> 日本版の maimaiでらっくすNET には Rasmai が借りられるセッションキーがないため、Rasmai
          の連携ページでこれらを入力していただき、スコアを読むたびにそれを使って maimaidx.jp にログインします。ディスクに書き込む前に AES-256-GCM
          で暗号化され、maimaidx.jp 以外に送られることはなく、表示・ログ記録・エクスポートへの収録も一切ありません。
        </li>
        <li>
          <b>プレイヤープロフィール</b>：maimaiでらっくすNET に表示されるプレイヤー名、レーティング、称号、段位、アイコン。スコアを読むたびに更新されます。
        </li>
        <li>
          <b>スコアのコンパクトなコピー</b>（譜面、達成率、ランク、レート、ランプ、でらっくスコア）：直近の読み取り時のもの。公式サイトを読み直さずにダッシュボード、
          <code>/compare</code>、<code>/export</code> を動かすために使い、読み取りのたびに置き換えます。
        </li>
        <li>
          <b>プレイ履歴。</b> Rasmai が最近のプレイのページで見つけたすべてのプレイ（譜面、達成率、でらっくスコア、ランプ、トラック、プレイ日時）と、読み取りで見つけた自己ベスト更新。maimaiでらっくすNET
          は直近50プレイしか表示しないため、このコピーによってスコアのグラフ、<code>/progress</code>、ダッシュボードの「最近」タブ、予測精度の確認でさらに過去までさかのぼれます。アカウントが連携されている間は増え続け、削られることはありません。
        </li>
        <li>
          <b>レーティングの推移の記録</b>（レーティング、ベスト50の合計、譜面数とプレイ回数、日時）：何かが変わった読み取りごとに1件。
          <code>/progress</code> でレーティングの推移を描くため。
        </li>
        <li>
          <b>譜面ごとのプレイ回数</b>：12時間、またはその譜面をもう一度遊ぶまでキャッシュします。毎回数百ページを読み直さずに済むようにするため。
        </li>
        <li>
          <b>判定の詳細とエリアの進み具合。</b> Rasmai が判定ページを読んだプレイについてはノーツ数と FAST/LATE の内訳、マップのエリアについてはどこまで進んだかとその記録日時。
        </li>
        <li>
          <b>ベータ版へのフィードバック。</b> ベータ機能が良くなったか・同じか・悪くなったかを Rasmai に伝えた場合、その回答と、任意で添えた短いメモ（最大500文字）を保存します。サイトの運営者が読むことができ、ほかの人に表示されることはありません。
        </li>
        <li>
          <b>設定</b>（<code>/settings</code>）：既定のレイアウト、既定の目標と難易度、そして<b>自分でオンにしない限りオフ</b>の各オプション：保存したスコアに対してほかの人が{" "}
          <code>/compare</code> を実行できるようにする、bot と共通のサーバーで <code>/leaderboard</code>{" "}
          に表示される、公開プロフィールのリンク（後述）、最近のプレイのページを毎日1回読み取る（後述）、その結果を Discord のメッセージで受け取る。比較・ランキング・プロフィールのオプションがオフなら、Rasmai
          を通じてあなたのアカウントについての情報がほかの人に見られることはありません。
        </li>
        <li>
          <b>1回限りのログインコード</b>：ハッシュとしてのみ保存します。1回だけ使え、10分で期限が切れ、1日以内に削除されます。
        </li>
      </ul>
      <p>
        スコアを読むのは、コマンドを実行したとき、ダッシュボードの「今すぐ読み取る」ボタンを押したとき、または <code>/settings history</code>{" "}
        をオンにしている場合は毎日1回バックグラウンドで、です。毎日の読み取りでは保存されたセッションキー（日本版アカウントの場合は保存された SEGA
        ID）でログインし、最近のプレイのページだけを読み込むので、コマンドの間にプレイが失われることはありません。最後に実行された日時と見つかったプレイ数は{" "}
        <code>/settings</code> で確認できます。
      </p>

      <h2>公開プロフィール</h2>
      <p>
        ダッシュボードの「アカウント」タブでオンにした場合に限り、Rasmai は <code>{SITE_URL.replace("https://", "")}/p/&hellip;</code>{" "}
        というページへのリンクを発行します。リンクを知っている人なら誰でも開けます。リンクはランダムなコードで、Discord ID ではなく、ページ上にあなたの Discord
        アカウントを特定できる情報はありません。常に表示されるのは maimai のプレイヤー名、称号、段位、ネームプレート、地域、レーティング、プレイ回数、レーティングの推移です。ベスト50、最近のプレイ、プレイの傾向、エリアの進み具合は、それぞれをオンにした場合だけ表示されます。リンクからは、同じデータで作られたプレビュー画像と
        Discord の埋め込みも生成されます。プロフィールをオフにするとリンクは使えなくなり、新しいリンクを発行すると古いリンクは即座に置き換わります。ネームプレートの画像は
        maimaiでらっくすNET からコピーされ、サーバーにキャッシュされます。
      </p>

      <h2>Webサイト</h2>
      <ul>
        <li>
          <b>ダッシュボードへのログイン。</b> Discord でログインすると、Discord ID・名前・アイコンのアドレスの署名つきコピーを持つクッキーが1つ（有効期間30日）と、ログイン処理中だけの短期間のクッキーが設定されます。要求するのは
          Discord ID と名前だけです。Rasmai がサーバーの一覧を求めたり、何かを投稿したりすることはありません。ログアウトするとクッキーは消去されます。
        </li>
        <li>
          <b>人間であることの確認。</b> ログインページとアカウント連携ページでは Cloudflare Turnstile の確認が表示され、Cloudflare
          からスクリプトを読み込みます。Cloudflare はこのサイトの前段にもあり、一般的なコンテンツ配信ネットワークと同様にこのサイトへのリクエストを処理します。どちらも{" "}
          <a href="https://www.cloudflare.com/privacypolicy/" rel="noopener noreferrer">
            Cloudflare のプライバシーポリシー
          </a>
          の対象です。
        </li>
        <li>
          <b>ログイン情報の保存（日本版アカウント・任意）。</b> SEGA ID でのログイン時に<b>次回のためにログイン情報を保存</b>にチェックを入れると、ブラウザのローカルストレージに
          SEGA ID と Aime カード番号が保存され、次回フォームに入力された状態になります。これはあなたの端末にとどまり、ログインするまでどこにも送られません。パスワードがそこに保存されることはありません。チェックを外すと削除されます。
        </li>
        <li>
          <b>ホーム画面アプリ。</b> このサイトはスマートフォンにインストールできます。サービスワーカーがキャッシュするのはサイト自身の静的ファイル（スクリプト、スタイル、フォント、アイコン）だけで、オフラインでもサイトを開けるようにするためのものです。スコア、ログイン、API
          の応答が端末にキャッシュされることはありません。
        </li>
        <li>アクセス解析、広告、その他の第三者のスクリプトはありません。</li>
      </ul>

      <h2>保存しないもの</h2>
      <ul>
        <li>支払い情報。海外版アカウントの場合は、SEGA ID、パスワード、Aime カード番号も保存しません（ログインは SEGA 自身のサイトで行われます）。</li>
        <li>IP アドレス。ログインの試行と読み取りの回数制限には、ディスクに書き込まれない短期間のメモリ上のカウンターを使います。</li>
        <li>Discord で送ったメッセージ。Rasmai は自分のスラッシュコマンドに応答するだけで、チャットは読みません。</li>
        <li>アカウントを連携していない人についての情報。</li>
      </ul>

      <h2>ほかに見る人</h2>
      <ul>
        <li>
          <b>SEGA（maimaiでらっくすNET）。</b> Rasmai はセッションキー（日本版アカウントの場合は SEGA
          ID）を使って、公式サイトからスコアのページを読み込みます。あなたが自分でログインしたときに見るのと同じページです。
        </li>
        <li>
          <b>Discord。</b> スコアから作った画像を含む Rasmai の返信は、コマンドを実行したチャンネルに投稿され、
          <a href="https://discord.com/privacy" rel="noopener noreferrer">
            Discord のプライバシーポリシー
          </a>
          の対象になります。ほかのメンバーに結果を見られたくない場合は、プライベートなチャンネルでコマンドを使ってください。
        </li>
        <li>
          <b>Cloudflare</b>：前述のとおり、Webサイトの前段のネットワークおよび人間確認の提供者として。
        </li>
        <li>
          <b>ほかには誰も見ません。</b> データの販売・共有・広告利用は行わず、アクセス解析やテレメトリーもありません。
        </li>
      </ul>

      <h2>保存期間と削除方法</h2>
      <p>
        連携したアカウント、そのスコアとプレイ履歴は、あなたが削除するまで保存されます。例外が1つあります：maimaiでらっくすNET がセッションキー（日本版アカウントの場合は
        SEGA ID とパスワード）を受け付けなくなり、30日以内に <code>/login</code> で再連携しなかった場合、下記の<b>自分ですぐに</b>
        に挙げたものがすべて自動的に削除されます。セッションが期限切れの間はダッシュボードにその日付が表示され、その2日前には、Discord がメッセージの送信を許可していれば、再連携のボタンつきで Rasmai
        からお知らせが届きます。それ以外に自然に期限切れになるのは、SEGA によって無効にされるセッションキーと、上記のキャッシュだけです。
      </p>
      <ul>
        <li>
          <b>自分ですぐに。</b> Discord で <code>/delete-account</code> を実行するか、ダッシュボードの「アカウント」タブで <b>連携解除</b>{" "}
          を押してください。どちらでも、セッションキーまたは SEGA ID のログイン情報、プロフィール、プロフィールのリンク、保存したスコア、プレイ履歴、判定の詳細、エリアの進み具合、レーティングの推移、設定、ベータ版へのフィードバック、プレイ回数のキャッシュ、ログインコードが即座に削除されます。ダッシュボードのログイン用クッキーはログアウトするか期限が切れるまで残りますが、含まれるのは
          Discord ID と名前だけです。
        </li>
        <li>
          <b>削除のしかた。</b> あなた自身、運営者、30日後の自動削除のいずれでも同じ方法で削除されます。あなたの Discord
          アカウントに紐づいて保存されたすべての行が削除され、データベースファイル内のその領域は上書きされるため、ファイルから読み戻すことはできません。データベースの変更ログもその直後に書き戻されて空になります。bot
          がメモリに保持しているコピーも同時に破棄され、過去のデータベース更新時にサーバーが保持している1つのバックアップや、運営者が有効にしたデバッグ用のコピーに含まれるあなたのデータも同様です。一度削除されると復元できません。
        </li>
        <li>
          <b>連絡による削除。</b> Discord アカウントにアクセスできなくなった場合など、上記のどちらも使えないとき、または連携していたという記録も含めてすべてを削除したいときは、
          {contact} までご連絡ください。データがどの Discord アカウントまたは maimai
          のプレイヤー名のものかをお知らせください。手作業で、通常は数日以内に削除し、完了したら返信します。保存されている内容のコピーの請求も同じ連絡先で受け付けますが、
          <code>/export</code> やダッシュボードの <b>JSON をダウンロード</b> ボタンでいつでも取得できます。
        </li>
      </ul>
      <p>Rasmai が Discord に投稿した返信は Discord に残ります。消したい場合は Discord 上で削除してください。</p>

      <h2>セキュリティ</h2>
      <ul>
        <li>
          保存されたログイン情報（セッションキー、日本版アカウントの SEGA ID とパスワード）は AES-256-GCM で暗号化されており、保存された値の改ざんも検出できます。256ビットの鍵は、データベースではなくサーバー上にのみ存在する秘密から
          scrypt で導出されます。各ログイン情報はそれぞれのアカウントに結び付けられているため、別のアカウントに移したコピーは開けません。
        </li>
        <li>
          ログイン情報が置き換えられたり削除されたりした場合、古いコピーは空き領域として扱われるだけでなく、データベースファイル内で上書きされます。以前の暗号化方式で保存されていたログイン情報も、同じ方式で暗号化し直されています。
        </li>
        <li>
          日本版アカウントの SEGA ID とパスワードは、ログインのために HTTPS で maimaidx.jp に送られる以外に使われません。あなたやほかの人に表示されることも、ログに書き込まれることも、
          <code>/export</code> に含まれることもありません。
        </li>
        <li>ログインリンクは1回限りで、あなたの Discord アカウントに結び付けられ、10分で期限が切れます。</li>
        <li>このサイトおよび maimaiでらっくすNET への接続は、すべて証明書を検証したうえで HTTPS を使います。</li>
        <li>ログインの試行には回数制限があり、人間であることの確認が必要です。</li>
      </ul>

      <h2>年齢</h2>
      <p>Rasmai は Discord を通じて使うため、Discord の最低年齢が適用されます。子どもを対象としたサービスではありません。</p>

      <h2>変更と連絡先</h2>
      <p>
        このポリシーが変更された場合は、上記の施行日も変わります。ご質問や削除の依頼は {contact} までお寄せください。このポリシーは bot と{" "}
        <code>{SITE_URL.replace("https://", "")}</code> に適用されます。
      </p>
    </>
    ),
    terms: () => (
    <>
      <h2>この日本語版について</h2>
      <p>
        このページは英語版利用規約の参考訳です。日本語版と英語版の内容が異なる場合は、<b>英語版が優先されます</b>。英語版は上部の「EN」ボタンで表示できます。
      </p>

      <h2>Rasmai とは</h2>
      <p>
        Rasmai は、あなたに代わって maimaiでらっくすNET にログインしてスコアを読み取り、レーティングが最も上がる譜面を提案する Discord bot
        です。個人による趣味のプロジェクトであり、<b>SEGA とは一切関係がなく、SEGA の承認や支援も受けていません</b>。maimai および maimai DX は SEGA
        の商標です。
      </p>

      <h2>あなたのアカウント</h2>
      <ul>
        <li>連携できるのは、あなた自身の maimai アカウントだけです。他人のアカウントを連携しようとしたり、アクセス・妨害したりすることは禁止します。</li>
        <li>
          連携することで、あなたは Rasmai に対し、あなたのセッションを使って maimaiでらっくすNET を読み取ること（日本版アカウントの場合は、提供された SEGA ID で
          maimaidx.jp にログインすること）を、あなたがブラウザで行うのと同じ方法で許可します。それが maimaiでらっくすNET に関する SEGA
          自身の規約のもとで問題ないかどうかは、あなたご自身の責任で判断してください。
        </li>
        <li>
          ログインリンクは他人に教えないでください。期限が切れる前にリンクを手に入れた人は、自分の maimai アカウントをあなたの Discord アカウントに連携できてしまいます。
        </li>
        <li>
          <code>/delete-account</code> でいつでもアカウントを削除でき、bot が保持しているあなたの情報が消去されます。具体的な内容は
          <a href="/privacy/">プライバシーページ</a>をご覧ください。
        </li>
      </ul>

      <h2>あなたが共有するもの</h2>
      <ul>
        <li>
          公開プロフィール、<code>/compare</code>、<code>/leaderboard</code>{" "}
          をオンにした場合、ほかの人に何を見せるかはあなたが選びます。プロフィールのリンクを知っている人は誰でも見られるので、見せてもよい相手にだけ共有してください。
        </li>
        <li>送ったベータ版へのフィードバックはアカウントとともに保存され、Rasmai の改善のために運営者が読みます。読まれて困ることはメモに書かないでください。</li>
      </ul>

      <h2>適正な利用</h2>
      <ul>
        <li>bot やサイトを使って、このサービス、maimaiでらっくすNET、Discord を探ったり、過負荷をかけたり、攻撃したりしないでください。</li>
        <li>コマンドにはユーザーごとの回数制限があります。その制限を回避すること、bot に対して自動化したクライアントを動かすことは認められません。</li>
        <li>Rasmai を SEGA の公式サービスであるかのように偽らないでください。</li>
      </ul>

      <h2>保証しないこと</h2>
      <ul>
        <li>
          <b>おすすめは推定です。</b> レーティングの計算はゲームの公開されている式に従いますが、譜面定数はコミュニティのデータベースから取得しているため、反映が遅れたり、あなたの地域と異なったりすることがあります。確率や目標はあなた自身の履歴にもとづく予測であり、保証されるものではありません。
        </li>
        <li>
          <b>サービスは現状のまま提供され</b>、いかなる保証もありません。maimaiでらっくすNET の変更によって動かなくなる場合を含め、いつでも利用できなくなったり、変更されたり、終了したりすることがあります。
        </li>
        <li>
          <b>責任は</b>法律で認められる最大限の範囲で<b>制限されます</b>。運営者は、bot やサイトの利用または利用できないことから生じたいかなる損失（あなたの SEGA
          アカウントに起きたことを含む）についても責任を負いません。
        </li>
      </ul>

      <h2>利用をやめるとき</h2>
      <p>
        Rasmai の利用はいつでもやめられます。<code>/delete-account</code> でデータが削除され、maimai のセッションが期限切れのまま30日間再連携されなかったアカウントは自動的に削除されます。運営者は、たとえば不正利用への対応として、予告なく連携したアカウントを削除したり、利用を制限したりすることがあります。
      </p>

      <h2>変更と連絡先</h2>
      <p>
        この規約は更新されることがあります。上記の施行日が現在の版を示します。変更後も利用を続けた場合、変更に同意したものとみなされます。ご質問は {contact} までお寄せください。
      </p>
    </>
    ),
  },
};

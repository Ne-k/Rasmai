import type { Metadata } from "next";
import { DiscordEmbed } from "@/components/DiscordEmbed";
import { Doc } from "@/components/Doc";
import { Term } from "@/components/Term";
import { buttons, embed, headline, rule, say } from "@/lib/embed";
import { env } from "@/lib/env";

export const metadata: Metadata = {
  title: "Commands",
  description: "Every Rasmai command and what it does, with the maimai terms explained.",
  alternates: { canonical: "/commands/" },
  openGraph: {
    title: "Commands · Rasmai",
    description: "Every Rasmai command and what it does, with the maimai terms explained.",
    url: "/commands/",
    images: ["/opengraph-image"],
  },
};

const SITE = env.publicUrl();

// the card this page unfurls into. Every command on it, grouped, so somebody who is sent the link
// gets the answer in the channel and only opens the page if they want the detail. Cyan rather than
// the front page's pink, so the two are told apart at a glance.
const UNFURL = embed("#21c3e3", [
  headline("Rasmai commands", `${SITE}/commands/`, ["All the commands and what they do."],
    { image: `${SITE}/app/icon-512.png` }),
  say(
    "**Play**\n`/analyze` `/plan` `/session` `/new` `/random`\n\n"
    + "**Scores**\n`/b50` `/chart` `/charts` `/recent` `/dxscore` `/progress` `/area`\n\n"
    + "**You**\n`/profile` `/compare` `/leaderboard`\n\n"
    + "**Account**\n`/login` `/settings` `/refresh` `/export` `/delete-account`",
  ),
  rule(),
  say("-# Hover any maimai word on the page for what it means."),
  buttons(
    { label: "Read the page", url: `${SITE}/commands/` },
    { label: "Add to Discord", url: `${SITE}/invite` },
  ),
]);

/** One command: what you type, and what comes back. */
function Cmd({ name, args, children }: { name: string; args?: string; children: React.ReactNode }) {
  return (
    <div className="cmd">
      <div className="cmd-name">
        <code>{name}</code>
        {args ? <span className="cmd-args">{args}</span> : null}
      </div>
      <div className="cmd-what">{children}</div>
    </div>
  );
}

export default function CommandsPage() {
  return (
    <>
      <DiscordEmbed embed={UNFURL} />
      <Doc
      tag="commands"
      dated={false}
      title={
        <>
          Commands and <em>what they do</em>.
        </>
      }
      intro="Hover or tap a word with a dotted underline to see what it means. Commands work in servers and DMs, or anywhere if you add Rasmai to your account."
    >
      <h2>Start here</h2>
      <div className="cmds">
        <Cmd name="/login">
          Links your maimai account. You get a link, sign in at maimai DX NET and press one button. It takes about a
          minute and you only do it once. You need to do this before any other command works. Only International
          accounts can be linked for now; Japan and China accounts sign in elsewhere and aren&apos;t supported yet.
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
      </Doc>
    </>
  );
}

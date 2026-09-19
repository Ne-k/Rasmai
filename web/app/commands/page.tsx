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
  headline("Rasmai commands", `${SITE}/commands/`, ["Every command, and what it does."],
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
          Every command, and <em>what it does</em>.
        </>
      }
      intro="Everything the bot answers to. Words with a dotted line under them have a meaning you can hover for, or tap on a phone. Everything here works in a server, in DMs, or anywhere at all if you add Rasmai to your account instead of a server."
    >
      <h2>Start here</h2>
      <div className="cmds">
        <Cmd name="/login">
          Links your maimai account. You get a link, you sign in at maimai DX NET, you press one button. Takes about a
          minute and you only do it once. Nothing else works until you have.
        </Cmd>
        <Cmd name="/help">Short version of this page, inside Discord.</Cmd>
        <Cmd name="/invite">Add the bot to a server or to your own account, and the link to the dashboard.</Cmd>
      </div>

      <h2>What to play</h2>
      <p>
        This is the point of the whole thing. Every pick is scored by the{" "}
        <Term
          word="rating"
          means="The number maimai shows next to your name. It is the sum of your best 50 charts, nothing else."
        />{" "}
        you would actually gain, not by how far off a perfect score you are.
      </p>
      <div className="cmds">
        <Cmd name="/analyze" args="[challenge] [level]">
          Your grind list. Each row is a chart, the score to aim for, and the{" "}
          <Term
            word="odds"
            means="How often you have scored that well on charts like this one, worked out from how much your score moves between repeat plays of the same chart. It is the chance of one run landing it, not a promise about tonight."
          />{" "}
          of getting there. <code>challenge</code> moves the targets: easier lands about half the time, balanced one in
          four, challenging one in six, long shots one in ten. <code>level</code> holds it to a level like{" "}
          <code>13+</code>, a{" "}
          <Term
            word="constant"
            means="The chart's real difficulty to one decimal place, like 13.2. maimai only shows you 13 or 13+, but the constant underneath is what your rating is actually calculated from."
          />{" "}
          like <code>13.2</code>, or a range like <code>13.0-13.4</code>.
        </Cmd>
        <Cmd name="/plan" args="[target] [difficulty] [min_level]">
          A route to a rating you name. A chain of realistic targets that add up to it, with the odds on each and the
          running total, so you can see what the number actually costs.
        </Cmd>
        <Cmd name="/session" args="[credits]">
          Say how many credits you have tonight. Each one goes where gain times odds is highest, warm ups first, with a
          repeat only if the first try missed.
        </Cmd>
        <Cmd name="/new" args="[difficulty] [level] [focus]">
          Charts you have never played that fit your level, with an estimate of what a first pass scores.{" "}
          <code>focus</code> leans the list toward a{" "}
          <Term
            word="trait"
            means="A thing charts ask of you: long streams, jacks, chained slides, touch clusters, tempo changes, and so on. Rasmai works out which ones you score above and below your own average on."
          />{" "}
          you lose points on, or one you are good at.
        </Cmd>
        <Cmd name="/random" args="[level] [difficulty] [unplayed]">
          You just want something to play. Here is something to play.
        </Cmd>
      </div>

      <h2>Your scores</h2>
      <div className="cmds">
        <Cmd name="/b50" args="or /top">
          The fifty charts your rating is made of. Fifteen from the{" "}
          <Term
            word="new pool"
            means="Charts from the version the game is currently on. Fifteen of these count toward your rating, and they are usually worth more per chart because fewer people have ground them."
          />{" "}
          and thirty five from the{" "}
          <Term
            word="old pool"
            means="Everything from older versions. Thirty five of these count. This is where most of your rating lives and where it moves slowest."
          />
          .
        </Cmd>
        <Cmd name="/chart" args="<title> [difficulty]">
          One chart in full: your score, what the model expects of you, what every rank is worth to your rating, what the
          chart asks of your hands, how to unlock it, and a video. Search in Japanese, romaji or English.
        </Cmd>
        <Cmd name="/charts" args="[pattern] [level] [difficulty]">
          Browse by pattern or level with your scores beside each chart. Useful once you know what you are bad at and
          want to drill it on purpose.
        </Cmd>
        <Cmd name="/recent" args="[play]">
          Your last sessions, every play, what was a new best and what counted.{" "}
          <code>play:1</code> opens one run in full with every{" "}
          <Term
            word="judgement"
            means="How each note landed: critical perfect, perfect, great, good or miss. Rasmai splits them by note type and tells you what each one cost you in percent."
          />{" "}
          and what it cost you.
        </Cmd>
        <Cmd name="/dxscore">
          Your{" "}
          <Term
            word="DX score"
            means="A second score maimai keeps, counting how many notes you hit with the best possible timing. It earns stars on a chart and has nothing to do with your rating."
          />{" "}
          stars, and the charts sitting closest to the next one.
        </Cmd>
        <Cmd name="/progress">
          Your rating over time, the pace that implies, and the date your next thousand arrives if you keep it up.
        </Cmd>
        <Cmd name="/area">
          Area travel: how far you are through each area, the next reward, and how many plays away it is.
        </Cmd>
      </div>

      <h2>How you play</h2>
      <div className="cmds">
        <Cmd name="/profile">
          Where your skill actually sits, read off your own results rather than a tier list. It gives you a{" "}
          <Term
            word="curve"
            means="Every chart you have scored, plotted against its constant, with a line fitted through it and a band showing how much you scatter. It is what the model expects of you at any difficulty."
          />
          , the constant you are comfortable at, the hardest chart you have taken an S on, and how well the model has
          been predicting you lately.
        </Cmd>
        <Cmd name="/profile" args="then the Traits button">
          What you are good at and what costs you points. Every trait is fitted against your own curve with play count
          and difficulty held still, then tested against shuffled tags a few hundred times. A trait is only called{" "}
          <Term
            word="confirmed"
            means="Shuffled tags beat it less than one time in fifty, and it kept its sign in both halves of your charts. Anything weaker is shown as leaning or worth watching, with the odds printed beside it."
          />{" "}
          when chance is unlikely to explain it. Most of this comes from tags written by the{" "}
          <Term
            word="maiノーツ"
            means="A community site where people tag charts by what they contain. It covers about one chart in ten, nearly all Master and above."
          />{" "}
          editors, and for the rest Rasmai reads the chart's own{" "}
          <Term
            word="notation"
            means="The chart file itself, note by note. Rasmai measures the patterns directly from it, so a trait can be found on a chart nobody has tagged."
          />{" "}
          and measures the patterns itself.
        </Cmd>
      </div>

      <h2>Reading and sharing</h2>
      <div className="cmds">
        <Cmd name="/compare" args="@user">
          Your scores against another player who turned sharing on.
        </Cmd>
        <Cmd name="/leaderboard">
          Rating leaderboard for this server. Opt in only, and a server owner can switch it off entirely.
        </Cmd>
        <Cmd name="/settings">
          Your defaults, whether the bot reads your recent plays once a day, whether it DMs you what it found, and who
          can see your scores. This is also where you turn on a public profile page you can link to.
        </Cmd>
        <Cmd name="/server">
          For people who manage a server. Turns <code>/leaderboard</code> on or off here.
        </Cmd>
      </div>

      <h2>Your data</h2>
      <div className="cmds">
        <Cmd name="/refresh">
          Read maimai DX NET right now instead of the saved copy. You rarely need this. The bot checks for new plays on
          its own whenever you run a command.
        </Cmd>
        <Cmd name="/export" args="[json|csv]">
          Every score it holds, as a file. Yours to keep, and it reads back in from the Account tab on the site.
        </Cmd>
        <Cmd name="/delete-account">
          Deletes everything stored about you. The account, the scores, the history, all of it. No confirmation email,
          no cooling off period, it just goes.
        </Cmd>
      </div>

      <h2>The website</h2>
      <p>
        <a href="/me/">The dashboard</a> has everything the commands have, with more room to look at it. Sign in is
        Discord and it only reads your ID and name.
      </p>
      <ul>
        <li>
          <b>Overview</b> gives you your rating over time and your curve, with every chart you have scored on it.
        </li>
        <li>
          <b>What to play</b> and <b>New charts</b> are <code>/analyze</code> and <code>/new</code>, with the filters
          you would otherwise have to retype.
        </li>
        <li>
          <b>Traits</b> shows the whole picture at once: what you lose points on, what you shine at, how sure it is
          about each, and charts in your own band to practise the weak ones on.
        </li>
        <li>
          <b>Best 50</b>, <b>All charts</b> and <b>Recent</b> are your scores with filters, sorting and search that
          takes Japanese, romaji or English.
        </li>
        <li>
          <b>Look up</b> is <code>/chart</code> with a pattern browser attached, so you can find every chart carrying a
          thing and go practise it.
        </li>
        <li>
          <b>Areas</b> and <b>Account</b> cover area travel, your settings, importing an old export and deleting
          everything.
        </li>
      </ul>
      <p>
        It installs on your phone as an app. Open <a href="/me/">rasmai.lol/me</a> in Safari or Chrome and add it to
        your home screen. The icon shortcuts jump straight to What to play, Best 50, Recent and Traits.
      </p>

      <h2>Things worth knowing</h2>
      <ul>
        <li>
          Rasmai only reads maimai DX NET when something changed. A command signs in, checks your profile and recent
          plays, and answers from the saved copy unless a new play shows up.
        </li>
        <li>
          Charts your{" "}
          <Term
            word="region"
            means="Which version of the game you play. International sits a version or so behind Japan, so some charts exist there and not here."
          />{" "}
          does not have yet are left out of everything that suggests something to play. Look up still finds them and
          tells you where they are playable.
        </li>
        <li>
          If your best on a chart was one bad run, the bot notices and offers it again at what you would actually score,
          priced as a first pass.
        </li>
        <li>
          Targets never ask for a rank you have not shown at that level. It will not tell a 12,000 player to go{" "}
          <Term
            word="SSS"
            means="100.0% achievement. The ranks above S are S+ at 98, SS at 99, SS+ at 99.5, SSS at 100 and SSS+ at 100.5."
          />{" "}
          a 14.
        </li>
      </ul>
      </Doc>
    </>
  );
}

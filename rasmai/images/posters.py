import math
import random
from html import escape
from typing import Any, Callable, Dict, List, Optional, Sequence

from rasmai.bot.ui.emoji import COMBO, RANKS, SYNC
from rasmai.config import site_label
from rasmai.engine.analysis.rating import rating_band, rating_step
from rasmai.images.markup import render, styleimage, template

CoverFn = Callable[[str, str], str]

DIFFICULTY_STYLES = {
    "basic": ("BASIC", "#4bb85f"),
    "advanced": ("ADVANCED", "#e0a020"),
    "expert": ("EXPERT", "#e2455a"),
    "master": ("MASTER", "#a266e8"),
    "remaster": ("Re:MASTER", "#cbbbe8"),
    "utage": ("UTAGE", "#e2609a"),
}


def tier(difficulty: str) -> tuple:
    return DIFFICULTY_STYLES.get(str(difficulty).strip().lower(), DIFFICULTY_STYLES["master"])


CSS = styleimage()


def panel(colour: str, title: str, body: str, note: str = "") -> str:
    """A section of a board: its name and a note over a hairline, then what it holds.

    :param colour: The section's colour, which the /area tiles and trait bars drawn in it take (``"pink"``, ``"gold"``, ``"cyan"``,
        ``"mint"`` or ``"purple"``), followed by any other class the section needs.
    :type colour: str
    :param title: The section's name, escaped here.
    :type title: str
    :param body: The section's markup, already escaped where it carries anyone's text.
    :type body: str
    :param note: A short line beside the name, escaped here.
    :type note: str
    :rtype: str
    """
    tag = f"<span>{_esc(note)}</span>" if note else ""
    return f'<section class="panel {colour}"><div class="tabs"><h2>{_esc(title)}</h2>{tag}</div>{body}</section>'


def mark(name: str) -> str:
    """One of Rasmai's own marks (brand/emoji), sized by the text it sits in.

    :param name: The mark's file name without its ending, such as ``"rank_sssp"``; ours, never a player's text.
    :type name: str
    :rtype: str
    """
    return f'<i class="mk mk-{name}"></i>'


def rank_mark(rank: Any) -> str:
    """A rank as its mark, the one the bot's messages use for it.

    :param rank: The rank, such as ``"SSS+"``.
    :type rank: Any
    :rtype: str
    """
    return mark(RANKS.get(str(rank or "").upper(), "rank_low")) if rank else ""


def lamp_marks(fc: Any, fs: Any) -> str:
    """A chart's lamps as their marks: the full combo or all perfect it holds, then its sync. A plain sync play has no mark, and is a word.

    :param fc: The combo lamp as maimai DX NET writes it (``"FC+"``), or nothing.
    :type fc: Any
    :param fs: The sync lamp (``"FDX"``, ``"SYNC"``), or nothing.
    :type fs: Any
    :rtype: str
    """
    marks = ""
    for lamp, table in ((str(fc or "").upper(), COMBO), (str(fs or "").upper(), SYNC)):
        if lamp in table:
            marks += mark(table[lamp])
        elif lamp not in ("", "NONE"):
            marks += f' <span class="lamp">{_esc(lamp)}</span>'
    return marks


def tier_mark(difficulty: Any) -> str:
    """A difficulty as its paper lantern; the festival lantern for one the pack has no drawing of (utage).

    :param difficulty: The difficulty tier, such as ``"master"``.
    :type difficulty: Any
    :rtype: str
    """
    key = str(difficulty or "").strip().lower()
    return mark(f"diff_{key}" if key in ("basic", "advanced", "expert", "master", "remaster") else "festival")


def kind_mark(chart_type: Any) -> str:
    """DX or STD as its card.

    :param chart_type: ``"dx"`` or ``"std"``.
    :type chart_type: Any
    :rtype: str
    """
    return mark("type_dx" if str(chart_type or "").lower() == "dx" else "type_std")


def _esc(text: Any) -> str:
    # only nothing is nothing: a count of 0 is a figure, and prints
    return escape("" if text is None else str(text))


def _avatar(avatar_b64: str) -> str:
    if avatar_b64:
        return render("avatar", data=avatar_b64)
    return template("avatar-none")


def _warm_up_line(warm: dict) -> str:
    """One clause about the first track of a credit, when the player's plays say anything about it."""
    if not warm:
        return ""
    gap = abs(float(warm.get("gap", 0)))
    if warm.get("colder"):
        return (f" &middot; your first track of a credit runs <b>{gap:.2f}%</b> under the rest, "
                f"so spend it on something you know")
    return f" &middot; your first track of a credit runs <b>{gap:.2f}%</b> over the rest"


# the background layouts in rasmai.css; "" is the default body::before
BACKDROPS = ("", "bg-chain", "bg-seal", "bg-ripple")


def _page(eyebrow: str, name: str, avatar_b64: str, headline_value: str,
          headline_caption: str, body: str, foot_more: str, foot_right: str, body_class: str = "") -> str:
    return render(
        "page",
        css=CSS,
        body_class=" ".join(c for c in (body_class, random.choice(BACKDROPS)) if c),
        avatar=_avatar(avatar_b64),
        eyebrow=_esc(eyebrow),
        name=_esc(name),
        headline_value=headline_value,
        headline_caption=_esc(headline_caption),
        body=body,
        foot_left=_esc(f"Rasmai · {site_label()} · maimai DX" + (f" · {foot_more}" if foot_more else "")),
        foot_right=_esc(foot_right),
    )


STAR_POINTS = "64,13 79.9,47.2 117.3,51.7 89.7,77.3 96.9,114.3 64,96 31.1,114.3 38.3,77.3 10.7,51.7 48.1,47.2"
_STAR = f'<svg class="rp-star" viewBox="0 0 128 128"><polygon points="{STAR_POINTS}"/></svg>'


def stats(figures: Sequence[tuple]) -> str:
    """Figures with their names, for a banner.

    :param figures: ``(name, value)`` pairs; a name is escaped here, a value is markup, already escaped where it carries anyone's text.
    :type figures: Sequence[tuple]
    :rtype: str
    """
    return '<dl class="stats">' + "".join(f'<div class="stat"><dt>{_esc(k)}</dt><dd>{v}</dd></div>' for k, v in figures) + "</dl>"


def rating_plate(rating: Any, small: bool = False) -> str:
    """The rating on its plate: the band's colour, each digit in a cell, a star per 250-point step.

    :param rating: The player's rating.
    :type rating: Any
    :param small: The small size, without the label, for a place that already says rating.
    :type small: bool
    :rtype: str
    """
    key, fill = rating_band(rating)
    try:
        text = str(max(0, min(99999, int(rating or 0))))
    except (TypeError, ValueError):
        text = "0"
    cells = '<i class="off">0</i>' * (5 - len(text)) + "".join(f"<i>{d}</i>" for d in text)
    stars = rating_step(rating)
    side = '<span class="rp-label">Rating</span>' + (f'<span class="rp-stars">{_STAR * stars}</span>' if stars else "")
    return (f'<span class="rplate{" sm" if small else ""}" style="--band:{fill}" title="{key}">'
            f'<span class="rp-side">{side}</span><span class="rp-cells">{cells}</span></span>')


def _plays(plays: int, unplayed: bool = False) -> str:
    if unplayed:
        return "never played"
    if plays <= 0:
        return "plays unknown"
    return f"{plays} play" if plays == 1 else f"{plays} plays"


def fit_across(places: int, room: int = 960) -> int:
    """The fewest jacket tiles across, six at least, whose rows of `places` fit in `room` pixels, so the page keeps to 16:9."""
    # a tile is 4/5 as tall as wide, across a 2320px page with 14px between tiles (rasmai.css .tracks)
    return next((a for a in range(6, 13) if -(-places // a) * (0.8 * (2320 - 14 * (a - 1)) / a + 14) <= room), 12)


def _roll(plates: Sequence[str], room: int = 960) -> str:
    return f'<div class="tracks" style="--across:{fit_across(len(plates), room)}">{"".join(plates)}</div>'


def _lanterns(difficulties: Sequence[Any]) -> str:
    """A tally of the lanterns a list holds, the most held first."""
    held = [str(d or "").lower() for d in difficulties]
    return '<div class="tally">' + "".join(f"<span>{tier_mark(d)}{held.count(d)}</span>" for d in sorted(set(held), key=held.count, reverse=True)) + "</div>"


def _step(option: Any, position: int, cover_html: CoverFn, flags: str, gain: int) -> str:
    """One chart to push, as a tile: a step of /plan's route, a credit of /session's running order.

    :param option: The chart and its target.
    :type option: Any
    :param position: The tile's number, which the embed's links share.
    :type position: int
    :param cover_html: Draws a jacket.
    :type cover_html: CoverFn
    :param flags: Tags beside the rank marks, such as a warm-up or a repeat.
    :type flags: str
    :param gain: What the target adds to the best-50, the stub's figure.
    :type gain: int
    :rtype: str
    """
    label, ink = tier(option.difficulty_type)
    constant = float(option.constant or 0)
    new = option.is_unplayed
    where = "never played" if new else f"from {option.current_accuracy:.2f}"
    return f"""
    <div class="track" style="--tier:{ink};">
      <div class="track-stub"><b>{position}</b>{tier_mark(option.difficulty_type)}<small>{f"{constant:.1f}" if constant > 0 else ""}</small><strong>+{gain}</strong></div>
      <div class="track-body">
        <div class="track-name"><b>{_esc(option.title)}</b>{kind_mark(option.chart_type)}</div>
        {cover_html(option.cover, "track-jacket")}
        <div class="track-score"><b>{option.target_accuracy:.2f}%</b><small>{label.title()} {_esc(option.level)}, {where}</small></div>
        <div class="track-foot"><span>{mark("new") if new else rank_mark(option.current_rank)}<i class="rs-to"></i>{rank_mark(option.target_rank)}</span>{flags}</div>
      </div>
    </div>"""



# ---------------------------------------------------------------- /plan

def plan_poster_html(plan: Any, player_name: str, player_rating: int, avatar_b64: str,
                     cover_html: CoverFn, stretch: bool = False, date_text: str = "",
                     bolder_label: str = "", limit_label: str = "", credits: int = 0) -> str:
    steps = list(plan.steps)
    needed = max(1, plan.needed)
    share = 100 * plan.total // needed
    after = player_rating + plan.total
    verdict = (f'<div class="rs-verdict reached"><b>covers +{plan.needed}</b><small>the whole way to {plan.goal_rating}</small></div>' if plan.reached else
               f'<div class="rs-verdict"><b>{plan.shortfall} short</b><small>{share}% of the way</small></div>')
    figures = [("Steps", str(len(steps))), ("Expected", f"+{plan.expected_gain:.0f}"), ("Over your usual", f"{plan.average_stretch:+.1f}%")]
    if credits:
        figures.append(("Credits", f"~{credits}"))
    bolder = (f'<p class="rs-note"><b>{_esc(bolder_label)} targets</b> cover the full +{plan.needed} on charts you already play</p>'
              if bolder_label else "")
    banner = (f'<div class="banner"><div class="sum"><span>{player_rating}<small>rating now</small></span><i>+</i>'
              f'<span>{plan.total}<small>this route</small></span><i>=</i><span><b>{after}</b>'
              f'<small>after {len(steps)} step{"" if len(steps) == 1 else "s"}</small></span></div>{verdict}{stats(figures)}{bolder}</div>')
    # the road is the route itself, from the rating now to the rating after it; what is left to the goal is the gap beyond it
    total = max(1, plan.total)
    stops = "".join(f'<i style="left:{min(100.0, 100.0 * step.cumulative / total):.1f}%"></i>' for step in steps)
    gap = ('<div class="rs-road-gap reached"><b>covers it</b></div>' if plan.reached else
           f'<div class="rs-road-gap"><b>{plan.shortfall} short</b></div>')
    road = (f'<div class="rs-road"><div class="rs-road-end"><small>now</small>{rating_plate(player_rating, small=True)}</div>'
            f'<div class="rs-road-way{" stretch" if stretch else ""}">{stops}<b>+{plan.total} = {after}</b></div>{gap}'
            f'<div class="rs-road-end"><small>goal</small><span class="rs-goal">{plan.goal_rating}</span></div></div>')
    kind = ("stretch targets" if stretch else "grind targets, 25% odds or better") + (f" · {limit_label} only" if limit_label else "")
    if steps:
        route = _roll([_step(step.option, position, cover_html, "", step.gain)
                       for position, step in enumerate(steps, 1)], room=800)
    else:
        route = '<div class="rs-empty">No achievable steps yet - play a few more charts and try again.</div>'
    body = (banner + panel("gold run", "The road", road, "one dot per step")
            + panel("cyan run", "Route", route, f"{len(steps)} step{'' if len(steps) == 1 else 's'} · {kind}"))
    return _page(f"Road to {plan.goal_rating}", player_name, avatar_b64,
                 f"+{plan.total}", f"of +{plan.needed}", body,
                 "", date_text)


# ---------------------------------------------------------------- /session

def session_poster_html(session: Any, player_name: str, avatar_b64: str,
                        cover_html: CoverFn, date_text: str = "", mix: str = "", limit_label: str = "") -> str:
    plays = list(session.plays)
    any_lands = session.any_lands * 100
    # the engine opens the night with the surest plays, at most two of those at 35% odds or better
    warm = min(2, sum(1 for play in plays if play.option.feasibility >= 0.35))
    figures = [("Credits", str(session.credits)), ("Charts", str(session.distinct_charts)),
               ("Repeats", str(sum(1 for play in plays if play.attempt > 1)))]
    figures += [(label, _esc(value)) for label, value in (("Mix", mix), ("Only", limit_label)) if value]
    banner = (f'<div class="banner"><div class="sum rs-pair-sum"><span><b>+{session.expected_total:.0f}</b><small>expected gain</small></span>'
              f'<span>{any_lands:.0f}%<small>odds one lands</small></span></div>{stats(figures)}'
              f'{_lanterns([play.option.difficulty_type for play in plays]) if plays else ""}</div>')
    if plays:
        plates = [_step(play.option, position, cover_html,
                        ('<span class="rs-tag rs-warm">warm-up</span>' if position <= warm else "")
                        + (f'<span class="rs-tag">try {play.attempt}</span>' if play.attempt > 1 else ""),
                        play.gain)
                  for position, play in enumerate(plays, 1)]
        order = _roll(plates)
    else:
        order = '<div class="rs-empty">Nothing tonight moves your best-50 at these odds. Try bolder targets.</div>'
    body = banner + panel("pink run", "Running order", order, "warm-ups first, then by difficulty")
    return _page("Tonight's session", player_name, avatar_b64, f"+{session.expected_total:.0f}",
                 "expected gain", body,
                 "odds from your own history", date_text)


# ---------------------------------------------------------------- /new

def new_poster_html(picks: Sequence[Any], player_name: str, player_rating: int, avatar_b64: str,
                    cover_html: CoverFn, labels: Sequence[str], lower: float, upper: float, date_text: str = "",
                    start: int = 1, note: str = "", known: int = 0) -> str:
    def plate(position: int, pick: Any) -> str:
        name, ink = tier(pick.difficulty)
        constant = float(pick.constant or 0)
        # a chart that would add nothing now banks for later, so its loud figure is the chance of an S instead of a +0
        loud = f"<strong>+{pick.rating_gain}</strong>" if pick.rating_gain > 0 else f'<strong class="rs-odds">{pick.odds_of_s * 100:.0f}%</strong>'
        return f"""
    <div class="track" style="--tier:{ink};">
      <div class="track-stub"><b>{position}</b>{tier_mark(pick.difficulty)}<small>{f"{constant:.1f}" if constant > 0 else ""}</small>{loud}</div>
      <div class="track-body">
        <div class="track-name"><b>{_esc(pick.title)}</b>{kind_mark(pick.chart_type)}</div>
        {cover_html(pick.cover, "track-jacket")}
        <div class="track-score"><b>~{pick.expected_accuracy:.1f}%</b><small>First try, {name.title()} {_esc(pick.level)}</small>
          <small>{pick.odds_of_s * 100:.0f}% odds of S</small><small>Genre: {_esc(pick.genre)}</small></div>
        <div class="track-foot"><span>{rank_mark(pick.expected_rank)}{mark("new")}</span></div>
      </div>
    </div>"""

    # the head's title holds the difficulty; a level or a focus asked for goes in the banner, so the title never runs under the head's figure
    first, *rest = labels
    worth = sum(1 for pick in picks if pick.rating_gain > 0)
    figures = [("To try", str(len(picks))), ("Worth rating now", str(worth)), ("Rating", str(player_rating))]
    if known:
        figures.append(("Charts known", str(known)))
    banks = ("the rest bank for later: their stub shows the odds of S" if worth else
             "all bank for later: each stub shows the odds of S") if worth < len(picks) else ""
    asked = (f'<p class="rs-note"><b>{_esc(" · ".join(rest))}</b> {_esc(note)}</p>' if rest or note else "")
    banner = (f'<div class="banner"><div class="sum"><span>{lower:.1f}<small>lowest level</small></span><i>to</i>'
              f'<span><b>{upper:.1f}</b><small>highest level</small></span></div>{stats(figures)}'
              f'{_lanterns([pick.difficulty for pick in picks]) if picks else ""}{asked}'
              f'{f"<p class='rs-note'>{banks}</p>" if banks and not asked else ""}</div>')
    if picks:
        shelf = _roll([plate(position, pick) for position, pick in enumerate(picks, start)])
    else:
        shelf = '<div class="rs-empty">No chart you have never played is in range at this difficulty.</div>'
    body = banner + panel("cyan run", "Never played", shelf, "first-try estimates" + (f" · {banks}" if banks and asked else ""))
    return _page(f"New charts · {first}", player_name, avatar_b64,
                 str(len(picks)), "charts to try", body,
                 f"{known} charts known" if known else "", date_text)


# ---------------------------------------------------------------- /profile

def _skill_chart_svg(profile: Any, songs: Sequence[Any], width: int = 1000, height: int = 600,
                     moved: Sequence[Any] = ()) -> str:
    """The scatter of every score against chart constant, with the fitted curve over it.

    Drawn rather than templated: every coordinate here is computed.

    :param profile: How the player plays, as measured from their scores.
    :type profile: Any
    :param songs: The player's scored charts.
    :type songs: Sequence[Any]
    :param width: How wide to draw, in pixels.
    :type width: int
    :param height: How tall to draw, in pixels.
    :type height: int
    :param moved: The scored charts whose best a recent play set, ringed so they stand out.
    :type moved: Sequence[Any]
    :rtype: str
    """
    pts = [
        (float(s.difficulty), float(s.accuracy), str(getattr(s, "difficulty_type", "")).lower(), s in moved)
        for s in songs
        if float(getattr(s, "difficulty", 0) or 0) > 0 and float(getattr(s, "accuracy", 0) or 0) > 0
        and str(getattr(s, "difficulty_type", "")).lower() != "utage"
    ]
    if not pts:
        return ""
    ml, mr, mt, mb = 138, 26, 44, 66
    x0, x1 = math.floor(min(p[0] for p in pts)), math.ceil(max(p[0] for p in pts)) + 0.5
    y0, y1 = 85.0, 101.0
    pw, ph = width - ml - mr, height - mt - mb

    def X(c: float) -> float:
        return ml + (c - x0) / (x1 - x0) * pw

    def Y(a: float) -> float:
        # S and up gets three fifths of the height: that is where the scores crowd, and its rank lines would run together on one scale
        a = min(max(a, y0), y1)
        return mt + ph * ((y1 - a) / (y1 - 97.0) * 0.6 if a >= 97.0 else 0.6 + (97.0 - a) / (97.0 - y0) * 0.4)

    parts: List[str] = []
    for a, name in ((90.0, ""), (97.0, "S"), (98.0, "S+"), (99.0, "SS"), (99.5, "SS+"), (100.0, "SSS"), (100.5, "SSS+")):
        y = Y(a)
        parts.append(f'<line x1="{ml}" y1="{y:.1f}" x2="{width - mr}" y2="{y:.1f}" class="rs-ch-grid{"" if name else " minor"}"/>')
        parts.append(f'<text x="{ml - 12}" y="{y + 7:.1f}" text-anchor="end" class="rs-ch-axis">{a:g}'
                     + (f' <tspan class="rs-ch-rank">{name}</tspan>' if name else "") + "</text>")
    c = math.ceil(x0)
    while c <= x1:
        x = X(c)
        parts.append(f'<line x1="{x:.1f}" y1="{mt}" x2="{x:.1f}" y2="{height - mb}" class="rs-ch-grid minor"/>')
        parts.append(f'<text x="{x:.1f}" y="{height - mb + 30}" text-anchor="middle" class="rs-ch-axis">{c}</text>')
        c += 1
    parts.append(f'<text x="{width - mr}" y="{height - 4}" text-anchor="end" class="rs-ch-title">chart constant</text>')

    sigma = max(0.3, float(getattr(profile, "consistency", 0.8)))
    band_top, band_bot, line = [], [], []
    steps = 60
    for i in range(steps + 1):
        cx = x0 + (x1 - x0) * i / steps
        e = profile.expected_accuracy(cx)
        line.append(f"{X(cx):.1f},{Y(e):.1f}")
        band_top.append(f"{X(cx):.1f},{Y(min(101.0, e + sigma)):.1f}")
        band_bot.append(f"{X(cx):.1f},{Y(e - sigma):.1f}")
    parts.append(f'<polygon points="{" ".join(band_top + band_bot[::-1])}" class="rs-ch-band"/>')

    # the ringed ones last, so a recent best is never buried under the old scores around it
    for cst, acc, dtype, recent in sorted(pts, key=lambda p: p[3]):
        _l, ink = tier(dtype)
        if recent:
            parts.append(f'<circle cx="{X(cst):.1f}" cy="{Y(acc):.1f}" r="9" fill="{ink}" class="rs-ch-recent"/>')
        else:
            parts.append(f'<circle cx="{X(cst):.1f}" cy="{Y(acc):.1f}" r="6" fill="{ink}" class="rs-ch-pt" opacity="{0.9 if acc >= y0 else 0.4}"/>')
    parts.append(f'<polyline points="{" ".join(line)}" class="rs-ch-under"/><polyline points="{" ".join(line)}" class="rs-ch-line"/>')

    marks = [(float(getattr(profile, "comfort_constant", 0)), "comfort"), (float(getattr(profile, "reach_constant", 0)), "reach")]
    for value, name in (m for m in marks if x0 <= m[0] <= x1):
        x = X(value)
        # each label above the plot at the top of its line, comfort leaning left and reach right, so the two a few tenths apart never meet
        right = name == "reach" and x + 135 < width
        parts.append(f'<line x1="{x:.1f}" y1="{mt - 8}" x2="{x:.1f}" y2="{height - mb}" class="rs-ch-mark"/>')
        parts.append(f'<text x="{x + 6 if right else x - 6:.1f}" y="{mt - 14}" text-anchor="{"start" if right else "end"}" class="rs-ch-label">{name} {value:.1f}</text>')

    return f'<svg viewBox="0 0 {width} {height}" width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg">{"".join(parts)}</svg>'


def profile_poster_html(summary: Dict[str, Any], profile: Any, songs: Sequence[Any], player_name: str,
                        player_rating: int, avatar_b64: str, recent_count: int, date_text: str = "",
                        moved: Sequence[Any] = (), judged: Optional[Dict[str, Any]] = None) -> str:
    p = summary.get("profile", {})
    b = summary.get("best50", {})

    def swing(label: str, count: str, value: float, width: float, figure: str) -> str:
        """A bar out from the middle, its length against the longest of its set."""
        side = "neg" if value < 0 else ""
        return (f'<div class="rs-swing"><span>{label}{f"<small>{count}</small>" if count else ""}</span>'
                f'<span class="rs-swing-bar"><i class="{side}" style="width:{min(100.0, width):.0f}%"></i></span><b class="{side}">{figure}</b></div>')

    def bars(bias: Dict[str, float], limit: int = 7) -> str:
        items = sorted(bias.items(), key=lambda kv: kv[1], reverse=True)[:limit]
        if not items:
            return '<div class="rs-swing rs-none"><span>not enough recent plays</span></div>'
        most = max(abs(value - 1.0) for _key, value in items) or 1.0
        return "".join(swing(_esc(key), "", value - 1.0, abs(value - 1.0) / most * 100, f"{(value - 1.0) * 100:+.0f}%") for key, value in items)

    def trait_bars(traits: Sequence[Dict[str, Any]]) -> str:
        if not traits:
            return '<div class="rs-swing rs-none"><span>no trait stands out yet</span></div>'
        # the four each way the reply's text names when there is no image, so neither says more than the other
        ordered = ([t for t in traits if float(t["offset"]) < 0][:4]
                   + [t for t in reversed(traits) if float(t["offset"]) > 0][:4])
        ordered.sort(key=lambda t: float(t["offset"]), reverse=True)
        most = max((abs(float(t["offset"])) for t in ordered), default=0.0) or 1.0
        return "".join(swing(_esc(t["label"]), f"{t['count']} {'plays' if t.get('dimension') == 'judgement' else 'charts'}",
                             float(t["offset"]), abs(float(t["offset"])) / most * 100, f"{float(t['offset']):+.1f}") for t in ordered)

    def deep(name: str, figure: str, line: str) -> str:
        return f'<div><dt>{name}</dt><dd>{figure}</dd><dd class="rs-sub">{line}</dd></div>'

    deeper = ""
    habits = p.get("habits") or {}
    age = habits.get("age") or {}
    if age.get("plays", 0) >= 10:
        rerates, notes = habits.get("rerates") or {}, habits.get("notes") or {}
        deeper += deep("How you pick", f"{float(age.get('medianYears', 0)):.1f} yr<small>median age of the charts you play</small>",
                       f"{float(age.get('freshShare', 0)) * 100:.0f}% were less than a year old"
                       + (f" &middot; re-rating has moved your best 50 by <b>{int(rerates['rating']):+d}</b> across {int(rerates['charts'])} charts"
                          if rerates.get("charts") else "")
                       + (f" &middot; {int(notes['notes']):,} notes hit" if notes.get("notes") else "")
                       + _warm_up_line(habits.get("warmUp") or {}))
    if judged:
        top = max(judged["types"], key=lambda t: t["lossShare"])
        late = judged.get("lateShare")
        kind = _esc(str(top["kind"]).title() + ("es" if top["kind"] == "touch" else "s"))
        deeper += deep(f"Judgements &middot; {judged['plays']} plays' judgement pages",
                       f"{kind}<small>carry {top['lossShare'] * 100:.0f}% of what you lose on {top['share'] * 100:.0f}% of the notes</small>",
                       f'hits land {"late" if late >= 0.6 else "early"} {max(late, 1 - late) * 100:.0f}% of the time'
                       if late is not None and (late >= 0.6 or late <= 0.4) else "")
    calibration = p.get("calibration") or {}
    if calibration.get("plays", 0) >= 15:
        deeper += deep(f"Model check &middot; {calibration.get('plays', 0)} recorded plays",
                       f"{float(calibration.get('coverage', 0)) * 100:.0f}%<small>of plays inside the predicted range</small>",
                       f"new-best odds said {float(calibration.get('newBestPredicted') or 0) * 100:.0f}%, "
                       f"{float(calibration.get('newBestActual') or 0) * 100:.0f}% happened &middot; spread scaled "
                       f"&times;{float(calibration.get('sigmaScale', 1.0)):.2f} &middot; centre shifted {float(calibration.get('shift', 0.0)):+.2f}, "
                       f"already in the odds you see")

    consistency = p.get("consistency", 0)
    chart_type = str(p.get("favoriteChartType", "?"))
    leans = (kind_mark(chart_type) if chart_type.lower() in ("dx", "std") else "") + _esc(chart_type.upper())
    open_slots = int(b.get("newSlotsOpen", 0)) + int(b.get("oldSlotsOpen", 0))
    best = [("Cutoffs", f"{b.get('newCutoff', 0)}<small>new</small> / {b.get('oldCutoff', 0)}<small>old</small>")]
    if open_slots:
        best.append(("Open slots", f'<span class="hot">{open_slots}</span>'))
    days = int(p.get("activeDays", 0) or 0)
    banner = (f'<div class="banner"><div class="rs-style"><b>{_esc(str(p.get("style", "unknown")).title())}</b>'
              f'<small>mostly {leans}, {_esc(p.get("favoriteGenre", "?"))} genre</small></div>'
              + stats([("FC rate", f'{mark("lamp_fc")}{p.get("fcRate", 0) * 100:.0f}%'), ("AP rate", f'{mark("lamp_ap")}{p.get("apRate", 0) * 100:.0f}%'),
                        ("DX score", f'{mark("dxstar")}{p.get("dxScoreRate", 0) * 100:.0f}%')])
              + stats([("Recent", f"{recent_count}<small>plays</small>"), ("Active", f"{days}<small>day{'' if days == 1 else 's'}</small>")]
                      + ([("Play counts known", str(p.get("playCountsKnown")))] if p.get("playCountsKnown") else []))
              + f'<div class="sum"><span>{b.get("newTotal", 0)}<small>new</small></span><i>+</i><span>{b.get("oldTotal", 0)}<small>old</small></span>'
                f'<i>=</i><span><b>{b.get("total", 0)}</b><small>best 50</small></span></div>' + stats(best) + "</div>")

    held = {str(getattr(s, "difficulty_type", "")).lower() for s in songs}
    legend = "".join(f"<span>{tier_mark(key)}{DIFFICULTY_STYLES[key][0].title()}</span>"
                     for key in ("basic", "advanced", "expert", "master", "remaster") if key in held)
    if moved:
        legend += '<span><i class="rs-swatch-ring"></i>best set in recent plays</span>'
    curve = panel("pink run", "Skill curve", f'<div class="rs-curve">{_skill_chart_svg(profile, songs, moved=moved)}'
                  f'<div class="rs-legend"><span><i class="rs-swatch-line"></i>what you usually score, &plusmn;{consistency}</span>'
                  f'<span><i class="rs-swatch-mark"></i>comfort (SS) / reach (S)</span>{legend}</div></div>', "every chart you have a score on")
    figures = [("SS up to", f'{rank_mark("SS")}{p.get("comfortConstant", 0)}'), ("S up to", f'{rank_mark("S")}{p.get("reachConstant", 0)}'),
               ("Hardest S", str(p.get("hardestS", 0))), ("Usual on 13s", f"{p.get('expectedAt13', 0)}<small>% &plusmn;{consistency}</small>"),
               ("Usual on 14s", f"{p.get('expectedAt14', 0)}<small>% &plusmn;{consistency}</small>"), ("Played up to", str(p.get("playedCeiling", 0)))]
    reach = panel("cyan run", "Range", '<dl class="rs-figs">' + "".join(f"<div><dt>{_esc(k)}</dt><dd>{v}</dd></div>" for k, v in figures) + "</dl>",
                  "the constants you hold, and what you usually score")
    swings = (panel("purple run", "Points won and lost", f'<div class="rs-swings">{trait_bars(p.get("traits") or [])}</div>',
                    "vs your curve")
              + panel("gold run", "Genres", f'<div class="rs-swings">{bars(getattr(profile, "genre_bias", {}) or {})}</div>',
                      "vs your average"))
    # what the database adds when it has it sits in a strip of its own, so the columns above hold the same blocks for every player
    body = (banner + f'<div class="rs-card">{curve}<div class="rs-side">{reach}{swings}</div></div>'
            + (panel("gold run", "Habits and checks", f'<dl class="rs-deep">{deeper}</dl>') if deeper else ""))
    return _page("Play profile", player_name, avatar_b64, rating_plate(player_rating),
                 "rating", body,
                 f"{len(songs)} charts · {recent_count} recent plays", date_text)

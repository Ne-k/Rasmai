from datetime import datetime
from typing import Any, Dict, Optional, Sequence, Tuple

from rasmai.images.posters import (CoverFn, _avatar, _esc, kind_mark, lamp_marks, mark, panel, rank_mark, rating_plate,
                                   stats, tier, tier_mark)
from rasmai.images.pages import _image, star_marks


def _card(eyebrow: str, name: str, avatar_b64: str, headline_value: str, headline_caption: str, body: str, date_text: str,
          body_class: str = "narrow") -> str:
    return _image(eyebrow, name, avatar_b64, headline_value, headline_caption, body, date_text, body_class)


def _banner(*parts: str) -> str:
    """The strip under the head that holds what the card adds up to; each part is markup, already escaped."""
    return '<div class="banner cd-banner">' + "".join(part for part in parts if part) + "</div>"


def _day(when: Any) -> str:
    """A date as the cards print it, ``14 Sep 2026``, keeping the time when the text gives one; text that is not a date prints as it is."""
    if isinstance(when, datetime):
        return f"{when.day} {when:%b %Y}"
    for shape, timed in (("%Y/%m/%d %H:%M", True), ("%Y/%m/%d", False)):
        try:
            parsed = datetime.strptime(str(when).strip(), shape)
        except ValueError:
            continue
        return f"{parsed.day} {parsed:%b %Y}" + (f" {parsed:%H:%M}" if timed else "")
    return str(when or "")


def _sentences(parts: Sequence[str]) -> str:
    """The builders' note and forecast as the card prints them: each clause is its own sentence."""
    return " ".join(part[:1].upper() + part[1:] + ("" if part.endswith((".", "!", "?")) else ".") for part in parts if part)


def _jacket(cover_html: CoverFn, cover: str, ink: str, title: str, under: str = "", foot: str = "") -> str:
    """The chart's own ticket stood on end: the jacket large in a frame of the difficulty's colour with the title under it, and a
    paper foot that tears off along the pink dashes.

    :param cover_html: Renders a jacket as markup.
    :type cover_html: CoverFn
    :param cover: The jacket file name.
    :type cover: str
    :param ink: The frame's colour.
    :type ink: str
    :param title: The song title, escaped here.
    :type title: str
    :param under: Markup for the line under the title, already escaped.
    :type under: str
    :param foot: Markup for the paper foot, already escaped.
    :type foot: str
    :rtype: str
    """
    return (f'<div class="cd-jk" style="--tier:{ink};"><div class="cd-jk-frame">{cover_html(cover, "cd-jk-art")}'
            f'<b class="cd-jk-title">{_esc(title)}</b>{under}</div>' + (f'<div class="cd-jk-foot">{foot}</div>' if foot else "") + "</div>")


# ---------------------------------------------------------------- /chart and /random

def song_card_html(title: str, artist: str, genre: str, version_label: str, cover: str, cover_html: CoverFn,
                   rows: Sequence[Dict[str, Any]], player_name: str, avatar_b64: str,
                   cutoffs: str, date_text: str = "", highlight: Optional[str] = None,
                   ladder: Sequence[Dict[str, Any]] = (), ladder_label: str = "", forecast: Sequence[str] = (),
                   eyebrow: str = "Chart lookup", facts: Sequence[str] = ()) -> str:
    tickets = ""
    frame = tier(rows[-1]["difficulty"])[1] if rows else "var(--card)"
    for r in rows:
        label, ink = tier(r["difficulty"])
        pick = bool(highlight) and f'{r["chart_type"]} {r["difficulty"]}' == highlight
        if pick:
            frame = ink
        meta = []
        if r.get("notes"):
            meta.append(f'<b>{r["notes"]:,}</b> notes')
        if r.get("designer"):
            meta.append(_esc(r["designer"]))
        if r.get("played"):
            score = f'<b>{r["accuracy"]:.4f}%</b>'
            marks = rank_mark(r["rank"]) + lamp_marks(r.get("fc"), r.get("fs"))
            worth = str(r["rating"])
            if r.get("max_dx"):
                meta.append(f'DX <b>{r["dx"]:,}</b> / {r["max_dx"]:,} <span class="stars">{star_marks(r["stars"])}</span>')
            elif r.get("dx"):
                meta.append(f'DX <b>{r["dx"]:,}</b>')
            if r.get("plays"):
                meta.append(f'{mark("plays")}<b>{r["plays"]}</b> play{"s" if r["plays"] != 1 else ""}')
        else:
            score, marks, worth = '<span class="cd-never">never played</span>', "", "—"
        flag = '<em class="cd-pick">This chart</em>' if pick else ""
        note = f'<p class="cd-diff-note">{_esc(_sentences([r["note"]]))}</p>' if r.get("note") else ""
        tickets += f"""
        <div class="track cd-diff{" pick" if pick else ""}" style="--tier:{ink};">
          <div class="track-stub"><b>{_esc(r["level"])}</b>{tier_mark(r["difficulty"])}<small>{r["constant"]:.1f}</small><strong>{worth}</strong></div>
          <div class="cd-diff-body">
            <div class="track-name"><b>{label}</b>{kind_mark(r["chart_type"])}{flag}</div>
            <div class="cd-diff-score">{score}<span class="cd-marks">{marks}</span></div>
            <div class="cd-diff-meta">{"".join(f"<span>{m}</span>" for m in meta)}</div>{note}
          </div>
        </div>"""
    # what the reply's text used to say about the chart it opened on, a line each; where a line lists things, commas for the embed's dots
    lines = [line.replace(" · ", ", ") for r in rows for line in r.get("about", ()) if line]
    about = "".join(f"<p>{_esc(line[:1].upper() + line[1:])}</p>" for line in lines)
    played = [r for r in rows if r.get("played")]
    best = max((r["rating"] for r in played), default=0)
    banner = _banner(stats([("Charts", str(len(rows))), ("Played", str(len(played))), ("Cutoffs", _esc(cutoffs))]))
    # the song's own facts sit on the ticket under its jacket, so the ticket is full whatever the column beside it holds
    tags = "".join(f'<span class="cd-tag">{_esc(f)}</span>' for f in [genre or "genre unknown", version_label, *facts] if f)
    left = _jacket(cover_html, cover, frame, title, f'<span class="cd-jk-under">{_esc(artist)}</span>',
                   f'<div class="cd-tags">{tags}</div>' + (f'<div class="cd-about">{about}</div>' if about else ""))
    # past five charts (a song with standard and DX charts) the tickets run in two columns so the card stays landscape
    tall = len(rows) if len(rows) <= 5 else -(-len(rows) // 2)
    middle = panel("pink run cd-grow", "Difficulties",
                   f'<div class="cd-diffs{" two" if len(rows) > 5 else ""}" style="--rows:{max(1, tall)};">{tickets}</div>',
                   "stub: rating")
    climb = ""
    if ladder:
        steps = ""
        # the top rank at the head of the ladder, the next one up at its foot
        for step in reversed(ladder):
            gain = f'+{step["gain"]}' if step["gain"] > 0 else "&mdash;"
            steps += (f'<div class="track cd-step"><div class="track-stub">{rank_mark(step["rank"])}<strong>{gain}</strong></div>'
                      f'<dl class="cd-step-figs"><div><dt>Needs</dt><dd>{step["need"]:.2f}%</dd></div>'
                      f'<div><dt>Rating</dt><dd>{step["rating"]}</dd></div>'
                      f'<div><dt>Your chance</dt><dd>{step["odds"] * 100:.0f}% odds</dd></div>'
                      f'<span class="cd-odds"><i style="width:{min(100.0, step["odds"] * 100):.1f}%"></i></span></dl></div>')
        climb = panel("gold run cd-ladder", "Rank ladder",
                      f'<div class="cd-steps">{steps}</div>'
                      + (f'<p class="cd-forecast">{_esc(_sentences(forecast))}</p>' if forecast else ""),
                      f"{ladder_label} · stub: gain")
    # with the ladder beside the difficulties the card needs the full width; without it, it is a card about one thing
    body = banner + f'<div class="cd-sc{" wide" if ladder else ""}">{left}<div class="cd-col">{middle}</div>{climb}</div>'
    return _card(eyebrow, player_name, avatar_b64, str(best) if best else "—", "best rating", body, date_text,
                 "" if ladder else "narrow")


# ---------------------------------------------------------------- /chart history

RANK_LINES = ((80.0, "A"), (90.0, "AA"), (94.0, "AAA"), (97.0, "S"), (98.0, "S+"), (99.0, "SS"), (99.5, "SS+"), (100.0, "SSS"), (100.5, "SSS+"))


def history_card_html(title: str, difficulty: str, level: str, chart_type: str, cover: str, cover_html: CoverFn,
                      points: Sequence[Dict[str, Any]], player_name: str, avatar_b64: str,
                      date_text: str = "", constant: float = 0.0) -> str:
    """Achievement over time for one chart: every recorded play as a mark, a star where it set a new best, the best so far
    as a thick line, and the figures the reply's text used to carry in the banner over it.

    :param title: The song title.
    :type title: str
    :param difficulty: The difficulty tier, such as ``"master"``.
    :type difficulty: str
    :param level: A displayed level such as ``"13"`` or ``"13+"``.
    :type level: str
    :param chart_type: ``"std"`` or ``"dx"``.
    :type chart_type: str
    :param cover: The jacket file name.
    :type cover: str
    :param cover_html: Renders a jacket as markup.
    :type cover_html: CoverFn
    :param points: ``(constant, achievement)`` pairs to fit.
    :type points: Sequence[Dict[str, Any]]
    :param player_name: The player's name on maimai DX NET.
    :type player_name: str
    :param avatar_b64: The player's avatar, base64 encoded.
    :type avatar_b64: str
    :param date_text: The date to print on the image.
    :type date_text: str
    :param constant: The chart's internal difficulty constant, as it stands today.
    :type constant: float
    :rtype: str
    """
    from rasmai.engine.analysis import rank_for
    label, ink = tier(difficulty)
    width, height = 1080, 600
    left, right, top, bottom = 170, 40, 54, 62
    plot_w, plot_h = width - left - right, height - top - bottom

    times = [p["when"] for p in points]
    values = [float(p["achievement"]) for p in points]
    low = min(values) if values else 96.0
    high = max(values) if values else 100.0
    # the range follows the scores, and reaches up to the next two rank lines as goals
    goals = [value for value, _name in RANK_LINES if value > high][:2]
    y_min = max(0.0, low - max(0.6, (high - low) * 0.08))
    y_max = min(101.0, max(high + 0.25, (goals[-1] + 0.15) if goals else high + 0.4))
    t0, t1 = (min(times), max(times)) if times else (None, None)
    span = (t1 - t0).total_seconds() if times and t1 != t0 else 0.0

    def x_at(when: datetime, index: int) -> float:
        if span <= 0 or len(points) < 2:
            return left + plot_w * (0.5 if len(points) < 2 else index / (len(points) - 1))
        return left + plot_w * ((when - t0).total_seconds() / span)

    def y_at(value: float) -> float:
        return top + plot_h * (1 - (min(y_max, max(y_min, value)) - y_min) / (y_max - y_min))

    def pin(x: float, y: float, html: str, cls: str) -> str:
        # the marks are pictures in the stylesheet, so they sit over the graph, placed in shares of its box
        return f'<span class="{cls}" style="left:{100 * x / width:.2f}%;top:{100 * y / height:.2f}%;">{html}</span>'

    svg, pins = [], []
    last_label_y = 1e9
    for value, name in RANK_LINES:
        if y_min < value < y_max:
            y = y_at(value)
            svg.append(f'<line class="cd-g-rank" x1="{left}" x2="{width - right}" y1="{y:.1f}" y2="{y:.1f}"/>')
            if last_label_y - y >= 44:      # labels for lines that sit on top of each other would just overprint
                svg.append(f'<text class="cd-g-axis" x="{left - 14}" y="{y + 7:.1f}" text-anchor="end">{value:g}</text>')
                pins.append(pin(70, y, rank_mark(name), "cd-g-rankmk"))
                last_label_y = y
    svg.append(f'<line class="cd-g-frame" x1="{left}" x2="{width - right}" y1="{top + plot_h}" y2="{top + plot_h}"/>')

    if points:
        best = 0.0
        step = []
        fresh = set()
        for index, point in enumerate(points):
            value = float(point["achievement"])
            x = x_at(point["when"], index)
            if value > best:
                if step:
                    step.append(f"L{x:.1f} {y_at(best):.1f}")
                best = value
                fresh.add(index)
                step.append(f"{'M' if len(step) == 0 else 'L'}{x:.1f} {y_at(best):.1f}")
        step.append(f"L{x_at(points[-1]['when'], len(points) - 1):.1f} {y_at(best):.1f}")
        path = " ".join(step)
        svg.append(f'<path class="cd-g-best edge" d="{path}"/><path class="cd-g-best" d="{path}"/>')
        for index, point in enumerate(points):
            x, y = x_at(point["when"], index), y_at(float(point["achievement"]))
            cls = "cd-g-dot top" if index in fresh else "cd-g-dot"
            # a score read off the scores page is a diamond, a play seen on the recent list a circle
            if point.get("source") == "best":
                svg.append(f'<rect class="{cls}" x="{x - 11:.1f}" y="{y - 11:.1f}" width="22" height="22" rx="3" transform="rotate(45 {x:.1f} {y:.1f})"/>')
            else:
                svg.append(f'<circle class="{cls}" cx="{x:.1f}" cy="{y:.1f}" r="{14 if index in fresh else 11}"/>')
            if index in fresh:
                pins.append(pin(x, y - 38, mark("pb"), "cd-g-pb"))
        # date labels at the ends and a few in between, never overlapping
        labels = [0] if len(points) == 1 else sorted({0, len(points) - 1, len(points) // 2, len(points) // 4, 3 * len(points) // 4})
        last_x = -1e9
        for index in labels:
            x = x_at(points[index]["when"], index)
            if x - last_x < 190:
                continue
            last_x = x
            anchor = "middle" if len(points) == 1 else "start" if index == 0 else "end" if index == len(points) - 1 else "middle"
            svg.append(f'<text class="cd-g-axis" x="{x:.1f}" y="{top + plot_h + 42}" text-anchor="{anchor}">'
                       f'{_day(points[index]["when"])}</text>')
        peak = max(points, key=lambda p: float(p["achievement"]))
        px, py = x_at(peak["when"], points.index(peak)), y_at(float(peak["achievement"]))
        px = min(max(px, left + 110), width - right - 110)     # the label stays inside the frame at either end
        label_y = py + 56 if py - 66 < 30 else py - 66
        svg.append(f'<text class="cd-g-peak" x="{px:.1f}" y="{label_y:.1f}" text-anchor="middle">{float(peak["achievement"]):.4f}%</text>')
    else:
        svg.append(f'<text class="cd-g-empty" x="{left + plot_w / 2:.0f}" y="{top + plot_h / 2 - 12:.0f}" text-anchor="middle">no scores recorded yet</text>'
                   f'<text class="cd-g-empty small" x="{left + plot_w / 2:.0f}" y="{top + plot_h / 2 + 26:.0f}" text-anchor="middle">'
                   'they build up from each analysis and your recent plays</text>')

    plays = [p for p in points if p.get("source") != "best"]
    figures = [("Scores", str(len(points))), ("Plays seen", str(len(plays))),
               ("Since", _day(points[0]["when"]) if points else "—")]
    if points:
        figures += [("Best rank", rank_mark(rank_for(high))),
                    ("Latest", f"{values[-1]:.4f}%<small>{_day(points[-1]['when'])}</small>"),
                    ("First", f"{values[0]:.4f}%<small>{high - values[0]:+.4f} since</small>")]
    if plays:
        recent = [float(p["achievement"]) for p in plays[-5:]]
        figures.append((f"Last {len(recent)} seen", f"{sum(recent) / len(recent):.4f}%<small>average</small>"))
    was = float(points[0].get("constant") or constant) if points else constant
    if constant:
        figures.append(("Constant", f"{constant:.1f}" + (f"<small>{was:.1f} when first recorded</small>" if abs(was - constant) >= 0.05 else "")))
    key = ('<div class="cd-key"><span><i class="cd-sw line"></i>best so far</span><span>' + mark("pb") + 'a new best</span>'
           '<span><i class="cd-sw play"></i>a recent play</span>'
           '<span><i class="cd-sw mark"></i>your current best</span></div>')
    chart = _jacket(cover_html, cover, ink, title,
                    f'<span class="cd-jk-under">{tier_mark(difficulty)}{label} {_esc(level)}{kind_mark(chart_type)}</span>', key)
    graph = (f'<div class="cd-graph"><svg viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg">{"".join(svg)}</svg>'
             f'{"".join(pins)}</div>')
    body = (_banner(stats(figures))
            + f'<div class="cd-hc">{panel("pink run cd-graph-panel", "Every score", graph, f"{len(points)} scores · {len(plays)} plays seen")}{chart}</div>')
    headline = f"{max(values):.4f}%" if values else "—"
    return _card("Score history", player_name, avatar_b64, headline, "best recorded", body, date_text)


# ---------------------------------------------------------------- /lastplay

JUDGEMENTS = ("critical", "perfect", "great", "good", "miss")


def play_card_html(play: Dict[str, Any], detail: Dict[str, Any], cover_html: CoverFn, player_name: str,
                   rating: int, avatar_b64: str, date_text: str = "") -> str:
    label, ink = tier(play["difficulty"])
    achievement = float(detail.get("achievement") or play.get("achievement") or 0.0)
    dx = int(detail.get("dx_score") or play.get("dx") or 0)
    max_dx = int(detail.get("max_dx_score") or play.get("max_dx") or 0)
    from rasmai.images.pages import stars_for
    from rasmai.engine.losses import note_losses
    stars = stars_for(dx / max_dx) if max_dx else 0
    notes = detail.get("notes") or {}
    totals = dict.fromkeys(JUDGEMENTS, 0)
    lost = note_losses(notes, achievement)
    all_lost = sum(lost.values())

    def tally(name: str, counts: Dict[str, int], cost: float, cls: str = "") -> str:
        """One note type's row: each judgement's count, then what the row cost over a bar of its share of everything lost."""
        cells = "".join(f'<span class="cd-j-{k}{"" if counts[k] else " zero"}">{counts[k]:,}</span>' for k in JUDGEMENTS)
        if cost < 0.005:
            loss = '<span class="cd-j-lost zero">&mdash;</span>'
        else:
            loss = f'<span class="cd-j-lost"><b>-{cost:.2f}%</b><i style="width:{100 * cost / all_lost:.1f}%"></i></span>'
        return f'<div class="cd-j-row {cls}"><b class="cd-j-kind">{name}</b>{cells}{loss}</div>'

    judge_rows = ""
    for kind in ("tap", "hold", "slide", "touch", "break"):
        n = notes.get(kind)
        if not n:
            continue
        counts = {k: int(n.get(k, 0)) for k in JUDGEMENTS}
        for k in JUDGEMENTS:
            totals[k] += counts[k]
        judge_rows += tally(kind.upper(), counts, lost.get(kind, 0.0))
    heads = "".join(f'<em class="cd-j-{k}">{k.title()}</em>' for k in JUDGEMENTS)
    judge = panel("cyan run cd-grow", "Judgements", f"""
      <div class="cd-judge">
        <div class="cd-j-row head"><u></u>{heads}<em class="cd-j-lost">Lost</em></div>
        {judge_rows}{tally("ALL", totals, all_lost, "all")}
      </div>""") if judge_rows else ""

    change = int(detail.get("rating_change") or 0)
    figures = [("Rating after", f"{rating_plate(int(detail.get('rating') or rating), small=True)}<small>{change:+d}</small>")]
    if play.get("chart_rating"):
        figures.append(("Chart rating", f'<b class="hot">{play["chart_rating"]}</b>'))
    figures += [
        ("DX score", f'{dx:,}<small>/ {max_dx:,}</small> <span class="stars">{star_marks(stars)}</span>'
                     + (f"<small>{100.0 * dx / max_dx:.1f}%</small>" if max_dx else "")),
        ("Combo", f"{int(detail.get('combo') or 0):,}<small>/ {int(detail.get('max_combo') or 0):,}</small>"),
    ]
    if detail.get("max_sync"):
        figures.append(("Sync", f"{int(detail.get('sync') or 0):,}<small>/ {int(detail.get('max_sync') or 0):,}</small>"))
    figures.append(("Timing", f"{int(detail.get('fast') or 0)}<small>fast</small> {int(detail.get('late') or 0)}<small>late</small>"))
    flags = "".join(f'<span class="cd-flag">{mark(icon)}{text}</span>'
                    for flag, icon, text in ((play.get("pb"), "pb", "new best"), (play.get("in_b50"), "best50", "in best-50")) if flag)
    figures += [("Track", _esc(str(detail.get("track") or play.get("track", "")).title())),
                ("Played", _esc(_day(detail.get("played_at") or play.get("day", ""))))]
    score = (f'<div class="track cd-score"><div class="track-stub">{rank_mark(play.get("rank", ""))}</div>'
             f'<div class="cd-score-body"><b class="cd-score-pct">{achievement:.4f}<small>%</small></b>'
             f'<div class="cd-score-flags">{flags or "<span>this play</span>"}</div></div></div>')
    jacket = _jacket(
        cover_html, play.get("cover", ""), ink, play["title"],
        f'<span class="cd-jk-under">{tier_mark(play["difficulty"])}{label} {_esc(play["level"])}{kind_mark(play["chart_type"])}</span>'
        f'<div class="cd-jk-lamps">{lamp_marks(play.get("fc"), play.get("fs"))}</div>')
    body = (_banner(stats(figures))
            + f'<div class="cd-lp{"" if judge else " bare"}">{jacket}<div class="cd-col">{score}{judge}</div></div>')
    return _card("Play detail", player_name, avatar_b64, f"{achievement:.4f}%", "this play", body, date_text)


# ---------------------------------------------------------------- /compare

def compare_image_html(me: Dict[str, Any], them: Dict[str, Any], levels: Sequence[Tuple[str, float, float, int]],
                       my_leads: Sequence[Dict[str, Any]], their_leads: Sequence[Dict[str, Any]], common: int,
                       cover_html: CoverFn, avatar_b64: str, date_text: str = "") -> str:
    def leads(items: Sequence[Dict[str, Any]]) -> str:
        out = ""
        for position, i in enumerate(items, 1):
            label, _ink = tier(i["difficulty"])
            out += (f'<div class="track" style="--tier:{_ink};">'
                    f'<div class="track-stub"><b>{position}</b>{tier_mark(i["difficulty"])}<small>{f"{i['constant']:.1f}" if i.get("constant") else ""}</small><strong>+{i["gap"]:.2f}</strong></div>'
                    f'<div class="track-body"><div class="track-name"><b>{_esc(i["title"])}</b></div>'
                    f'{cover_html(i.get("cover", ""), "track-jacket")}'
                    f'<div class="track-score"><b>{i["mine"]:.4f}%</b><small>vs {i["theirs"]:.4f}%</small><small>{label} {_esc(i["level"])}</small></div></div></div>')
        return f'<div class="tracks cd-leads">{out}</div>' if out else '<p class="cd-none">no leads</p>'

    def figures(p: Dict[str, Any]) -> str:
        # the rating is on the side's own sheet; the best-50 total is said only where it differs from it
        best50 = [("Best-50", _esc(p["best50"]))] if str(p["best50"]) != str(p["rating"]) else []
        return stats(best50 + [("Charts", _esc(p["charts"])),
                       ("Plays", _esc(p["plays"] or "?")), ("SSS", _esc(p["sss"])), ("SS", _esc(p["ss"])), ("FC", _esc(p["fc"])),
                       ("Hardest S", f'{p["hardest"]:.1f}')])

    def side(colour: str, p: Dict[str, Any], avatar: str, items: Sequence[Dict[str, Any]], heading: str) -> str:
        return panel(f"{colour} run cd-side", p["name"], f"""
          <div class="cd-who"><div class="emblem">{_avatar(avatar)}</div><div class="cd-who-name"><b>{_esc(p["name"])}</b>{rating_plate(p["rating"])}</div></div>
          <h3 class="cd-h3">{heading} <small>stub: gap</small></h3>{leads(items)}""", f"leads {p['leads']}")

    # the bars start below the lowest average, so a level where both are near 100 still shows who is ahead
    averages = [value for _level, mine, theirs, _n in levels for value in (mine, theirs)]
    floor = min(100.0, min(averages) - (101.0 - min(averages)) * 0.25) if averages else 0.0

    def reach(value: float) -> float:
        return max(4.0, min(100.0, 100.0 * (value - floor) / (101.0 - floor)))

    duels = "".join(
        f'<div class="cd-duel"><b class="cd-duel-v mine{" win" if mine > theirs else ""}">{mine:.2f}</b>'
        f'<span class="cd-duel-bar mine{" win" if mine > theirs else ""}"><i style="width:{reach(mine):.1f}%"></i></span>'
        f'<span class="cd-duel-lv"><b>{_esc(level)}</b><small>{n} charts</small></span>'
        f'<span class="cd-duel-bar theirs{" win" if theirs > mine else ""}"><i style="width:{reach(theirs):.1f}%"></i></span>'
        f'<b class="cd-duel-v theirs{" win" if theirs > mine else ""}">{theirs:.2f}</b></div>'
        for level, mine, theirs, n in levels
    ) or '<p class="cd-none">too few shared charts</p>'
    tied = common - me["leads"] - them["leads"]
    split = "".join(f'<i class="{cls}" style="flex-grow:{count};"></i>'
                    for cls, count in (("mine", me["leads"]), ("tie", tied), ("theirs", them["leads"])) if count > 0)
    middle = panel("gold run cd-mid", "Level by level", f"""
      <div class="cd-vs"><b class="mine">{_esc(me["name"])}</b><i>VS</i><b class="theirs">{_esc(them["name"])}</b></div>
      <div class="cd-split">{split}</div>
      <h3 class="cd-h3">Average on shared charts{f" <small>bars from {floor:.1f}%</small>" if levels else ""}</h3>
      <div class="cd-duels">{duels}</div>""", f"{common} in common")
    banner = _banner(f'<div class="cd-bside mine">{figures(me)}</div>',
                     stats([("Common", str(common)), ("You lead", f'<b class="hot">{me["leads"]}</b>'), ("Tied", str(tied)),
                             ("They lead", f'<b class="cd-cool">{them["leads"]}</b>')]),
                     f'<div class="cd-bside theirs">{figures(them)}</div>')
    body = (banner + f'<div class="cd-cmp">{side("pink", me, avatar_b64, my_leads, "Your biggest leads")}{middle}'
            f'{side("cyan", them, "", their_leads, "Their biggest leads")}</div>')
    diff = int(me["rating"]) - int(them["rating"])
    return _card(f"vs {them['name']}", me["name"], avatar_b64, f"{diff:+d}", "rating difference", body, date_text, "")


# ---------------------------------------------------------------- /leaderboard

def leaderboard_image_html(guild_name: str, rows: Sequence[Tuple[int, str, str, str]], date_text: str = "",
                           start: int = 0, size: int = 20) -> str:
    """The board, `size` players from `start`: the page the reply is on, under the count and the top rating of the whole board.
    The first three take the prize tickets across the top and everyone after them runs below as a roll of numbered stubs."""
    def who(display: str, maimai: str, region: str) -> str:
        return (f'<div class="cd-seat-who"><b>{_esc(display)}</b>'
                + (f'<small>{_esc(maimai)}</small>' if maimai and maimai != display else "") + "</div>"
                + (f'<span class="cd-region">{_esc(region.upper())}</span>' if region != "intl" else ""))

    page = list(enumerate(rows[start:start + size], start + 1))
    top = {position: row for position, row in page if position <= 3}
    rest = [(position, row) for position, row in page if position > 3]
    wide = len(page) > 8
    body = _banner(stats([("Opted in", str(len(rows))), ("Top rating", str(rows[0][0]) if rows else "—"),
                           ("On this page", f"{page[0][0]} to {page[-1][0]}" if page else "—")]))
    if top:
        prizes = "".join(
            f'<div class="cd-prize p{position}"><div class="cd-prize-stub"><b>{position}<small>{("st", "nd", "rd")[position - 1]}</small></b></div>'
            f'<div class="cd-prize-paper">{who(*top[position][1:])}{rating_plate(top[position][0])}</div></div>'
            for position in (2, 1, 3) if position in top)
        body += panel("gold run", "Top three", f'<div class="cd-prizes">{prizes}</div>')
    if rest:
        # the roll fills whole columns, top to bottom; a full page has the full width for four of them
        across = 4 if wide else 1 if len(rest) <= 3 else 2
        spare = across * -(-len(rest) // across) - len(rest)
        seats = "".join(f'<div class="track cd-seat"><div class="track-stub"><b>{position}</b></div>'
                        f'<div class="cd-seat-paper">{who(display, maimai, region)}{rating_plate(rating, small=True)}</div></div>'
                        for position, (rating, display, maimai, region) in rest)
        # the spare places at the foot of the last column hold how to join, so the roll ends square
        if spare:
            seats += (f'<p class="cd-seat-note" style="grid-row:span {spare};"><b>/settings leaderboard:True</b> puts you on the board.'
                      " Ratings come from each player's last /analyze.</p>")
        body += panel("cyan run", "The board", f'<div class="cd-seats" style="--across:{across};--rows:{-(-len(rest) // across)};">{seats}</div>',
                      f"{rest[0][0]} to {rest[-1][0]} of {len(rows)}")
    return _card("Rating leaderboard", guild_name.upper(), "", str(rows[0][0]) if rows else "—", "top rating", body, date_text,
                 "" if wide else "narrow")

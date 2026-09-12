from datetime import datetime
from typing import Any, Dict, Optional, Sequence, Tuple

from rasmai.images.markup import render
from rasmai.images.posters import CoverFn, _esc, tier
from rasmai.images.pages import _image, star_text

def _card(eyebrow: str, name: str, avatar_b64: str, counters: Sequence[tuple], headline_value: str,
          headline_caption: str, body: str, date_text: str) -> str:
    return _image(eyebrow, name, avatar_b64, counters, headline_value, headline_caption, body, date_text, "narrow")


def _lamp(fc: str, fs: str) -> str:
    return " · ".join(b for b in (str(fc or "").upper(), str(fs or "").upper()) if b and b != "NONE")


# ---------------------------------------------------------------- /chart and /random

def song_card_html(title: str, artist: str, genre: str, version_label: str, cover: str, cover_html: CoverFn,
                   rows: Sequence[Dict[str, Any]], player_name: str, rating: int, avatar_b64: str,
                   cutoffs: str, date_text: str = "", highlight: Optional[str] = None,
                   ladder: Sequence[Dict[str, Any]] = (), ladder_label: str = "", forecast: str = "",
                   eyebrow: str = "Chart lookup", facts: Sequence[str] = ()) -> str:
    table = ""
    for r in rows:
        label, ink = tier(r["difficulty"])
        cls = ' class="pick"' if highlight and r["difficulty"] == highlight else ""
        if r.get("played"):
            score = f'<span class="big">{r["accuracy"]:.4f}<small>{_esc(r["rank"])}</small></span>'
            rate = f'<span class="big">{r["rating"]}</span>'
            lamp = _esc(_lamp(r.get("fc"), r.get("fs")) or "—")
            if r.get("max_dx"):
                dx = f'{r["dx"]:,} / {r["max_dx"]:,}<br /><span class="stars">{star_text(r["stars"])}</span>'
            elif r.get("dx"):
                dx = f'{r["dx"]:,}'
            else:
                dx = "—"
            plays = f'{r["plays"]} play{"s" if r["plays"] != 1 else ""}' if r.get("plays") else "—"
        else:
            score = '<span class="dim">never played</span>'
            rate, lamp, dx, plays = "—", "—", "—", "—"
        table += f"""
        <tr style="--tier:{ink};"{cls}>
          <td><span class="badge">{label} {_esc(r["level"])}<small>{_esc(r["chart_type"].upper())}</small></span></td>
          <td class="num">{r["constant"]:.1f}</td>
          <td>{score}</td>
          <td>{rate}</td>
          <td class="num">{lamp}</td>
          <td class="num">{dx}</td>
          <td class="num">{plays}</td>
          <td class="num">{_esc(r.get("note", ""))}</td>
        </tr>"""
    body = f"""
    <div class="card-head">
      {cover_html(cover, "song-cover")}
      <div>
        <div class="card-title">{_esc(title)}</div>
        <div class="card-sub">{_esc(artist)}<br />{" · ".join(_esc(f) for f in ([genre, version_label] + list(facts)) if f)}<br />your best-50 cutoffs: <b>{_esc(cutoffs)}</b></div>
      </div>
    </div>
    <table class="difftable">
      <thead><tr><th>Chart</th><th>Const</th><th>Your score</th><th>Rating</th><th>Lamp</th><th>DX score</th><th>Plays</th><th>Best-50</th></tr></thead>
      <tbody>{table}</tbody>
    </table>"""
    if ladder:
        steps = "".join(
            render("ladder-row", rank=_esc(step["rank"]), need=step["need"], rating=step["rating"],
                   gain=f"+{step['gain']}" if step["gain"] > 0 else "&mdash;", odds=step["odds"] * 100)
            for step in ladder
        )
        body += render("ladder", label=_esc(ladder_label), rows=steps,
                       forecast=f'<div class="forecast">{_esc(forecast)}</div>' if forecast else "")

    played = [r for r in rows if r.get("played")]
    best = max((r["rating"] for r in played), default=0)
    counters = [("Charts", str(len(rows))), ("Played", str(len(played)))]
    return _card(eyebrow, player_name, avatar_b64, counters, str(best) if best else "—", "best rating on this song", body, date_text)


# ---------------------------------------------------------------- /chart history

RANK_LINES = ((80.0, "A"), (90.0, "AA"), (94.0, "AAA"), (97.0, "S"), (98.0, "S+"), (99.0, "SS"), (99.5, "SS+"), (100.0, "SSS"), (100.5, "SSS+"))


def history_card_html(title: str, difficulty: str, level: str, chart_type: str, cover: str, cover_html: CoverFn,
                      points: Sequence[Dict[str, Any]], player_name: str, rating: int, avatar_b64: str,
                      date_text: str = "") -> str:
    """Achievement over time for one chart: every recorded play as a dot, the best so far as a line.

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
    :param rating: The player's rating.
    :type rating: int
    :param avatar_b64: The player's avatar, base64 encoded.
    :type avatar_b64: str
    :param date_text: The date to print on the image.
    :type date_text: str
    :rtype: str
    """
    label, ink = tier(difficulty)
    width, height = 1480, 520
    left, right, top, bottom = 124, 36, 28, 60
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

    svg = []
    last_label_y = 1e9
    for value, name in RANK_LINES:
        if y_min < value < y_max:
            y = y_at(value)
            svg.append(f'<line class="hist-rank" x1="{left}" x2="{width - right}" y1="{y:.1f}" y2="{y:.1f}"/>')
            if last_label_y - y >= 18:      # labels for lines that sit on top of each other would just overprint
                svg.append(f'<text class="hist-axis" x="{left - 14}" y="{y + 4:.1f}" text-anchor="end">{_esc(name)} {value:g}</text>')
                last_label_y = y
    svg.append(f'<line class="hist-frame" x1="{left}" x2="{width - right}" y1="{top + plot_h}" y2="{top + plot_h}"/>')

    if points:
        best = 0.0
        step = []
        for index, point in enumerate(points):
            value = float(point["achievement"])
            x = x_at(point["when"], index)
            if value > best:
                if step:
                    step.append(f"L{x:.1f} {y_at(best):.1f}")
                best = value
                step.append(f"{'M' if len(step) == 0 else 'L'}{x:.1f} {y_at(best):.1f}")
        step.append(f"L{x_at(points[-1]['when'], len(points) - 1):.1f} {y_at(best):.1f}")
        svg.append(f'<path class="hist-best" d="{" ".join(step)}"/>')
        for index, point in enumerate(points):
            x, y = x_at(point["when"], index), y_at(float(point["achievement"]))
            cls = "hist-dot best" if point.get("source") == "best" else "hist-dot"
            svg.append(f'<circle class="{cls}" cx="{x:.1f}" cy="{y:.1f}" r="{7 if point.get("source") == "best" else 6}"/>')
        # date labels at the ends and a few in between, never overlapping
        labels = [0] if len(points) == 1 else sorted({0, len(points) - 1, len(points) // 2, len(points) // 4, 3 * len(points) // 4})
        last_x = -1e9
        for index in labels:
            x = x_at(points[index]["when"], index)
            if x - last_x < 120:
                continue
            last_x = x
            anchor = "start" if index == 0 else "end" if index == len(points) - 1 else "middle"
            svg.append(f'<text class="hist-axis" x="{x:.1f}" y="{top + plot_h + 30}" text-anchor="{anchor}">'
                       f'{points[index]["when"].strftime("%d %b %Y")}</text>')
        peak = max(points, key=lambda p: float(p["achievement"]))
        px, py = x_at(peak["when"], points.index(peak)), y_at(float(peak["achievement"]))
        px = min(max(px, left + 70), width - right - 70)     # the label stays inside the frame at either end
        svg.append(f'<text class="hist-peak" x="{px:.1f}" y="{max(top + 14, py - 16):.1f}" text-anchor="middle">{float(peak["achievement"]):.4f}%</text>')
    else:
        svg.append(f'<text class="hist-empty" x="{left + plot_w / 2:.0f}" y="{top + plot_h / 2:.0f}" text-anchor="middle">'
                   'no scores recorded yet - they build up from each analysis and your recent plays</text>')

    plays = [p for p in points if p.get("source") != "best"]
    body = f"""
    <div class="card-head hist-head">
      {cover_html(cover, "song-cover")}
      <div>
        <div class="card-title">{_esc(title)}</div>
        <div class="card-sub" style="--tier:{ink};"><span class="badge">{label} {_esc(level)}<small>{_esc(chart_type.upper())}</small></span></div>
        <div class="hist-legend"><span class="sw best"></span>best so far <span class="sw play"></span>play seen in your recent list <span class="sw mark"></span>best read from your scores</div>
      </div>
    </div>
    <svg class="hist" viewBox="0 0 {width} {height}" width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg">{"".join(svg)}</svg>"""
    first = points[0]["when"].strftime("%d %b %Y") if points else "—"
    counters = [("Scores", str(len(points))), ("Plays seen", str(len(plays))), ("Since", first)]
    headline = f"{max(values):.4f}%" if values else "—"
    return _card("Score history", player_name, avatar_b64, counters, headline, "best recorded", body, date_text)


# ---------------------------------------------------------------- /lastplay

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
    order = ("tap", "hold", "slide", "touch", "break")
    totals = {"critical": 0, "perfect": 0, "great": 0, "good": 0, "miss": 0}
    lost = note_losses(notes, achievement)
    judge_rows = ""
    for kind in order:
        n = notes.get(kind)
        if not n:
            continue
        for k in totals:
            totals[k] += int(n.get(k, 0))
        cost = lost.get(kind, 0.0)
        judge_rows += (f'<tr><td>{kind.upper()}</td><td class="crit">{n["critical"]}</td><td>{n["perfect"]}</td>'
                       f'<td>{n["great"]}</td><td>{n["good"]}</td><td class="miss">{n["miss"]}</td>'
                       f'<td class="{"miss" if cost >= 0.5 else ""}">{f"-{cost:.2f}%" if cost >= 0.005 else ""}</td></tr>')
    judge = f"""
    <table class="judge">
      <thead><tr><th>Notes</th><th>Critical</th><th>Perfect</th><th>Great</th><th>Good</th><th>Miss</th><th>Lost</th></tr></thead>
      <tbody>{judge_rows}<tr class="total"><td>ALL</td><td class="crit">{totals["critical"]}</td><td>{totals["perfect"]}</td><td>{totals["great"]}</td><td>{totals["good"]}</td><td class="miss">{totals["miss"]}</td><td>{f"-{sum(lost.values()):.2f}%" if lost else ""}</td></tr></tbody>
    </table>""" if judge_rows else ""
    change = int(detail.get("rating_change") or 0)
    tiles = [
        ("Achievement", f"{achievement:.4f}<small>%</small>", play.get("rank", "")),
        ("DX score", f"{dx:,}<small>/ {max_dx:,}</small>", star_text(stars)),
        ("Combo", f"{int(detail.get('combo') or 0):,}<small>/ {int(detail.get('max_combo') or 0):,}</small>",
         f"sync {int(detail.get('sync') or 0):,} / {int(detail.get('max_sync') or 0):,}" if detail.get("max_sync") else "&nbsp;"),
        ("Timing", f"{int(detail.get('fast') or 0)}<small>fast</small> {int(detail.get('late') or 0)}<small>late</small>", "&nbsp;"),
        ("Rating after", f"{int(detail.get('rating') or rating)}<small>{change:+d}</small>", "in best-50" if play.get("in_b50") else ("new best" if play.get("pb") else "&nbsp;")),
    ]
    tile_html = "".join(f'<div class="tile"><div class="k">{_esc(k)}</div><div class="v">{v}</div><div class="s">{s}</div></div>' for k, v, s in tiles)
    lamp = _lamp(play.get("fc"), play.get("fs"))
    body = f"""
    <div class="card-head" style="--tier:{ink};">
      {cover_html(play.get("cover", ""), "song-cover")}
      <div>
        <div class="card-title">{_esc(play["title"])}</div>
        <div class="card-sub"><span class="badge">{label} {_esc(play["level"])}<small>{_esc(play["chart_type"].upper())}</small></span><br />
          {_esc(detail.get("track") or play.get("track", ""))} · {_esc(detail.get("played_at") or play.get("day", ""))}{(" · <b>" + _esc(lamp) + "</b>") if lamp else ""}</div>
        <div class="stat-row">{tile_html}</div>
      </div>
    </div>
    {judge}"""
    counters = [("Rating", str(rating))]
    return _card("Play detail", player_name, avatar_b64, counters, f"{achievement:.4f}", _esc(play.get("rank", "")) + " on this play", body, date_text)


# ---------------------------------------------------------------- /compare

def compare_image_html(me: Dict[str, Any], them: Dict[str, Any], levels: Sequence[Tuple[str, float, float, int]],
                       my_leads: Sequence[Dict[str, Any]], their_leads: Sequence[Dict[str, Any]], common: int,
                       cover_html: CoverFn, avatar_b64: str, date_text: str = "") -> str:
    def side(p: Dict[str, Any]) -> str:
        return (f'<div class="tiles" style="grid-template-columns: repeat(2, 1fr)">'
                f'<div class="tile"><div class="k">Rating</div><div class="v">{p["rating"]}</div><div class="s">best-50 {p["best50"]}</div></div>'
                f'<div class="tile"><div class="k">Charts</div><div class="v">{p["charts"]}</div><div class="s">{p["plays"] or "?"} plays</div></div>'
                f'<div class="tile"><div class="k">SSS / SS</div><div class="v">{p["sss"]}<small>/ {p["ss"]}</small></div><div class="s">{p["fc"]} FC</div></div>'
                f'<div class="tile"><div class="k">Hardest S</div><div class="v">{p["hardest"]:.1f}</div><div class="s">&nbsp;</div></div></div>')

    level_rows = "".join(
        f'<div class="vs-row"><span class="{"win" if mine > theirs else ""}" style="text-align:right">{mine:.2f}</span>'
        f'<span class="lv">{_esc(level)} · {n}</span><span class="{"win" if theirs > mine else ""}">{theirs:.2f}</span></div>'
        for level, mine, theirs, n in levels
    ) or '<div class="vs-row"><span></span><span class="lv">too few shared charts</span><span></span></div>'

    def leads(items: Sequence[Dict[str, Any]]) -> str:
        return "".join(
            f'<div class="lead">{cover_html(i.get("cover", ""), "")}<div><div class="t">{_esc(i["title"])}</div>'
            f'<div class="m">{tier(i["difficulty"])[0]} {_esc(i["level"])} · {i["mine"]:.2f} vs {i["theirs"]:.2f}</div></div><div class="g">+{i["gap"]:.2f}</div></div>'
            for i in items
        ) or '<div class="lead"><div></div><div class="m">none</div><div></div></div>'

    body = f"""
    <div class="two">
      <div class="side"><h3>{_esc(me["name"])}</h3>{side(me)}</div>
      <div class="side"><h3>{_esc(them["name"])}</h3>{side(them)}</div>
    </div>
    <div class="section-label">Average on shared charts · {common} in common</div>
    <div class="vs-row" style="border-top:none;color:var(--paper-dim);font-size:12px"><span style="text-align:right">{_esc(me["name"])}</span><span class="lv">level</span><span>{_esc(them["name"])}</span></div>
    {level_rows}
    <div class="two">
      <div class="side"><h3>Your biggest leads</h3>{leads(my_leads)}</div>
      <div class="side"><h3>Their biggest leads</h3>{leads(their_leads)}</div>
    </div>"""
    counters = [("Common", str(common)), ("You lead", str(me["leads"])), ("They lead", str(them["leads"]))]
    diff = int(me["rating"]) - int(them["rating"])
    return _card(f"vs {them['name']}", me["name"], avatar_b64, counters, f"{diff:+d}", "rating difference", body, date_text)


# ---------------------------------------------------------------- /leaderboard

def leaderboard_image_html(guild_name: str, rows: Sequence[Tuple[int, str, str, str]], date_text: str = "") -> str:
    table = "".join(
        f'<tr><td class="pos">{position}</td><td>{_esc(display)}{(" <span class=dim>· " + _esc(maimai) + "</span>") if maimai and maimai != display else ""}</td>'
        f'<td class="dim">{_esc(region.upper()) if region != "intl" else ""}</td><td class="rt">{rating}</td></tr>'
        for position, (rating, display, maimai, region) in enumerate(rows, 1)
    )
    body = f'<table class="board"><tbody>{table}</tbody></table>'
    counters = [("Players", str(len(rows)))]
    return _card("Rating leaderboard", guild_name, "", counters, str(rows[0][0]) if rows else "—", "top rating", body, date_text)

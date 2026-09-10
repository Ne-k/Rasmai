from typing import Any, Dict, Sequence, Tuple

from rasmai.images.markup import render
from rasmai.images.posters import lvl, CoverFn, _esc, tier
from rasmai.images.pages.common import _fc, _image


def best50_image_html(new_entries: Sequence[Dict[str, Any]], old_entries: Sequence[Dict[str, Any]],
                      player_name: str, rating: int, avatar_b64: str, cover_html: CoverFn,
                      new_total: int, old_total: int, date_text: str = "") -> str:
    def cards(entries: Sequence[Dict[str, Any]], size: int) -> str:
        out = ""
        for position, e in enumerate(entries, 1):
            label, ink = tier(e["difficulty"])
            out += f"""
            <div class="b50" style="--tier:{ink};">
              {cover_html(e.get("cover", ""), "cv")}
              <div class="pos">#{position}</div>
              <div class="t" title="{_esc(e["title"])}">{_esc(e["title"])}</div>
              <div class="d">{label} {lvl(e["level"], e.get("constant"))} · {_esc(e["chart_type"].upper())}</div>
              <div class="s"><b>{e["accuracy"]:.4f}</b> {_esc(e["rank"])}{(" · " + _esc(_fc(e.get("fc"), e.get("fs")))) if _fc(e.get("fc"), e.get("fs")) else ""}</div>
              <div class="r">{e["rating"]}</div>
            </div>"""
        for _ in range(max(0, size - len(entries))):
            out += '<div class="b50" style="--tier:#2b2924;"><div class="no-cover"></div><div class="pos">open slot</div></div>'
        return out

    body = f"""
    <div class="section-label">Current version · {len(new_entries)} of 15 · {new_total}</div>
    <div class="b50-grid">{cards(new_entries, 15)}</div>
    <div class="section-label">Older versions · {len(old_entries)} of 35 · {old_total}</div>
    <div class="b50-grid">{cards(old_entries, 35)}</div>"""
    counters = [("New", str(new_total)), ("Old", str(old_total)),
                ("Lowest", f"{min([e['rating'] for e in new_entries] or [0])} / {min([e['rating'] for e in old_entries] or [0])}")]
    return _image("Best 50", player_name, avatar_b64, counters, str(new_total + old_total), "best-50 total", body, date_text)


def recent_image_html(days: Sequence[Tuple[str, Sequence[Dict[str, Any]]]], player_name: str, rating: int,
                      avatar_b64: str, cover_html: CoverFn, pbs: int, date_text: str = "") -> str:
    items = ""
    for day_label, plays in days:
        items += render("recent-head", label=_esc(day_label), count=len(plays))
        for p in plays:
            label, ink = tier(p["difficulty"])
            extras = []
            if p.get("max_dx"):
                extras.append(f"{p['dx_pct']:.0f}% DX")
            lamp = _fc(p.get("fc"), p.get("fs"))
            if lamp:
                extras.append(lamp)
            items += render(
                "recent-play",
                ink=ink,
                cover=cover_html(p.get("cover", ""), ""),
                title=_esc(p["title"]),
                flags=('<span class="flag">PB</span>' if p.get("pb") else "") + ('<span class="flag dim">B50</span>' if p.get("in_b50") else ""),
                time=_esc(p["time"]),
                tier_label=label,
                level=lvl(p["level"], p.get("constant")),
                achievement=f"{p['achievement']:.4f}" if p.get("achievement") is not None else "—",
                rank=_esc(p["rank"]),
                extra=_esc(" · " + " · ".join(extras)) if extras else "",
                chart_rating=p["chart_rating"] or "",
            )
    total = sum(len(p) for _d, p in days)
    # the image is a picture, so its clock faces cannot follow the reader: say which zone they are
    counters = [("Days", str(len(days))), ("Plays", str(total)), ("New bests", str(pbs)), ("Times", "JST")]
    return _image("Recent plays", player_name, avatar_b64, counters, str(rating), "rating",
                  render("recent-body", items=items), date_text)


def level_image_html(rows: Sequence[Dict[str, Any]], level_label: str, sort_label: str, player_name: str,
                     rating: int, avatar_b64: str, cover_html: CoverFn, total: int, played: int,
                     start: int = 1, date_text: str = "") -> str:
    """One page of a level as a poster: a dozen big cards, the way /analyze draws its picks.

    A table of sixty rows was legible only at full size; Discord's preview shrinks the image
    to a few hundred pixels, so the image carries the same charts as the embed page, large.

    :param rows: The rows to render.
    :type rows: Sequence[Dict[str, Any]]
    :param player_name: The player's name on maimai DX NET.
    :type player_name: str
    :param rating: The player's rating.
    :type rating: int
    :param avatar_b64: The player's avatar, base64 encoded.
    :type avatar_b64: str
    :param cover_html: Renders a jacket as markup.
    :type cover_html: CoverFn
    :param total: The total to measure against.
    :type total: int
    :param played: Whether the player has a score on the chart.
    :type played: int
    :param start: Where to start from.
    :type start: int
    :param date_text: The date to print on the image.
    :type date_text: str
    :param level_label: The level as it is shown.
    :type level_label: str
    :param sort_label: The chosen order, as it is shown.
    :type sort_label: str
    :rtype: str
    """
    cards = ""
    for offset, r in enumerate(rows):
        label, ink = tier(r["difficulty"])
        if r.get("unplayed"):
            score = '<span style="color:#5cd3e8">never played</span>'
            worth = f'<div class="worth dim">const {r["constant"]:.1f}</div>'
        else:
            lamp = _fc(r.get("fc"), r.get("fs"))
            score = f"<b>{r['accuracy']:.4f}</b> {_esc(r['rank'])}" + (f" &middot; {_esc(lamp)}" if lamp else "")
            worth = f'<div class="worth">{r["rating"]} <small>const {r["constant"]:.1f}</small></div>'
        note = f'<div class="genre">{_esc(r["note"])}</div>' if r.get("note") else ""
        cards += f"""
        <div class="card" style="--tier:{ink};">
          {cover_html(r.get('cover', ''), 'card-cover')}
          <div>
            <div class="rank">{start + offset}</div>
            <div class="tier">{label} {_esc(r['level'])} <span>&middot; {_esc(r['chart_type'].upper())}</span></div>
            <div class="title">{_esc(r['title'])}</div>
            <div class="est">{score}</div>
            {worth}
            {note}
          </div>
        </div>"""
    last = start + len(rows) - 1
    body = f"""
    <div class="section-label">Level {_esc(level_label)} &middot; {sort_label} &middot; charts {start}&ndash;{last} of {total} &middot; {played} played</div>
    <div class="grid level-grid">{cards}</div>"""
    counters = [("Charts", str(total)), ("Played", str(played)), ("Page", f"{(start - 1) // max(1, len(rows)) + 1 if rows else 1}")]
    return _image(f"Level {level_label}", player_name, avatar_b64, counters, str(rating), "rating", body, date_text)


STAR_STEPS = ((0.85, 1), (0.90, 2), (0.93, 3), (0.95, 4), (0.97, 5))


def stars_for(ratio: float) -> int:
    stars = 0
    for threshold, count in STAR_STEPS:
        if ratio >= threshold:
            stars = count
    return stars


def star_text(stars: int) -> str:
    return "★" * stars + "☆" * (5 - stars)


def dxscore_image_html(tiles: Dict[int, int], rows: Sequence[Dict[str, Any]], player_name: str, rating: int,
                       avatar_b64: str, cover_html: CoverFn, average: float, date_text: str = "") -> str:
    tile_html = "".join(
        f'<div class="tile"><div class="k">{star_text(s)}</div><div class="v">{tiles.get(s, 0)}<small>charts</small></div></div>'
        for s in (5, 4, 3, 2, 1, 0)
    )
    head = """<thead><tr><th></th><th></th><th>Chart</th><th>DX score</th><th>Now</th><th>Next</th><th style="text-align:right">Points short</th></tr></thead>"""

    def table(chunk: Sequence[Dict[str, Any]], start: int) -> str:
        out = ""
        for offset, r in enumerate(chunk):
            label, ink = tier(r["difficulty"])
            out += f"""
            <tr style="--tier:{ink};">
              <td class="c-rank">{start + offset}</td>
              <td class="c-cover">{cover_html(r.get('cover', ''), 'row-cover')}</td>
              <td><span class="row-title">{_esc(r['title'])}</span><span class="row-tier">{label} {lvl(r['level'], r.get('constant'))} · {_esc(r['chart_type'].upper())}</span></td>
              <td class="num"><b>{r['dx']:,}</b> / {r['max_dx']:,} · {r['ratio'] * 100:.1f}%</td>
              <td class="stars{' dim' if r['stars'] == 0 else ''}">{star_text(r['stars'])}</td>
              <td class="stars">{star_text(r['stars'] + 1)}</td>
              <td class="c-gain" style="font-size:18px">{r['short']}</td>
            </tr>"""
        return out

    half = (len(rows) + 1) // 2
    body = f"""
    <div class="section-label">Charts by DX star</div>
    <div class="tiles" style="grid-template-columns: repeat(6, 1fr)">{tile_html}</div>
    <div class="section-label">Closest to the next star</div>
    <div class="columns">
      <div><table>{head}<tbody>{table(rows[:half], 1)}</tbody></table></div>
      <div><table>{head}<tbody>{table(rows[half:], half + 1)}</tbody></table></div>
    </div>"""
    total = sum(tiles.values())
    counters = [("Charts", str(total)), ("Average", f"{average * 100:.1f}%")]
    return _image("DX score", player_name, avatar_b64, counters, str(tiles.get(5, 0)), "five-star charts", body, date_text)

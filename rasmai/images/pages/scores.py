from typing import Any, Dict, List, Sequence, Tuple

from rasmai.images.posters import _esc, CoverFn, STAR_POINTS, kind_mark, lamp_marks, mark, panel, rank_mark, rating_plate, stats, tier, tier_mark
from rasmai.bot.ui.emoji import RANKS
from rasmai.images.pages.common import _image


def best50_image_html(new_entries: Sequence[Dict[str, Any]], old_entries: Sequence[Dict[str, Any]],
                      player_name: str, avatar_b64: str, cover_html: CoverFn,
                      new_total: int, old_total: int, date_text: str = "") -> str:
    def tickets(entries: Sequence[Dict[str, Any]], size: int) -> str:
        out = ""
        for position, e in enumerate(entries, 1):
            label, ink = tier(e["difficulty"])
            constant = f'<small>{e["constant"]:.1f}</small>' if e.get("constant") else ""
            dx = (f'<small>DX {e["dx"]:,}' + (f' / {e["max_dx"]:,}' if e.get("max_dx") else "") + "</small>") if e.get("dx") else ""
            out += f"""
            <div class="track" style="--tier:{ink};">
              <div class="track-stub"><b>{position}</b>{tier_mark(e["difficulty"])}{constant}<strong>{e["rating"]}</strong></div>
              <div class="track-body">
                <div class="track-name"><b title="{_esc(e["title"])}">{_esc(e["title"])}</b>{kind_mark(e["chart_type"])}</div>
                {cover_html(e.get("cover", ""), "track-jacket")}
                <div class="track-score"><b>{e["accuracy"]:.4f}%</b><small>{label} {_esc(e["level"])}</small>{dx}</div>
                <div class="track-foot"><span>{rank_mark(e["rank"])}{lamp_marks(e.get("fc"), e.get("fs"))}</span></div>
              </div>
            </div>"""
        for _ in range(max(0, size - len(entries))):
            out += ('<div class="track open"><div class="track-stub"></div><div class="track-body"><div class="track-name"><b>open slot</b></div>'
                    '<div class="track-jacket no-cover"></div></div></div>')
        return out

    everything = [*new_entries, *old_entries]
    banner = ""
    if everything:
        n = len(everything)

        def tally(field: str, order: Sequence[str], draw) -> str:
            # one of each mark the fifty hold, best first, with how many
            held = [str(e.get(field) or "").upper() for e in everything]
            return "".join(f"<span>{draw(name)}{held.count(name)}</span>" for name in order if name in held)
        tiers = [str(e["difficulty"]).lower() for e in everything]
        figures = [("Lowest in", f"{min([e['rating'] for e in new_entries] or [0])} / {min([e['rating'] for e in old_entries] or [0])}"),
                   ("Average constant", f"{sum(e['constant'] for e in everything) / n:.2f}"),
                   ("Average achievement", f"{sum(e['accuracy'] for e in everything) / n:.4f}%"),
                   ("Rating per chart", f"{sum(e['rating'] for e in everything) / n:.1f}")]
        if n < 50:
            figures.append(("Open slots", str(50 - n)))
        banner = f"""
    <div class="banner">
      <div class="sum"><span>{new_total}<small>new charts</small></span><i>+</i><span>{old_total}<small>old charts</small></span>
        <i>=</i><span><b>{new_total + old_total}</b><small>best-50 total</small></span></div>
      {stats(figures)}
      <div class="tally">{tally("rank", list(RANKS), rank_mark)}{"".join(f"<span>{tier_mark(name)}{tiers.count(name)}</span>" for name in sorted(set(tiers), key=tiers.count, reverse=True))}</div>
      <div class="tally">{tally("fc", ("AP+", "AP", "FC+", "FC"), lambda name: lamp_marks(name, None))}{tally("fs", ("FDX+", "FDX", "FS+", "FS", "SYNC"), lambda name: lamp_marks(None, name))}</div>
    </div>"""
    # eight across: 15 charts and the stub's key fill two rolls, 35 charts and the marks' key five, so both sheets end square
    stub_key = (f'<div class="b50-key b50-key-stub"><p><b>Stub:</b> place, difficulty, constant, rating</p>'
                f'<p><span>{mark("type_dx")}DX</span><span>{mark("type_std")}Standard</span></p></div>')
    marks_key = f"""<div class="b50-key" style="grid-column:span 5">
      <p><span>{mark("diff_basic")}Basic</span><span>{mark("diff_advanced")}Advanced</span><span>{mark("diff_expert")}Expert</span><span>{mark("diff_master")}Master</span>
         <span>{mark("diff_remaster")}Re:Master</span></p>
      <p><span>{mark("rank_sssp")}rank</span><span>{mark("lamp_fc")}full combo</span><span>{mark("lamp_ap")}all perfect</span><span>{mark("lamp_fs")}full sync</span>
         <span>{mark("lamp_fdx")}full sync DX</span><span>{mark("lamp_fcp")}a plus is the better one</span></p></div>"""
    body = (banner
            + panel("pink run", "New charts", f'<div class="tracks" style="--across:8">{tickets(new_entries, 15)}{stub_key}</div>',
                    "your best charts from the current version")
            + panel("cyan run", "Old charts", f'<div class="tracks" style="--across:8">{tickets(old_entries, 35)}{marks_key}</div>',
                    "your best charts from every earlier version"))
    return _image("Best 50", player_name, avatar_b64, rating_plate(new_total + old_total), "best-50 total", body, date_text)


def _ticket(stub: str, ink: str, row: Dict[str, Any], cover_html: CoverFn, score: str, foot: str, flags: str = "", shape: str = "") -> str:
    return (f'<div class="track{shape}" style="--tier:{ink};"><div class="track-stub">{stub}</div><div class="track-body">'
            f'<div class="track-name"><b>{_esc(row["title"])}</b>{flags}{kind_mark(row["chart_type"])}</div>'
            f'{cover_html(row.get("cover", ""), "track-jacket")}<div class="track-score">{score}</div>'
            f'<div class="track-foot">{foot}</div></div></div>')


def _stub(first: str, row: Dict[str, Any], loud: Any) -> str:
    constant = f'<small>{row["constant"]:.1f}</small>' if row.get("constant") else "<small></small>"
    return f"<b>{first}</b>{tier_mark(row['difficulty'])}{constant}<strong>{loud}</strong>"


def _tally(rows: Sequence[Dict[str, Any]]) -> str:
    held = [str(r.get("rank") or "").upper() for r in rows]
    fcs = [str(r.get("fc") or "").upper() for r in rows]
    fss = [str(r.get("fs") or "").upper() for r in rows]
    return ("".join(f"<span>{rank_mark(name)}{held.count(name)}</span>" for name in RANKS if name in held)
            + "".join(f"<span>{lamp_marks(name, None)}{fcs.count(name)}</span>" for name in ("AP+", "AP", "FC+", "FC") if name in fcs)
            + "".join(f"<span>{lamp_marks(None, name)}{fss.count(name)}</span>" for name in ("FDX+", "FDX", "FS+", "FS", "SYNC") if name in fss))


_ACROSS = 8
_RUNS = ("pink", "cyan", "gold")


def recent_image_html(days: Sequence[Tuple[str, Sequence[Dict[str, Any]]]], player_name: str, rating: int,
                      avatar_b64: str, cover_html: CoverFn, pbs: int, date_text: str = "") -> str:
    def average(plays: Sequence[Dict[str, Any]]) -> str:
        scored = [p["achievement"] for p in plays if p.get("achievement") is not None]
        return f"{sum(scored) / len(scored) if scored else 0.0:.2f}%"

    def date(label: str, year: bool = True) -> str:
        # "Mon 01 Aug 2026" as "1 Aug 2026"
        parts = label.split()
        if len(parts) != 4 or not parts[1].isdigit():
            return label
        return f"{int(parts[1])} {parts[2]}" + (f" {parts[3]}" if year else "")

    def count(n: int, word: str) -> str:
        return f"{n} {word}{'s' * (n != 1)}"

    def play(p: Dict[str, Any]) -> str:
        label, ink = tier(p["difficulty"])
        score = f"{p['achievement']:.4f}%" if p.get("achievement") is not None else "—"
        dx = f"<small>DX {p['dx_pct']:.1f}%</small>" if p.get("max_dx") else ""
        flags = (mark("pb") if p.get("pb") else "") + (mark("best50") if p.get("in_b50") else "")
        return _ticket(_stub(_esc(p["time"]), p, p["chart_rating"] or "—"), ink, p, cover_html,
                       f"<b>{score}</b><small>{label} {_esc(p['level'])}</small>{dx}",
                       f'<span>{rank_mark(p.get("rank"))}{lamp_marks(p.get("fc"), p.get("fs"))}</span>', flags, " sc-play")

    def pack() -> List[List[List[int]]]:
        lines: List[List[List[int]]] = []
        for at, (_label, group) in enumerate(days):
            cells = len(group)
            wide = min(cells, _ACROSS)
            # each sheet's own edge takes room, so a line shared by several days holds seven tickets, not eight
            if not lines or sum(day[1] for day in lines[-1]) + wide > _ACROSS - 1:
                lines.append([])
            lines[-1].append([at, wide, cells])
        for line in lines:
            # the last day on a line takes the room the line leaves, so every line of sheets ends level
            line[-1][1] += _ACROSS - (len(line) > 1) - sum(day[1] for day in line)
        return lines

    plays = [p for _d, group in days for p in group]
    lines = pack()
    placed = [(at, wide, cells, -cells % wide, len(line)) for line in lines for at, wide, cells in line]
    # the first ragged roll is closed by the key; any later one by the hours the day's plays span
    keyed = next((at for at, _w, _c, spare, _n in placed if spare), None)
    key = (f'<p>{mark("pb")}Matches your current best</p><p>{mark("best50")}Counts toward your rating</p>'
           '<p><b>Stub:</b> time, difficulty, constant, rating</p><p>Times in JST</p>')
    sheets = ""
    for at, wide, cells, spare, shared in placed:
        label, group = days[at]
        colour = _RUNS[at % len(_RUNS)]
        new = sum(1 for p in group if p.get("pb"))
        piece = ""
        if spare:
            piece = (f'<div class="sc-key" style="grid-column:span {spare}">'
                     + (key if at == keyed else f'<p><b>{_esc(group[-1]["time"])} – {_esc(group[0]["time"])}</b></p><p>First to last play</p>') + "</div>")
        body = "".join(play(p) for p in group) + piece
        # a day's figures ride its band: a sheet two tickets wide or less has room for the count alone
        figures = [count(len(group), "play"), count(new, "new best") if new else "", f"average {average(group)}"]
        note = ", ".join(f for f in figures if f) if wide > 2 else figures[0]
        if keyed is None and at == 0:
            note = ", ".join(n for n in (note, "times in JST") if n)
        sheets += (f'<div class="sc-sheet" style="grid-column:span {wide * 56 // (_ACROSS - (shared > 1))}">'
                   + panel(f"{colour} run sc-day", date(label, wide > 1), f'<div class="tracks" style="--across:{wide}">{body}</div>', note)
                   + "</div>")
    days_tally = ("".join(f"<span>{mark('plays')}{len(group)} on {_esc(date(label, False))}</span>" for label, group in days[:6])
                  + (f"<span>+{len(days) - 6} more days</span>" if len(days) > 6 else ""))
    banner = (f'<div class="banner">{stats([("Days", str(len(days))), ("Plays", str(len(plays))), ("Average", average(plays))])}'
              f'<div class="tally"><span>{mark("pb")}{pbs}</span><span>{mark("best50")}{sum(1 for p in plays if p.get("in_b50"))}</span>{days_tally}</div>'
              f'<div class="tally">{_tally(plays)}</div></div>')
    body = banner + f'<div class="sc-days">{sheets}</div>' if plays else '<p class="sc-empty">No recent plays yet.</p>'
    return _image("Recent plays", player_name, avatar_b64, rating_plate(rating), "rating", body, date_text)


def level_image_html(rows: Sequence[Dict[str, Any]], level_label: str, sort_label: str, player_name: str,
                     rating: int, avatar_b64: str, cover_html: CoverFn, total: int, played: int,
                     start: int = 1, date_text: str = "", page: int = 1, pages: int = 1) -> str:
    """One page of a level as a shelf: a dozen tickets stood on end, six across, the row's number on each stub.

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
    :param page: Which page this is, from 1.
    :type page: int
    :param pages: How many pages the level has.
    :type pages: int
    :rtype: str
    """
    def tag(number: int, r: Dict[str, Any]) -> str:
        label, ink = tier(r["difficulty"])
        if r.get("unplayed"):
            marks, score = mark("unknown"), "<b>never played</b>"
        else:
            marks, score = rank_mark(r["rank"]) + lamp_marks(r.get("fc"), r.get("fs")), f'<b>{r["accuracy"]:.4f}%</b>'
        return (f'<div class="sc-tag{" sc-unplayed" if r.get("unplayed") else ""}" style="--tier:{ink};">'
                f'<div class="sc-tag-stub"><b>{number}</b>{tier_mark(r["difficulty"])}<span>{label} {_esc(r["level"])}<small>{r["constant"]:.1f}</small></span>'
                f'<strong>{"" if r.get("unplayed") else r["rating"]}</strong></div>'
                f'<div class="sc-tag-paper"><p class="sc-tag-name"><b>{_esc(r["title"])}</b>{kind_mark(r["chart_type"])}</p>'
                f'{cover_html(r.get("cover", ""), "sc-tag-jacket")}<p class="sc-tag-score">{score}</p><div class="sc-tag-marks">{marks}</div>'
                f'<p class="sc-tag-note">{_esc(r.get("note")) or "&nbsp;"}</p></div></div>')

    scored = [r for r in rows if not r.get("unplayed")]
    shelf = "".join(tag(number, r) for number, r in enumerate(rows, start))
    spare = 6 * (1 if len(rows) <= 6 else 2) - len(rows)
    if spare:
        shelf += (f'<div class="sc-key" style="grid-column:span {spare}"><p><b>Stub:</b> row, difficulty, level and constant, rating</p>'
                  f'<p>{mark("unknown")}Never played</p><p>The last of {total} charts at this level</p></div>')
    figures = [("Charts", str(total)), ("Played", str(played)), ("Never played", str(total - played)), ("Page", f"{page} / {pages}")]
    if scored:
        figures.append(("Average", f"{sum(r['accuracy'] for r in scored) / len(scored):.4f}%"))
    banner = f'<div class="banner">{stats(figures)}' + (f'<div class="tally">{_tally(scored)}</div>' if scored else "") + "</div>"
    counted = f"{start}–{start + len(rows) - 1} of {total}"
    body = (banner + panel("cyan run sc-day", sort_label[:1].upper() + sort_label[1:], f'<div class="sc-shelf">{shelf}</div>', counted)
            if rows else '<p class="sc-empty">No charts on this page.</p>')
    return _image(f"Level {level_label}", player_name, avatar_b64, rating_plate(rating), "rating", body, date_text)


STAR_STEPS = ((0.85, 1), (0.90, 2), (0.93, 3), (0.95, 4), (0.97, 5))


def stars_for(ratio: float) -> int:
    stars = 0
    for threshold, count in STAR_STEPS:
        if ratio >= threshold:
            stars = count
    return stars


# brand/emoji/svg/dxstar.svg, drawn inline: an image is one HTML string with no files beside it
_STAR_ON = (f'<svg class="dxstar" viewBox="0 0 128 128"><polygon class="halo" points="{STAR_POINTS}"/>'
            f'<polygon points="{STAR_POINTS}"/><circle cx="64" cy="70" r="8"/></svg>')
_STAR_OFF = f'<svg class="dxstar off" viewBox="0 0 128 128"><polygon points="{STAR_POINTS}"/></svg>'


def star_marks(stars: int) -> str:
    """Five DX stars for an image: the earned ones in the dxstar mark, the rest as dim outlines.

    :param stars: How many of the five are earned.
    :type stars: int
    :rtype: str
    """
    stars = max(0, min(5, int(stars)))
    return _STAR_ON * stars + _STAR_OFF * (5 - stars)


def dxscore_image_html(tiles: Dict[int, int], rows: Sequence[Dict[str, Any]], player_name: str,
                       avatar_b64: str, cover_html: CoverFn, average: float, date_text: str = "") -> str:
    floors = {count: threshold for threshold, count in STAR_STEPS}
    total = sum(tiles.values())
    stars = "".join(
        f'<span class="sc-rung"><span class="stars">{star_marks(s)}</span><b>{tiles.get(s, 0)}</b>'
        f'<small>{f"{floors[s] * 100:.0f}%+" if s else f"under {floors[1] * 100:.0f}%"}</small></span>'
        for s in (5, 4, 3, 2, 1, 0)
    )
    banner = (f'<div class="banner">{stats([("Charts", str(total)), ("Average", f"{average * 100:.1f}%")])}'
              f'<div class="tally sc-starcount">{stars}</div></div>')

    def ticket(number: int, r: Dict[str, Any]) -> str:
        label, ink = tier(r["difficulty"])
        return _ticket(_stub(str(number), r, r["short"]), ink, r, cover_html,
                       f'<b>{r["dx"]:,}</b><small>of {r["max_dx"]:,}</small><small>{r["ratio"] * 100:.2f}%</small><small>{label} {_esc(r["level"])}</small>',
                       f'<span class="sc-next"><span class="stars">{star_marks(r["stars"])}</span>'
                       f'<span class="stars">{star_marks(min(5, r["stars"] + 1))}</span></span>', shape=" sc-near")

    tickets = "".join(ticket(number, r) for number, r in enumerate(rows, 1))
    spare = -len(rows) % _ACROSS
    if rows and spare:
        tickets += (f'<div class="sc-key" style="grid-column:span {spare}"><p><b>Stub:</b> row, difficulty, constant, points to the next star</p>'
                    f'<p><span class="stars">{star_marks(3)}</span><b>Stars:</b> now over next</p><p>Max DX score is notes × 3</p></div>')
    body = banner + (panel("gold run sc-day", "Closest to the next star", f'<div class="tracks" style="--across:{_ACROSS}">{tickets}</div>', "points short of the next star" if spare else "stub: row, difficulty, constant, points to the next star")
                     if rows else '<p class="sc-empty">Every chart is already five stars.</p>')
    return _image("DX score", player_name, avatar_b64, str(tiles.get(5, 0)), "five-star charts", body, date_text)

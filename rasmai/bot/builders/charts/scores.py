from typing import Any, Dict, List, Optional, Tuple
import math
import discord
from rasmai.bot.ui import palette

from rasmai.engine.analysis import rank_for
from rasmai.bot.state.cache import CachedAnalysis
from rasmai.bot.ui.formatting import TIER_SHORT, _fit, add_link_run, chart_link, level_text, message_files, today
from rasmai.bot.state.snapshots import chart_key
from rasmai.images.render import cover_html_factory
from rasmai.bot.ui.emoji import dx_stars
from rasmai.images.pages import STAR_STEPS, best50_image_html, dxscore_image_html, stars_for
from rasmai.bot.builders.charts.index import songs_by_key
from rasmai.bot.ui.views import PagedView, from_cache

PAGE = 8          # two-line entries per field: eight sit inside Discord's field cap
DRAWN = 30        # rows of /dxscore's table in the image


def dxscore_rows(cached: CachedAnalysis) -> Tuple[Dict[int, int], List[Dict[str, Any]], float]:
    a = cached.analyzer
    tiles: Dict[int, int] = {s: 0 for s in range(6)}
    rows: List[Dict[str, Any]] = []
    ratios: List[float] = []
    for song in a.songs:
        key = chart_key(song)
        if key[2] == "utage":
            continue
        ref = a.chart_index.get(key)
        if ref is None or ref.notes <= 0:
            continue
        max_dx = ref.notes * 3
        dx = int(song.dx_score or 0)
        if dx <= 0:
            continue
        ratio = min(1.0, dx / max_dx)
        ratios.append(ratio)
        stars = stars_for(ratio)
        tiles[stars] += 1
        if stars < 5:
            threshold = next(t for t, count in STAR_STEPS if count == stars + 1)
            rows.append({
                "title": song.name, "difficulty": key[2], "chart_type": key[1], "level": song.level,
                "constant": float(song.difficulty or 0),
                "dx": dx, "max_dx": max_dx, "ratio": ratio, "stars": stars,
                "short": max(1, math.ceil(threshold * max_dx) - dx), "cover": song.cover_url or ref.cover,
            })
    rows.sort(key=lambda r: (r["short"], -r["ratio"]))
    average = sum(ratios) / len(ratios) if ratios else 0.0
    return tiles, rows, average


async def build_dxscore(cached: CachedAnalysis, owner_id: Optional[int] = None, page: int = 0
                        ) -> Tuple[discord.Embed, List[discord.File], Optional[discord.ui.View]]:
    from rasmai.bot.builders.results import _image
    a = cached.analyzer
    player = a.player
    tiles, rows, average = dxscore_rows(cached)
    rows = rows[:PAGE * 6]          # the closest to their next star; the rest are not close
    pages = max(1, math.ceil(len(rows) / PAGE))
    page = max(0, min(page, pages - 1))
    shot = None
    if rows or any(tiles.values()):
        shot = await _image(cached, "dxscore", lambda: dxscore_image_html(
            tiles, rows[:DRAWN], player.name, cached.start_rating, player.avatar_base64,
            cover_html_factory(a.jacket_path), average, date_text=today(),
        ))
    files, avatar_url = message_files(player, shot, "rasmai-dxscore.png")
    drawn = shot is not None
    embed = discord.Embed(title="DX score", color=palette.LOOKUP)
    embed.set_author(name=player.name, icon_url=avatar_url)
    total = sum(tiles.values())
    if not drawn:
        embed.description = (f"**{tiles[5]}** five-star charts of **{total}** · average **{average * 100:.1f}%** of max DX score\n"
                             f"-# {dx_stars(5)} 97% · {dx_stars(4)} 95% · {dx_stars(3)} 93% · {dx_stars(2)} 90% · {dx_stars(1)} 85%")
        embed.add_field(name="By star", value="\n".join(f"{dx_stars(s)} **{tiles[s]}**" for s in (5, 4, 3, 2, 1, 0)), inline=True)

    def line(index: int, r: Dict[str, Any]) -> str:
        name = f"{chart_link(r['title'], r['chart_type'], r['difficulty'], r.get('cover', ''))} {TIER_SHORT.get(r['difficulty'], '')} {level_text(r['level'], r.get('constant'))}"
        figures = f"{r['dx']:,}/{r['max_dx']:,} · {dx_stars(r['stars'])} → {dx_stars(r['stars'] + 1)}"
        if not drawn:
            return f"`{r['short']:>4}` {name}\n-# {figures}"
        # numbered as the image's table numbers them; past its last row a line still carries its figures, the stars as digits
        # because five star emoji a side would not leave room for the page
        return f"`{index:>2}` {name}" + (f"\n-# {r['short']} short · {r['dx']:,}/{r['max_dx']:,} · {r['stars']}★ → {r['stars'] + 1}★" if index > DRAWN else "")

    lines = [line(index, r) for index, r in enumerate(rows[page * PAGE:(page + 1) * PAGE], page * PAGE + 1)]
    name = ("Closest to the next star" if drawn else "Points short of the next star") + (f" · {page * PAGE + 1}-{min((page + 1) * PAGE, len(rows))} of {len(rows)}" if len(rows) > PAGE else "")
    if drawn and lines and page * PAGE + len(lines) <= DRAWN:
        add_link_run(embed, name, lines)
    else:
        # lines with figures are twice the length, so a page of them is two fields
        halves = [lines[:PAGE // 2], lines[PAGE // 2:]] if drawn and lines else [lines]
        for at, half in enumerate([h for h in halves if h] or [[]]):
            embed.add_field(name="\u200b" if at else name, value=_fit(half) if half else "Every chart is already five stars.", inline=True)
    embed.set_footer(text="max DX score = notes × 3, from otoge-db" + (f" · page {page + 1}/{pages}" if pages > 1 else "") + " · closest thirty in the image, forty-eight in the text")
    view = PagedView(owner_id, page, pages, from_cache(owner_id, lambda c, p: build_dxscore(c, owner_id, p))) if owner_id is not None and pages > 1 else None
    return embed, files, view


def best50_entries(cached: CachedAnalysis) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    a = cached.analyzer
    by_key = songs_by_key(cached)

    def entries(pool) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for key, rating in pool.ranked[:pool.size]:
            song = by_key.get(key)
            ref = a.chart_index.get(key)
            if song is None:
                continue
            out.append({
                "title": song.name, "difficulty": key[2], "chart_type": key[1], "level": song.level,
                "constant": float(song.difficulty or 0), "accuracy": float(song.accuracy or 0),
                "rank": song.current_rank or rank_for(float(song.accuracy or 0)), "rating": int(rating),
                "fc": song.fc_status, "fs": song.fs_status, "cover": song.cover_url or (ref.cover if ref else ""),
                "dx": int(song.dx_score or 0), "max_dx": ref.notes * 3 if ref and ref.notes > 0 else 0,
            })
        return out

    if a.best50 is None:
        return [], []
    return entries(a.best50.new_pool), entries(a.best50.old_pool)


async def build_b50(cached: CachedAnalysis, owner_id: Optional[int] = None, page: int = 0
                    ) -> Tuple[discord.Embed, List[discord.File], Optional[discord.ui.View]]:
    from rasmai.bot.builders.results import _image
    a = cached.analyzer
    player = a.player
    new_entries, old_entries = best50_entries(cached)
    b50 = a.best50
    pages = max(1, math.ceil(max(len(new_entries), len(old_entries)) / PAGE))
    page = max(0, min(page, pages - 1))
    shot = await _image(cached, "b50", lambda: best50_image_html(
        new_entries, old_entries, player.name, cached.start_rating, player.avatar_base64,
        cover_html_factory(a.jacket_path), b50.new_pool.total, b50.old_pool.total, date_text=today(),
    ))
    files, avatar_url = message_files(player, shot, "rasmai-b50.png")
    drawn = shot is not None
    embed = discord.Embed(title=f"Best 50 · {b50.total}", color=palette.RATING)
    embed.set_author(name=player.name, icon_url=avatar_url)
    if not drawn:
        embed.description = (f"**{b50.new_pool.total}** from {len(new_entries)} current-version charts · "
                             f"**{b50.old_pool.total}** from {len(old_entries)} older charts\n"
                             f"-# cutoffs {b50.new_pool.cutoff} / {b50.old_pool.cutoff}"
                             + (f" · {b50.new_pool.headroom() + b50.old_pool.headroom()} slots open" if b50.new_pool.headroom() + b50.old_pool.headroom() else ""))

    start = page * PAGE

    def lines(entries: List[Dict[str, Any]]) -> str:
        # the image's cards carry each chart's figures under the same number
        return _fit([
            f"`{i:>2}` {chart_link(e['title'], e['chart_type'], e['difficulty'], e.get('cover', ''))} {TIER_SHORT.get(e['difficulty'], '')} {level_text(e['level'], e.get('constant'))}"
            + ("" if drawn else f"\n-# {e['accuracy']:.4f} {e['rank']} · **{e['rating']}**")
            for i, e in enumerate(entries[start:start + PAGE], start + 1)
        ]) if len(entries) > start else "-# no more on this page"

    def span(entries: List[Dict[str, Any]]) -> str:
        return f" · {start + 1}-{min(start + PAGE, len(entries))} of {len(entries)}" if len(entries) > PAGE and len(entries) > start else ""

    for name, entries in (("New version", new_entries), ("Older versions", old_entries)):
        if drawn:
            add_link_run(embed, name + span(entries), lines(entries).split("\n"))
        else:
            embed.add_field(name=name + span(entries), value=lines(entries), inline=True)
    embed.set_footer(text=(f"page {page + 1}/{pages} · " if pages > 1 else "") + "all 50 in the image")
    view = PagedView(owner_id, page, pages, from_cache(owner_id, lambda c, p: build_b50(c, owner_id, p))) if owner_id is not None and pages > 1 else None
    return embed, files, view

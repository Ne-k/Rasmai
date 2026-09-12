from typing import Any, Dict, List, Optional, Sequence
import logging

from rasmai.engine.analysis import ChartRef, rank_for
from rasmai.bot.state.cache import CachedAnalysis
from rasmai.bot.ui.formatting import today
from rasmai.bot.state.snapshots import chart_key
from rasmai.bot.core import try_render
from rasmai.images.cards import song_card_html
from rasmai.images.render import cover_html_factory
from rasmai.images.pages import star_text, stars_for
from rasmai.bot.builders.charts.index import song_for_chart, songs_by_loose_key
from rasmai.bot.builders.charts.ladder import _cutoffs, _version_label, entry_note

logger = logging.getLogger(__name__)


def _chart_rows(cached: Optional[CachedAnalysis], refs: List[ChartRef]) -> List[Dict[str, Any]]:
    """One row per chart of a song: the chart, and the player's score on it when there is one.

    :param cached: The player's analysis, held in memory.
    :type cached: Optional[CachedAnalysis]
    :param refs: Every chart the song has.
    :type refs: List[ChartRef]
    :rtype: List[Dict[str, Any]]
    """
    loose_map = songs_by_loose_key(cached) if cached else {}
    rows: List[Dict[str, Any]] = []
    for ref in refs:
        song = song_for_chart(loose_map, ref)
        row: Dict[str, Any] = {
            "difficulty": ref.difficulty, "level": ref.level, "chart_type": ref.chart_type, "constant": ref.constant,
            "played": song is not None, "note": entry_note(cached, ref, song) if cached else "",
        }
        if song is not None:
            dx = int(song.dx_score or 0)
            max_dx = ref.notes * 3 if ref.notes else 0
            row.update({
                "accuracy": float(song.accuracy or 0), "rank": song.current_rank or rank_for(float(song.accuracy or 0)),
                "rating": int(song.rating or 0), "fc": song.fc_status, "fs": song.fs_status,
                "dx": dx, "max_dx": max_dx, "stars": stars_for(dx / max_dx) if max_dx and dx else 0,
                "plays": max(0, cached.analyzer.play_counts.get(chart_key(song), 0)) if cached else 0,
            })
        rows.append(row)
    return rows


def _score_lines(row: Dict[str, Any]) -> str:
    """The per-chart block of the /chart embed.

    :param row: One row of the table.
    :type row: Dict[str, Any]
    :rtype: str
    """
    if not row["played"]:
        return "never played" + (f"\n-# {row['note']}" if row.get("note") else "")
    lines = [f"**{row['accuracy']:.4f}%** {row['rank']} · rating **{row['rating']}**"]
    extras = []
    lamp = " · ".join(b for b in (str(row.get("fc") or "").upper(), str(row.get("fs") or "").upper()) if b and b != "NONE")
    if lamp:
        extras.append(lamp)
    if row.get("plays"):
        extras.append(f"{row['plays']} play{'s' if row['plays'] != 1 else ''}")
    if row.get("max_dx"):
        extras.append(f"DX {row['dx']:,}/{row['max_dx']:,} {star_text(row['stars'])}")
    if extras:
        lines.append("-# " + " · ".join(extras))
    if row.get("note"):
        lines.append(f"-# {row['note']}")
    return "\n".join(lines)


async def _song_card(cached: Optional[CachedAnalysis], title: str, refs: List[ChartRef], rows: List[Dict[str, Any]],
                     highlight: Optional[str] = None, ladder: Optional[List[Dict[str, Any]]] = None,
                     ladder_label: str = "", forecast: str = "", eyebrow: str = "Chart lookup",
                     version: str = "", facts: Sequence[str] = ()) -> Optional[bytes]:
    first = refs[0] if refs else None
    if first is None:
        return None
    jacket_path = cached.analyzer.jacket_path if cached else "otoge_cache/jackets/"
    player = cached.analyzer.player if cached else None
    html = song_card_html(
        title, first.artist, first.genre, version or _version_label(cached, first), first.cover, cover_html_factory(jacket_path),
        rows, player.name if player else "", cached.start_rating if cached else 0,
        player.avatar_base64 if player else "", _cutoffs(cached), date_text=today(), highlight=highlight,
        ladder=ladder or (), ladder_label=ladder_label, forecast=forecast, eyebrow=eyebrow, facts=facts,
    )
    key = f"song:{title}:{highlight or ''}:{'l' if ladder else ''}:{eyebrow}"
    if cached is None:
        return await try_render(html)
    if key not in cached.images:
        cached.images[key] = await try_render(html)
    return cached.images[key]

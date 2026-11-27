from datetime import datetime
from html import escape as html_escape
from typing import List, Dict, Optional, Any
import logging

from rasmai.config import site_label
from rasmai.engine import analysis
from rasmai.images.classic.markup import styleimage
from rasmai.images.render import _cover_markup
from rasmai.images.classic.posters import rating_plate
from rasmai.storage.models import Recommendation

logger = logging.getLogger(__name__)


DIFFICULTY_STYLES = {
    "basic":    ("BASIC",     "#4bb85f", "#151512"),
    "advanced": ("ADVANCED",  "#e0a020", "#151512"),
    "expert":   ("EXPERT",    "#e2455a", "#151512"),
    "master":   ("MASTER",    "#a266e8", "#151512"),
    "remaster": ("Re:MASTER", "#cbbbe8", "#151512"),
    "utage":    ("UTAGE",     "#e2609a", "#151512"),
}


def get_difficulty_style(difficulty_type: str) -> tuple:
    """Label, ink and wash for a chart's difficulty tier.

    :param difficulty_type: The difficulty tier, such as ``"master"``.
    :type difficulty_type: str
    :rtype: tuple
    """
    return DIFFICULTY_STYLES.get(str(difficulty_type).strip().lower(), DIFFICULTY_STYLES["master"])


def _plays_text(plays: int) -> str:
    if plays <= 0:
        return "plays unknown"
    return f"{plays} play" if plays == 1 else f"{plays} plays"


def generate_poster_html(recommendations: List[Recommendation], player_name: str, player_rating: int,
                         fc: int, fc_plus: int, clears: int, avatar_base64: str = "",
                         jacket_path: str = "otoge_cache/jackets/",
                         plan: Optional["analysis.Plan"] = None, image_gain: Optional[int] = None, scope: str = "",
                         summary: Optional[Dict[str, Any]] = None, counts: str = "") -> str:
    movers = [r for r in recommendations if r.category not in ("near", "try")]
    scope_html = f" &middot; {scope}" if scope else ""       # our own wording ("level 13+"), never the player's text
    near = [r for r in recommendations if r.category == "near"]

    # gains overlap once several picks land, so the headline is the simulated total when the caller has it
    total_gain = image_gain if image_gain is not None else sum(r.potential_gain for r in movers)
    featured = movers[:3]
    listed = movers[3:15]
    near = near[:8]

    avatar_html = (
        f'<img src="data:image/png;base64,{avatar_base64}" class="avatar" />'
        if avatar_base64 else '<div class="avatar no-cover"></div>'
    )

    featured_html = ""
    for position, rec in enumerate(featured, 1):
        label, ink, wash = get_difficulty_style(rec.difficulty_type)
        fresh = ' <span class="new-flag">New</span>' if rec.is_unplayed else ""
        hero_class = "hero fresh" if rec.is_unplayed else "hero"
        featured_html += f"""
        <article class="{hero_class}" style="--tier:{ink}; --wash:{wash};">
            <div class="hero-rank">{position}</div>
            {_cover_markup(rec, jacket_path, "hero-cover")}
            <div class="hero-body">
                <div class="tier">{label} <span class="lv">{html_escape(rec.level)} &middot; {rec.difficulty:.1f}</span></div>
                <h2 class="hero-title">{html_escape(rec.song)}{fresh}</h2>
                <div class="hero-move">
                    <span class="from">{rec.current_accuracy:.2f}%</span>
                    <span class="arrow">&rarr;</span>
                    <span class="to">{rec.target_accuracy:.2f}%</span>
                    <span class="ranks">{rec.current_rank} &rarr; {rec.target_rank}</span>
                </div>
                <div class="hero-meta">{"never played" if rec.is_unplayed else _plays_text(rec.plays)} &middot; you usually score ~{rec.expected:.1f}% here</div>
            </div>
            <div class="hero-gain">
                <div class="plus">+{rec.potential_gain}</div>
                <div class="unit">rating</div>
                <div class="odds">{rec.feasibility * 100:.0f}% likely</div>
            </div>
        </article>"""

    rows_html = ""
    for position, rec in enumerate(listed, len(featured) + 1):
        label, ink, wash = get_difficulty_style(rec.difficulty_type)
        fresh = ' <span class="new-flag">New</span>' if rec.is_unplayed else ""
        row_class = "fresh" if rec.is_unplayed else ""
        rows_html += f"""
        <tr class="{row_class}" style="--tier:{ink};">
            <td class="c-rank">{position}</td>
            <td class="c-cover">{_cover_markup(rec, jacket_path, "row-cover")}</td>
            <td class="c-song">
                <span class="row-title">{html_escape(rec.song)}{fresh}</span>
                <span class="row-tier">{label} {html_escape(rec.level)} &middot; {rec.difficulty:.1f}</span>
                <span class="row-meta">{"never played" if rec.is_unplayed else _plays_text(rec.plays)}</span>
            </td>
            <td class="c-acc">{rec.current_accuracy:.2f} <span class="arrow">&rarr;</span> <b>{rec.target_accuracy:.2f}</b></td>
            <td class="c-rank-move">{rec.current_rank} <span class="arrow">&rarr;</span> <b>{rec.target_rank}</b></td>
            <td class="c-odds">{rec.feasibility * 100:.0f}%</td>
            <td class="c-gain">+{rec.potential_gain}</td>
        </tr>"""

    road_html = ""
    if plan and plan.steps:
        road_rows = ""
        for position, step in enumerate(plan.steps[:16], 1):
            option = step.option
            label, ink, _wash = get_difficulty_style(option.difficulty_type)
            stub = Recommendation(
                song=option.title, difficulty=option.constant, current_accuracy=option.current_accuracy,
                target_accuracy=option.target_accuracy, current_rating=0, target_rating=option.target_rating,
                potential_gain=step.gain, max_possible_gain=step.gain, current_rank=option.current_rank,
                target_rank=option.target_rank, fc_status="", is_new=option.is_new, priority_score=0,
                effort_score=0, efficiency=0, level=option.level,
                cover_url=option.cover.split("/")[-1].split("?")[0] if option.cover else "",
            )
            now = "never played" if option.is_unplayed else f"{option.current_accuracy:.2f}"
            road_rows += f"""
            <tr class="{'fresh' if option.is_unplayed else ''}" style="--tier:{ink};">
                <td class="c-rank">{position}</td>
                <td class="c-cover">{_cover_markup(stub, jacket_path, "row-cover")}</td>
                <td class="c-song">
                    <span class="row-title">{html_escape(option.title)}{' <span class="new-flag">New</span>' if option.is_unplayed else ''}</span>
                    <span class="row-tier">{label} {html_escape(option.level)} &middot; {option.constant:.1f}</span>
                    <span class="row-meta">{"never played" if option.is_unplayed else _plays_text(option.plays)}</span>
                </td>
                <td class="c-acc">{now} <span class="arrow">&rarr;</span> <b>{option.target_accuracy:.2f}</b></td>
                <td class="c-rank-move">{option.current_rank} <span class="arrow">&rarr;</span> <b>{option.target_rank}</b></td>
                <td class="c-odds">{option.feasibility * 100:.0f}%</td>
                <td class="c-gain">+{step.gain}</td>
                <td class="c-cum">{step.cumulative}</td>
            </tr>"""
        verdict = (
            f"covers the full +{plan.needed}" if plan.reached
            else f"+{plan.total} of the +{plan.needed} needed &middot; {plan.shortfall} short"
        )
        fresh = plan.gap_steps
        notes = [f"worth about +{plan.expected_gain:.0f} by odds"]
        if fresh:
            notes.append(f"{len(fresh)} never played, worth +{plan.gap_gain}")
        elif not plan.reached:
            notes.append("no unplayed chart would clear your best 50 on a first pass")
        road_html = f"""
        <section class="road">
            <div class="road-head">
                <div>
                    <div class="section-label">Road to {plan.goal_rating}</div>
                    <div class="road-verdict">{verdict}</div>
                    <div class="road-note">{" &middot; ".join(notes)}</div>
                </div>
                <div class="road-stretch">
                    <div class="value">{plan.average_stretch:+.1f}%</div>
                    <div class="caption">above your usual score</div>
                </div>
            </div>
            <table>
                <thead><tr>
                    <th></th><th></th><th>Chart</th><th>Achievement</th><th>Rank</th><th>Odds</th>
                    <th style="text-align:right">Gain</th><th style="text-align:right">Total</th>
                </tr></thead>
                <tbody>{road_rows}</tbody>
            </table>
        </section>"""

    near_html = ""
    if near:
        items = "".join(
            f'<li><span class="near-name">{html_escape(r.song)}</span>'
            f'<span class="near-need">{r.required_accuracy:.2f}%</span></li>'
            for r in near
        )
        near_html = f"""
        <section class="near">
            <h3>Just outside your best 50</h3>
            <p>These pay nothing yet. Reach the score shown and they start counting.</p>
            <ul>{items}</ul>
        </section>"""

    counters = "".join(
        f'<div class="counter"><dt>{label}</dt><dd>{value}</dd></div>'
        for label, value in (("FC", fc), ("FC+", fc_plus), ("Clears", clears))
        if value
    )

    tiles_html = ""
    if summary:
        profile, best50 = summary.get("profile", {}), summary.get("best50", {})
        open_slots = best50.get("newSlotsOpen", 0) + best50.get("oldSlotsOpen", 0)
        tiles = (
            ("Style", html_escape(str(profile.get("style", "unknown")).title()),
             f"{profile.get('fcRate', 0) * 100:.0f}% FC &middot; {profile.get('apRate', 0) * 100:.0f}% AP &middot; "
             f"{profile.get('dxScoreRate', 0) * 100:.0f}% DX score<br>leans {html_escape(str(profile.get('favoriteChartType', '?')).upper())}"),
            ("Levels", f"{profile.get('comfortConstant', 0)}<small>comfort</small>",
             f"reach {profile.get('reachConstant', 0)} &middot; hardest S {profile.get('hardestS', 0)}<br>"
             f"{profile.get('expectedAt13', 0)}% on 13s &middot; {profile.get('expectedAt14', 0)}% on 14s"),
            ("Best 50", str(best50.get("total", 0)),
             f"{best50.get('newTotal', 0)} new + {best50.get('oldTotal', 0)} old<br>cutoffs {best50.get('newCutoff', 0)} / {best50.get('oldCutoff', 0)}"
             + (f" &middot; {open_slots} slots empty" if open_slots else "")),
        )
        tiles_html = '<section class="tiles">' + "".join(
            f'<div class="tile"><div class="k">{label}</div><div class="v">{value}</div><div class="s">{detail}</div></div>'
            for label, value, detail in tiles) + "</section>"

    poster_css = styleimage()
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<style>{poster_css}</style>
</head>
<body>
<div class="image">
  <header>
    {avatar_html}
    <div class="who">
      <div class="eyebrow">What to play next</div>
      <h1>{html_escape(player_name)}</h1>
    </div>
    <div class="counters">
      <div class="counter"><dt>Rating</dt><dd>{rating_plate(player_rating, small=True)}</dd></div>
      {counters}
    </div>
    <div class="headline-figure">
      <div class="value">+{total_gain}</div>
      <div class="caption">rating on this image</div>
    </div>
  </header>

  <div class="columns">
  <div class="col">
  <div class="section-label">Grind these &middot; {len(movers)} charts &middot; +{total_gain}{scope_html}</div>
  <div class="heroes">{featured_html}</div>

  <table>
    <thead>
      <tr>
        <th></th><th></th><th>Chart</th><th>Achievement</th><th>Rank</th><th>Odds</th>
        <th style="text-align:right">Gain</th>
      </tr>
    </thead>
    <tbody>{rows_html}</tbody>
  </table>

  </div>
  <div class="col">
  {road_html}
  {tiles_html}
  </div>
  </div>

  {near_html}

  <footer>
    <span>Rasmai &middot; {html_escape(site_label())} &middot; maimai DX{" &middot; " + html_escape(counts) if counts else ""}</span>
    <span>{datetime.now().strftime('%d %B %Y')}</span>
  </footer>
</div>
</body>
</html>"""

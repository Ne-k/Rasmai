from datetime import datetime
from html import escape as html_escape
from pathlib import Path
from playwright.async_api import async_playwright
from typing import List, Dict, Optional, Any
import asyncio
import base64
import hashlib
import os
import re
import requests
import logging

from rasmai.config import BROWSER_USER_AGENT, site_label
from rasmai.engine import analysis
from rasmai.images.markup import styleimage
from rasmai.storage.models import Recommendation

logger = logging.getLogger(__name__)


def _load_local_jacket(cover_url: str, jacket_path: str) -> str:
    if not cover_url:
        return ""

    jacket_filename = cover_url
    if '/' in jacket_filename:
        jacket_filename = jacket_filename.split('/')[-1]
    if '?' in jacket_filename:
        jacket_filename = jacket_filename.split('?')[0]

    stem = Path(jacket_filename).stem
    possible_paths = [
        Path(jacket_path) / f"{stem}.webp",
        Path("otoge_cache/jackets") / f"{stem}.webp",
        Path(jacket_path) / jacket_filename,
        Path("otoge_cache/repo/maimai/jacket") / jacket_filename,
        Path("maimai/jacket") / jacket_filename,
        Path("jacket") / jacket_filename,
        Path(jacket_path) / f"{Path(jacket_filename).stem}.jpg",
        Path(jacket_path) / f"{Path(jacket_filename).stem}.png",
        Path("otoge_cache/repo/maimai/jacket") / f"{Path(jacket_filename).stem}.jpg",
        Path("otoge_cache/repo/maimai/jacket") / f"{Path(jacket_filename).stem}.png",
    ]

    for path in possible_paths:
        if path.exists():
            try:
                with open(path, 'rb') as f:
                    jacket_data = base64.b64encode(f.read()).decode('utf-8')
                    ext = path.suffix.lower()
                    content_type = {'.png': 'image/png', '.webp': 'image/webp'}.get(ext, 'image/jpeg')
                    return f'<img src="data:{content_type};base64,{jacket_data}" class="cover-img" />'
            except Exception as e:
                print(f"Error loading jacket from {path}: {e}")
                continue

    jacket_dir = Path(jacket_path)
    if jacket_dir.exists():
        for file in jacket_dir.glob("*"):
            if file.name.lower() == jacket_filename.lower():
                try:
                    with open(file, 'rb') as f:
                        jacket_data = base64.b64encode(f.read()).decode('utf-8')
                        ext = file.suffix.lower()
                        content_type = {'.png': 'image/png', '.webp': 'image/webp'}.get(ext, 'image/jpeg')
                        return f'<img src="data:{content_type};base64,{jacket_data}" class="cover-img" />'
                except Exception as e:
                    print(f"Error loading jacket from {file}: {e}")
                    break

    for base_path in ["otoge_cache/repo/maimai/jacket", "maimai/jacket", "jacket"]:
        jacket_dir = Path(base_path)
        if jacket_dir.exists():
            for ext in ['.png', '.jpg', '.jpeg']:
                test_path = jacket_dir / f"{Path(jacket_filename).stem}{ext}"
                if test_path.exists():
                    try:
                        with open(test_path, 'rb') as f:
                            jacket_data = base64.b64encode(f.read()).decode('utf-8')
                            content_type = {'.png': 'image/png', '.webp': 'image/webp'}.get(ext, 'image/jpeg')
                            return f'<img src="data:{content_type};base64,{jacket_data}" class="cover-img" />'
                    except Exception:
                        continue

    return ""


def download_cover_image(cover_url: str, cache_dir: str = "cover_cache") -> Optional[str]:
    if not cover_url:
        return None

    try:
        if cover_url.startswith('data:image'):
            return cover_url

        if not cover_url.startswith('http'):
            jacket_paths = [
                "otoge_cache/repo/maimai/jacket/",
                "maimai/jacket/",
                "jacket/"
            ]
            for jacket_path in jacket_paths:
                for ext in ['', '.png', '.jpg', '.jpeg']:
                    full_filename = cover_url + ext if ext else cover_url
                    jacket_result = _load_local_jacket(full_filename, jacket_path)
                    if jacket_result:
                        match = re.search(r'src="([^"]+)"', jacket_result)
                        if match:
                            return match.group(1)
            return None

        os.makedirs(cache_dir, exist_ok=True)

        url_hash = hashlib.md5(cover_url.encode()).hexdigest()
        cache_path = os.path.join(cache_dir, f"{url_hash}.jpg")

        if os.path.exists(cache_path):
            with open(cache_path, 'rb') as f:
                img_data = base64.b64encode(f.read()).decode('utf-8')
                return f"data:image/jpeg;base64,{img_data}"

        headers = {'User-Agent': BROWSER_USER_AGENT}

        response = requests.get(cover_url, headers=headers, timeout=10, stream=True)
        if response.status_code == 200:
            with open(cache_path, 'wb') as f:
                f.write(response.content)

            img_data = base64.b64encode(response.content).decode('utf-8')
            content_type = response.headers.get('content-type', 'image/jpeg')
            return f"data:{content_type};base64,{img_data}"

        return None

    except Exception as e:
        print(f"Error downloading cover image: {e}")
        return None


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


def _cover_markup(rec: "Recommendation", jacket_path: str, css_class: str) -> str:
    cover_html = ""
    if rec.cover_url and rec.cover_url.startswith("http"):
        cover_data = download_cover_image(rec.cover_url)
        cover_html = f'<img src="{cover_data}" class="{css_class}" />' if cover_data else _load_local_jacket(rec.cover_url, jacket_path)
    elif rec.cover_url:
        cover_html = _load_local_jacket(rec.cover_url, jacket_path)
    if cover_html:
        return cover_html.replace('class="cover-img"', f'class="{css_class}"')
    return f'<div class="{css_class} no-cover"></div>'


def cover_html_factory(jacket_path: str):
    """Cover renderer for posters.py: (cover_url, css_class) -> <img> or placeholder.

    :param jacket_path: Where the cached jackets live.
    :type jacket_path: str
    """
    def render(cover_url: str, css_class: str) -> str:
        stub = Recommendation(
            song="", difficulty=0, current_accuracy=0, target_accuracy=0, current_rating=0, target_rating=0,
            potential_gain=0, max_possible_gain=0, current_rank="", target_rank="", fc_status="", is_new=False,
            priority_score=0, effort_score=0, efficiency=0,
            cover_url=cover_url.split("/")[-1].split("?")[0] if cover_url else "",
        )
        return _cover_markup(stub, jacket_path, css_class)
    return render


def generate_poster_html(recommendations: List[Recommendation], player_name: str, player_rating: int,
                         fc: int, fc_plus: int, clears: int, avatar_base64: str = "",
                         jacket_path: str = "otoge_cache/jackets/",
                         plan: Optional["analysis.Plan"] = None, image_gain: Optional[int] = None, scope: str = "") -> str:
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
        road_html = f"""
        <section class="road">
            <div class="road-head">
                <div>
                    <div class="section-label">Road to {plan.goal_rating}</div>
                    <div class="road-verdict">{verdict}</div>
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
      <div class="counter"><dt>Rating</dt><dd>{player_rating}</dd></div>
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
  </div>
  </div>

  {near_html}

  <footer>
    <span>Rasmai &middot; {html_escape(site_label())} &middot; maimai DX &middot; best-50 aware</span>
    <span>{datetime.now().strftime('%d %B %Y')}</span>
  </footer>
</div>
</body>
</html>"""


CHROMIUM_ARGS = [
    "--no-sandbox", "--disable-setuid-sandbox", "--disable-gpu", "--disable-dev-shm-usage",
    "--no-zygote", "--disable-features=dbus",
]


_browser_state: Dict[str, Any] = {"playwright": None, "browser": None}


_browser_lock: Optional[asyncio.Lock] = None


async def _launch(playwright):
    """Headless shell first; if it dies on this host (emulation, seccomp), the full browser in single-process mode.

    :param playwright: The running Playwright driver.
    """
    try:
        return await playwright.chromium.launch(headless=True, args=CHROMIUM_ARGS)
    except Exception as first:
        logger.warning(f"Headless shell failed to start ({type(first).__name__}); retrying with the full browser")
        return await playwright.chromium.launch(
            headless=True, channel="chromium", args=CHROMIUM_ARGS + ["--single-process"]
        )


async def _get_browser():
    """The shared browser, started on first use. Launch costs ~0.6s, so it is kept for the life of the process."""
    global _browser_lock
    if _browser_lock is None:
        _browser_lock = asyncio.Lock()
    async with _browser_lock:
        browser = _browser_state["browser"]
        if browser is not None and browser.is_connected():
            return browser
        await _drop_browser()
        playwright = await async_playwright().start()
        browser = await _launch(playwright)
        _browser_state["playwright"], _browser_state["browser"] = playwright, browser
        return browser


async def _drop_browser() -> None:
    browser, playwright = _browser_state["browser"], _browser_state["playwright"]
    _browser_state["browser"] = _browser_state["playwright"] = None
    for closer in ((browser.close if browser else None), (playwright.stop if playwright else None)):
        if closer:
            try:
                await closer()
            except Exception:
                pass


async def render_html_to_image(html_content: str) -> bytes:
    browser = await _get_browser()
    context = None
    try:
        context = await browser.new_context(viewport={"width": 2400, "height": 400}, device_scale_factor=1)
        page = await context.new_page()
        await page.set_content(html_content, wait_until="networkidle")
        await page.wait_for_timeout(300)
        # the body sets its own width (2400 for posters, narrower for cards), so clip to it, not the viewport
        dimensions = await page.evaluate(
            "() => ({ width: document.body.offsetWidth || Math.max(document.body.scrollWidth, document.documentElement.scrollWidth),"
            " height: Math.max(document.body.scrollHeight, document.documentElement.scrollHeight) })"
        )
        return await page.screenshot(
            full_page=True,
            clip={"x": 0, "y": 0, "width": dimensions["width"], "height": dimensions["height"]},
        )
    except Exception:
        # A dead renderer would poison every later call; forget it so the next render relaunches.
        # A failure on one page while others are mid-render is not that.
        if not browser.is_connected():
            await _drop_browser()
        raise
    finally:
        if context is not None:
            try:
                await context.close()
            except Exception:
                pass

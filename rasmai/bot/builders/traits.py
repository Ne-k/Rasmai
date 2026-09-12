from typing import Any, Dict, List, Tuple

import discord

from rasmai.bot.state.cache import CachedAnalysis
from rasmai.bot.ui.formatting import TIER_SHORT, _fit, chart_link, message_files
from rasmai.engine import insights
from rasmai.engine.judgements import judgement_profile
from rasmai.storage.db import load_judgements
from rasmai.images.pages import traits_image_html
from rasmai.scraping.mai_notes import english_label

PRACTICE_TRAITS = 2       # weak patterns that get a practice list in the embed
PRACTICE_CHARTS = 3       # charts named for each


def _lines(items: List[Dict[str, Any]]) -> str:
    def basis(t: Dict[str, Any]) -> str:
        plays = int(t.get("plays") or 0)
        seen = f"over {t['count']} charts" + (f" and {plays} plays" if plays else "")
        return seen if t.get("verified") else f"{seen} · leaning, not confirmed"
    return _fit([f"`{float(t['offset']):+.2f}` **{t['label']}**\n-# {basis(t)}" for t in items])


def _practice_lines(axis: Dict[str, Any], rows: List[Dict[str, Any]]) -> List[str]:
    tag = str(axis["label"]).split(" (")[0]
    lines = [f"**{english_label(str(axis['label']))}** `{float(axis['offset']):+.2f}` · `/charts pattern:{tag}` for all of them"]
    for r in rows:
        short = TIER_SHORT.get(r["difficulty"], r["difficulty"][:3].upper())
        mine = f"you hold **{r['accuracy']:.4f}**" if r.get("accuracy") is not None else "not played yet"
        lines.append(f"{chart_link(r['title'], r['chart_type'], r['difficulty'], r.get('cover', ''))} {short} {r['chart_type'].upper()} {r['constant']:.1f} · {mine}")
    return lines


async def build_traits(cached: CachedAnalysis) -> Tuple[discord.Embed, List[discord.File], None]:
    """Where the player loses points and where they shine, what to practise, and what they play like everything else.

    Three tiers of trait are shown. Confirmed traits beat shuffled tags and keep their sign in
    both halves of the player's charts, and are the only ones the model acts on. Leaning traits
    point the same way on the player's data but have not passed that gate; they are shown as
    hints and marked. Even traits sit inside the noise: knowing that streams are not a weakness
    is information too.

    :param cached: The player's analysis, held in memory.
    :type cached: CachedAnalysis
    :rtype: Tuple[discord.Embed, List[discord.File], None]
    """
    from rasmai.bot.builders.results import _image
    a = cached.analyzer
    player = a.player
    profile = a.play_profile
    axes = list(getattr(profile, "trait_axes", []) or []) if profile else []
    sample = profile.sample_size if profile else 0
    confirmed = insights.notable(axes)
    leaning = insights.leaning(axes)
    even = insights.even(axes)
    shown = confirmed + leaning
    weak = sorted([t for t in shown if float(t["offset"]) < 0], key=lambda t: float(t["offset"]))[:6]
    strong = sorted([t for t in shown if float(t["offset"]) > 0], key=lambda t: -float(t["offset"]))[:6]

    shot = None
    wheel = insights.radar_axes(axes)
    if len(wheel) >= 3:
        shot = await _image(cached, "traits", lambda: traits_image_html(
            wheel, weak, strong, player.name, cached.start_rating, player.avatar_base64, sample, date_text=cached.extras.get("date", ""),
        ))
    files, avatar_url = message_files(player, shot, "rasmai-traits.png")
    embed = discord.Embed(title="Your traits", color=discord.Color.from_rgb(92, 211, 232))
    embed.set_author(name=player.name, icon_url=avatar_url)
    gate = ("confirmed = rarer than 1 in 50 under shuffled tags and the same sign in both halves of your charts, three splits over · "
            "leaning = points one way but has not passed that, so read it as a hint · only confirmed traits steer your picks")

    if not shown:
        largest = sorted(axes, key=lambda t: -abs(float(t["offset"])))[:4]
        embed.description = (f"Nothing separates from noise yet: **{len(axes)}** groups measured over **{sample}** scored charts, "
                             f"none far enough from your usual score to trust.\n-# {gate}\n-# more plays sharpen this: every recorded play counts, not only your bests")
        if largest:
            embed.add_field(name="Largest measured, none confirmed",
                            value=_fit([f"`{float(t['offset']):+.2f}` {t['label']}\n-# over {t['count']} charts · 1 in {max(1, round(1 / max(float(t['p']), 0.001)))} shuffles matched it"
                                        for t in largest]), inline=False)
    else:
        embed.description = (f"**{len(confirmed)}** confirmed · **{len(leaning)}** leaning · **{len(even)}** groups sit level with your usual score, "
                             f"from **{sample}** scored charts and every play recorded since you linked.\n-# {gate}")
        if weak:
            embed.add_field(name="Where you lose points", value=_lines(weak), inline=True)
        if strong:
            embed.add_field(name="Where you shine", value=_lines(strong), inline=True)

    practice: List[str] = []
    for axis in [t for t in weak if t["dimension"] == "pattern"][:PRACTICE_TRAITS]:
        rows = insights.practice_for(axis, a.chart_index, profile, a.songs, PRACTICE_CHARTS)
        if rows:
            practice.extend(_practice_lines(axis, rows))
    if practice:
        embed.add_field(name="Work on", value=_fit(practice), inline=False)
    if even:
        names = [english_label(str(t["label"])) for t in even[:8]]
        more = f" and {len(even) - 8} more" if len(even) > 8 else ""
        embed.add_field(name="Level with the rest",
                        value=f"{', '.join(names)}{more}.\n-# measured over enough charts and within ±{insights.TRAIT_LEAN_OFFSET:.1f} of your usual score: not a weakness, not a strength",
                        inline=False)
    judged = judgement_profile(load_judgements(cached.user_id))
    if judged:
        embed.add_field(name="Judgements, measured", value=_judgement_lines(judged), inline=False)
    embed.set_footer(text="points against your own curve · patterns and note mix via maiノーツ · hollow point on the wheel = leaning · middle ring = your own average")
    return embed, files, None


def _judgement_lines(judged: Dict[str, Any]) -> str:
    """What the judgement pages say: the note types the points go to, and whether the hits land early or late.

    :param judged: The judgement profile.
    :type judged: Dict[str, Any]
    :rtype: str
    """
    lines = []
    for t in sorted(judged["types"], key=lambda t: -t["lossShare"])[:2]:
        mark = " · **costs you most**" if t["kind"] == judged.get("weak") else ""
        lines.append(f"**{t['kind']}** {t['lossShare'] * 100:.0f}% of what you lose on {t['share'] * 100:.0f}% of the notes · {t['per100']:.2f} pts per 100{mark}")
    share = judged.get("lateShare")
    if share is not None:
        if share >= 0.6:
            lines.append(f"off-timing hits land **late {share * 100:.0f}%** of the time: a touch behind the beat")
        elif share <= 0.4:
            lines.append(f"off-timing hits land **early {(1 - share) * 100:.0f}%** of the time: a touch ahead of the beat")
        else:
            lines.append("off-timing hits split evenly between fast and late")
    lines.append(f"-# read from {judged['plays']} plays' judgement pages, not inferred from scores · every read collects the pages for new plays")
    return "\n".join(lines)

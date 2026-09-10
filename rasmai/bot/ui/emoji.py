from pathlib import Path
from typing import Dict, Optional
import hashlib
import json
import logging
import os

import discord

from rasmai.config import DATABASE_PATH

logger = logging.getLogger(__name__)


EMOJI_DIR = Path("brand/emoji/png")
UPLOADED_MARKER = DATABASE_PATH.parent / "emoji-uploaded.json"     # name -> hash of the image Discord has
EMOJI_ENABLED = os.getenv("MAIMAI_EMOJI", "true").lower() == "true"

RANKS = {
    "SSS+": "rank_sssp", "SSS": "rank_sss", "SS+": "rank_ssp", "SS": "rank_ss", "S+": "rank_sp", "S": "rank_s",
    "AAA": "rank_aaa", "AA": "rank_aa", "A": "rank_a",
}
COMBO = {"FC": "lamp_fc", "FC+": "lamp_fcp", "AP": "lamp_ap", "AP+": "lamp_app"}
SYNC = {"FS": "lamp_fs", "FS+": "lamp_fsp", "FDX": "lamp_fdx", "FDX+": "lamp_fdxp"}

_registry: Dict[str, str] = {}
_synced = False


def _uploaded_hashes() -> Dict[str, str]:
    try:
        return json.loads(UPLOADED_MARKER.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _remember_hashes(hashes: Dict[str, str]) -> None:
    try:
        UPLOADED_MARKER.parent.mkdir(parents=True, exist_ok=True)
        UPLOADED_MARKER.write_text(json.dumps(hashes, indent=1, sort_keys=True), encoding="utf-8")
    except OSError as error:
        logger.warning(f"Could not remember which emoji were uploaded: {error}")


async def sync_application_emojis(bot: discord.Client) -> None:
    """Upload the pack as application emoji, replace any whose image changed, and remember every id for `emoji()`.

    Application emoji work in every server and in DMs, for user installs too, so
    nothing here depends on where the bot was added. A redrawn image is noticed by its
    hash: the old emoji is deleted and the new one uploaded under the same name.

    :param bot: The Discord client.
    :type bot: discord.Client
    """
    global _synced
    if _synced or not EMOJI_ENABLED:
        return
    _synced = True
    try:
        existing = {item.name: item for item in await bot.fetch_application_emojis()}
    except Exception as error:
        logger.warning(f"Application emoji unavailable: {error}")
        return
    known = _uploaded_hashes()
    uploaded = replaced = 0
    for path in sorted(EMOJI_DIR.glob("*.png")) if EMOJI_DIR.is_dir() else []:
        name = path.stem
        image = path.read_bytes()
        digest = hashlib.sha1(image).hexdigest()
        if name in existing and known.get(name) == digest:
            continue
        if name in existing and name in known:
            # the image was redrawn since it was uploaded: swap it
            try:
                await existing[name].delete()
                replaced += 1
            except discord.HTTPException as error:
                logger.warning(f"Could not replace emoji {name}: {error}")
                continue
        elif name in existing:
            known[name] = digest           # uploaded before this marker existed; adopt it as current
            continue
        try:
            existing[name] = await bot.create_application_emoji(name=name, image=image)
            known[name] = digest
            uploaded += 1
        except discord.HTTPException as error:
            logger.warning(f"Could not upload emoji {name}: {error}")
    _remember_hashes(known)
    _registry.update({name: str(item) for name, item in existing.items()})
    logger.info(f"{len(_registry)} application emoji ready"
                + (f", {uploaded} uploaded" if uploaded else "") + (f", {replaced} replaced" if replaced else ""))


def emoji(name: str, fallback: str = "") -> str:
    """`<:name:id>` for a pack emoji, or the fallback when the pack is not loaded.

    :param name: The name to look up.
    :type name: str
    :param fallback: What to show when there is nothing.
    :type fallback: str
    :rtype: str
    """
    return _registry.get(name, fallback)


def partial(name: str) -> Optional[discord.PartialEmoji]:
    text = _registry.get(name)
    return discord.PartialEmoji.from_str(text) if text else None


def rank(rank_text: str, fallback: str = "") -> str:
    key = RANKS.get(str(rank_text or "").upper(), "rank_low" if rank_text else "")
    return emoji(key, fallback) if key else fallback


def lamps(fc: str, fs: str) -> str:
    """Combo and sync lamps as emoji, or their text when the pack is not loaded.

    :param fc: The full-combo lamp.
    :type fc: str
    :param fs: The sync lamp.
    :type fs: str
    :rtype: str
    """
    parts = []
    for value, table in ((fc, COMBO), (fs, SYNC)):
        value = str(value or "").upper()
        if value in table:
            parts.append(emoji(table[value], value))
        elif value and value != "NONE":
            parts.append(value)
    return " · ".join(parts)


def difficulty(difficulty_type: str) -> str:
    return emoji(f"diff_{str(difficulty_type or '').lower()}")


def chart_type(kind: str) -> str:
    return emoji(f"type_{str(kind or 'std').lower()}")

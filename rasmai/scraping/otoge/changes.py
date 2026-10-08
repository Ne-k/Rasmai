from pathlib import Path
from typing import Any, Dict, List, Tuple
import json
import logging
import pickle
import threading

import requests

from rasmai.config import OTOGE_WEBHOOK_URL

logger = logging.getLogger(__name__)

_TIERS = (("bas", "BASIC"), ("adv", "ADVANCED"), ("exp", "EXPERT"), ("mas", "MASTER"), ("remas", "Re:MASTER"))
_KINDS = (("", "STD"), ("dx_", "DX"))
CONTENT_LIMIT = 1900         # Discord allows 2000 characters a message; the rest of a long report goes in the attached file


def held(cache_file: Path) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """The Japan and international tables in the saved cache, which is what every process last agreed on; empty when there is none."""
    try:
        with open(cache_file, "rb") as f:
            data = pickle.load(f)
        return data.get("songs") or {}, data.get("songs_intl") or {}
    except Exception:
        return {}, {}


def _songs(table: Dict[str, Any]) -> Dict[Tuple[str, str], Dict[str, Any]]:
    """Each song once: a table also holds a song under its reading, and two songs can share a title, so they go by title and artist."""
    return {(str(song.get("title", "")), str(song.get("artist", ""))): song for song in table.values()}


def _chart(song: Dict[str, Any], prefix: str, tier: str) -> Dict[str, str]:
    return {field: str(song.get(f"{prefix}lev_{tier}{suffix}", "") or "").strip()
            for field, suffix in (("level", ""), ("constant", "_i"), ("notes", "_notes"), ("designer", "_designer"))}


def _version(song: Dict[str, Any]) -> str:
    try:
        from rasmai.bot.builders.charts.index import version_name
        return version_name(song)
    except Exception:
        return str(song.get("version", ""))


def _levels(song: Dict[str, Any]) -> str:
    """A song's charts in a few words: "DX 2 / 6 / 9 / 13+ (13.7)", the last one with its constant."""
    parts = []
    for prefix, kind in _KINDS:
        charts = [_chart(song, prefix, tier) for tier, _name in _TIERS]
        shown = [chart["level"] for chart in charts if chart["level"]]
        if shown:
            top = next(chart for chart in reversed(charts) if chart["level"])
            parts.append(f"{kind} {' / '.join(shown)}" + (f" ({top['constant']})" if top["constant"] else ""))
    return ", ".join(parts)


def diff(old: Dict[str, Any], new: Dict[str, Any]) -> Dict[str, List[str]]:
    """What changed between two song tables, as lines under "added", "removed" and "changed"."""
    before, after = _songs(old), _songs(new)
    report: Dict[str, List[str]] = {"added": [], "removed": [], "changed": []}
    for key in sorted(after.keys() - before.keys()):
        song = after[key]
        version = _version(song)
        report["added"].append(f"**{key[0]}** - {key[1]}" + (f" ({version})" if version else "") + (f": {_levels(song)}" if _levels(song) else ""))
    for key in sorted(before.keys() - after.keys()):
        report["removed"].append(f"**{key[0]}** - {key[1]}")
    for key in sorted(before.keys() & after.keys()):
        was, now = before[key], after[key]
        lines = []
        if bool(was.get("deleted")) != bool(now.get("deleted")):
            lines.append("removed from the game" if now.get("deleted") else "back in the game")
        if str(was.get("intl", "")) != str(now.get("intl", "")) and str(now.get("intl", "")) == "1":
            lines.append("now on the international version")
        filled = []         # note counts and designers turning up for charts that had none: one short line, not a dozen "? → 284"
        for prefix, kind in _KINDS:
            for tier, name in _TIERS:
                a, b = _chart(was, prefix, tier), _chart(now, prefix, tier)
                if a == b:
                    continue
                for field in ("notes", "designer"):
                    if not a[field] and b[field]:
                        filled.append(field)
                        a = {**a, field: b[field]}
                if a == b:
                    continue
                label = f"{kind} {name}"
                if not a["level"] and b["level"]:
                    lines.append(f"{label} added: {b['level']}" + (f" ({b['constant']})" if b["constant"] else ""))
                    continue
                if a["level"] and not b["level"]:
                    lines.append(f"{label} removed")
                    continue
                bits = []
                if a["level"] != b["level"]:
                    bits.append(f"level {a['level']} → {b['level']}")
                if a["constant"] != b["constant"]:
                    bits.append(f"constant {a['constant'] or '?'} → {b['constant'] or '?'}")
                if a["notes"] != b["notes"]:
                    bits.append(f"notes {a['notes'] or '?'} → {b['notes'] or '?'}")
                if a["designer"] != b["designer"]:
                    bits.append(f"designer {a['designer'] or '?'} → {b['designer'] or '?'}")
                lines.append(f"{label} " + ", ".join(bits))
        if filled:
            lines.append(" and ".join(f"{field if field == 'notes' else 'designers'} filled in" for field in dict.fromkeys(filled)).replace("notes", "note counts"))
        if lines:
            report["changed"].append(f"**{key[0]}**: " + "; ".join(lines))
    return report


def describe(tables: List[Tuple[str, Dict[str, Any], Dict[str, Any]]]) -> str:
    """The whole report for these ``(region name, old table, new table)``; empty when nothing changed."""
    sections = []
    for region, old, new in tables:
        if not old:
            continue        # nothing to compare with: a cache from before the international table existed, say
        report = diff(old, new)
        if not any(report.values()):
            continue
        counts = f"{len(report['added'])} added, {len(report['removed'])} removed, {len(report['changed'])} changed"
        body = [f"## {region} ({counts})"]
        for heading, key in (("Added", "added"), ("Removed", "removed"), ("Changed", "changed")):
            if report[key]:
                body.append(f"**{heading}**\n" + "\n".join(f"- {line}" for line in report[key]))
        sections.append("\n".join(body))
    return "\n\n".join(sections)


def _send(text: str) -> None:
    # the report names songs, and a title could be anything: nothing in it may ping anyone
    payload = {"username": "otoge-db", "allowed_mentions": {"parse": []}}
    files = None
    if len(text) <= CONTENT_LIMIT:
        payload["content"] = "# otoge-db updated\n" + text
    else:
        cut = text[:CONTENT_LIMIT].rsplit("\n", 1)[0]
        payload["content"] = "# otoge-db updated\n" + cut + "\n\n-# The full list is in the attached file."
        files = {"file": ("otoge-db-changes.md", text.encode("utf-8"), "text/markdown")}
    try:
        if files:
            response = requests.post(OTOGE_WEBHOOK_URL, data={"payload_json": json.dumps(payload)}, files=files, timeout=30)
        else:
            response = requests.post(OTOGE_WEBHOOK_URL, json=payload, timeout=30)
        if response.status_code >= 300:
            logger.warning("otoge-db changes: the webhook answered %s", response.status_code)
    except requests.RequestException as error:
        logger.warning("otoge-db changes: the webhook could not be reached (%s)", type(error).__name__)


def announce(tables: List[Tuple[str, Dict[str, Any], Dict[str, Any]]]) -> str:
    """Post what changed to the otoge-db webhook, in the background so the fetch is not held up. Returns the report.

    Nothing is posted when no webhook is set, when nothing changed, or when there was no earlier copy to compare with.
    """
    if not OTOGE_WEBHOOK_URL or not any(old for _region, old, _new in tables):
        return ""
    text = describe(tables)
    if text:
        threading.Thread(target=_send, args=(text,), daemon=True, name="otoge-db changes").start()
    return text

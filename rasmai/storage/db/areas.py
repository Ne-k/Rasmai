from datetime import datetime
from typing import List, Dict, Optional, Tuple, Any

from rasmai.storage.db.connection import _load_json_column, get_database_connection


def _period_iso(stamp: Any) -> Optional[str]:
    """An event period bound (milliseconds since the epoch, from the scraper) as ISO text.

    :rtype: Optional[str]
    """
    try:
        return datetime.fromtimestamp(int(stamp) / 1000).astimezone().isoformat(timespec="seconds") if stamp else None
    except (TypeError, ValueError, OSError):
        return None


def record_area_progress(user_id: str, events: Optional[Dict[str, Any]], plays: int) -> int:
    """Remember each area's distance from one read of the map pages; unchanged areas add nothing.

    A row is stored only when the distance, the next reward or the state moved since the
    last stored row for that area, with the account's total play count at the time, so
    the distance a play earns can be measured from the player's own reads.

    :param user_id: The Discord user id.
    :type user_id: str
    :param events: The map data, as the site lists it.
    :type events: Optional[Dict[str, Any]]
    :param plays: How many times the chart has been played.
    :type plays: int
    :rtype: int
    """
    if not events:
        return 0
    rows: List[Tuple[Any, ...]] = []
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    for kind, key in (("area", "areaEvents"), ("event", "eventAreaEvents")):
        for event in events.get(key) or []:
            name = str(event.get("name") or "").strip()
            if not name:
                continue
            period = event.get("eventPeriod") or [None, None]
            rows.append((user_id, kind, name, now, int(event.get("currentDistance") or 0),
                         event.get("nextRewardDistance"), str(event.get("state") or "in_progress"), int(plays or 0),
                         _period_iso(period[0]), _period_iso(period[1])))
    if not rows:
        return 0
    connection = get_database_connection()
    try:
        added = 0
        with connection:
            for row in rows:
                last = connection.execute(
                    "SELECT distance, next_reward, state, plays FROM area_progress WHERE user_id = ? AND kind = ? AND name = ? "
                    "ORDER BY recorded_at DESC LIMIT 1",
                    (user_id, row[1], row[2]),
                ).fetchone()
                if last and int(last["distance"]) == row[4] and last["next_reward"] == row[5] and last["state"] == row[6]:
                    continue
                connection.execute("INSERT OR REPLACE INTO area_progress VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", row)
                added += 1
        return added
    finally:
        connection.close()


def stored_area_images() -> List[Dict[str, str]]:
    """The picture address and key of every area in every account's stored snapshot, each once.

    :rtype: List[Dict[str, str]]
    """
    connection = get_database_connection()
    try:
        rows = connection.execute("SELECT latest_snapshot FROM connected_accounts WHERE latest_snapshot IS NOT NULL").fetchall()
    finally:
        connection.close()
    seen: Dict[str, Dict[str, str]] = {}
    for row in rows:
        snapshot = _load_json_column(row["latest_snapshot"]) or {}
        areas = snapshot.get("areas") or {}
        for event in list(areas.get("areaEvents") or []) + list(areas.get("eventAreaEvents") or []) + list(areas.get("endedEvents") or []):
            url = str(event.get("imageUrl") or "")
            if url and url not in seen:
                seen[url] = {"url": url, "key": str(event.get("imageKey") or "")}
    return list(seen.values())


def load_area_progress(user_id: str) -> List[Dict[str, Any]]:
    """Every stored area reading for the account, oldest first.

    :param user_id: The Discord user id.
    :type user_id: str
    :rtype: List[Dict[str, Any]]
    """
    connection = get_database_connection()
    try:
        rows = connection.execute(
            "SELECT kind, name, recorded_at, distance, next_reward, state, plays, period_start, period_end "
            "FROM area_progress WHERE user_id = ? ORDER BY recorded_at",
            (user_id,),
        ).fetchall()
    finally:
        connection.close()
    return [dict(row) for row in rows]

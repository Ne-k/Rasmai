from typing import Dict
import sqlite3
import zlib

from rasmai.storage.db import connection as store
from rasmai.storage.db.connection import _dump_json_column, _load_json_column, get_database_connection


def pack() -> Dict[str, int]:
    """Pack what was stored before packing, and give the space back to the disk.

    New writes are packed as they happen; this is for the accounts nobody has read since, which
    would otherwise stay as text for good. A copy of the database is taken first, beside it, and
    the file only shrinks at the end, when VACUUM rewrites it.

    :returns: What was packed, and the file's size before and after.
    :rtype: Dict[str, int]
    """
    connection = get_database_connection()
    size = lambda: connection.execute("PRAGMA page_count").fetchone()[0] * connection.execute("PRAGMA page_size").fetchone()[0]
    before = size()
    backup = sqlite3.connect(str(store.DATABASE_PATH) + ".before-pack")
    connection.backup(backup)
    backup.close()
    accounts = sources = 0
    try:
        for (user_id,) in connection.execute(
                "SELECT user_id FROM connected_accounts WHERE typeof(latest_snapshot) = 'text'").fetchall():
            row = connection.execute("SELECT latest_snapshot FROM connected_accounts WHERE user_id = ?", (user_id,)).fetchone()
            snapshot = _load_json_column(row[0])
            if snapshot is None:
                continue
            # The two recent-play lists become one. "recent" was "recentPlays" less any play without an
            # id; where it holds something else, a quiet read wrote it later, and it is the one to keep.
            recent = snapshot.pop("recent", None)
            if recent and recent != [r for r in snapshot.get("recentPlays") or [] if r.get("idx")]:
                snapshot["recentPlays"] = recent
            with connection:
                connection.execute("UPDATE connected_accounts SET latest_snapshot = ? WHERE user_id = ?",
                                   (_dump_json_column(snapshot, packed=True), user_id))
            accounts += 1
        for source, payload in connection.execute(
                "SELECT source, payload FROM news_state WHERE typeof(payload) = 'text' AND length(payload) > 4096").fetchall():
            with connection:
                connection.execute("UPDATE news_state SET payload = ? WHERE source = ?",
                                   (zlib.compress(payload.encode("utf-8"), 6), source))
            sources += 1
        connection.execute("VACUUM")
        return {"accounts": accounts, "sources": sources, "before": before, "after": size()}
    finally:
        connection.close()


if __name__ == "__main__":
    done = pack()
    print(f"packed {done['accounts']} accounts and {done['sources']} source payloads; "
          f"{done['before'] / 1e6:.1f} MB -> {done['after'] / 1e6:.1f} MB "
          f"(the copy from before is {store.DATABASE_PATH}.before-pack)")

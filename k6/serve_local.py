from pathlib import Path
import argparse
import json
import os
import secrets
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parent.parent
FIRST_ID = 100000000000000000      # test ids for a scratch database; no Discord account is behind them


def _exports():
    """Every debug export that carries a score table, as (player, songs, recent, profile)."""
    found = []
    for path in sorted((ROOT / "debug").glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        if "player" in data and data.get("songs"):
            found.append((data["player"], data["songs"], data.get("recentSongsData") or [],
                          data.get("officialProfile") or {}))
    return found


def _seed(count):
    """Link ``count`` test accounts to snapshots built the way the bot builds them, from debug/.

    Each distinct export is analysed once and its snapshot reused under as many ids as asked for:
    what an analysis costs depends on the charts in it, not on whose they are.
    """
    from rasmai.bot.state.snapshots import compact_snapshot
    from rasmai.scraping.scraper import MaimaiRatingAnalyzer
    from rasmai.storage.db import upsert_connected_account
    from rasmai.storage.models import PlayerInfo, SongInfo

    exports = _exports()
    if not exports:
        sys.exit("no usable exports in debug/")
    player_fields, song_fields = PlayerInfo.__dataclass_fields__, SongInfo.__dataclass_fields__
    built = []
    for player, songs, recent, profile in exports:
        analyzer = MaimaiRatingAnalyzer()
        analyzer.player = PlayerInfo(**{k: v for k, v in player.items() if k in player_fields})
        analyzer.songs = [SongInfo(**{k: v for k, v in row.items() if k in song_fields}) for row in songs]
        analyzer.recent_songs = list(recent)
        analyzer.generate_recommendations()
        built.append((compact_snapshot(analyzer), {**profile, "name": player.get("name", ""),
                                                   "rating": player.get("rating", 0)}))
    users = []
    for number in range(count):
        snapshot, profile = built[number % len(built)]
        user_id = str(FIRST_ID + number)
        # no maimai session: nothing here may read the live site, only what is stored
        upsert_connected_account(user_id, "intl", "", profile, snapshot)
        users.append(user_id)
    return users, len(built)


def main():
    """Serve Rasmai's internal API on localhost, over a scratch database seeded from debug/.

    For load testing with k6. The Discord bot is not started, data/ is never opened, and nothing
    reaches maimai or the chart repositories: the one path that would fetch in the background is
    replaced with a no-op for the life of the process.
    """
    parser = argparse.ArgumentParser(description=main.__doc__.splitlines()[0])
    scratch = Path(tempfile.gettempdir())
    parser.add_argument("--port", type=int, default=18765)
    parser.add_argument("--users", type=int, default=8, help="test accounts to link, cycling the exports")
    parser.add_argument("--db", default=str(scratch / "rasmai-k6.sqlite3"))
    parser.add_argument("--out", default=str(scratch / "rasmai-k6-users.json"),
                        help="where k6 reads the user ids and the secret from")
    args = parser.parse_args()

    database = Path(args.db)
    if database.exists():
        database.unlink()           # a fresh scratch database every run, never data/
    secret = secrets.token_hex(16)  # made for this run and nowhere else
    os.environ["MAIMAI_DATABASE_PATH"] = str(database)
    os.environ["RASMAI_INTERNAL_SECRET"] = secret
    os.environ["MAIMAI_WEBSERVER_HOST"] = "127.0.0.1"
    sys.path.insert(0, str(ROOT))

    from rasmai.web.dashboard import analysis as dashboard_analysis
    dashboard_analysis.resolve_unknown_later = lambda cached, loop=None: False

    started = time.monotonic()
    users, distinct = _seed(args.users)
    Path(args.out).write_text(json.dumps({"users": users, "secret": secret,
                                          "base": f"http://127.0.0.1:{args.port}"}), encoding="utf-8")
    print(f"seeded {len(users)} accounts from {distinct} exports in {time.monotonic() - started:.1f}s")

    from rasmai.web.web_server import InternalApiServer
    server = InternalApiServer(host="127.0.0.1", port=args.port)
    server.start()
    print(f"internal API on http://127.0.0.1:{args.port}; users and secret in {args.out}", flush=True)
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()

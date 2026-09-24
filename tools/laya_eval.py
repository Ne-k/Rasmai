from pathlib import Path
from typing import Any, Callable, Dict, Optional, Sequence, Tuple
import collections
import json
import os
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, OSError):
    pass

from rasmai.engine import analysis
from rasmai.scraping.otoge import CachedOtogeDB
from rasmai.storage.models import SongInfo

Key = Tuple[str, str, str]
SPLIT = 0.6      # the share of a player's play log the profile is allowed to see
_INDEX: list = [None]    # the chart database of the account being scored, for scorers that want it
_NAME: list = [""]       # and whose account it is, so a scorer can find what was written down for them


def _accounts() -> Dict[str, Dict[str, Any]]:
    """Every exported account, with its newest score table and the union of its play logs.

    One account is exported many times over a fortnight; each export carries only the last fifty
    plays, so the union across files is a longer log than any single file holds.

    :returns: ``{name: {"songs": [...], "plays": [...]}}`` with plays oldest first.
    :rtype: Dict[str, Dict[str, Any]]
    """
    newest: Dict[str, Tuple[str, Any]] = {}
    plays: Dict[str, Dict[Tuple[str, str, str, str], Dict[str, Any]]] = collections.defaultdict(dict)
    allowed = SongInfo.__dataclass_fields__
    for path in sorted(Path("debug").glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        if "player" not in data or not data.get("songs"):
            continue
        name = data["player"]["name"]
        if name not in newest or path.name > newest[name][0]:
            newest[name] = (path.name, [SongInfo(**{k: v for k, v in row.items() if k in allowed})
                                        for row in data["songs"]])
        for play in data.get("recentSongsData") or []:
            plays[name][(play.get("playedAt", ""), play.get("songName", ""),
                         play.get("difficulty", ""), play.get("musicType", ""))] = play
    return {name: {"songs": songs, "plays": sorted(plays[name].values(), key=lambda p: p.get("playedAt", ""))}
            for name, (_file, songs) in newest.items() if plays[name]}


def _key(title: str, chart_type: str, difficulty: str) -> Key:
    return (str(title).casefold(), str(chart_type).lower() or "std", str(difficulty).lower())


def _percentile(scores: Dict[Key, float], wanted: Key) -> float:
    """Where a chart landed in the ranking, as the share of the pool it beat.

    1.0 means it was ranked first and 0.5 means the scorer did no better than a coin.

    :rtype: float
    """
    mine = scores[wanted]
    below = sum(1 for value in scores.values() if value < mine)
    tied = sum(1 for value in scores.values() if value == mine) - 1
    return (below + tied / 2.0) / max(1, len(scores) - 1)


def evaluate(scorer: Callable[[Any, Sequence[Any], Sequence[Dict[str, Any]]], Dict[Key, float]],
             quiet: bool = False) -> Dict[str, Any]:
    """Rank every chart an account holds a score on, and see where the ones they went and played land.

    The profile is built from the older part of each play log and judged on the newer part, so no
    scorer ever sees the plays it is being asked to predict.

    :param scorer: Given ``(profile, songs, seen_plays)``, a score per chart key. Higher is likelier.
    :type scorer: Callable
    :param quiet: Skip the per-account table.
    :type quiet: bool
    :rtype: Dict[str, Any]
    """
    database = CachedOtogeDB()
    database.update_if_needed()
    per_account, placements = {}, []
    for name, account in sorted(_accounts().items()):
        songs, plays = account["songs"], account["plays"]
        cut = int(len(plays) * SPLIT)
        seen, held = plays[:cut], plays[cut:]
        if not held:
            continue
        index = analysis.build_chart_index(database.songs_data, region="intl")
        version = analysis.detect_current_version(songs, index)
        index.current_version = version
        analysis.enrich_songs(songs, index, version)
        _INDEX[0], _NAME[0] = index, name
        profile = analysis.build_play_profile(songs, seen, index, version)

        pool = {_key(s.name, s.chart_type, s.difficulty_type) for s in songs
                if float(getattr(s, "difficulty", 0) or 0) > 0
                and float(getattr(s, "accuracy", 0) or 0) > 0
                and str(getattr(s, "difficulty_type", "")).lower() != "utage"}
        scores = {key: value for key, value in scorer(profile, songs, seen).items() if key in pool}
        if len(scores) != len(pool):
            raise SystemExit(f"{name}: the scorer answered for {len(scores)} of {len(pool)} charts")

        mine = []
        for play in held:
            key = _key(play.get("songName", ""), play.get("musicType", ""), play.get("difficulty", ""))
            if key in scores:
                mine.append(_percentile(scores, key))
        if not mine:
            continue
        placements.extend(mine)
        per_account[name] = {"plays": len(mine), "pool": len(pool),
                             "percentile": sum(mine) / len(mine),
                             "top25": sum(1 for p in mine if p >= 1 - 25 / len(pool)) / len(mine)}
        if not quiet:
            row = per_account[name]
            print(f"  {name[:16]:18} {row['plays']:4} held-out plays  pool {row['pool']:5}  "
                  f"percentile {row['percentile']:.3f}  top-25 {row['top25']:.1%}")
    overall = sum(placements) / len(placements) if placements else 0.0
    if not quiet:
        print(f"  {'OVERALL':18} {len(placements):4} plays                       percentile {overall:.3f}")
    return {"percentile": overall, "plays": len(placements), "accounts": per_account,
            "placements": placements}


def affinity_scorer(profile, songs, seen) -> Dict[Key, float]:
    """The taste term the recommender ships today: chart type times genre times difficulty."""
    out = {}
    for song in songs:
        key = _key(song.name, song.chart_type, song.difficulty_type)
        out[key] = profile.affinity(key[1], str(getattr(song, "genre", "")), key[2])
    return out


def chance_scorer(profile, songs, seen) -> Dict[Key, float]:
    """Every chart scored alike, so the percentile it earns is the coin toss everything else must beat."""
    return {_key(s.name, s.chart_type, s.difficulty_type): 1.0 for s in songs}


def _band(profile, songs) -> Tuple[float, float]:
    """The level the player has been living in, and how wide a spread around it they play."""
    levels = [float(getattr(s, "difficulty", 0) or 0) for s in songs
              if _key(s.name, s.chart_type, s.difficulty_type) in profile.recent_keys]
    if not levels:
        return 12.0, 1.5
    centre = sum(levels) / len(levels)
    return centre, max(0.8, (max(levels) - min(levels)) / 4.0) if len(levels) > 1 else 1.5


def habit_scorer(profile, songs, seen, grind: bool = True) -> Dict[Key, float]:
    """What a few lines of arithmetic can say about the next chart, with nothing learned.

    Players stay in a narrow level band, come back to what they were already grinding, and lean
    the way their taste leans. This is the rung below a model, and whatever a model costs has to
    buy something over it.

    :param grind: Whether returning to a chart already being ground counts. Off, this is the part
        of the guess a recommender is allowed to use: ``_freshness`` exists to push *against*
        replaying the same chart, so a score that wins by remembering the grind wins nothing.
    :type grind: bool
    """
    centre, spread = _band(profile, songs)
    out = {}
    for song in songs:
        key = _key(song.name, song.chart_type, song.difficulty_type)
        constant = float(getattr(song, "difficulty", 0) or 0)
        score = 2.718 ** (-((constant - centre) / spread) ** 2)       # the level band they are living in
        if grind:
            score *= 1.0 + 3.0 * profile.recent_grind.get(key, 0)     # a chart they are already grinding
            if key in profile.recent_keys:
                score *= 2.0
        score *= profile.affinity(key[1], str(getattr(song, "genre", "")), key[2])
        out[key] = score
    return out


def band_scorer(profile, songs, seen) -> Dict[Key, float]:
    """The habit guess with the grind memory taken out: level band times taste, nothing else."""
    return habit_scorer(profile, songs, seen, grind=False)


def laya_scorer(profile, songs, seen, weight: Optional[float] = None) -> Dict[Key, float]:
    """The arithmetic, with the decision model allowed to reorder the shortlist it produced.

    Shaped exactly like the bot: rank everything with the arithmetic, hand the model only the
    charts that could actually be recommended, and let it move those. A chart the model never
    saw keeps the score it already had, so the model can only ever win or lose on its own list.
    """
    from rasmai.engine.insights import laya

    base = band_scorer(profile, songs, seen)
    index = _INDEX[0]
    _base, rows = _shortlist(profile, songs, seen, index)
    cached = _cached_odds(_NAME[0])
    odds = cached if cached else laya.pick_odds(profile, rows)
    odds = {row["key"]: odds[row["key"]] for row in rows if row["key"] in odds}
    if not odds:
        raise SystemExit("the model answered for nothing at all; is laya installed and the model downloaded?")
    taste = laya.weigh(odds, weight=laya.WEIGHT if weight is None else weight)
    return {key: value * taste.get(key, 1.0) for key, value in base.items()}


def _cached_odds(name: str) -> Dict[Key, float]:
    """What was written down for this account last time it was asked, if anything.

    The model is minutes per account and its answers do not change between runs, so a scorer
    reads them back rather than paying for them again.
    """
    if not name or not CACHE.exists():
        return {}
    try:
        rows = json.loads(CACHE.read_text(encoding="utf-8"))["accounts"].get(name) or {}
    except (OSError, ValueError, KeyError):
        return {}
    return {tuple(key.split("|")): value for key, value in (rows.get("odds") or {}).items()}


SCORERS: Dict[str, Callable] = {"chance": chance_scorer, "affinity": affinity_scorer,
                                "habit": habit_scorer, "band": band_scorer,
                                "laya": laya_scorer}


# the answers are a tuning artefact, not project data, so they live outside the tree
CACHE = Path(os.getenv("RASMAI_LAYA_CACHE", Path(tempfile.gettempdir()) / "rasmai-laya-odds.json"))


def _shortlist(profile, songs, seen, index):
    """The charts the model would be shown, and everything needed to describe them."""
    from rasmai.engine.insights import laya
    from rasmai.engine.insights.tags import chart_traits
    base = band_scorer(profile, songs, seen)
    by_key = {_key(s.name, s.chart_type, s.difficulty_type): s for s in songs}
    rows = []
    for key in sorted(base, key=lambda k: -base[k])[:laya.CAP]:
        song = by_key[key]
        chart = index.get(key) if index else None
        try:
            traits = chart_traits(chart) if chart else []
        except Exception:
            traits = []
        rows.append({"key": key, "title": song.name, "artist": str(getattr(song, "artist", "")),
                     "genre": str(getattr(song, "genre", "")), "level": str(getattr(song, "level", "")),
                     "difficulty": key[2], "chart_type": key[1],
                     "is_new": bool(getattr(song, "is_new", False)), "traits": traits})
    return base, rows


def collect() -> None:
    """Ask the model about every account once and write the answers down.

    The model is the slow part by a mile, and what is done with its answers afterwards is
    arithmetic. Asking once and fitting offline is the difference between a minute a try and
    half an hour a try.
    """
    from rasmai.engine.insights import laya
    database = CachedOtogeDB()
    database.update_if_needed()
    out: Dict[str, Any] = {"cap": laya.CAP, "recent_shown": laya.RECENT_SHOWN, "brief": laya.BRIEF,
                           "accounts": {}}
    for name, account in sorted(_accounts().items()):
        songs, plays = account["songs"], account["plays"]
        cut = int(len(plays) * SPLIT)
        seen, held = plays[:cut], plays[cut:]
        index = analysis.build_chart_index(database.songs_data, region="intl")
        version = analysis.detect_current_version(songs, index)
        index.current_version = version
        analysis.enrich_songs(songs, index, version)
        profile = analysis.build_play_profile(songs, seen, index, version)
        _base, rows = _shortlist(profile, songs, seen, index)
        started = __import__("time").time()
        odds = laya.pick_odds(profile, rows)
        if not odds:
            sys.exit("the model answered for nothing at all; is laya installed?")
        out["accounts"][name] = {"odds": {"|".join(key): value for key, value in odds.items()},
                                 "held": ["|".join(_key(p.get("songName", ""), p.get("musicType", ""),
                                                        p.get("difficulty", ""))) for p in held]}
        print(f"  {name[:16]:18} {len(odds):3} charts asked in {__import__('time').time() - started:5.1f}s", flush=True)
    CACHE.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    print(f"\nwritten to {CACHE}")


def _mapped(odds: Dict[Key, float], how: str, weight: float) -> Dict[Key, float]:
    """The model's odds turned into a multiplier, by exactly the code the bot uses."""
    from rasmai.engine.insights import laya
    return laya.weigh(odds, weight=weight, how=how)


def tune() -> None:
    """Fit how far to believe the model, on the ordering that is actually the model's to change.

    Measured inside the shortlist, not against the whole game. The thirty charts the model is
    shown are already the top thirty of six hundred, so asking where they land among six hundred
    answers itself; the only real question is whether the played one moves up *within the thirty*.
    Half is the coin toss here, and the arithmetic's own order is what has to be beaten.
    """
    if not CACHE.exists():
        sys.exit(f"no cached answers at {CACHE}; run `python tools/laya_eval.py collect` first")
    import statistics
    cached = json.loads(CACHE.read_text(encoding="utf-8"))
    database = CachedOtogeDB()
    database.update_if_needed()

    bases: Dict[str, Any] = {}
    for name, account in sorted(_accounts().items()):
        if name not in cached["accounts"]:
            continue
        songs, plays = account["songs"], account["plays"]
        seen = plays[:int(len(plays) * SPLIT)]
        index = analysis.build_chart_index(database.songs_data, region="intl")
        version = analysis.detect_current_version(songs, index)
        index.current_version = version
        analysis.enrich_songs(songs, index, version)
        profile = analysis.build_play_profile(songs, seen, index, version)
        base = band_scorer(profile, songs, seen)
        odds = {tuple(key.split("|")): value for key, value in cached["accounts"][name]["odds"].items()}
        held = [tuple(key.split("|")) for key in cached["accounts"][name]["held"]]
        wanted = [key for key in held if key in odds]
        if not wanted:
            continue
        bases[name] = {"base": {key: base[key] for key in odds if key in base}, "odds": odds, "held": wanted}

    def score(how: str, weight: float) -> Dict[str, list]:
        out = {}
        for name, row in bases.items():
            scores = dict(row["base"])
            if weight:
                for key, factor in _mapped(row["odds"], how, weight).items():
                    if key in scores:
                        scores[key] *= factor
            out[name] = [_percentile(scores, key) for key in row["held"] if key in scores]
        return {name: values for name, values in out.items() if values}

    flat = lambda got: [p for values in got.values() for p in values]
    counted = len(flat(score("mean", 0.0)))
    print()
    print(f"{counted} held-out plays landed on a shortlist the model was shown, across "
          f"{len(bases)} accounts; 0.500 is the coin toss inside a shortlist")
    baseline = statistics.fmean(flat(score("mean", 0.0)))
    per_account_baseline = {name: statistics.fmean(values) for name, values in score("mean", 0.0).items()}
    print(f"the arithmetic's own order, inside the shortlist: {baseline:.4f}")
    print()
    print(f"  {'mapping':9} {'weight':>7}  {'percentile':>10}  {'vs arithmetic':>14}  accounts better")
    best = (baseline, "mean", 0.0)
    for how in ("mean", "spread", "rank"):
        for weight in (0.25, 0.5, 1.0, 1.5, 2.0, 3.0):
            got = score(how, weight)
            overall = statistics.fmean(flat(got))
            better = sum(1 for name, values in got.items()
                         if statistics.fmean(values) > per_account_baseline[name])
            print(f"  {how:9} {weight:7.2f}  {overall:10.4f}  {overall - baseline:+14.4f}  {better}/{len(got)}")
            if overall > best[0]:
                best = (overall, how, weight)
    print()
    print(f"best: {best[1]} at weight {best[2]} -> {best[0]:.4f} ({best[0] - baseline:+.4f})")

    # held out a player at a time: a setting fitted on eight accounts and only good on those eight
    # is a setting that will not survive the ninth
    print()
    print("leave one player out")
    kept = []
    for left_out in bases:
        pick, pick_at = None, -1.0
        for how in ("mean", "spread", "rank"):
            for weight in (0.25, 0.5, 1.0, 1.5, 2.0, 3.0):
                got = {name: values for name, values in score(how, weight).items() if name != left_out}
                overall = statistics.fmean([p for values in got.values() for p in values])
                if overall > pick_at:
                    pick, pick_at = (how, weight), overall
        mine = statistics.fmean(score(pick[0], pick[1])[left_out])
        was = per_account_baseline[left_out]
        kept.append(mine - was)
        print(f"  {left_out[:16]:18} others chose {pick[0]:7} at {pick[1]:.2f}  ->  "
              f"{was:.4f} to {mine:.4f}  ({mine - was:+.4f})")
    print()
    print(f"  mean change on the held-out player: {statistics.fmean(kept):+.4f}  "
          f"({sum(1 for k in kept if k > 0)}/{len(kept)} improved)")


def main() -> None:
    """Run each named scorer over every exported account."""
    wanted = sys.argv[1:] or ["chance", "affinity"]
    if wanted[0] == "collect":
        return collect()
    if wanted[0] == "tune":
        return tune()
    for name in wanted:
        if name not in SCORERS:
            sys.exit(f"no scorer called {name}; try {', '.join(SCORERS)}, collect, tune")
        print(f"\n{name}")
        evaluate(SCORERS[name])


if __name__ == "__main__":
    main()

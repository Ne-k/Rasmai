from pathlib import Path
from typing import Any, Dict, List
import statistics
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rasmai.engine import analysis, insights
from rasmai.engine.insights import traits as T
from rasmai.scraping.otoge import CachedOtogeDB
from tools.replay import load

ACCOUNTS = 10


def profiles(limit: int = ACCOUNTS):
    """Every account in debug/, largest first, as (name, profile). Never re-reads the chart index."""
    database = CachedOtogeDB()
    seen = set()
    for path in sorted(Path("debug").glob("maimai-export-*.json"), key=lambda p: -p.stat().st_size):
        try:
            name, rating, songs, recent = load(path)
        except SystemExit:
            continue
        if not songs or name in seen:
            continue
        seen.add(name)
        index = analysis.build_chart_index(database.songs_data, region="intl")
        version = analysis.detect_current_version(songs, index)
        index.current_version = version
        analysis.enrich_songs(songs, index, version)
        judgements = [dict(p, notes=(p.get("judgement") or {}).get("notes") or {}) for p in recent if p.get("judgement")]
        yield name, analysis.build_play_profile(songs, recent, index, version, judgements=judgements)
        if len(seen) >= limit:
            return


def blocking(axis: Dict[str, Any]) -> List[str]:
    """Which gates a measured axis fails, for an axis that is neither confirmed nor leaning."""
    failed = []
    if abs(float(axis["offset"])) < T.TRAIT_THRESHOLD:
        failed.append("offset")
    if float(axis["p"]) > T.TRAIT_P:
        failed.append("p")
    if int(axis["count"]) < T.TRAIT_CONFIRM_CHARTS:
        failed.append("charts")
    if not axis.get("verified") and not failed:
        failed.append("split")     # far enough, rare enough, common enough, and still not confirmed
    return failed


def main() -> None:
    rows = []
    only = {"offset": 0, "p": 0, "charts": 0, "split": 0}
    for name, profile in profiles():
        axes = [a for a in (profile.trait_axes or []) if a["dimension"] not in insights.NOT_A_SKILL]
        confirmed, leaning, even = insights.notable(axes), insights.leaning(axes), insights.even(axes)
        shown = len(confirmed) + len(leaning)
        rows.append((name, len(axes), len(confirmed), len(leaning), len(even), shown))
        for axis in axes:
            if axis.get("verified") or axis.get("leaning"):
                continue
            failed = blocking(axis)
            if len(failed) == 1:
                only[failed[0]] += 1
    print(f"{'player':16} {'axes':>5} {'confirmed':>10} {'leaning':>8} {'level':>6} {'SHOWN':>6}")
    for name, axes, confirmed, leaning, even, shown in rows:
        print(f"{name:16} {axes:>5} {confirmed:>10} {leaning:>8} {even:>6} {shown:>6}")
    print(f"\n{'total':16} {sum(r[1] for r in rows):>5} {sum(r[2] for r in rows):>10} "
          f"{sum(r[3] for r in rows):>8} {sum(r[4] for r in rows):>6} {sum(r[5] for r in rows):>6}")
    print(f"\ngates in force: offset>={T.TRAIT_THRESHOLD} p<={T.TRAIT_P} charts>={T.TRAIT_CONFIRM_CHARTS} "
          f"lean>={T.TRAIT_LEAN_OFFSET}/p<={T.TRAIT_LEAN_P} measured>={T.TRAIT_MIN_CHARTS}")
    print("axes held back by exactly one gate, so moving that one gate would admit them:")
    for gate, count in sorted(only.items(), key=lambda kv: -kv[1]):
        print(f"   {gate:8} {count:>4}")


if __name__ == "__main__":
    main()

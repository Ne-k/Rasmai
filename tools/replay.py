from pathlib import Path
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rasmai.engine import analysis, insights
from rasmai.scraping.otoge import CachedOtogeDB
from rasmai.storage.models import SongInfo


def load(path):
    """Read an account from either export shape.

    `/export` writes rows against a ``fields`` list; the debug export writes whole song
    objects. Both end up as the same list of scores.

    :param path: The file to read.
    :type path: Path
    :returns: ``(player name, rating, scores, recent plays)``.
    :rtype: Tuple[str, int, List[SongInfo], List[dict]]

    :param path: The file to read or write.
    """
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if "player" in data and "songs" in data:
        allowed = SongInfo.__dataclass_fields__
        songs = [SongInfo(**{k: v for k, v in row.items() if k in allowed}) for row in data["songs"]]
        return data["player"]["name"], int(data["player"]["rating"] or 0), songs, data.get("recentSongsData") or []
    if "charts" in data and "fields" in data:
        songs = []
        for row in data["charts"]:
            fields = dict(zip(data["fields"], row))
            songs.append(SongInfo(
                name=fields["name"], chart_type=fields["chart_type"], difficulty_type=fields["difficulty_type"],
                accuracy=float(fields["accuracy"] or 0), rating=int(fields["rating"] or 0), level=str(fields["level"]),
                difficulty=float(fields["constant"] or 0), fc_status=fields["fc_status"] or "",
                fs_status=fields["fs_status"] or "", is_new=bool(fields["is_new"]), dx_score=int(fields["dx_score"] or 0),
            ))
        return data.get("name", "?"), int(data.get("rating") or 0), songs, data.get("recentPlays") or []
    sys.exit("That file is neither an /export nor a debug export.")


def main() -> None:
    """Print what the model makes of one exported account."""
    if len(sys.argv) < 2:
        sys.exit("usage: python tools/replay.py <export.json>")
    name, rating, songs, recent = load(sys.argv[1])
    database = CachedOtogeDB()
    database.update_if_needed()
    index = analysis.build_chart_index(database.songs_data, region="intl")
    version = analysis.detect_current_version(songs, index)
    index.current_version = version
    analysis.enrich_songs(songs, index, version)
    profile = analysis.build_play_profile(songs, recent, index, version)
    best50 = analysis.build_best50(songs)

    print(f"\n{name}  rating {rating}  version {version}  {len(songs)} charts")
    print(f"  comfortable to {profile.comfort_constant:.1f}, S expected to {profile.reach_constant:.1f}, "
          f"best-50 {best50.total}")
    print("\n  curve against the player's own upper quartile")
    for constant in sorted(profile.bucket_stats):
        representative, count, _best = profile.bucket_stats[constant]
        if count < 4 or constant < 10:
            continue
        gap = profile.expected_accuracy(constant) - representative
        print(f"    {constant:5.1f}  {count:4d} charts  curve {profile.expected_accuracy(constant):7.2f}  "
              f"own {representative:7.2f}  {gap:+.2f}")

    candidates = analysis.generate_recommendations(songs, profile, best50, index, version)
    print(f"\n  top picks ({len(candidates)} scored)")
    for candidate in candidates[:5]:
        print(f"    +{candidate.rating_gain:<3d} {candidate.title[:34]:36s} {candidate.difficulty_type:9s} "
              f"{candidate.constant:5.1f}  {candidate.current_accuracy:8.4f} -> {candidate.target_accuracy:.2f}")

    print("\n  traits")
    for trait in profile.traits[:5]:
        print(f"    {trait['offset']:+.2f}  {trait['label'][:46]:48s} {trait['count']} charts")
    wheel = insights.radar_axes(profile.trait_axes)
    print(f"  radar axes: {', '.join(a['label'].split(' (')[0] for a in wheel)}")


if __name__ == "__main__":
    main()

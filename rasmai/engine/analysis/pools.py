from dataclasses import dataclass
from typing import Any, Dict, Sequence

from rasmai.engine.analysis.rating import calculate_rating, rank_for
from rasmai.engine.analysis.charts import level_range, ChartIndex

class RatingPool:
    """One half of the best-50 (top 15 new charts, top 35 old charts)."""

    def __init__(self, size: int, entries: Dict[Any, int]):
        self.size = size
        self.entries = dict(entries)
        self._rebuild()

    def _rebuild(self) -> None:
        ordered = sorted(self.entries.items(), key=lambda item: item[1], reverse=True)
        size = self.size
        self.ranked = ordered
        self.in_pool = {key for key, _rating in ordered[:size]}
        self.total = sum(rating for _key, rating in ordered[:size])
        self.cutoff = ordered[size - 1][1] if len(ordered) >= size else 0
        self.next_value = ordered[size][1] if len(ordered) > size else 0

    def apply(self, key: Any, new_rating: int) -> int:
        """Record a new score for `key` and return how much the pool total moved.

        :param key: The chart, as ``(title, chart type, difficulty)``.
        :type key: Any
        :param new_rating: The rating the chart would hold after the new score.
        :type new_rating: int
        :returns: How much the pool total moved.
        :rtype: int
        """
        if self.entries.get(key, 0) >= new_rating:
            return 0
        before = self.total
        self.entries[key] = new_rating
        self._rebuild()
        return self.total - before

    def clone(self) -> "RatingPool":
        return RatingPool(self.size, self.entries)

    def gain_if(self, key: Any, new_rating: int) -> int:
        current = self.entries.get(key)
        if key in self.in_pool:
            replacement = max(new_rating, self.next_value)
            return replacement - (current or 0)
        if new_rating > self.cutoff:
            return new_rating - self.cutoff
        return 0

    def headroom(self) -> int:
        """Rating still missing before the pool is full.

        :returns: The rating still missing before the pool is full.
        :rtype: int
        """
        return max(0, self.size - len(self.in_pool))

@dataclass
class Best50:
    new_pool: RatingPool
    old_pool: RatingPool

    @property
    def total(self) -> int:
        return self.new_pool.total + self.old_pool.total

    def pool_for(self, is_new: bool) -> RatingPool:
        return self.new_pool if is_new else self.old_pool

    def gain_if(self, key: Any, is_new: bool, new_rating: int) -> int:
        return self.pool_for(is_new).gain_if(key, new_rating)

def build_best50(songs: Sequence[Any]) -> Best50:
    new_entries: Dict[Any, int] = {}
    old_entries: Dict[Any, int] = {}
    for song in songs:
        if str(getattr(song, "difficulty_type", "")) == "utage":
            continue
        rating = int(getattr(song, "rating", 0) or 0)
        if rating <= 0:
            continue
        key = (
            str(getattr(song, "name", "")).casefold(),
            str(getattr(song, "chart_type", "")).lower() or "std",
            str(getattr(song, "difficulty_type", "")).lower(),
        )
        target = new_entries if getattr(song, "is_new", False) else old_entries
        target[key] = max(target.get(key, 0), rating)
    return Best50(RatingPool(15, new_entries), RatingPool(35, old_entries))

def enrich_songs(
    songs: Sequence[Any],
    chart_index: ChartIndex,
    current_version: int,
) -> None:
    """Apply chart constants, version flags and correct ratings to scraped songs.

    :param songs: The player's scored charts.
    :type songs: Sequence[Any]
    :param chart_index: The chart database to look constants and metadata up in.
    :type chart_index: ChartIndex
    :param current_version: The game version the player is on.
    :type current_version: int
    """
    for song in songs:
        difficulty_type = str(getattr(song, "difficulty_type", "")).lower()
        if difficulty_type == "utage":
            continue
        key = (
            str(getattr(song, "name", "")).casefold(),
            str(getattr(song, "chart_type", "")).lower() or "std",
            difficulty_type,
        )
        chart = chart_index.get(key, level=str(getattr(song, "level", "") or ""))
        song.constant_estimated = chart is None
        if chart is None:
            # the site prints only the level; a "10+" was read as 10.0, below the band it names. The middle
            # of the band is the best single guess until the chart database learns the song.
            span = level_range(str(getattr(song, "level", "") or ""))
            if span:
                song.difficulty = round((span[0] + span[1]) / 2, 2)
        if chart:
            if chart.constant > 0:
                song.difficulty = chart.constant
            if not getattr(song, "genre", ""):
                song.genre = chart.genre
            if not getattr(song, "artist", ""):
                song.artist = chart.artist
            if not getattr(song, "cover_url", "") and chart.cover:
                song.cover_url = chart.cover.split("/")[-1].split("?")[0]
            if not getattr(song, "level", ""):
                song.level = chart.level
            song.is_new = bool(current_version) and chart.version == current_version
        song.rating = calculate_rating(float(song.difficulty or 0), float(song.accuracy or 0))
        song.current_rank = rank_for(float(song.accuracy or 0))

from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple, Any

from rasmai.config import ANALYSIS_CACHE_MAX
from rasmai.engine import analysis
from rasmai.storage.models import Recommendation
from rasmai.scraping.scraper import MaimaiRatingAnalyzer


ANALYSIS_TTL = timedelta(minutes=15)


IMAGES_PER_USER = 12


class BoundedImages(dict):
    """Rendered images for one analysis; the oldest go when there are too many."""

    def __setitem__(self, key, value):
        super().__setitem__(key, value)
        while len(self) > IMAGES_PER_USER:
            del self[next(iter(self))]


@dataclass
class CachedAnalysis:
    user_id: str
    region: str
    analyzer: "MaimaiRatingAnalyzer"
    recommendations: List[Recommendation]
    value_charts: Dict[str, Any]
    created: datetime = field(default_factory=datetime.now)
    checked: datetime = field(default_factory=datetime.now)     # when maimai DX NET last confirmed these scores are current
    plans: Dict[Tuple[Optional[int], bool, str], Any] = field(default_factory=dict)
    images: Dict[str, Optional[bytes]] = field(default_factory=BoundedImages)
    extras: Dict[str, Any] = field(default_factory=dict)
    analyses: Dict[Tuple[str, str], Tuple[List[Recommendation], Dict[str, Any]]] = field(default_factory=dict)   # (challenge, level filter)

    @property
    def start_rating(self) -> int:
        return int(self.analyzer.player.rating or 0) or self.analyzer.best50.total

    def analysis_for(self, challenge: str, level: Optional[str] = None) -> Tuple[List[Recommendation], Dict[str, Any]]:
        """(recommendations, summary) at a challenge level, computed on first use.

        :param challenge: How bold the targets are: ``"easy"``, ``"balanced"``, ``"hard"`` or ``"extreme"``.
        :type challenge: str
        :param level: A level (``13+``), a constant (``13.2``) or a range (``13.0-13.4``) to hold the picks to; None for everything.
        :type level: Optional[str]
        :rtype: Tuple[List[Recommendation], Dict[str, Any]]
        """
        challenge = challenge if challenge in analysis.CHALLENGES else "balanced"
        scope = str(level or "").strip() if level and analysis.constant_span(level) else ""
        key = (challenge, scope)
        if key not in self.analyses:
            a = self.analyzer
            if challenge == getattr(a, "challenge", "balanced") and not scope:
                self.analyses[key] = (self.recommendations, a.analysis_summary)
            else:
                candidates = analysis.generate_recommendations(
                    a.songs, a.play_profile, a.best50, a.chart_index, a.current_version, challenge=challenge, level=scope or None,
                )
                if not any(c.rating_gain > 0 for c in candidates) and challenge == "easy":
                    # safe steps exist but none moves this best-50: show the balanced picks and say so
                    recs, summary = self.analysis_for("balanced", scope or None)
                    summary = dict(summary or {})
                    summary["fallbackFrom"] = challenge
                    self.analyses[key] = (recs, summary)
                else:
                    recs = [a._candidate_to_recommendation(c) for c in candidates]
                    summary = analysis.summarise(candidates, a.play_profile, a.best50)
                    if scope:
                        summary = dict(summary or {})
                        summary["scope"] = analysis.describe_span(scope)
                    self.analyses[key] = (recs, summary)
        return self.analyses[key]

    def bolder_level(self, target: Optional[int], stretch: bool, challenge: str,
                     difficulty: Optional[str] = None, min_level: Optional[str] = None) -> Optional[str]:
        """The first bolder target level whose route covers the goal, when this one does not.

        Every level's route is cached, so asking costs one build the first time and
        nothing afterwards.

        :param target: The rating to reach.
        :type target: Optional[int]
        :param stretch: Whether to allow targets beyond the challenge level's usual reach.
        :type stretch: bool
        :param challenge: How bold the targets are: ``"easy"``, ``"balanced"``, ``"hard"`` or ``"extreme"``.
        :type challenge: str
        :param difficulty: The difficulty tier, such as ``"master"``.
        :type difficulty: Optional[str]
        :param min_level: Hold the route to charts at this displayed level and above.
        :type min_level: Optional[str]
        :rtype: Optional[str]
        """
        order = list(analysis.CHALLENGES)
        if stretch or challenge not in order:
            return None
        for key in order[order.index(challenge) + 1:]:
            if self.plan_for(target, stretch, key, difficulty, min_level).reached:
                return key
        return None

    def forget(self, challenge: str) -> None:
        """Drop everything built for one challenge level: its picks, its routes and its posters.

        Play counts feed the ranking, so the moment more are read the level's results are stale. A
        poster's key carries the level between colons, never at the end, so it is matched by part.

        :param challenge: The level whose results are stale.
        :type challenge: str
        """
        for key in [k for k in self.analyses if k[0] == challenge]:
            self.analyses.pop(key, None)
        for key in [k for k in self.plans if k[2] == challenge]:
            self.plans.pop(key, None)
        for key in [k for k in self.images if challenge in str(k).split(":")]:
            self.images.pop(key, None)

    def plan_for(self, target: Optional[int], stretch: bool, challenge: str = "balanced",
                 difficulty: Optional[str] = None, min_level: Optional[str] = None):
        challenge = challenge if challenge in analysis.CHALLENGES else "balanced"
        key = (target, stretch, challenge, difficulty or "", min_level or "")
        if key not in self.plans:
            a = self.analyzer
            if target is None and not stretch and not difficulty and not min_level and challenge == getattr(a, "challenge", "balanced"):
                self.plans[key] = a.plan
            else:
                plan = analysis.build_plan(
                    a.songs, a.play_profile, a.best50, a.chart_index, a.current_version,
                    start_rating=self.start_rating, goal_rating=target, stretch=stretch, challenge=challenge,
                    difficulty=difficulty, min_level=min_level,
                )
                if not plan.steps and challenge == "easy":
                    # a copy: the balanced plan is cached under its own key and must not say it stood in for anything
                    plan = replace(self.plan_for(target, stretch, "balanced", difficulty, min_level), fallback_from=challenge)
                self.plans[key] = plan
        return self.plans[key]


_analysis_cache: Dict[str, CachedAnalysis] = {}


def cache_get(user_id: str) -> Optional[CachedAnalysis]:
    cached = _analysis_cache.get(user_id)
    if cached and datetime.now() - cached.created < ANALYSIS_TTL:
        return cached
    _analysis_cache.pop(user_id, None)
    return None


def cache_put(cached: CachedAnalysis) -> None:
    _analysis_cache[cached.user_id] = cached
    while len(_analysis_cache) > ANALYSIS_CACHE_MAX:
        oldest = min(_analysis_cache, key=lambda k: _analysis_cache[k].created)
        _analysis_cache.pop(oldest, None)


def forget_analysis(user_id: str) -> None:
    _analysis_cache.pop(user_id, None)


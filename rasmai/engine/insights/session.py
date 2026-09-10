from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from rasmai.engine.analysis import Best50, ChartIndex, PlanOption, PlayProfile, _plan_options, challenge_for


def plan_credits(plan: Any) -> int:
    """Credits a route should take at its odds: one over the chance of each step, capped.

    :param plan: The route to a rating target.
    :type plan: Any
    :rtype: int
    """
    return int(round(sum(min(8.0, 1.0 / max(0.12, step.option.feasibility)) for step in plan.steps)))


@dataclass
class SessionPlay:
    option: PlanOption
    attempt: int              # first, second or third try on this chart tonight
    gain: int                 # what the target adds to the best-50 if it lands
    chance: float             # chance this particular credit is the one that lands it
    expected: float           # rating this credit is worth, on average
    cumulative: float = 0.0


@dataclass
class Session:
    credits: int
    start_rating: int
    plays: List[SessionPlay] = field(default_factory=list)

    @property
    def expected_total(self) -> float:
        return sum(play.expected for play in self.plays)

    @property
    def any_lands(self) -> float:
        """Chance that at least one target of the night lands.

        :rtype: float
        """
        miss = 1.0
        for play in self.plays:
            miss *= 1.0 - play.option.feasibility
        return 1.0 - miss

    @property
    def distinct_charts(self) -> int:
        return len({play.option.key for play in self.plays})


def build_session(songs: Sequence[Any], profile: PlayProfile, best50: Best50, chart_index: ChartIndex,
                  current_version: int, start_rating: int, credits: int = 6, challenge: str = "balanced",
                  difficulty: Optional[str] = None, max_attempts: int = 3) -> Session:
    """Spend a fixed number of credits where each one is worth the most rating.

    A credit on a chart is worth gain x odds; a second credit on the same chart is worth
    the same only if the first missed, so repeats fall off geometrically and a chart is
    tried at most three times. Warm-ups come first, long shots after the second credit.

    :param songs: The player's scored charts.
    :type songs: Sequence[Any]
    :param profile: How the player plays, as measured from their scores.
    :type profile: PlayProfile
    :param best50: The player's two rating pools.
    :type best50: Best50
    :param chart_index: The chart database to look constants and metadata up in.
    :type chart_index: ChartIndex
    :param current_version: The game version the player is on.
    :type current_version: int
    :param start_rating: The rating the route starts from.
    :type start_rating: int
    :param credits: How many credits the session is worth.
    :type credits: int
    :param challenge: How bold the targets are: ``"easy"``, ``"balanced"`` or ``"hard"``.
    :type challenge: str
    :param difficulty: The difficulty tier, such as ``"master"``.
    :type difficulty: Optional[str]
    :param max_attempts: Most tries before giving up.
    :type max_attempts: int
    :rtype: Session
    """
    mode = challenge_for(challenge)
    options = _plan_options(songs, profile, chart_index, current_version, 0.08, True, mode.plan_sigmas, mode.slack)
    wanted = str(difficulty or "").lower() or None
    if wanted:
        options = [option for option in options if option.difficulty_type == wanted]
    simulated = Best50(best50.new_pool.clone(), best50.old_pool.clone())

    def best_target(key: Tuple[str, str, str]) -> Optional[Tuple[PlanOption, int]]:
        """The target rank on this chart worth the most in expectation, against the simulated best-50.

        :param key: The chart, as ``(title, chart type, difficulty)``.
        :type key: Tuple[str, str, str]
        :rtype: Optional[Tuple[PlanOption, int]]
        """
        choice: Optional[Tuple[PlanOption, int]] = None
        value = 0.0
        for option in options:
            if option.key != key:
                continue
            gain = simulated.gain_if(option.key, option.is_new, option.target_rating)
            if gain <= 0:
                continue
            worth = gain * option.feasibility
            if worth > value:
                choice, value = (option, gain), worth
        return choice

    keys = list(dict.fromkeys(option.key for option in options))
    attempts: Dict[Tuple[str, str, str], int] = {}
    taken: Dict[Tuple[str, str, str], Tuple[PlanOption, int]] = {}
    plays: List[SessionPlay] = []
    for _credit in range(max(1, credits)):
        best: Optional[Tuple[Tuple[str, str, str], PlanOption, int, float]] = None
        best_value = 0.0
        for key in keys:
            tries = attempts.get(key, 0)
            if tries >= max_attempts:
                continue
            target = taken.get(key) or best_target(key)
            if target is None:
                continue
            option, gain = target
            p = option.feasibility
            marginal = gain * p * (1.0 - p) ** tries * (0.75 if option.is_unplayed else 1.0)
            if marginal > best_value:
                best, best_value = (key, option, gain, p), marginal
        if best is None:
            break
        key, option, gain, p = best
        tries = attempts.get(key, 0)
        if key not in taken:
            taken[key] = (option, gain)
            simulated.pool_for(option.is_new).apply(option.key, option.target_rating)   # later picks see the slot taken
        attempts[key] = tries + 1
        chance = p * (1.0 - p) ** tries
        plays.append(SessionPlay(option=option, attempt=tries + 1, gain=gain, chance=chance, expected=gain * chance))

    # warm-ups first: the two surest plays open, then everything by difficulty with repeats together
    plays.sort(key=lambda play: (play.option.constant, play.option.key, play.attempt))
    sure = [play for play in plays if play.option.feasibility >= 0.35]
    opening = sorted(sure, key=lambda play: -play.option.feasibility)[:2]
    rest = [play for play in plays if play not in opening]
    ordered = opening + sorted(rest, key=lambda play: (play.option.constant, play.option.key, play.attempt))
    running = 0.0
    for play in ordered:
        running += play.expected
        play.cumulative = running
    return Session(credits=credits, start_rating=start_rating, plays=ordered)

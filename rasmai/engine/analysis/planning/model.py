import statistics
from dataclasses import dataclass
from typing import List, Optional, Tuple


@dataclass
class PlanOption:
    key: Tuple[str, str, str]
    title: str
    chart_type: str
    difficulty_type: str
    level: str
    constant: float
    cover: str
    is_new: bool
    is_unplayed: bool
    current_accuracy: float
    current_rank: str
    target_accuracy: float
    target_rank: str
    target_rating: int
    feasibility: float
    affinity: float
    above_curve: float          # how far the target sits above the player's usual score here
    plays: int = 0
    expected: float = 0.0


@dataclass
class PlanStep:
    option: PlanOption
    gain: int
    cumulative: int
    fills_gap: bool = False       # added after the played charts ran out, to cover the rest


@dataclass
class Plan:
    goal_rating: int
    start_rating: int
    steps: List[PlanStep]

    fallback_from: Optional[str] = None   # set when an easier level had nothing and this plan stands in

    @property
    def total(self) -> int:
        return self.steps[-1].cumulative if self.steps else 0

    @property
    def needed(self) -> int:
        return max(0, self.goal_rating - self.start_rating)

    @property
    def reached(self) -> bool:
        return self.total >= self.needed

    @property
    def shortfall(self) -> int:
        return max(0, self.needed - self.total)

    @property
    def average_stretch(self) -> float:
        if not self.steps:
            return 0.0
        return statistics.fmean(step.option.above_curve for step in self.steps)

    @property
    def expected_gain(self) -> float:
        """Rating the plan is worth once each step's odds are taken into account.

        :returns: The rating the route is worth once the odds are counted.
        :rtype: float
        """
        return sum(step.gain * step.option.feasibility for step in self.steps)

    @property
    def gap_steps(self) -> List["PlanStep"]:
        """Steps on charts the player has never played, added to close the gap.

        :returns: The steps played on charts the player has never touched.
        :rtype: List['PlanStep']
        """
        return [step for step in self.steps if step.fills_gap]

    @property
    def gap_gain(self) -> int:
        return sum(step.gain for step in self.gap_steps)


def next_milestone(rating: int, step: int = 1000) -> int:
    return (rating // step + 1) * step


GAP_STEPS = 8      # never-played charts the plan may add once the played ones run out


LADDER_ROWS = 6      # rank targets shown per chart: the nearest ones above the current score

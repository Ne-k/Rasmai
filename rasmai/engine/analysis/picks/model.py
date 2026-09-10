from dataclasses import dataclass

MAX_UNPLAYED_PICKS = 6     # unplayed charts allowed among the picks; the New charts view is where the rest belong


MIN_PICKS = 12             # a shorter list of played picks than this is continued with charts worth a first run


DROPPED_BEST_STRETCH = 0.5 # how far past its first-pass estimate a chart whose best was a dropped run may be aimed, in spreads


@dataclass
class ScoredCandidate:
    title: str
    chart_type: str
    difficulty_type: str
    level: str
    constant: float
    genre: str
    artist: str
    cover: str
    is_new: bool
    is_unplayed: bool
    current_accuracy: float
    current_rating: int
    target_accuracy: float
    target_rating: int
    target_rank: str
    current_rank: str
    chart_gain: int
    rating_gain: int
    feasibility: float
    affinity: float
    score: float
    fc_status: str
    category: str
    reason: str
    required_accuracy: float = 0.0   # achievement needed before this counts at all
    reach_gap: float = 0.0           # how far that is beyond a realistic score
    plays: int = 0                   # how often the player has played this chart
    expected: float = 0.0            # what they score here when they try

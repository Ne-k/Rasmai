from dataclasses import dataclass, field
from typing import Dict, Optional


@dataclass
class SongInfo:
    rank: int = 0
    name: str = ""
    genre: str = ""
    difficulty: float = 0.0
    accuracy: float = 0.0
    rating: int = 0
    fc_status: str = ""
    is_new: bool = True
    potential_gains: Dict[str, Optional[int]] = field(default_factory=dict)
    current_rank: str = ""
    target_accuracy: float = 0.0
    target_rank: str = ""
    potential_gain: int = 0
    target_rating: int = 0
    is_value_chart: bool = False
    value_chart_reason: str = ""
    level: str = ""
    s_rating: int = 0
    s_plus_rating: int = 0
    ss_rating: int = 0
    ss_plus_rating: int = 0
    sss_rating: int = 0
    sss_plus_rating: int = 0
    cover_url: str = ""
    artist: str = ""
    chart_constants: Dict = field(default_factory=dict)
    difficulty_type: str = ""
    chart_type: str = ""
    dx_score: int = 0
    fs_status: str = ""
    constant_estimated: bool = False   # the chart database did not know this chart, so the constant is guessed from its level
    official_idx: str = ""


@dataclass
class PlayerInfo:
    name: str = ""
    rating: int = 0
    dan: str = ""
    title: str = ""
    title_type: str = "normal"
    fc: int = 0
    fc_plus: int = 0
    clears: int = 0
    ap: int = 0
    ap_plus: int = 0
    version_play_count: int = 0
    new_songs_total: int = 0
    new_songs_avg: int = 0
    old_songs_total: int = 0
    old_songs_avg: int = 0
    icon_url: str = ""
    avatar_base64: str = ""
    player_id: str = ""
    trophy: str = ""
    region: str = ""
    game_version: str = ""
    stars: int = 0
    total_play_count: int = 0
    course_rank_url: str = ""
    class_rank_url: str = ""


@dataclass
class Recommendation:
    song: str
    difficulty: float
    current_accuracy: float
    target_accuracy: float
    current_rating: int
    target_rating: int
    potential_gain: int
    max_possible_gain: int
    current_rank: str
    target_rank: str
    fc_status: str
    is_new: bool
    priority_score: float
    effort_score: float
    efficiency: float
    is_value_chart: bool = False
    value_chart_reason: str = ""
    level: str = ""
    cover_url: str = ""
    artist: str = ""
    is_unplayed: bool = False
    feasibility: float = 0.0
    required_accuracy: float = 0.0
    chart_type: str = ""
    difficulty_type: str = ""
    category: str = ""
    plays: int = 0
    expected: float = 0.0
    estimated: bool = False            # the chart is not in the database yet; its constant is guessed from its level

from dataclasses import dataclass
from typing import Dict, Iterable, List, Tuple
import numpy as np

Key = Tuple[str, str, str]

# What it takes to be shown anything. These are about how few people a number may stand on, so
# raising one is always safe and lowering one is a privacy decision.
MIN_COHORT = 20                # players in the cohort before it says anything
MIN_ACCOUNT_SCORES = 30        # an account with fewer scored charts adds nothing to the fit
MIN_PLAYERS_DIFFICULTY = 12    # players on a chart before its observed difficulty is shown

TARGET = 99.0                  # a best of at least this counts as having beaten the chart (SS)
RIDGE_TAU = 0.7                # prior spread of one chart's offset, in logit units: thin charts shrink to zero
LIST_Z = 1.0                   # a chart reads harder/easier only when its offset is this many standard errors
LIST_MIN_GAP = 0.10            # ... and the beat rate at least this far (ten points) from the expected one
BAND = 0.5                     # a chart is compared with the charts within this many levels of its constant


@dataclass
class Cohort:
    """Everyone's best score per chart, as plain arrays: row u holds ``vals[indptr[u]:indptr[u+1]]`` on charts ``cols[...]``.

    ``tags`` is an opaque stand-in for each account, only ever used to leave the viewer out of their own neighbours.
    """
    keys: List[Key]
    constants: np.ndarray
    ratings: np.ndarray
    tags: List[bytes]
    indptr: np.ndarray
    cols: np.ndarray
    vals: np.ndarray

    @property
    def players(self) -> int:
        return len(self.ratings)

    def owners(self) -> np.ndarray:
        return np.repeat(np.arange(self.players), np.diff(self.indptr))

    def without(self, tag: bytes) -> "Cohort":
        """The same cohort with one account's row taken out."""
        if tag not in self.tags:
            return self
        keep = np.array([t != tag for t in self.tags])
        sizes = np.diff(self.indptr)
        entries = np.repeat(keep, sizes)
        return Cohort(self.keys, self.constants, self.ratings[keep], [t for t in self.tags if t != tag],
                      np.concatenate(([0], np.cumsum(sizes[keep]))), self.cols[entries], self.vals[entries])


def build_cohort(accounts: Iterable[Tuple[bytes, float, Dict[Key, float]]], constants: Dict[Key, float]) -> Cohort:
    """Pack accounts as ``(tag, rating, {chart: best})`` into arrays, in an order that does not depend on how they arrived.

    The columns are the charts in ``constants``; scores on other charts are dropped, and so are accounts
    left with too few scores to compare. Accounts are consumed one at a time, so a generator keeps memory
    to the arrays.
    """
    keys = sorted(constants)
    column = {key: i for i, key in enumerate(keys)}
    rows = []
    for tag, rating, scores in accounts:
        pairs = sorted((column[key], float(score)) for key, score in scores.items() if key in column and score > 0)
        if rating > 0 and len(pairs) >= MIN_ACCOUNT_SCORES:
            rows.append((float(rating), bytes(tag), np.array([c for c, _v in pairs], dtype=np.int32),
                         np.array([v for _c, v in pairs], dtype=np.float32)))
    rows.sort(key=lambda row: (row[0], row[1]))
    sizes = [len(row[2]) for row in rows]
    return Cohort(
        keys, np.array([constants[key] for key in keys], dtype=np.float64),
        np.array([row[0] for row in rows], dtype=np.float64), [row[1] for row in rows],
        np.concatenate(([0], np.cumsum(sizes))).astype(np.int64),
        np.concatenate([row[2] for row in rows]) if rows else np.zeros(0, dtype=np.int32),
        np.concatenate([row[3] for row in rows]) if rows else np.zeros(0, dtype=np.float32))


def _sigmoid(z: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(z, -30.0, 30.0)))


@dataclass
class Difficulty:
    """What the fit found, per chart: ``(rate, expected, players, offset, error)``.

    ``rate`` is the share of the players who played it that reached ``TARGET``, ``expected`` the share players of
    their rating reach on charts of the same level, and ``offset`` and ``error`` the shrunk log-odds between the two.
    """
    charts: Dict[Key, Tuple[float, float, int, float, float]]


def lean(rate: float, expected: float, offset: float, error: float) -> str:
    """Whether a chart is clearly harder or easier than charts of its level: the offset is clear of its error and the rates are apart."""
    if abs(offset) < LIST_Z * error or abs(rate - expected) < LIST_MIN_GAP:
        return "same"
    return "harder" if offset < 0 else "easier"


def fit_difficulty(cohort: Cohort) -> Difficulty:
    """How often do the people who played each chart reach ``TARGET`` on it, against how often players of their rating do on charts of its level?

    One logistic curve is fitted over every (player, chart) pair: P(best >= TARGET) from the player's rating
    and a separate base for each half-level of constant (``BAND``), std and dx apart. Each chart then gets an offset on top of
    that, with a ridge prior, so a chart few people have played stays at what its level says.

    The comparison is with charts of the same level on purpose. It first measured how hard a chart was in
    levels, with one slope for the constant, and on real players that gave nonsense: people only play charts
    they can mostly clear, so the clear rate hardly falls as the constant rises, the fitted slope came out at
    0.29 a level where about 1.5 is believable, and every shift was multiplied by four or five. Charts of the
    same level need no slope, and a shift is read as a rate.

    What this measures is how the people who played a chart did on it. People pick charts, and a chart that
    suits its players clears more often than a random player of the same rating would clear it, so some of
    what shows is taste. It is a second opinion on the number, not a replacement.
    """
    if cohort.players == 0 or not len(cohort.cols):
        return Difficulty({})
    rows, cols = cohort.owners(), cohort.cols
    y = (cohort.vals >= TARGET).astype(np.float64)
    r = (cohort.ratings - cohort.ratings.mean())[rows] / 1000.0
    # a chart is compared with others of its type as well as its level: on the real players std charts were cleared
    # a good deal less often than dx charts of the same constant, and without this two thirds of them read as harder
    labelled = np.array([[int(np.floor(c / BAND)), int(key[1] == "dx")] for key, c in zip(cohort.keys, cohort.constants)])
    _unique, band = np.unique(labelled, axis=0, return_inverse=True)
    band = band.reshape(-1)
    bands = int(band.max()) + 1
    x = np.zeros((len(y), bands + 1))
    x[np.arange(len(y)), band[cols]] = 1.0
    x[:, bands] = r
    # a thin band is drawn gently toward the rest; the rating slope is left free
    ridge = np.concatenate([np.full(bands, 1e-2), [1e-6]])
    mean = float(y.mean())
    beta = np.zeros(bands + 1)
    beta[:bands] = float(np.log((mean + 1e-3) / (1.0 - mean + 1e-3)))
    for _ in range(40):
        p = _sigmoid(x @ beta)
        step = np.linalg.solve(x.T @ (x * (p * (1.0 - p))[:, None]) + np.diag(ridge), x.T @ (y - p) - ridge * beta)
        beta += step
        if float(np.abs(step).max()) < 1e-7:
            break
    base = x @ beta
    size = len(cohort.keys)
    count = np.bincount(cols, minlength=size)
    offset = np.zeros(size)
    for _ in range(40):
        p = _sigmoid(base + offset[cols])
        grad = np.bincount(cols, weights=y - p, minlength=size) - offset / RIDGE_TAU ** 2
        info = np.bincount(cols, weights=p * (1.0 - p), minlength=size) + 1.0 / RIDGE_TAU ** 2
        step = grad / info
        offset += step
        if float(np.abs(step).max()) < 1e-6:
            break
    p = _sigmoid(base + offset[cols])
    info = np.bincount(cols, weights=p * (1.0 - p), minlength=size) + 1.0 / RIDGE_TAU ** 2
    seen = np.maximum(count, 1)
    rate = np.bincount(cols, weights=y, minlength=size) / seen
    expected = np.bincount(cols, weights=_sigmoid(base), minlength=size) / seen
    out: Dict[Key, Tuple[float, float, int, float, float]] = {}
    for i, key in enumerate(cohort.keys):
        if count[i] >= MIN_PLAYERS_DIFFICULTY:
            out[key] = (float(rate[i]), float(expected[i]), int(count[i]), float(offset[i]), 1.0 / float(np.sqrt(info[i])))
    return Difficulty(out)

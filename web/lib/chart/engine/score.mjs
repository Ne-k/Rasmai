// Score keeping: a port of GameScoreList.SetResult / achievement / DX score / combo flags, JudgeResultSt.UpdateScore, UserRate.
import { T, K, SCORE, convertJudge, BOX, isFast, isLate } from './timing.mjs';

export const COMBO = Object.freeze({ None: 0, Silver: 1, Gold: 2, AllPerfect: 3, AllPerfectPlus: 4 });   // PlayComboflagID: none / FC / FC+ / AP / AP+
export const COMBO_NAMES = ['', 'FC', 'FC+', 'AP', 'AP+'];

export class ScoreKeeper {
  // kinds: the EScoreType of every scoring note, in note order (connected slide pieces do not score and are not listed)
  constructor(kinds) {
    this.kinds = kinds;
    this.res = kinds.map(() => null);                  // per note: {kind, timing, score, bonus, deluxe}
    this.allPerfect = kinds.reduce((s, k) => s + SCORE[k][T.Critical], 0);
    this.breakBonusTotal = kinds.reduce((s, k) => s + (k === K.Break ? SCORE[K.BreakBonus][T.Critical] : 0), 0);
    this.combo = 0; this.maxCombo = 0;
    this.sumScore = 0; this.sumBonus = 0; this.sumTheory = 0; this.sumDx = 0; this.judged = 0;
    this.counts = { critical: 0, perfect: 0, great: 0, good: 0, miss: 0 };
    this.byKind = Array.from({ length: 5 }, () => new Array(15).fill(0));   // [EScoreType][ETiming]
    this.fast = 0; this.late = 0;
  }

  setResult(index, kind, timing) {
    if (this.res[index]) return false;
    const bonus = kind === K.Break ? SCORE[K.BreakBonus][timing] : 0;
    const box = convertJudge(timing);
    const deluxe = box === BOX.Critical ? 3 : box === BOX.Perfect ? 2 : box === BOX.Great ? 1 : 0;
    this.res[index] = { kind, timing, score: SCORE[kind][timing], bonus, deluxe };
    this.judged++;
    this.sumScore += SCORE[kind][timing]; this.sumBonus += bonus; this.sumDx += deluxe;
    this.byKind[kind][timing]++;
    if (timing === T.TooFast || timing === T.TooLate) this.combo = 0; else this.combo++;
    if (this.combo > this.maxCombo) this.maxCombo = this.combo;
    this.counts[['miss', 'good', 'great', 'perfect', 'critical'][box]]++;
    if (isFast(timing)) this.fast++; else if (isLate(timing)) this.late++;
    return true;
  }

  get done() { return this.judged >= this.kinds.length; }
  // percent, 0..101 (decimal in the game; plain double here, which is exact for these sums)
  get achievement() {
    if (!this.allPerfect) return 0;
    return (this.sumScore / this.allPerfect) * 100 + (this.breakBonusTotal ? (this.sumBonus / this.breakBonusTotal) * 1 : 0);
  }
  get dxScore() { return this.sumDx; }
  get dxMax() { return this.kinds.length * 3; }
  get missCount() { return this.counts.miss; }
  // PlayComboflagID for a finished play
  get comboType() {
    const c = this.counts;
    if (c.miss || !this.kinds.length) return COMBO.None;
    if (this.achievement >= 101 - 1e-9 || (!this.breakBonusTotal && this.achievement >= 100 - 1e-9)) return COMBO.AllPerfectPlus;
    if (c.good === 0 && c.great === 0) return COMBO.AllPerfect;
    if (c.good === 0) return COMBO.Gold;
    return COMBO.Silver;
  }
}

// MusicClearrankID: achievement is compared as an integer percent x 10000 (GameManager.ConvAchiveDecimalToInt)
export const RANK_NAMES = ['D', 'C', 'B', 'BB', 'BBB', 'A', 'AA', 'AAA', 'S', 'S+', 'SS', 'SS+', 'SSS', 'SSS+'];
export const achieveInt = (pct) => Math.floor(pct * 10000 + 1e-6);
// thresholds = [achieve of rank id 1 .. 13] ascending, from A000/musicClearRank (rank id 0 = D is "below the first")
export function clearRank(pct, thresholds) {
  const a = achieveInt(pct);
  for (let i = 0; i < thresholds.length; i++) if (a < thresholds[i]) return i;
  return thresholds.length;                            // SSS+
}

// UserRate: the rating one score is worth (RatingTableID records: [minimum achievement, offset])
export const RATING_TABLE = [[0, 0], [100000, 16], [200000, 32], [300000, 48], [400000, 64], [500000, 80], [600000, 96], [700000, 112], [750000, 120],
  [799999, 128], [800000, 136], [900000, 152], [940000, 168], [969999, 176], [970000, 200], [980000, 203], [989999, 206], [990000, 208],
  [995000, 211], [999999, 214], [1000000, 216], [1004999, 222], [1005000, 224]];
export function singleRate(levelTimes10, achievementPct, comboType) {
  const a = Math.min(achieveInt(achievementPct), 1005000);
  let offset = 0;
  for (let i = RATING_TABLE.length - 1; i >= 0; i--) if (RATING_TABLE[i][0] <= a) { offset = RATING_TABLE[i][1]; break; }
  const ap = comboType >= COMBO.AllPerfect ? 1 : 0;      // ApBonusTable: +1 for AP and AP+
  return Math.floor((levelTimes10 * a * offset) / 100000000) + ap;
}

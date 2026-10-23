"""In-play soccer: how the prices move while the match is being played.

MODEL
-----
Goals arrive as two Poisson processes whose intensity changes with

  * TIME    : expected goals are spread over the 90 + stoppage minutes by a profile w(t)
              (slightly more goals late in each half; first half holds ~45.5 % of the goals);
  * SCORE   : the team that is ahead by d goals scores at rate  exp(-beta * d)  times its base rate,
              the team that is behind at  exp(+beta * d)   ("score effects": trailing teams push);
  * RED CARD: a team with a man less scores at exp(-red_own) and concedes at exp(+red_opp).

Because the rates depend on the goal difference, the final score cannot be read from a plain
Poisson shift; instead the probability table over (extra home goals i, extra away goals j) is
stepped forward minute by minute (a Markov chain, solved by dynamic programming):

    P_{t+1}(i, j) = P_t(i, j) (1-p_h)(1-p_a) + P_t(i-1, j) p_h (1-p_a) + P_t(i, j-1) (1-p_h) p_a
                    + P_t(i-1, j-1) p_h p_a,              p_h = 1 - exp(-lam * w_t * m_h(i - j))

With beta = 0 and no red cards this reduces EXACTLY to independent Poisson counts over the
remaining time (checked in the tests).  beta, red_own, red_opp are priors from the literature,
not calibrated to your data yet (see prompts/06 for the calibration task).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from ..markets.scoredist import ScoreDist


@dataclass
class InPlayParams:
    beta_score: float = 0.08     # score-effect strength per goal of difference
    red_own: float = 0.25        # own scoring drops by exp(-0.25) ~ -22 % per red card
    red_opp: float = 0.20        # opponent scoring rises by exp(+0.20) ~ +22 % per red card
    h1_share: float = 0.455      # share of a match's expected goals scored in the first half
    ramp: float = 0.20           # intensity rises linearly ~ +/-10 % across each half
    stoppage1: int = 2           # expected added minutes, first half
    stoppage2: int = 5           # expected added minutes, second half
    max_extra: int = 10          # goals beyond the current score that we track
    diff_clip: int = 3           # score effect saturates at +/- 3 goals


@dataclass
class SoccerState:
    phase: str = "pre"           # pre | h1 | ht | h2 | ft
    minute: float = 0.0          # displayed clock, 47.0 == 45'+2'
    home: int = 0
    away: int = 0
    red_home: int = 0
    red_away: int = 0
    goals: List[str] = field(default_factory=list)   # scorers in order: "h" / "a"

    def lead_history(self) -> Tuple[int, int]:
        """(max lead ever held by home, max lead ever held by away) from the goal sequence."""
        d = mh = ma = 0
        for g in self.goals:
            d += 1 if g == "h" else -1
            mh, ma = max(mh, d), max(ma, -d)
        return mh, ma


# ------------------------------------------------------------------ time profile
def half_weights(p: InPlayParams) -> Tuple[np.ndarray, np.ndarray]:
    """Expected-goal weight of each minute of play (first half, second half); they sum to 1 together."""
    def one(length: int, share: float) -> np.ndarray:
        u = np.linspace(0.0, 1.0, length + 1)
        cum = u + p.ramp * (u ** 2 / 2.0 - u / 2.0)      # integral of 1 + ramp (u - 1/2); cum[-1] = 1
        return share * np.diff(cum)
    return one(45 + p.stoppage1, p.h1_share), one(45 + p.stoppage2, 1.0 - p.h1_share)


def elapsed_steps(p: InPlayParams, st: SoccerState) -> int:
    """How many 1-minute steps of the full timeline are already gone."""
    l1, l2 = 45 + p.stoppage1, 45 + p.stoppage2
    if st.phase == "pre":
        return 0
    if st.phase == "h1":
        return int(min(max(np.floor(st.minute), 0), l1 - 1))
    if st.phase == "ht":
        return l1
    if st.phase == "h2":
        return l1 + int(min(max(np.floor(st.minute - 45), 0), l2 - 1))
    return l1 + l2


def remaining_weights(p: InPlayParams, st: SoccerState, first_half_only: bool = False) -> np.ndarray:
    w1, w2 = half_weights(p)
    full = np.concatenate([w1, w2])
    i0 = elapsed_steps(p, st)
    if first_half_only:
        return full[i0:len(w1)] if i0 < len(w1) else np.zeros(0)
    return full[i0:]


# ------------------------------------------------------------------ dynamic programming
def _mults(p: InPlayParams, D, red_h: int, red_a: int):
    dc = np.clip(D, -p.diff_clip, p.diff_clip)
    mh = np.exp(-p.beta_score * dc) * np.exp(-p.red_own * red_h + p.red_opp * red_a)
    ma = np.exp(+p.beta_score * dc) * np.exp(-p.red_own * red_a + p.red_opp * red_h)
    return mh, ma


def _step_pmfs(rate: np.ndarray, kmax: int = 3) -> List[np.ndarray]:
    """P(k goals in one minute) for k = 0..kmax, for an array of rates (Poisson)."""
    e = np.exp(-rate)
    out, term = [e], e
    for k in range(1, kmax + 1):
        term = term * rate / k
        out.append(term)
    return out


def run_dp(lam: float, mu: float, st: SoccerState, weights: np.ndarray, p: InPlayParams,
           scale: Tuple[float, float] = (1.0, 1.0), snapshots: Optional[Dict[int, np.ndarray]] = None,
           snap_steps: Sequence[int] = ()) -> np.ndarray:
    """Distribution of (extra home goals, extra away goals) over the given time weights."""
    K = p.max_extra + 1
    I = np.arange(K)[:, None]
    J = np.arange(K)[None, :]
    D = (st.home + I) - (st.away + J)
    mh, ma = _mults(p, D, st.red_home, st.red_away)
    ls, ms = lam * scale[0], mu * scale[1]
    cur = np.zeros((K, K))
    cur[0, 0] = 1.0
    snap = set(snap_steps)
    for step, wt in enumerate(weights):
        if snapshots is not None and step in snap:
            snapshots[step] = cur.copy()
        ph = _step_pmfs(ls * wt * mh)
        pa = _step_pmfs(ms * wt * ma)
        new = np.zeros_like(cur)
        for k in range(4):
            for l in range(4):
                term = cur * ph[k] * pa[l]
                new[k:, l:] += term[:K - k, :K - l]
        cur = new / new.sum()
    if snapshots is not None and len(weights) in snap:
        snapshots[len(weights)] = cur.copy()
    return cur


def calibrate_scale(lam: float, mu: float, p: InPlayParams, iters: int = 4) -> Tuple[float, float]:
    """Rescale the base rates so that the full-match DP reproduces the pre-match expected goals.

    Score effects and stoppage bookkeeping slightly change the average number of goals; this keeps
    the in-play model consistent with the fitted Dixon-Coles means at kickoff.
    """
    w = remaining_weights(p, SoccerState())
    kh = km = 1.0
    K = p.max_extra + 1
    for _ in range(iters):
        G = run_dp(lam, mu, SoccerState(), w, p, (kh, km))
        eh = float((G.sum(axis=1) * np.arange(K)).sum())
        ea = float((G.sum(axis=0) * np.arange(K)).sum())
        kh *= lam / max(eh, 1e-9)
        km *= mu / max(ea, 1e-9)
    return kh, km


def _tilt_slice(R: np.ndarray, h0: int, a0: int, K: int) -> np.ndarray:
    """Part of the terminal tilt R (indexed by FINAL score) that applies to cells (h0+i, a0+j)."""
    out = np.ones((K, K))
    rh, ra = R.shape
    ni, nj = max(0, min(K, rh - h0)), max(0, min(K, ra - a0))
    if ni > 0 and nj > 0:
        out[:ni, :nj] = R[h0:h0 + ni, a0:a0 + nj]
    return out


def inplay_dist(lam: float, mu: float, st: SoccerState, p: InPlayParams,
                scale: Tuple[float, float] = (1.0, 1.0), tilt: Optional[np.ndarray] = None) -> ScoreDist:
    """Final-score distribution given the current state.

    `tilt` (optional) is R[x, y] = G_DC[x, y] / G_DP0[x, y]: it re-weights the terminal scores so that at
    kickoff the in-play model reproduces the pre-match Dixon-Coles table EXACTLY (no jump at 0'), and
    lets the low-score correlation (rho) keep working later in the match.
    """
    w = remaining_weights(p, st)
    K = p.max_extra + 1
    if len(w) == 0:
        G = np.zeros((K, K))
        G[0, 0] = 1.0
    else:
        G = run_dp(lam, mu, st, w, p, scale)
        if tilt is not None:
            G = G * _tilt_slice(tilt, st.home, st.away, K)
            G = G / G.sum()
    return ScoreDist(G, st.home, st.away)


def make_tilt(lam: float, mu: float, rho: float, p: InPlayParams, scale: Tuple[float, float],
              max_goals: int = 10) -> np.ndarray:
    """Terminal re-weighting that aligns the DP model with Dixon-Coles at kickoff."""
    from ..models.dixon_coles import dc_grid
    g_dc = dc_grid(lam, mu, rho, max_goals)
    g_dp = run_dp(lam, mu, SoccerState(), remaining_weights(p, SoccerState()), p, scale)
    n = min(g_dc.shape[0], g_dp.shape[0])
    R = np.ones((n, n))
    a, b = g_dc[:n, :n], g_dp[:n, :n]
    ok = b > 1e-12
    R[ok] = a[ok] / b[ok]
    return np.clip(R, 0.05, 20.0)


def first_half_dist(lam: float, mu: float, st: SoccerState, p: InPlayParams,
                    scale: Tuple[float, float] = (1.0, 1.0)) -> Optional[ScoreDist]:
    """Distribution of the HALF-TIME score (only before the break)."""
    if st.phase not in ("pre", "h1"):
        return None
    w = remaining_weights(p, st, first_half_only=True)
    if len(w) == 0:
        G = np.zeros((p.max_extra + 1, p.max_extra + 1))
        G[0, 0] = 1.0
    else:
        G = run_dp(lam, mu, st, w, p, scale)
    return ScoreDist(G, st.home, st.away)


# ------------------------------------------------------------------ path-dependent quantities
def next_goal_probs(lam: float, mu: float, st: SoccerState, p: InPlayParams,
                    scale: Tuple[float, float] = (1.0, 1.0)) -> Dict[str, float]:
    """Who scores the next goal (or nobody): competing exponential clocks with the current rates."""
    w = remaining_weights(p, st)
    if len(w) == 0:
        return {"home": 0.0, "away": 0.0, "none": 1.0}
    mh, ma = _mults(p, np.array(st.home - st.away), st.red_home, st.red_away)
    hh = lam * scale[0] * w * float(mh)
    ha = mu * scale[1] * w * float(ma)
    ht = hh + ha
    surv = np.exp(-np.concatenate([[0.0], np.cumsum(ht)[:-1]]))
    first = surv * (1.0 - np.exp(-ht))
    share_h = hh / np.maximum(ht, 1e-15)
    ph = float(np.sum(first * share_h))
    pa = float(np.sum(first * (1.0 - share_h)))
    return {"home": ph, "away": pa, "none": float(np.exp(-ht.sum()))}


def lead_hit_prob(lam: float, mu: float, st: SoccerState, p: InPlayParams,
                  scale: Tuple[float, float], target: int, side: str = "home") -> float:
    """P(the side is ahead by >= target goals at SOME moment from now on).

    This prices the "1UP / 2UP" markets, which pay out as a win as soon as the team leads by
    1 (2) goals, even if the match is later drawn or lost.
    """
    sign = 1 if side == "home" else -1
    d0 = (st.home - st.away) * sign
    mh_lead, ma_lead = st.lead_history()
    if (mh_lead if side == "home" else ma_lead) >= target or d0 >= target:
        return 1.0
    w = remaining_weights(p, st)
    depth = 8
    dvals = np.arange(-depth, target)                 # lead of `side` in goals, non-absorbed states
    v = np.zeros(len(dvals))
    v[int(np.clip(d0, -depth, target - 1)) + depth] = 1.0
    Dh = sign * dvals
    mh, ma = _mults(p, Dh, st.red_home, st.red_away)
    if side == "home":
        rs_base, ro_base = lam * scale[0] * mh, mu * scale[1] * ma
    else:
        rs_base, ro_base = mu * scale[1] * ma, lam * scale[0] * mh
    hit = 0.0
    n = len(v)
    for wt in w:
        ps = _step_pmfs(rs_base * wt)
        po = _step_pmfs(ro_base * wt)
        new = np.zeros(n)
        for k in range(4):
            for l in range(4):
                mass = v * ps[k] * po[l]
                delta = k - l
                if delta == 0:
                    new += mass
                elif delta > 0:
                    hit += mass[n - delta:].sum()
                    new[delta:] += mass[:n - delta]
                else:
                    dd = -delta
                    new[:n - dd] += mass[dd:]
                    new[0] += mass[:dd].sum()
        v = new
    return float(min(1.0, hit))


def window_goal_probs(lam: float, mu: float, st: SoccerState, p: InPlayParams,
                      scale: Tuple[float, float], windows: Sequence[Tuple[str, int, int]]) -> Dict[str, float]:
    """P(at least one goal) in windows given as (label, first_step, last_step_exclusive) of the FULL timeline."""
    w1, w2 = half_weights(p)
    full = np.concatenate([w1, w2])
    i0 = elapsed_steps(p, st)
    rem = full[i0:]
    snaps: Dict[int, np.ndarray] = {}
    starts = [max(a, i0) - i0 for (_, a, b) in windows if b > i0]
    run_dp(lam, mu, st, rem, p, scale, snapshots=snaps, snap_steps=starts)
    K = p.max_extra + 1
    I = np.arange(K)[:, None]
    J = np.arange(K)[None, :]
    mh, ma = _mults(p, (st.home + I) - (st.away + J), st.red_home, st.red_away)
    out: Dict[str, float] = {}
    for label, a, b in windows:
        if b <= i0:
            continue
        s0, s1 = max(a, i0), b
        expo = float(full[s0:s1].sum())
        snap = snaps.get(s0 - i0)
        if snap is None:
            continue
        hazard = (lam * scale[0] * mh + mu * scale[1] * ma) * expo
        out[label] = float(1.0 - np.sum(snap * np.exp(-hazard)))
    return out

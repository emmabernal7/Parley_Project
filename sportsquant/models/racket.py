"""Point-by-point Markov models for tennis and volleyball.

TENNIS   p_a = P(A wins a point on A's serve), p_b = P(B wins a point on B's serve).
         point -> game (with deuce) -> tie-break -> set (6 games, tie-break at 6-6) -> match.
VOLLEYBALL  rally scoring: p = P(A wins a rally); a set goes to 25 (win by 2), the 5th set to 15.

Both give the exact win probability, the set-score distribution and the total-games / total-points
distribution, and can start from the middle of a match.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Dict, Optional, Tuple

import numpy as np
from scipy.optimize import brentq


# ------------------------------------------------------------------------- tennis
@lru_cache(maxsize=8192)
def _game_win_prob_cached(p: float, x: int, y: int) -> float:
    if x >= 4 and x - y >= 2:
        return 1.0
    if y >= 4 and y - x >= 2:
        return 0.0
    pd_ = p * p / (p * p + (1 - p) ** 2)
    if x >= 3 and y >= 3:
        d = x - y
        return pd_ if d == 0 else (p + (1 - p) * pd_ if d == 1 else p * pd_)
    return p * _game_win_prob_cached(p, x + 1, y) + (1 - p) * _game_win_prob_cached(p, x, y + 1)


def game_win_prob(p: float, a: int = 0, b: int = 0) -> float:
    """P(server wins the game) from point score (a, b) [a = server's points won]."""
    return _game_win_prob_cached(round(float(p), 5), a, b)


@lru_cache(maxsize=8192)
def _tiebreak_cached(pa: float, pb: float, a_first: bool, x: int, y: int) -> float:
    if x >= 7 and x - y >= 2:
        return 1.0
    if y >= 7 and y - x >= 2:
        return 0.0
    pbar = 0.5 * (pa + (1 - pb))
    pd_ = pbar * pbar / (pbar * pbar + (1 - pbar) ** 2)
    if x >= 6 and y >= 6:
        d = x - y
        return pd_ if d == 0 else (pbar + (1 - pbar) * pd_ if d == 1 else pbar * pd_)
    n = x + y
    first_serves = ((n + 1) // 2) % 2 == 0
    a_serves = first_serves if a_first else not first_serves
    p_pt = pa if a_serves else (1 - pb)
    return p_pt * _tiebreak_cached(pa, pb, a_first, x + 1, y) + (1 - p_pt) * _tiebreak_cached(pa, pb, a_first, x, y + 1)


def tiebreak_win_prob(pa: float, pb: float, a_first: bool, a_pts: int = 0, b_pts: int = 0) -> float:
    """P(A wins the 7-point tie-break).  First server serves 1 point, then serving alternates every 2."""
    return _tiebreak_cached(round(float(pa), 5), round(float(pb), 5), a_first, a_pts, b_pts)


@lru_cache(maxsize=16384)
def _set_dist_cached(pa: float, pb: float, first_a: bool, ga: int, gb: int) -> Tuple[Tuple[Tuple[int, int], float], ...]:
    if (ga >= 6 and ga - gb >= 2) or ga >= 7:
        return (((ga, gb), 1.0),)
    if (gb >= 6 and gb - ga >= 2) or gb >= 7:
        return (((ga, gb), 1.0),)
    if ga >= 6 and gb >= 6:
        tb = _tiebreak_cached(pa, pb, first_a, 0, 0)
        return (((7, 6), tb), ((6, 7), 1.0 - tb))
    hold_a = _game_win_prob_cached(pa, 0, 0)
    brk_a = 1.0 - _game_win_prob_cached(pb, 0, 0)
    a_serves = first_a if (ga + gb) % 2 == 0 else not first_a
    pg = hold_a if a_serves else brk_a
    out: Dict[Tuple[int, int], float] = {}
    for res, q in _set_dist_cached(pa, pb, first_a, ga + 1, gb):
        out[res] = out.get(res, 0.0) + pg * q
    for res, q in _set_dist_cached(pa, pb, first_a, ga, gb + 1):
        out[res] = out.get(res, 0.0) + (1 - pg) * q
    return tuple(out.items())


def set_dist(pa: float, pb: float, first_a: bool, start: Tuple[int, int] = (0, 0),
             game_pts: Optional[Tuple[int, int]] = None) -> Dict[Tuple[int, int], float]:
    """Distribution of the final set score {(games_a, games_b): prob}.

    first_a  : did A serve the first game of this set?
    start    : games already played in this set
    game_pts : points in the game in progress (server derived from the game count), or None
    """
    pa_r, pb_r = round(float(pa), 5), round(float(pb), 5)
    if game_pts is None:
        return dict(_set_dist_cached(pa_r, pb_r, first_a, start[0], start[1]))
    ga, gb = start
    server_is_a = first_a if (ga + gb) % 2 == 0 else not first_a
    if server_is_a:
        pw = game_win_prob(pa_r, game_pts[0], game_pts[1])
    else:
        pw = 1.0 - game_win_prob(pb_r, game_pts[1], game_pts[0])
    out: Dict[Tuple[int, int], float] = {}
    for res, q in _set_dist_cached(pa_r, pb_r, first_a, ga + 1, gb):
        out[res] = out.get(res, 0.0) + pw * q
    for res, q in _set_dist_cached(pa_r, pb_r, first_a, ga, gb + 1):
        out[res] = out.get(res, 0.0) + (1 - pw) * q
    return out


def tennis_match(pa: float, pb: float, best_of: int = 3, first_a: bool = True, sets: Tuple[int, int] = (0, 0),
                 games_before: int = 0, cur_games: Tuple[int, int] = (0, 0), cur_first_a: Optional[bool] = None,
                 game_pts: Optional[Tuple[int, int]] = None) -> Dict:
    """Exact distribution of the rest of a tennis match.

    Returns {"win_a", "set_scores": {(sa, sb): p}, "games": {total_games: p}}.
    games_before = games in completed sets;  cur_games = games so far in the current set.
    """
    need = best_of // 2 + 1
    in_progress = cur_games != (0, 0) or game_pts is not None
    first_cur = first_a if cur_first_a is None else cur_first_a
    states: Dict[Tuple[int, int, bool, int], float] = {}
    # finish the current set (or play the first one)
    for (ga, gb), q in set_dist(pa, pb, first_cur, cur_games if in_progress else (0, 0), game_pts).items():
        sa, sb = sets[0] + (ga > gb), sets[1] + (gb > ga)
        nxt = first_cur if (ga + gb) % 2 == 0 else not first_cur
        key = (sa, sb, nxt, games_before + ga + gb)
        states[key] = states.get(key, 0.0) + q
    final: Dict[Tuple[int, int, int], float] = {}
    for _ in range(best_of):
        nxt_states: Dict[Tuple[int, int, bool, int], float] = {}
        for (sa, sb, fa, g), q in states.items():
            if sa >= need or sb >= need:
                final[(sa, sb, g)] = final.get((sa, sb, g), 0.0) + q
                continue
            for (ga, gb), r in set_dist(pa, pb, fa).items():
                key = (sa + (ga > gb), sb + (gb > ga), fa if (ga + gb) % 2 == 0 else not fa, g + ga + gb)
                nxt_states[key] = nxt_states.get(key, 0.0) + q * r
        states = nxt_states
        if not states:
            break
    for (sa, sb, fa, g), q in states.items():          # anything left is terminal too
        final[(sa, sb, g)] = final.get((sa, sb, g), 0.0) + q
    win_a = sum(q for (sa, sb, g), q in final.items() if sa >= need and sa > sb)
    set_scores: Dict[Tuple[int, int], float] = {}
    games: Dict[int, float] = {}
    for (sa, sb, g), q in final.items():
        set_scores[(sa, sb)] = set_scores.get((sa, sb), 0.0) + q
        games[g] = games.get(g, 0.0) + q
    return {"win_a": float(win_a), "set_scores": set_scores, "games": games}


@lru_cache(maxsize=2048)
def _serve_probs_cached(p_win: float, base_serve: float, best_of: int) -> Tuple[float, float]:
    f = lambda d: tennis_match(base_serve + d, base_serve - d, best_of)["win_a"] - p_win
    lim = min(base_serve, 1 - base_serve) - 0.02
    d = brentq(f, -lim, lim, xtol=1e-4)
    return base_serve + d, base_serve - d


def serve_probs_for_win(p_win: float, base_serve: float = 0.64, best_of: int = 3) -> Tuple[float, float]:
    """Find (pa, pb) = (base + d, base - d) so that the pre-match win probability equals p_win."""
    p_win = round(float(min(0.995, max(0.005, p_win))), 4)
    return _serve_probs_cached(p_win, round(float(base_serve), 4), best_of)


# ------------------------------------------------------------------------- volleyball
def _volleyball_set_win_prob(p: float, target: int) -> float:
    """Exact probability that A wins a rally-scoring set to `target` (win by 2) from 0-0."""
    import math
    q = 1.0 - p
    p_T = p ** target
    win = 0.0
    for b in range(target - 1):
        win += math.comb(target - 1 + b, b) * p_T * (q ** b)
    deuce = math.comb(2 * target - 2, target - 1) * (p ** (target - 1)) * (q ** (target - 1))
    pd_ = (p * p) / (p * p + q * q)
    return win + deuce * pd_


def _volleyball_match_win_prob_fast(p: float, best_of: int = 5) -> float:
    s = _volleyball_set_win_prob(p, 25)
    q = 1.0 - s
    s15 = _volleyball_set_win_prob(p, 15)
    if best_of == 3:
        return s * s + 2.0 * s * q * s15
    return (s ** 3) * (1.0 + 3.0 * q) + 6.0 * (s * s) * (q * q) * s15


@lru_cache(maxsize=2048)
def _set_scores(p: float, target: int, cap: int = 30) -> Tuple[Tuple[Tuple[int, int], float], ...]:
    """Distribution of final (a, b) of a set played to `target`, win by 2."""
    W = target + cap
    dist = np.zeros((W + 2, W + 2))
    dist[0, 0] = 1.0
    out: Dict[Tuple[int, int], float] = {}
    for total in range(0, 2 * W):
        for a in range(max(0, total - W), min(total, W) + 1):
            b = total - a
            q = dist[a, b]
            if q == 0.0:
                continue
            if a >= target and a - b >= 2:
                out[(a, b)] = out.get((a, b), 0.0) + q
                continue
            if b >= target and b - a >= 2:
                out[(a, b)] = out.get((a, b), 0.0) + q
                continue
            dist[a + 1, b] += q * p
            dist[a, b + 1] += q * (1 - p)
    return tuple(out.items())


@lru_cache(maxsize=1024)
def _volleyball_prematch_cached(p_round: float, best_of: int) -> Dict:
    need = best_of // 2 + 1
    states: Dict[Tuple[int, int, int], float] = {(0, 0, 0): 1.0}
    final: Dict[Tuple[int, int, int], float] = {}
    for _ in range(best_of + 1):
        nxt: Dict[Tuple[int, int, int], float] = {}
        for (sa, sb, pts), q in states.items():
            if sa >= need or sb >= need:
                final[(sa, sb, pts)] = final.get((sa, sb, pts), 0.0) + q
                continue
            target = 15 if sa + sb == best_of - 1 else 25
            for (a, b), r in _set_scores(p_round, target):
                key = (sa + (a > b), sb + (b > a), pts + a + b)
                nxt[key] = nxt.get(key, 0.0) + q * r
        states = nxt
        if not states:
            break
    for k, q in states.items():
        final[k] = final.get(k, 0.0) + q
    win_a = sum(q for (sa, sb, _), q in final.items() if sa >= need and sa > sb)
    set_scores: Dict[Tuple[int, int], float] = {}
    pts_d: Dict[int, float] = {}
    for (sa, sb, pts), q in final.items():
        set_scores[(sa, sb)] = set_scores.get((sa, sb), 0.0) + q
        pts_d[pts] = pts_d.get(pts, 0.0) + q
    return {"win_a": float(win_a), "set_scores": set_scores, "points": pts_d}


def volleyball_match(p: float, best_of: int = 5, sets: Tuple[int, int] = (0, 0),
                     cur_points: Tuple[int, int] = (0, 0), in_set: bool = False, points_before: int = 0) -> Dict:
    """Rest of a volleyball match.  Returns {"win_a", "set_scores", "points": {total: p}}."""
    if sets == (0, 0) and not in_set and cur_points == (0, 0) and points_before == 0:
        return _volleyball_prematch_cached(round(float(p), 4), best_of)
    need = best_of // 2 + 1

    def set_target(sa: int, sb: int) -> int:
        return 15 if sa + sb == best_of - 1 else 25

    def set_dist_from(sa: int, sb: int, start: Tuple[int, int]) -> Dict[Tuple[int, int], float]:
        target = set_target(sa, sb)
        if start == (0, 0):
            return dict(_set_scores(round(float(p), 4), target))
        # start mid-set: DP from the given score
        a0, b0 = start
        W = max(target, a0, b0) + 30
        dist = np.zeros((W + 2, W + 2))
        dist[a0, b0] = 1.0
        out: Dict[Tuple[int, int], float] = {}
        for total in range(a0 + b0, 2 * W):
            for a in range(max(a0, total - W), min(total, W) + 1):
                b = total - a
                if b < b0:
                    continue
                q = dist[a, b]
                if q == 0.0:
                    continue
                if (a >= target and a - b >= 2) or (b >= target and b - a >= 2):
                    out[(a, b)] = out.get((a, b), 0.0) + q
                    continue
                dist[a + 1, b] += q * p
                dist[a, b + 1] += q * (1 - p)
        return out

    states: Dict[Tuple[int, int, int], float] = {(sets[0], sets[1], points_before): 1.0}
    final: Dict[Tuple[int, int, int], float] = {}
    first = True
    for _ in range(best_of + 1):
        nxt: Dict[Tuple[int, int, int], float] = {}
        for (sa, sb, pts), q in states.items():
            if sa >= need or sb >= need:
                final[(sa, sb, pts)] = final.get((sa, sb, pts), 0.0) + q
                continue
            start = cur_points if (first and in_set) else (0, 0)
            for (a, b), r in set_dist_from(sa, sb, start).items():
                key = (sa + (a > b), sb + (b > a), pts + a + b)
                nxt[key] = nxt.get(key, 0.0) + q * r
        first = False
        states = nxt
        if not states:
            break
    for k, q in states.items():
        final[k] = final.get(k, 0.0) + q
    win_a = sum(q for (sa, sb, _), q in final.items() if sa >= need and sa > sb)
    set_scores: Dict[Tuple[int, int], float] = {}
    pts_d: Dict[int, float] = {}
    for (sa, sb, pts), q in final.items():
        set_scores[(sa, sb)] = set_scores.get((sa, sb), 0.0) + q
        pts_d[pts] = pts_d.get(pts, 0.0) + q
    return {"win_a": float(win_a), "set_scores": set_scores, "points": pts_d}


@lru_cache(maxsize=1024)
def _rally_prob_cached(p_win: float, best_of: int) -> float:
    return float(brentq(lambda p: _volleyball_match_win_prob_fast(p, best_of) - p_win, 0.2, 0.8, xtol=1e-5))


def rally_prob_for_win(p_win: float, best_of: int = 5) -> float:
    """Rally-win probability p such that the pre-match win probability equals p_win."""
    p_win = round(float(min(0.995, max(0.005, p_win))), 4)
    return _rally_prob_cached(p_win, best_of)

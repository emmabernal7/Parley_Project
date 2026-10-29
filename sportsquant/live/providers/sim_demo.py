"""Demo matches: a small, clearly-labelled universe that keeps the app "alive" between real kickoffs.

Nothing here is a real result.  Each demo match is a single DRAW from our own Dixon-Coles /
rating model (goal minutes sampled from the model's own probabilities), replayed on a compressed
clock so a 90-minute match takes a few real minutes.  Watching it is, literally, watching a sample
path of the model that also prices the real matches elsewhere in the app - useful for seeing the
"price moves after a goal" behaviour without waiting for a real kickoff.
"""
from __future__ import annotations

import hashlib
import math
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

from ...events import Event
from ...inplay.soccer import InPlayParams, _mults, calibrate_scale, half_weights
from ...models.racket import serve_probs_for_win

# (home, away, lam, mu, rho, competition) - illustrative attack/defence priors, NOT fitted on data.
SOCCER_CARD = [
    ("Barcelona", "Galatasaray", 2.35, 0.70, -0.08, "UEFA Champions League (demo)"),
    ("Manchester City", "Brentford", 2.55, 0.60, -0.07, "Premier League (demo)"),
    ("Real Madrid", "Villarreal", 2.10, 0.85, -0.06, "La Liga (demo)"),
    ("Inter Milan", "Bologna", 1.95, 0.80, -0.07, "Serie A (demo)"),
    ("Bayern Munich", "Werder Bremen", 2.60, 0.65, -0.06, "Bundesliga (demo)"),
    ("Boca Juniors", "River Plate", 1.35, 1.15, -0.10, "Copa de la Liga (demo)"),
]
BASKETBALL_CARD = [("Los Angeles Lakers", "Boston Celtics", -1.5, 226.0, "NBA (demo)"),
                   ("Golden State Warriors", "Denver Nuggets", 2.0, 231.0, "NBA (demo)")]
TENNIS_CARD = [("Carlos Alcaraz", "Jannik Sinner", 0.50, 5, "ATP demo final"),
              ("Iga Swiatek", "Aryna Sabalenka", 0.47, 3, "WTA demo final")]

CYCLE_MINUTES = 8.0     # one full compressed "match" (kickoff to full time) takes this many real minutes


def _slot(now: datetime, cycle_minutes: float) -> Tuple[int, float]:
    """Which cycle number we're in, and the fraction of the way through it (0..1)."""
    epoch = datetime(2026, 1, 1, tzinfo=timezone.utc)
    total_min = (now - epoch).total_seconds() / 60.0
    n = int(total_min // cycle_minutes)
    frac = (total_min % cycle_minutes) / cycle_minutes
    return n, frac


def _rng_for(seed_key: str, n: int) -> random.Random:
    h = hashlib.sha256(f"{seed_key}:{n}".encode()).hexdigest()
    return random.Random(int(h[:16], 16))


def _draw_soccer_timeline(rng: random.Random, lam: float, mu: float) -> Dict:
    """One MC draw of the whole match, minute by minute, using the SAME per-minute hazard as the
    live in-play DP (models/inplay/soccer.py): this is a sample path of that exact model."""
    p = InPlayParams()
    scale = calibrate_scale(lam, mu, p)
    w1, w2 = half_weights(p)
    weights = list(w1) + list(w2)
    events: List[Dict] = []
    h = a = 0
    for minute_step, wt in enumerate(weights):
        mh, ma = _mults(p, h - a, 0, 0)
        ph = 1.0 - math.exp(-(lam * scale[0] * wt * float(mh)))
        pa = 1.0 - math.exp(-(mu * scale[1] * wt * float(ma)))
        if rng.random() < ph:
            h += 1
            events.append({"minute": minute_step + 1, "side": "h", "score": [h, a]})
        if rng.random() < pa:
            a += 1
            events.append({"minute": minute_step + 1, "side": "a", "score": [h, a]})
    return {"final": [h, a], "events": events, "total_minutes": len(weights)}


@dataclass
class DemoSoccerMatch:
    home: str
    away: str
    lam: float
    mu: float
    rho: float
    competition: str
    n: int
    draw: Dict = field(default_factory=dict)

    def event(self, frac: float) -> Event:
        if not self.draw:
            self.draw = _draw_soccer_timeline(_rng_for(f"{self.home}|{self.away}", self.n), self.lam, self.mu)
        total = self.draw["total_minutes"]
        elapsed_steps = min(total, int(frac * total * 1.02))
        seen = [e for e in self.draw["events"] if e["minute"] <= elapsed_steps]
        h, a = (seen[-1]["score"] if seen else [0, 0])
        finished = frac >= 1.0
        l1 = 45 + InPlayParams().stoppage1
        if finished:
            status, phase, minute = "finished", "ft", 90.0
        elif elapsed_steps >= l1:
            status, phase, minute = "live", "h2", 45.0 + (elapsed_steps - l1)
        else:
            status, phase, minute = "live", "h1", float(elapsed_steps)
        goals = ["h" if e["side"] == "h" else "a" for e in seen]
        kickoff = datetime.now(timezone.utc) - timedelta(minutes=frac * CYCLE_MINUTES)
        ev_id = f"demo_soccer_{self.home}_{self.away}".replace(" ", "_")
        return Event(id=ev_id, sport="soccer",
                    competition=self.competition, home=self.home, away=self.away, kickoff=kickoff,
                    status=status, score=(h, a), clock={} if status != "live" else {"phase": phase, "minute": minute},
                    live={"goals": goals, "red_home": 0, "red_away": 0}, source="demo",
                    meta={"lam": self.lam, "mu": self.mu, "rho": self.rho, "demo": True})


def soccer_demo_events(now: Optional[datetime] = None) -> List[Event]:
    now = now or datetime.now(timezone.utc)
    n, frac = _slot(now, CYCLE_MINUTES)
    out = []
    for i, (home, away, lam, mu, rho, comp) in enumerate(SOCCER_CARD):
        m = DemoSoccerMatch(home, away, lam, mu, rho, comp, n + i * 977)   # stagger seeds so matches differ
        out.append(m.event(frac if i % 2 == 0 else (frac + 0.5) % 1.0))
    return out


def basketball_demo_events(now: Optional[datetime] = None) -> List[Event]:
    now = now or datetime.now(timezone.utc)
    n, frac = _slot(now, CYCLE_MINUTES)
    out = []
    for i, (home, away, margin, total, comp) in enumerate(BASKETBALL_CARD):
        rng = _rng_for(f"{home}|{away}", n + i * 401)
        f = frac if i % 2 == 0 else (frac + 0.5) % 1.0
        finished = f >= 1.0
        elapsed = min(1.0, f * 1.02)
        cur_margin = rng.gauss(margin * elapsed, 12.0 * (elapsed * (1 - elapsed)) ** 0.5 + 0.01)
        cur_total = max(0.0, rng.gauss(total * elapsed, 18.0 * (elapsed * (1 - elapsed)) ** 0.5 + 0.01))
        h = round((cur_total + cur_margin) / 2.0)
        a = round((cur_total - cur_margin) / 2.0)
        status = "finished" if finished else "live"
        ev_id = f"demo_basketball_{home}_{away}".replace(" ", "_")
        out.append(Event(id=ev_id, sport="basketball",
                         competition=comp, home=home, away=away, kickoff=now, status=status,
                         score=(int(max(0, h)), int(max(0, a))),
                         clock={} if status != "live" else {"elapsed": elapsed}, source="demo",
                         meta={"margin": margin, "total": total, "demo": True}))
    return out


def tennis_demo_events(now: Optional[datetime] = None) -> List[Event]:
    now = now or datetime.now(timezone.utc)
    n, frac = _slot(now, CYCLE_MINUTES * 1.5)
    out = []
    for i, (a_name, b_name, p_win, best_of, comp) in enumerate(TENNIS_CARD):
        pa, pb = serve_probs_for_win(p_win, 0.64, best_of)
        f = frac if i % 2 == 0 else (frac + 0.5) % 1.0
        rng = _rng_for(f"{a_name}|{b_name}", n + i * 233)
        finished = f >= 1.0
        sets_a = sets_b = games_a = games_b = 0
        if not finished:
            target_games = int(f * (best_of * 12))
            for _ in range(target_games):
                if rng.random() < 0.5 + 0.3 * (pa - pb):
                    games_a += 1
                else:
                    games_b += 1
                if games_a >= 6 and games_a - games_b >= 2:
                    sets_a += 1
                    games_a = games_b = 0
                elif games_b >= 6 and games_b - games_a >= 2:
                    sets_b += 1
                    games_a = games_b = 0
                if max(sets_a, sets_b) >= best_of // 2 + 1:
                    break
        status = "finished" if finished else "live"
        ev_id = f"demo_tennis_{a_name}_{b_name}".replace(" ", "_")
        out.append(Event(id=ev_id, sport="tennis",
                         competition=comp, home=a_name, away=b_name, kickoff=now, status=status,
                         score=(sets_a, sets_b),
                         live={} if status != "live" else {"sets": [sets_a, sets_b], "games": [games_a, games_b],
                                                           "games_before": 0, "set_first_a": True, "points": None},
                         source="demo", meta={"p_win_a": p_win, "best_of": best_of, "demo": True}))
    return out


MMA_CARD = [("Jon Jones", "Stipe Miocic", 0.72, 5, "UFC Championship (demo)"),
            ("Islam Makhachev", "Arman Tsarukyan", 0.68, 5, "UFC Lightweight Title (demo)")]
VOLLEYBALL_CARD = [("Poland", "Italy", 0.52, 5, "FIVB VNL Final (demo)"),
                   ("Brazil", "USA", 0.49, 5, "Olympic Volleyball (demo)")]
MOTORSPORT_CARD = [("Max Verstappen", "Lando Norris", 0.65, 57, "Formula 1 Grand Prix (demo)"),
                   ("Charles Leclerc", "Lewis Hamilton", 0.55, 57, "Formula 1 Grand Prix (demo)")]
BASEBALL_CARD = [("Tampa Bay Rays", "Cleveland Guardians", 0.5, 7.5, "MLB (demo)"),
                 ("New York Yankees", "Los Angeles Dodgers", 0.2, 8.5, "MLB World Series (demo)"),
                 ("Boston Red Sox", "Houston Astros", -0.5, 8.0, "MLB (demo)")]
FOOTBALL_CARD = [("Kansas City Chiefs", "San Francisco 49ers", -2.5, 47.5, "NFL (demo)"),
                 ("Baltimore Ravens", "Buffalo Bills", -1.5, 48.0, "NFL (demo)")]
HOCKEY_CARD = [("Edmonton Oilers", "Florida Panthers", -1.5, 6.5, "NHL Stanley Cup (demo)"),
               ("New York Rangers", "Toronto Maple Leafs", 0.5, 6.0, "NHL (demo)")]


def mma_demo_events(now: Optional[datetime] = None) -> List[Event]:
    now = now or datetime.now(timezone.utc)
    n, frac = _slot(now, CYCLE_MINUTES)
    out = []
    for i, (home, away, p_win, rounds, comp) in enumerate(MMA_CARD):
        status = "finished" if frac >= 1.0 else "live"
        ev_id = f"demo_mma_{home}_{away}".replace(" ", "_")
        out.append(Event(id=ev_id, sport="mma",
                         competition=comp, home=home, away=away, kickoff=now, status=status,
                         score=(1 if frac >= 1.0 and p_win > 0.5 else 0, 1 if frac >= 1.0 and p_win <= 0.5 else 0),
                         clock={} if status != "live" else {"round": min(rounds, int(frac * rounds) + 1)},
                         source="demo", meta={"p_win_a": p_win, "rounds": rounds, "demo": True}))
    return out


def volleyball_demo_events(now: Optional[datetime] = None) -> List[Event]:
    now = now or datetime.now(timezone.utc)
    n, frac = _slot(now, CYCLE_MINUTES)
    out = []
    for i, (home, away, p_win, best_of, comp) in enumerate(VOLLEYBALL_CARD):
        status = "finished" if frac >= 1.0 else "live"
        ev_id = f"demo_volleyball_{home}_{away}".replace(" ", "_")
        out.append(Event(id=ev_id, sport="volleyball",
                         competition=comp, home=home, away=away, kickoff=now, status=status,
                         score=(2 if frac >= 0.5 else 1, 1 if frac >= 0.5 else 2),
                         clock={} if status != "live" else {"set": min(best_of, int(frac * best_of) + 1)},
                         source="demo", meta={"p_win_a": p_win, "best_of": best_of, "demo": True}))
    return out


def motorsport_demo_events(now: Optional[datetime] = None) -> List[Event]:
    now = now or datetime.now(timezone.utc)
    n, frac = _slot(now, CYCLE_MINUTES)
    out = []
    for i, (home, away, p_win, laps, comp) in enumerate(MOTORSPORT_CARD):
        status = "finished" if frac >= 1.0 else "live"
        ev_id = f"demo_motorsport_{home}_{away}".replace(" ", "_")
        out.append(Event(id=ev_id, sport="motorsport",
                         competition=comp, home=home, away=away, kickoff=now, status=status,
                         score=(1 if frac >= 1.0 else 0, 2 if frac >= 1.0 else 0),
                         clock={} if status != "live" else {"lap": min(laps, int(frac * laps) + 1)},
                         source="demo", meta={"p_win_a": p_win, "laps": laps, "demo": True}))
    return out


def baseball_demo_events(now: Optional[datetime] = None) -> List[Event]:
    now = now or datetime.now(timezone.utc)
    n, frac = _slot(now, CYCLE_MINUTES)
    out = []
    for i, (home, away, margin, total, comp) in enumerate(BASEBALL_CARD):
        status = "finished" if frac >= 1.0 else "live"
        h_score = int(round(total * frac * 0.55)) if frac < 1.0 else (5 if margin > 0 else 3)
        a_score = int(round(total * frac * 0.45)) if frac < 1.0 else (3 if margin > 0 else 4)
        pitchers = {"home": "Shane McClanahan", "away": "Shane Bieber"} if "Tampa Bay" in home else {"home": "Gerrit Cole", "away": "Yoshinobu Yamamoto"}
        meta = {
            "margin": margin, "total": total, "demo": True,
            "pitchers": pitchers,
            "form": {"home": "WWLWW", "away": "WLWWL"},
            "records": {"home": [{"summary": "88-54", "type": "total"}], "away": [{"summary": "82-60", "type": "total"}]}
        }
        ev_id = f"demo_baseball_{home}_{away}".replace(" ", "_")
        out.append(Event(id=ev_id, sport="baseball",
                         competition=comp, home=home, away=away, kickoff=now, status=status,
                         score=(h_score, a_score),
                         clock={} if status != "live" else {"inning": min(9, int(frac * 9) + 1), "half": "top", "outs": 1},
                         source="demo", meta=meta))
    return out


def football_demo_events(now: Optional[datetime] = None) -> List[Event]:
    now = now or datetime.now(timezone.utc)
    n, frac = _slot(now, CYCLE_MINUTES)
    out = []
    for i, (home, away, margin, total, comp) in enumerate(FOOTBALL_CARD):
        status = "finished" if frac >= 1.0 else "live"
        ev_id = f"demo_american_football_{home}_{away}".replace(" ", "_")
        out.append(Event(id=ev_id, sport="american_football",
                         competition=comp, home=home, away=away, kickoff=now, status=status,
                         score=(24 if frac >= 0.5 else 14, 21 if frac >= 0.5 else 17),
                         clock={} if status != "live" else {"elapsed": min(1.0, frac)},
                         source="demo", meta={"margin": margin, "total": total, "demo": True}))
    return out


def hockey_demo_events(now: Optional[datetime] = None) -> List[Event]:
    now = now or datetime.now(timezone.utc)
    n, frac = _slot(now, CYCLE_MINUTES)
    out = []
    for i, (home, away, margin, total, comp) in enumerate(HOCKEY_CARD):
        status = "finished" if frac >= 1.0 else "live"
        ev_id = f"demo_hockey_{home}_{away}".replace(" ", "_")
        out.append(Event(id=ev_id, sport="hockey",
                         competition=comp, home=home, away=away, kickoff=now, status=status,
                         score=(3 if frac >= 0.5 else 1, 2 if frac >= 0.5 else 2),
                         clock={} if status != "live" else {"elapsed": min(1.0, frac)},
                         source="demo", meta={"margin": margin, "total": total, "demo": True}))
    return out


def all_demo_events(now: Optional[datetime] = None) -> List[Event]:
    evs: List[Event] = []
    evs.extend(soccer_demo_events(now))
    evs.extend(basketball_demo_events(now))
    evs.extend(tennis_demo_events(now))
    evs.extend(baseball_demo_events(now))
    evs.extend(football_demo_events(now))
    evs.extend(hockey_demo_events(now))
    evs.extend(volleyball_demo_events(now))
    evs.extend(motorsport_demo_events(now))
    evs.extend(mma_demo_events(now))
    return evs

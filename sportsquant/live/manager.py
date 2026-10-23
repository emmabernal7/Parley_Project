"""Keeps a live table of events and prices any one of them on demand.

Background thread: refreshes schedules (ESPN, slow poll) and live scores (fast poll) and always
regenerates the demo universe (cheap, deterministic).  Pricing is NOT precomputed for every event -
it is computed the moment the frontend asks for an event's markets, which is fast enough
(a few ms to ~30ms per soccer match) that there is no need to warm a cache nobody is looking at.
"""
from __future__ import annotations

import json
import logging
import threading
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from ..data.store import Store
from ..engines.others import MMAEngine, TennisEngine, VolleyballEngine, WaterpoloEngine, settle_generic
from ..engines.soccer import settle_soccer, state_from_event
from ..events import Event, SPORTS
from ..live.providers import espn, sofascore, thesportsdb, weather
from ..live.providers.sim_demo import all_demo_events
from ..markets.schema import flatten
from ..models.elo import elo_to_goal_rates
from ..services.model_manager import ModelManager
from ..settings import CONFIG_DIR, get_settings

log = logging.getLogger(__name__)


class LiveManager:
    def __init__(self, store: Store, models: ModelManager):
        self.store, self.models = store, models
        self._lock = threading.RLock()
        self.events: Dict[str, Event] = {}
        if get_settings().enable_demo:
            try:
                for e in all_demo_events():
                    self.events[e.id] = e
            except Exception as ex:
                log.debug("initial demo seeding failed: %s", ex)
        self._last_schedule: float = 0.0
        self._last_live: float = 0.0
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._price_cache: Dict[str, Tuple[float, Dict]] = {}
        self._main_market_cache: Dict[str, Tuple[float, Dict]] = {}

    # ------------------------------------------------------------------ background loop
    def start(self) -> None:
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _loop(self) -> None:
        s = get_settings()
        try:
            self.refresh_all(force=True)
        except Exception:
            log.exception("initial live refresh error")
        try:
            self.models.ensure_seed_data()
            self.models.refit()
        except Exception:
            log.exception("initial seed ingest / model fit failed (will retry on schedule)")
        while not self._stop.is_set():
            try:
                self.refresh_all()
                self.settle_open_slips()
                if self.models.last_fit is None or (time.time() - self.models.last_fit.timestamp()) > s.refit_hours * 3600:
                    self.models.refit()
            except Exception:
                log.exception("live refresh loop error")
            self._stop.wait(s.poll_live_seconds)

    # ------------------------------------------------------------------ refresh
    def refresh_all(self, force: bool = False) -> None:
        s = get_settings()
        now = time.time()
        if s.enable_demo:
            self._refresh_demo()
        should_fetch = force or (now - self._last_schedule > s.poll_schedule_seconds)
        if should_fetch:
            self._last_schedule = now
            if "espn" in s.providers:
                self._refresh_espn()
            self._refresh_thesportsdb()
            self._refresh_sofascore()
        self._prune()

    def _refresh_demo(self) -> None:
        try:
            demos = all_demo_events()
            with self._lock:
                for e in demos:
                    self.events[e.id] = e
        except Exception:
            log.exception("demo refresh failed")

    def _refresh_sofascore(self) -> None:
        try:
            for sp in SPORTS:
                evs = sofascore.fetch_live(sp)
                if evs:
                    with self._lock:
                        for e in evs:
                            self.events[e.id] = e
        except Exception as ex:
            log.debug("SofaScore refresh error: %s", ex)

    def _refresh_espn(self) -> None:
        try:
            leagues = json.loads((CONFIG_DIR / "leagues.json").read_text(encoding="utf-8"))
        except Exception:
            log.exception("could not read config/leagues.json")
            return
            
        tasks = []
        for sport in leagues.keys():
            for entry in leagues.get(sport, []):
                espn_slug = entry.get("espn")
                if espn_slug:
                    tasks.append((sport, espn_slug, entry.get("name", espn_slug)))
                    
        def _fetch_one(t):
            sport, espn_slug, comp_name = t
            try:
                evs = espn.fetch(sport, espn_slug, get_settings().espn_days_ahead)
                if evs:
                    for e in evs:
                        e.competition = comp_name
                    with self._lock:
                        for e in evs:
                            self.events[e.id] = e
                return evs
            except Exception:
                return []

        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
            list(executor.map(_fetch_one, tasks))

    def _refresh_thesportsdb(self) -> None:
        try:
            evs = thesportsdb.fetch("", days_ahead=get_settings().espn_days_ahead)
            with self._lock:
                for e in evs:
                    if e.id not in self.events:
                        self.events[e.id] = e
        except Exception:
            log.exception("TheSportsDB refresh failed")

    def _prune(self) -> None:
        s = get_settings()
        cutoff = datetime.now(timezone.utc).timestamp() - 6 * 3600
        with self._lock:
            self.events = {k: v for k, v in self.events.items()
                           if (v.source != "demo" or s.enable_demo) and (v.status != "finished" or v.kickoff.timestamp() > cutoff)}

    def quick_main_market(self, ev: Event) -> Optional[Dict]:
        now = time.time()
        ttl = 2.5 if ev.status == "live" else 120.0
        if ev.id in self._main_market_cache:
            ts, cached_g0 = self._main_market_cache[ev.id]
            if now - ts < ttl:
                return cached_g0

        user_odds = self.store.get_user_odds(ev.id)
        cache_key = f"{ev.id}:{hash(frozenset(user_odds.items())) if user_odds else ''}"
        if cache_key in self._price_cache:
            ts, cached_res = self._price_cache[cache_key]
            if now - ts < ttl:
                if cached_res.get("groups"):
                    g0 = cached_res["groups"][0]
                    self._main_market_cache[ev.id] = (now, g0)
                    return g0

        if ev.sport == "soccer":
            pr = self.models.soccer_pricer(ev)
            st = state_from_event(ev)
            g0 = pr.main_market(st)
        else:
            p = self.price(ev)
            g0 = p["groups"][0] if (p and p.get("groups")) else None
        if g0:
            self._main_market_cache[ev.id] = (now, g0)
        return g0

    def list_events(self, sport: Optional[str] = None, status: Optional[str] = None) -> List[Dict]:
        with self._lock:
            evs = list(self.events.values())
        if sport:
            evs = [e for e in evs if e.sport == sport]
        if status:
            evs = [e for e in evs if e.status == status]
        evs.sort(key=lambda e: (e.status != "live", e.kickoff))

        out = []
        for e in evs:
            b = e.brief()
            try:
                g0 = self.quick_main_market(e)
                if g0:
                    b["main_market"] = {
                        "name": g0["name"],
                        "selections": [
                            {"label": s["label"], "prob": s.get("prob"), "odds": s.get("odds")}
                            for s in g0.get("selections", [])
                        ]
                    }
            except Exception as ex:
                log.debug("could not get main market for brief %s: %s", e.id, ex)
            out.append(b)
        return out

    def get_event(self, event_id: str) -> Optional[Event]:
        with self._lock:
            return self.events.get(event_id)

    # ------------------------------------------------------------------ pricing dispatch
    def price(self, ev: Event, ttl_seconds: float = 3.0) -> Dict:
        now = time.time()
        user_odds = self.store.get_user_odds(ev.id)
        cache_key = f"{ev.id}:{hash(frozenset(user_odds.items())) if user_odds else ''}"
        effective_ttl = 2.5 if ev.status == "live" else max(ttl_seconds, 60.0)
        if cache_key in self._price_cache:
            ts, cached_res = self._price_cache[cache_key]
            if now - ts < effective_ttl:
                return cached_res

        if ev.sport == "soccer":
            pr = self.models.soccer_pricer(ev)
            st = state_from_event(ev)
            groups = pr.markets(st)
            info = pr.info(st)
        elif ev.sport in ("basketball", "american_football"):
            eng = self.models.gaussian_engine(ev)
            groups = eng.markets(ev)
            info = eng.info(ev)
        elif ev.sport in ("hockey", "baseball"):
            eng = self.models.race_engine(ev)
            groups = eng.markets(ev)
            info = eng.info(ev)
        elif ev.sport == "tennis":
            p_win = ev.meta.get("p_win_a", 0.5)
            eng = TennisEngine(ev.home, ev.away, p_win, ev.meta.get("best_of", 3),
                               model_label="Elo-style prior + exact Markov chain" if ev.source != "demo" else "Demo prior",
                               confidence="low" if ev.source != "demo" else "demo")
            groups, info = eng.markets(ev), eng.info(ev)
        elif ev.sport == "volleyball":
            eng = VolleyballEngine(ev.home, ev.away, ev.meta.get("p_win_a", 0.5), ev.meta.get("best_of", 5))
            groups, info = eng.markets(ev), eng.info(ev)
        elif ev.sport == "mma":
            eng = MMAEngine(ev.home, ev.away, ev.meta.get("p_win_a", 0.5), ev.meta.get("rounds", 3))
            groups, info = eng.markets(ev), eng.info(ev)
        elif ev.sport == "waterpolo":
            lam = float(ev.meta.get("lam", 11.2) or 11.2)
            mu = float(ev.meta.get("mu", 9.6) or 9.6)
            eng = WaterpoloEngine(ev.home, ev.away, lam, mu,
                                  model_label="Waterpolo Poisson ratings" if ev.source != "demo" else "Demo prior",
                                  confidence="ok" if ev.source != "demo" else "demo")
            groups, info = eng.markets(ev), eng.info(ev)
        else:
            groups, info = [], {"model": "not yet implemented", "confidence": "low"}
        for g in groups:
            for sel in g["selections"]:
                key = f"{g['id']}:{sel['id']}"
                if key in user_odds:
                    sel["user_odds"] = user_odds[key]
        out = {"event": ev.brief(), "groups": groups, "flat": flatten(groups), "info": info,
               "venue": ev.venue, "weather": ev.weather, "referee": ev.referee, "market_meta": ev.meta.get("source")}
        self._price_cache[cache_key] = (now, out)
        return out

    def event_detail(self, event_id: str) -> Optional[Dict]:
        ev = self.get_event(event_id)
        return self.price(ev) if ev else None

    def settle(self, ev: Event, gid: str, sid: str) -> Optional[str]:
        if ev.status != "finished":
            return None
        if ev.sport == "soccer":
            live = ev.live or {}
            ht = tuple(live["ht"]) if "ht" in live else None
            return settle_soccer(gid, sid, ev.score, ht, live.get("goals"))
        return settle_generic(gid, sid, ev.score, ev.sport)

    def settle_open_slips(self) -> None:
        for slip in self.store.list_slips(status="open"):
            results, all_known = [], True
            for leg in slip["legs"]:
                ev = self.get_event(leg["event_id"])
                if ev is None or ev.status != "finished":
                    all_known = False
                    break
                gid, sid = leg["key"].split(":")
                r = self.settle(ev, gid, sid)
                if r is None:
                    all_known = False
                    break
                results.append(r)
            if not all_known:
                continue
            odds = [leg.get("odds", 1.0) for leg in slip["legs"]]
            if any(r == "lost" for r in results):
                status, mult = "lost", 0.0
            elif all(r == "void" for r in results):
                status, mult = "void", 1.0
            else:
                status = "won"
                mult = 1.0
                for r, o in zip(results, odds):
                    if r == "won":
                        mult *= o
                    elif r == "half_won":
                        mult *= (1.0 + (o - 1.0) / 2.0)
                    elif r == "half_lost":
                        mult *= 0.5
                    # 'void' leg: mult unchanged (that leg pushed)
            pnl = slip["stake"] * (mult - 1.0)
            for leg, r in zip(slip["legs"], results):
                leg["result"] = r
            self.store.update_slip(slip["id"], slip["legs"], status, round(pnl, 2))

"""The common shape of a market, whatever the sport.

    group = {"id": "1x2", "name": "1x2", "tab": "main", "kind": "3way",
             "selections": [{"id": "home", "label": "Barcelona", "prob": 0.74, "odds": 1.35}, ...],
             "note": "..."}

`prob` is the model probability (what you see as XX %); `odds` is the fair DECIMAL odds 1 / prob
(what you see as 1.28).  Bookmaker prices are attached separately as `market_odds`.
"""
from __future__ import annotations

from typing import Dict, Iterable, List, Optional

from ..odds import prob_to_odds


def sel(sid: str, label: str, prob: float, line: Optional[float] = None, **extra) -> Dict:
    d = {"id": sid, "label": label, "prob": float(max(0.0, min(1.0, prob)))}
    if line is not None:
        d["line"] = float(line)
    d.update(extra)
    return d


def group(gid: str, name: str, tab: str, selections: List[Dict], kind: str = "multi",
          note: Optional[str] = None, **extra) -> Dict:
    g = {"id": gid, "name": name, "tab": tab, "kind": kind, "selections": selections}
    if note:
        g["note"] = note
    g.update(extra)
    return g


def finalize(groups: Iterable[Dict]) -> List[Dict]:
    """Attach fair decimal odds to every selection (1 / probability, shown from 1.01 to 1000)."""
    out = []
    for g in groups:
        for s in g["selections"]:
            s["odds"] = prob_to_odds(s["prob"])
        out.append(g)
    return out


def flatten(groups: Iterable[Dict]) -> Dict[str, List[float]]:
    """{'1x2:home': [prob, odds], ...}  compact map used for live updates."""
    flat: Dict[str, List[float]] = {}
    for g in groups:
        for s in g["selections"]:
            flat[f"{g['id']}:{s['id']}"] = [round(s["prob"], 5), round(s.get("odds", prob_to_odds(s["prob"])), 3)]
    return flat


def find_selection(groups: Iterable[Dict], key: str) -> Optional[Dict]:
    gid, _, sid = key.partition(":")
    for g in groups:
        if g["id"] == gid:
            for s in g["selections"]:
                if s["id"] == sid:
                    return {**s, "group": g["name"], "group_id": g["id"], "event_side_names": None}
    return None

"""Team-name harmonisation: 'Man United' (football-data) = 'Manchester United' (ESPN) = 'Man Utd' (odds feed)."""
from __future__ import annotations

import difflib
import json
import re
import unicodedata
from functools import lru_cache
from typing import Dict, Iterable, Optional

from .settings import SEED_DIR

_STOP = {"fc", "cf", "afc", "sc", "ac", "as", "sd", "cd", "ud", "rc", "fk", "sk", "ssc", "ss", "us", "bk", "if", "sv",
         "vfl", "vfb", "tsg", "fsv", "1", "de", "the", "club", "calcio"}


def _ascii(s: str) -> str:
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")


@lru_cache(maxsize=1)
def _aliases() -> Dict[str, str]:
    p = SEED_DIR / "aliases.json"
    if not p.exists():
        return {}
    raw = json.loads(p.read_text(encoding="utf-8"))
    return {_norm(k): _norm(v) for k, v in raw.items()}


def _norm(name: str) -> str:
    s = _ascii(name).lower().replace("&", " and ").replace("'", "").replace(".", " ").replace("-", " ")
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    toks = [t for t in s.split() if t not in _STOP]
    return " ".join(toks)


def canon(name: str) -> str:
    """Canonical key for a team name (accents, 'FC', punctuation removed; known aliases applied)."""
    n = _norm(name)
    return _aliases().get(n, n)


def best_match(name: str, candidates: Iterable[str], cutoff: float = 0.84) -> Optional[str]:
    """Closest candidate to `name` by canonical form; exact canonical matches win."""
    target = canon(name)
    cands = list(candidates)
    by_canon = {canon(c): c for c in cands}
    if target in by_canon:
        return by_canon[target]
    close = difflib.get_close_matches(target, list(by_canon), n=1, cutoff=cutoff)
    return by_canon[close[0]] if close else None

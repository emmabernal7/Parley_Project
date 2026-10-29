"""Generic bet settlement for 2-way and multi-way sports."""
from __future__ import annotations

from typing import Optional, Tuple


def settle_generic(gid: str, sid: str, final: Tuple[int, int], sport: str = "") -> Optional[str]:
    """Moneyline / spread / total / set settlement for the non-soccer engines."""
    h, a = final
    d, t = h - a, h + a
    win = lambda c: "won" if c else "lost"
    if gid == "1x2":
        if d > 0:
            return "won" if sid == "home" else "lost"
        elif d < 0:
            return "won" if sid == "away" else "lost"
        else:
            return "won" if sid == "draw" else "lost"
    if gid == "ml":
        if sport in ("tennis", "volleyball", "mma"):
            return win((h > a) == (sid == "a"))
        return win((d > 0) == (sid == "home")) if d != 0 else "void"
    for prefix in ("sp_", "pl_", "rl_", "sh_", "gl_"):
        if gid.startswith(prefix):
            L = float(gid[len(prefix):])
            m = d if sid in ("home", "a") else -d
            L = L if sid in ("home", "a") else -L
            return "void" if abs(m + L) < 1e-9 else win(m + L > 0)
    for prefix in ("tot_", "sets_", "pts_", "games_"):
        if gid.startswith(prefix):
            return win((t > float(gid[len(prefix):])) == (sid == "over"))
    return None

"""Unified facade for non-soccer pricing engines.

This module re-exports the modular engines for backward compatibility:
- Timed sports (Basketball, NFL): sportsquant.engines.timed.gaussian.GaussianEngine
- Diamond & Ice sports (Baseball, Hockey): sportsquant.engines.diamond.race.PoissonRaceEngine
- Court sports (Tennis, Volleyball): sportsquant.engines.court
- Combat sports (MMA): sportsquant.engines.combat.mma.MMAEngine
- Racing (F1): sportsquant.engines.racing.f1.F1Engine
- Settlement: sportsquant.engines.settlement.settle_generic
"""
from __future__ import annotations

from .combat.mma import MMAEngine
from .common import _hl, nearest_half
from .court.tennis import TennisEngine
from .court.volleyball import VolleyballEngine
from .diamond.race import PoissonRaceEngine
from .racing.f1 import F1Engine
from .settlement import settle_generic
from .timed.gaussian import GaussianEngine

__all__ = [
    "nearest_half",
    "_hl",
    "GaussianEngine",
    "PoissonRaceEngine",
    "TennisEngine",
    "VolleyballEngine",
    "MMAEngine",
    "F1Engine",
    "settle_generic",
]

"""TheSportsDB provider (deprecated in favor of ESPN public endpoints)."""
from __future__ import annotations
from typing import List
from ...events import Event

def fetch(sport: str = "", days_ahead: int = 3) -> List[Event]:
    return []

"""Event: one match / fight / race as the whole program sees it."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

SPORTS = ["soccer", "basketball", "baseball", "american_football", "hockey", "tennis", "mma",
          "volleyball", "motorsport"]

SPORT_LABELS = {
    "soccer": "Soccer", "basketball": "Basketball", "baseball": "Baseball",
    "american_football": "American Football", "hockey": "Ice Hockey", "tennis": "Tennis",
    "mma": "MMA", "volleyball": "Volleyball", "motorsport": "Formula 1",
}


@dataclass
class Event:
    id: str
    sport: str
    competition: str
    home: str
    away: str
    kickoff: datetime
    status: str = "scheduled"                 # scheduled | live | finished | postponed
    score: Tuple[int, int] = (0, 0)
    clock: Dict[str, Any] = field(default_factory=dict)      # {"display": "67'", "phase": "h2", "minute": 67.0}
    live: Dict[str, Any] = field(default_factory=dict)       # sport-specific live state
    venue: Optional[Dict[str, Any]] = None                   # {"name","city","country","lat","lon"}
    referee: Optional[str] = None
    weather: Optional[Dict[str, Any]] = None
    market_odds: Dict[str, Any] = field(default_factory=dict)  # feed prices (decimal), e.g. {"source": "DraftKings", "1x2": {...}}
    user_odds: Dict[str, float] = field(default_factory=dict)  # prices typed by the user: {"1x2:home": 7.8}
    source: str = "sim"
    neutral: bool = False
    meta: Dict[str, Any] = field(default_factory=dict)
    stats: Dict[str, Any] = field(default_factory=dict)      # final stats when known (corners, cards...)

    def __post_init__(self) -> None:
        if self.kickoff.tzinfo is None:
            self.kickoff = self.kickoff.replace(tzinfo=timezone.utc)

    @property
    def is_live(self) -> bool:
        return self.status == "live"

    @property
    def title(self) -> str:
        return f"{self.home} vs {self.away}"

    def brief(self) -> Dict[str, Any]:
        return {
            "id": self.id, "sport": self.sport, "competition": self.competition, "home": self.home,
            "away": self.away, "kickoff": self.kickoff.isoformat(), "status": self.status,
            "score": list(self.score), "clock": self.clock, "venue": self.venue, "source": self.source,
        }

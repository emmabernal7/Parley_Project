"""Social intelligence flags extractor.
NOTE: Twitter / X API v2 has been deprecated in favor of official, structured ESPN injury & lineup reports.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional

log = logging.getLogger(__name__)


@dataclass
class RawPost:
    account: str
    tier: str
    text: str
    created_at: str
    url: str


class SocialExtractor:
    def __init__(self):
        self.accounts = {}

    @property
    def enabled(self) -> bool:
        return False

    def status(self) -> Dict:
        return {
            "enabled": False,
            "status": "disabled",
            "note": "X/Twitter API disabled. Live injuries and rosters are directly provided by official ESPN endpoints."
        }

    def poll(self, tiers: List[str] = (), max_results: int = 5) -> List[RawPost]:
        return []

    def extract_flags(self, posts: List[RawPost], llm_extract) -> List[Dict]:
        return []

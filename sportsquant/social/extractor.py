"""Turns X posts from trusted accounts into structured flags ({team, player, status, source}).

INACTIVE BY DEFAULT.  The official X API has no free tier for reading posts (see
docs/model_guide.tex section 8) - roughly $0.005 per post read at the time this was written, so
polling even 30 accounts a few times a day is a real, ongoing cost you opt into on purpose.  Set
X_BEARER_TOKEN in .env to turn it on; until then, every method here returns an empty, clearly
labelled result rather than pretending to have data.

This module only ever reads Tier-1/Tier-2 accounts (config/accounts_twitter.json) for anything
that could be treated as a fact. Tier-3/4 accounts, if you choose to poll them at all, come back
tagged sentiment-only and are never passed to `extract_flags`.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Dict, List, Optional

import requests

from ..settings import CONFIG_DIR, get_settings

log = logging.getLogger(__name__)
API = "https://api.twitter.com/2"


@dataclass
class RawPost:
    account: str
    tier: str
    text: str
    created_at: str
    url: str


def load_accounts() -> Dict[str, List[str]]:
    data = json.loads((CONFIG_DIR / "accounts_twitter.json").read_text(encoding="utf-8"))
    return {
        "tier1_official": data.get("tier1_official", {}).get("examples", []),
        "tier2_journalists": data.get("tier2_journalists", {}).get("accounts", []),
        "tier3_community": data.get("tier3_community", {}).get("accounts", []),
        "tier4_banter_and_unverified": data.get("tier4_banter_and_unverified", {}).get("accounts", []),
    }


class XClient:
    def __init__(self, token: str):
        self.token = token
        self.session = requests.Session()
        self.session.headers.update({"Authorization": f"Bearer {token}"})

    def user_id(self, handle: str) -> Optional[str]:
        r = self.session.get(f"{API}/users/by/username/{handle.lstrip('@')}", timeout=10)
        if r.status_code != 200:
            log.info("X lookup failed for %s: %s", handle, r.status_code)
            return None
        return r.json().get("data", {}).get("id")

    def recent_posts(self, handle: str, max_results: int = 10) -> List[Dict]:
        uid = self.user_id(handle)
        if not uid:
            return []
        r = self.session.get(f"{API}/users/{uid}/tweets", params={
            "max_results": max(5, min(max_results, 100)), "tweet.fields": "created_at",
            "exclude": "retweets,replies",
        }, timeout=10)
        if r.status_code != 200:
            log.info("X timeline failed for %s: %s", handle, r.status_code)
            return []
        return r.json().get("data", [])


class SocialExtractor:
    def __init__(self):
        self.accounts = load_accounts()

    @property
    def enabled(self) -> bool:
        return bool(getattr(get_settings(), "x_bearer_token", ""))

    def status(self) -> Dict:
        return {"enabled": self.enabled, "accounts_configured": {k: len(v) for k, v in self.accounts.items()},
               "note": ("Set X_BEARER_TOKEN in .env to enable - reading the X API has no free tier, "
                        "see docs/model_guide.tex section 8 for the cost.") if not self.enabled else "active"}

    def poll(self, tiers: List[str] = ("tier1_official", "tier2_journalists"), max_results: int = 5) -> List[RawPost]:
        if not self.enabled:
            return []
        client = XClient(getattr(get_settings(), "x_bearer_token", ""))
        out: List[RawPost] = []
        for tier in tiers:
            for handle in self.accounts.get(tier, []):
                for p in client.recent_posts(handle, max_results):
                    out.append(RawPost(account=handle, tier=tier, text=p.get("text", ""),
                                       created_at=p.get("created_at", ""), url=f"https://x.com/{handle}"))
        return out

    def extract_flags(self, posts: List[RawPost], llm_extract) -> List[Dict]:
        """posts -> [{team, player, status, source, confidence}], using an LLM call the caller supplies
        (llm_extract(text) -> dict | None) so this module carries no model-specific code. Tier-3/4 posts
        are refused here even if passed in by mistake - only tier1/tier2 can produce a flag."""
        out = []
        for p in posts:
            if p.tier not in ("tier1_official", "tier2_journalists"):
                continue
            try:
                flag = llm_extract(p.text)
            except Exception as e:
                log.warning("extraction failed for a post from %s: %s", p.account, e)
                continue
            if flag:
                flag["source"] = p.account
                flag["tier"] = p.tier
                flag["confidence"] = "confirmed" if p.tier == "tier1_official" else "reported"
                out.append(flag)
        return out

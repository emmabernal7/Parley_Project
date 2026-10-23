"""Settings: defaults in code, overridden by config/settings.yaml, then by environment variables / .env."""
from __future__ import annotations

import os
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any, Dict, List

import yaml

ROOT = Path(__file__).resolve().parent.parent          # the project folder (contains config/, data/, sportsquant/)
DATA_DIR = ROOT / "data"
SEED_DIR = DATA_DIR / "seed"
CONFIG_DIR = ROOT / "config"


def _load_dotenv() -> None:
    env = ROOT / ".env"
    if not env.exists():
        return
    for line in env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


@dataclass
class Settings:
    # ---- server
    host: str = "127.0.0.1"
    port: int = 8000
    open_browser: bool = True
    db_path: str = str(DATA_DIR / "sportsquant.db")
    # ---- data providers: "espn" (real, free, unofficial)
    providers: List[str] = field(default_factory=lambda: ["espn"])
    enable_demo: bool = False                   # eliminated by default
    sim_only_if_no_internet: bool = False       # if ESPN answers nothing at all, show empty list
    sim_speed: float = 20.0                     # demo matches speed
    espn_days_ahead: int = 3                    # upcoming window for the schedule
    poll_live_seconds: float = 15.0             # how often live matches are refreshed
    poll_schedule_seconds: float = 600.0        # how often the upcoming schedule is refreshed
    refit_hours: float = 6.0                    # models are refitted with new results this often
    # ---- modelling
    lookback_seasons: int = 3
    xi: float = 0.0019                          # Dixon-Coles time decay per day (half-life ~ 1 year)
    reg: float = 1.0                            # ridge strength on team strengths
    weather_adjust: bool = False                # apply the (uncalibrated) weather prior to expected goals
    bankroll: float = 1000.0                    # paper bankroll shown in the top bar
    kelly_fraction: float = 0.25
    value_min_edge: float = 0.03
    # ---- keys (from .env)
    odds_api_key: str = ""
    gemini_api_key: str = ""
    anthropic_api_key: str = ""
    x_bearer_token: str = ""
    gemini_model: str = "gemini-2.5-flash"
    anthropic_model: str = "claude-sonnet-5"
    llm_provider: str = "auto"                  # auto | gemini | anthropic | offline

    def public(self) -> Dict[str, Any]:
        d = {f.name: getattr(self, f.name) for f in fields(self)}
        for k in ("odds_api_key", "gemini_api_key", "anthropic_api_key", "x_bearer_token"):
            d[k] = bool(d[k])
        return d


_SETTINGS: Settings | None = None


def get_settings(reload: bool = False) -> Settings:
    global _SETTINGS
    if _SETTINGS is not None and not reload:
        return _SETTINGS
    _load_dotenv()
    s = Settings()
    cfg = CONFIG_DIR / "settings.yaml"
    if cfg.exists():
        data = yaml.safe_load(cfg.read_text(encoding="utf-8")) or {}
        for k, v in data.items():
            if hasattr(s, k):
                setattr(s, k, v)
    env_map = {"THE_ODDS_API_KEY": "odds_api_key", "ODDS_API_KEY": "odds_api_key", "GEMINI_API_KEY": "gemini_api_key",
               "ANTHROPIC_API_KEY": "anthropic_api_key", "X_BEARER_TOKEN": "x_bearer_token", "SQ_DB": "db_path", "SQ_PORT": "port",
               "SQ_SIM_SPEED": "sim_speed", "SQ_LLM": "llm_provider", "GEMINI_MODEL": "gemini_model",
               "ANTHROPIC_MODEL": "anthropic_model"}
    for env, attr in env_map.items():
        val = os.environ.get(env)
        if val:
            cur = getattr(s, attr)
            setattr(s, attr, type(cur)(val) if not isinstance(cur, str) else val)
    if os.environ.get("SQ_PROVIDERS"):
        s.providers = [p.strip() for p in os.environ["SQ_PROVIDERS"].split(",") if p.strip()]
    _SETTINGS = s
    return s

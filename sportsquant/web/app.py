"""FastAPI app.  Run with: python run.py  (see README.md)."""
from __future__ import annotations

import logging
import webbrowser
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ..chat.engine import ChatEngine
from ..chat.tools import ToolBox
from ..data.store import Store
from ..live.manager import LiveManager
from ..services.model_manager import ModelManager
from ..settings import get_settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("sportsquant")

STATIC_DIR = Path(__file__).resolve().parent / "static"

state = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()
    store = Store(s.db_path)
    models = ModelManager(store)
    live = LiveManager(store, models)
    tools = ToolBox(live, store)
    chat = ChatEngine(tools)
    state.update(store=store, models=models, live=live, tools=tools, chat=chat)
    live.start()
    log.info("sportsquant ready on http://%s:%s", s.host, s.port)
    yield
    live.stop()


app = FastAPI(title="SportsQuant", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
def index():
    return FileResponse(str(STATIC_DIR / "index.html"))


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return FileResponse(str(STATIC_DIR / "favicon.ico"), media_type="image/x-icon")


@app.get("/api/settings")
def get_settings_api():
    return get_settings().public()


class SettingsPatch(BaseModel):
    bankroll: Optional[float] = None
    kelly_fraction: Optional[float] = None
    value_min_edge: Optional[float] = None


@app.post("/api/settings")
def patch_settings(body: SettingsPatch):
    s = get_settings()
    for field in ("bankroll", "kelly_fraction", "value_min_edge"):
        v = getattr(body, field)
        if v is not None:
            setattr(s, field, v)
    return s.public()


@app.get("/api/events")
def list_events(sport: Optional[str] = None, status: Optional[str] = None):
    return state["live"].list_events(sport=sport, status=status)


@app.post("/api/events/refresh")
def refresh_events():
    state["live"].refresh_all(force=True)
    return {"ok": True, "count": len(state["live"].events)}


@app.get("/api/event/{event_id}")
def event_detail(event_id: str):
    detail = state["live"].event_detail(event_id)
    if detail is None:
        raise HTTPException(404, "event not found (it may have finished and rolled off)")
    return detail


class OddsBody(BaseModel):
    key: str
    odds: Optional[float] = None


@app.post("/api/event/{event_id}/odds")
def set_user_odds(event_id: str, body: OddsBody):
    state["store"].set_user_odds(event_id, body.key, body.odds)
    return {"ok": True}


@app.get("/api/data-status")
def data_status():
    return {"soccer_leagues": state["store"].match_counts(),
            "last_fit": state["models"].last_fit.isoformat() if state["models"].last_fit else None,
            "fitted_soccer_leagues": list(state["models"].soccer_models.keys())}


@app.get("/api/social/status")
def social_status():
    from ..social.extractor import SocialExtractor
    return SocialExtractor().status()


@app.get("/api/ml/backtest")
def ml_backtest(league: Optional[str] = None, stake: float = 25.0):
    from ..services.backtester import BacktesterService
    bt = BacktesterService(state["store"])
    return bt.run_backtest(league=league, stake=stake)


@app.post("/api/refit")
def refit():
    return {"fitted": state["models"].refit()}


class ChatBody(BaseModel):
    session_id: str
    message: str


@app.post("/api/chat")
def chat(body: ChatBody):
    return state["chat"].reply(body.session_id, body.message)


class SlipAdd(BaseModel):
    session_id: str
    event_id: str
    key: str
    odds: Optional[float] = None


@app.post("/api/slip/add")
def slip_add(body: SlipAdd):
    return {"slip": state["chat"].add_to_slip(body.session_id, body.event_id, body.key, body.odds)}


class SlipRemove(BaseModel):
    session_id: str
    event_id: str
    key: str


@app.post("/api/slip/remove")
def slip_remove(body: SlipRemove):
    slip = state["chat"].get_slip(body.session_id)
    slip[:] = [l for l in slip if not (l["event_id"] == body.event_id and l["key"] == body.key)]
    return {"slip": slip}


@app.get("/api/slip")
def slip_get(session_id: str):
    legs = state["chat"].get_slip(session_id)
    if not legs:
        return {"legs": [], "priced": None}
    priced = state["tools"].price_parlay(legs)
    return {"legs": legs, "priced": priced}


class SlipClear(BaseModel):
    session_id: str


@app.post("/api/slip/clear")
def slip_clear(body: SlipClear):
    state["chat"].clear_slip(body.session_id)
    return {"ok": True}


class PlaceBet(BaseModel):
    session_id: str
    stake: float


@app.post("/api/bets")
def place_bet(body: PlaceBet):
    legs = state["chat"].get_slip(body.session_id)
    if not legs:
        raise HTTPException(400, "slip is empty")
    priced = state["tools"].price_parlay(legs)
    if "error" in priced:
        raise HTTPException(400, priced["error"])
    for leg, l in zip(legs, priced["legs"]):
        leg.setdefault("odds", round(priced["odds_used"] ** (1.0 / len(legs)), 4))
        leg["label"] = f"{l['event']} - {l['selection']} ({l['market']})"
    slip_id = state["store"].add_slip(body.stake, legs, note=f"{len(legs)}-leg paper bet")
    state["chat"].clear_slip(body.session_id)
    return {"id": slip_id, "priced": priced}


@app.get("/api/bets")
def list_bets(status: Optional[str] = None):
    return state["store"].list_slips(status=status)


@app.delete("/api/bets/{bet_id}")
def delete_bet(bet_id: int):
    state["store"].delete_slip(bet_id)
    return {"ok": True}


def main() -> None:
    import threading
    import time
    import urllib.request
    import uvicorn

    s = get_settings()
    if s.open_browser:
        def _wait_and_open():
            url = f"http://{s.host}:{s.port}"
            for _ in range(60):  # Poll up to 12s until server is responsive
                time.sleep(0.2)
                try:
                    with urllib.request.urlopen(url, timeout=1) as resp:
                        if resp.status == 200:
                            webbrowser.open(url)
                            return
                except Exception:
                    pass
            try:
                webbrowser.open(url)
            except Exception:
                pass

        threading.Thread(target=_wait_and_open, daemon=True).start()

    uvicorn.run("sportsquant.web.app:app", host=s.host, port=s.port, reload=False)


if __name__ == "__main__":
    main()

"""ML Ensemble integration using sports-betting package capabilities."""
from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from sklearn.compose import make_column_transformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.multioutput import MultiOutputClassifier
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import OneHotEncoder

# Add sports-betting src path
SPORTSBET_SRC = Path(__file__).resolve().parent.parent.parent.parent / "sports-betting-main" / "src"
if SPORTSBET_SRC.exists() and str(SPORTSBET_SRC) not in sys.path:
    sys.path.insert(0, str(SPORTSBET_SRC))

try:
    from sportsbet.evaluation import ClassifierBettor
    SPORTSBET_AVAILABLE = True
except ImportError:
    SPORTSBET_AVAILABLE = False

log = logging.getLogger(__name__)


class MLEnsembleService:
    """Trains a Scikit-Learn MultiOutputClassifier via sports-betting on match history."""

    def __init__(self, weight_dc: float = 0.70):
        self.weight_dc = weight_dc
        self.weight_ml = 1.0 - weight_dc
        self.model: Optional[MultiOutputClassifier] = None
        self.is_fitted = False
        self.feature_names: List[str] = []

    def fit_from_matches(self, df_matches: pd.DataFrame) -> bool:
        if len(df_matches) < 30:
            return False
        try:
            df = df_matches.copy().sort_values("date")
            df["home_win"] = (df["fthg"] > df["ftag"]).astype(int)
            df["draw"] = (df["fthg"] == df["ftag"]).astype(int)
            df["away_win"] = (df["fthg"] < df["ftag"]).astype(int)

            X = df[["league", "home", "away"]].copy()
            Y = df[["home_win", "draw", "away_win"]].to_numpy()

            pipeline = make_pipeline(
                make_column_transformer(
                    (OneHotEncoder(handle_unknown="ignore"), ["league", "home", "away"]),
                    remainder="passthrough",
                ),
                SimpleImputer(strategy="most_frequent"),
                MultiOutputClassifier(LogisticRegression(solver="liblinear", max_iter=200, random_state=42)),
            )
            pipeline.fit(X, Y)
            self.model = pipeline
            self.is_fitted = True
            log.info("ML Ensemble Service successfully fitted on %d matches", len(df))
            return True
        except Exception as e:
            log.warning("ML Ensemble fit failed: %s", e)
            return False

    def predict_probs(self, league: str, home: str, away: str) -> Optional[Dict[str, float]]:
        if not self.is_fitted or self.model is None:
            return None
        try:
            X_test = pd.DataFrame([{"league": league, "home": home, "away": away}])
            proba_list = self.model.predict_proba(X_test)
            # proba_list is a list of arrays for each target column (home_win, draw, away_win)
            p_home = float(proba_list[0][0, 1]) if proba_list[0].shape[1] > 1 else 0.33
            p_draw = float(proba_list[1][0, 1]) if proba_list[1].shape[1] > 1 else 0.33
            p_away = float(proba_list[2][0, 1]) if proba_list[2].shape[1] > 1 else 0.33
            total = p_home + p_draw + p_away
            if total > 0:
                p_home, p_draw, p_away = p_home / total, p_draw / total, p_away / total
            return {"home": p_home, "draw": p_draw, "away": p_away}
        except Exception as e:
            log.debug("ML Ensemble predict failed for %s vs %s: %s", home, away, e)
            return None

    def ensemble_1x2(self, dc_probs: Dict[str, float], league: str, home: str, away: str) -> Tuple[Dict[str, float], str]:
        ml_p = self.predict_probs(league, home, away)
        if ml_p is None:
            return dc_probs, "Dixon-Coles Pure"
        ens = {
            "home": self.weight_dc * dc_probs["home"] + self.weight_ml * ml_p["home"],
            "draw": self.weight_dc * dc_probs["draw"] + self.weight_ml * ml_p["draw"],
            "away": self.weight_dc * dc_probs["away"] + self.weight_ml * ml_p["away"],
        }
        tot = sum(ens.values())
        if tot > 0:
            ens = {k: v / tot for k, v in ens.items()}
        return ens, f"Ensemble (Dixon-Coles {int(self.weight_dc*100)}% + ML {int(self.weight_ml*100)}%)"

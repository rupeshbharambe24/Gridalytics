"""State-wise endpoints — the all-India rollout surface.

Exposes, for every Indian state/UT: the registry entry (region, DISCOMs, tier,
scraper), live data-collection status (rows stored), recent demand, and — where a
model has been trained with scripts/train_state.py — its champion metrics. This
powers the dashboard's state-wise view.

Note: per-state forecasting is supported through the recursive forecast engine
(src/forecasting/future.py), serving day-ahead forecasts for trained state models.
These endpoints provide status, history, model metrics, and forecasts.
"""

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func

from src.data.db.session import get_db
from src.data.db.models import StateDemandRecord, StatePSPDaily, DemandRecord
from src.data.scrapers.states import INDIAN_STATES, STATES_BY_CODE
from src.forecasting.future import forecast_state_future

logger = logging.getLogger(__name__)
router = APIRouter()

_MODELS = Path("models") / "states"
_RES_ORDER = ("5min", "15min", "hourly", "daily")       # finest -> coarsest
_PRIMARY_ORDER = ("hourly", "15min", "daily", "5min")   # which model headlines a state


def _row_count(db: Session, code: str) -> int:
    if code == "delhi":
        return db.query(func.count(DemandRecord.id)).scalar() or 0
    return (db.query(func.count(StateDemandRecord.id))
            .filter(StateDemandRecord.state_code == code).scalar() or 0)


def _all_models(code: str) -> list[dict]:
    """Every trained model for a state — one enriched served.json per resolution."""
    if code == "delhi":
        return []   # Delhi models are served via the Delhi pipeline, not models/states/
    out: list[dict] = []
    base = _MODELS / code
    for res in _RES_ORDER:
        p = base / res / "served.json"
        if p.exists():
            try:
                meta = json.loads(p.read_text())
            except Exception:
                meta = {}
            meta.setdefault("resolution", res)
            out.append(meta)
    return out


def _model_info(code: str) -> dict | None:
    """The single headline model for a state (back-compat for the list view)."""
    if code == "delhi":
        return {"resolution": "multi", "served_model": "lightgbm/xgboost",
                "note": "primary Delhi models (daily/hourly/5min)"}
    by_res = {m.get("resolution"): m for m in _all_models(code)}
    for res in _PRIMARY_ORDER:
        if res in by_res:
            return by_res[res]
    return None


def _trim(m: dict | None) -> dict | None:
    """Drop the heavy feature_list so the list endpoint stays lean."""
    if not m:
        return m
    return {k: v for k, v in m.items() if k != "feature_list"}


_FORECASTERS: dict = {}  # (code, resolution) -> loaded forecaster, cached


def _load_state_forecaster(code: str, resolution: str, meta: dict):
    """Load (and cache) the served forecaster for a state/resolution."""
    key = (code, resolution)
    if key not in _FORECASTERS:
        from src.models.lightgbm_model import LightGBMForecaster
        from src.models.xgboost_model import XGBoostForecaster
        cls = XGBoostForecaster if meta.get("served_model") == "XGBoost" else LightGBMForecaster
        _FORECASTERS[key] = cls.load(_MODELS / code / resolution)
    return _FORECASTERS[key]


def _state_dict(db: Session, st, detail: bool = False) -> dict:
    n = _row_count(db, st.code)
    models = _all_models(st.code)
    mi = _model_info(st.code)
    d = {
        "code": st.code, "name": st.name, "region": st.region.value,
        "tier": st.tier.value, "method": st.method.value, "scraper": st.scraper,
        "discoms": list(st.discoms), "discom_level": st.discom_level,
        "rows_stored": int(n), "has_data": n > 0,
        "has_model": bool(models) or (st.code == "delhi" and mi is not None),
        "model_count": len(models),
    }
    if detail:
        if mi:
            d["model"] = mi
        d["models"] = models                 # full, with feature_list
        d["source_url"] = st.source_url
        d["notes"] = st.notes
    else:
        if mi:
            d["model"] = _trim(mi)            # headline only, no feature_list
    return d


@router.get("")
def list_states(db: Session = Depends(get_db)):
    """Registry + live status for all 36 states/UTs, with a rollout summary."""
    states = [_state_dict(db, st) for st in INDIAN_STATES]
    summary = {
        "total": len(states),
        "with_data": sum(1 for s in states if s["has_data"]),
        "with_model": sum(1 for s in states if s["has_model"]),
        "direct": sum(1 for st in INDIAN_STATES if st.tier.value == "direct"),
        "fallback": sum(1 for st in INDIAN_STATES if st.tier.value == "fallback"),
        "deferred": sum(1 for st in INDIAN_STATES if st.tier.value == "deferred"),
        "discom_level": sum(1 for st in INDIAN_STATES if st.discom_level),
    }
    return {"summary": summary, "states": states}


@router.get("/{code}")
def state_detail(code: str, db: Session = Depends(get_db)):
    st = STATES_BY_CODE.get(code)
    if not st:
        raise HTTPException(status_code=404, detail=f"Unknown state '{code}'")
    return _state_dict(db, st, detail=True)


@router.get("/{code}/forecast")
def state_forecast(
    code: str,
    resolution: str | None = Query(None, description="model resolution; default = headline model"),
    target: str | None = Query(None, description="forecast date YYYY-MM-DD; default = day after last data"),
    db: Session = Depends(get_db),
):
    """Day-ahead demand forecast for a state, via the recursive engine over its
    own trained model. Returns timestamps + predicted/lower/upper MW."""
    models = _all_models(code)   # also covers all_india (a model, not a registered state)
    if not models:
        raise HTTPException(status_code=404, detail=f"No trained model for '{code}'")
    if resolution:
        meta = next((m for m in models if m.get("resolution") == resolution), None)
        if not meta:
            have = [m.get("resolution") for m in models]
            raise HTTPException(status_code=404,
                                detail=f"No '{resolution}' model for '{code}' (have {have})")
    else:
        meta = _model_info(code)
    res = meta["resolution"]

    tdate = None
    if target:
        try:
            tdate = datetime.strptime(target, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(status_code=400, detail="target must be YYYY-MM-DD")

    try:
        forecaster = _load_state_forecaster(code, res, meta)
        out = forecast_state_future(code, res, tdate, forecaster, db,
                                    source=meta.get("source", "state_demand"))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:  # pragma: no cover
        logger.exception("state forecast failed")
        raise HTTPException(status_code=500, detail=f"forecast failed: {e}")

    out["served_model"] = meta.get("served_model")
    out["champion_cv_mape"] = meta.get("champion_cv_mape")
    return out


@router.get("/{code}/demand")
def state_demand(code: str,
                 days: int = Query(14, ge=1, le=365),
                 max_points: int = Query(1500, ge=100, le=5000),
                 db: Session = Depends(get_db)):
    """Recent stored demand series for a state (for the dashboard chart).

    Downsamples (uniform stride) to at most ``max_points`` so a fine-resolution
    state (Delhi 5-min = thousands of points) never ships a heavy payload — keeps
    the dashboard instant.
    """
    st = STATES_BY_CODE.get(code)
    if not st:
        raise HTTPException(status_code=404, detail=f"Unknown state '{code}'")

    if code == "delhi":
        latest = db.query(func.max(DemandRecord.timestamp)).scalar()
        if latest is None:
            return {"code": code, "name": st.name, "series": [], "n": 0}
        cutoff = latest - timedelta(days=days)
        q = (db.query(DemandRecord.timestamp, DemandRecord.delhi_mw)
             .filter(DemandRecord.timestamp >= cutoff)
             .order_by(DemandRecord.timestamp.asc()).all())
    else:
        latest = (db.query(func.max(StateDemandRecord.timestamp))
                  .filter(StateDemandRecord.state_code == code).scalar())
        if latest is None:
            return {"code": code, "name": st.name, "series": [], "n": 0}
        cutoff = latest - timedelta(days=days)
        q = (db.query(StateDemandRecord.timestamp, StateDemandRecord.demand_mw)
             .filter(StateDemandRecord.state_code == code,
                     StateDemandRecord.timestamp >= cutoff)
             .order_by(StateDemandRecord.timestamp.asc()).all())

    series = [{"t": str(t), "mw": round(float(v), 1)} for t, v in q if v is not None]
    total = len(series)
    if total > max_points:
        stride = total // max_points + 1
        series = series[::stride]
    return {"code": code, "name": st.name, "latest": str(latest),
            "series": series, "n": len(series), "total": total}

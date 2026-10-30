"""State-wise endpoints — the all-India rollout surface.

Exposes, for every Indian state/UT: the registry entry (region, DISCOMs, tier,
scraper), live data-collection status (rows stored), recent demand, and — where a
model has been trained with scripts/train_state.py — its champion metrics. This
powers the dashboard's state-wise view.

Note: full recursive per-state *forecasting* is a follow-on; the forecast engine
(src/forecasting/future.py) is currently Delhi-specific. These endpoints serve
status + history + model metrics, which is what the state-wise UI needs today.
"""

import json
import logging
from datetime import timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func

from src.data.db.session import get_db
from src.data.db.models import StateDemandRecord, StatePSPDaily, DemandRecord
from src.data.scrapers.states import INDIAN_STATES, STATES_BY_CODE

logger = logging.getLogger(__name__)
router = APIRouter()

_MODELS = Path("models") / "states"


def _row_count(db: Session, code: str) -> int:
    if code == "delhi":
        return db.query(func.count(DemandRecord.id)).scalar() or 0
    return (db.query(func.count(StateDemandRecord.id))
            .filter(StateDemandRecord.state_code == code).scalar() or 0)


def _model_info(code: str) -> dict | None:
    """Return served-model metadata if a model was trained for this state."""
    if code == "delhi":
        return {"resolution": "multi", "served_model": "lightgbm/xgboost",
                "note": "primary Delhi models (daily/hourly/5min)"}
    for res in ("hourly", "daily", "5min"):
        p = _MODELS / code / res / "served.json"
        if p.exists():
            try:
                return {"resolution": res, **json.loads(p.read_text())}
            except Exception:
                return {"resolution": res}
    return None


def _state_dict(db: Session, st, detail: bool = False) -> dict:
    n = _row_count(db, st.code)
    mi = _model_info(st.code)
    d = {
        "code": st.code, "name": st.name, "region": st.region.value,
        "tier": st.tier.value, "method": st.method.value, "scraper": st.scraper,
        "discoms": list(st.discoms), "discom_level": st.discom_level,
        "rows_stored": int(n), "has_data": n > 0, "has_model": mi is not None,
    }
    if mi:
        d["model"] = mi
    if detail:
        d["source_url"] = st.source_url
        d["notes"] = st.notes
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


@router.get("/{code}/demand")
def state_demand(code: str,
                 days: int = Query(14, ge=1, le=365),
                 db: Session = Depends(get_db)):
    """Recent stored demand series for a state (for the dashboard chart)."""
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
    return {"code": code, "name": st.name, "latest": str(latest), "series": series, "n": len(series)}

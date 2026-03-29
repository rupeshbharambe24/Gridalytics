"""Admin endpoints - model management, retraining, scraper status, scheduler info."""

import json
import logging
import threading
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func

from src.data.db.session import get_db
from src.data.db.models import DemandRecord, WeatherRecord, AQIRecord, User
from src.api.auth import require_admin
from config import settings

logger = logging.getLogger(__name__)
router = APIRouter()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class RetrainRequest(BaseModel):
    resolution: str = "hourly"


# ---------------------------------------------------------------------------
# GET /models  -  List all trained models with metrics
# ---------------------------------------------------------------------------

@router.get("/models")
def list_trained_models(admin: User = Depends(require_admin)):
    """List all trained models found in the models/ directory."""
    models_root = Path("models")
    if not models_root.exists():
        return {"models": []}

    results = []
    for resolution_dir in sorted(models_root.iterdir()):
        if not resolution_dir.is_dir():
            continue
        resolution = resolution_dir.name
        for model_dir in sorted(resolution_dir.iterdir()):
            if not model_dir.is_dir():
                continue
            meta_path = model_dir / "meta.json"
            if not meta_path.exists():
                continue

            try:
                meta = json.loads(meta_path.read_text())
            except Exception:
                meta = {}

            # Compute total file size of the model directory
            total_bytes = sum(f.stat().st_size for f in model_dir.rglob("*") if f.is_file())
            size_mb = round(total_bytes / (1024 * 1024), 2)

            feature_names = meta.get("feature_names", [])

            results.append({
                "name": meta.get("name", model_dir.name),
                "resolution": resolution,
                "path": str(model_dir),
                "size_mb": size_mb,
                "feature_count": len(feature_names),
                "params": meta.get("params", {}),
            })

    return {"models": results}


# ---------------------------------------------------------------------------
# POST /retrain  -  Trigger manual retraining in a background thread
# ---------------------------------------------------------------------------

_retrain_status: dict = {"running": False, "last_resolution": None, "last_error": None}


def _retrain_worker(resolution: str):
    """Run training in a background thread."""
    global _retrain_status
    try:
        from scripts.initial_train import train_and_evaluate
        train_and_evaluate(resolution)
        _retrain_status["last_error"] = None
        logger.info(f"Retraining complete for {resolution}")
    except Exception as e:
        _retrain_status["last_error"] = str(e)
        logger.error(f"Retraining failed for {resolution}: {e}", exc_info=True)
    finally:
        _retrain_status["running"] = False


@router.post("/retrain")
def trigger_retrain(body: RetrainRequest, admin: User = Depends(require_admin)):
    """Trigger manual model retraining (runs in background)."""
    if body.resolution not in ("5min", "hourly", "daily"):
        raise HTTPException(status_code=400, detail="Resolution must be 'hourly' or 'daily'")

    if _retrain_status["running"]:
        raise HTTPException(status_code=409, detail="A retraining job is already running")

    _retrain_status["running"] = True
    _retrain_status["last_resolution"] = body.resolution
    _retrain_status["last_error"] = None

    thread = threading.Thread(target=_retrain_worker, args=(body.resolution,), daemon=True)
    thread.start()

    return {"status": "started", "resolution": body.resolution}


@router.get("/retrain/status")
def retrain_status(admin: User = Depends(require_admin)):
    """Check the status of the last retraining job."""
    return _retrain_status


# ---------------------------------------------------------------------------
# GET /scraper-status  -  Data freshness and row counts
# ---------------------------------------------------------------------------

@router.get("/scraper-status")
def get_scraper_status(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    """Return data freshness: latest timestamps, hours old, and row counts."""
    now = datetime.utcnow()

    # Demand
    demand_latest = db.query(func.max(DemandRecord.timestamp)).scalar()
    demand_count = db.query(func.count(DemandRecord.id)).scalar()

    # Weather
    weather_latest = db.query(func.max(WeatherRecord.timestamp)).scalar()
    weather_count = db.query(func.count(WeatherRecord.id)).scalar()

    # AQI
    aqi_latest = db.query(func.max(AQIRecord.date)).scalar()
    aqi_count = db.query(func.count(AQIRecord.id)).scalar()

    def hours_old(ts):
        if ts is None:
            return None
        if isinstance(ts, datetime):
            delta = now - ts
        else:
            # ts is a date object
            delta = now - datetime.combine(ts, datetime.min.time())
        return round(delta.total_seconds() / 3600, 1)

    return {
        "demand_5min": {
            "latest": str(demand_latest) if demand_latest else None,
            "hours_old": hours_old(demand_latest),
            "row_count": demand_count,
        },
        "weather_hourly": {
            "latest": str(weather_latest) if weather_latest else None,
            "hours_old": hours_old(weather_latest),
            "row_count": weather_count,
        },
        "aqi_daily": {
            "latest": str(aqi_latest) if aqi_latest else None,
            "hours_old": hours_old(aqi_latest),
            "row_count": aqi_count,
        },
    }


# ---------------------------------------------------------------------------
# GET /scheduler-jobs  -  Configured scheduler jobs (hardcoded from config)
# ---------------------------------------------------------------------------

@router.get("/scheduler-jobs")
def get_scheduler_jobs(admin: User = Depends(require_admin)):
    """Return list of configured scheduler jobs with intervals and schedules.

    Since APScheduler runs in a separate process, we return the
    known configuration from the scheduler module rather than live state.
    """
    scrape_interval = settings.SCRAPE_INTERVAL_HOURS

    jobs = [
        {
            "id": "demand_scrape",
            "name": "SLDC Demand Scrape",
            "trigger": "interval",
            "interval": f"every {scrape_interval}h",
            "description": "Scrapes last 2 days of demand data from Delhi SLDC",
        },
        {
            "id": "weather_archive",
            "name": "Weather Archive Backfill",
            "trigger": "cron",
            "interval": "daily at 02:00",
            "description": "Backfills weather data from Open-Meteo archive API",
        },
        {
            "id": "weather_forecast",
            "name": "Weather Forecast Fetch",
            "trigger": "interval",
            "interval": "every 6h",
            "description": "Fetches 7-day weather forecast for predictions",
        },
        {
            "id": "holidays",
            "name": "Holiday Calendar Update",
            "trigger": "cron",
            "interval": "weekly on Sunday at 03:00",
            "description": "Updates Indian holiday calendar for current and next year",
        },
        {
            "id": "prediction_tracker",
            "name": "Prediction Tracker (predict + evaluate)",
            "trigger": "cron",
            "interval": "daily at 23:00",
            "description": "Predicts tomorrow's demand and evaluates yesterday's prediction",
        },
        {
            "id": "status",
            "name": "Data Status Report",
            "trigger": "interval",
            "interval": "every 1h",
            "description": "Logs current data freshness status",
        },
    ]

    return {"jobs": jobs}

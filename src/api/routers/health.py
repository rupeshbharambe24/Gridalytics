"""Health check endpoints."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func

from src.data.db.session import get_db
from src.data.db.models import DemandRecord, WeatherRecord
from src.api.model_registry import get_available_models
from src.api.schemas import HealthResponse

router = APIRouter()


@router.get("/ready", response_model=HealthResponse)
def health_check(db: Session = Depends(get_db)):
    """Readiness check - verifies DB and models are loaded."""
    models = get_available_models()
    d_latest = db.query(func.max(DemandRecord.timestamp)).scalar()
    w_latest = db.query(func.max(WeatherRecord.timestamp)).scalar()

    return HealthResponse(
        status="ok" if models else "degraded",
        models_loaded=len(models),
        database="connected",
        demand_latest=str(d_latest) if d_latest else None,
        weather_latest=str(w_latest) if w_latest else None,
    )

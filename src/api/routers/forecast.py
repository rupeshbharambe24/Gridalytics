"""Forecast endpoints - predictions for daily, hourly, 5-min demand.

Handles both:
- Historical dates (where demand data exists): uses full feature pipeline
- Future dates (beyond available data): uses recursive forecasting engine
"""

import logging
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func

from src.data.db.session import get_db
from src.data.db.models import DemandRecord
from src.features.pipeline import FeaturePipeline
from src.api.model_registry import get_model, get_available_models
from src.api.schemas import ForecastResponse, WhatIfRequest
from src.forecasting.future import forecast_future

logger = logging.getLogger(__name__)
router = APIRouter()


def _get_last_data_date(db: Session) -> date | None:
    """Get the last date we have demand data for."""
    latest = db.query(func.max(DemandRecord.timestamp)).scalar()
    return latest.date() if latest else None


def _build_forecast(
    resolution: str,
    target_date: str,
    model_name: str | None,
    db: Session,
    overrides: dict | None = None,
) -> ForecastResponse:
    """Core forecast logic - dispatches to historical or future engine."""
    model = get_model(resolution, model_name)
    if model is None:
        raise HTTPException(status_code=503, detail=f"No model loaded for {resolution}")

    try:
        dt = datetime.strptime(target_date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")

    last_data = _get_last_data_date(db)
    is_future = last_data is None or dt > last_data

    if is_future:
        # Use future forecasting engine (recursive prediction)
        logger.info(f"Future forecast for {dt} (data ends {last_data})")
        try:
            result = forecast_future(resolution, dt, model, db, overrides=overrides)
        except Exception as e:
            logger.error(f"Future forecast failed: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Forecast generation failed: {str(e)}")

        return ForecastResponse(
            timestamps=result["timestamps"],
            predicted_mw=result["predicted_mw"],
            lower_bound_mw=result["lower_bound_mw"],
            upper_bound_mw=result["upper_bound_mw"],
            model_name=model.name if hasattr(model, "name") else "unknown",
            resolution=resolution,
            metadata={"date": target_date, "mode": "future", "n_points": len(result["predicted_mw"])},
        )
    else:
        # Historical: use full feature pipeline
        lag_days = {"5min": 10, "hourly": 35, "daily": 750}
        start = dt - timedelta(days=lag_days.get(resolution, 32))

        pipeline = FeaturePipeline(resolution, db)
        df = pipeline.build(start, dt)

        if df.empty:
            raise HTTPException(status_code=404, detail="No data available for the requested date")

        target_mask = df.index.date == dt
        if not target_mask.any():
            raise HTTPException(status_code=404, detail=f"No data for {target_date}")

        target_df = df[target_mask]
        features = pipeline.get_feature_names(df)
        sub_regional = ["brpl_mw", "bypl_mw", "ndpl_mw", "ndmc_mw", "mes_mw"]
        features = [f for f in features if f not in sub_regional]
        X = target_df[features].fillna(0)

        try:
            point, lower, upper = model.predict_interval(X)
        except Exception:
            point = model.predict(X)
            lower = point * 0.95
            upper = point * 1.05

        return ForecastResponse(
            timestamps=[str(t) for t in target_df.index],
            predicted_mw=[round(float(v), 1) for v in point],
            lower_bound_mw=[round(float(v), 1) for v in lower],
            upper_bound_mw=[round(float(v), 1) for v in upper],
            model_name=model.name if hasattr(model, "name") else "unknown",
            resolution=resolution,
            metadata={"date": target_date, "mode": "historical", "n_points": len(point)},
        )


@router.get("/{resolution}", response_model=ForecastResponse)
def get_forecast(
    resolution: str,
    date: str = Query(..., description="Target date (YYYY-MM-DD)"),
    model: str | None = Query(None, description="Model name (lightgbm, xgboost)"),
    db: Session = Depends(get_db),
):
    """Get demand forecast for a specific date (past or future)."""
    if resolution not in ("daily", "hourly", "5min"):
        raise HTTPException(status_code=400, detail="Resolution must be daily, hourly, or 5min")
    return _build_forecast(resolution, date, model, db)


@router.get("/{resolution}/range", response_model=ForecastResponse)
def get_forecast_range(
    resolution: str,
    start: str = Query(..., description="Start date (YYYY-MM-DD)"),
    end: str = Query(..., description="End date (YYYY-MM-DD)"),
    model_name: str | None = Query(None),
    db: Session = Depends(get_db),
):
    """Get forecast for a date range (supports future dates)."""
    if resolution not in ("daily", "hourly", "5min"):
        raise HTTPException(status_code=400, detail="Invalid resolution")

    model_obj = get_model(resolution, model_name)
    if model_obj is None:
        raise HTTPException(status_code=503, detail=f"No model for {resolution}")

    try:
        start_dt = datetime.strptime(start, "%Y-%m-%d").date()
        end_dt = datetime.strptime(end, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format")

    # Limit range to 90 days to prevent very long requests
    if (end_dt - start_dt).days > 90:
        raise HTTPException(status_code=400, detail="Date range cannot exceed 90 days")

    # Collect forecasts day by day
    all_ts, all_pred, all_lo, all_hi = [], [], [], []
    current = start_dt

    while current <= end_dt:
        try:
            resp = _build_forecast(resolution, current.isoformat(), model_name, db)
            all_ts.extend(resp.timestamps)
            all_pred.extend(resp.predicted_mw)
            all_lo.extend(resp.lower_bound_mw)
            all_hi.extend(resp.upper_bound_mw)
        except HTTPException:
            pass  # skip days with no data
        current += timedelta(days=1)

    if not all_ts:
        raise HTTPException(status_code=404, detail="No forecast data for the range")

    return ForecastResponse(
        timestamps=all_ts,
        predicted_mw=all_pred,
        lower_bound_mw=all_lo,
        upper_bound_mw=all_hi,
        model_name=model_obj.name if hasattr(model_obj, "name") else "unknown",
        resolution=resolution,
        metadata={"start": start, "end": end, "n_points": len(all_ts)},
    )


@router.post("/what-if", response_model=ForecastResponse)
def what_if_forecast(
    body: WhatIfRequest,
    db: Session = Depends(get_db),
):
    """Run a what-if scenario with custom weather/holiday overrides.

    Works for both past and future dates. Overrides:
    - temperature: float (C)
    - humidity: float (%)
    - is_holiday: bool
    - aqi: float
    """
    return _build_forecast(body.resolution, body.date, None, db, overrides=body.overrides)


@router.get("/models/available")
def list_models():
    """List all available models."""
    return get_available_models()

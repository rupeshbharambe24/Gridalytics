"""Forecast endpoints - predictions for daily, hourly, 5-min demand."""

import logging
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from src.data.db.session import get_db
from src.features.pipeline import FeaturePipeline
from src.api.model_registry import get_model, get_available_models
from src.api.schemas import ForecastResponse, WhatIfRequest

logger = logging.getLogger(__name__)
router = APIRouter()


def _build_forecast(
    resolution: str,
    target_date: str,
    model_name: str | None,
    db: Session,
) -> ForecastResponse:
    """Core forecast logic shared by multiple endpoints."""
    model = get_model(resolution, model_name)
    if model is None:
        raise HTTPException(status_code=503, detail=f"No model loaded for {resolution}")

    # Parse target date
    try:
        dt = datetime.strptime(target_date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")

    # Build features for the target date
    # We need historical data for lag features, so load a window before the target
    lag_days = {"5min": 10, "hourly": 35, "daily": 750}
    start = dt - timedelta(days=lag_days.get(resolution, 32))

    pipeline = FeaturePipeline(resolution, db)
    df = pipeline.build(start, dt)

    if df.empty:
        raise HTTPException(status_code=404, detail="No data available for the requested date")

    # Filter to the target date only
    target_mask = df.index.date == dt
    if not target_mask.any():
        raise HTTPException(status_code=404, detail=f"No data for {target_date}")

    target_df = df[target_mask]
    features = pipeline.get_feature_names(df)
    sub_regional = ["brpl_mw", "bypl_mw", "ndpl_mw", "ndmc_mw", "mes_mw"]
    features = [f for f in features if f not in sub_regional]
    X = target_df[features].fillna(0)

    # Predict
    try:
        point, lower, upper = model.predict_interval(X)
    except Exception as e:
        logger.error(f"Prediction failed: {e}")
        # Fallback to point prediction
        point = model.predict(X)
        lower = point * 0.95
        upper = point * 1.05

    return ForecastResponse(
        timestamps=[str(t) for t in target_df.index],
        predicted_mw=[round(float(v), 1) for v in point],
        lower_bound_mw=[round(float(v), 1) for v in lower],
        upper_bound_mw=[round(float(v), 1) for v in upper],
        model_name=model.name if hasattr(model, 'name') else "unknown",
        resolution=resolution,
        metadata={"date": target_date, "n_points": len(point)},
    )


@router.get("/{resolution}", response_model=ForecastResponse)
def get_forecast(
    resolution: str,
    date: str = Query(..., description="Target date (YYYY-MM-DD)"),
    model: str | None = Query(None, description="Model name (lightgbm, xgboost)"),
    db: Session = Depends(get_db),
):
    """Get demand forecast for a specific date."""
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
    """Get forecast for a date range."""
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

    lag_days = {"5min": 10, "hourly": 35, "daily": 750}
    load_start = start_dt - timedelta(days=lag_days.get(resolution, 32))

    pipeline = FeaturePipeline(resolution, db)
    df = pipeline.build(load_start, end_dt)

    if df.empty:
        raise HTTPException(status_code=404, detail="No data available")

    mask = (df.index.date >= start_dt) & (df.index.date <= end_dt)
    target_df = df[mask]

    if target_df.empty:
        raise HTTPException(status_code=404, detail="No data for the date range")

    features = pipeline.get_feature_names(df)
    sub_regional = ["brpl_mw", "bypl_mw", "ndpl_mw", "ndmc_mw", "mes_mw"]
    features = [f for f in features if f not in sub_regional]
    X = target_df[features].fillna(0)

    try:
        point, lower, upper = model_obj.predict_interval(X)
    except Exception:
        point = model_obj.predict(X)
        lower = point * 0.95
        upper = point * 1.05

    return ForecastResponse(
        timestamps=[str(t) for t in target_df.index],
        predicted_mw=[round(float(v), 1) for v in point],
        lower_bound_mw=[round(float(v), 1) for v in lower],
        upper_bound_mw=[round(float(v), 1) for v in upper],
        model_name=model_obj.name if hasattr(model_obj, 'name') else "unknown",
        resolution=resolution,
        metadata={"start": start, "end": end, "n_points": len(point)},
    )


@router.post("/what-if", response_model=ForecastResponse)
def what_if_forecast(
    body: WhatIfRequest,
    db: Session = Depends(get_db),
):
    """Run a what-if scenario with custom weather/holiday overrides."""
    resolution = body.resolution
    model_obj = get_model(resolution)
    if model_obj is None:
        raise HTTPException(status_code=503, detail=f"No model for {resolution}")

    try:
        dt = datetime.strptime(body.date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format")

    lag_days = {"5min": 10, "hourly": 35, "daily": 750}
    load_start = dt - timedelta(days=lag_days.get(resolution, 32))

    pipeline = FeaturePipeline(resolution, db)
    df = pipeline.build(load_start, dt)

    if df.empty:
        raise HTTPException(status_code=404, detail="No data available")

    mask = df.index.date == dt
    target_df = df[mask].copy()

    if target_df.empty:
        raise HTTPException(status_code=404, detail=f"No data for {body.date}")

    # Apply overrides
    overrides = body.overrides
    if "temperature" in overrides and "temperature_2m" in target_df.columns:
        target_df["temperature_2m"] = overrides["temperature"]
        target_df["CDD"] = max(overrides["temperature"] - 24, 0)
        target_df["HDD"] = max(18 - overrides["temperature"], 0)
        target_df["temp_squared"] = overrides["temperature"] ** 2
    if "humidity" in overrides and "relative_humidity_2m" in target_df.columns:
        target_df["relative_humidity_2m"] = overrides["humidity"]
    if "is_holiday" in overrides and "is_holiday" in target_df.columns:
        target_df["is_holiday"] = int(overrides["is_holiday"])
    if "aqi" in overrides and "aqi_value" in target_df.columns:
        target_df["aqi_value"] = overrides["aqi"]

    features = pipeline.get_feature_names(df)
    sub_regional = ["brpl_mw", "bypl_mw", "ndpl_mw", "ndmc_mw", "mes_mw"]
    features = [f for f in features if f not in sub_regional]
    X = target_df[features].fillna(0)

    point = model_obj.predict(X)

    return ForecastResponse(
        timestamps=[str(t) for t in target_df.index],
        predicted_mw=[round(float(v), 1) for v in point],
        lower_bound_mw=[round(float(v) * 0.95, 1) for v in point],
        upper_bound_mw=[round(float(v) * 1.05, 1) for v in point],
        model_name=model_obj.name if hasattr(model_obj, 'name') else "unknown",
        resolution=resolution,
        metadata={"scenario": "what-if", "overrides": overrides},
    )


@router.get("/models/available")
def list_models():
    """List all available models."""
    return get_available_models()

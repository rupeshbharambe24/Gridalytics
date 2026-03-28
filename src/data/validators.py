"""Data quality validation for EDFS data pipeline."""

import logging
from datetime import date, timedelta

import pandas as pd
from sqlalchemy.orm import Session
from sqlalchemy import func

from src.data.db.models import DemandRecord, WeatherRecord

logger = logging.getLogger(__name__)


def check_demand_gaps(session: Session, resolution_minutes: int = 5, lookback_days: int = 7) -> list[dict]:
    """Find gaps in demand data for the last N days."""
    cutoff = date.today() - timedelta(days=lookback_days)
    records = (
        session.query(DemandRecord.timestamp)
        .filter(DemandRecord.timestamp >= cutoff.isoformat())
        .order_by(DemandRecord.timestamp)
        .all()
    )

    if not records:
        return [{"issue": "no_data", "message": f"No demand data in last {lookback_days} days"}]

    timestamps = pd.Series([r.timestamp for r in records])
    expected_delta = pd.Timedelta(minutes=resolution_minutes)
    gaps = []

    for i in range(1, len(timestamps)):
        delta = timestamps.iloc[i] - timestamps.iloc[i - 1]
        if delta > expected_delta * 2:
            gaps.append({
                "issue": "gap",
                "start": str(timestamps.iloc[i - 1]),
                "end": str(timestamps.iloc[i]),
                "duration_hours": delta.total_seconds() / 3600,
            })

    return gaps


def check_weather_gaps(session: Session, lookback_days: int = 7) -> list[dict]:
    """Find gaps in weather data."""
    cutoff = date.today() - timedelta(days=lookback_days)
    records = (
        session.query(WeatherRecord.timestamp)
        .filter(WeatherRecord.timestamp >= cutoff.isoformat())
        .order_by(WeatherRecord.timestamp)
        .all()
    )

    if not records:
        return [{"issue": "no_data", "message": f"No weather data in last {lookback_days} days"}]

    timestamps = pd.Series([r.timestamp for r in records])
    expected_delta = pd.Timedelta(hours=1)
    gaps = []

    for i in range(1, len(timestamps)):
        delta = timestamps.iloc[i] - timestamps.iloc[i - 1]
        if delta > expected_delta * 2:
            gaps.append({
                "issue": "gap",
                "start": str(timestamps.iloc[i - 1]),
                "end": str(timestamps.iloc[i]),
                "duration_hours": delta.total_seconds() / 3600,
            })

    return gaps


def check_data_freshness(session: Session) -> dict:
    """Check how fresh the data is."""
    latest_demand = session.query(func.max(DemandRecord.timestamp)).scalar()
    latest_weather = session.query(func.max(WeatherRecord.timestamp)).scalar()

    from datetime import datetime
    now = datetime.utcnow()

    return {
        "demand_latest": str(latest_demand) if latest_demand else None,
        "demand_age_hours": (now - latest_demand).total_seconds() / 3600 if latest_demand else None,
        "weather_latest": str(latest_weather) if latest_weather else None,
        "weather_age_hours": (now - latest_weather).total_seconds() / 3600 if latest_weather else None,
        "demand_stale": (now - latest_demand).total_seconds() / 3600 > 12 if latest_demand else True,
        "weather_stale": (now - latest_weather).total_seconds() / 3600 > 24 if latest_weather else True,
    }


def validate_dataframe(df: pd.DataFrame, name: str = "data") -> dict:
    """Run general quality checks on a DataFrame."""
    report = {
        "name": name,
        "rows": len(df),
        "columns": list(df.columns),
        "null_counts": df.isnull().sum().to_dict(),
        "null_pct": (df.isnull().sum() / len(df) * 100).round(2).to_dict() if len(df) > 0 else {},
        "duplicates": df.duplicated().sum(),
    }

    issues = []
    for col, pct in report["null_pct"].items():
        if pct > 10:
            issues.append(f"{col} has {pct}% missing values")

    if report["duplicates"] > 0:
        issues.append(f"{report['duplicates']} duplicate rows found")

    report["issues"] = issues
    report["is_valid"] = len(issues) == 0

    if issues:
        for issue in issues:
            logger.warning(f"[{name}] {issue}")

    return report

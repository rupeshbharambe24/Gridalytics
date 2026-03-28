"""Load data from database into pandas DataFrames for model training."""

from datetime import date, datetime

import pandas as pd
from sqlalchemy.orm import Session
from sqlalchemy import func

from src.data.db.models import DemandRecord, WeatherRecord, AQIRecord, HolidayRecord


def load_demand(
    session: Session,
    resolution: str,
    start_date: date | None = None,
    end_date: date | None = None,
) -> pd.DataFrame:
    """Load demand data at the specified resolution.

    Args:
        session: Database session
        resolution: '5min', 'hourly', or 'daily'
        start_date: Optional start date filter
        end_date: Optional end date filter

    Returns:
        DataFrame with timestamp index and demand columns
    """
    query = session.query(DemandRecord)

    if start_date:
        query = query.filter(DemandRecord.timestamp >= datetime.combine(start_date, datetime.min.time()))
    if end_date:
        query = query.filter(DemandRecord.timestamp <= datetime.combine(end_date, datetime.max.time()))

    query = query.order_by(DemandRecord.timestamp)
    df = pd.read_sql(query.statement, session.bind)

    if df.empty:
        return df

    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.set_index("timestamp")

    # Resample based on resolution
    demand_cols = ["delhi_mw", "brpl_mw", "bypl_mw", "ndpl_mw", "ndmc_mw", "mes_mw"]

    if resolution == "hourly":
        df = df[demand_cols].resample("1h").mean().dropna(subset=["delhi_mw"])
    elif resolution == "daily":
        df = df[demand_cols].resample("1D").mean().dropna(subset=["delhi_mw"])
    # else '5min' - keep as-is

    return df


def load_weather(
    session: Session,
    start_date: date | None = None,
    end_date: date | None = None,
) -> pd.DataFrame:
    """Load hourly weather data."""
    query = session.query(WeatherRecord)

    if start_date:
        query = query.filter(WeatherRecord.timestamp >= datetime.combine(start_date, datetime.min.time()))
    if end_date:
        query = query.filter(WeatherRecord.timestamp <= datetime.combine(end_date, datetime.max.time()))

    query = query.order_by(WeatherRecord.timestamp)
    df = pd.read_sql(query.statement, session.bind)

    if df.empty:
        return df

    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.set_index("timestamp")
    df = df.drop(columns=["id", "source", "created_at"], errors="ignore")

    return df


def load_holidays(
    session: Session,
    start_date: date | None = None,
    end_date: date | None = None,
) -> pd.DataFrame:
    """Load holiday data."""
    query = session.query(HolidayRecord)

    if start_date:
        query = query.filter(HolidayRecord.date >= start_date)
    if end_date:
        query = query.filter(HolidayRecord.date <= end_date)

    df = pd.read_sql(query.statement, session.bind)
    return df


def load_aqi(
    session: Session,
    start_date: date | None = None,
    end_date: date | None = None,
) -> pd.DataFrame:
    """Load daily AQI data."""
    query = session.query(AQIRecord)

    if start_date:
        query = query.filter(AQIRecord.date >= start_date)
    if end_date:
        query = query.filter(AQIRecord.date <= end_date)

    df = pd.read_sql(query.statement, session.bind)
    return df


def get_data_summary(session: Session) -> dict:
    """Get summary of available data in the database."""
    demand_count = session.query(func.count(DemandRecord.id)).scalar()
    weather_count = session.query(func.count(WeatherRecord.id)).scalar()
    holiday_count = session.query(func.count(HolidayRecord.id)).scalar()
    aqi_count = session.query(func.count(AQIRecord.id)).scalar()

    demand_range = session.query(
        func.min(DemandRecord.timestamp),
        func.max(DemandRecord.timestamp),
    ).first()

    weather_range = session.query(
        func.min(WeatherRecord.timestamp),
        func.max(WeatherRecord.timestamp),
    ).first()

    return {
        "demand_5min_rows": demand_count,
        "demand_range": (str(demand_range[0]), str(demand_range[1])) if demand_range[0] else None,
        "weather_hourly_rows": weather_count,
        "weather_range": (str(weather_range[0]), str(weather_range[1])) if weather_range[0] else None,
        "holiday_rows": holiday_count,
        "aqi_rows": aqi_count,
    }

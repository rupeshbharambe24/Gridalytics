"""Load data from database into pandas DataFrames for model training."""

from datetime import date, datetime

import pandas as pd
from sqlalchemy.orm import Session
from sqlalchemy import func

from src.data.db.models import DemandRecord, WeatherRecord, AQIRecord, HolidayRecord, PSPDailyReport


def _query_to_df(session: Session, query) -> pd.DataFrame:
    """Execute a SQLAlchemy ORM query and return a DataFrame."""
    results = query.all()
    if not results:
        return pd.DataFrame()
    records = [{c.name: getattr(r, c.name) for c in r.__table__.columns} for r in results]
    return pd.DataFrame(records)


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
    df = _query_to_df(session, query)

    if df.empty:
        return df

    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.set_index("timestamp")

    # Resample based on resolution
    demand_cols = ["delhi_mw", "brpl_mw", "bypl_mw", "ndpl_mw", "ndmc_mw", "mes_mw"]

    if resolution == "hourly":
        df = df[demand_cols].resample("1h").mean().dropna(subset=["delhi_mw"])
    elif resolution == "daily":
        # For daily: combine 5-min resampled data with PSP daily reports
        df_5min_daily = df[demand_cols].resample("1D").mean().dropna(subset=["delhi_mw"])

        # Also load PSP daily data (goes back to 2015)
        psp_df = _load_psp_daily(session, start_date, end_date)
        if not psp_df.empty:
            # Merge: prefer 5-min resampled (more accurate), fill gaps with PSP
            combined = psp_df.combine_first(df_5min_daily)
            combined = combined.dropna(subset=["delhi_mw"])
            return combined

        df = df_5min_daily
    # else '5min' - keep as-is

    return df


def _load_psp_daily(
    session: Session,
    start_date: date | None = None,
    end_date: date | None = None,
) -> pd.DataFrame:
    """Load PSP daily demand reports (2015-2024)."""
    query = session.query(PSPDailyReport)
    if start_date:
        query = query.filter(PSPDailyReport.date >= start_date)
    if end_date:
        query = query.filter(PSPDailyReport.date <= end_date)
    query = query.order_by(PSPDailyReport.date)

    df = _query_to_df(session, query)
    if df.empty:
        return df

    df["timestamp"] = pd.to_datetime(df["date"])
    df = df.set_index("timestamp")
    df = df.rename(columns={"delhi_demand_met_mw": "delhi_mw"})
    df = df[["delhi_mw"]].dropna()
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
    df = _query_to_df(session, query)

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

    df = _query_to_df(session, query)
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

    df = _query_to_df(session, query)
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

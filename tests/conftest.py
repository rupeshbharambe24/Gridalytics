"""Shared test fixtures for Gridalytics."""

import pytest
from datetime import date, datetime, timedelta

import pandas as pd
import numpy as np
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.data.db.models import Base, DemandRecord, WeatherRecord, HolidayRecord


@pytest.fixture(scope="session")
def test_engine():
    """Create an in-memory SQLite database for tests."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    return engine


@pytest.fixture
def db_session(test_engine):
    """Provide a transactional database session that rolls back after each test."""
    Session = sessionmaker(bind=test_engine)
    session = Session()

    # Seed some test data
    base_date = datetime(2024, 1, 1)
    for i in range(720):  # 30 days of hourly data
        ts = base_date + timedelta(hours=i)
        # Simulate realistic demand: base + daily pattern + noise
        hour = ts.hour
        base_demand = 3500
        daily_pattern = 500 * np.sin(np.pi * (hour - 6) / 12) if 6 <= hour <= 18 else -300
        noise = np.random.normal(0, 50)
        demand = base_demand + daily_pattern + noise

        session.add(DemandRecord(
            timestamp=ts,
            delhi_mw=max(1500, demand),
            brpl_mw=demand * 0.35,
            bypl_mw=demand * 0.20,
            ndpl_mw=demand * 0.25,
            ndmc_mw=demand * 0.10,
            mes_mw=demand * 0.05,
            source="test",
        ))

    # Seed weather data
    for i in range(720):
        ts = base_date + timedelta(hours=i)
        hour = ts.hour
        temp = 15 + 10 * np.sin(np.pi * (hour - 6) / 12) + np.random.normal(0, 2)
        session.add(WeatherRecord(
            timestamp=ts,
            temperature_2m=temp,
            relative_humidity_2m=50 + np.random.normal(0, 10),
            dew_point_2m=temp - 5,
            precipitation_mm=max(0, np.random.normal(0, 0.5)),
            cloud_cover_pct=np.random.uniform(0, 100),
            wind_speed_10m=np.random.uniform(2, 20),
            shortwave_radiation=max(0, 400 * np.sin(np.pi * (hour - 6) / 12)) if 6 <= hour <= 18 else 0,
            source="test",
        ))

    # Seed holidays
    session.add(HolidayRecord(date=date(2024, 1, 1), name="New Year", type="national", category="government"))
    session.add(HolidayRecord(date=date(2024, 1, 26), name="Republic Day", type="national", category="government"))

    session.commit()
    yield session
    session.rollback()
    session.close()


@pytest.fixture
def sample_demand_df():
    """Generate a sample demand DataFrame for testing."""
    dates = pd.date_range("2024-01-01", periods=720, freq="h")
    demand = 3500 + 500 * np.sin(np.pi * (dates.hour - 6) / 12) + np.random.normal(0, 50, 720)
    return pd.DataFrame({"delhi_mw": demand}, index=dates)


@pytest.fixture
def sample_features_df():
    """Generate a sample feature DataFrame for model testing."""
    n = 500
    np.random.seed(42)
    idx = pd.date_range("2024-01-01", periods=n, freq="h")

    df = pd.DataFrame({
        "delhi_mw": 3500 + 500 * np.sin(np.pi * (idx.hour - 6) / 12) + np.random.normal(0, 50, n),
        "delhi_mw_lag_1": np.random.normal(3500, 200, n),
        "delhi_mw_lag_6": np.random.normal(3500, 200, n),
        "delhi_mw_lag_24": np.random.normal(3500, 200, n),
        "delhi_mw_lag_168": np.random.normal(3500, 200, n),
        "delhi_mw_lag_720": np.random.normal(3500, 200, n),
        "delhi_mw_diff_1": np.random.normal(0, 100, n),
        "delhi_mw_diff_24": np.random.normal(0, 100, n),
        "delhi_mw_rmean_6h": np.random.normal(3500, 100, n),
        "delhi_mw_rstd_6h": np.random.uniform(50, 200, n),
        "delhi_mw_rmin_6h": np.random.normal(3200, 100, n),
        "delhi_mw_rmax_6h": np.random.normal(3800, 100, n),
        "delhi_mw_rmean_1d": np.random.normal(3500, 80, n),
        "temperature_2m": 15 + 10 * np.sin(np.pi * (idx.hour - 6) / 12),
        "relative_humidity_2m": np.random.uniform(30, 80, n),
        "dew_point_2m": np.random.normal(10, 3, n),
        "wind_speed_10m": np.random.uniform(2, 20, n),
        "CDD": np.maximum(15 + 10 * np.sin(np.pi * (idx.hour - 6) / 12) - 24, 0),
        "HDD": np.maximum(18 - (15 + 10 * np.sin(np.pi * (idx.hour - 6) / 12)), 0),
        "heat_index": np.random.normal(25, 5, n),
        "temp_squared": (15 + 10 * np.sin(np.pi * (idx.hour - 6) / 12)) ** 2,
        "temp_x_hour": (15 + 10 * np.sin(np.pi * (idx.hour - 6) / 12)) * idx.hour,
        "hour_sin": np.sin(2 * np.pi * idx.hour / 24),
        "hour_cos": np.cos(2 * np.pi * idx.hour / 24),
        "hour": idx.hour,
        "dayofweek": idx.dayofweek,
        "dow_sin": np.sin(2 * np.pi * idx.dayofweek / 7),
        "dow_cos": np.cos(2 * np.pi * idx.dayofweek / 7),
        "month_sin": np.sin(2 * np.pi * idx.month / 12),
        "month_cos": np.cos(2 * np.pi * idx.month / 12),
        "month": idx.month,
        "is_weekend": (idx.dayofweek >= 5).astype(int),
        "is_peak_hour": ((idx.hour >= 14) & (idx.hour <= 17)).astype(int),
        "is_night": ((idx.hour >= 22) | (idx.hour <= 5)).astype(int),
        "is_holiday": 0,
        "is_festival": 0,
        "aqi_value": 100,
    }, index=idx)

    return df

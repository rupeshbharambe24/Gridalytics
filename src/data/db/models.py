"""SQLAlchemy ORM models for all EDFS data tables."""

from datetime import datetime, date, time
from sqlalchemy import (
    Column, Integer, Float, String, DateTime, Boolean, Date, Time,
    UniqueConstraint, Index,
)
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class DemandRecord(Base):
    """5-minute interval demand data from Delhi SLDC."""
    __tablename__ = "demand_5min"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    delhi_mw = Column(Float, nullable=False)
    brpl_mw = Column(Float)
    bypl_mw = Column(Float)
    ndpl_mw = Column(Float)
    ndmc_mw = Column(Float)
    mes_mw = Column(Float)
    source = Column(String(20), default="sldc")
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("timestamp", name="uq_demand_timestamp"),
        Index("ix_demand_ts", "timestamp"),
    )


class WeatherRecord(Base):
    """Hourly weather data from Open-Meteo."""
    __tablename__ = "weather_hourly"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    temperature_2m = Column(Float)
    relative_humidity_2m = Column(Float)
    dew_point_2m = Column(Float)
    precipitation_mm = Column(Float)
    cloud_cover_pct = Column(Float)
    wind_speed_10m = Column(Float)
    shortwave_radiation = Column(Float)
    source = Column(String(20), default="open_meteo")
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("timestamp", name="uq_weather_timestamp"),
    )


class AQIRecord(Base):
    """Daily AQI data for Delhi."""
    __tablename__ = "aqi_daily"

    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(Date, nullable=False, unique=True, index=True)
    aqi_value = Column(Float)
    pm25 = Column(Float)
    pm10 = Column(Float)
    category = Column(String(50))
    source = Column(String(20), default="cpcb")
    created_at = Column(DateTime, default=datetime.utcnow)


class HolidayRecord(Base):
    """Indian holidays and special events."""
    __tablename__ = "holidays"

    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(Date, nullable=False, index=True)
    name = Column(String(100), nullable=False)
    type = Column(String(30))       # national / regional / restricted / event
    category = Column(String(30))   # festival / government / sporting / political
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("date", "name", name="uq_holiday_date_name"),
    )


class PSPDailyReport(Base):
    """Grid India PSP daily summary."""
    __tablename__ = "psp_daily"

    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(Date, nullable=False, unique=True, index=True)
    delhi_demand_met_mw = Column(Float)
    delhi_energy_met_mu = Column(Float)
    northern_region_demand_mw = Column(Float)
    source = Column(String(20), default="grid_india")
    created_at = Column(DateTime, default=datetime.utcnow)


class ModelMetric(Base):
    """Tracks model performance over time for drift detection."""
    __tablename__ = "model_metrics"

    id = Column(Integer, primary_key=True, autoincrement=True)
    model_name = Column(String(50), nullable=False)
    model_version = Column(String(20))
    resolution = Column(String(10))     # 5min / hourly / daily
    metric_name = Column(String(20))    # mape / rmse / mae / r2
    metric_value = Column(Float)
    evaluation_date = Column(Date, nullable=False)
    fold_number = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow)


class PredictionLog(Base):
    """Daily log: what the model predicted vs what actually happened.

    Every day, the scheduler:
    1. Looks at yesterday's prediction (stored here the day before)
    2. Fetches yesterday's actual demand from SLDC
    3. Computes error metrics and updates this row
    """
    __tablename__ = "prediction_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    target_date = Column(Date, nullable=False, index=True)
    model_name = Column(String(50), nullable=False)
    resolution = Column(String(10), default="hourly")

    # What the model predicted (stored when prediction is made)
    predicted_peak_mw = Column(Float)
    predicted_avg_mw = Column(Float)
    predicted_min_mw = Column(Float)
    predicted_total_mwh = Column(Float)     # sum of hourly predictions

    # What actually happened (filled in the next day)
    actual_peak_mw = Column(Float)
    actual_avg_mw = Column(Float)
    actual_min_mw = Column(Float)
    actual_total_mwh = Column(Float)

    # Error metrics (computed once actuals are available)
    peak_error_mw = Column(Float)           # predicted_peak - actual_peak
    avg_error_mw = Column(Float)
    mape_pct = Column(Float)                # mean absolute percentage error
    mae_mw = Column(Float)                  # mean absolute error

    # Context
    peak_hour_predicted = Column(Integer)    # hour of predicted peak (0-23)
    peak_hour_actual = Column(Integer)       # hour of actual peak
    weather_temp_avg = Column(Float)         # average temperature that day
    is_holiday = Column(Boolean, default=False)
    notes = Column(String(200))             # auto-generated: "heatwave", "holiday miss", etc.

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("target_date", "model_name", name="uq_predlog_date_model"),
    )


class User(Base):
    """Application users with JWT authentication."""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(255), nullable=False, unique=True, index=True)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(100))
    role = Column(String(20), default="user")   # user / admin
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

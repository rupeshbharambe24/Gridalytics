"""Future forecasting engine.

For dates beyond available demand data, constructs synthetic feature rows using:
1. Last known demand values for lag features
2. Weather forecasts from Open-Meteo (up to 7 days) or climatological averages (beyond)
3. Calendar features (holidays, weekday, season)
4. Recursive prediction: predict day/hour N, use it as lag for day/hour N+1

Supports:
- Hourly: up to 7 days ahead with weather forecast, beyond with climatology
- Daily: up to 365 days ahead using recursive prediction + climatology
"""

import logging
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd
from sqlalchemy.orm import Session
from sqlalchemy import func

from src.data.db.models import DemandRecord, WeatherRecord, HolidayRecord
from src.data.scrapers.open_meteo import OpenMeteoScraper
from src.features.temporal import LAG_CONFIGS, add_cyclical_encoding, add_fourier_terms, add_time_features
from src.features.weather import add_heat_index, add_degree_days, add_weather_interactions, add_weather_categories, add_solar_features
from src.features.calendar import add_holiday_features

logger = logging.getLogger(__name__)


def _get_recent_demand(session: Session, n_rows: int = 8760) -> pd.DataFrame:
    """Get the most recent demand data for lag feature construction."""
    records = (
        session.query(DemandRecord)
        .order_by(DemandRecord.timestamp.desc())
        .limit(n_rows)
        .all()
    )
    if not records:
        return pd.DataFrame()

    df = pd.DataFrame([{
        "timestamp": r.timestamp,
        "delhi_mw": r.delhi_mw,
    } for r in reversed(records)])
    df = df.set_index("timestamp")
    return df


def _get_weather_forecast(session: Session, start: date, end: date) -> pd.DataFrame:
    """Get weather data: try Open-Meteo forecast API first, fall back to climatology."""
    # First check if we have recent weather data in DB
    weather_records = (
        session.query(WeatherRecord)
        .filter(WeatherRecord.timestamp >= datetime.combine(start, datetime.min.time()))
        .filter(WeatherRecord.timestamp <= datetime.combine(end, datetime.max.time()))
        .order_by(WeatherRecord.timestamp)
        .all()
    )

    if weather_records:
        df = pd.DataFrame([{
            "timestamp": r.timestamp,
            "temperature_2m": r.temperature_2m,
            "relative_humidity_2m": r.relative_humidity_2m,
            "dew_point_2m": r.dew_point_2m,
            "precipitation_mm": r.precipitation_mm,
            "cloud_cover_pct": r.cloud_cover_pct,
            "wind_speed_10m": r.wind_speed_10m,
            "shortwave_radiation": r.shortwave_radiation,
        } for r in weather_records])
        df = df.set_index("timestamp")
        if len(df) > 0:
            return df

    # Try Open-Meteo forecast API (free, up to 16 days ahead)
    days_ahead = (end - date.today()).days + 1
    if days_ahead <= 16:
        try:
            scraper = OpenMeteoScraper()
            forecast_df = scraper.scrape_forecast(days=min(days_ahead, 16))
            if not forecast_df.empty:
                forecast_df = forecast_df.set_index("timestamp")
                mask = (forecast_df.index.date >= start) & (forecast_df.index.date <= end)
                result = forecast_df[mask]
                if len(result) > 0:
                    logger.info(f"Got {len(result)} rows from Open-Meteo forecast API")
                    return result
        except Exception as e:
            logger.warning(f"Open-Meteo forecast failed: {e}")

    # Fall back to climatological averages (historical same-month averages)
    logger.info(f"Using climatological averages for {start} to {end}")
    return _build_climatology(session, start, end)


def _build_climatology(session: Session, start: date, end: date) -> pd.DataFrame:
    """Build hourly weather data from historical averages for the same month/hour."""
    rows = []
    current = datetime.combine(start, datetime.min.time())
    end_dt = datetime.combine(end, datetime.max.time())

    while current <= end_dt:
        # Query historical average for this month and hour
        month = current.month
        hour = current.hour

        avg = session.query(
            func.avg(WeatherRecord.temperature_2m),
            func.avg(WeatherRecord.relative_humidity_2m),
            func.avg(WeatherRecord.dew_point_2m),
            func.avg(WeatherRecord.precipitation_mm),
            func.avg(WeatherRecord.cloud_cover_pct),
            func.avg(WeatherRecord.wind_speed_10m),
            func.avg(WeatherRecord.shortwave_radiation),
        ).filter(
            func.strftime("%m", WeatherRecord.timestamp) == f"{month:02d}",
            func.strftime("%H", WeatherRecord.timestamp) == f"{hour:02d}",
        ).first()

        rows.append({
            "timestamp": current,
            "temperature_2m": avg[0] or 25.0,
            "relative_humidity_2m": avg[1] or 50.0,
            "dew_point_2m": avg[2] or 15.0,
            "precipitation_mm": avg[3] or 0.0,
            "cloud_cover_pct": avg[4] or 50.0,
            "wind_speed_10m": avg[5] or 10.0,
            "shortwave_radiation": avg[6] or 200.0,
        })
        current += timedelta(hours=1)

    df = pd.DataFrame(rows).set_index("timestamp")
    return df


def forecast_future(
    resolution: str,
    target_date: date,
    model,
    session: Session,
    overrides: dict | None = None,
) -> dict:
    """Generate forecast for a future date using recursive prediction.

    Returns dict with timestamps, predicted_mw, lower_bound_mw, upper_bound_mw.
    """
    logger.info(f"Future forecast: {resolution} for {target_date}")

    # 1. Get recent demand history for lag features
    demand_history = _get_recent_demand(session, n_rows=10000)
    if demand_history.empty:
        raise ValueError("No historical demand data available")

    last_timestamp = demand_history.index[-1]
    last_date = last_timestamp.date()
    logger.info(f"Last known demand: {last_timestamp}")

    # 2. Get weather data (forecast or climatology)
    weather = _get_weather_forecast(session, last_date, target_date)

    # 3. Build timestamps for the target date
    if resolution == "hourly":
        timestamps = pd.date_range(
            start=f"{target_date} 00:00",
            end=f"{target_date} 23:00",
            freq="h",
        )
    elif resolution == "daily":
        timestamps = pd.DatetimeIndex([datetime.combine(target_date, datetime.min.time())])
    else:  # 5min
        timestamps = pd.date_range(
            start=f"{target_date} 00:00",
            end=f"{target_date} 23:55",
            freq="5min",
        )

    # 4. Get model's expected feature names
    if hasattr(model, "feature_names") and model.feature_names:
        expected_features = model.feature_names
    else:
        raise ValueError("Model does not have feature_names attribute")

    # 5. Recursive prediction - for each timestamp, build features and predict
    all_predictions = []
    all_lower = []
    all_upper = []

    # Extend demand history with predictions as we go
    extended_demand = demand_history["delhi_mw"].copy()

    for ts in timestamps:
        row = _build_single_row(
            ts, extended_demand, weather, session,
            expected_features, resolution, overrides,
        )

        # Predict
        X = pd.DataFrame([row], columns=expected_features)
        X = X.fillna(0)

        try:
            point, lower, upper = model.predict_interval(X)
            pred = float(point[0])
            lo = float(lower[0])
            hi = float(upper[0])
        except Exception:
            pred = float(model.predict(X)[0])
            lo = pred * 0.92
            hi = pred * 1.08

        # Clamp to reasonable range
        pred = max(500, min(12000, pred))
        lo = max(500, min(12000, lo))
        hi = max(500, min(12000, hi))

        all_predictions.append(round(pred, 1))
        all_lower.append(round(lo, 1))
        all_upper.append(round(hi, 1))

        # Add prediction to history for next iteration's lag features
        extended_demand[ts] = pred

    return {
        "timestamps": [str(t) for t in timestamps],
        "predicted_mw": all_predictions,
        "lower_bound_mw": all_lower,
        "upper_bound_mw": all_upper,
    }


def _build_single_row(
    ts: pd.Timestamp,
    demand_history: pd.Series,
    weather: pd.DataFrame,
    session: Session,
    expected_features: list[str],
    resolution: str,
    overrides: dict | None = None,
) -> dict:
    """Build a single feature row for a future timestamp."""
    row = {}

    # --- Lag features ---
    lags = LAG_CONFIGS.get(resolution, LAG_CONFIGS["hourly"])
    for lag in lags:
        col_name = f"delhi_mw_lag_{lag}"
        if col_name in expected_features:
            if resolution == "hourly":
                lag_ts = ts - timedelta(hours=lag)
            elif resolution == "daily":
                lag_ts = ts - timedelta(days=lag)
            else:
                lag_ts = ts - timedelta(minutes=lag * 5)

            # Find closest value in history
            if lag_ts in demand_history.index:
                row[col_name] = demand_history[lag_ts]
            else:
                # Find nearest
                idx = demand_history.index.get_indexer([lag_ts], method="nearest")
                if idx[0] >= 0 and idx[0] < len(demand_history):
                    row[col_name] = demand_history.iloc[idx[0]]
                else:
                    row[col_name] = demand_history.iloc[-1]

    # --- Diff features ---
    for col in expected_features:
        if col.startswith("delhi_mw_diff_"):
            lag_n = int(col.split("_")[-1])
            lag_col = f"delhi_mw_lag_{lag_n}"
            current_est = demand_history.iloc[-1] if len(demand_history) > 0 else 3500
            lag_val = row.get(lag_col, current_est)
            row[col] = current_est - lag_val

    # --- Rolling stats ---
    for col in expected_features:
        if "rmean" in col or "rstd" in col or "rmin" in col or "rmax" in col or "rsum" in col:
            # Use recent demand history to compute rolling stats
            if "rmean" in col:
                row[col] = demand_history.iloc[-24:].mean() if len(demand_history) >= 24 else demand_history.mean()
            elif "rstd" in col:
                row[col] = demand_history.iloc[-24:].std() if len(demand_history) >= 24 else demand_history.std()
            elif "rmin" in col:
                row[col] = demand_history.iloc[-24:].min() if len(demand_history) >= 24 else demand_history.min()
            elif "rmax" in col:
                row[col] = demand_history.iloc[-24:].max() if len(demand_history) >= 24 else demand_history.max()
            elif "rsum" in col:
                row[col] = demand_history.iloc[-24:].sum() if len(demand_history) >= 24 else demand_history.sum()

    # --- Weather features ---
    weather_cols = ["temperature_2m", "relative_humidity_2m", "dew_point_2m",
                    "precipitation_mm", "cloud_cover_pct", "wind_speed_10m", "shortwave_radiation"]

    # Find closest weather row
    if not weather.empty:
        w_idx = weather.index.get_indexer([ts], method="nearest")
        if w_idx[0] >= 0 and w_idx[0] < len(weather):
            w_row = weather.iloc[w_idx[0]]
            for wc in weather_cols:
                if wc in expected_features and wc in w_row.index:
                    row[wc] = w_row[wc]

    # Apply overrides
    if overrides:
        if "temperature" in overrides:
            row["temperature_2m"] = overrides["temperature"]
        if "humidity" in overrides:
            row["relative_humidity_2m"] = overrides["humidity"]

    temp = row.get("temperature_2m", 25.0)
    humidity = row.get("relative_humidity_2m", 50.0)

    # Derived weather
    if "CDD" in expected_features:
        row["CDD"] = max(temp - 24, 0)
    if "HDD" in expected_features:
        row["HDD"] = max(18 - temp, 0)
    if "temp_squared" in expected_features:
        row["temp_squared"] = temp ** 2
    if "temp_x_humidity" in expected_features:
        row["temp_x_humidity"] = temp * humidity / 100.0
    if "heat_index" in expected_features:
        if temp > 20:
            HI = (-8.7847 + 1.6114 * temp + 2.3385 * humidity
                   - 0.1462 * temp * humidity - 0.0123 * temp**2
                   - 0.0164 * humidity**2 + 0.0022 * temp**2 * humidity
                   + 0.0007 * temp * humidity**2 - 0.0000036 * temp**2 * humidity**2)
            row["heat_index"] = HI
        else:
            row["heat_index"] = temp

    # --- Time features ---
    hour = ts.hour
    dow = ts.dayofweek
    month = ts.month
    doy = ts.dayofyear

    if "hour" in expected_features: row["hour"] = hour
    if "hour_sin" in expected_features: row["hour_sin"] = np.sin(2 * np.pi * hour / 24)
    if "hour_cos" in expected_features: row["hour_cos"] = np.cos(2 * np.pi * hour / 24)
    if "dayofweek" in expected_features: row["dayofweek"] = dow
    if "dow_sin" in expected_features: row["dow_sin"] = np.sin(2 * np.pi * dow / 7)
    if "dow_cos" in expected_features: row["dow_cos"] = np.cos(2 * np.pi * dow / 7)
    if "month" in expected_features: row["month"] = month
    if "month_sin" in expected_features: row["month_sin"] = np.sin(2 * np.pi * month / 12)
    if "month_cos" in expected_features: row["month_cos"] = np.cos(2 * np.pi * month / 12)
    if "doy_sin" in expected_features: row["doy_sin"] = np.sin(2 * np.pi * doy / 365.25)
    if "doy_cos" in expected_features: row["doy_cos"] = np.cos(2 * np.pi * doy / 365.25)
    if "is_weekend" in expected_features: row["is_weekend"] = 1 if dow >= 5 else 0
    if "is_peak_hour" in expected_features: row["is_peak_hour"] = 1 if 14 <= hour <= 17 else 0
    if "is_night" in expected_features: row["is_night"] = 1 if hour >= 22 or hour <= 5 else 0
    if "is_morning_ramp" in expected_features: row["is_morning_ramp"] = 1 if 6 <= hour <= 9 else 0
    if "quarter" in expected_features: row["quarter"] = (month - 1) // 3 + 1

    if "temp_x_hour" in expected_features:
        row["temp_x_hour"] = temp * hour
    if "temp_ramp_1h" in expected_features:
        row["temp_ramp_1h"] = 0
    if "temp_ramp_3h" in expected_features:
        row["temp_ramp_3h"] = 0

    # --- Season flags ---
    season_map = {
        (11, 12, 1, 2): "winter",
        (3, 4): "spring",
        (5, 6): "summer",
        (7, 8, 9): "monsoon",
        (10,): "autumn",
    }
    current_season = "unknown"
    for months, name in season_map.items():
        if month in months:
            current_season = name
            break

    for s in ["winter", "spring", "summer", "monsoon", "autumn"]:
        col = f"season_{s}"
        if col in expected_features:
            row[col] = 1 if s == current_season else 0

    # --- Precipitation/cloud flags ---
    precip = row.get("precipitation_mm", 0)
    cloud = row.get("cloud_cover_pct", 50)
    if "is_rainy" in expected_features: row["is_rainy"] = 1 if precip > 1 else 0
    if "is_heavy_rain" in expected_features: row["is_heavy_rain"] = 1 if precip > 10 else 0
    if "is_cloudy" in expected_features: row["is_cloudy"] = 1 if cloud > 50 else 0
    if "is_clear" in expected_features: row["is_clear"] = 1 if cloud < 20 else 0
    if "is_daylight" in expected_features:
        row["is_daylight"] = 1 if 6 <= hour <= 18 else 0
    if "solar_high" in expected_features:
        row["solar_high"] = 1 if row.get("shortwave_radiation", 0) > 500 else 0

    # --- Holiday features ---
    target_d = ts.date()
    holidays = session.query(HolidayRecord).filter(HolidayRecord.date == target_d).all()
    if "is_holiday" in expected_features:
        val = 1 if holidays else 0
        if overrides and "is_holiday" in overrides:
            val = int(overrides["is_holiday"])
        row["is_holiday"] = val
    if "is_national_holiday" in expected_features:
        row["is_national_holiday"] = 1 if any(h.type == "national" for h in holidays) else 0
    if "is_festival" in expected_features:
        row["is_festival"] = 1 if any(h.category == "festival" for h in holidays) else 0
    if "is_ipl_season" in expected_features:
        row["is_ipl_season"] = 1 if any(h.category == "sporting" for h in holidays) else 0
    if "days_to_next_holiday" in expected_features:
        row["days_to_next_holiday"] = 7  # default
    if "days_since_last_holiday" in expected_features:
        row["days_since_last_holiday"] = 7
    if "is_pre_holiday" in expected_features:
        row["is_pre_holiday"] = 0
    if "is_post_holiday" in expected_features:
        row["is_post_holiday"] = 0

    # --- AQI ---
    if "aqi_value" in expected_features:
        aqi = overrides.get("aqi", 100) if overrides else 100
        row["aqi_value"] = aqi
    if "aqi_severe" in expected_features: row["aqi_severe"] = 0
    if "aqi_poor" in expected_features: row["aqi_poor"] = 0

    # --- Fourier terms (approximate) ---
    for col in expected_features:
        if col.startswith("fourier_") and col not in row:
            row[col] = 0  # Fourier terms are position-dependent; approximate as 0

    # --- Rolling weather ---
    for col in expected_features:
        if col.startswith("temp_rmean") or col.startswith("humidity_rmean") or col.startswith("CDD_rsum"):
            if col not in row:
                if "temp" in col:
                    row[col] = temp
                elif "humidity" in col:
                    row[col] = humidity
                elif "CDD" in col:
                    row[col] = max(temp - 24, 0) * 24

    # Fill any remaining missing features with 0
    for f in expected_features:
        if f not in row:
            row[f] = 0

    return row

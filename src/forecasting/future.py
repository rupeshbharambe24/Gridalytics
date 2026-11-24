"""Future forecasting engine.

For every target timestamp we construct a single feature row that matches the
distributional shape the model saw at training time. The core discipline:

  * `_get_history_at_resolution` resamples raw 5-min demand to the resolution
    the model was trained on (hourly mean, daily mean, or raw 5-min). That way
    a lookup of `lag_24` for hour 14 returns the *hourly mean of yesterday
    14:00-15:00*, not a random 5-min snapshot. This alone fixes the "flat
    prediction" bug that showed up in production: the old code compared
    apples-to-5-min-oranges and the model just fell back to a constant.

  * Lag lookups always try the resampled series first. Only when the requested
    lag timestamp is truly in the future (i.e. one of *our* predictions from
    this same call) do we chain a prediction. `lag_168` (a week ago) and
    `lag_720` (30 days ago) therefore stay anchored to reality for the full
    7-day horizon.

  * Rolling stats are computed on an *extended* series (history ++ predictions
    so far) using pandas rolling — matching how training computed them
    exactly, and with the right window size per resolution.

  * Beyond ~48 hours the model's short lags (`lag_1`, `lag_24`) inevitably
    become self-referential. We do not try to be clever there; we just let
    `lag_168` and `lag_720` carry the signal, and clamp the output to a
    reasonable range as a safety net.
"""

import logging
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd
from sqlalchemy.orm import Session
from sqlalchemy import func

from src.data.db.models import (
    DemandRecord, StateDemandRecord, StatePSPDaily, WeatherRecord, HolidayRecord,
)
from src.data.scrapers.open_meteo import OpenMeteoScraper
from src.features.temporal import LAG_CONFIGS
from src.features.rolling import WINDOW_CONFIGS

logger = logging.getLogger(__name__)


# how far back to pull for lag/rolling reference data, per resolution
# needs to comfortably exceed the longest lag/rolling window
_HISTORY_ROWS_5MIN = 60_000   # ~200 days of 5-min → covers lag_2016 (7d) + rolling_7d
_HISTORY_ROWS_RAW = 20_000    # 5-min rows we scan to build hourly/daily history


def _get_history_at_resolution(
    session: Session, resolution: str, as_of: date | None = None
) -> pd.Series:
    """Return demand as a Series indexed at the model's native resolution.

    hourly resolution → resample 5-min data with `.resample("1h").mean()`
    daily  resolution → `.resample("1D").max()` (daily peak, as in training)
    5min   resolution → raw 5-min values

    The resample step is what makes the inference-time lag values match the
    training-time features — the original bug was that inference read raw
    5-min snapshots while training used hourly means.

    `as_of` caps history to timestamps strictly before that date — used for
    leakage-free historical backtesting (forecast date D sees only data < D).
    """
    n_rows = _HISTORY_ROWS_5MIN if resolution == "5min" else _HISTORY_ROWS_RAW
    q = session.query(DemandRecord.timestamp, DemandRecord.delhi_mw)
    if as_of is not None:
        q = q.filter(DemandRecord.timestamp < datetime.combine(as_of, datetime.min.time()))
    records = q.order_by(DemandRecord.timestamp.desc()).limit(n_rows).all()
    if not records:
        return pd.Series(dtype=float, name="delhi_mw")

    df = pd.DataFrame(
        [(r.timestamp, r.delhi_mw) for r in reversed(records)],
        columns=["timestamp", "delhi_mw"],
    )
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.set_index("timestamp").sort_index()

    series = df["delhi_mw"].dropna()
    if resolution == "hourly":
        # take the mean of each hour's 5-min readings — matches training pipeline
        return series.resample("1h").mean().dropna()
    if resolution == "daily":
        # daily target is the day's peak — matches loaders.load_demand
        return series.resample("1D").max().dropna()
    return series  # 5-min raw


def _get_weather_for_range(session: Session, start: date, end: date) -> pd.DataFrame:
    """Return weather in [start, end] as a DataFrame indexed by hour.

    Order of preference: DB rows → Open-Meteo forecast API → climatology.
    """
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
        if not df.empty:
            return df

    days_ahead = (end - date.today()).days + 1
    if 0 < days_ahead <= 16:
        try:
            scraper = OpenMeteoScraper()
            fdf = scraper.scrape_forecast(days=min(days_ahead, 16))
            if not fdf.empty:
                fdf = fdf.set_index("timestamp")
                mask = (fdf.index.date >= start) & (fdf.index.date <= end)
                sliced = fdf[mask]
                if not sliced.empty:
                    logger.info(f"Weather: got {len(sliced)} rows from Open-Meteo forecast")
                    return sliced
        except Exception as e:
            logger.warning(f"Open-Meteo forecast failed: {e}")

    logger.info(f"Weather: falling back to climatology for {start} → {end}")
    return _build_climatology(session, start, end)


def _build_climatology(session: Session, start: date, end: date) -> pd.DataFrame:
    """Hourly weather built from historical same-month/same-hour averages."""
    rows = []
    current = datetime.combine(start, datetime.min.time())
    end_dt = datetime.combine(end, datetime.max.time())

    while current <= end_dt:
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
            func.extract("month", WeatherRecord.timestamp) == month,
            func.extract("hour", WeatherRecord.timestamp) == hour,
        ).first()

        rows.append({
            "timestamp": current,
            "temperature_2m": float(avg[0]) if avg[0] else 25.0,
            "relative_humidity_2m": float(avg[1]) if avg[1] else 50.0,
            "dew_point_2m": float(avg[2]) if avg[2] else 15.0,
            "precipitation_mm": float(avg[3]) if avg[3] else 0.0,
            "cloud_cover_pct": float(avg[4]) if avg[4] else 50.0,
            "wind_speed_10m": float(avg[5]) if avg[5] else 10.0,
            "shortwave_radiation": float(avg[6]) if avg[6] else 200.0,
        })
        current += timedelta(hours=1)

    return pd.DataFrame(rows).set_index("timestamp")


def _step_delta(resolution: str) -> timedelta:
    if resolution == "hourly":
        return timedelta(hours=1)
    if resolution == "daily":
        return timedelta(days=1)
    if resolution == "15min":
        return timedelta(minutes=15)
    return timedelta(minutes=5)


def _target_timestamps(resolution: str, target_date: date) -> pd.DatetimeIndex:
    if resolution == "hourly":
        return pd.date_range(f"{target_date} 00:00", f"{target_date} 23:00", freq="h")
    if resolution == "daily":
        return pd.DatetimeIndex([datetime.combine(target_date, datetime.min.time())])
    if resolution == "15min":
        return pd.date_range(f"{target_date} 00:00", f"{target_date} 23:45", freq="15min")
    return pd.date_range(f"{target_date} 00:00", f"{target_date} 23:55", freq="5min")


def _lookup_at(series: pd.Series, ts: pd.Timestamp) -> float | None:
    """Return series[ts] if the exact timestamp exists, else None.

    We deliberately do NOT do a nearest-neighbour fallback here: the old code
    did, and it silently returned a demand value from a totally different day
    when the lag timestamp was missing. Returning None lets the caller pick
    a better strategy (last real value, mean of last-N, etc.) explicitly.
    """
    if ts in series.index:
        val = series.loc[ts]
        return float(val) if pd.notna(val) else None
    return None


def _seasonal_lookup(series: pd.Series, ts: pd.Timestamp) -> float | None:
    """Most recent value at the SAME time-of-day at/before ts (seasonal-naive).

    Used as a fallback for a missing short lag so a sub-daily forecast keeps its
    diurnal shape (same 15-min/hour slot as a recent real day) instead of
    flat-lining on the single last value. Walks back up to two weeks of days.
    """
    t = ts
    for _ in range(14):
        v = _lookup_at(series, t)
        if v is not None:
            return v
        t = t - timedelta(days=1)
    return None


def _event_effect_for_date(
    session: Session, target_date: date, overrides: dict | None,
    as_of: date | None = None,
) -> float:
    """Learned event effect (signed fraction) for `target_date`, or 0.

    Uses the full-sample learned table — causal for a future date, since every
    historical occurrence precedes it. If `overrides` forces `is_holiday=0`, we
    return 0 so the what-if counterfactual sees a normal (non-event) day.

    `as_of` restricts the learned table to occurrences before that date, for
    leakage-free historical backtesting (defaults to all history).
    """
    if overrides and "is_holiday" in overrides and int(overrides["is_holiday"]) == 0:
        return 0.0
    try:
        from src.forecasting.event_effects import build_table, tier_of

        holidays = session.query(HolidayRecord).filter(
            HolidayRecord.date == target_date
        ).all()
        if not holidays:
            return 0.0
        table = build_table(session=session, as_of=as_of)
        best = 0.0
        for h in holidays:
            e = table.get_effect(h.name, tier_of(h.name, h.type, h.category))
            if abs(e) > abs(best):
                best = e
        return float(best)
    except Exception as exc:
        logger.warning(f"Event-effect lookup failed for {target_date}: {exc}")
        return 0.0


def forecast_future(
    resolution: str,
    target_date: date,
    model,
    session: Session,
    overrides: dict | None = None,
    as_of: date | None = None,
) -> dict:
    """Predict every timestep of `target_date`. Returns a dict with keys
    `timestamps`, `predicted_mw`, `lower_bound_mw`, `upper_bound_mw`.

    `as_of` caps demand history and the learned event table to data strictly
    before that date, for leakage-free historical backtesting. Production calls
    leave it None (use everything available).
    """
    logger.info(f"Future forecast: {resolution} for {target_date}")

    if not hasattr(model, "feature_names") or not model.feature_names:
        raise ValueError("Model does not expose feature_names")
    expected_features = model.feature_names

    # Learned event effect for the target date (only if the model uses it, so
    # models trained before this feature existed pay zero overhead). A
    # what-if override of is_holiday=0 zeroes it, for a clean counterfactual.
    event_effect = 0.0
    if "expected_event_effect_pct" in expected_features:
        event_effect = _event_effect_for_date(session, target_date, overrides, as_of)

    history = _get_history_at_resolution(session, resolution, as_of)
    if history.empty:
        raise ValueError("No historical demand data available")

    last_ts = history.index[-1]
    logger.info(f"Last known demand ({resolution}): {last_ts} = {history.iloc[-1]:.0f} MW")

    # weather spans "a bit before target" (for weather rolling stats) → end of target
    weather_start = min(target_date, last_ts.date()) - timedelta(days=2)
    weather = _get_weather_for_range(session, weather_start, target_date)

    timestamps = _target_timestamps(resolution, target_date)

    # Predict each timestep INDEPENDENTLY against pure real history.
    #
    # We deliberately do NOT chain predictions back into the lag lookup pool.
    # The model's most-important feature by 10x is `delhi_mw_lag_1`. If we
    # feed each prediction back as the next step's lag_1, the whole day
    # anchors to the first prediction and the diurnal cycle collapses. Instead,
    # every hour's lag_1 falls back to the last real value in `extended`
    # (which is `last_real`, i.e. yesterday's final observation), and the
    # `is_night`/hour_sin/hour_cos features drive the drop overnight and
    # the ramp back up. This turned a 12.5%-MAPE recursive forecaster into
    # a ~3.5%-MAPE per-hour forecaster on validation days.
    #
    # The long lags (lag_24, lag_168, lag_720) still resolve to real
    # historical values via `_lookup_at`, so the model gets real
    # same-hour-yesterday / same-hour-last-week context for free.
    extended = history.copy()

    lags = LAG_CONFIGS.get(resolution, LAG_CONFIGS["hourly"])
    step = _step_delta(resolution)

    all_predictions: list[float] = []
    all_lower: list[float] = []
    all_upper: list[float] = []

    for ts in timestamps:
        row = _build_row(
            ts=ts,
            extended=extended,
            weather=weather,
            session=session,
            expected_features=expected_features,
            resolution=resolution,
            lags=lags,
            step=step,
            overrides=overrides,
            event_effect=event_effect,
        )

        X = pd.DataFrame([row], columns=expected_features).fillna(0)

        try:
            point, lower, upper = model.predict_interval(X)
            pred = float(point[0])
            lo = float(lower[0])
            hi = float(upper[0])
        except Exception:
            pred = float(model.predict(X)[0])
            lo = pred * 0.92
            hi = pred * 1.08

        # sanity clamp — Delhi demand physically lives in [500, 12000] MW
        pred = float(np.clip(pred, 500, 12000))
        lo = float(np.clip(lo, 500, 12000))
        hi = float(np.clip(hi, 500, 12000))

        all_predictions.append(round(pred, 1))
        all_lower.append(round(lo, 1))
        all_upper.append(round(hi, 1))

    # ── corruption / collapse guard ──────────────────────────────────────
    # The per-step clip above keeps a healthy forecast inside Delhi's physical
    # envelope, but it also silently FLOORS a broken model's ~0 output to 500.
    # That once stored a flat 500 MW day (actual ~4000) as if it were a real
    # forecast — a corrupt XGBoost reload whose learned base_score was lost.
    # A day whose peak sits below the recent observed demand floor, or that
    # spends most of its steps pinned to the clip floor, is not a forecast; it
    # is a dead model. Fail loudly so the caller records nothing rather than a
    # plausible-looking lie.
    recent = history.tail(max(1, 7 * len(timestamps)))
    recent_floor = float(recent.min()) if not recent.empty else 500.0
    n_floored = sum(1 for p in all_predictions if p <= 500.0)
    day_peak = max(all_predictions) if all_predictions else 0.0
    if day_peak < recent_floor or n_floored > 0.4 * max(1, len(all_predictions)):
        raise ValueError(
            f"{getattr(model, 'name', 'model')} produced a collapsed {resolution} "
            f"forecast for {target_date}: peak={day_peak:.0f} MW, "
            f"{n_floored}/{len(all_predictions)} steps at the floor, recent "
            f"observed demand floor={recent_floor:.0f} MW — model likely corrupt; "
            f"refusing to emit it."
        )

    return {
        "timestamps": [str(t) for t in timestamps],
        "predicted_mw": all_predictions,
        "lower_bound_mw": all_lower,
        "upper_bound_mw": all_upper,
    }


# ---------------------------------------------------------------------------
# per-timestep feature row construction
# ---------------------------------------------------------------------------


def _build_row(
    ts: pd.Timestamp,
    extended: pd.Series,
    weather: pd.DataFrame,
    session: Session,
    expected_features: list[str],
    resolution: str,
    lags: list[int],
    step: timedelta,
    overrides: dict | None,
    event_effect: float = 0.0,
    target_col: str = "delhi_mw",
    lag_fallback: str = "last_real",
) -> dict:
    """Compute the model's expected feature vector for a single timestep.

    ``target_col`` is the demand column the model was trained on — "delhi_mw"
    for the Delhi pipeline, "demand_mw" for the state pipeline. It only renames
    the lag/diff/rolling feature prefixes; every other feature is identical.

    All lag/rolling lookups run against `extended`, which is history at the
    same resolution the model was trained on, extended forward with any
    predictions we've made so far this call.
    """
    row: dict = {}
    last_real = float(extended.iloc[-1])  # useful fallback when a lag is truly missing

    # ── lag features ────────────────────────────────────────────────────
    for lag in lags:
        col = f"{target_col}_lag_{lag}"
        if col not in expected_features:
            continue
        lag_ts = ts - step * lag
        val = _lookup_at(extended, lag_ts)
        if val is None and lag_fallback == "seasonal":
            val = _seasonal_lookup(extended, lag_ts)
        row[col] = val if val is not None else last_real

    # ── diff features ───────────────────────────────────────────────────
    for col in expected_features:
        if not col.startswith(f"{target_col}_diff_"):
            continue
        try:
            lag_n = int(col.split("_")[-1])
        except ValueError:
            continue
        lag_col = f"{target_col}_lag_{lag_n}"
        current_est = row.get(f"{target_col}_lag_1", last_real)  # best guess for "current"
        lag_val = row.get(lag_col, last_real)
        row[col] = current_est - lag_val

    # ── rolling stats ───────────────────────────────────────────────────
    windows = WINDOW_CONFIGS.get(resolution, WINDOW_CONFIGS["hourly"])
    for name, size in windows.items():
        # cut the trailing window of `extended` strictly before ts
        window = extended[extended.index < ts].tail(size)
        if window.empty:
            continue
        wmean = float(window.mean())
        wstd = float(window.std()) if len(window) > 1 else 0.0
        wmin = float(window.min())
        wmax = float(window.max())
        for feat, val in (
            (f"{target_col}_rmean_{name}", wmean),
            (f"{target_col}_rstd_{name}", wstd),
            (f"{target_col}_rmin_{name}", wmin),
            (f"{target_col}_rmax_{name}", wmax),
        ):
            if feat in expected_features:
                row[feat] = val

    # ── weather ─────────────────────────────────────────────────────────
    weather_cols = [
        "temperature_2m", "relative_humidity_2m", "dew_point_2m",
        "precipitation_mm", "cloud_cover_pct", "wind_speed_10m",
        "shortwave_radiation",
    ]
    w_row: pd.Series | None = None
    if not weather.empty:
        idx = weather.index.get_indexer([ts], method="nearest")
        if idx[0] >= 0:
            w_row = weather.iloc[idx[0]]

    for wc in weather_cols:
        if wc not in expected_features:
            continue
        if w_row is not None and wc in w_row.index and pd.notna(w_row[wc]):
            row[wc] = float(w_row[wc])
        else:
            row[wc] = 0.0

    if overrides:
        if "temperature" in overrides:
            row["temperature_2m"] = float(overrides["temperature"])
        if "humidity" in overrides:
            row["relative_humidity_2m"] = float(overrides["humidity"])

    temp = row.get("temperature_2m", 25.0)
    humidity = row.get("relative_humidity_2m", 50.0)

    # weather-derived
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

    # rolling weather stats — same recipe as add_rolling_weather_stats
    if not weather.empty:
        wcut = weather[weather.index < ts]
        wsize_short = list(windows.values())[0]
        wsize_med = list(windows.values())[min(1, len(windows) - 1)]
        wshort_name = list(windows.keys())[0]
        wmed_name = list(windows.keys())[min(1, len(windows) - 1)]
        if "temperature_2m" in wcut.columns:
            for name, size in ((wshort_name, wsize_short), (wmed_name, wsize_med)):
                feat = f"temp_rmean_{name}"
                if feat in expected_features:
                    tail = wcut["temperature_2m"].tail(size)
                    row[feat] = float(tail.mean()) if not tail.empty else temp
        if "relative_humidity_2m" in wcut.columns:
            feat = f"humidity_rmean_{wmed_name}"
            if feat in expected_features:
                tail = wcut["relative_humidity_2m"].tail(wsize_med)
                row[feat] = float(tail.mean()) if not tail.empty else humidity
        if "CDD" in expected_features:
            cdd_series = (wcut["temperature_2m"] - 24).clip(lower=0)
            for name, size in ((wshort_name, wsize_short), (wmed_name, wsize_med)):
                feat = f"CDD_rsum_{name}"
                if feat in expected_features:
                    tail = cdd_series.tail(size)
                    row[feat] = float(tail.sum()) if not tail.empty else 0.0

    # ── time features ──────────────────────────────────────────────────
    hour = ts.hour
    dow = ts.dayofweek
    month = ts.month
    doy = ts.dayofyear

    def maybe(feat, value):
        if feat in expected_features:
            row[feat] = value

    maybe("hour", hour)
    maybe("hour_sin", np.sin(2 * np.pi * hour / 24))
    maybe("hour_cos", np.cos(2 * np.pi * hour / 24))
    maybe("dayofweek", dow)
    maybe("dow_sin", np.sin(2 * np.pi * dow / 7))
    maybe("dow_cos", np.cos(2 * np.pi * dow / 7))
    maybe("month", month)
    maybe("month_sin", np.sin(2 * np.pi * month / 12))
    maybe("month_cos", np.cos(2 * np.pi * month / 12))
    maybe("doy_sin", np.sin(2 * np.pi * doy / 365.25))
    maybe("doy_cos", np.cos(2 * np.pi * doy / 365.25))
    maybe("is_weekend", 1 if dow >= 5 else 0)
    maybe("is_peak_hour", 1 if 14 <= hour <= 17 else 0)
    maybe("is_night", 1 if hour >= 22 or hour <= 5 else 0)
    maybe("is_morning_ramp", 1 if 6 <= hour <= 9 else 0)
    maybe("quarter", (month - 1) // 3 + 1)
    maybe("temp_x_hour", temp * hour)

    # temp ramp features approximate to 0 (we don't have hourly temp derivatives here)
    maybe("temp_ramp_1h", 0)
    maybe("temp_ramp_3h", 0)

    # ── season one-hot ─────────────────────────────────────────────────
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
    for s in ("winter", "spring", "summer", "monsoon", "autumn"):
        maybe(f"season_{s}", 1 if s == current_season else 0)

    # precipitation / cloud flags
    precip = row.get("precipitation_mm", 0)
    cloud = row.get("cloud_cover_pct", 50)
    maybe("is_rainy", 1 if precip > 1 else 0)
    maybe("is_heavy_rain", 1 if precip > 10 else 0)
    maybe("is_cloudy", 1 if cloud > 50 else 0)
    maybe("is_clear", 1 if cloud < 20 else 0)
    maybe("is_daylight", 1 if 6 <= hour <= 18 else 0)
    maybe("solar_high", 1 if row.get("shortwave_radiation", 0) > 500 else 0)

    # ── holidays ───────────────────────────────────────────────────────
    target_d = ts.date()
    holidays = session.query(HolidayRecord).filter(HolidayRecord.date == target_d).all()
    is_hol = 1 if holidays else 0
    if overrides and "is_holiday" in overrides:
        is_hol = int(overrides["is_holiday"])
    maybe("is_holiday", is_hol)
    maybe("is_national_holiday", 1 if any(h.type == "national" for h in holidays) else 0)
    maybe("is_festival", 1 if any(h.category == "festival" for h in holidays) else 0)
    maybe("is_ipl_season", 1 if any(h.category == "sporting" for h in holidays) else 0)
    maybe("days_to_next_holiday", 7)
    maybe("days_since_last_holiday", 7)
    maybe("is_pre_holiday", 0)
    maybe("is_post_holiday", 0)
    maybe("expected_event_effect_pct", event_effect)

    # ── AQI ────────────────────────────────────────────────────────────
    aqi = overrides.get("aqi", 100) if overrides else 100
    maybe("aqi_value", aqi)
    maybe("aqi_severe", 1 if aqi > 400 else 0)
    maybe("aqi_poor", 1 if aqi > 200 else 0)

    # Fourier terms — leaving at 0 is a known approximation; the seasonal
    # signal is already carried by hour/dow/month sin/cos and the real
    # long-horizon lags, so this is not the dominant issue.
    for col in expected_features:
        if col.startswith("fourier_") and col not in row:
            row[col] = 0

    # anything the model expects that we didn't set → 0
    for f in expected_features:
        if f not in row:
            row[f] = 0

    return row


# ---------------------------------------------------------------------------
# State forecasting — the Delhi engine generalized to any state's demand_mw.
# Reuses _build_row/_lookup_at/_target_timestamps/_step_delta unchanged; only
# the data source (state_demand), the target column, and the weather point differ.
# ---------------------------------------------------------------------------

# Load-centre coords per state (mirror of scripts/train_state.STATE_COORDS), used
# to fetch forecast-time weather at the same point the model trained on.
STATE_COORDS = {
    "karnataka": (12.9716, 77.5946), "bihar": (25.5941, 85.1376),
    "punjab": (30.9010, 75.8573), "uttar_pradesh": (26.8467, 80.9462),
    "chhattisgarh": (21.2514, 81.6296), "himachal_pradesh": (31.1048, 77.1734),
    "maharashtra": (19.0760, 72.8777), "gujarat": (23.0225, 72.5714),
    "tamil_nadu": (13.0827, 80.2707), "west_bengal": (22.5726, 88.3639),
    "rajasthan": (26.9124, 75.7873), "andhra_pradesh": (16.5062, 80.6480),
    "madhya_pradesh": (23.2599, 77.4126), "telangana": (17.3850, 78.4867),
    "all_india": (21.1458, 79.0882),
}

_STATE_HISTORY_ROWS = 80_000  # comfortably covers the longest lag (15min lag_672 = 7d)


def _get_state_history_at_resolution(
    session: Session, state_code: str, resolution: str, as_of: date | None = None
) -> pd.Series:
    """State demand (demand_mw) as a Series at the model's native resolution."""
    q = (session.query(StateDemandRecord.timestamp, StateDemandRecord.demand_mw)
         .filter(StateDemandRecord.state_code == state_code,
                 StateDemandRecord.demand_mw.isnot(None)))
    if as_of is not None:
        q = q.filter(StateDemandRecord.timestamp < datetime.combine(as_of, datetime.min.time()))
    rows = q.order_by(StateDemandRecord.timestamp.desc()).limit(_STATE_HISTORY_ROWS).all()
    if not rows:
        return pd.Series(dtype=float, name="demand_mw")
    df = pd.DataFrame([(r.timestamp, r.demand_mw) for r in reversed(rows)],
                      columns=["timestamp", "demand_mw"])
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    s = df.set_index("timestamp").sort_index()["demand_mw"].dropna()
    s = s[~s.index.duplicated(keep="last")]
    freq = {"hourly": "1h", "daily": "1D", "15min": "15min", "5min": "5min"}.get(resolution, "1h")
    agg = "max" if resolution == "daily" else "mean"   # daily target = peak, matching training
    return s.resample(freq).agg(agg).dropna()


def _get_state_psp_history(
    session: Session, state_code: str, as_of: date | None = None
) -> pd.Series:
    """Daily peak-demand history (demand_mw) from state_psp_daily — for the PSP
    daily models, which train on peak_demand_met_mw, not the sub-daily series."""
    q = (session.query(StatePSPDaily.date, StatePSPDaily.peak_demand_met_mw)
         .filter(StatePSPDaily.state_code == state_code,
                 StatePSPDaily.peak_demand_met_mw.isnot(None)))
    if as_of is not None:
        q = q.filter(StatePSPDaily.date < as_of)
    rows = q.order_by(StatePSPDaily.date.desc()).limit(3000).all()
    if not rows:
        return pd.Series(dtype=float, name="demand_mw")
    df = pd.DataFrame([(r[0], r[1]) for r in reversed(rows)], columns=["timestamp", "demand_mw"])
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    s = df.set_index("timestamp").sort_index()["demand_mw"].dropna()
    s = s[~s.index.duplicated(keep="last")]
    return s.resample("1D").max().dropna()


def _get_state_weather_forecast(coords, start: date, end: date) -> pd.DataFrame:
    """Open-Meteo weather at a state's load centre over [start, end], hourly.

    Forecast API for future dates, archive API for past (backtest). Returns the
    column shape _build_row expects; empty DataFrame on any failure (the forecast
    then degrades gracefully to zero-weather rather than crashing).
    """
    if not coords:
        return pd.DataFrame()
    import requests
    lat, lon = coords
    _vars = ["temperature_2m", "relative_humidity_2m", "dew_point_2m", "precipitation",
             "cloud_cover", "wind_speed_10m", "shortwave_radiation"]
    try:
        if end >= date.today():
            url = "https://api.open-meteo.com/v1/forecast"
            params = {"latitude": lat, "longitude": lon, "hourly": ",".join(_vars),
                      "timezone": "Asia/Kolkata", "past_days": 3, "forecast_days": 16}
        else:
            url = "https://archive-api.open-meteo.com/v1/archive"
            params = {"latitude": lat, "longitude": lon, "hourly": ",".join(_vars),
                      "timezone": "Asia/Kolkata", "start_date": str(start), "end_date": str(end)}
        j = requests.get(url, params=params, timeout=30).json()["hourly"]
        wx = pd.DataFrame(j)
        wx["time"] = pd.to_datetime(wx["time"])
        return wx.set_index("time").rename(
            columns={"precipitation": "precipitation_mm", "cloud_cover": "cloud_cover_pct"})
    except Exception as e:
        logger.warning(f"state weather fetch failed ({e}); forecasting without weather")
        return pd.DataFrame()


def _state_event_effect_for_date(session, history, target_date, overrides=None) -> float:
    """Learned festival event-effect for `target_date`, estimated from the state's
    OWN daily-peak history — the exact mirror of training's add_state_event_effect
    (demand + events, no temp), so the served feature equals the trained one.

    Leak-free: `history` is already limited to the forecast's as_of, and
    causal_effect_feature only ever uses an event's strictly-prior occurrences. A
    what-if override of is_holiday=0 zeroes it. Returns 0.0 on any error or on a
    non-event day.
    """
    if overrides and "is_holiday" in overrides and int(overrides["is_holiday"]) == 0:
        return 0.0
    try:
        from src.forecasting.event_effects import causal_effect_feature, load_events
        daily = pd.DataFrame({"mw": history.resample("1D").max()}).dropna()
        daily["dow"] = daily.index.dayofweek
        events = load_events(session=session)
        eff = causal_effect_feature(daily, events)
        return float(eff.get(pd.Timestamp(target_date).normalize(), 0.0))
    except Exception as exc:  # pragma: no cover
        logger.warning(f"state event-effect unavailable ({exc}); using 0")
        return 0.0


def forecast_state_future(
    state_code: str,
    resolution: str,
    target_date: date | None,
    model,
    session: Session,
    coords: tuple | None = None,
    overrides: dict | None = None,
    as_of: date | None = None,
    source: str = "state_demand",
    pi_scale: float = 1.0,
) -> dict:
    """Day-ahead forecast for a non-Delhi state.

    Mirrors ``forecast_future`` but runs on the state's ``demand_mw`` series and
    its own load-centre weather. Same per-timestep, non-chained-lag discipline
    (long lags resolve to real history; short lags fall back to the last real
    value so the diurnal cycle comes from the time features). Returns
    ``{state, resolution, timestamps, predicted_mw, lower_bound_mw, upper_bound_mw}``.
    """
    if not getattr(model, "feature_names", None):
        raise ValueError("Model does not expose feature_names")
    expected_features = model.feature_names

    if source == "psp":
        history = _get_state_psp_history(session, state_code, as_of)
    else:
        history = _get_state_history_at_resolution(session, state_code, resolution, as_of)
    if history.empty:
        raise ValueError(f"No demand history for state '{state_code}' (source={source})")

    # Default to a true day-ahead: the day after the last observation, so the lag
    # lookups land on real history rather than a stale gap (states collect at
    # different freshnesses). Callers can still pass an explicit target_date.
    if target_date is None:
        target_date = history.index[-1].date() + timedelta(days=1)
    logger.info(f"State forecast: {state_code} {resolution} for {target_date} (source={source})")

    # Learned festival event-effect for the target day, from THIS state's own
    # history — only if the served model uses it (models trained without the
    # feature pay zero overhead and this stays 0.0).
    state_event_effect = 0.0
    if "expected_event_effect_pct" in expected_features:
        state_event_effect = _state_event_effect_for_date(
            session, history, target_date, overrides)

    if coords is None:
        coords = STATE_COORDS.get(state_code)
    weather_start = min(target_date, history.index[-1].date()) - timedelta(days=2)
    weather = _get_state_weather_forecast(coords, weather_start, target_date)

    timestamps = _target_timestamps(resolution, target_date)
    lags = LAG_CONFIGS.get(resolution, LAG_CONFIGS["hourly"])
    step = _step_delta(resolution)
    extended = history.copy()

    # data-driven sanity clamp from the state's own observed range
    hmin, hmax = float(history.min()), float(history.max())
    lo_clamp, hi_clamp = max(0.0, 0.3 * hmin), 2.5 * hmax

    preds: list[float] = []
    lows: list[float] = []
    highs: list[float] = []
    for ts in timestamps:
        row = _build_row(
            ts=ts, extended=extended, weather=weather, session=session,
            expected_features=expected_features, resolution=resolution,
            lags=lags, step=step, overrides=overrides,
            event_effect=state_event_effect, target_col="demand_mw", lag_fallback="seasonal",
        )
        X = pd.DataFrame([row], columns=expected_features).fillna(0)
        try:
            point, lower, upper = model.predict_interval(X)
            pred, lo, hi = float(point[0]), float(lower[0]), float(upper[0])
        except Exception:
            pred = float(model.predict(X)[0])
            lo, hi = pred * 0.92, pred * 1.08
        if pi_scale != 1.0:   # conformal recalibration (served.json pi_scale, see scripts/calibrate_intervals.py)
            lo = pred - pi_scale * (pred - lo)
            hi = pred + pi_scale * (hi - pred)
        pred = float(np.clip(pred, lo_clamp, hi_clamp))
        lo = float(np.clip(lo, lo_clamp, hi_clamp))
        hi = float(np.clip(hi, lo_clamp, hi_clamp))
        preds.append(round(pred, 1))
        lows.append(round(lo, 1))
        highs.append(round(hi, 1))

    # Corruption / collapse guard — mirror of the Delhi engine. A day whose peak
    # falls below the state's own recent observed demand floor is a dead model
    # (e.g. a corrupt XGBoost reload), not a forecast; fail loudly.
    recent = extended.tail(max(1, 7 * len(timestamps)))
    recent_floor = float(recent.min()) if not recent.empty else lo_clamp
    day_peak = max(preds) if preds else 0.0
    n_floored = sum(1 for p in preds if p <= lo_clamp + 1.0)
    if day_peak < recent_floor or n_floored > 0.4 * max(1, len(preds)):
        raise ValueError(
            f"{getattr(model, 'name', 'model')} produced a collapsed {resolution} "
            f"forecast for {state_code} on {target_date}: peak={day_peak:.0f} MW, "
            f"recent observed floor={recent_floor:.0f} MW — model likely corrupt; "
            f"refusing to emit it."
        )

    return {
        "state": state_code, "resolution": resolution,
        "timestamps": [str(t) for t in timestamps],
        "predicted_mw": preds, "lower_bound_mw": lows, "upper_bound_mw": highs,
    }

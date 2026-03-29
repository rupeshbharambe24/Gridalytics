"""Prediction tracker - records predictions and compares with actuals.

Daily workflow:
1. Evening: predict tomorrow's demand, store in prediction_log
2. Next day evening: fetch actual demand, compute errors, update the row
3. Dashboard shows rolling accuracy over time

Can also backfill: re-predict past dates and compare with known actuals.
"""

import logging
from datetime import date, datetime, timedelta

import numpy as np
from sqlalchemy.orm import Session
from sqlalchemy import func

from src.data.db.models import DemandRecord, PredictionLog, WeatherRecord, HolidayRecord
from src.api.model_registry import get_model
from src.forecasting.future import forecast_future

logger = logging.getLogger(__name__)


def _predict_for_date(target_date: date, model, session: Session, resolution: str) -> dict | None:
    """Generate prediction using historical pipeline (for past dates) or future engine."""
    from src.data.db.models import DemandRecord
    from sqlalchemy import func as sqlfunc

    last_data = session.query(sqlfunc.max(DemandRecord.timestamp)).scalar()
    last_data_date = last_data.date() if last_data else None

    if last_data_date and target_date <= last_data_date:
        # Past date - use historical feature pipeline
        from src.features.pipeline import FeaturePipeline
        lag_days = {"5min": 10, "hourly": 35, "daily": 750}
        start = target_date - timedelta(days=lag_days.get(resolution, 35))

        pipeline = FeaturePipeline(resolution, session)
        df = pipeline.build(start, target_date)

        if df.empty:
            return None

        mask = df.index.date == target_date
        target_df = df[mask]
        if target_df.empty:
            return None

        features = pipeline.get_feature_names(df)
        sub_regional = ["brpl_mw", "bypl_mw", "ndpl_mw", "ndmc_mw", "mes_mw"]
        features = [f for f in features if f not in sub_regional]
        X = target_df[features].fillna(0)

        try:
            point, lower, upper = model.predict_interval(X)
        except Exception:
            point = model.predict(X)
            lower = point * 0.92
            upper = point * 1.08

        return {
            "timestamps": [str(t) for t in target_df.index],
            "predicted_mw": [float(v) for v in point],
            "lower_bound_mw": [float(v) for v in lower],
            "upper_bound_mw": [float(v) for v in upper],
        }
    else:
        # Future date - use recursive forecast engine
        return forecast_future(resolution, target_date, model, session)


def record_prediction(target_date: date, session: Session, resolution: str = "hourly") -> PredictionLog | None:
    """Make a prediction for target_date and store it in the log."""
    model = get_model(resolution)
    if model is None:
        logger.error(f"No model available for {resolution}")
        return None

    # Check if already predicted
    existing = session.query(PredictionLog).filter(
        PredictionLog.target_date == target_date,
        PredictionLog.model_name == model.name,
    ).first()

    if existing and existing.predicted_peak_mw is not None:
        logger.info(f"Prediction already exists for {target_date}")
        return existing

    # Generate forecast
    try:
        result = _predict_for_date(target_date, model, session, resolution)
    except Exception as e:
        logger.error(f"Forecast failed for {target_date}: {e}")
        return None

    if result is None:
        return None

    preds = result["predicted_mw"]
    peak_idx = int(np.argmax(preds))

    # Check if target date is a holiday
    holidays = session.query(HolidayRecord).filter(HolidayRecord.date == target_date).all()

    # Get weather
    avg_temp = session.query(func.avg(WeatherRecord.temperature_2m)).filter(
        WeatherRecord.timestamp >= datetime.combine(target_date, datetime.min.time()),
        WeatherRecord.timestamp < datetime.combine(target_date + timedelta(days=1), datetime.min.time()),
    ).scalar()

    if existing:
        # Update existing row with prediction
        existing.predicted_peak_mw = max(preds)
        existing.predicted_avg_mw = sum(preds) / len(preds)
        existing.predicted_min_mw = min(preds)
        existing.predicted_total_mwh = sum(preds)
        existing.peak_hour_predicted = peak_idx
        existing.weather_temp_avg = avg_temp
        existing.is_holiday = len(holidays) > 0
        return existing

    log = PredictionLog(
        target_date=target_date,
        model_name=model.name,
        resolution=resolution,
        predicted_peak_mw=max(preds),
        predicted_avg_mw=sum(preds) / len(preds),
        predicted_min_mw=min(preds),
        predicted_total_mwh=sum(preds),
        peak_hour_predicted=peak_idx,
        weather_temp_avg=avg_temp,
        is_holiday=len(holidays) > 0,
    )
    session.add(log)
    session.flush()
    logger.info(f"Recorded prediction for {target_date}: peak={log.predicted_peak_mw:.0f} MW")
    return log


def fill_actuals(target_date: date, session: Session) -> PredictionLog | None:
    """Fill in actual demand values for a date where we have predictions."""
    log = session.query(PredictionLog).filter(
        PredictionLog.target_date == target_date,
    ).first()

    if not log:
        logger.info(f"No prediction log for {target_date}")
        return None

    if log.actual_peak_mw is not None:
        logger.info(f"Actuals already filled for {target_date}")
        return log

    # Query actual demand for that day
    start = datetime.combine(target_date, datetime.min.time())
    end = datetime.combine(target_date + timedelta(days=1), datetime.min.time())

    actuals = (
        session.query(DemandRecord.delhi_mw, DemandRecord.timestamp)
        .filter(DemandRecord.timestamp >= start, DemandRecord.timestamp < end)
        .order_by(DemandRecord.timestamp)
        .all()
    )

    if not actuals or len(actuals) < 10:
        logger.info(f"Not enough actual data for {target_date} ({len(actuals)} rows)")
        return None

    demand_values = [a.delhi_mw for a in actuals if a.delhi_mw]
    if not demand_values:
        return None

    # Compute hourly averages for MAPE calculation
    hourly = {}
    for a in actuals:
        h = a.timestamp.hour
        if h not in hourly:
            hourly[h] = []
        hourly[h].append(a.delhi_mw)
    hourly_avg = {h: np.mean(vals) for h, vals in hourly.items()}

    actual_peak = max(demand_values)
    actual_avg = np.mean(demand_values)
    actual_min = min(demand_values)
    peak_hour = max(hourly_avg, key=hourly_avg.get) if hourly_avg else None

    # Compute errors
    peak_error = log.predicted_peak_mw - actual_peak if log.predicted_peak_mw else None
    avg_error = log.predicted_avg_mw - actual_avg if log.predicted_avg_mw else None

    # MAPE: compare hourly predicted vs hourly actual
    mape_errors = []
    if log.predicted_avg_mw and actual_avg > 0:
        mape_errors.append(abs((log.predicted_avg_mw - actual_avg) / actual_avg))
    if log.predicted_peak_mw and actual_peak > 0:
        mape_errors.append(abs((log.predicted_peak_mw - actual_peak) / actual_peak))
    mape = np.mean(mape_errors) * 100 if mape_errors else None

    mae = abs(avg_error) if avg_error is not None else None

    # Auto-generate notes
    notes = []
    if mape and mape > 5:
        notes.append("high_error")
    if peak_error and abs(peak_error) > 300:
        notes.append(f"peak_off_by_{abs(peak_error):.0f}MW")
    if log.is_holiday:
        notes.append("holiday")
    if log.weather_temp_avg and log.weather_temp_avg > 40:
        notes.append("heatwave")
    if peak_hour and log.peak_hour_predicted and peak_hour != log.peak_hour_predicted:
        notes.append(f"peak_hour_shift_{log.peak_hour_predicted}h->{peak_hour}h")

    # Update the log
    log.actual_peak_mw = actual_peak
    log.actual_avg_mw = actual_avg
    log.actual_min_mw = actual_min
    log.actual_total_mwh = sum(demand_values) / (len(demand_values) / 24) if demand_values else None
    log.peak_hour_actual = peak_hour
    log.peak_error_mw = peak_error
    log.avg_error_mw = avg_error
    log.mape_pct = mape
    log.mae_mw = mae
    log.notes = ", ".join(notes) if notes else None

    session.flush()
    logger.info(f"Filled actuals for {target_date}: actual_peak={actual_peak:.0f} MW, MAPE={mape:.2f}%")
    return log


def backfill_prediction_log(session: Session, days_back: int = 30) -> int:
    """Backfill prediction log for the last N days.

    For each day: make a prediction (using future engine) and compare with actuals.
    This bootstraps the accuracy dashboard with historical data.
    """
    from src.api.model_registry import load_models
    load_models()

    count = 0
    today = date.today()

    for i in range(days_back, 0, -1):
        target = today - timedelta(days=i)
        logger.info(f"Backfilling {target} ({days_back - i + 1}/{days_back})")

        log = record_prediction(target, session, "hourly")
        if log:
            fill_actuals(target, session)
            count += 1

    return count


def daily_prediction_job(session: Session):
    """Daily job: predict tomorrow + fill yesterday's actuals.

    Called by the scheduler every day at ~23:00.
    """
    tomorrow = date.today() + timedelta(days=1)
    yesterday = date.today() - timedelta(days=1)

    logger.info(f"Daily prediction job: predict {tomorrow}, fill actuals for {yesterday}")

    # Record prediction for tomorrow
    record_prediction(tomorrow, session, "hourly")

    # Fill actuals for yesterday (data should be available by now)
    fill_actuals(yesterday, session)

    # Also try filling actuals for today (partial data)
    fill_actuals(date.today(), session)

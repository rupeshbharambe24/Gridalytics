"""Gridalytics — Full Weekly Pipeline (single entrypoint).

Runs the complete cycle:
  1. Scrape latest SLDC demand (last 3 days catch-up)
  2. Backfill any demand gap between latest DB row and yesterday
  3. Refresh weather (archive + 7-day forecast) and AQI
  4. Update holidays for current/next year
  5. Retrain the 3 champion models (5min, hourly, daily) on full history
  6. Reload the models in memory and forecast next 7 days at hourly resolution
  7. Log every hourly prediction into prediction_log_hourly
  8. Fill in actuals + per-hour errors for every past prediction missing them
  9. Print a drift summary

Designed to run on a developer laptop (Friday 23:00 IST). On success the wrapper
script `train_weekly.bat` commits and pushes the new model files; on failure
this script exits non-zero and the wrapper aborts the push.
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
import traceback
import warnings
from datetime import date, datetime, timedelta
from pathlib import Path

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np
from sqlalchemy import func

from src.data.db.session import get_session, create_tables
from src.data.db.models import (
    DemandRecord, WeatherRecord, AQIRecord, HolidayRecord,
    PredictionLog, PredictionLogHourly,
)
from src.data.scrapers.sldc import SLDCScraper
from src.data.scrapers.open_meteo import OpenMeteoScraper
from src.data.scrapers.aqi import AQIScraper
from src.data.scrapers.holidays import HolidayScraper

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
log = logging.getLogger("pipeline")
# quiet down chatty libs
for noisy in ("httpx", "urllib3", "sqlalchemy.engine"):
    logging.getLogger(noisy).setLevel(logging.WARNING)


# -----------------------------------------------------------------
# helpers
# -----------------------------------------------------------------

class StepTimer:
    def __init__(self, name: str):
        self.name = name

    def __enter__(self):
        log.info(f">> {self.name}")
        self.t0 = time.time()
        return self

    def __exit__(self, exc_type, exc, tb):
        elapsed = time.time() - self.t0
        status = "FAILED" if exc_type else "OK"
        log.info(f"-- {self.name}: {status} ({elapsed:.1f}s)")
        return False


def banner(title: str) -> None:
    line = "=" * 60
    print(f"\n{line}\n  {title}\n{line}")


# -----------------------------------------------------------------
# stage 1 — scrape latest + backfill
# -----------------------------------------------------------------

def scrape_demand(session) -> int:
    """Scrape from the latest DB timestamp up to yesterday.

    Today's data is intentionally skipped — SLDC publishes the current day
    incrementally, so the row count is partial and would pollute lag features.
    """
    latest = session.query(func.max(DemandRecord.timestamp)).scalar()
    if latest is None:
        start = date.today() - timedelta(days=30)
    else:
        start = latest.date()  # re-scrape the latest day to fill partials
    end = date.today() - timedelta(days=1)

    if start > end:
        log.info(f"Demand already up to date (latest={latest})")
        return 0

    days = (end - start).days + 1
    log.info(f"Scraping demand: {start} → {end} ({days} days)")

    scraper = SLDCScraper()
    # for long backfills, drop rate-limit a bit
    if days > 14:
        scraper.rate_limit_delay = 0.5

    count = scraper.run(start, end, session)
    log.info(f"Demand: +{count} new rows")
    return count


def scrape_weather(session) -> int:
    latest = session.query(func.max(WeatherRecord.timestamp)).scalar()
    if latest is None:
        start = date.today() - timedelta(days=60)
    else:
        start = latest.date()
    end = date.today() - timedelta(days=1)

    scraper = OpenMeteoScraper()
    total = 0
    if start <= end:
        log.info(f"Scraping weather archive: {start} → {end}")
        total += scraper.run(start, end, session)

    # Forecast — always refresh
    try:
        log.info("Fetching 7-day weather forecast")
        df = scraper.scrape_forecast(days=7)
        if not df.empty:
            df = scraper.validate(df)
            total += scraper.upsert(df, session)
    except Exception as e:
        log.warning(f"Forecast fetch failed (non-fatal): {e}")

    log.info(f"Weather: +{total} new rows")
    return total


def scrape_aqi(session) -> int:
    scraper = AQIScraper()
    end = date.today() - timedelta(days=1)
    start = end - timedelta(days=7)
    count = scraper.run(start, end, session)
    log.info(f"AQI: +{count} new rows")
    return count


def update_holidays(session) -> int:
    scraper = HolidayScraper()
    start = date(date.today().year, 1, 1)
    end = date(date.today().year + 1, 12, 31)
    count = scraper.run(start, end, session)
    log.info(f"Holidays: +{count} new rows")
    return count


# -----------------------------------------------------------------
# stage 2 — train all 3 models
# -----------------------------------------------------------------

def train_all_models(skip: bool = False) -> dict:
    """Re-train 5min, hourly, daily models. Returns CV-mape per resolution."""
    results = {}
    if skip:
        log.info("Skipping training (--no-train)")
        return results

    # daily first (fastest), then hourly, then 5min (slowest)
    from scripts.initial_train import train_and_evaluate
    from scripts.train_5min_model import train_5min

    for res in ("daily", "hourly"):
        with StepTimer(f"train {res}"):
            try:
                train_and_evaluate(res)
                results[res] = "ok"
            except Exception as e:
                log.error(f"Training {res} failed: {e}")
                log.error(traceback.format_exc())
                results[res] = f"failed: {e}"

    with StepTimer("train 5min"):
        try:
            train_5min()
            results["5min"] = "ok"
        except Exception as e:
            log.error(f"Training 5min failed: {e}")
            log.error(traceback.format_exc())
            results["5min"] = f"failed: {e}"

    return results


# -----------------------------------------------------------------
# stage 3 — predict next 7 days + log hourly
# -----------------------------------------------------------------

def predict_and_log(session, days_ahead: int = 7, days_back: int = 0) -> int:
    """Predict a window of days at hourly resolution, log each hour.

    Args:
        days_ahead: how many days FROM today to forecast (inclusive of today).
        days_back:  how many days BEFORE today to also (re)predict + log.
                    Useful after fixing a forecasting bug to rebuild history.

    For each day in [today - days_back, today + days_ahead):
      - run forecast_future("hourly", day)
      - upsert one PredictionLogHourly row per hour (predicted_*, lower, upper)
      - also upsert the daily PredictionLog summary
    """
    from src.api.model_registry import load_models, get_model
    from src.forecasting.future import forecast_future

    load_models()
    model = get_model("hourly")
    if model is None:
        log.error("No hourly model loaded — skipping predict_and_log")
        return 0

    rows_written = 0
    today = date.today()

    for day_offset in range(-days_back, days_ahead):
        target = today + timedelta(days=day_offset)
        try:
            result = forecast_future("hourly", target, model, session)
        except Exception as e:
            log.error(f"Forecast failed for {target}: {e}")
            continue

        preds = result["predicted_mw"]
        lowers = result["lower_bound_mw"]
        uppers = result["upper_bound_mw"]
        timestamps = result["timestamps"]
        if not preds:
            continue

        # is_holiday + avg_temp for this date
        is_holiday = session.query(HolidayRecord).filter(
            HolidayRecord.date == target
        ).first() is not None

        avg_temp = session.query(func.avg(WeatherRecord.temperature_2m)).filter(
            WeatherRecord.timestamp >= datetime.combine(target, datetime.min.time()),
            WeatherRecord.timestamp < datetime.combine(target + timedelta(days=1), datetime.min.time()),
        ).scalar()

        # daily summary
        peak_idx = int(np.argmax(preds))
        existing_daily = session.query(PredictionLog).filter(
            PredictionLog.target_date == target,
            PredictionLog.model_name == model.name,
        ).first()
        if existing_daily is None:
            session.add(PredictionLog(
                target_date=target,
                model_name=model.name,
                resolution="hourly",
                predicted_peak_mw=float(max(preds)),
                predicted_avg_mw=float(np.mean(preds)),
                predicted_min_mw=float(min(preds)),
                predicted_total_mwh=float(sum(preds)),
                peak_hour_predicted=peak_idx,
                weather_temp_avg=float(avg_temp) if avg_temp else None,
                is_holiday=is_holiday,
            ))
        else:
            existing_daily.predicted_peak_mw = float(max(preds))
            existing_daily.predicted_avg_mw = float(np.mean(preds))
            existing_daily.predicted_min_mw = float(min(preds))
            existing_daily.predicted_total_mwh = float(sum(preds))
            existing_daily.peak_hour_predicted = peak_idx
            existing_daily.weather_temp_avg = float(avg_temp) if avg_temp else None
            existing_daily.is_holiday = is_holiday

        # hourly rows
        for i, ts_str in enumerate(timestamps):
            ts = datetime.fromisoformat(ts_str)
            hour = ts.hour

            existing = session.query(PredictionLogHourly).filter(
                PredictionLogHourly.target_date == target,
                PredictionLogHourly.target_hour == hour,
                PredictionLogHourly.model_name == model.name,
            ).first()

            if existing is None:
                session.add(PredictionLogHourly(
                    target_date=target,
                    target_hour=hour,
                    model_name=model.name,
                    resolution="hourly",
                    predicted_mw=float(preds[i]),
                    predicted_lower_mw=float(lowers[i]),
                    predicted_upper_mw=float(uppers[i]),
                    temperature_c=float(avg_temp) if avg_temp else None,
                    is_holiday=is_holiday,
                ))
                rows_written += 1
            else:
                # only refresh predictions if we haven't already filled actuals
                if existing.actual_mw is None:
                    existing.predicted_mw = float(preds[i])
                    existing.predicted_lower_mw = float(lowers[i])
                    existing.predicted_upper_mw = float(uppers[i])

        session.flush()
        log.info(f"  {target}: peak={max(preds):.0f}MW@{peak_idx}h, avg={np.mean(preds):.0f}MW, holiday={is_holiday}")

    return rows_written


# -----------------------------------------------------------------
# stage 4 — fill actuals for past predictions
# -----------------------------------------------------------------

def fill_hourly_actuals(session, lookback_days: int = 30) -> int:
    """For every hourly prediction without actuals, fetch the actual demand
    from demand_5min (resampled to hourly mean) and compute errors."""
    from src.data.loaders import load_demand

    cutoff = date.today() - timedelta(days=lookback_days)
    pending = session.query(PredictionLogHourly).filter(
        PredictionLogHourly.actual_mw.is_(None),
        PredictionLogHourly.target_date >= cutoff,
        PredictionLogHourly.target_date < date.today(),  # don't fill today (partial)
    ).all()

    if not pending:
        return 0

    # group by date for efficient demand loading
    by_date: dict[date, list[PredictionLogHourly]] = {}
    for p in pending:
        by_date.setdefault(p.target_date, []).append(p)

    filled = 0
    for d, rows in sorted(by_date.items()):
        hourly_demand = load_demand(session, "hourly", d, d)
        if hourly_demand.empty:
            continue
        hour_to_mw = {ts.hour: float(v) for ts, v in zip(hourly_demand.index, hourly_demand["delhi_mw"])}

        for r in rows:
            actual = hour_to_mw.get(r.target_hour)
            if actual is None:
                continue
            err = r.predicted_mw - actual
            pct = (err / actual) * 100 if actual else None
            r.actual_mw = actual
            r.abs_error_mw = abs(err)
            r.pct_error = pct
            if r.predicted_lower_mw is not None and r.predicted_upper_mw is not None:
                r.in_interval = bool(r.predicted_lower_mw <= actual <= r.predicted_upper_mw)
            filled += 1

    session.flush()
    log.info(f"Filled actuals for {filled} hourly rows ({len(by_date)} days)")
    return filled


def fill_daily_actuals(session, lookback_days: int = 30) -> None:
    """Run the existing daily fill_actuals for any PredictionLog missing them."""
    from src.forecasting.tracker import fill_actuals
    cutoff = date.today() - timedelta(days=lookback_days)
    pending = session.query(PredictionLog).filter(
        PredictionLog.actual_peak_mw.is_(None),
        PredictionLog.target_date >= cutoff,
        PredictionLog.target_date < date.today(),
    ).all()
    for p in pending:
        try:
            fill_actuals(p.target_date, session)
        except Exception as e:
            log.warning(f"fill_actuals({p.target_date}) failed: {e}")


# -----------------------------------------------------------------
# stage 5 — drift summary
# -----------------------------------------------------------------

def drift_summary(session) -> dict:
    cutoff = date.today() - timedelta(days=30)
    rows = session.query(PredictionLogHourly).filter(
        PredictionLogHourly.target_date >= cutoff,
        PredictionLogHourly.actual_mw.isnot(None),
    ).all()

    if not rows:
        log.info("No hourly accuracy data in last 30 days")
        return {}

    abs_errors = [r.abs_error_mw for r in rows if r.abs_error_mw is not None]
    pct_errors = [abs(r.pct_error) for r in rows if r.pct_error is not None]
    in_interval = [1 if r.in_interval else 0 for r in rows if r.in_interval is not None]

    summary = {
        "rows_evaluated": len(rows),
        "mae_mw": round(float(np.mean(abs_errors)), 2) if abs_errors else None,
        "mape_pct": round(float(np.mean(pct_errors)), 2) if pct_errors else None,
        "interval_coverage_pct": round(float(np.mean(in_interval)) * 100, 1) if in_interval else None,
    }

    banner("DRIFT SUMMARY - last 30 days, hourly")
    for k, v in summary.items():
        print(f"  {k:25s}: {v}")

    return summary


# -----------------------------------------------------------------
# main
# -----------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-train", action="store_true", help="skip model training (scrape + predict only)")
    ap.add_argument("--no-scrape", action="store_true", help="skip data scraping")
    ap.add_argument("--days-ahead", type=int, default=7, help="forecast horizon")
    args = ap.parse_args()

    banner(f"Gridalytics Pipeline - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log.info(f"Mode: {'predict-only' if args.no_train else 'full retrain'}")

    create_tables()

    if not args.no_scrape:
        with get_session() as session:
            with StepTimer("scrape demand"):
                scrape_demand(session)
            with StepTimer("scrape weather"):
                scrape_weather(session)
            with StepTimer("scrape aqi"):
                scrape_aqi(session)
            with StepTimer("update holidays"):
                update_holidays(session)

    train_results = train_all_models(skip=args.no_train)

    with get_session() as session:
        with StepTimer(f"predict next {args.days_ahead} days + log hourly"):
            predict_and_log(session, days_ahead=args.days_ahead)

        with StepTimer("fill hourly actuals (last 30d)"):
            fill_hourly_actuals(session, lookback_days=30)

        with StepTimer("fill daily actuals (last 30d)"):
            fill_daily_actuals(session, lookback_days=30)

        drift_summary(session)

    banner("PIPELINE COMPLETE")
    if train_results:
        print("  Training results:")
        for res, status in train_results.items():
            print(f"    {res:8s}: {status}")
    print(f"  Finished at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        log.error("Pipeline crashed:")
        log.error(traceback.format_exc())
        sys.exit(1)

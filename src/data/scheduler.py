"""Automated data collection scheduler using APScheduler.

Runs scraping jobs on configurable intervals to keep the database
continuously up-to-date with the latest demand and weather data.

Usage:
    python -m src.data.scheduler          # Run scheduler (blocking)
    python -m src.data.scheduler --once   # Run all scrapers once and exit
"""

import sys
import logging
from datetime import date, timedelta

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from config import settings
from src.data.db.session import get_session, create_tables
from src.data.db.models import DemandRecord, WeatherRecord
from src.data.scrapers.sldc import SLDCScraper
from src.data.scrapers.open_meteo import OpenMeteoScraper
from src.data.scrapers.holidays import HolidayScraper
from sqlalchemy import func

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("scheduler")


def scrape_demand_latest():
    """Scrape the last 2 days of demand data from SLDC.

    We scrape 2 days to catch any data that was missing on the previous run
    (SLDC sometimes publishes data with a delay). The upsert logic
    handles duplicates automatically.
    """
    logger.info("Starting demand scrape job")
    scraper = SLDCScraper()
    end = date.today()
    start = end - timedelta(days=1)

    try:
        with get_session() as session:
            count = scraper.run(start, end, session)
            logger.info(f"Demand scrape complete: {count} new rows")
    except Exception as e:
        logger.error(f"Demand scrape failed: {e}")


def scrape_weather_latest():
    """Backfill weather data up to yesterday (archive API has ~1 day delay)."""
    logger.info("Starting weather scrape job")
    scraper = OpenMeteoScraper()

    # Find latest weather timestamp
    with get_session() as session:
        latest = session.query(func.max(WeatherRecord.timestamp)).scalar()

    if latest is None:
        start = date.today() - timedelta(days=30)
    else:
        start = latest.date()

    end = date.today() - timedelta(days=1)

    if start >= end:
        logger.info("Weather data is already up to date")
        return

    try:
        with get_session() as session:
            count = scraper.run(start, end, session)
            logger.info(f"Weather scrape complete: {count} new rows")
    except Exception as e:
        logger.error(f"Weather scrape failed: {e}")


def scrape_weather_forecast():
    """Fetch 7-day weather forecast for predictions."""
    logger.info("Starting weather forecast fetch")
    scraper = OpenMeteoScraper()

    try:
        df = scraper.scrape_forecast(days=7)
        if not df.empty:
            df = scraper.validate(df)
            with get_session() as session:
                count = scraper.upsert(df, session)
                logger.info(f"Weather forecast: {count} new rows")
    except Exception as e:
        logger.error(f"Weather forecast failed: {e}")


def update_holidays():
    """Update holidays for current and next year."""
    logger.info("Updating holiday calendar")
    scraper = HolidayScraper()
    try:
        with get_session() as session:
            count = scraper.run(
                date(date.today().year, 1, 1),
                date(date.today().year + 1, 12, 31),
                session,
            )
            logger.info(f"Holidays updated: {count} new entries")
    except Exception as e:
        logger.error(f"Holiday update failed: {e}")


def run_prediction_tracker():
    """Daily job: predict tomorrow, fill yesterday's actuals."""
    logger.info("Running prediction tracker")
    try:
        from src.api.model_registry import load_models
        from src.forecasting.tracker import daily_prediction_job
        load_models()
        with get_session() as session:
            daily_prediction_job(session)
            logger.info("Prediction tracker complete")
    except Exception as e:
        logger.error(f"Prediction tracker failed: {e}")


def print_status():
    """Print current data status."""
    with get_session() as session:
        d_max = session.query(func.max(DemandRecord.timestamp)).scalar()
        w_max = session.query(func.max(WeatherRecord.timestamp)).scalar()
        d_count = session.query(func.count(DemandRecord.id)).scalar()
        w_count = session.query(func.count(WeatherRecord.id)).scalar()

    logger.info(f"Status - Demand: {d_count:,} rows (latest: {d_max})")
    logger.info(f"Status - Weather: {w_count:,} rows (latest: {w_max})")


def run_all_once():
    """Run all scrapers once (for manual/CLI use)."""
    logger.info("Running all scrapers once...")
    create_tables()
    scrape_demand_latest()
    scrape_weather_latest()
    scrape_weather_forecast()
    update_holidays()
    run_prediction_tracker()
    print_status()
    logger.info("All scrapers complete")


def start_scheduler():
    """Start the continuous scheduler."""
    create_tables()
    scheduler = BlockingScheduler()

    # Demand: every 6 hours
    scheduler.add_job(
        scrape_demand_latest,
        IntervalTrigger(hours=settings.SCRAPE_INTERVAL_HOURS),
        id="demand_scrape",
        name="SLDC Demand Scrape",
        misfire_grace_time=3600,
    )

    # Weather archive: daily at 2 AM
    scheduler.add_job(
        scrape_weather_latest,
        CronTrigger(hour=2, minute=0),
        id="weather_archive",
        name="Weather Archive Backfill",
        misfire_grace_time=3600,
    )

    # Weather forecast: every 6 hours
    scheduler.add_job(
        scrape_weather_forecast,
        IntervalTrigger(hours=6),
        id="weather_forecast",
        name="Weather Forecast Fetch",
        misfire_grace_time=3600,
    )

    # Holidays: weekly on Sunday
    scheduler.add_job(
        update_holidays,
        CronTrigger(day_of_week="sun", hour=3),
        id="holidays",
        name="Holiday Calendar Update",
        misfire_grace_time=86400,
    )

    # Prediction tracker: daily at 23:00 (predict tomorrow, fill yesterday's actuals)
    scheduler.add_job(
        run_prediction_tracker,
        CronTrigger(hour=23, minute=0),
        id="prediction_tracker",
        name="Prediction Tracker (predict + evaluate)",
        misfire_grace_time=3600,
    )

    # Status log: every hour
    scheduler.add_job(
        print_status,
        IntervalTrigger(hours=1),
        id="status",
        name="Data Status Report",
    )

    logger.info("Scheduler started with jobs:")
    for job in scheduler.get_jobs():
        logger.info(f"  - {job.name}: next run at {job.next_run_time}")

    # Run scrapers immediately on startup
    scrape_demand_latest()
    scrape_weather_latest()
    scrape_weather_forecast()
    print_status()

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler stopped")


if __name__ == "__main__":
    if "--once" in sys.argv:
        run_all_once()
    else:
        start_scheduler()

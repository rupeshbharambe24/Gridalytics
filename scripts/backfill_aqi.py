"""Backfill 365 days of AQI data for Delhi using Open-Meteo Air Quality API.

Usage:
    python scripts/backfill_aqi.py

This script fetches the last 365 days of AQI data and inserts it into
the aqi_daily table. It is safe to run multiple times - existing records
will be updated rather than duplicated.
"""

import sys
import logging
from datetime import date, timedelta

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("aqi_backfill")

from src.data.db.session import get_session, create_tables
from src.data.db.models import AQIRecord
from src.data.scrapers.aqi import AQIScraper
from sqlalchemy import func


def main():
    # Create tables if they don't exist
    create_tables()

    scraper = AQIScraper()
    end_date = date.today() - timedelta(days=1)
    start_date = end_date - timedelta(days=364)  # 365 days total

    logger.info(f"Backfilling AQI data from {start_date} to {end_date} (365 days)")

    # The Open-Meteo API can handle large date ranges in one call
    with get_session() as session:
        count = scraper.run(start_date, end_date, session)
        total = session.query(func.count(AQIRecord.id)).scalar()
        latest = session.query(func.max(AQIRecord.date)).scalar()
        earliest = session.query(func.min(AQIRecord.date)).scalar()

    logger.info("Backfill complete!")
    logger.info(f"New rows inserted: {count}")
    logger.info(f"Total AQI rows in database: {total}")
    logger.info(f"Date range: {earliest} to {latest}")

    # Test summary
    print("\n=== AQI Backfill Test Results ===")
    print(f"Rows inserted this run: {count}")
    print(f"Total rows in aqi_daily table: {total}")
    print(f"Date range: {earliest} to {latest}")
    print(f"Expected ~365 days, got {total} rows")
    if total > 300:
        print("Backfill PASSED (>300 rows)")
    else:
        print("Backfill NEEDS INVESTIGATION (<300 rows)")


if __name__ == "__main__":
    main()

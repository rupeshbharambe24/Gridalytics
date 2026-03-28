"""Abstract base class for all data scrapers."""

from abc import ABC, abstractmethod
from datetime import date
import logging
import time

import pandas as pd
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class BaseScraper(ABC):
    """Base interface for all EDFS data scrapers."""

    def __init__(self, name: str, max_retries: int = 3, retry_delay: float = 2.0):
        self.name = name
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.logger = logging.getLogger(f"scraper.{name}")

    @abstractmethod
    def scrape(self, start_date: date, end_date: date) -> pd.DataFrame:
        """Fetch data for the given date range. Returns a clean DataFrame."""
        ...

    @abstractmethod
    def validate(self, df: pd.DataFrame) -> pd.DataFrame:
        """Run quality checks. Logs warnings, drops invalid rows."""
        ...

    @abstractmethod
    def upsert(self, df: pd.DataFrame, session: Session) -> int:
        """Insert or update records in the database. Returns count of rows inserted."""
        ...

    def run(self, start_date: date, end_date: date, session: Session) -> int:
        """Full pipeline: scrape -> validate -> upsert."""
        self.logger.info(f"Scraping {self.name} from {start_date} to {end_date}")

        df = self.scrape(start_date, end_date)
        if df is None or df.empty:
            self.logger.warning(f"No data returned for {start_date} to {end_date}")
            return 0

        self.logger.info(f"Scraped {len(df)} rows")
        df = self.validate(df)
        self.logger.info(f"{len(df)} rows after validation")

        count = self.upsert(df, session)
        self.logger.info(f"Upserted {count} rows into database")
        return count

    def _retry_request(self, func, *args, **kwargs):
        """Execute a function with retry logic and exponential backoff."""
        for attempt in range(1, self.max_retries + 1):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                if attempt == self.max_retries:
                    self.logger.error(f"Failed after {self.max_retries} attempts: {e}")
                    raise
                wait = self.retry_delay * (2 ** (attempt - 1))
                self.logger.warning(f"Attempt {attempt} failed: {e}. Retrying in {wait}s...")
                time.sleep(wait)

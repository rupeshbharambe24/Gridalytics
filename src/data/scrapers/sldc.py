"""Delhi SLDC 5-minute demand data scraper.

Source: https://www.delhisldc.org/Loaddata.aspx?mode=DD/MM/YYYY
Free, no authentication required.
Provides 5-minute interval demand for Delhi and sub-regions (BRPL, BYPL, NDPL, NDMC, MES).
"""

from datetime import date, datetime, timedelta
import time

import pandas as pd
import requests
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from config import settings
from src.data.db.models import DemandRecord
from .base import BaseScraper


class SLDCScraper(BaseScraper):
    """Scrapes 5-minute demand data from Delhi SLDC website."""

    def __init__(self):
        super().__init__(name="sldc", max_retries=3, retry_delay=2.0)
        self.base_url = settings.SLDC_BASE_URL
        self.rate_limit_delay = 1.0  # seconds between requests

    def scrape(self, start_date: date, end_date: date) -> pd.DataFrame:
        """Fetch 5-min demand data for each day in the date range."""
        all_data = []
        current = start_date

        while current <= end_date:
            date_str = current.strftime("%d/%m/%Y")
            self.logger.info(f"Fetching SLDC data for {date_str}")

            try:
                daily_data = self._fetch_day(date_str)
                if daily_data:
                    all_data.extend(daily_data)
            except Exception as e:
                self.logger.warning(f"Failed to fetch {date_str}: {e}")

            current += timedelta(days=1)
            time.sleep(self.rate_limit_delay)

        if not all_data:
            return pd.DataFrame()

        columns = ["date_str", "time_slot", "delhi", "brpl", "bypl", "ndpl", "ndmc", "mes"]
        df = pd.DataFrame(all_data, columns=columns)
        return self._parse_dataframe(df)

    def _fetch_day(self, date_str: str) -> list | None:
        """Fetch a single day of data from SLDC."""
        url = f"{self.base_url}?mode={date_str}"
        headers = {"User-Agent": "Mozilla/5.0 (EDFS Research Project)"}

        response = self._retry_request(requests.get, url, headers=headers, timeout=30)

        if response.status_code != 200:
            self.logger.warning(f"HTTP {response.status_code} for {date_str}")
            return None

        soup = BeautifulSoup(response.text, "html.parser")
        table = soup.find("table")

        if not table:
            self.logger.warning(f"No data table found for {date_str}")
            return None

        rows = table.find_all("tr")
        data = []

        for row in rows[1:]:  # skip header
            cols = row.find_all("td")
            if len(cols) >= 7:
                data.append(
                    [date_str] + [col.text.strip() for col in cols[:7]]
                )

        return data if data else None

    def _parse_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """Parse raw scraped data into typed DataFrame."""
        # Parse timestamp
        df["timestamp"] = pd.to_datetime(
            df["date_str"] + " " + df["time_slot"],
            dayfirst=True,
            errors="coerce",
        )
        df = df.dropna(subset=["timestamp"])

        # Parse numeric columns
        for col in ["delhi", "brpl", "bypl", "ndpl", "ndmc", "mes"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")

        # Rename to match DB schema
        df = df.rename(columns={
            "delhi": "delhi_mw",
            "brpl": "brpl_mw",
            "bypl": "bypl_mw",
            "ndpl": "ndpl_mw",
            "ndmc": "ndmc_mw",
            "mes": "mes_mw",
        })

        return df[["timestamp", "delhi_mw", "brpl_mw", "bypl_mw", "ndpl_mw", "ndmc_mw", "mes_mw"]]

    def validate(self, df: pd.DataFrame) -> pd.DataFrame:
        """Validate demand data quality."""
        initial_len = len(df)

        # Drop rows where Delhi demand is missing
        df = df.dropna(subset=["delhi_mw"])

        # Drop rows with unreasonable values (Delhi demand should be 500-10000 MW)
        df = df[(df["delhi_mw"] >= 500) & (df["delhi_mw"] <= 12000)]

        # Drop duplicate timestamps
        df = df.drop_duplicates(subset=["timestamp"], keep="last")

        dropped = initial_len - len(df)
        if dropped > 0:
            self.logger.warning(f"Dropped {dropped} invalid rows out of {initial_len}")

        return df.reset_index(drop=True)

    def upsert(self, df: pd.DataFrame, session: Session) -> int:
        """Insert demand records, skip duplicates."""
        count = 0
        for _, row in df.iterrows():
            # Check if record already exists
            exists = session.query(DemandRecord).filter(
                DemandRecord.timestamp == row["timestamp"]
            ).first()

            if not exists:
                record = DemandRecord(
                    timestamp=row["timestamp"],
                    delhi_mw=row["delhi_mw"],
                    brpl_mw=row.get("brpl_mw"),
                    bypl_mw=row.get("bypl_mw"),
                    ndpl_mw=row.get("ndpl_mw"),
                    ndmc_mw=row.get("ndmc_mw"),
                    mes_mw=row.get("mes_mw"),
                    source="sldc",
                )
                session.add(record)
                count += 1

        session.flush()
        return count

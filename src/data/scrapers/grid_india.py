"""Grid India PSP daily report scraper (stub).

Source: https://report.grid-india.in/psp_report.php
The full implementation would require Selenium to interact with
the date-picker and download the PDF/HTML report.

For now, this is a placeholder. Historical PSP data is available
from the legacy EDFS migration and can be loaded via the backfill
scripts. A full Selenium-based scraper can be added later when
automated daily PSP ingestion is needed.
"""

from datetime import date

import pandas as pd
from sqlalchemy.orm import Session

from src.data.db.models import PSPDailyReport
from .base import BaseScraper


class GridIndiaScraper(BaseScraper):
    """Placeholder scraper for Grid India PSP reports.

    The Grid India PSP report site requires Selenium to:
    1. Navigate to https://report.grid-india.in/psp_report.php
    2. Select the target date via a JavaScript date picker
    3. Click "View Report" and wait for the table to load
    4. Parse the HTML table for Delhi demand/energy figures

    This scraper is intentionally left as a stub. PSP data from
    the legacy EDFS system has already been migrated into the
    psp_daily table. When daily automated scraping is needed,
    implement the Selenium logic in the scrape() method below.

    Example future implementation:
        from selenium import webdriver
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
    """

    def __init__(self):
        super().__init__(name="grid_india", max_retries=2, retry_delay=5.0)

    def scrape(self, start_date: date, end_date: date) -> pd.DataFrame:
        """Fetch PSP report data for the given date range.

        Currently returns an empty DataFrame. Full Selenium
        implementation can be added later.
        """
        self.logger.info(
            "Grid India scraper not yet implemented "
            "(data available from legacy migration)"
        )
        return pd.DataFrame()

    def validate(self, df: pd.DataFrame) -> pd.DataFrame:
        """Validate PSP report data.

        Expected validations (for future implementation):
        - delhi_demand_met_mw: 2000-10000 MW range for Delhi
        - delhi_energy_met_mu: positive, reasonable range
        - northern_region_demand_mw: positive, > delhi demand
        - No duplicate dates
        """
        if df.empty:
            return df

        initial_len = len(df)
        df = df.dropna(subset=["date"])
        df = df.drop_duplicates(subset=["date"], keep="last")

        dropped = initial_len - len(df)
        if dropped > 0:
            self.logger.warning(f"Dropped {dropped} invalid PSP rows")

        return df.reset_index(drop=True)

    def upsert(self, df: pd.DataFrame, session: Session) -> int:
        """Insert PSP records, skip duplicates.

        Follows the same pattern as other scrapers.
        """
        if df.empty:
            return 0

        count = 0
        for _, row in df.iterrows():
            exists = session.query(PSPDailyReport).filter(
                PSPDailyReport.date == row["date"]
            ).first()

            if not exists:
                record = PSPDailyReport(
                    date=row["date"],
                    delhi_demand_met_mw=row.get("delhi_demand_met_mw"),
                    delhi_energy_met_mu=row.get("delhi_energy_met_mu"),
                    northern_region_demand_mw=row.get("northern_region_demand_mw"),
                    source="grid_india",
                )
                session.add(record)
                count += 1

        session.flush()
        return count

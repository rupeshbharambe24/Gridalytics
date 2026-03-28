"""Indian holiday and festival calendar generator.

Uses the `holidays` Python library for standard national holidays.
Supplements with a manually curated festivals CSV for Delhi-specific events
(Diwali, Holi, Eid, IPL season, elections, etc.).
"""

from datetime import date
from pathlib import Path

import holidays as holidays_lib
import pandas as pd
from sqlalchemy.orm import Session

from src.data.db.models import HolidayRecord
from .base import BaseScraper


# Major Indian festivals and events with approximate dates (update yearly)
# These are events that significantly affect Delhi electricity demand
FIXED_EVENTS = {
    # Format: (month, day, name, type, category)
    # Republic Day
    (1, 26): ("Republic Day", "national", "government"),
    # Independence Day
    (8, 15): ("Independence Day", "national", "government"),
    # Gandhi Jayanti
    (10, 2): ("Gandhi Jayanti", "national", "government"),
}

# Variable-date festivals (must be updated yearly or computed)
# These are approximate - real dates shift with lunar calendar
FESTIVALS_BY_YEAR = {
    2024: [
        (date(2024, 1, 15), "Makar Sankranti", "festival", "festival"),
        (date(2024, 1, 26), "Republic Day", "national", "government"),
        (date(2024, 3, 25), "Holi", "festival", "festival"),
        (date(2024, 3, 29), "Good Friday", "restricted", "festival"),
        (date(2024, 4, 11), "Eid ul-Fitr", "festival", "festival"),
        (date(2024, 4, 14), "Ambedkar Jayanti", "national", "government"),
        (date(2024, 4, 17), "Ram Navami", "festival", "festival"),
        (date(2024, 6, 17), "Eid ul-Adha", "festival", "festival"),
        (date(2024, 8, 15), "Independence Day", "national", "government"),
        (date(2024, 8, 26), "Janmashtami", "festival", "festival"),
        (date(2024, 10, 2), "Gandhi Jayanti", "national", "government"),
        (date(2024, 10, 12), "Dussehra", "festival", "festival"),
        (date(2024, 11, 1), "Diwali", "festival", "festival"),
        (date(2024, 11, 2), "Diwali (Day 2)", "festival", "festival"),
        (date(2024, 11, 15), "Guru Nanak Jayanti", "festival", "festival"),
        (date(2024, 12, 25), "Christmas", "restricted", "festival"),
    ],
    2025: [
        (date(2025, 1, 14), "Makar Sankranti", "festival", "festival"),
        (date(2025, 1, 26), "Republic Day", "national", "government"),
        (date(2025, 3, 14), "Holi", "festival", "festival"),
        (date(2025, 3, 31), "Eid ul-Fitr", "festival", "festival"),
        (date(2025, 4, 6), "Ram Navami", "festival", "festival"),
        (date(2025, 4, 14), "Ambedkar Jayanti", "national", "government"),
        (date(2025, 6, 7), "Eid ul-Adha", "festival", "festival"),
        (date(2025, 8, 15), "Independence Day/Janmashtami", "national", "government"),
        (date(2025, 10, 2), "Gandhi Jayanti/Dussehra", "national", "government"),
        (date(2025, 10, 20), "Diwali", "festival", "festival"),
        (date(2025, 10, 21), "Diwali (Day 2)", "festival", "festival"),
        (date(2025, 11, 5), "Guru Nanak Jayanti", "festival", "festival"),
        (date(2025, 12, 25), "Christmas", "restricted", "festival"),
    ],
    2026: [
        (date(2026, 1, 14), "Makar Sankranti", "festival", "festival"),
        (date(2026, 1, 26), "Republic Day", "national", "government"),
        (date(2026, 3, 3), "Holi", "festival", "festival"),
        (date(2026, 3, 20), "Eid ul-Fitr", "festival", "festival"),
        (date(2026, 3, 26), "Ram Navami", "festival", "festival"),
        (date(2026, 4, 14), "Ambedkar Jayanti", "national", "government"),
        (date(2026, 5, 27), "Eid ul-Adha", "festival", "festival"),
        (date(2026, 8, 15), "Independence Day", "national", "government"),
        (date(2026, 10, 2), "Gandhi Jayanti", "national", "government"),
        (date(2026, 10, 8), "Diwali", "festival", "festival"),
        (date(2026, 10, 9), "Diwali (Day 2)", "festival", "festival"),
        (date(2026, 12, 25), "Christmas", "restricted", "festival"),
    ],
}

# IPL season dates (approximate - March to May each year)
IPL_SEASONS = {
    2023: (date(2023, 3, 31), date(2023, 5, 28)),
    2024: (date(2024, 3, 22), date(2024, 5, 26)),
    2025: (date(2025, 3, 21), date(2025, 5, 25)),
    2026: (date(2026, 3, 20), date(2026, 5, 24)),
}


class HolidayScraper(BaseScraper):
    """Generates holiday and event data for the Indian calendar."""

    def __init__(self):
        super().__init__(name="holidays")

    def scrape(self, start_date: date, end_date: date) -> pd.DataFrame:
        """Generate holiday records for the date range."""
        records = []

        # Get standard Indian holidays from the holidays library
        for year in range(start_date.year, end_date.year + 1):
            india_holidays = holidays_lib.India(years=year)
            for dt, name in india_holidays.items():
                if start_date <= dt <= end_date:
                    records.append({
                        "date": dt,
                        "name": name,
                        "type": "national",
                        "category": "government",
                    })

        # Add curated festivals
        for year in range(start_date.year, end_date.year + 1):
            if year in FESTIVALS_BY_YEAR:
                for dt, name, type_, category in FESTIVALS_BY_YEAR[year]:
                    if start_date <= dt <= end_date:
                        records.append({
                            "date": dt,
                            "name": name,
                            "type": type_,
                            "category": category,
                        })

        # Add IPL season dates as events
        for year in range(start_date.year, end_date.year + 1):
            if year in IPL_SEASONS:
                ipl_start, ipl_end = IPL_SEASONS[year]
                current = max(ipl_start, start_date)
                end = min(ipl_end, end_date)
                while current <= end:
                    records.append({
                        "date": current,
                        "name": f"IPL Season {year}",
                        "type": "event",
                        "category": "sporting",
                    })
                    current += pd.Timedelta(days=1)

        if not records:
            return pd.DataFrame()

        df = pd.DataFrame(records)
        return df

    def validate(self, df: pd.DataFrame) -> pd.DataFrame:
        """Validate holiday data."""
        df = df.dropna(subset=["date", "name"])
        df = df.drop_duplicates(subset=["date", "name"], keep="last")
        return df.reset_index(drop=True)

    def upsert(self, df: pd.DataFrame, session: Session) -> int:
        """Insert holiday records, skip duplicates."""
        count = 0
        for _, row in df.iterrows():
            exists = session.query(HolidayRecord).filter(
                HolidayRecord.date == row["date"],
                HolidayRecord.name == row["name"],
            ).first()

            if not exists:
                record = HolidayRecord(
                    date=row["date"],
                    name=row["name"],
                    type=row.get("type", "national"),
                    category=row.get("category", "government"),
                )
                session.add(record)
                count += 1

        session.flush()
        return count

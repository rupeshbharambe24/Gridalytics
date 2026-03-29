"""Open-Meteo Air Quality API scraper for Delhi AQI data.

API: https://air-quality-api.open-meteo.com/v1/air-quality
FREE - no API key required.
Provides hourly air quality data for Delhi (28.7041, 77.1025).
We resample hourly data to daily (max AQI per day).
"""

from datetime import date, datetime

import httpx
import pandas as pd
from sqlalchemy.orm import Session

from config import settings
from src.data.db.models import AQIRecord
from .base import BaseScraper

# Open-Meteo Air Quality API endpoint
AQI_API_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"

# AQI category thresholds (US EPA standard)
AQI_CATEGORIES = [
    (0, 50, "Good"),
    (51, 100, "Moderate"),
    (101, 150, "Unhealthy for Sensitive Groups"),
    (151, 200, "Unhealthy"),
    (201, 300, "Very Unhealthy"),
    (301, 500, "Hazardous"),
]


def classify_aqi(value: float | None) -> str | None:
    """Classify an AQI value into its EPA category."""
    if value is None or pd.isna(value):
        return None
    value = int(round(value))
    for low, high, category in AQI_CATEGORIES:
        if low <= value <= high:
            return category
    if value > 500:
        return "Hazardous"
    return None


class AQIScraper(BaseScraper):
    """Scrapes hourly air quality data from Open-Meteo and resamples to daily."""

    def __init__(self):
        super().__init__(name="aqi", max_retries=3, retry_delay=2.0)

    def scrape(self, start_date: date, end_date: date) -> pd.DataFrame:
        """Fetch hourly AQI data and resample to daily max."""
        params = {
            "latitude": settings.DELHI_LAT,
            "longitude": settings.DELHI_LON,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "hourly": "pm2_5,pm10,european_aqi",
            "timezone": "Asia/Kolkata",
        }

        self.logger.info(f"Fetching AQI data from {start_date} to {end_date}")

        response = self._retry_request(
            httpx.get,
            AQI_API_URL,
            params=params,
            timeout=60.0,
        )

        if response.status_code != 200:
            self.logger.error(
                f"AQI API returned {response.status_code}: {response.text}"
            )
            return pd.DataFrame()

        data = response.json()
        if "hourly" not in data:
            self.logger.error("No 'hourly' key in AQI API response")
            return pd.DataFrame()

        # Build hourly DataFrame
        df = pd.DataFrame(data["hourly"])
        df["timestamp"] = pd.to_datetime(df["time"])
        df = df.drop(columns=["time"])
        df["date"] = df["timestamp"].dt.date

        # Resample to daily: take the max AQI and max PM values per day
        daily = df.groupby("date").agg(
            aqi_value=("european_aqi", "max"),
            pm25=("pm2_5", "max"),
            pm10=("pm10", "max"),
        ).reset_index()

        # Classify AQI category
        daily["category"] = daily["aqi_value"].apply(classify_aqi)

        self.logger.info(f"Resampled {len(df)} hourly rows to {len(daily)} daily rows")
        return daily

    def validate(self, df: pd.DataFrame) -> pd.DataFrame:
        """Validate AQI data quality."""
        initial_len = len(df)

        # Drop rows with no date
        df = df.dropna(subset=["date"])

        # AQI value: 0-500 range
        if "aqi_value" in df.columns:
            df = df[
                (df["aqi_value"] >= 0) & (df["aqi_value"] <= 500)
                | df["aqi_value"].isna()
            ]

        # PM2.5: 0-999 range
        if "pm25" in df.columns:
            df = df[
                (df["pm25"] >= 0) & (df["pm25"] <= 999)
                | df["pm25"].isna()
            ]

        # PM10: 0-999 range
        if "pm10" in df.columns:
            df = df[
                (df["pm10"] >= 0) & (df["pm10"] <= 999)
                | df["pm10"].isna()
            ]

        # Drop duplicate dates
        df = df.drop_duplicates(subset=["date"], keep="last")

        dropped = initial_len - len(df)
        if dropped > 0:
            self.logger.warning(f"Dropped {dropped} invalid AQI rows")

        return df.reset_index(drop=True)

    def upsert(self, df: pd.DataFrame, session: Session) -> int:
        """Insert AQI records, skip duplicates."""
        count = 0
        for _, row in df.iterrows():
            exists = session.query(AQIRecord).filter(
                AQIRecord.date == row["date"]
            ).first()

            if not exists:
                record = AQIRecord(
                    date=row["date"],
                    aqi_value=row.get("aqi_value"),
                    pm25=row.get("pm25"),
                    pm10=row.get("pm10"),
                    category=row.get("category"),
                    source="open_meteo_aqi",
                )
                session.add(record)
                count += 1
            else:
                # Update existing record if we have newer/better data
                exists.aqi_value = row.get("aqi_value") or exists.aqi_value
                exists.pm25 = row.get("pm25") or exists.pm25
                exists.pm10 = row.get("pm10") or exists.pm10
                exists.category = row.get("category") or exists.category

        session.flush()
        return count

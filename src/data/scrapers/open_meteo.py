"""Open-Meteo weather data scraper.

Archive: https://archive-api.open-meteo.com/v1/archive (historical)
Forecast: https://api.open-meteo.com/v1/forecast (7-day ahead)
FREE - no API key required.
Provides hourly weather data for Delhi (28.7041, 77.1025).
"""

from datetime import date, datetime

import httpx
import pandas as pd
from sqlalchemy.orm import Session

from config import settings
from src.data.db.models import WeatherRecord
from .base import BaseScraper


# Parameters to fetch from Open-Meteo
HOURLY_PARAMS = [
    "temperature_2m",
    "relative_humidity_2m",
    "dew_point_2m",
    "precipitation",
    "cloudcover",
    "windspeed_10m",
    "shortwave_radiation",
]


class OpenMeteoScraper(BaseScraper):
    """Scrapes hourly weather data from Open-Meteo API (free, no key)."""

    def __init__(self):
        super().__init__(name="open_meteo", max_retries=3, retry_delay=2.0)

    def scrape(self, start_date: date, end_date: date) -> pd.DataFrame:
        """Fetch historical hourly weather data."""
        params = {
            "latitude": settings.DELHI_LAT,
            "longitude": settings.DELHI_LON,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "hourly": ",".join(HOURLY_PARAMS),
            "timezone": "Asia/Kolkata",
        }

        self.logger.info(f"Fetching weather from {start_date} to {end_date}")

        response = self._retry_request(
            httpx.get,
            settings.OPEN_METEO_ARCHIVE_URL,
            params=params,
            timeout=60.0,
        )

        if response.status_code != 200:
            self.logger.error(f"Open-Meteo API returned {response.status_code}: {response.text}")
            return pd.DataFrame()

        data = response.json()
        if "hourly" not in data:
            self.logger.error("No 'hourly' key in API response")
            return pd.DataFrame()

        df = pd.DataFrame(data["hourly"])
        df["timestamp"] = pd.to_datetime(df["time"])
        df = df.drop(columns=["time"])

        # Rename columns to match DB schema
        df = df.rename(columns={
            "precipitation": "precipitation_mm",
            "cloudcover": "cloud_cover_pct",
        })

        return df

    def scrape_forecast(self, days: int = 7) -> pd.DataFrame:
        """Fetch weather forecast for the next N days."""
        params = {
            "latitude": settings.DELHI_LAT,
            "longitude": settings.DELHI_LON,
            "hourly": ",".join(HOURLY_PARAMS),
            "forecast_days": days,
            "timezone": "Asia/Kolkata",
        }

        self.logger.info(f"Fetching {days}-day weather forecast")

        response = self._retry_request(
            httpx.get,
            settings.OPEN_METEO_FORECAST_URL,
            params=params,
            timeout=60.0,
        )

        if response.status_code != 200:
            self.logger.error(f"Forecast API returned {response.status_code}")
            return pd.DataFrame()

        data = response.json()
        if "hourly" not in data:
            return pd.DataFrame()

        df = pd.DataFrame(data["hourly"])
        df["timestamp"] = pd.to_datetime(df["time"])
        df = df.drop(columns=["time"])
        df = df.rename(columns={
            "precipitation": "precipitation_mm",
            "cloudcover": "cloud_cover_pct",
        })

        return df

    def validate(self, df: pd.DataFrame) -> pd.DataFrame:
        """Validate weather data quality."""
        initial_len = len(df)

        # Drop rows with no timestamp
        df = df.dropna(subset=["timestamp"])

        # Temperature sanity check for Delhi (-5 to 55 C)
        if "temperature_2m" in df.columns:
            df = df[
                (df["temperature_2m"] >= -5) & (df["temperature_2m"] <= 55)
                | df["temperature_2m"].isna()
            ]

        # Humidity 0-100%
        if "relative_humidity_2m" in df.columns:
            df.loc[df["relative_humidity_2m"] > 100, "relative_humidity_2m"] = 100
            df.loc[df["relative_humidity_2m"] < 0, "relative_humidity_2m"] = 0

        # Drop duplicate timestamps
        df = df.drop_duplicates(subset=["timestamp"], keep="last")

        dropped = initial_len - len(df)
        if dropped > 0:
            self.logger.warning(f"Dropped {dropped} invalid weather rows")

        return df.reset_index(drop=True)

    def upsert(self, df: pd.DataFrame, session: Session) -> int:
        """Insert weather records, skip duplicates."""
        count = 0
        for _, row in df.iterrows():
            exists = session.query(WeatherRecord).filter(
                WeatherRecord.timestamp == row["timestamp"]
            ).first()

            if not exists:
                record = WeatherRecord(
                    timestamp=row["timestamp"],
                    temperature_2m=row.get("temperature_2m"),
                    relative_humidity_2m=row.get("relative_humidity_2m"),
                    dew_point_2m=row.get("dew_point_2m"),
                    precipitation_mm=row.get("precipitation_mm"),
                    cloud_cover_pct=row.get("cloud_cover_pct"),
                    wind_speed_10m=row.get("windspeed_10m"),
                    shortwave_radiation=row.get("shortwave_radiation"),
                    source="open_meteo",
                )
                session.add(record)
                count += 1

        session.flush()
        return count

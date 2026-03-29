"""Feature pipeline orchestrator.

Chains all feature engineering steps into a single pipeline that:
1. Loads demand data from DB at the correct resolution
2. Merges weather data (forward-fills hourly weather to 5-min)
3. Merges calendar/holiday features
4. Adds temporal features (lags, cyclical, Fourier)
5. Adds weather-derived features (CDD, heat index, interactions)
6. Adds rolling statistics
7. Drops NaN rows from lagging (beginning of series only)

The output DataFrame has ~60-80 feature columns ready for model training.
"""

import logging
from datetime import date

import pandas as pd
from sqlalchemy.orm import Session

from src.data.loaders import load_demand, load_weather
from src.features.temporal import (
    add_lag_features,
    add_diff_features,
    add_cyclical_encoding,
    add_fourier_terms,
    add_time_features,
)
from src.features.weather import (
    add_heat_index,
    add_degree_days,
    add_weather_interactions,
    add_weather_categories,
    add_solar_features,
)
from src.features.calendar import add_holiday_features, add_aqi_features
from src.features.rolling import add_rolling_stats, add_rolling_weather_stats

logger = logging.getLogger(__name__)

# Target column name
TARGET = "delhi_mw"


class FeaturePipeline:
    """Orchestrates all feature engineering transforms."""

    def __init__(self, resolution: str, session: Session):
        """
        Args:
            resolution: '5min', 'hourly', or 'daily'
            session: SQLAlchemy database session
        """
        if resolution not in ("5min", "hourly", "daily"):
            raise ValueError(f"Invalid resolution: {resolution}")
        self.resolution = resolution
        self.session = session

    def build(
        self,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> pd.DataFrame:
        """Build the complete feature DataFrame.

        Returns a DataFrame with datetime index, target column, and
        all engineered features. NaN rows from lagging are dropped.
        """
        logger.info(f"Building features: resolution={self.resolution}, "
                     f"start={start_date}, end={end_date}")

        # Step 1: Load demand
        df = load_demand(self.session, self.resolution, start_date, end_date)
        if df.empty:
            logger.warning("No demand data found for the given range")
            return df

        logger.info(f"Loaded {len(df)} demand rows ({df.index.min()} to {df.index.max()})")

        # Step 2: Merge weather
        df = self._merge_weather(df, start_date, end_date)

        # Step 3: Add time extraction features (needed by weather interactions)
        df = add_time_features(df)
        df = add_cyclical_encoding(df)

        # Step 4: Add weather-derived features
        df = add_heat_index(df)
        df = add_degree_days(df)
        df = add_weather_interactions(df)
        df = add_weather_categories(df)
        df = add_solar_features(df)

        # Step 5: Merge calendar features (holidays, AQI)
        df = add_holiday_features(df, self.session)
        df = add_aqi_features(df, self.session)

        # Step 6: Add rolling statistics (before lags, as some lags use rolling)
        df = add_rolling_stats(df, TARGET, self.resolution)
        df = add_rolling_weather_stats(df, self.resolution)

        # Step 7: Add lag features (AFTER rolling stats, as lags shift data)
        df = add_lag_features(df, TARGET, self.resolution)
        df = add_diff_features(df, TARGET, self.resolution)

        # Step 8: Add Fourier terms
        df = add_fourier_terms(df, self.resolution)

        # Step 9: Drop non-feature columns
        drop_cols = [
            "delhi_season",  # text version (we have one-hot encoded)
        ]
        df = df.drop(columns=[c for c in drop_cols if c in df.columns])

        # Step 10: Drop rows with NaN from lagging (beginning of series)
        initial_len = len(df)
        df = df.dropna(subset=[c for c in df.columns if "_lag_" in c])
        dropped = initial_len - len(df)
        if dropped > 0:
            logger.info(f"Dropped {dropped} rows with NaN from lagging")

        logger.info(f"Feature pipeline complete: {len(df)} rows, {len(df.columns)} columns")
        return df

    def _merge_weather(
        self,
        df: pd.DataFrame,
        start_date: date | None,
        end_date: date | None,
    ) -> pd.DataFrame:
        """Merge hourly weather data into the demand DataFrame.

        For 5-min resolution: forward-fill hourly weather values.
        For daily resolution: resample weather to daily means.
        """
        weather = load_weather(self.session, start_date, end_date)
        if weather.empty:
            logger.warning("No weather data found - features will be limited")
            return df

        weather_cols = [
            "temperature_2m", "relative_humidity_2m", "dew_point_2m",
            "precipitation_mm", "cloud_cover_pct", "wind_speed_10m",
            "shortwave_radiation",
        ]
        weather = weather[[c for c in weather_cols if c in weather.columns]]

        if self.resolution == "5min":
            # Reindex weather to 5-min and forward-fill
            weather = weather.reindex(df.index, method="ffill")
            df = df.join(weather, how="left")
        elif self.resolution == "daily":
            # Aggregate weather to daily
            weather_daily = weather.resample("1D").agg({
                "temperature_2m": "mean",
                "relative_humidity_2m": "mean",
                "dew_point_2m": "mean",
                "precipitation_mm": "sum",
                "cloud_cover_pct": "mean",
                "wind_speed_10m": "mean",
                "shortwave_radiation": "mean",
            })
            df = df.join(weather_daily, how="left")
        else:
            # Hourly - direct join
            df = df.join(weather, how="left")

        # Forward-fill any remaining weather NaNs
        for col in weather_cols:
            if col in df.columns:
                df[col] = df[col].ffill().bfill()

        logger.info(f"Merged weather data ({len(weather_cols)} columns)")
        return df

    def get_feature_names(self, df: pd.DataFrame) -> list[str]:
        """Get list of feature column names (everything except target and sub-regions)."""
        exclude = {TARGET, "brpl_mw", "bypl_mw", "ndpl_mw", "ndmc_mw", "mes_mw"}
        return [c for c in df.columns if c not in exclude]

    def get_target_name(self) -> str:
        """Get the target column name."""
        return TARGET

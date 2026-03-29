"""Temporal feature engineering: lags, cyclical encoding, Fourier terms."""

import numpy as np
import pandas as pd


# Lag definitions by resolution
LAG_CONFIGS = {
    "5min": [1, 6, 12, 288, 2016],        # 5m, 30m, 1h, 1d, 7d
    "hourly": [1, 6, 24, 168, 720],        # 1h, 6h, 1d, 7d, 30d
    "daily": [1, 7, 14, 30, 365],          # 1d, 7d, 14d, 30d, 1y
}

# Fourier periods by resolution
FOURIER_CONFIGS = {
    "5min": [288, 2016],       # daily (288 per day), weekly (2016 per week)
    "hourly": [24, 168],       # daily (24h), weekly (168h)
    "daily": [7, 30, 365],     # weekly, monthly, yearly
}


def add_lag_features(df: pd.DataFrame, target: str, resolution: str) -> pd.DataFrame:
    """Add lagged values of the target variable.

    These are typically the single most important features for time series
    forecasting. lag_1 = previous timestep, lag_24 = same hour yesterday, etc.
    """
    lags = LAG_CONFIGS.get(resolution, LAG_CONFIGS["hourly"])
    for lag in lags:
        df[f"{target}_lag_{lag}"] = df[target].shift(lag)
    return df


def add_diff_features(df: pd.DataFrame, target: str, resolution: str) -> pd.DataFrame:
    """Add demand rate-of-change features (difference from previous timestep)."""
    key_lags = {
        "5min": [1, 288],       # vs 5min ago, vs same time yesterday
        "hourly": [1, 24],      # vs 1h ago, vs same hour yesterday
        "daily": [1, 7],        # vs yesterday, vs same day last week
    }
    for lag in key_lags.get(resolution, [1]):
        df[f"{target}_diff_{lag}"] = df[target].diff(lag)
    return df


def add_cyclical_encoding(df: pd.DataFrame) -> pd.DataFrame:
    """Sin/cos encoding for hour-of-day, day-of-week, month-of-year, day-of-year.

    Cyclical encoding preserves the circular nature of time:
    hour 23 is close to hour 0, December is close to January.
    """
    idx = df.index

    # Hour of day (0-23)
    if hasattr(idx, "hour"):
        df["hour_sin"] = np.sin(2 * np.pi * idx.hour / 24)
        df["hour_cos"] = np.cos(2 * np.pi * idx.hour / 24)
        df["hour"] = idx.hour

    # Day of week (0=Monday, 6=Sunday)
    df["dow_sin"] = np.sin(2 * np.pi * idx.dayofweek / 7)
    df["dow_cos"] = np.cos(2 * np.pi * idx.dayofweek / 7)
    df["dayofweek"] = idx.dayofweek

    # Month (1-12)
    df["month_sin"] = np.sin(2 * np.pi * idx.month / 12)
    df["month_cos"] = np.cos(2 * np.pi * idx.month / 12)
    df["month"] = idx.month

    # Day of year (1-366)
    df["doy_sin"] = np.sin(2 * np.pi * idx.dayofyear / 365.25)
    df["doy_cos"] = np.cos(2 * np.pi * idx.dayofyear / 365.25)

    # Is weekend
    df["is_weekend"] = (idx.dayofweek >= 5).astype(int)

    return df


def add_fourier_terms(
    df: pd.DataFrame, resolution: str, n_terms: int = 3
) -> pd.DataFrame:
    """Add Fourier series terms for capturing complex seasonality.

    Fourier terms decompose seasonality into sine/cosine waves at
    different frequencies. This is especially useful for gradient
    boosting models which can't learn periodic patterns natively.
    """
    periods = FOURIER_CONFIGS.get(resolution, FOURIER_CONFIGS["hourly"])
    t = np.arange(len(df))

    for period in periods:
        for k in range(1, n_terms + 1):
            df[f"fourier_sin_{period}_{k}"] = np.sin(2 * np.pi * k * t / period)
            df[f"fourier_cos_{period}_{k}"] = np.cos(2 * np.pi * k * t / period)

    return df


def add_time_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add basic time extraction features (non-cyclical, for tree models)."""
    idx = df.index

    if hasattr(idx, "hour"):
        # Peak hour flags for Delhi (AC load peaks 14:00-17:00 in summer)
        df["is_peak_hour"] = ((idx.hour >= 14) & (idx.hour <= 17)).astype(int)
        df["is_night"] = ((idx.hour >= 22) | (idx.hour <= 5)).astype(int)
        df["is_morning_ramp"] = ((idx.hour >= 6) & (idx.hour <= 9)).astype(int)

    # Quarter
    df["quarter"] = idx.quarter

    return df

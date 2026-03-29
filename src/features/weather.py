"""Weather-derived feature engineering.

Delhi-specific: cooling load dominates electricity demand. Features like
CDD (Cooling Degree Days), heat index, and temperature-hour interactions
are among the strongest predictors after lag features.
"""

import numpy as np
import pandas as pd


def add_heat_index(df: pd.DataFrame) -> pd.DataFrame:
    """Compute heat index (feels-like temperature) from temp and humidity.

    Uses the simplified Steadman formula. Heat index is more predictive
    than raw temperature for Delhi's monsoon season when humidity is extreme
    and people run AC even at 30C.
    """
    T = df.get("temperature_2m")
    RH = df.get("relative_humidity_2m")

    if T is None or RH is None:
        return df

    # Simplified Steadman formula (valid for T > 20C)
    HI = (
        -8.7847
        + 1.6114 * T
        + 2.3385 * RH
        - 0.1462 * T * RH
        - 0.0123 * T**2
        - 0.0164 * RH**2
        + 0.0022 * T**2 * RH
        + 0.0007 * T * RH**2
        - 0.0000036 * T**2 * RH**2
    )

    # For low temperatures, heat index = temperature
    df["heat_index"] = np.where(T > 20, HI, T)

    return df


def add_degree_days(
    df: pd.DataFrame, cooling_base: float = 24.0, heating_base: float = 18.0
) -> pd.DataFrame:
    """Add Cooling Degree Days (CDD) and Heating Degree Days (HDD).

    CDD is critical for Delhi where cooling (AC) dominates electricity demand.
    CDD = max(temperature - base, 0). Higher CDD = more AC usage = more demand.

    Delhi-specific base temperatures:
    - Cooling base 24C: AC usage starts around this threshold
    - Heating base 18C: minimal heating in Delhi, but some electric heaters in winter
    """
    T = df.get("temperature_2m")
    if T is None:
        return df

    df["CDD"] = np.maximum(T - cooling_base, 0)
    df["HDD"] = np.maximum(heating_base - T, 0)

    return df


def add_weather_interactions(df: pd.DataFrame) -> pd.DataFrame:
    """Add interaction and non-linear weather features.

    Temperature x Hour captures the AC load curve: high temp at 3 PM
    causes much more demand than high temp at 3 AM.
    """
    T = df.get("temperature_2m")
    RH = df.get("relative_humidity_2m")

    if T is None:
        return df

    # Non-linear temperature effects (U-shaped: heating + cooling)
    df["temp_squared"] = T**2

    # Temperature-humidity interaction (discomfort index)
    if RH is not None:
        df["temp_x_humidity"] = T * RH / 100.0

    # Temperature-hour interaction (AC load curve)
    if "hour" in df.columns:
        df["temp_x_hour"] = T * df["hour"]

    # Temperature ramp rate (how fast is it getting hotter/colder)
    df["temp_ramp_1h"] = T.diff(1)
    df["temp_ramp_3h"] = T.diff(3) if len(df) > 3 else 0

    return df


def add_weather_categories(df: pd.DataFrame) -> pd.DataFrame:
    """Categorize weather conditions for Delhi's climate.

    Delhi has 5 effective seasons that drive different demand patterns:
    - Winter (Nov-Feb): Low demand, some heating
    - Spring (Mar-Apr): Rapidly rising demand
    - Summer (May-Jun): Peak demand, extreme heat, AC dominates
    - Monsoon (Jul-Sep): High humidity, moderate temp, still high demand
    - Autumn (Oct): Transitional, AQI worsens
    """
    if "month" not in df.columns:
        df["month"] = df.index.month

    conditions = [
        df["month"].isin([11, 12, 1, 2]),
        df["month"].isin([3, 4]),
        df["month"].isin([5, 6]),
        df["month"].isin([7, 8, 9]),
        df["month"].isin([10]),
    ]
    seasons = ["winter", "spring", "summer", "monsoon", "autumn"]
    df["delhi_season"] = np.select(conditions, seasons, default="unknown")

    # One-hot encode seasons
    for season in seasons:
        df[f"season_{season}"] = (df["delhi_season"] == season).astype(int)

    # Precipitation flag (rainy day reduces outdoor activity)
    precip = df.get("precipitation_mm")
    if precip is not None:
        df["is_rainy"] = (precip > 1.0).astype(int)
        df["is_heavy_rain"] = (precip > 10.0).astype(int)

    # Cloud cover categories
    cloud = df.get("cloud_cover_pct")
    if cloud is not None:
        df["is_cloudy"] = (cloud > 50).astype(int)
        df["is_clear"] = (cloud < 20).astype(int)

    return df


def add_solar_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add solar radiation derived features.

    Solar irradiance drives both:
    1. Direct AC load (sun heats buildings)
    2. Rooftop solar generation (reduces net grid demand)
    """
    solar = df.get("shortwave_radiation")
    if solar is None:
        return df

    # Is daylight (radiation > 0)
    df["is_daylight"] = (solar > 10).astype(int)

    # Solar intensity category
    df["solar_high"] = (solar > 500).astype(int)

    return df

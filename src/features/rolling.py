"""Rolling statistics feature engineering.

Rolling mean, std, min, max capture recent trends and volatility
in demand. These help models understand whether demand is currently
trending up/down and how variable it has been recently.
"""

import pandas as pd


# Rolling window sizes by resolution (in number of timesteps)
WINDOW_CONFIGS = {
    "5min": {
        "1h": 12,       # 12 x 5min = 1 hour
        "1d": 288,      # 288 x 5min = 24 hours
        "7d": 2016,     # 2016 x 5min = 7 days
    },
    "hourly": {
        "6h": 6,
        "1d": 24,
        "7d": 168,
        "30d": 720,
    },
    "daily": {
        "7d": 7,
        "14d": 14,
        "30d": 30,
        "90d": 90,
    },
}


def add_rolling_stats(
    df: pd.DataFrame, target: str, resolution: str
) -> pd.DataFrame:
    """Add rolling mean, std, min, max for the target variable.

    All rolling windows are backward-looking only (no future data leakage).
    min_periods=1 ensures we get values even at the start of the series.
    """
    windows = WINDOW_CONFIGS.get(resolution, WINDOW_CONFIGS["hourly"])

    for name, size in windows.items():
        rolling = df[target].rolling(window=size, min_periods=1)

        df[f"{target}_rmean_{name}"] = rolling.mean()
        df[f"{target}_rstd_{name}"] = rolling.std().fillna(0)
        df[f"{target}_rmin_{name}"] = rolling.min()
        df[f"{target}_rmax_{name}"] = rolling.max()

    return df


def add_rolling_weather_stats(
    df: pd.DataFrame, resolution: str
) -> pd.DataFrame:
    """Add rolling statistics for weather features.

    Rolling CDD (accumulated cooling stress) is especially important:
    3 consecutive hot days cause more demand than a single hot day
    because buildings retain heat.
    """
    windows = WINDOW_CONFIGS.get(resolution, WINDOW_CONFIGS["hourly"])

    # Use the shortest and a medium window
    window_names = list(windows.keys())
    short = window_names[0]
    medium = window_names[min(1, len(window_names) - 1)]

    short_size = windows[short]
    medium_size = windows[medium]

    # Rolling temperature
    if "temperature_2m" in df.columns:
        df[f"temp_rmean_{short}"] = (
            df["temperature_2m"].rolling(short_size, min_periods=1).mean()
        )
        df[f"temp_rmean_{medium}"] = (
            df["temperature_2m"].rolling(medium_size, min_periods=1).mean()
        )

    # Rolling CDD (accumulated cooling stress)
    if "CDD" in df.columns:
        df[f"CDD_rsum_{short}"] = (
            df["CDD"].rolling(short_size, min_periods=1).sum()
        )
        df[f"CDD_rsum_{medium}"] = (
            df["CDD"].rolling(medium_size, min_periods=1).sum()
        )

    # Rolling humidity
    if "relative_humidity_2m" in df.columns:
        df[f"humidity_rmean_{medium}"] = (
            df["relative_humidity_2m"].rolling(medium_size, min_periods=1).mean()
        )

    return df

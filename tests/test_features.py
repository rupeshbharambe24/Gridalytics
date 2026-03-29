"""Tests for feature engineering pipeline."""

import pytest
import numpy as np
import pandas as pd
from datetime import datetime

from src.features.temporal import (
    add_lag_features, add_diff_features, add_cyclical_encoding,
    add_fourier_terms, add_time_features,
)
from src.features.weather import (
    add_heat_index, add_degree_days, add_weather_interactions,
    add_weather_categories,
)
from src.features.rolling import add_rolling_stats


class TestTemporalFeatures:
    def test_lag_features_hourly(self, sample_demand_df):
        df = add_lag_features(sample_demand_df, "delhi_mw", "hourly")
        assert "delhi_mw_lag_1" in df.columns
        assert "delhi_mw_lag_24" in df.columns
        assert "delhi_mw_lag_168" in df.columns
        # lag_1 should be previous value
        assert df["delhi_mw_lag_1"].iloc[1] == df["delhi_mw"].iloc[0]

    def test_lag_features_daily(self, sample_demand_df):
        daily = sample_demand_df.resample("D").mean()
        df = add_lag_features(daily, "delhi_mw", "daily")
        assert "delhi_mw_lag_1" in df.columns
        assert "delhi_mw_lag_7" in df.columns
        assert "delhi_mw_lag_365" in df.columns

    def test_diff_features(self, sample_demand_df):
        df = add_diff_features(sample_demand_df, "delhi_mw", "hourly")
        assert "delhi_mw_diff_1" in df.columns
        assert "delhi_mw_diff_24" in df.columns

    def test_cyclical_encoding(self, sample_demand_df):
        df = add_cyclical_encoding(sample_demand_df)
        assert "hour_sin" in df.columns
        assert "hour_cos" in df.columns
        assert "dow_sin" in df.columns
        assert "is_weekend" in df.columns
        # sin^2 + cos^2 should ≈ 1
        sin_sq = df["hour_sin"] ** 2
        cos_sq = df["hour_cos"] ** 2
        np.testing.assert_allclose(sin_sq + cos_sq, 1.0, atol=1e-10)

    def test_fourier_terms(self, sample_demand_df):
        df = add_fourier_terms(sample_demand_df, "hourly", n_terms=2)
        assert "fourier_sin_24_1" in df.columns
        assert "fourier_cos_168_2" in df.columns

    def test_time_features(self, sample_demand_df):
        df = add_time_features(sample_demand_df)
        assert "is_peak_hour" in df.columns
        assert "is_night" in df.columns
        # 3 PM should be peak hour
        assert df.loc[df.index.hour == 15, "is_peak_hour"].all()
        # 2 AM should be night
        assert df.loc[df.index.hour == 2, "is_night"].all()


class TestWeatherFeatures:
    def test_degree_days(self):
        df = pd.DataFrame({
            "temperature_2m": [10, 20, 30, 40],
        }, index=pd.date_range("2024-01-01", periods=4, freq="h"))

        df = add_degree_days(df, cooling_base=24, heating_base=18)
        assert "CDD" in df.columns
        assert "HDD" in df.columns
        assert df["CDD"].iloc[0] == 0     # 10C < 24C base
        assert df["CDD"].iloc[3] == 16    # 40C - 24C = 16
        assert df["HDD"].iloc[0] == 8     # 18C - 10C = 8
        assert df["HDD"].iloc[3] == 0     # 40C > 18C base

    def test_heat_index(self):
        df = pd.DataFrame({
            "temperature_2m": [35.0],
            "relative_humidity_2m": [60.0],
        }, index=pd.date_range("2024-06-01", periods=1, freq="h"))

        df = add_heat_index(df)
        assert "heat_index" in df.columns
        assert df["heat_index"].iloc[0] > 35  # should feel hotter

    def test_heat_index_low_temp(self):
        df = pd.DataFrame({
            "temperature_2m": [15.0],
            "relative_humidity_2m": [50.0],
        }, index=pd.date_range("2024-01-01", periods=1, freq="h"))

        df = add_heat_index(df)
        assert df["heat_index"].iloc[0] == 15.0  # below 20C, returns raw temp

    def test_weather_categories(self):
        df = pd.DataFrame({
            "temperature_2m": [10, 25, 35, 30, 22],
            "month": [1, 4, 6, 8, 10],
        }, index=pd.date_range("2024-01-01", periods=5, freq="D"))

        df = add_weather_categories(df)
        assert "season_winter" in df.columns
        assert "season_summer" in df.columns
        assert df["season_winter"].iloc[0] == 1  # January
        assert df["season_summer"].iloc[2] == 1  # June


class TestRollingFeatures:
    def test_rolling_stats(self, sample_demand_df):
        df = add_rolling_stats(sample_demand_df, "delhi_mw", "hourly")
        assert "delhi_mw_rmean_6h" in df.columns
        assert "delhi_mw_rstd_1d" in df.columns
        assert "delhi_mw_rmin_7d" in df.columns
        assert "delhi_mw_rmax_30d" in df.columns
        # Rolling mean should be close to actual for smooth data
        assert not df["delhi_mw_rmean_6h"].isna().all()

    def test_no_future_leakage(self, sample_demand_df):
        """Rolling stats should only use past data."""
        df = add_rolling_stats(sample_demand_df, "delhi_mw", "hourly")
        # The rolling mean at index 5 should only consider indices 0-5
        window = sample_demand_df["delhi_mw"].iloc[:6]
        expected = window.mean()
        actual = df["delhi_mw_rmean_6h"].iloc[5]
        np.testing.assert_allclose(actual, expected, rtol=0.01)

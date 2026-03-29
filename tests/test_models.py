"""Tests for ML models."""

import pytest
import numpy as np
import pandas as pd
from pathlib import Path
import tempfile
import shutil

from src.models.lightgbm_model import LightGBMForecaster
from src.models.xgboost_model import XGBoostForecaster
from src.models.ensemble import EnsembleForecaster


class TestLightGBMForecaster:
    def test_init(self):
        model = LightGBMForecaster(resolution="hourly")
        assert model.name == "lightgbm"
        assert model.resolution == "hourly"
        assert not model.is_fitted

    def test_fit_and_predict(self, sample_features_df):
        df = sample_features_df
        target = "delhi_mw"
        features = [c for c in df.columns if c != target]

        train = df.iloc[:400]
        test = df.iloc[400:]

        model = LightGBMForecaster(resolution="hourly", params={
            "n_estimators": 50, "num_leaves": 15, "verbose": -1
        })

        metrics = model.fit(train[features], train[target], test[features], test[target])
        assert model.is_fitted
        assert "train_mae" in metrics
        assert "train_mape" in metrics

        preds = model.predict(test[features])
        assert len(preds) == len(test)
        assert all(np.isfinite(preds))

    def test_predict_interval(self, sample_features_df):
        df = sample_features_df
        target = "delhi_mw"
        features = [c for c in df.columns if c != target]

        model = LightGBMForecaster(resolution="hourly", params={
            "n_estimators": 50, "num_leaves": 15, "verbose": -1
        })
        model.fit(df.iloc[:400][features], df.iloc[:400][target])

        point, lower, upper = model.predict_interval(df.iloc[400:][features])
        assert len(point) == len(lower) == len(upper) == 100
        # Lower should generally be less than upper
        assert np.mean(lower <= upper) > 0.9

    def test_save_and_load(self, sample_features_df):
        df = sample_features_df
        target = "delhi_mw"
        features = [c for c in df.columns if c != target]

        model = LightGBMForecaster(resolution="hourly", params={
            "n_estimators": 50, "num_leaves": 15, "verbose": -1
        })
        model.fit(df.iloc[:400][features], df.iloc[:400][target])

        with tempfile.TemporaryDirectory() as tmpdir:
            save_path = Path(tmpdir) / "test_model"
            model.save(save_path)
            assert (save_path / "model.txt").exists()
            assert (save_path / "meta.json").exists()

            loaded = LightGBMForecaster.load(save_path)
            assert loaded.is_fitted
            assert loaded.resolution == "hourly"
            assert loaded.feature_names == model.feature_names

    def test_feature_importance(self, sample_features_df):
        df = sample_features_df
        target = "delhi_mw"
        features = [c for c in df.columns if c != target]

        model = LightGBMForecaster(resolution="hourly", params={
            "n_estimators": 50, "num_leaves": 15, "verbose": -1
        })
        model.fit(df.iloc[:400][features], df.iloc[:400][target])

        imp = model.get_feature_importance()
        assert imp is not None
        assert len(imp) == len(features)
        assert imp.sum() > 0

    def test_model_size_reasonable(self, sample_features_df):
        """Model file should be under 10MB for this test data."""
        df = sample_features_df
        target = "delhi_mw"
        features = [c for c in df.columns if c != target]

        model = LightGBMForecaster(resolution="hourly", params={
            "n_estimators": 100, "num_leaves": 31, "verbose": -1
        })
        model.fit(df.iloc[:400][features], df.iloc[:400][target])

        with tempfile.TemporaryDirectory() as tmpdir:
            save_path = Path(tmpdir) / "test_model"
            model.save(save_path)
            total_size = sum(f.stat().st_size for f in save_path.rglob("*")) / (1024 * 1024)
            assert total_size < 10  # MB


class TestXGBoostForecaster:
    def test_fit_and_predict(self, sample_features_df):
        df = sample_features_df
        target = "delhi_mw"
        features = [c for c in df.columns if c != target]

        model = XGBoostForecaster(resolution="hourly", params={
            "n_estimators": 50, "max_depth": 5, "verbosity": 0
        })
        # XGBoost early_stopping needs eval_set, so pass validation data
        model.fit(df.iloc[:400][features], df.iloc[:400][target],
                  df.iloc[400:][features], df.iloc[400:][target])
        assert model.is_fitted

        preds = model.predict(df.iloc[400:][features])
        assert len(preds) == 100
        assert all(np.isfinite(preds))


class TestEnsemble:
    def test_ensemble_prediction(self, sample_features_df):
        df = sample_features_df
        target = "delhi_mw"
        features = [c for c in df.columns if c != target]

        lgb = LightGBMForecaster(resolution="hourly", params={
            "n_estimators": 50, "num_leaves": 15, "verbose": -1
        })
        xgb = XGBoostForecaster(resolution="hourly", params={
            "n_estimators": 50, "max_depth": 5, "verbosity": 0
        })

        lgb.fit(df.iloc[:400][features], df.iloc[:400][target])
        xgb.fit(df.iloc[:400][features], df.iloc[:400][target],
                df.iloc[400:][features], df.iloc[400:][target])

        ensemble = EnsembleForecaster([lgb, xgb], resolution="hourly", weights=[0.5, 0.5])
        preds = ensemble.predict(df.iloc[400:][features])
        assert len(preds) == 100

        # Ensemble should be between individual predictions
        lgb_preds = lgb.predict(df.iloc[400:][features])
        xgb_preds = xgb.predict(df.iloc[400:][features])
        expected = 0.5 * lgb_preds + 0.5 * xgb_preds
        np.testing.assert_allclose(preds, expected, rtol=1e-5)

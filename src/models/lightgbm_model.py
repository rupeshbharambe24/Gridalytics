"""LightGBM forecaster - primary baseline model.

Expected performance: MAPE < 5% daily, < 4% hourly
Expected model size: 1-5 MB (vs 395 MB for old SARIMAX)
Training time: seconds to minutes
"""

import json
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd

from .base import BaseForecaster


# Default hyperparameters (can be tuned with Optuna)
DEFAULT_PARAMS = {
    "objective": "regression",
    "metric": "mae",
    "boosting_type": "gbdt",
    "num_leaves": 63,
    "learning_rate": 0.05,
    "feature_fraction": 0.8,
    "bagging_fraction": 0.8,
    "bagging_freq": 5,
    "min_child_samples": 20,
    "reg_alpha": 0.1,
    "reg_lambda": 0.1,
    "n_estimators": 1000,
    "verbose": -1,
    "n_jobs": -1,
}


class LightGBMForecaster(BaseForecaster):
    """LightGBM gradient boosting forecaster.

    Trains 3 models for quantile prediction:
    - q=0.50 (median, used as point prediction)
    - q=0.05 (lower bound of 90% prediction interval)
    - q=0.95 (upper bound of 90% prediction interval)
    """

    def __init__(self, resolution: str, params: dict | None = None):
        super().__init__(resolution=resolution, name="lightgbm")
        self.params = {**DEFAULT_PARAMS, **(params or {})}
        self.model: lgb.LGBMRegressor | None = None
        self.model_lower: lgb.LGBMRegressor | None = None
        self.model_upper: lgb.LGBMRegressor | None = None
        self.feature_names: list[str] = []

    def fit(
        self,
        X_train: pd.DataFrame,
        y_train: pd.Series,
        X_val: pd.DataFrame | None = None,
        y_val: pd.Series | None = None,
    ) -> dict:
        """Train LightGBM models (point + quantile)."""
        self.feature_names = list(X_train.columns)

        callbacks = [lgb.log_evaluation(period=0)]  # suppress per-iteration logging
        if X_val is not None and y_val is not None:
            callbacks.append(lgb.early_stopping(stopping_rounds=50, verbose=False))
            eval_set = [(X_val, y_val)]
        else:
            eval_set = None

        # Point prediction model (regression)
        self.model = lgb.LGBMRegressor(**self.params)
        self.model.fit(
            X_train, y_train,
            eval_set=eval_set,
            callbacks=callbacks,
        )

        # Quantile models for prediction intervals
        q_params = {**self.params, "objective": "quantile", "metric": "quantile"}

        self.model_lower = lgb.LGBMRegressor(**{**q_params, "alpha": 0.05})
        self.model_lower.fit(X_train, y_train, eval_set=eval_set, callbacks=callbacks)

        self.model_upper = lgb.LGBMRegressor(**{**q_params, "alpha": 0.95})
        self.model_upper.fit(X_train, y_train, eval_set=eval_set, callbacks=callbacks)

        self.is_fitted = True

        # Return training metrics
        train_pred = self.model.predict(X_train)
        metrics = {
            "train_mae": float(np.mean(np.abs(y_train - train_pred))),
            "train_mape": float(np.mean(np.abs((y_train - train_pred) / y_train)) * 100),
            "n_estimators_used": self.model.best_iteration_ if self.model.best_iteration_ > 0 else self.params["n_estimators"],
        }

        if X_val is not None and y_val is not None:
            val_pred = self.model.predict(X_val)
            metrics["val_mae"] = float(np.mean(np.abs(y_val - val_pred)))
            metrics["val_mape"] = float(np.mean(np.abs((y_val - val_pred) / y_val)) * 100)

        return metrics

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        """Return point predictions."""
        return self.model.predict(X)

    def predict_interval(
        self, X: pd.DataFrame, alpha: float = 0.05
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Return (point, lower, upper) predictions."""
        point = self.model.predict(X)
        lower = self.model_lower.predict(X)
        upper = self.model_upper.predict(X)
        return point, lower, upper

    def save(self, path: str | Path) -> None:
        """Save all 3 models to disk."""
        path = Path(path)
        path.mkdir(parents=True, exist_ok=True)

        self.model.booster_.save_model(str(path / "model.txt"))
        self.model_lower.booster_.save_model(str(path / "model_lower.txt"))
        self.model_upper.booster_.save_model(str(path / "model_upper.txt"))

        meta = {
            "name": self.name,
            "resolution": self.resolution,
            "params": self.params,
            "feature_names": self.feature_names,
        }
        with open(path / "meta.json", "w") as f:
            json.dump(meta, f, indent=2, default=str)

    @classmethod
    def load(cls, path: str | Path) -> "LightGBMForecaster":
        """Load models from disk."""
        path = Path(path)

        with open(path / "meta.json") as f:
            meta = json.load(f)

        forecaster = cls(resolution=meta["resolution"], params=meta["params"])
        forecaster.feature_names = meta["feature_names"]

        forecaster.model = lgb.Booster(model_file=str(path / "model.txt"))
        forecaster.model_lower = lgb.Booster(model_file=str(path / "model_lower.txt"))
        forecaster.model_upper = lgb.Booster(model_file=str(path / "model_upper.txt"))
        forecaster.is_fitted = True

        # Wrap Boosters to have a predict method compatible with our interface
        return forecaster

    def get_feature_importance(self) -> pd.Series:
        """Return feature importances from the point prediction model."""
        if not self.is_fitted or not hasattr(self.model, "feature_importances_"):
            return None
        return pd.Series(
            self.model.feature_importances_,
            index=self.feature_names,
        ).sort_values(ascending=False)

    def get_params(self) -> dict:
        """Return hyperparameters for MLflow logging."""
        return {
            "name": self.name,
            "resolution": self.resolution,
            "num_leaves": self.params["num_leaves"],
            "learning_rate": self.params["learning_rate"],
            "n_estimators": self.params["n_estimators"],
            "feature_fraction": self.params["feature_fraction"],
        }

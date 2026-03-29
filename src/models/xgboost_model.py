"""XGBoost forecaster - comparison model alongside LightGBM."""

import json
from pathlib import Path

import numpy as np
import pandas as pd
import xgboost as xgb

from .base import BaseForecaster


DEFAULT_PARAMS = {
    "objective": "reg:squarederror",
    "eval_metric": "mae",
    "max_depth": 8,
    "learning_rate": 0.05,
    "n_estimators": 1000,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "reg_alpha": 0.1,
    "reg_lambda": 1.0,
    "min_child_weight": 5,
    "tree_method": "hist",
    "verbosity": 0,
    "n_jobs": -1,
}


class XGBoostForecaster(BaseForecaster):
    """XGBoost gradient boosting forecaster with quantile prediction."""

    def __init__(self, resolution: str, params: dict | None = None):
        super().__init__(resolution=resolution, name="xgboost")
        self.params = {**DEFAULT_PARAMS, **(params or {})}
        self.model: xgb.XGBRegressor | None = None
        self.model_lower: xgb.XGBRegressor | None = None
        self.model_upper: xgb.XGBRegressor | None = None
        self.feature_names: list[str] = []

    def fit(
        self,
        X_train: pd.DataFrame,
        y_train: pd.Series,
        X_val: pd.DataFrame | None = None,
        y_val: pd.Series | None = None,
    ) -> dict:
        self.feature_names = list(X_train.columns)

        fit_kwargs = {}
        if X_val is not None and y_val is not None:
            fit_kwargs["eval_set"] = [(X_val, y_val)]
            fit_kwargs["verbose"] = False

        # Point prediction
        self.model = xgb.XGBRegressor(**self.params, early_stopping_rounds=50)
        self.model.fit(X_train, y_train, **fit_kwargs)

        # Quantile models
        q_params = {**self.params, "objective": "reg:quantileerror"}

        self.model_lower = xgb.XGBRegressor(**q_params, quantile_alpha=0.05, early_stopping_rounds=50)
        self.model_lower.fit(X_train, y_train, **fit_kwargs)

        self.model_upper = xgb.XGBRegressor(**q_params, quantile_alpha=0.95, early_stopping_rounds=50)
        self.model_upper.fit(X_train, y_train, **fit_kwargs)

        self.is_fitted = True

        train_pred = self.model.predict(X_train)
        metrics = {
            "train_mae": float(np.mean(np.abs(y_train - train_pred))),
            "train_mape": float(np.mean(np.abs((y_train - train_pred) / y_train)) * 100),
        }
        if X_val is not None and y_val is not None:
            val_pred = self.model.predict(X_val)
            metrics["val_mae"] = float(np.mean(np.abs(y_val - val_pred)))
            metrics["val_mape"] = float(np.mean(np.abs((y_val - val_pred) / y_val)) * 100)

        return metrics

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        return self.model.predict(X)

    def predict_interval(
        self, X: pd.DataFrame, alpha: float = 0.05
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        point = self.model.predict(X)
        lower = self.model_lower.predict(X)
        upper = self.model_upper.predict(X)
        return point, lower, upper

    def save(self, path: str | Path) -> None:
        path = Path(path)
        path.mkdir(parents=True, exist_ok=True)
        self.model.save_model(str(path / "model.json"))
        self.model_lower.save_model(str(path / "model_lower.json"))
        self.model_upper.save_model(str(path / "model_upper.json"))
        meta = {"name": self.name, "resolution": self.resolution,
                "params": self.params, "feature_names": self.feature_names}
        with open(path / "meta.json", "w") as f:
            json.dump(meta, f, indent=2, default=str)

    @classmethod
    def load(cls, path: str | Path) -> "XGBoostForecaster":
        path = Path(path)
        with open(path / "meta.json") as f:
            meta = json.load(f)
        forecaster = cls(resolution=meta["resolution"], params=meta["params"])
        forecaster.feature_names = meta["feature_names"]
        forecaster.model = xgb.XGBRegressor()
        forecaster.model.load_model(str(path / "model.json"))
        forecaster.model_lower = xgb.XGBRegressor()
        forecaster.model_lower.load_model(str(path / "model_lower.json"))
        forecaster.model_upper = xgb.XGBRegressor()
        forecaster.model_upper.load_model(str(path / "model_upper.json"))
        forecaster.is_fitted = True
        return forecaster

    def get_feature_importance(self) -> pd.Series:
        if not self.is_fitted:
            return None
        imp = self.model.get_booster().get_score(importance_type="gain")
        return pd.Series(imp).sort_values(ascending=False)

    def get_params(self) -> dict:
        return {"name": self.name, "resolution": self.resolution,
                "max_depth": self.params["max_depth"],
                "learning_rate": self.params["learning_rate"],
                "n_estimators": self.params["n_estimators"]}

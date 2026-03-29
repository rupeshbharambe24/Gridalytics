"""Ensemble forecaster - weighted combination of multiple models.

Weights are determined by inverse MAPE on validation data:
better models get higher weight.
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd

from .base import BaseForecaster


class EnsembleForecaster(BaseForecaster):
    """Weighted ensemble of multiple forecasting models."""

    def __init__(
        self,
        models: list[BaseForecaster],
        resolution: str,
        weights: list[float] | None = None,
    ):
        super().__init__(resolution=resolution, name="ensemble")
        self.models = models
        self.weights = weights or [1.0 / len(models)] * len(models)
        self.is_fitted = all(m.is_fitted for m in models)

    def fit(self, X_train, y_train, X_val=None, y_val=None) -> dict:
        """Fit all sub-models and compute weights from validation MAPE."""
        mapes = []
        for model in self.models:
            model.fit(X_train, y_train, X_val, y_val)
            if X_val is not None and y_val is not None:
                preds = model.predict(X_val)
                mape = float(np.mean(np.abs((y_val - preds) / y_val)) * 100)
                mapes.append(mape)

        # Compute inverse-MAPE weights
        if mapes:
            inv_mapes = [1.0 / max(m, 0.01) for m in mapes]
            total = sum(inv_mapes)
            self.weights = [w / total for w in inv_mapes]

        self.is_fitted = True
        return {"weights": dict(zip([m.name for m in self.models], self.weights))}

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        """Weighted average of all model predictions."""
        preds = np.zeros(len(X))
        for model, weight in zip(self.models, self.weights):
            preds += weight * model.predict(X)
        return preds

    def predict_interval(self, X, alpha=0.05):
        """Combine prediction intervals (take widest bounds)."""
        point = self.predict(X)
        lowers, uppers = [], []
        for model in self.models:
            _, lo, hi = model.predict_interval(X, alpha)
            lowers.append(lo)
            uppers.append(hi)
        lower = np.min(lowers, axis=0)
        upper = np.max(uppers, axis=0)
        return point, lower, upper

    def save(self, path: str | Path) -> None:
        path = Path(path)
        path.mkdir(parents=True, exist_ok=True)
        for i, model in enumerate(self.models):
            model.save(path / f"model_{i}_{model.name}")
        meta = {"name": "ensemble", "resolution": self.resolution,
                "model_names": [m.name for m in self.models],
                "weights": self.weights}
        with open(path / "meta.json", "w") as f:
            json.dump(meta, f, indent=2)

    @classmethod
    def load(cls, path: str | Path) -> "EnsembleForecaster":
        raise NotImplementedError("Load individual models and construct ensemble manually")

    def get_params(self) -> dict:
        return {"name": "ensemble", "n_models": len(self.models),
                "model_names": [m.name for m in self.models],
                "weights": self.weights}

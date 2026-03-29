"""Abstract base class for all Gridalytics forecasting models."""

from abc import ABC, abstractmethod
from pathlib import Path

import numpy as np
import pandas as pd


class BaseForecaster(ABC):
    """Base interface for all Gridalytics forecasting models."""

    def __init__(self, resolution: str, name: str):
        self.resolution = resolution
        self.name = name
        self.is_fitted = False

    @abstractmethod
    def fit(
        self,
        X_train: pd.DataFrame,
        y_train: pd.Series,
        X_val: pd.DataFrame | None = None,
        y_val: pd.Series | None = None,
    ) -> dict:
        """Train the model. Returns dict of training metrics."""
        ...

    @abstractmethod
    def predict(self, X: pd.DataFrame) -> np.ndarray:
        """Return point predictions."""
        ...

    def predict_interval(
        self, X: pd.DataFrame, alpha: float = 0.05
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Return (point, lower, upper) predictions.

        Default implementation returns point prediction with no interval.
        Override in subclasses that support quantile/interval prediction.
        """
        point = self.predict(X)
        return point, point, point

    @abstractmethod
    def save(self, path: str | Path) -> None:
        """Save model to disk."""
        ...

    @classmethod
    @abstractmethod
    def load(cls, path: str | Path) -> "BaseForecaster":
        """Load model from disk."""
        ...

    def get_feature_importance(self) -> pd.Series | None:
        """Return feature importances. Override in subclasses that support it."""
        return None

    def get_params(self) -> dict:
        """Return model hyperparameters for logging."""
        return {"name": self.name, "resolution": self.resolution}

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name={self.name!r}, resolution={self.resolution!r})"

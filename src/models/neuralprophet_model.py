"""NeuralProphet forecaster for daily demand prediction.

NeuralProphet = Facebook Prophet + Neural Network components.
Best for daily resolution with holiday effects.
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd

from .base import BaseForecaster


class NeuralProphetForecaster(BaseForecaster):
    """NeuralProphet daily demand forecaster."""

    def __init__(self, resolution: str = "daily", epochs: int = 100,
                 learning_rate: float = 0.01, yearly_seasonality: int = 10,
                 weekly_seasonality: int = 5):
        super().__init__(resolution=resolution, name="neuralprophet")
        self.epochs = epochs
        self.learning_rate = learning_rate
        self.yearly_seasonality = yearly_seasonality
        self.weekly_seasonality = weekly_seasonality
        self.model = None
        self.feature_names: list[str] = []

    def fit(self, X_train, y_train, X_val=None, y_val=None):
        from neuralprophet import NeuralProphet, set_log_level
        set_log_level("ERROR")

        self.feature_names = list(X_train.columns)

        # NeuralProphet expects a DataFrame with 'ds' and 'y' columns
        train_df = pd.DataFrame({
            "ds": X_train.index,
            "y": y_train.values,
        })

        # Add regressors from key features
        regressor_cols = []
        for col in ["temperature_2m", "CDD", "HDD", "is_holiday", "is_weekend"]:
            if col in X_train.columns:
                train_df[col] = X_train[col].values
                regressor_cols.append(col)

        self.model = NeuralProphet(
            epochs=self.epochs,
            learning_rate=self.learning_rate,
            yearly_seasonality=self.yearly_seasonality,
            weekly_seasonality=self.weekly_seasonality,
            daily_seasonality=False if self.resolution == "daily" else "auto",
            n_forecasts=1,
            n_lags=0,  # use regressors instead of auto-regression for simplicity
            batch_size=64,
            accelerator="auto",
        )

        # Add country holidays
        self.model.add_country_holidays("IN")

        # Add lagged regressors
        for col in regressor_cols:
            self.model.add_future_regressor(col)

        # Prepare validation
        val_df = None
        if X_val is not None and y_val is not None:
            val_df = pd.DataFrame({"ds": X_val.index, "y": y_val.values})
            for col in regressor_cols:
                if col in X_val.columns:
                    val_df[col] = X_val[col].values

        # Train
        metrics = self.model.fit(train_df, freq="D" if self.resolution == "daily" else "h",
                                  validation_df=val_df)

        self.is_fitted = True
        self._regressor_cols = regressor_cols

        # Compute train metrics
        train_pred = self.model.predict(train_df)
        y_pred = train_pred["yhat1"].values
        y_true = y_train.values[:len(y_pred)]
        mask = y_true > 0
        train_mape = float(np.mean(np.abs((y_true[mask] - y_pred[mask]) / y_true[mask])) * 100)

        return {"train_mape": train_mape, "train_mae": float(np.mean(np.abs(y_true - y_pred)))}

    def predict(self, X):
        future_df = pd.DataFrame({"ds": X.index})
        for col in self._regressor_cols:
            if col in X.columns:
                future_df[col] = X[col].values

        forecast = self.model.predict(future_df)
        return forecast["yhat1"].values

    def predict_interval(self, X, alpha=0.05):
        point = self.predict(X)
        lower = point * 0.93
        upper = point * 1.07
        return point, lower, upper

    def save(self, path):
        path = Path(path)
        path.mkdir(parents=True, exist_ok=True)
        # NeuralProphet save
        self.model.save(str(path / "neuralprophet_model.np"))
        meta = {
            "name": self.name, "resolution": self.resolution,
            "epochs": self.epochs, "regressor_cols": self._regressor_cols,
            "feature_names": self.feature_names,
        }
        with open(path / "meta.json", "w") as f:
            json.dump(meta, f, indent=2)

    @classmethod
    def load(cls, path):
        from neuralprophet import NeuralProphet
        path = Path(path)
        with open(path / "meta.json") as f:
            meta = json.load(f)
        forecaster = cls(resolution=meta["resolution"], epochs=meta["epochs"])
        forecaster.model = NeuralProphet.load(str(path / "neuralprophet_model.np"))
        forecaster.feature_names = meta["feature_names"]
        forecaster._regressor_cols = meta["regressor_cols"]
        forecaster.is_fitted = True
        return forecaster

    def get_params(self):
        return {"name": "neuralprophet", "resolution": self.resolution,
                "epochs": self.epochs, "yearly_seasonality": self.yearly_seasonality,
                "weekly_seasonality": self.weekly_seasonality}

"""Corrected SARIMAX forecaster.

Fixes from the old EDFS:
- Correct seasonal periods: m=7 for daily, m=24 for hourly (NOT m=12)
- Uses auto_arima to find optimal (p,d,q) orders
- Trains on train data only (no data leakage)
- Scaler fit on train only
- Skips 5-min (m=288 is computationally infeasible)
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd
import joblib
from sklearn.preprocessing import StandardScaler

from .base import BaseForecaster

# Correct seasonal periods for Delhi electricity demand
SEASONAL_PERIODS = {
    "daily": 7,     # Weekly cycle (7 days)
    "hourly": 24,   # Daily cycle (24 hours)
}


class SARIMAXForecaster(BaseForecaster):
    """SARIMAX model with corrected seasonal periods."""

    def __init__(self, resolution: str, max_p: int = 3, max_q: int = 3,
                 max_P: int = 1, max_Q: int = 1, max_d: int = 2):
        super().__init__(resolution=resolution, name="sarimax")
        if resolution == "5min":
            raise ValueError("SARIMAX is not feasible for 5-min resolution (m=288 too large)")
        self.max_p = max_p
        self.max_q = max_q
        self.max_P = max_P
        self.max_Q = max_Q
        self.max_d = max_d
        self.seasonal_period = SEASONAL_PERIODS.get(resolution, 7)
        self.model = None
        self.model_fit = None
        self.scaler = StandardScaler()
        self.feature_names: list[str] = []
        self.order = None
        self.seasonal_order = None

    def fit(self, X_train, y_train, X_val=None, y_val=None):
        import pmdarima as pm
        from statsmodels.tsa.statespace.sarimax import SARIMAX

        self.feature_names = list(X_train.columns)

        # Select key exogenous variables only (SARIMAX can't handle 90+ features)
        exog_cols = [c for c in ["temperature_2m", "CDD", "is_holiday", "is_weekend"]
                     if c in X_train.columns]

        exog_train = X_train[exog_cols].values if exog_cols else None

        # Scale exogenous
        if exog_train is not None:
            exog_train = self.scaler.fit_transform(exog_train)

        # Find optimal orders with auto_arima
        print(f"  Running auto_arima (m={self.seasonal_period})...")
        auto_model = pm.auto_arima(
            y_train.values,
            exogenous=exog_train,
            seasonal=True,
            m=self.seasonal_period,
            max_p=self.max_p, max_q=self.max_q, max_d=self.max_d,
            max_P=self.max_P, max_Q=self.max_Q, max_D=1,
            stepwise=True,
            suppress_warnings=True,
            error_action="ignore",
            n_fits=30,
        )

        self.order = auto_model.order
        self.seasonal_order = auto_model.seasonal_order
        print(f"  Best order: {self.order}, seasonal: {self.seasonal_order}")

        # Fit final SARIMAX
        self.model = SARIMAX(
            y_train.values,
            exog=exog_train,
            order=self.order,
            seasonal_order=self.seasonal_order,
            enforce_stationarity=False,
            enforce_invertibility=False,
        )
        self.model_fit = self.model.fit(disp=False, maxiter=200)
        self.is_fitted = True
        self._exog_cols = exog_cols

        # Metrics
        fitted = self.model_fit.fittedvalues
        mask = y_train.values > 0
        mape = float(np.mean(np.abs((y_train.values[mask] - fitted[mask]) / y_train.values[mask])) * 100)

        metrics = {
            "train_mape": mape,
            "train_mae": float(np.mean(np.abs(y_train.values - fitted))),
            "aic": float(self.model_fit.aic),
            "bic": float(self.model_fit.bic),
            "order": str(self.order),
            "seasonal_order": str(self.seasonal_order),
        }

        if X_val is not None and y_val is not None:
            exog_val = self.scaler.transform(X_val[exog_cols].values) if exog_cols else None
            forecast = self.model_fit.forecast(steps=len(y_val), exog=exog_val)
            val_mask = y_val.values > 0
            metrics["val_mape"] = float(np.mean(np.abs((y_val.values[val_mask] - forecast[val_mask]) / y_val.values[val_mask])) * 100)
            metrics["val_mae"] = float(np.mean(np.abs(y_val.values - forecast)))

        return metrics

    def predict(self, X):
        exog = None
        if self._exog_cols:
            X_df = X if isinstance(X, pd.DataFrame) else pd.DataFrame(X)
            exog = self.scaler.transform(X_df[self._exog_cols].values)
        forecast = self.model_fit.forecast(steps=len(X), exog=exog)
        return np.asarray(forecast, dtype=float)

    def predict_interval(self, X, alpha=0.05):
        exog = None
        if self._exog_cols:
            X_df = X if isinstance(X, pd.DataFrame) else pd.DataFrame(X)
            exog = self.scaler.transform(X_df[self._exog_cols].values)
        forecast = self.model_fit.get_forecast(steps=len(X), exog=exog, alpha=alpha)
        point = forecast.predicted_mean.values
        ci = forecast.conf_int(alpha=alpha)
        lower = ci.iloc[:, 0].values
        upper = ci.iloc[:, 1].values
        return point, lower, upper

    def save(self, path):
        path = Path(path)
        path.mkdir(parents=True, exist_ok=True)
        joblib.dump(self.model_fit, path / "sarimax_fit.joblib")
        joblib.dump(self.scaler, path / "scaler.joblib")
        meta = {
            "name": self.name, "resolution": self.resolution,
            "order": list(self.order), "seasonal_order": list(self.seasonal_order),
            "exog_cols": self._exog_cols, "feature_names": self.feature_names,
        }
        with open(path / "meta.json", "w") as f:
            json.dump(meta, f, indent=2)

    @classmethod
    def load(cls, path):
        path = Path(path)
        with open(path / "meta.json") as f:
            meta = json.load(f)
        forecaster = cls(resolution=meta["resolution"])
        forecaster.order = tuple(meta["order"])
        forecaster.seasonal_order = tuple(meta["seasonal_order"])
        forecaster.model_fit = joblib.load(path / "sarimax_fit.joblib")
        forecaster.scaler = joblib.load(path / "scaler.joblib")
        forecaster._exog_cols = meta["exog_cols"]
        forecaster.feature_names = meta["feature_names"]
        forecaster.is_fitted = True
        return forecaster

    def get_params(self):
        return {"name": "sarimax", "resolution": self.resolution,
                "order": str(self.order), "seasonal_order": str(self.seasonal_order),
                "m": self.seasonal_period}

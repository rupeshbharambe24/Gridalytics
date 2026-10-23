"""NeuralProphet forecaster.

NeuralProphet = Prophet-style decomposition (trend + seasonality + holidays)
with neural components, plus **future regressors** for exogenous drivers.

This version:
  * wires a configurable regressor set from the engineered feature matrix
    (`regressors="curated"` by default, or `"all"` numeric features, or an
    explicit list) instead of a hardcoded five;
  * registers Indian country holidays;
  * is robust to missing regressor columns at predict time and to the
    DatetimeIndex / freq handling for daily vs hourly;
  * conforms to BaseForecaster so it plugs into the training harness.

Note: NeuralProphet needs `torch` + `pytorch-lightning` (heavy); the import is
deferred to `fit`/`load` so the rest of the package stays importable without it.
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd

from .base import BaseForecaster

# A compact, informative default regressor set (intersected with what's present).
CURATED_REGRESSORS = [
    "temperature_2m", "relative_humidity_2m", "CDD", "HDD", "heat_index",
    "temp_squared", "aqi_value",
    "is_holiday", "is_national_holiday", "is_festival", "is_weekend",
    "is_ipl_season", "expected_event_effect_pct",
]


class NeuralProphetForecaster(BaseForecaster):
    """NeuralProphet demand forecaster with configurable future regressors."""

    def __init__(self, resolution: str = "daily", epochs: int = 100,
                 learning_rate: float = 0.01, yearly_seasonality: int = 10,
                 weekly_seasonality: int = 5, regressors="curated"):
        super().__init__(resolution=resolution, name="neuralprophet")
        self.epochs = epochs
        self.learning_rate = learning_rate
        self.yearly_seasonality = yearly_seasonality
        self.weekly_seasonality = weekly_seasonality
        self.regressors = regressors          # "curated" | "all" | list[str]
        self.model = None
        self.feature_names: list[str] = []
        self._regressor_cols: list[str] = []

    def _choose_regressors(self, X: pd.DataFrame) -> list[str]:
        if isinstance(self.regressors, (list, tuple)):
            return [c for c in self.regressors if c in X.columns]
        if self.regressors == "all":
            num = X.select_dtypes(include=[np.number])
            return [c for c in num.columns if num[c].nunique() > 1]
        return [c for c in CURATED_REGRESSORS if c in X.columns]  # "curated"

    @property
    def _freq(self) -> str:
        return "D" if self.resolution == "daily" else "h"

    def _frame(self, X: pd.DataFrame, y: pd.Series | None = None) -> pd.DataFrame:
        df = pd.DataFrame({"ds": pd.to_datetime(X.index)})
        # NeuralProphet requires a 'y' column even when predicting (NaN rows).
        df["y"] = np.asarray(y, dtype=float) if y is not None else np.nan
        for col in self._regressor_cols:
            if col in X.columns:
                df[col] = np.asarray(X[col], dtype=float)
            else:
                df[col] = 0.0
        return df

    def fit(self, X_train, y_train, X_val=None, y_val=None):
        from neuralprophet import NeuralProphet, set_log_level
        set_log_level("ERROR")

        self.feature_names = list(X_train.columns)
        self._regressor_cols = self._choose_regressors(X_train)
        print(f"  NeuralProphet regressors: {len(self._regressor_cols)} "
              f"({self.regressors if isinstance(self.regressors, str) else 'explicit'})")

        self.model = NeuralProphet(
            epochs=self.epochs,
            learning_rate=self.learning_rate,
            yearly_seasonality=self.yearly_seasonality,
            weekly_seasonality=self.weekly_seasonality,
            daily_seasonality=(self.resolution != "daily"),
            n_forecasts=1,
            n_lags=0,           # regressors + seasonality rather than autoregression
            batch_size=64,
            accelerator="auto",
        )
        try:
            self.model.add_country_holidays("IN")
        except Exception:
            pass
        for col in self._regressor_cols:
            self.model.add_future_regressor(col)

        train_df = self._frame(X_train, y_train)
        val_df = self._frame(X_val, y_val) if (X_val is not None and y_val is not None) else None
        self.model.fit(train_df, freq=self._freq, validation_df=val_df)
        self.is_fitted = True

        pred = self.model.predict(train_df)["yhat1"].to_numpy()
        yt = np.asarray(y_train, dtype=float)[:len(pred)]
        mask = (yt > 0) & ~np.isnan(pred)
        metrics = {
            "train_mape": float(np.mean(np.abs((yt[mask] - pred[mask]) / yt[mask])) * 100),
            "train_mae": float(np.nanmean(np.abs(yt - pred))),
            "n_regressors": len(self._regressor_cols),
        }
        if val_df is not None:
            fc = self.predict(X_val)
            yv = np.asarray(y_val, dtype=float)
            vm = (yv > 0) & ~np.isnan(fc)
            if vm.any():
                metrics["val_mape"] = float(np.mean(np.abs((yv[vm] - fc[vm]) / yv[vm])) * 100)
        return metrics

    def predict(self, X):
        future = self._frame(X)
        out = self.model.predict(future)["yhat1"].to_numpy()
        return np.nan_to_num(out, nan=float(np.nanmean(out)) if np.isfinite(np.nanmean(out)) else 0.0)

    def predict_interval(self, X, alpha=0.05):
        point = self.predict(X)
        return point, point * 0.93, point * 1.07

    def save(self, path):
        path = Path(path)
        path.mkdir(parents=True, exist_ok=True)
        model_path = str(path / "neuralprophet_model.np")
        # NeuralProphet >= 0.6 exposes module-level save()/load(); older
        # versions had model.save(). Try the module API first.
        try:
            from neuralprophet import save as _np_save
            _np_save(self.model, model_path)
        except (ImportError, AttributeError):
            self.model.save(model_path)
        meta = {
            "name": self.name, "resolution": self.resolution, "epochs": self.epochs,
            "yearly_seasonality": self.yearly_seasonality,
            "weekly_seasonality": self.weekly_seasonality,
            "regressor_cols": self._regressor_cols, "feature_names": self.feature_names,
        }
        with open(path / "meta.json", "w") as f:
            json.dump(meta, f, indent=2)

    @classmethod
    def load(cls, path):
        path = Path(path)
        with open(path / "meta.json") as f:
            meta = json.load(f)
        m = cls(resolution=meta["resolution"], epochs=meta["epochs"],
                regressors=meta["regressor_cols"])
        model_path = str(path / "neuralprophet_model.np")
        # torch >= 2.6 defaults torch.load(weights_only=True), which rejects the
        # NeuralProphet checkpoint. Force weights_only=False for this trusted file.
        import torch
        _orig_load = torch.load
        torch.load = lambda *a, **k: _orig_load(*a, **{**k, "weights_only": False})
        try:
            try:
                from neuralprophet import load as _np_load
                m.model = _np_load(model_path)
            except (ImportError, AttributeError):
                from neuralprophet import NeuralProphet
                m.model = NeuralProphet.load(model_path)
        finally:
            torch.load = _orig_load
        m.feature_names = meta["feature_names"]
        m._regressor_cols = meta["regressor_cols"]
        m.is_fitted = True
        return m

    def get_params(self):
        return {"name": "neuralprophet", "resolution": self.resolution,
                "epochs": self.epochs, "yearly_seasonality": self.yearly_seasonality,
                "weekly_seasonality": self.weekly_seasonality,
                "n_regressors": len(self._regressor_cols)}

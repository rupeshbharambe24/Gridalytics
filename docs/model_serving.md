# Model serving notes

## XGBoost is unusable in the current environment (xgboost 2.1.4 × scikit-learn 1.9.1)

### Symptom
Day-ahead hourly forecasts for Delhi were being logged as a **flat 500 MW** for
every hour (e.g. `prediction_log` 2026-11-23: predicted peak 500 MW vs actual
4021 MW, 85.8% MAPE), while the Accuracy page's drift status still read
"stable".

### Root cause
`XGBoostForecaster` uses `xgboost.XGBRegressor`. Under this version pair, the
sklearn-wrapper's `_estimator_type` mechanism changed and xgboost 2.1.4 trips on
it in **both** directions:

- **save** (`XGBRegressor.save_model` → `_get_type()`) raises
  `TypeError: _estimator_type undefined. Please use appropriate mixin ...`,
  so new XGBoost models cannot be written at all.
- **load** (`XGBRegressor().load_model`) raises the same error, so the registry
  skips the model (`load_models` logs "Failed to load xgboost/…").

The hourly XGBoost artifact on disk predates this and, when force-loaded past
the error, predicts ~110 MW for every input (its learned `base_score`/tree
contributions are effectively lost) — i.e. it is corrupt. The forecast engine's
old sanity clamp `np.clip(pred, 500, 12000)` then floored those ~110 values to
exactly 500, producing a plausible-looking flat line that was stored silently.

Two silent-failure layers hid it:
1. the registry swallowed the load failure, and
2. the clamp disguised a dead model's output as a "valid" 500.

### What was changed (commit on `main`)
- **`src/forecasting/future.py`** — both `forecast_future` (Delhi) and
  `forecast_state_future` now run a **collapse guard** after prediction: a day
  whose peak falls below the recent observed demand floor, or that spends >40%
  of its steps pinned to the clip floor, raises `ValueError` instead of
  returning a floored forecast. A corrupt model now fails loudly; the tracker
  records nothing rather than a lie.
- **`src/api/model_registry.py`** — `get_model` now prefers **LightGBM** over
  XGBoost as the default served model. LightGBM is the reliably-serializable
  Delhi model (hourly day-ahead peak MAPE ~1–6%); XGBoost stays reachable by
  explicit name for comparison but can never become the default by accident.
- **`src/api/routers/dashboard.py`** — the drift detector gained an **absolute**
  trigger (latest day or recent 7-day rolling MAPE over the 5% threshold)
  alongside the existing relative-trend check, so a "stably bad" model or a
  single smoothed-away spike can no longer read "stable".
- **data** — the two poisoned `prediction_log` rows (2026-11-23/24) were deleted
  and regenerated with the served LightGBM model (Nov 23: pred 3969 vs actual
  4031, 0.93% MAPE).

### State XGBoost models are fine
Audited 2026-11-24: of the 24 state models, three serve XGBoost (all_india/15min,
himachal_pradesh/15min, karnataka/hourly). All three load cleanly and forecast
correctly — they were saved *with* the `_estimator_type` field by the state
training path, so they are unaffected. The corruption is specific to the
pre-shim Delhi artifact.

The corrupt `models/hourly/xgboost/` artifact has been **removed** from the repo
(it was unloadable and predicted ~0); `models/5min/xgboost/` was an incomplete
leftover (no `meta.json`, never loaded). Regenerate them by retraining once the
environment is fixed.

### How to revive XGBoost (optional, future)
XGBoost is not required — LightGBM serves all Delhi resolutions accurately. To
bring XGBoost back:
1. Fix the environment version pair (e.g. upgrade xgboost to a build whose
   sklearn wrapper is compatible with scikit-learn ≥1.9, or pin sklearn to a
   version xgboost 2.1.4 supports). The user runs environment changes.
2. **Retrain and re-save** every XGBoost artifact (the on-disk files are
   corrupt and must be regenerated): `python -m src.training.train hourly`, etc.
3. Validate a round-trip (`save → load → predict`) returns realistic MW before
   trusting it, then decide champion by walk-forward CV as usual.

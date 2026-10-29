# CLAUDE.md

Guidance for Claude Code / AI assistants working in this repository.

## Project Overview

Gridalytics forecasts electricity demand for the **Delhi power grid** at **5-minute,
hourly, and daily** resolutions. It has a FastAPI backend, a Next.js 14 dashboard, and
an automated data pipeline (Delhi SLDC SCADA + Open-Meteo weather/AQI + Indian
holidays). Models are chosen by **champion/challenger walk-forward cross-validation**
(lowest MAPE wins), with no data leakage.

## Key Commands

```bash
# Backend deps
pip install -r requirements.txt            # or: pip install -e .

# Train (champion/challenger over LightGBM + XGBoost; add classical challengers)
python -m src.training.train hourly        # or: daily / 5min

# Run the API
uvicorn src.api.main:app --reload --port 8000

# Data collection (scheduler)
python -m src.data.scheduler [--once]

# Evaluate classical/alt models vs a LightGBM baseline
python scripts/eval_classical.py sarimax arima neuralprophet --resolution daily

# Event-effect estimator (prints the learned festival/holiday table)
python src/forecasting/event_effects.py <path-to-edfs.db>

# Frontend
cd frontend && npm install && npm run dev   # build: npm run build

# Tests
python -m pytest tests/ -v
```

## Where things live

- `config/settings.py` — Pydantic settings; `DATABASE_URL` from `.env` (sqlite
  `data/edfs.db` locally, Postgres/Supabase in production).
- `src/data/` — `scrapers/` (SLDC, Open-Meteo, AQI, holidays), `db/models.py`
  (SQLAlchemy ORM), `loaders.py` (DB → DataFrame per resolution), `scheduler.py`.
- `src/features/` — feature engineering; `pipeline.py` orchestrates temporal, weather,
  calendar, rolling (~93 features). `calendar.py` also holds the optional
  `expected_event_effect_pct` feature.
- `src/models/` — `base.py` (`BaseForecaster` interface) + `lightgbm_model.py`,
  `xgboost_model.py`, `sarimax_model.py` (SARIMAX **and** ARIMA), `neuralprophet_model.py`,
  `lstm_model.py`, `ensemble.py`.
- `src/evaluation/` — `cross_validation.py` (walk-forward CV), `metrics.py`.
- `src/forecasting/` — `future.py` (recursive day-ahead engine; supports `overrides=`
  what-if and `as_of=` leakage-free backtest), `tracker.py` (predicted vs actual),
  `event_effects.py` (learned event-effect estimator).
- `src/training/` — `train.py` (orchestrator + champion pick; `extra_models=` adds
  classical challengers), `registry.py` (MLflow), `hyperopt.py` (Optuna).
- `src/api/` — FastAPI app + routers; `model_registry.py` loads/serves models + ensemble.
- `frontend/` — Next.js 14 app-router dashboard; data layer in `src/lib/api.ts` +
  `src/lib/hooks.ts` (shared stale-while-revalidate cache).
- `scripts/` — training/eval/backfill utilities. `docs/` — design & results write-ups.
  `tests/` — pytest suite.

## Conventions

- **No data leakage.** Evaluate with walk-forward CV; never fit on future data. For
  historical backtests use `forecast_future(..., as_of=D)` so history/effect tables see
  only data before `D`.
- **New models implement `BaseForecaster`** (`fit / predict / predict_interval / save /
  load / get_params / get_feature_importance`) — they then slot into CV, training, and
  the registry/ensemble automatically.
- **Linear models (SARIMAX/ARIMA)** use only genuine exogenous drivers as `exog`; the
  `delhi_mw_*` target-history features (lag/diff/rolling) are excluded because they form
  exact linear identities that leak the target. SARIMA models the target's own
  autocorrelation via its `(p,d,q)(P,D,Q)` terms.
- **Target** is `delhi_mw`; sub-regional DISCOM columns (`brpl_mw`, `bypl_mw`, …) are
  excluded from features. At **daily** resolution it is the day's **peak** (PSP reports
  peak demand met; 5-min days are aggregated with `.max()`, never `.mean()`).
- **Known open issue — target leak:** `delhi_mw_diff_*` and the `delhi_mw_r*` rolling
  stats include the current target in training but not at inference. CV MAPEs from the
  tree models are inflated until these are shifted to end at t−1 (see
  `docs/classical_models.md`).
- **Dates:** source dates are DD-MM-YYYY — always parse with `dayfirst=True`. PSP reports
  are labelled by report date (= previous day's demand). `scripts/fix_date_integrity.py`
  repairs a DB migrated before this was handled (dry run by default).

## Documentation

- `docs/event_aware_forecasting.md` — event-effect layer design + measured results.
- `docs/classical_models.md` — SARIMAX/ARIMA (full exogenous features) + NeuralProphet.
- `docs/frontend_performance.md` — frontend load/tab-switch diagnosis + fixes.
- `docs/paper_festival_effects.md` — research-paper plan: festival demand effects, the
  data-integrity audit, feasibility results (`scripts/paper/`).
- `docs/research_angles.md` — literature-checked paper angles (partly superseded by the above).

## Git Workflow

Never push directly to `main`. Branch (`feat/…`, `fix/…`, `perf/…`), commit, push, open a PR.

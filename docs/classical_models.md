# Classical / alternative models — SARIMAX, ARIMA, NeuralProphet

**Status:** implemented + evaluated. None beats LightGBM for the one-step task;
kept as diversity / challenger / ensemble candidates.

These three models existed in `src/models/` but were orphaned — not wired into
training and (SARIMAX) using only 4 of the ~93 engineered features. This work
makes them use the engineered feature matrix and adds an eval harness so they're
actually exercised.

## What changed

- **`src/models/sarimax_model.py`** — `SARIMAXForecaster(exog="all")` now feeds the
  full engineered feature matrix as exogenous regressors (scaled, de-collinearized),
  with a fixed `(p,d,q)(P,D,Q,m)` order by default (`auto=True` enables `auto_arima`).
  **New `ARIMAForecaster`** = the non-seasonal special case (same full-exog handling).
- **`src/models/neuralprophet_model.py`** — completed + generalized: configurable
  regressors (`regressors="curated"` default / `"all"` / explicit list) instead of a
  hardcoded five; robust predict (NeuralProphet needs a `y=NaN` column at predict time);
  deferred torch import so the package stays importable without it.
- **`scripts/eval_classical.py`** — walk-forward CV harness comparing these to a
  LightGBM baseline. `python3 scripts/eval_classical.py sarimax arima neuralprophet lightgbm --resolution daily --folds 3`.

## The leakage trap we hit (and fixed)

Feeding **all** 93 features to SARIMAX first gave **0.00% MAPE** — a tell, not skill.
The feature matrix is *tree-oriented* and contains exact **linear identities**:
`delhi_mw_diff_n = delhi_mw − delhi_mw_lag_n`, so `delhi_mw = lag_n + diff_n`. A linear
model (SARIMAX/ARIMA) reconstructs the target perfectly from those columns; trees
(LightGBM) cannot exploit the identity exactly, which is why they never showed 0%.

> ⚠️ **Correction (2026-10-30): trees exploit it too, just not to 0%.** `diff_n` is computed
> from the *current* target and the `delhi_mw_r{mean,std,min,max}_*` windows include the
> current row, so every model sees y_t in its features. Walk-forward CV (LightGBM, 12 folds,
> after the date fixes): daily **1.08%** as shipped vs **3.87%** with those features shifted to
> end at t−1 (persistence: 5.05%); hourly 0.35% as shipped vs 3.43% persistence; the 5-min
> 0.18% headline sits below 5-min persistence (0.68%). Inference (`future.py`) cannot see y_t —
> it sets `diff_1 = lag_1 − lag_1 = 0` and uses windows ending before t — so there is also
> train/serve skew. The LightGBM numbers in the table below are leak-inflated; the
> exogenous-only linear models are not.

**Fix:** for linear models, exog = genuine **external drivers only** (weather, calendar,
cyclical, AQI, event) — the `delhi_mw_*` lag/diff/rolling columns are excluded
(`exclude_target_history=True`). SARIMA already models the target's own autocorrelation
via its `(p,d,q)(P,D,Q)` terms, so feeding its own lags is both leaky and redundant.
After the fix SARIMAX uses **66 of 100** features and behaves sanely.

## Measured results (real `edfs.db`, daily, last 3 walk-forward folds)

| Model | Mean CV MAPE | MAE | Feature use | Fit time (3 folds) |
|---|---|---|---|---|
| **LightGBM** (champion) | **0.87%** | 50 MW | full tree features incl. target lags | 114 s |
| NeuralProphet | 5.84% | 344 MW | 13 curated regressors + IN holidays + seasonality | 91 s |
| SARIMAX | 8.06% | 474 MW | 66 exogenous drivers + (2,1,2)(1,0,1,7) | 277 s |
| ARIMA | 8.37% | 488 MW | 66 exogenous drivers, non-seasonal | 24 s |

**Read:** in one-step CV the tree's target-lags dominate (`lag_1` ≈ the answer), so the
exogenous-only linear/decomposition models can't match it. That does **not** make them
useless — they bring modelling diversity (SARIMA's explicit autocorrelation,
NeuralProphet's trend/seasonality/holiday decomposition) and are natural **ensemble
members** and **challenger baselines**. ARIMA is ~10× faster than seasonal SARIMAX for
nearly the same accuracy.

## Suggested next steps (not done here)
- Add these to `train.py` / `src/api/model_registry.py` as optional challengers, or to
  `EnsembleForecaster`, rather than the LGB-vs-XGB champion race (they're slower and
  weaker alone). Keep them opt-in given the fit-time cost.
- SARIMAX/ARIMA on `hourly` is feasible but slow (MLE over ~60 exog × 20k rows); evaluate
  only if the diversity proves worth it in an ensemble.

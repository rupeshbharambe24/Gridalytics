# Event-Aware Forecasting — Design & Plan

**Status:** proposal / tested (Idea 1 Phase 1–1.5 complete; verdict below)

> ⚠️ **Correction (2026-10-30).** The magnitudes and the "neutral" verdict below were measured
> on corrupted data: `psp_daily` 2015–2020 was dated one day late, legacy 5-min rows had
> day/month swapped, Holi was missing from the calendar, and weather before 2021 was absent.
> Fixed by `scripts/fix_date_integrity.py`. On corrected data the effects are much larger
> (Holi ≈ −31%, Diwali ≈ −17% with −19%/−12% on the next two days, Republic Day ≈ −14%,
> Id-ul-Fitr ≈ 0 rather than +3%), and a causal magnitude feature *does* cut festival-day error
> in a leak-free daily backtest (h=7: 9.5% → 7.1%). The CV A/B and the hourly recursive backtest
> remain uninformative until the target leak in `delhi_mw_diff_*`/rolling features is fixed
> (see `docs/classical_models.md`). Details: `docs/paper_festival_effects.md`.
**Owner:** Rupesh Bharambe
**Scope:** two complementary features that make Gridalytics forecasts react to real-world events
(festivals, holidays, and ad-hoc happenings), grounded in historically-measured demand impact.

- **Idea 1 — Counterfactual Event-Effect Layer** (learns *how much* each event moves demand)
- **Idea 2 — LLM Event-Detection Agent** (detects *which* events are coming, including novel ones)

They compose: Idea 2 finds the events, Idea 1 supplies the numbers. Neither the LLM nor the event
flag ever touches a prediction directly — they only set **features** the existing models consume.

---

## 0. Context — what the system already does

- **Champion/challenger retraining** (`src/training/train.py`): each retrain runs walk-forward CV
  for LightGBM vs XGBoost, logs to MLflow, picks the champion by lowest mean CV MAPE.
- **Event/holiday features already exist** (`src/features/calendar.py`): `is_holiday`,
  `is_national_holiday`, `is_festival`, `is_ipl_season`, `days_to/since_holiday`,
  `is_pre/post_holiday`, plus AQI flags — all read from the `holidays` table (`HolidayRecord`).
- **Holiday source** (`src/data/scrapers/holidays.py`): `holidays` lib for national holidays +
  **hardcoded `FESTIVALS_BY_YEAR` / `IPL_SEASONS` dicts that stop at 2026** → the system goes
  blind to festivals after 2026.
- **Residual store exists** (`src/forecasting/tracker.py`): `prediction_log` (daily) and
  `prediction_log_hourly` (per-hour predicted vs actual) tables.
- **What-if already works**: `forecast_future(..., overrides=...)` can force `temperature`,
  `humidity`, `is_holiday`, `aqi`.

**Takeaway:** we already have both halves needed — a baseline forecaster and a residual/actuals
store. These two ideas are extensions, not a rebuild.

---

## 1. Data reality (measured, not assumed)

Source DB: `data/edfs.db` (local SQLite; `.env` → `DATABASE_URL=sqlite:///./data/edfs.db`).

| Table | What | Period | Coverage |
|---|---|---|---|
| `demand_5min` | SCADA load, Delhi + 5 DISCOMs, 5-min | 2021-01-01 → 2026-10-03 | **sparse — ~905 distinct days** |
| `weather_hourly` | Open-Meteo, 7 vars, hourly | 2021-01-01 → 2026-10-10 | ~complete |
| `psp_daily` | Grid-India daily peak/energy | **2015-01-01 → 2024-11-20** | **continuous (~10 yrs)** |
| `aqi_daily` | Open-Meteo AQI | 2025-03-30 → 2026-10-03 | daily |
| `holidays` | calendar/festivals | 2015 → 2027 | reference |

**Critical finding for event modeling:** the 5-minute demand is too sparse to learn event effects.
Of 114 festival/holiday dates in the 5-min range, only ~24 are usable. That tiny sample is actively
misleading — e.g. Gandhi Jayanti measures −23% on the 5-min scraps but +1.9% on the 10-year daily
series. So:

> **Learn event-effect magnitudes on `psp_daily` (10 years, complete), not on `demand_5min`.**

### Measured daily effects (psp_daily 2015–2024, same-DOW weather-adjusted baseline)

| Event | Shrunk effect | Years |
|---|---|---|
| Diwali | **−10.5%** | 10 |
| Good Friday | −9.0% | 8 |
| Dussehra | −4.5% | 10 |
| Republic Day | −3.9% | 10 |
| Independence Day | −3.6% | 9 |
| **Id-ul-Fitr** | **+3.0%** | 8 |
| IPL season | +2.4% | 13–14 |

Note the **sign** varies: Diwali/Good Friday drop demand, Eid/Christmas raise it. A single binary
`is_festival` flag cannot express that — which is the premise a signed feature was meant to exploit.

---

## 2. Idea 1 — Counterfactual Event-Effect Layer

### 2.1 What we want
A learned table of **event effects**: for each event (and tier), how much demand deviates from the
"normal" counterfactual. The models get this as a feature (`expected_event_effect_pct`) so forecasts
bend on Diwali, Holi, Eid, etc. instead of predicting a normal day.

### 2.2–2.4 Method (implemented in `src/forecasting/event_effects.py`)
- **Counterfactual baseline, weather-adjusted:** same-day-of-week non-holiday days within ±21 days,
  fit demand~temp, evaluate at the event day's temperature.
- **Causality / no leakage:** `estimate_effects(as_of=D)` and `causal_effect_feature` use only
  occurrences strictly before each point (expanding window).
- **Pooling + shrinkage:** tiers (major_festival / national / minor_festival / sporting), shrink
  each event toward its tier mean by `n/(n+k)`.

### 2.5 Where it plugs into the codebase (DONE)
- `src/forecasting/event_effects.py` — estimator + `EventEffectTable.get_effect` + the causal
  training feature `causal_effect_feature`.
- `src/features/calendar.py::add_event_effect_feature` → called from `FeaturePipeline.build`
  (training), gated by `FeaturePipeline(..., include_event_effect=True)`.
- `src/forecasting/future.py::_event_effect_for_date` → `_build_row` (inference); only computed
  when the model's feature_names include the column; `is_holiday=0` override zeroes it.
- `forecast_future(..., as_of=D)` — leakage-free history + effect table, for backtesting.
- Both paths fail safe to 0.

### 2.6 Phases & status
- **Phase 1 — DONE.** Daily estimator on `psp_daily`. Run: `python3 src/forecasting/event_effects.py <db>`.
- **Phase 1.5 — DONE + TESTED.** Feature wired into training + inference. Two leakage-free tests:
  - **Walk-forward CV A/B** (`scripts/ab_event_effect.py`): **neutral**. daily 1.29%→1.29%,
    hourly 0.43%→0.43%; importance rank #64/100 and #70/94. CV is the *wrong gate* — it scores
    one-step-ahead with the true lag columns present, which already encode the event.
  - **Recursive day-ahead backtest** (`scripts/backtest_event_effect.py`, train <2026 / test 2026,
    `forecast_future(as_of=D)`): **marginal and not event-specific.** Event-day MAPE 14.25%→14.12%
    (Δ−0.13%), normal-day 17.92%→17.64% (Δ−0.28%). Normal days (where the feature is exactly 0)
    improved *more* than event days → the change is global model-perturbation noise, not a real
    event signal.
  - **Verdict: do NOT ship into the champion.** The existing binary holiday flags already capture
    the available event signal; a signed daily magnitude is redundant, and day-ahead error (14–31%)
    is dominated by lag-fallback under 5-min sparsity + 2025→2026 regime shift, not event mis-sizing.
    The feature stays implemented behind `include_event_effect` (default on in the pipeline, but not
    worth enabling for the champion on current evidence).
- **Phase 2 — the only lever with upside:** festivals reshape the **intraday profile** (evening
  peak), which neither a daily scalar nor `is_festival` can express. Needs a 5-min backfill around
  event dates (current 5-min too sparse). Bigger bet; scope before committing.

#### Bug caught during testing (fixed)
The first A/B showed 0 event-days in validation: the training feature only emitted values for dates
present in `psp_daily` (ends 2024-11), while CV folds sit in 2024-11→2026. `causal_effect_feature`
now assigns the prior-year estimate to **every** event occurrence (incl. 2025–26 festivals), so
recent event days carry the learned magnitude. Without this fix the A/B was silently blind.

---

## 3. Idea 2 — LLM Event-Detection Agent

### 3.1 What we want
A weekly agent that, before the forecast/retrain, fetches **upcoming events** in the forecast window
and writes them as structured rows the feature pipeline already consumes.

### 3.2 Why — and what's genuinely new
- Recurring national holidays: already handled by the `holidays` lib.
- Recurring festivals/IPL: handled, **but hardcoded through 2026** → maintenance liability.
- **Additive value:** (a) auto-maintain the festival calendar past 2026 (lunar dates shift yearly);
  (b) catch **ad-hoc, non-calendar events** — a cricket final, a big concert/rally, an IMD
  heatwave/cold-wave advisory, GRAP pollution curbs, a strike.

> **Re-scoped after Idea 1's result:** Idea 2's value was partly "feed magnitudes from Idea 1."
> Since those magnitudes don't move accuracy, Idea 2 is best framed as a **calendar-freshness +
> ad-hoc-event coverage** tool, not a magnitude-driven accuracy lever.

### 3.3 How it works
1. Weekly (≤16-day window to match Open-Meteo's horizon), an LLM with web search pulls upcoming events.
2. Emits **structured, schema-validated JSON**:
   `{date, event_type, affects_demand, direction, est_magnitude, confidence, source_url}`.
3. Validated rows → `holidays`/a new `events` table → consumed by the existing feature pipeline.

### 3.4 Guardrails
- LLM sets features only, never predictions. Require `source_url`; confidence threshold; idempotent.
- Graceful fallback to calendar features on error. Human review for high-impact/low-confidence.

### 3.5 Where it plugs in
- New: `src/data/scrapers/event_llm.py` — fetch → validate → upsert. Wire into the weekly scheduler.

---

## 4. Combined roadmap

| Phase | Deliverable | Status |
|---|---|---|
| **1** | Daily event-effect estimator (`event_effects.py`) + fitted table | DONE |
| 1.5 | `expected_event_effect_pct` feature + CV A/B + recursive backtest | DONE — neutral, not shipped |
| 2 | 5-min backfill around events → intraday event shapes | open (only lever with upside) |
| 3 | LLM event-detection agent → calendar freshness + ad-hoc events | open |

---

## 5. Open questions
- Phase 2 feasibility/cost of SLDC 5-min backfill around event dates (the gate for intraday shape).
- Event tiers: the "major_festival" tier is behaviorally heterogeneous (Diwali −, Eid +); per-event
  estimates with 7–14 yrs are usually trusted over the tier mean anyway.
- Inference matches events by exact name then tier; a festival-name normalization would harden the
  fallback (e.g. "Deepavali" vs "Diwali").

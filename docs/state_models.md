# State models — the all-India fleet

**Status (Nov 2026).** Beyond Delhi's three resolutions, Gridalytics serves **24 curated
state & national demand models**, each the champion of its own leak-free walk-forward
contest and **each beating the persistence baseline**. The set is deliberately curated:
`train_state.py` saves every champion it trains (and `served.json` flags the ones that lose
to persistence), but only models that genuinely beat "tomorrow = today" are served on `main`.

| Model | Region | Resolution | Source | Champion CV MAPE | Persistence | Gain | Notes |
|---|---|---|---:|---:|---:|---:|---|
| All-India | national | 15-min | SLDC | **0.28%** | 0.72% | 61% | one model, whole-country 15-min series |
| Haryana | Northern | daily peak | PSP | **4.31%** | 9.85% | 56% | NCR load centre |
| Himachal Pradesh | Northern | 15-min | HPSLDC | **0.92%** | 1.91% | 52% | 2017→, 335k rows |
| Karnataka | Southern | hourly | KPTCL | **2.38%** | 4.71% | 50% | back-extended to 2011 (138k rows) |
| Sikkim | Eastern | daily peak | PSP | **6.41%** | 12.68% | 49% | tiny grid (~95 MW peak) |
| Tamil Nadu | Southern | daily peak | PSP | **2.99%** | 5.66% | 47% | |
| Chandigarh | Northern | daily peak | PSP | **3.54%** | 6.72% | 47% | UT |
| Uttarakhand | Northern | daily peak | PSP | **3.32%** | 6.24% | 47% | |
| Puducherry | Southern | daily peak | PSP | **3.09%** | 5.51% | 44% | UT |
| Bihar | Eastern | hourly | BSPTCL | **1.56%** | 2.72% | 43% | TLS via pinned CA (verify on) |
| Punjab | Northern | daily peak | PSP | **4.54%** | 7.32% | 38% | **festival event-effect feature** |
| Uttar Pradesh | Northern | daily peak | PSP | **3.54%** | 5.37% | 34% | |
| Assam | North-Eastern | daily peak | PSP | **3.50%** | 5.33% | 34% | |
| Andhra Pradesh | Southern | daily peak | PSP | **2.98%** | 4.19% | 29% | |
| Maharashtra | Western | daily peak | PSP | **2.62%** | 3.71% | 29% | |
| Mizoram | North-Eastern | daily peak | PSP | **5.60%** | 7.73% | 28% | small NE grid |
| Manipur | North-Eastern | daily peak | PSP | **4.81%** | 6.34% | 24% | |
| Kerala | Southern | daily peak | PSP | **3.17%** | 4.06% | 22% | |
| Meghalaya | North-Eastern | daily peak | PSP | **3.25%** | 4.10% | 21% | |
| Jammu & Kashmir | Northern | daily peak | PSP | **3.27%** | 4.07% | 19% | |
| Chhattisgarh | Western | daily peak | PSP | **2.41%** | 2.99% | 19% | direct HTML scraper exists |
| Goa | Western | daily peak | PSP | **2.51%** | 2.96% | 15% | |
| West Bengal | Eastern | daily peak | PSP | **3.12%** | 3.64% | 14% | |
| Odisha | Eastern | daily peak | PSP | **3.98%** | 4.12% | 3% | only beats persistence with lag-365 dropped |

All twenty-four are served by **LightGBM**. For the all-India and Karnataka models XGBoost is the
CV champion but can't be pickled under xgboost 2.1.4 / sklearn 1.9 (`_estimator_type` on
save), so the near-tied LightGBM is served; `served.json` records both.

The nine most recent daily models (Haryana, Chandigarh, Uttarakhand, Puducherry, Assam,
Kerala, Jammu & Kashmir, Chhattisgarh, Goa) came from a **Nov 2026 fleet-expansion sweep** of
previously-untried PSP series on the dense 2021-05→ span, each with Open-Meteo weather at a new
load-centre city (`train_state.STATE_COORDS`). Of the ten states swept, nine beat persistence;
**Jharkhand** was the only one that did not (−0.19 pts) and is not served.

A **second sweep** then added four small Eastern/North-Eastern grids — **Sikkim, Mizoram,
Manipur, Meghalaya** — on the same span and method. Of the seven states swept, four beat
persistence; **Tripura** (−10 pts), **Nagaland** (−8 pts) and **Dadra & Nagar Haveli / Daman &
Diu** (marginal +1 pt, and its point forecast slipped just outside its own prediction band) are
not served. Sikkim is a useful illustration of why the baseline matters: its 6.41% MAPE is the
fleet's highest, but on a ~95 MW grid where "tomorrow = today" misses by 12.7%, that is still a
49% improvement.

## How they are trained

`scripts/train_state.py <state> [--resolution hourly | --source psp]` runs the **same
leak-free pipeline as Delhi** (reusing `src/features/*`):

- **Features** — lags, diffs and rolling stats ending strictly at **t−1**; cyclical +
  Fourier seasonality; calendar/holiday/festival flags; Open-Meteo weather at one
  load-centre city per state (`STATE_COORDS`). Daily models use the day's mean weather
  (precipitation summed).
- **Champion/challenger** — LightGBM vs XGBoost under **walk-forward CV, 12 folds** (daily:
  365-day min train / 30-day val; hourly: 720h / 168h; 15-min: 672-step val).
- **Baseline** — persistence (`y[t−1]`), scored on the *same* validation rows. A model is
  served only if its CV MAPE beats it.

Two tracks:

| Track | Target | Source table |
|---|---|---|
| sub-daily (`--resolution 15min/hourly`) | mean demand (MW) | `state_demand` (SLDC scrapers / history backfills) |
| daily (`--source psp`) | day's **peak demand met** (MW) | `state_psp_daily` (Grid-India NLDC PSP) |

`scripts/retrain_all.py` is the single source of truth for *how* each model is trained
(source, span, and the flags below) and drives the weekly retrain.

## Two per-state experiments

**`--no-lag365` (Odisha).** The daily lag set includes `y[t−365]`, which costs each series its
first year to lag warm-up. On short, drift-heavy PSP series this yearly lag can add more noise
than signal. Dropping it (the yearly signal survives in `fourier_365` + month/day-of-year
cyclicals) and recovering ~a year of training rows flipped **Odisha** from losing to
persistence to beating it (3.98% vs 4.12%). It did **not** rescue the other four daily losers
(Madhya Pradesh, Gujarat, Telangana, Rajasthan), which stay unserved.

**`--event-effect` (Punjab).** Beyond the binary `is_festival` flag, this adds
`expected_event_effect_pct` — the **signed, learned magnitude** of each festival's demand
impact, estimated causally (expanding window, strictly-prior occurrences) from the state's own
daily-peak series, so it's leak-free in CV and computed identically at serve time. An ablation
across 12 states found it clearly helps only **Punjab** (+0.18 pts, 4.72→4.54%; it learns e.g.
Diwali ≈ −10%, Holi ≈ −7% peak demand) — elsewhere the effect is within fold noise or slightly
negative (it hurts Odisha), so it's applied to Punjab alone.

## Serving

`GET /api/v1/states/{code}/forecast` runs the recursive engine
(`src/forecasting/future.py::forecast_state_future`) over a state's champion model: the
state's own history + load-centre weather, non-chained lags with a seasonal-naive fallback so
sub-daily forecasts keep real diurnal shape, and a data-driven sanity clamp. The `/states`
dashboard view renders a model card per resolution plus the day-ahead forecast chart.

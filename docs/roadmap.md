# Gridalytics Roadmap — forecasting India, state by state

**Goal:** demand forecasting for every Indian state/UT grid, on one pipeline. We started with the
Delhi grid, generalised the pipeline to any state, and now onboard states as their data comes online.

Status legend: ✅ done · 🔄 in progress · ⬜ planned. Current `main` reflects everything marked ✅/🔄.

---

## Where we are today

- **36 states/UTs mapped** in one registry (`src/data/scrapers/states.py`) — region, DISCOMs, data
  source, scraper, tier.
- **2 states modelled:** **Delhi** (daily / hourly / 5-min) and **Karnataka** (hourly).
- **State-wise API + dashboard** live (`/api/v1/states`, `/states` page) showing every state's status.
- All numbers leak-free and reported against a persistence baseline.

| | Count | Detail |
|--|--:|--|
| States/UTs mapped | 36 | full registry |
| Modelled | 2 | Delhi, Karnataka |
| Collecting data | 2 | Delhi, Karnataka |
| Direct scrapers built | 6 | Delhi, Bihar, Punjab, Uttar Pradesh, Karnataka, Chhattisgarh |
| National fallback (Grid-India PSP) | 29 | code ready; needs the collector to run |
| Deferred (access-gated) | 1 | Gujarat |
| DISCOM-level capable | 3 | Delhi, Bihar, Karnataka |

---

## Phases

### ✅ Phase 0 — Foundation (Delhi)
Multi-resolution forecasting (5-min / hourly / daily), champion/challenger walk-forward CV, FastAPI
backend, Next.js dashboard, automated collection. Leak-free features + honest persistence baselines.

### ✅ Phase 1 — Multi-state framework
- `states.py` registry of all 36 states/UTs.
- Per-state scrapers (`state_sldc.py`) + Grid-India PSP fallback (`state_fallback.py`).
- Long-format storage (`state_demand`, `state_demand_discom`, `state_psp_daily`) + Alembic migrations.
- State-generic trainer (`scripts/train_state.py`) and collector CLI (`scripts/collect_states.py`).
- States API + `/states` dashboard with per-state analysis.

### 🔄 Phase 2 — First states beyond Delhi
- ✅ **Karnataka** — hourly model (XGBoost 2.46% vs 4.70% persistence), DISCOM-level source.
- 🔄 **Bihar · Punjab · Uttar Pradesh · Chhattisgarh** — scrapers built; onboard each once it has enough
  stored history. Bihar & Punjab need `SLDC_INSECURE_TLS=true` (old gov TLS); Bihar/Karnataka are
  DISCOM-level. Recipe below.

### ⬜ Phase 3 — National fallback live (the other 29 states)
Run the Grid-India daily-PSP collector so every remaining state gets a **daily** state-total model.
Gating: `report.grid-india.in` must be reachable from the run host (it was unreachable from the dev
machine); then schedule the nightly PSP job and train daily models per state.

### ⬜ Phase 4 — Live per-state forecasts
Generalise the recursive forecast engine (`src/forecasting/future.py`, currently Delhi-specific) so the
states API serves **day-ahead forecasts** per state, not just status + history + trained-model metrics.

### ⬜ Phase 5 — Depth & fidelity
- More DISCOM-level states where the source allows; deeper historical backfills.
- Higher resolution where a state exposes it (sub-hourly beyond Delhi/Bihar).
- Gujarat (deferred) once its source access is sorted.
- Intraday event/festival shapes; per-state weather at the right load centre.

---

## How to onboard a new state

```bash
# 1. Collect its data into state_demand
python scripts/collect_states.py --states <code>           # live poll (snapshot states)
#    (states with a history source, e.g. Karnataka's load-curve, backfill a date range)

# 2. Train — same leak-free pipeline + champion/challenger CV vs persistence
python scripts/train_state.py <code> --resolution hourly
```

The model saves to `models/states/<code>/<resolution>/` and the `/states` dashboard flips the state to
"model trained" automatically. Add the state's load-centre coordinates to `STATE_COORDS` in
`scripts/train_state.py` so weather features are included.

Full per-state source map and scrape methods: **[state_grid_data_sources.md](state_grid_data_sources.md)**.

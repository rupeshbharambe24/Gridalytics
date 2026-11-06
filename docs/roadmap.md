# Gridalytics Roadmap — forecasting India, state by state

**Goal:** demand forecasting for every Indian state/UT grid, on one pipeline. We started with the
Delhi grid, generalised the pipeline to any state, and now onboard states as their data comes online.

Status legend: ✅ done · 🔄 in progress · ⬜ planned. Current `main` reflects everything marked ✅/🔄.

---

## Where we are today

- **36 states/UTs mapped** in one registry (`src/data/scrapers/states.py`) — region, DISCOMs, data
  source, scraper, tier.
- **33 states/UTs modelled:** a daily peak-demand model for every state/UT in the Grid-India PSP, plus
  hourly models for **Karnataka, Bihar, Himachal Pradesh** and Delhi's own 5-min/hourly/daily models.
  Results: [state_models.md](state_models.md).
- **State-wise API + dashboard** live (`/api/v1/states`, `/states` page) showing every state's status.
- All numbers leak-free and reported against a persistence baseline.

| | Count | Detail |
|--|--:|--|
| States/UTs mapped | 36 | full registry |
| Modelled — daily peak (PSP) | 33 | all but Ladakh (inside J&K's row), Andaman & Nicobar, Lakshadweep |
| Modelled — hourly | 4 | Delhi (+5-min), Karnataka, Bihar, Himachal Pradesh |
| Direct scrapers built | 9 | Delhi, Bihar, Punjab, UP, Karnataka, Chhattisgarh, Gujarat, Maharashtra, Himachal |
| Daily PSP collection | 33 | energymap mirror + official NLDC PDF fill, nightly |
| No data | 3 | Ladakh (separately), Andaman & Nicobar, Lakshadweep |
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
- ✅ **Hourly models:** Karnataka 2.33% vs 4.79% persistence, Himachal 1.75% vs 4.45%, Bihar 1.81% vs 2.77%.
- 🔄 **Punjab · Uttar Pradesh · Chhattisgarh · Gujarat · Maharashtra** — live scrapers work (TLS verified,
  no `SLDC_INSECURE_TLS`); they need the scheduler running to accumulate sub-daily history before an
  hourly model. Recipe below.

### ✅ Phase 3 — National fallback live
Daily PSP for 33 states/UTs (energymap mirror + official NLDC PDF fill for J&K, DNH&DD, MP, UP), collected
nightly by the scheduler; a daily peak model per state. 29/33 beat persistence; MP, Bihar, Andhra and
Odisha do not yet — serve persistence there until improved ([state_models.md](state_models.md)).

### ⬜ Phase 4 — Live per-state forecasts
Generalise the recursive forecast engine (`src/forecasting/future.py`, currently Delhi-specific) so the
states API serves **day-ahead forecasts** per state, not just status + history + trained-model metrics.

### ⬜ Phase 5 — Depth & fidelity
- More DISCOM-level states where the source allows; deeper historical backfills.
- Higher resolution where a state exposes it (sub-hourly beyond Delhi/Bihar).
- Regional holiday calendars; multi-point weather for large states.
- Intraday event/festival shapes; per-state weather at the right load centre.

---

## How to onboard a new state

```bash
# 1. Collect its data into state_demand
python scripts/collect_states.py --states <code>           # live poll (snapshot states)
#    (states with a history source, e.g. Karnataka's load-curve, backfill a date range)

# 2. Train — same leak-free pipeline + champion/challenger CV vs persistence
python scripts/train_state.py <code> --resolution hourly
#    or, daily peak from the PSP table:
python scripts/train_state.py <code> --source psp
```

The model saves to `models/states/<code>/<resolution>/` and the `/states` dashboard flips the state to
"model trained" automatically. Add the state's load-centre coordinates to `STATE_COORDS` in
`scripts/train_state.py` so weather features are included.

Full per-state source map and scrape methods: **[state_grid_data_sources.md](state_grid_data_sources.md)**.

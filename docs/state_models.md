# State models — every state/UT with data

**Status (Nov 2026):** 36 models trained across **33 states/UTs**. That is a **daily peak-demand** model
for each of the 33 with Grid-India PSP data, plus **hourly** models for the three states with a deep
sub-daily history (Karnataka, Bihar, Himachal Pradesh). The three states/UTs left are
Ladakh (no separate series; it is inside J&K's row), Andaman & Nicobar and Lakshadweep (not in the PSP).

The headline result:
- **Hourly** models beat persistence by **35–61%**.
- **Daily-peak** models beat it in 29 of 33 states. The median gain is about +20%, and it is small in
  several states.
- In **four states** the daily model is *worse* than "tomorrow's peak = today's peak": Madhya Pradesh,
  Bihar, Andhra Pradesh and Odisha.

## How they are trained

`scripts/train_state.py <state> [--resolution hourly | --source psp]` uses the same leak-free pipeline
as Delhi:
- **Features:** lags, diff and rolling stats ending at t−1; calendar and holidays; Open-Meteo weather.
- **Champion/challenger:** LightGBM vs XGBoost under walk-forward CV with 12 folds:
  - daily: 365-day minimum train, 30-day validation;
  - hourly: 720-hour minimum train, 168-hour validation.
- **Baselines** are scored on the *same* validation rows:
  - **persistence:** y[t−1];
  - **seasonal-naive:** y[t−24] hourly, y[t−7] daily.

| Track | Target | Source |
|---|---|---|
| hourly | hourly mean demand (MW) | `state_demand` (SLDC scrapers / history backfills) |
| daily (`--source psp`) | day's **peak demand met** (MW) | `state_psp_daily` (Grid-India NLDC PSP) |

**Gaps.** The series is put on a regular grid.
- Short gaps are interpolated in time: at most **3 hours** (hourly) or **2 days** (daily).
- Longer gaps stay empty. Any row whose target or lag falls in one is dropped, so no value is fabricated.
- The daily lag set includes **y[t−365]**, so each series loses its first year. Sparse pre-2021 Wayback
  PSP rows rarely contribute, which is why most daily models train on mid-2021/2022 onward.

**Weather.** Open-Meteo at one load-centre city per state (`STATE_COORDS`). Daily models use the day's
mean, with precipitation summed.

`served.json` beside each model records:
- the served model and the CV MAPE of every challenger;
- both baselines and the skill vs persistence;
- the data span and row count, and how many rows were interpolated.

`scripts/summarize_state_models.py` prints the table below.

## Results

*skill* = 1 − model MAPE / persistence MAPE (positive = better than persistence). *data* = span of
rows actually used after lag warm-up. MAPE is for the **served** model. Karnataka hourly's champion is
XGBoost (2.31%), but its save hits the known xgboost×sklearn bug, so LightGBM (2.33%) is served.

| state | region | resolution | source | data | rows | served | cv_mape | persistence | seasonal_naive | skill |
|---|---|---|---|---|---|---|---|---|---|---|
| Bihar | Eastern | daily | psp | 2021-06-24 – 2026-10-29 | 1677 | LightGBM | 3.76% | 3.28% | 7.30% | -15% |
| Jharkhand | Eastern | daily | psp | 2021-06-24 – 2026-10-29 | 1676 | LightGBM | 3.72% | 3.73% | 5.34% | +0% |
| Odisha | Eastern | daily | psp | 2022-03-02 – 2026-10-29 | 1632 | LightGBM | 3.82% | 3.73% | 7.67% | -2% |
| Sikkim | Eastern | daily | psp | 2021-06-24 – 2026-10-29 | 1677 | LightGBM | 6.31% | 9.80% | 9.98% | +36% |
| West Bengal | Eastern | daily | psp | 2021-06-24 – 2026-10-29 | 1677 | LightGBM | 3.02% | 4.15% | 7.59% | +27% |
| Arunachal Pradesh | North-Eastern | daily | psp | 2021-06-24 – 2026-10-29 | 1677 | LightGBM | 4.25% | 4.78% | 6.67% | +11% |
| Assam | North-Eastern | daily | psp | 2021-06-24 – 2026-10-29 | 1677 | LightGBM | 3.55% | 5.18% | 6.97% | +32% |
| Manipur | North-Eastern | daily | psp | 2021-06-24 – 2026-10-29 | 1677 | LightGBM | 4.62% | 4.97% | 6.09% | +7% |
| Meghalaya | North-Eastern | daily | psp | 2022-05-09 – 2026-10-29 | 1629 | LightGBM | 3.23% | 4.58% | 4.33% | +29% |
| Mizoram | North-Eastern | daily | psp | 2021-06-24 – 2026-10-29 | 1677 | LightGBM | 5.59% | 8.79% | 7.45% | +36% |
| Nagaland | North-Eastern | daily | psp | 2021-06-24 – 2026-10-28 | 1676 | LightGBM | 4.59% | 5.59% | 5.52% | +18% |
| Tripura | North-Eastern | daily | psp | 2021-06-24 – 2026-10-29 | 1677 | LightGBM | 4.49% | 5.64% | 9.45% | +20% |
| Chandigarh | Northern | daily | psp | 2021-06-24 – 2026-10-28 | 1676 | LightGBM | 3.63% | 6.46% | 10.27% | +44% |
| Delhi | Northern | daily | psp | 2021-06-24 – 2026-10-29 | 1677 | LightGBM | 3.29% | 4.83% | 9.94% | +32% |
| Haryana | Northern | daily | psp | 2021-06-24 – 2026-10-29 | 1677 | LightGBM | 4.25% | 6.15% | 9.76% | +31% |
| Himachal Pradesh | Northern | daily | psp | 2017-07-10 – 2026-10-29 | 3271 | LightGBM | 3.72% | 4.65% | 4.95% | +20% |
| Jammu & Kashmir | Northern | daily | psp | 2022-05-16 – 2026-11-04 | 1628 | LightGBM | 3.27% | 3.32% | 5.12% | +2% |
| Punjab | Northern | daily | psp | 2021-06-24 – 2026-10-29 | 1677 | LightGBM | 4.80% | 5.39% | 10.91% | +11% |
| Rajasthan | Northern | daily | psp | 2021-06-24 – 2026-10-29 | 1677 | LightGBM | 2.72% | 2.90% | 6.90% | +6% |
| Uttar Pradesh | Northern | daily | psp | 2022-05-16 – 2026-11-04 | 1634 | LightGBM | 3.54% | 3.64% | 7.61% | +3% |
| Uttarakhand | Northern | daily | psp | 2021-06-24 – 2026-10-29 | 1677 | LightGBM | 3.38% | 4.51% | 6.01% | +25% |
| Andhra Pradesh | Southern | daily | psp | 2021-06-24 – 2026-10-29 | 1677 | LightGBM | 3.00% | 2.85% | 6.62% | -5% |
| Karnataka | Southern | daily | psp | 2022-05-09 – 2026-10-29 | 1629 | LightGBM | 3.54% | 4.71% | 6.32% | +25% |
| Kerala | Southern | daily | psp | 2021-06-24 – 2026-10-29 | 1677 | LightGBM | 3.22% | 4.01% | 4.87% | +20% |
| Puducherry | Southern | daily | psp | 2021-06-24 – 2026-10-29 | 1677 | LightGBM | 3.12% | 4.58% | 4.88% | +32% |
| Tamil Nadu | Southern | daily | psp | 2021-06-24 – 2026-10-29 | 1677 | LightGBM | 2.92% | 4.89% | 4.49% | +40% |
| Telangana | Southern | daily | psp | 2016-12-31 – 2026-10-29 | 3026 | LightGBM | 3.46% | 3.59% | 6.79% | +4% |
| Chhattisgarh | Western | daily | psp | 2021-06-24 – 2026-10-28 | 1676 | LightGBM | 2.42% | 2.52% | 5.69% | +4% |
| Dadra & Nagar Haveli and Daman & Diu | Western | daily | psp | 2023-06-01 – 2026-11-04 | 1253 | LightGBM | 2.40% | 3.29% | 3.38% | +27% |
| Goa | Western | daily | psp | 2021-06-24 – 2026-10-29 | 1677 | LightGBM | 2.55% | 3.74% | 4.18% | +32% |
| Gujarat | Western | daily | psp | 2021-06-24 – 2026-10-29 | 1677 | LightGBM | 3.40% | 4.12% | 7.28% | +17% |
| Madhya Pradesh | Western | daily | psp | 2021-06-24 – 2026-11-04 | 1682 | LightGBM | 2.59% | 2.24% | 6.13% | -16% |
| Maharashtra | Western | daily | psp | 2022-03-02 – 2026-10-29 | 1638 | LightGBM | 2.56% | 2.98% | 4.07% | +14% |
| Bihar | Eastern | hourly | state_demand | 2023-07-01 – 2026-10-31 | 18128 | LightGBM | 1.81% | 2.77% | 6.81% | +35% |
| Himachal Pradesh | Northern | hourly | state_demand | 2017-05-01 – 2026-10-31 | 79069 | LightGBM | 1.75% | 4.45% | 6.37% | +61% |
| Karnataka | Southern | hourly | state_demand | 2015-01-31 – 2026-10-29 | 93783 | LightGBM | 2.33% | 4.79% | 4.77% | +51% |

## Reading the results

- **Hourly is where the models clearly earn their keep.**
  - Himachal: 1.75% vs 4.45% persistence.
  - Karnataka: 2.33% vs 4.79%.
  - Bihar: 1.81% vs 2.77%.
  - These are in line with Delhi's hourly result (1.31% vs 3.43%).
- **Daily peak is a hard target for a one-step model.**
  - Yesterday's peak is already a strong forecast: persistence is 2.2–3.7% in the large, steady
    states (MP, Chhattisgarh, Rajasthan, Andhra, Bihar).
  - With about 4.5 years of usable daily rows (≈1,650), the tree models add little there.
- **Biggest daily gains:** small or weather-volatile systems, where persistence is weak — Chandigarh,
  Tamil Nadu, Sikkim, Mizoram, Delhi, Goa, Puducherry and Assam (+30–44%).
- **Models that lose to persistence (MP −16%, Bihar −15%, Andhra −5%, Odisha −2%) should not be
  served as-is.** Until they are improved, the state API should fall back to persistence for any
  state whose `served.json` shows a negative `skill_vs_persistence`.
- **Not comparable:** the Delhi PSP daily model (3.29%) and the main Delhi daily model (3.92%, `models/daily/`).
  The latter's target is the max of 5-minute SLDC data over a different period.

## Limitations

- **Oracle weather.** CV uses the observed weather for the target day. Live forecasts will use
  forecast weather, so expect somewhat higher error.
- **One weather point per state.** Large states such as UP, MP, Rajasthan and Maharashtra span several
  climate zones.
- **Holiday calendar is national/Delhi-centric.** Regional festivals (Onam, Pongal, Bihu, Chhath, …)
  are not yet state-specific.
- **One-step-ahead evaluation.** These are next-step accuracies with true lags. A recursive day-ahead
  (hourly) or week-ahead (daily) forecast will degrade with horizon. `src/forecasting/future.py` is
  still Delhi-specific.
- **Short daily histories.**
  - DNH&DD covers only the merged DNHDDPDCL era (2022-06 →). The earlier separate DNH and DD rows are
    not summed.
  - J&K's series includes Ladakh.
  - UP and MP before 2023 come from the official PDF fill (`nldc_psp_official`); that history starts
    2021-05.

## Possible next steps

1. Serve persistence where `skill_vs_persistence < 0` (MP, Bihar, Andhra, Odisha).
2. Drop or replace the y[t−365] lag for daily PSP models: it costs a full year of training rows.
   Re-test against persistence.
3. Use state-specific holiday calendars and population-weighted multi-point weather.
4. Generalise `future.py` so the states API serves day-ahead forecasts.
5. Let the scheduler accumulate sub-daily history for the live-polled states (Punjab, UP,
   Chhattisgarh, Gujarat, Maharashtra), then train hourly models for them.

## Reproduce

```bash
python scripts/backfill_psp_official.py --start 2021-05-01      # J&K, DNH&DD, MP, UP gaps
python scripts/train_state.py karnataka --resolution hourly     # hourly track
python scripts/train_state.py madhya_pradesh --source psp       # daily-peak track
python scripts/summarize_state_models.py                        # this table
```

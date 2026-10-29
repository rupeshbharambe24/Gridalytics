# Paper plan: festival demand shocks on the Delhi grid

**Status:** feasibility done 2026-10-29. This file supersedes the J+B+F plan in
`research_angles.md` §4①. The old "negative result" (B) and its "one-step CV hid it"
explanation (F) **do not survive** on corrected data. See §2.

## Working title

> **Festivals as Demand Shocks: A Decade of Weather-Adjusted Estimates for Delhi's Peak
> Electricity Demand, and Why Binary Holiday Flags Under-serve Gradient-Boosted Forecasters**

Shorter alternative: *"How Much Do Festivals Move Delhi's Grid? Counterfactual Estimates
from Ten Years of Peak Demand and Their Value for Day-Ahead Forecasting"*

## 1. Claims (narrowest honest version)

1. **Quantification (main).** To our knowledge, this is the first multi-year (2015–2024)
   per-festival estimate of holiday effects on Delhi's daily peak demand. Each estimate is
   a weather-adjusted counterfactual with uncertainty intervals. The effects are large
   and stable from year to year (Table 1).
   Prior work notes the dips **qualitatively only**: Gaur et al. NPSC 2016 and Grid-India's
   *Electricity Demand Pattern Analysis 2023* Vol. I §4.5.1. Hunt & Bloomfield 2025
   model Indian states but give no per-festival sizes. Banerjee & Sarkar 2010 found
   *no* holiday effect for the Northern grid.
2. **Multi-day structure.** The Diwali effect spans about 3 days: −17% on Diwali, −19% on
   Govardhan Puja and −12% on Bhai Duj. Holi has a day-after effect (Holi −31%, day after
   −13%). A single-day binary flag cannot represent either pattern.
3. **Forecasting value of an effect-size prior.** In a rolling-origin backtest (test years
   2019–2024), a causal signed-magnitude feature cuts LightGBM festival-day MAPE:
   - h=1: 6.6% → 5.6%, Wilcoxon p = 0.045.
   - h=7: 9.5% → 7.1%, p = 3×10⁻⁵.
   - Holi: about 32% → 11%.

   A binary flag and even a categorical festival identity do not do this. With only about
   one occurrence per year, trees cannot isolate a rare event from a flag.
   *Framing: a rare-event encoding result, not a new method. Cite Ziel 2018, plus target
   encoding and impact-adjusted dummies as precedent.*
4. **Data-integrity case study (secondary section).** Three silent defects in the pipeline
   each pushed conclusions toward "festivals don't matter":
   - a one-day report-date lag in pre-2021 daily data;
   - a day/month swap in the 5-min SCADA data;
   - Holi missing from the off-the-shelf holiday calendar.

   Together they produced a published-looking negative result. The section gives cheap
   detection tests (§3).

**Do not claim:** "first for India" (Grid-India Vol. II state tables are unchecked), that
the mechanism is new, or any 5-min/hourly accuracy headline.

## 2. What changed vs the earlier analysis (why B/F are dead)

| | Earlier (`event_aware_forecasting.md`) | Corrected (this plan) |
|---|---|---|
| psp_daily dates 2015–2020 | stored +1 day (report date) | shifted back 1 day |
| Weather 2015–2020 | none (DB weather starts 2021), so unadjusted | ERA5 daily via Open-Meteo archive |
| Holi in calendar | missing before 2024 | included (`holidays.India` optional category) |
| Diwali | −10.5% (shrunk) | **−17.2%** [−19.4, −14.9] |
| Holi | absent | **−31.2%** [−32.6, −29.8] |
| Republic Day | −3.9% | **−14.2%** [−16.3, −12.1] |
| Id-ul-Fitr | **+3.0%** ("sign varies") | −0.6%, null. The positive sign was an artifact. |
| Magnitude feature | neutral | **helps on festival days** (claim 3) |

Model fit: R² 0.953 → 0.967, and residual SD 5.21% → 4.39% after the date fix. This is
independent evidence that the shift is real. Corrupted dates also explain the old per-year
pattern (Diwali/Holi ≈ 0% in 2015–20, ≈ −20 to −30% in 2021–24).

## 3. Data defects found

**Status 2026-10-30:** defects 1–3 are fixed in the code, and the local DB was repaired with
`scripts/fix_date_integrity.py`, which is idempotent and does a dry run by default. Two more
issues were found while re-running the evaluations:

- **4. Daily target mixed peak and mean.** The daily target combined PSP *peak* with a 5-min
  daily *mean* (≈0.83× peak) after 2024-11. This created a fake level drop. Fixed: the daily
  target is now the peak everywhere.
- **5. Target leak.** `delhi_mw_diff_*` and the rolling stats include y_t in training but not
  at inference. Daily CV is 1.08% as shipped vs 3.87% leak-free, against 5.05% for
  persistence. **Still open; needs a feature fix and a retrain.** This is a strong
  paper-worthy illustration for Angle C. The corrected framing is "trees exploit it too",
  not "only linear models".


1. **`psp_daily` pre-2021: one-day lag.**
   - Evidence: the weekly low falls on Sun/Mon in 2015–20 but Sat/Sun in 2021–24, and the
     pattern is identical for day-of-month ≤12 vs >12, so this is a shift, not a swap.
   - The break is about 2021-01-02 (cumulative-sum test).
   - Likely cause: the Grid-India PSP report dated D reports day D−1.
2. **`demand_5min` legacy rows (2021 → ~late 2025): day/month swapped when day ≤ 12.**
   - Daily max vs psp: stored date gives median APE 24.3% and corr 0.002. Swapped date gives
     0.6% and 0.999 (n=492). Days >12 are correct (0.7%, 0.998).
   - Cause: `scripts/migrate_legacy_data.py:49` calls `pd.to_datetime(..., errors="coerce")`
     without `dayfirst=True`.
   - Live-scraped 2025-12 onward looks correct.
   - **Impact:** all 5-min/hourly models, their CV MAPEs, the hourly event A/B, and the
     5-min weather join are trained on mis-dated rows for about 60% of legacy days.
     Re-run after the fix.
3. **Holiday calendar** lacks Holi (and Govardhan Puja, Bhai Duj, Chhath, Karwa Chauth)
   before 2024, because `holidays.India()` defaults to the public category only.

Detection tests worth putting in the paper:
- a day-of-week-profile alignment test;
- a cross-source agreement test (5-min daily max vs PSP peak), checked at offsets −1/0/+1
  and with day/month swapped;
- a calendar-completeness check against an optional-holiday list.

## 4. Feasibility results (run 2026-10-29)

Scripts are in `scripts/paper/`. Fetch the weather first:
```
curl -s "https://archive-api.open-meteo.com/v1/archive?latitude=28.6139&longitude=77.209&start_date=2015-01-01&end_date=2024-12-31&daily=temperature_2m_mean,temperature_2m_max,temperature_2m_min,relative_humidity_2m_mean,precipitation_sum&timezone=Asia%2FKolkata" -o era5_delhi_daily.json
.venv/bin/python scripts/paper/festival_eventstudy.py data/edfs.db era5_delhi_daily.json out.csv
.venv/bin/python scripts/paper/festival_forecast_ablation.py data/edfs.db era5_delhi_daily.json scripts/paper/festival_eventstudy.py
```

**Event study.** The model is log(peak) ~ CDD/HDD (squared, lags 1–2) + Tmax + RH + rain +
DOW + year-month FE + two COVID-lockdown dummies + 25 festival dummies, with HAC(7) SEs.
N = 3,569 days.

**Table 1 (draft). Effect on daily peak vs counterfactual, 95% CI.**

| Festival | Effect | 95% CI | Years |
|---|---|---|---|
| Holi | −31.2% | [−32.6, −29.8] | 10 |
| Govardhan Puja (Diwali+1) | −18.7% | [−22.1, −15.3] | 10 |
| Diwali | −17.2% | [−19.4, −14.9] | 10 |
| Republic Day | −14.2% | [−16.3, −12.1] | 10 |
| Bhai Duj (Diwali+2) | −11.7% | [−14.5, −8.9] | 10 |
| Dussehra | −10.7% | [−14.0, −7.3] | 10 |
| Ram Navami | −6.2% | [−8.1, −4.3] | 10 |
| Independence Day | −3.8% | [−6.5, −1.1] | 8 |
| Eid-ul-Fitr / Bakrid | ≈0 | n.s. | 10 |
| Christmas | +4.1% | [+2.4, +5.9] | 9 (check: winter/New-Year confound) |
| Maha Shivaratri | +6.0% | [+3.5, +8.4] | 9 (check: Feb–Mar weather transition) |

Per-year stability: Holi falls between −27% and −34% in every year 2015–2024. Diwali falls
between −11% and −24%, and the drop is deepening (2021–24 are the four largest).

**Placebo test.** All dates are shifted ±4 and ±5 weeks, keeping the same day of week. The
placebo coefficients have mean 0.5% and SD 1.9%, but **22% reach p < 0.05 against a
nominal 5%**, so HAC SEs are anti-conservative. For the paper, use randomization (placebo)
inference or block bootstrap. The top seven effects are more than 3 placebo SDs out, so
they survive regardless.

**Forecast ablation.** LightGBM forecasts log peak, trained rolling-origin with test years
2019–24. Weather is *oracle* (actual ERA5). There are 146 festival test days.

| h | none | DB flag | full flag | flag + identity | flag + magnitude | persistence |
|---|---|---|---|---|---|---|
| 1, festival days | 7.95 | 7.43 | 6.57 | 6.64 | **5.59** | 7.38 |
| 1, normal days | 4.26 | 4.15 | 4.05 | 4.06 | 4.03 | 4.56 |
| 7, festival days | 10.31 | 9.95 | 9.52 | 9.43 | **7.07** | 13.37 |
| 7, normal days | 6.78 | 6.66 | 6.47 | 6.47 | 6.37 | 9.21 |

The magnitude feature does not uniformly win. Bhai Duj at h=1 gets worse (2.8% → 7.7%).
Investigate whether this is an interaction with the lag-1 = Govardhan Puja day.

## 5. To-do before drafting (in order)

1. ~~**Fix the data in the repo.**~~ Done 2026-10-30 (`fix/data-date-integrity`). The
   event-study numbers are unchanged after the fix. Next, fix the target leak (defect 5),
   then re-run the CV and recursive backtests.
2. **Make the ablation fully causal.** Fit the counterfactual for the magnitude feature
   only on data before each test year (it currently uses full-sample coefficients;
   event deviations are already prior-years-only).
3. **Replace oracle weather** with archived forecasts (Open-Meteo historical-forecast API,
   2022+) or a noise-injection sensitivity check. Add Diebold–Mariano tests and 5 seeds.
4. **Robustness grid.**
   - Alternative counterfactuals: the repo's ±21-day same-DOW estimator, this regression,
     and an ML counterfactual.
   - Drop the 2020–21 COVID years.
   - Peak vs energy: `delhi_energy_met_mu` is null for legacy rows, so re-scrape the PSP
     reports for it.
   - Window effects d−1 to d+3.
5. **Intraday-shape section (optional, strong figure).** With corrected 5-min dates, the
   2021–2026 festival days become usable. Show the Diwali evening profile vs a normal-day
   counterfactual. This quantifies the "Diwali evening peak" that Grid-India 2023 describes
   qualitatively.
6. Explain Christmas (+) and Maha Shivaratri (+), or report them as unexplained.
7. Confirm the exact psp break date and whether the source labels by report date. Read
   Grid-India *Demand Pattern Analysis 2023* **Vol. II** (state-level) for any Delhi
   festival numbers. This is the last scoop risk.

## 6. Outline

1. Introduction: festivals as large, recurring, culturally-timed demand shocks; the
   operational relevance for SLDC scheduling and DISCOM power purchase.
2. Related work: the qualitative Indian sources; holiday modelling (Ziel 2018, Arora &
   Taylor 2018); counterfactual demand estimation (Fezzi & Fanghella 2020, Prasanna et al.
   2022, the COVID-lockdown literature).
3. Data: PSP daily peak 2015–24, ERA5, calendar construction, and **§3.x data-integrity
   audit** (the three defects and their tests).
4. Method: the event-study counterfactual, inference (HAC + placebo), and multi-day windows.
5. Results I: the festival catalogue, per-year stability, and multi-day structure.
6. Results II: forecasting value of flag vs identity vs magnitude, by horizon and per
   festival.
7. Discussion: why binary flags fail for rare events, what the earlier corrupted pipeline
   concluded, and operational use.
8. Limitations: daily peak only, one city, oracle-weather sensitivity, COVID years.

## 7. Venues (confirm 2026 APC terms)

- arXiv (stat.AP / eess.SY) first.
- Then **Sadhana** or **Current Science** (Indian, no APC), or **MPCE** (power systems).
- *Energy for Sustainable Development* (Elsevier) via the subscription route (no APC) is a
  good topical fit.

## 8. Verified references (literature check 2026-10-29)

- Gaur, Rathour, Agarwal, Baba, Soonee, "Analysing the Electricity Demand Pattern," NPSC
  2016. iitk.ac.in/npsc/Papers/NPSC2016/1570293957.pdf. Qualitative "abrupt fall" only;
  copies weekend coefficients.
- Grid-India, *Electricity Demand Pattern Analysis: All India and Regional, 2023*, Vol. I
  §4.5.1. Qualitative festival discussion; no Delhi magnitudes.
- Hunt & Bloomfield (2025), *Environ. Res.: Energy* 2(2), 10.1088/2753-3751/adc7bc.
  Nearest academic neighbour.
- Banerjee & Sarkar (2010), IIM Calcutta WPS 656. No holiday effect found (a foil).
- Ziel (2018), JMPSCE 6(2):191–207, 10.1007/s40565-018-0385-5.
- Arora & Taylor (2018), EJOR 266(1):259–268, 10.1016/j.ejor.2017.08.056.
- Fezzi & Fanghella (2020), *Environ. Resource Econ.* 76:885–900,
  10.1007/s10640-020-00467-4.
- Prasanna, Grecov, Weng, Bergmeir (2022), arXiv:2209.08885.
- Bahmanyar, Estebsari, Ernst (2020), ERSS 68:101683, 10.1016/j.erss.2020.101683.
- Rubattu, Maroni, Corani (2023), arXiv:2305.05575.
- Clements & Hendry (1996), OBES 58(4):657–684.

Note: PR #5 (public) already discloses the event-effect idea. It is your own prior work,
so cite or mention it as such.

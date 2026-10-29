# Gridalytics — Research-Paper Angles & Publication Plan

> 🔴 **UPDATE 2026-10-29 — read `docs/paper_festival_effects.md` first.** A data audit found
> (1) a one-day date lag in `psp_daily` 2015–2020, (2) a day/month swap in legacy `demand_5min`
> rows, (3) Holi missing from the holiday calendar. On corrected data the festival effects are
> much larger (Holi −31%, Diwali −17%, Republic Day −14%; Eid ≈ 0, not +3%) and the
> event-magnitude feature **does** help festival-day forecasts. Angles **B and F (negative
> result) are void**; J becomes the flagship with a positive forecasting result. Numbers in §1
> below are pre-correction.

**Purpose:** self-contained handoff for a dedicated *research* chat. Everything here was
produced in a separate (code-implementation) session: candidate paper angles extracted from
the project, each verified against the published literature by four parallel literature-search
agents (Oct 2026), ranked, and turned into a concrete publication plan.

**How to use this file:** open a new chat in this repo and point it here. Start from §2
(verdict) and §4 (plan). §5 has the full per-angle detail and citations to chase.

> ⚠️ **Citation health warning.** All citations in §5–§6 were gathered by automated literature
> search. Several could **not** be full-text verified (publisher 403s, paywalls), and some
> arXiv IDs / years may be inaccurate or hallucinated. **Verify every reference yourself before
> citing it in a submission.** Unverified items are flagged inline.

---

## 1. Project context (grounding for the research chat)

**Gridalytics** = production ML system forecasting electricity demand for the **Delhi power grid**
at **5-minute, hourly, and daily** resolutions. Repo: `rupeshbharambe24/Gridalytics` (MIT).

- **Data (all free/open):**
  - `demand_5min` — Delhi SLDC SCADA load, Delhi + 5 DISCOMs (BRPL, BYPL, NDPL/TPDDL, NDMC, MES),
    5-min, 2021-01-01 → present. **Sparse: ~905 distinct days.**
  - `weather_hourly` — Open-Meteo, 7 vars, hourly, 2021 → present (≈complete).
  - `psp_daily` — Grid-India daily peak/energy, **2015-01-01 → 2024-11-20, continuous ~10 yr** (the
    strongest series).
  - `aqi_daily` — Open-Meteo AQI (PM2.5/PM10), **only 2025-03-30 → present (~1 yr, thin).**
  - `holidays` — calendar + festivals, 2015 → 2027 (festival dict hardcoded, goes blind after 2026).
- **Models:** LightGBM + XGBoost (champions, chosen by walk-forward CV), SARIMAX, ARIMA,
  NeuralProphet, BiLSTM. ~93 engineered features (lags, diffs, rolling, weather-derived,
  cyclical, Fourier, calendar/AQI).
- **Headline accuracy (walk-forward CV):** 5-min LightGBM **0.18% MAPE** / 8.6 MW / R² 0.9997;
  hourly LightGBM (Optuna) **0.50%** / 24.9 MW / 0.9983; hourly XGBoost 0.52%; daily LightGBM
  **2.65%** / 96.6 MW / 0.90. ⚠️ See §3 — the ultra-low numbers are a liability, not an asset.
- **Measured festival effects** (psp_daily 2015–2024, weather-adjusted same-DOW counterfactual,
  tier-shrunk): Diwali **−10.5%**, Good Friday −9.0%, Dussehra −4.5%, Republic Day −3.9%,
  Independence Day −3.6%, **Id-ul-Fitr +3.0%**, IPL season +2.4%. **Sign varies** (some events
  cut demand, some raise it) — a single binary `is_festival` flag can't express that.
- **Event-feature test result (negative):** a signed `expected_event_effect_pct` feature was
  neutral in walk-forward CV (daily 1.29%→1.29%, hourly 0.43%→0.43%) and marginal/not
  event-specific in a recursive day-ahead backtest (event-day MAPE 14.25%→14.12%, normal-day
  17.92%→17.64% — normal days improved *more*, so it's global noise, not event signal).
  → Not shipped. Full write-up: `docs/event_aware_forecasting.md`.
- **Classical-model CV (daily, 3 folds):** LightGBM 0.87% ≪ NeuralProphet 5.84% < SARIMAX 8.06%
  < ARIMA 8.37% MAPE. Linear models use 66/100 exog features (target-history excluded to avoid
  the leakage in Angle C). Full write-up: `docs/classical_models.md`.

---

## 2. Executive verdict

**No angle is wide-open-novel.** The project's *accuracy* is the wrong thing to lead with (a
0.18% 5-min MAPE reads to reviewers as near-persistence / leakage). But **four angles have real,
narrow, defensible gaps**, and the publishable contribution is your **rigor and honesty**
(leakage-free causal estimation, recursive backtests, a documented negative result), not a
leaderboard number. Frame everything as *method / quantification / honest negative result*.

---

## 3. Ranked novelty matrix

| Rank | Angle | Verdict | What already exists (so you must cite / not claim) | Free venue? |
|---|---|---|---|---|
| 1 | **J — 10-yr signed per-festival demand magnitudes** | **GAP** (narrow) | POSOCO NPSC-2016 documents the *qualitative* sign only; no per-festival magnitudes / counterfactual for India | ✅ Current Science, Sadhana (no-APC) |
| 2 | **C — lag+diff identity leaks target to linear (not tree) models** | **GAP** (narrow) | Leakage *category* known (Kaufman 2012; Kapoor–Narayanan 2023, "L2"); this exact mechanism undocumented | ✅ ReScience C, TMLR, arXiv (diamond OA) |
| 3 | **B+F — event feature adds nothing + one-step CV hid why** | PARTIAL | Target-encoding / lasso holiday-dummies (Ziel); one-step≠multi-step (Clements–Hendry, Hansen). Negative result + directional framing unpublished | ✅ MPCE; IJF (green OA) |
| 4 | **E — per-DISCOM + hierarchical reconciliation (Delhi's 5)** | **GAP**, needs new work | No *published* Delhi-DISCOM forecasting; BSES/TPDDL do it operationally (unpublished); reconciliation mature elsewhere | ✅ CSEE JPES, MPCE, IEEE PES India conf |
| 5 | **D — open 5-min + DISCOM + weather+AQI Delhi benchmark** | PARTIAL | Hourly Delhi sets exist (one paywalled); Karnataka already did the "Indian-SLDC-dataset" paper | ✅ Zenodo DOI + arXiv descriptor |
| 6 | A — AQI as a load driver | PARTIAL, weak | Birdal 2024 (AQI helps forecasting); Salvo 2020 (mechanism). Your AQI data thin (2025+); likely a null | a *section*, not a paper |
| 7 | G — unified 3-resolution champion/challenger system | **DONE** | Multi-res + temporal hierarchy + champion/challenger all established; 0.18% MAPE hurts credibility | not a research paper |

---

## 4. Recommended publication plan

### ① Flagship paper — combine J + B + F into one honest arc *(best bet; uses your strongest data)*
- **Claim 1 (J):** first multi-year (2015–2024) empirical quantification of the *signed* demand
  impact of individual Indian festivals/holidays on grid peak demand, via a weather-adjusted
  same-day-of-week counterfactual with tier pooling + shrinkage — a calibrated per-festival
  magnitude catalogue (+ IPL-season effect), not the qualitative "treat-as-weekend" heuristic.
- **Claim 2 (B):** feeding those magnitudes back as a forecasting feature does **not** beat plain
  binary holiday flags in a gradient-boosted load model — a documented negative ablation in a
  high-festival-density grid.
- **Claim 3 (F):** *why* it looked neutral — one-step CV with the true lag present masks the
  exogenous event signal (the realized lag already encodes the event); the recursive multi-step
  backtest is the honest inclusion gate.
- **Must cite head-on:** POSOCO NPSC-2016 (qualitative antecedent), Ziel 2018/2021, Clements–Hendry.
- **Venue:** Current Science or Sadhana (Indian, no-APC) or MPCE (power, no-APC). arXiv preprint first.

### ② Quick-win note — C (the leakage pitfall), standalone *(fastest real publication)*
- The `y = lag_n + diff_n` additive identity gives linear models (SARIMAX/ARIMA/ridge) a spurious
  ~0% error while trees never reveal it — silent until a linear model is swapped into a
  tree-oriented feature matrix. Give the algebraic condition, a detection recipe, and the fix
  (drop target-history columns from exogenous regressors for linear models).
- **Frame as** a model-family-dependent *instance* of the known L2 leakage category (Kaufman 2012;
  Kapoor–Narayanan 2023) — **not** a new category (reviewers will reject an over-claim).
- **Venue:** ReScience C or TMLR (zero APC, reproducibility-friendly), arXiv.

### ③ Dataset deposit — D, as Zenodo + arXiv data descriptor *(free DOI, low lift, underpins ①–②)*
- Claim must carry **every** qualifier or a competitor covers it: *first open, free-to-access,
  citable, multi-resolution (5-min + hourly + daily) Delhi grid-load benchmark with per-entity
  breakdown (Delhi + 5 DISCOMs), 2021–present, bundled with aligned Open-Meteo weather **and** AQI
  + Indian-holiday calendars + reproducible walk-forward splits.*
- Do **not** claim "first Delhi load dataset" or "first Indian SLDC benchmark" — both false.
- Note: raw data is already public on the SLDC site → contribution is curation/alignment/splits.
- Optional paid upgrade: *Data in Brief* (~US$600 APC). Diamond-OA data journals in energy are ~nil.

### ④ Future bigger paper — E (DISCOM hierarchical reconciliation) *(invest if you want a "proper" journal paper)*
- The one genuinely new *power-systems* result, but needs **new experiments**: per-DISCOM models +
  hierarchical reconciliation (MinT/OLS) vs forecasting the Delhi aggregate; quantify whether
  disaggregation/reconciliation helps. Claim "first *published, reproducible*" (BSES/TPDDL do it
  operationally).
- **Venue:** CSEE JPES, MPCE (both historically no-APC), or IEEE PES India conference.

### Skip as standalone papers
- **A (AQI):** thin data (2025+), likely a null, mechanism already established. Use as a
  feature-ablation *section* inside another paper if at all. **Read Birdal 2024 first.**
- **G (system/accuracy):** not novel; the headline MAPE hurts. At most an applied case-study,
  and only if reported with persistence/seasonal-naive **skill scores (MASE)** + a lag ablation.

---

## 5. Angles in detail

### Angle J — 10-year signed per-festival demand quantification  → **GAP (flagship)**
- **Closest prior art:**
  - Gaur, Rathour, Agarwal, Baba, Soonee (POSOCO/NLDC), *"Analysing the Electricity Demand
    Pattern,"* NPSC 2016, IIT Kanpur — states Diwali/Holi/Republic/Independence Day cause an
    "abrupt fall," recommends copying weekend coefficients. **Qualitative only, no magnitudes.**
    (iitk.ac.in/npsc/Papers/NPSC2016/1570293957.pdf) — *your single most important antecedent.*
  - Ziel (2018), *"Modeling public holidays in load forecasting: a German case study,"* JMPSCE,
    10.1007/s40565-018-0385-5 — holiday dummies, treat-as-Sunday vs separate-dummy; Germany, no magnitudes.
  - IIM Calcutta WP-656 — AR + holiday dummies, found *no* significant holiday effect (a
    methodological foil; crude dummies, no weather-adjusted counterfactual).
  - Dong et al. (2021) *"...Special Days Based on Bagged Regression Trees,"* Qingdao, PMC8460367;
    China Spring-Festival "distance" variable, arXiv:2310.15204 — method precedents for
    moving/lunar festivals (relevant to Eid/Diwali). ⚠️ verify.
  - International analogues (press/utility, not peer-reviewed): Ramadan −8% (Jordan/NEPCO),
    Indonesia PLN Eid peak −30% — confirm the sign-varying pattern exists globally.
  - "Sustainability, Culture & Electricity Demand Pattern in India" (ResearchGate 369824316) —
    descriptive; ⚠️ full text not accessed.
- **Why it's a gap:** existence + sign are documented *qualitatively* (POSOCO); **no peer-reviewed
  per-festival magnitude catalogue over ~10 yr with a weather-adjusted same-DOW counterfactual +
  tier shrinkage** exists for India.
- **Narrowest honest claim:** see §4 ①, Claim 1.
- **Data feasibility:** STRONG (psp_daily, 10 full years).
- **Free venues:** Current Science (IAS, no-APC), Sadhana (Springer/IAS, no-APC to publish), MPCE.

### Angle C — lag+diff additive-identity leakage, model-family-dependent  → **GAP (quick win)**
- **Closest prior art:**
  - Kapoor & Narayanan (2023), *"Leakage and the Reproducibility Crisis in ML-based Science,"*
    Patterns 4(9), arXiv:2207.07048 — canonical taxonomy; **L2 = "model uses illegitimate
    features"** (a feature that's a function of the target) — but **no subcategory** for exact
    algebraic reconstruction. (⚠️ *Patterns* itself charges an APC.)
  - Kaufman, Rosset, Perlich, Stitelman (2012), *"Leakage in Data Mining,"* ACM TKDD 6(4),
    10.1145/2382577.2382579 — foundational; target-derived feature = "illegitimate feature."
  - *"Which Leakage Types Matter? ...2,047 Benchmark Datasets,"* arXiv:2604.04199 — leakage impact
    is model-family-dependent but for *memorization* (trees most vulnerable) — opposite mechanism. ⚠️ verify ID.
  - TabLeak (arXiv:2210.01785), Leakage in Concept-Based Models (arXiv:2504.14094) — linear vs
    non-linear leakage susceptibility, but gradient-inversion/concept settings, not lag/diff.
  - Textbook collinearity of level/lag/difference (econometrics) — framed as collinearity among
    regressors, *not* as target leakage; no model-family point.
  - temporalcv / tsauditor docs — ⚠️ the "differenced target + lags encode current value" claim
    appears to be an unverified search-model inference; **do not cite until you read the docs.**
- **Why it's a gap:** the *category* is old; the *specific mechanism* (two individually-common
  engineered features forming `y = lag_n + diff_n`, exploited exactly by linear models, invisible
  to trees, silent until a linear model is tried on a shared tree-oriented matrix) is undocumented.
- **Narrowest honest claim:** see §4 ②. Position as an instance/corollary of L2, not a new type.
- **Free venues:** ReScience C (diamond OA, zero APC), TMLR (no APC), arXiv cs.LG; JMLR (high bar).

### Angles B + F — event-feature negative result + evaluation gate  → **PARTIAL (fold into flagship)**
- **Angle B closest prior art:**
  - Rubattu, Maroni & Corani (2023/24), *"Electricity Load and Peak Forecasting: Feature
    Engineering, Probabilistic LightGBM and Temporal Hierarchies,"* arXiv:2305.05575 — nearest
    echo: calendar/target-encoding block gave "no notable improvement" (MAPE 4.81→4.83). Not
    holiday-specific, not framed as a finding.
  - Ziel (2021), *"Smoothed Bernstein Online Aggregation...,"* arXiv:2107.06268 — lasso
    impact-adjusted (signed, shrunk) holiday dummies — closest "learned effect-size w/ shrinkage,"
    but inside a linear model, not an exogenous feature to a GBM.
  - Prophet→XGBoost/CatBoost two-stage (2025), Energy, S0360544225036230 — Prophet per-holiday
    coefficient feeds a GBM (structural analogue). ⚠️ unverified whether passed as a feature.
  - Ben Taieb & Hyndman GEFCom-2012 boosting; Qingdao bagged trees (PMC8460367); SAS (2016)
    holiday schemes — the binary/categorical baselines your result compares against.
  - Transformer explainability, arXiv:2512.20514 — holiday effect is *hour-varying* (binary daily
    flag misses it) — counterpoint to "binary already captures it." ⚠️ verify ID.
  - DoorDash eng. blog — trees miss holiday variation even one-hot encoded (≈1 obs/yr) — bears on
    whether continuous encodings have enough data to help.
- **Angle F closest prior art (riskier — principle is well known):**
  - *"Feature Construction and Selection for PV Solar Power Modeling,"* arXiv:2202.06226 — **most
    threatening**: already does feature selection by multi-step (not one-step) error. Opposite
    direction (good one-step / fails multi-step) from yours (neutral one-step / valuable multi-step).
  - skforecast docs, "Backtesting vs One-step-ahead" — one-step vs backtesting "can select
    different configurations."
  - Clements & Hendry (1996), Oxford Bulletin (centaur.reading.ac.uk/72764); Chevillon & Hendry
    (2004) — one-step fit ≠ optimal multi-step; MSFE rankings change with horizon.
  - Ben Taieb & Atiya (2016), IEEE TNNLS — bias/variance of multi-step strategies.
  - Short-term LV load + weather, arXiv:1804.02955 — uses horizon-dependence as a diagnostic for
    exogenous (weather) value; lags dominate. Closest *mechanism*, not framed as a CV-gate error.
  - Bergmeir, Hyndman & Koo (2018) CSDA; Hyndman `tsCV`; Hansen "Multi-step forecast model
    selection"; "Epistemic Error Decomposition...," arXiv:2511.11461. ⚠️ verify IDs.
- **Why it's a gap:** the *general* one-step≠multi-step principle is published; your *specific,
  directional* claim — in lag-dominated load models the true lag encodes the event, so one-step CV
  *masks* an exogenous event feature and is the wrong inclusion gate — plus a clean documented
  negative ablation, is not. **Caveat:** negative results are under-published (part of the "gap"
  is publication bias); a reviewer may call B "folklore." F is thin alone → only publish tied to B.
- **Free venues:** MPCE; International Journal of Forecasting (no mandatory APC, green self-archive;
  welcomes rigorous negative/replication results — selective); arXiv stat.AP.

### Angle E — DISCOM-level + hierarchical reconciliation  → **GAP, needs new experiments**
- **Closest prior art:**
  - BSES (BRPL, BYPL) & TPDDL operational AI forecasting — **industry, unpublished** (powerline.net.in
    2025). The biggest threat to a "first" claim → say "first *published, reproducible*."
  - Odisha-vs-Delhi CNN-BiLSTM, IJEEE 20(2), 2024 — Delhi *aggregate*, daily. ⚠️ verify.
  - ANN + time-series STLF, New Delhi & Greater Noida, Springer 10.1007/978-981-33-4501-0_41 —
    city/regional aggregate.
  - Delhi ARIMA/RNN/LSTM/GRU; IRJET 2026 (⚠️ low-rigor outlet, verify); VIT Bhopal ensemble 2024 —
    all aggregate Delhi, none disaggregate to DISCOMs.
  - Hierarchical methodology (non-India): Mogos et al., IEEE Access 2023,
    10.1109/ACCESS.2023.3309746 (MinT + AMI); "Hierarchical Demand Forecasting Benchmark for the
    Distribution Grid," arXiv:1910.03976 — establish MinT/OLS reconciliation, not applied to India.
- **Why it's a gap:** no peer-reviewed work forecasts Delhi's individual DISCOMs or reconciles them
  to the aggregate; reconciliation is mature but unapplied to Indian DISCOMs.
- **Narrowest honest claim:** first *published, reproducible* STLF that disaggregates to the five
  Delhi DISCOMs and hierarchically reconciles to the Delhi aggregate, quantifying whether that
  beats forecasting the aggregate directly. (Hierarchical reconciliation = the cleanest novelty.)
- **Free venues:** CSEE JPES, MPCE (both historically no-APC — ⚠️ confirm 2026 terms), IEEE PES /
  PIICON / ICPS India (registration only, no APC).

### Angle D — open multi-resolution Delhi benchmark dataset  → **PARTIAL gap (deposit)**
- **Closest existing datasets:**
  - Singh (NIT Delhi), *"Multi-Year Hourly Electricity Demand and Weather Dataset ... Delhi,"* IEEE
    DataPort, DOI 10.21227/wrt1-g704 — Delhi hourly 2018–2025, weather only, **no AQI/holidays/DISCOM,
    subscription-gated (not free).** Most direct competitor.
  - Bansal, IEEE DataPort, DOI 10.21227/kxed-hj49 — Delhi hourly load+weather.
  - happyman11/Delhi-SLDC (HuggingFace) — Apr–Aug 2024 only, irregular ~11-min, gated, messy.
  - happyman11/Karnataka-SLDC + *"...Hierarchical Multi-Task Deep Learning...Karnataka-SLDC Dataset,"*
    J. of Supercomputing (⚠️ "under review 2024" — confirm status). **The genre-precedent**: its card
    states "No public benchmark exists for Indian state-level SLDC data" — corroborates the gap for
    Delhi *and* shows the "Indian-SLDC-dataset-as-paper" play is taken (for Karnataka).
  - Basu et al., *"Indian power sector peak power demand time series,"* IEEE DataPort,
    DOI 10.21227/jcsm-hj03 — national evening-peak, 2014–2021; not Delhi-granular/sub-daily.
  - Barbar/Hanna (MIT), Zenodo 10.5281/zenodo.4564581, CC-BY-4.0 — projection to 2050, not observed.
  - ⚠️ Kaggle: no Delhi SLDC/DISCOM set surfaced — **do a manual Kaggle search before "first."**
- **Why it's a gap:** no *open, free, citable* set provides 5-min + multi-year + per-DISCOM +
  aligned weather **and** AQI + holidays + defined splits in one multi-resolution package.
- **Narrowest honest claim / venues:** see §4 ③.

### Angle A — AQI/PM2.5 as a load-forecast driver  → **PARTIAL, weak (a section at most)**
- **Closest prior art:**
  - Birdal (2024), *"Air pollution impact on forecasting electricity demand ... CNN-PSO,"*
    Environmental Research Communications 6(5), IOP — **explicitly uses air pollution as a
    load-forecasting input, claims MAPE −19.5%.** ⚠️ region not stated, no visible ablation, full
    text 403. **Read this before staking anything on A.**
  - "Short-term power demand forecasting using air pollution prevention measures," Sustainability
    11(10):2983 (2019, China) — pollution-policy curbs → demand (closest to the GRAP idea).
  - IET 2015 (China) — air quality folded into a fog/haze "comfort index."
  - **Salvo (2020), *"Local Pollution as a Determinant of Residential Electricity Demand,"* JAERE,
    10.1086/709533** — the mechanism paper: +1.1% residential demand per +10 µg/m³ PM2.5
    (AC/purifier/indoors), Singapore. **The mechanism is established — do not claim it.**
  - Delhi AQI-*prediction* papers exist (reverse direction, out of scope).
- **Why it's weak:** generic claim published; mechanism established; your AQI data is ~1 yr; a
  credible result may be a null (AQI adds little once temperature is in). Only daylight = a
  Delhi-specific AQI ablation + the (apparently unpublished) **GRAP-curb → demand** link.

---

## 6. Pre-submission verification checklist
- [ ] **Read Birdal 2024 full text** (region? pollutants? real ablation?) — gates Angle A.
- [ ] Confirm **Karnataka-SLDC paper** publication status + venue (nearest genre precedent for D).
- [ ] **Manual Kaggle search** "Delhi SLDC" / "Delhi DISCOM load" before any "first dataset" claim.
- [ ] **Direct IEEE Xplore + Scopus** title/abstract search on BSES/BRPL/BYPL/TPDDL/NDMC/"Delhi
      distribution" load forecasting before "first published" for E.
- [ ] **Measure persistence + seasonal-naive baselines** at 5-min/hourly/daily and report **MASE /
      % improvement over persistence**; run a **lag-ablation** — required if you cite any accuracy.
- [ ] Confirm current **APC/OA terms** for CSEE JPES, MPCE, Current Science, Sadhana, ReScience C,
      TMLR, IJF (sponsorship terms change).
- [ ] Verify **every arXiv ID / DOI** in §5–§6 (some may be inaccurate/hallucinated).
- [ ] For J, obtain the per-festival magnitude table with CIs and year counts from `psp_daily`.

## 7. Repo code & docs pointers
- `docs/event_aware_forecasting.md` — event-effect layer design + the negative result (Angles B/F/J).
- `docs/classical_models.md` — SARIMAX/ARIMA/NeuralProphet + the linear-model leakage (Angle C).
- `src/forecasting/event_effects.py` — counterfactual estimator + causal/leakage-free feature (J/B).
- `src/forecasting/future.py` — recursive day-ahead engine with `as_of=` backtest (F).
- `scripts/ab_event_effect.py`, `scripts/backtest_event_effect.py` — the A/B + recursive backtest (B/F).
- `scripts/eval_classical.py` — walk-forward CV harness that surfaced the leakage (C).
- Memory: `research-angles.md` (verdicts), `gridalytics-project.md`, `event-effect-feature-result.md`,
  `classical-models.md`.

## 8. One-line recommendation
Write **① (J+B+F flagship)** and **② (C note)** first — both land in free venues, both are honest
and defensible; deposit **③ (dataset)** on Zenodo to support them; keep **④ (E)** as the bigger
follow-up if you want a flagship power-systems journal paper. Lead with *quantification, method,
and the negative result* — never with the 0.18% MAPE.

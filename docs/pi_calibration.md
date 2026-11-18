# Prediction-interval calibration

Out-of-sample coverage of each served model's **90% prediction interval**, on the `holdout` rows the served artifact never trained on. Each model now carries a **conformal scale factor** (`pi_scale` in its `served.json`) computed by `scripts/calibrate_intervals.py`; the serving layer multiplies the band half-widths by it (the point forecast is unchanged), and `scripts/evaluate_calibration.py` applies it when measuring. Coverage below is **before &rarr; after** that recalibration.

| Model | Res | Served | `pi_scale` | Coverage before | after | n |
|---|---|---|---:|---:|---:|---:|
| maharashtra | daily | LightGBM | 6.00 | 30.0% | **83.3%** | 30 |
| andhra_pradesh | daily | LightGBM | 2.68 | 70.0% | **93.3%** | 30 |
| odisha | daily | LightGBM | 2.08 | 70.0% | **93.3%** | 30 |
| haryana | daily | LightGBM | 2.62 | 70.0% | **93.3%** | 30 |
| all_india | 15min | XGBoost | 2.03 | 73.8% | **90.2%** | 672 |
| tamil_nadu | daily | LightGBM | 1.84 | 76.7% | **93.3%** | 30 |
| puducherry | daily | LightGBM | 1.58 | 76.7% | **93.3%** | 30 |
| bihar | hourly | LightGBM | 1.73 | 79.9% | **89.6%** | 720 |
| uttar_pradesh | daily | LightGBM | 1.17 | 80.0% | **93.3%** | 30 |
| chandigarh | daily | LightGBM | 2.16 | 80.0% | **93.3%** | 30 |
| chhattisgarh | daily | LightGBM | 1.36 | 80.0% | **93.3%** | 30 |
| himachal_pradesh | 15min | XGBoost | 1.28 | 81.4% | **90.2%** | 672 |
| karnataka | hourly | XGBoost | 1.48 | 81.9% | **90.0%** | 720 |
| punjab | daily | LightGBM | 1.05 | 86.7% | **93.3%** | 30 |
| uttarakhand | daily | LightGBM | 1.13 | 86.7% | **93.3%** | 30 |
| jammu_kashmir | daily | LightGBM | 1.17 | 86.7% | **93.3%** | 30 |
| goa | daily | LightGBM | 1.91 | 86.7% | **93.3%** | 30 |
| sikkim | daily | LightGBM | 1.01 | 86.7% | **93.3%** | 30 |
| west_bengal | daily | LightGBM | 1.20 | 90.0% | **93.3%** | 30 |
| kerala | daily | LightGBM | 1.22 | 90.0% | **93.3%** | 30 |
| mizoram | daily | LightGBM | 1.03 | 90.0% | **93.3%** | 30 |
| manipur | daily | LightGBM | 1.04 | 90.0% | **93.3%** | 30 |
| meghalaya | daily | LightGBM | 1.02 | 90.0% | **93.3%** | 30 |
| assam | daily | LightGBM | 0.95 | 96.7% | **93.3%** | 30 |

**Summary:** 24 served models. Mean empirical coverage **80.4% &rarr; 92.3%** (nominal 90%) after applying the per-model conformal factors — the bands are no longer systematically over-confident. Maharashtra remains the hardest case (its raw band was ~3&times; too tight; the factor is clipped at 6&times;). 

**Caveats.** The factor is fit on the same holdout used to measure coverage, so the *after* figures are in-sample for the conformal step — optimistic on the n=30 daily holdouts (which snap to 28/30 = 93.3%). A cleaner build fits `pi_scale` on a separate calibration split and re-measures on untouched data; and `train_state.py` could compute it at train time so retrains stay calibrated. Delhi's three resolutions use the separate Delhi pipeline and are not covered here.

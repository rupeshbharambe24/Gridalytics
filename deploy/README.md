# Deployment / scheduled jobs

## Weekly model retrain

Refreshes every served state model on the latest data and re-emits each
`served.json` (metrics + data provenance/size/period + feature list), which is
what the dashboard model cards and `/api/v1/states` read.

- **`scripts/retrain_all.py`** — the driver. Explicit `MANIFEST` of how each
  state/resolution model is trained (source, span, weather). `--only <state>`,
  `--dry-run`.
- **`deploy/retrain_weekly.sh`** — wrapper: sets `DATABASE_URL`, runs the driver
  against a checkout of `main`, logs. Args pass through.
- **`deploy/com.gridalytics.retrain.plist`** — launchd agent, Sundays 03:30.

### Run once now
```bash
bash deploy/retrain_weekly.sh            # all models
bash deploy/retrain_weekly.sh --only bihar
```

### Schedule it
```bash
cp deploy/com.gridalytics.retrain.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.gridalytics.retrain.plist
# logs: ~/Library/Logs/gridalytics-retrain.{out,err}.log
```

**Requires a checkout of `main`** at the path in the wrapper/plist (where
`train_state.py` and `models/` live). If your working tree is on another branch,
set `GRIDALYTICS_REPO` to a main checkout or keep a dedicated one. By default the
wrapper only trains; uncomment its last lines to auto-commit/push the refreshed
models and run `gdrive-sync push`.

## Data scheduler (separate)

`python -m src.data.scheduler` polls the snapshot SLDC states every 15 min and runs
the nightly PSP/weather jobs. That's what makes UP/Chhattisgarh/Gujarat accumulate a
sub-daily series. Run it (or wrap it in its own LaunchAgent) with
`SLDC_INSECURE_TLS=true` for the TLS-gated states (Bihar/Punjab).

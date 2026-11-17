#!/usr/bin/env bash
# Weekly Gridalytics model retrain wrapper (called by the launchd agent, or by hand).
#
# Runs scripts/retrain_all.py against a checkout of `main` (train_state.py + models/
# live on main). Override the defaults with env vars if your layout differs:
#   GRIDALYTICS_REPO  checkout of main (default below)
#   DATABASE_URL      canonical DB (default: the local sqlite file)
#
#   bash deploy/retrain_weekly.sh                 # retrain all
#   bash deploy/retrain_weekly.sh --only bihar    # one state (args pass through)
set -uo pipefail

REPO="${GRIDALYTICS_REPO:-/Users/rbih/Projects/Experiments/gridalytics/Gridalytics}"
DB="${DATABASE_URL:-sqlite:////Users/rbih/Projects/Experiments/gridalytics/Gridalytics/data/edfs.db}"
PY="$REPO/.venv/bin/python"

cd "$REPO" || { echo "no repo at $REPO" >&2; exit 1; }
branch="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo '?')"
[[ "$branch" != "main" ]] && echo "WARN: $REPO is on '$branch', not main — models save to THIS checkout." >&2

echo "=== retrain start $(date)  (repo=$REPO branch=$branch) ==="
DATABASE_URL="$DB" "$PY" scripts/retrain_all.py "$@"
rc=$?
echo "=== retrain done rc=$rc $(date) ==="

# Optional automation (left manual by default — uncomment to enable):
#   git add models/states && git commit -m "chore(models): weekly retrain $(date +%F)" && git push origin main
#   gdrive-sync push     # refresh the Drive backup with the new model artifacts
exit $rc

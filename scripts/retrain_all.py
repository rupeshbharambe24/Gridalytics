"""Retrain every served state model on the latest data (weekly pipeline driver).

Re-runs scripts/train_state.py for each entry in MANIFEST — the single source of
truth for *how* each state/resolution model is trained (source, span, weather).
Each run picks up new data since last time and re-emits the schema-v2 served.json
(metrics + data provenance/size/period + feature list), so the dashboard's model
cards and the API stay current. train_state.py always saves the champion (even if
it loses to persistence); served.json's `beats_persistence` flags the losers.

  python scripts/retrain_all.py                  # retrain all models
  python scripts/retrain_all.py --only bihar     # just one state
  python scripts/retrain_all.py --dry-run        # print the commands, run nothing

Run from a checkout of `main` (train_state.py + models/ live there) with
DATABASE_URL pointing at the canonical DB, e.g.:

  DATABASE_URL="sqlite:////.../data/edfs.db" python scripts/retrain_all.py

--end is left open where we want fresh data each week; it is pinned only where a
known server-side gap must stay excluded (Bihar's 337-day BSPTCL hole).
"""
import argparse
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

MANIFEST = [
    # sub-daily SLDC models
    {"state": "all_india",        "resolution": "15min", "no_weather": True},
    {"state": "himachal_pradesh", "resolution": "15min"},
    {"state": "karnataka",        "resolution": "hourly"},
    {"state": "bihar",            "resolution": "hourly", "start": "2023-06-01", "end": "2025-08-31"},
    # daily peak (NLDC PSP) — dense span from 2021-05, open end for fresh data
    {"state": "tamil_nadu",       "source": "psp", "start": "2021-05-09"},
    # Punjab: the learned festival event-effect feature helps here (+0.18 pts);
    # it learns e.g. Diwali ~ -10% peak demand. Marginal/negative elsewhere.
    {"state": "punjab",           "source": "psp", "start": "2021-05-09", "event_effect": True},
    {"state": "uttar_pradesh",    "source": "psp", "start": "2021-05-09"},
    {"state": "andhra_pradesh",   "source": "psp", "start": "2021-05-09"},
    {"state": "maharashtra",      "source": "psp", "start": "2021-05-09"},
    {"state": "west_bengal",      "source": "psp", "start": "2021-05-09"},
    # Odisha only beats persistence once the yearly (lag_365) features are dropped
    # — they add noise on its short, drift-heavy PSP series. See --no-lag365.
    {"state": "odisha",           "source": "psp", "start": "2021-05-09", "no_lag365": True},
    # daily-PSP fleet expansion (Nov 2026): previously-untried states whose champion
    # beats persistence on the 2021-05→ dense span (weather on; load-centre coords in
    # train_state.STATE_COORDS). Jharkhand was tried too but loses (−0.19 pts), so it
    # is not served. See docs/state_models.md.
    {"state": "haryana",          "source": "psp", "start": "2021-05-09"},
    {"state": "chandigarh",       "source": "psp", "start": "2021-05-09"},
    {"state": "uttarakhand",      "source": "psp", "start": "2021-05-09"},
    {"state": "puducherry",       "source": "psp", "start": "2021-05-09"},
    {"state": "assam",            "source": "psp", "start": "2021-05-09"},
    {"state": "kerala",           "source": "psp", "start": "2021-05-09"},
    {"state": "jammu_kashmir",    "source": "psp", "start": "2021-05-09"},
    {"state": "chhattisgarh",     "source": "psp", "start": "2021-05-09"},
    {"state": "goa",              "source": "psp", "start": "2021-05-09"},
    # second fleet-expansion sweep (Nov 2026): small NE/UT grids. Of the seven
    # swept, four beat persistence and are served; Tripura (−10 pts), Nagaland
    # (−8 pts) and Dadra & Nagar Haveli / Daman & Diu (marginal +1 pt, and its
    # point forecast slipped just outside its own PI band) are not served.
    {"state": "sikkim",           "source": "psp", "start": "2021-05-09"},
    {"state": "mizoram",          "source": "psp", "start": "2021-05-09"},
    {"state": "manipur",          "source": "psp", "start": "2021-05-09"},
    {"state": "meghalaya",        "source": "psp", "start": "2021-05-09"},
]


def build_cmd(m: dict) -> list[str]:
    cmd = [sys.executable, str(ROOT / "scripts" / "train_state.py"), m["state"]]
    if m.get("source"):
        cmd += ["--source", m["source"]]
    if m.get("resolution"):
        cmd += ["--resolution", m["resolution"]]
    if m.get("start"):
        cmd += ["--start", m["start"]]
    if m.get("end"):
        cmd += ["--end", m["end"]]
    if m.get("no_weather"):
        cmd += ["--no-weather"]
    if m.get("no_lag365"):
        cmd += ["--no-lag365"]
    if m.get("event_effect"):
        cmd += ["--event-effect"]
    return cmd


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="retrain only this state")
    ap.add_argument("--dry-run", action="store_true", help="print commands, run nothing")
    args = ap.parse_args()

    items = [m for m in MANIFEST if not args.only or m["state"] == args.only]
    if not items:
        known = ", ".join(sorted({m["state"] for m in MANIFEST}))
        print(f"no model matches --only '{args.only}'. known: {known}")
        sys.exit(1)

    results = []
    for m in items:
        cmd = build_cmd(m)
        print(f"\n{'=' * 72}\n$ {' '.join(cmd)}\n{'=' * 72}", flush=True)
        if args.dry_run:
            continue
        t0 = time.time()
        rc = subprocess.run(cmd, cwd=str(ROOT)).returncode
        results.append((m["state"], m.get("resolution", m.get("source", "?")), rc, time.time() - t0))

    if args.dry_run:
        return

    print(f"\n{'#' * 72}\n  RETRAIN SUMMARY ({len(results)} models)\n{'#' * 72}")
    for state, res, rc, dt in results:
        print(f"  {'OK  ' if rc == 0 else 'FAIL'} {state:<18} {str(res):<8} {dt:6.0f}s")
    fails = [r for r in results if r[2] != 0]
    print(f"  {len(results) - len(fails)}/{len(results)} succeeded.")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()

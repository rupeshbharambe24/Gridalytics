"""Collect multi-state SLDC demand data (Phase 1: Bihar, Punjab, Uttar Pradesh).

Writes to the long-format `state_demand` / `state_demand_discom` tables.

Usage:
  # Today's snapshot/data for all configured states
  python scripts/collect_states.py

  # Backfill a date range (only matters for historical states, e.g. Bihar)
  python scripts/collect_states.py --start 2026-10-01 --end 2026-10-29

  # Specific states only
  python scripts/collect_states.py --states bihar,punjab

Snapshot states (Punjab, UP) have no history endpoint — a range is ignored and
only the current value is captured. Use the scheduler to poll them on an interval.
"""

import sys
import argparse
import logging
from pathlib import Path
from datetime import date, datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.data.db.session import get_session, create_tables
from src.data.db.models import StateDemandRecord
from src.data.scrapers.state_sldc import STATE_SCRAPERS, SNAPSHOT_STATES
from sqlalchemy import func

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger("collect_states")


def _parse_date(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def main():
    ap = argparse.ArgumentParser(description="Collect multi-state SLDC demand data")
    ap.add_argument("--states", default="",
                    help="comma-separated state codes (default: all configured)")
    ap.add_argument("--start", type=_parse_date, default=date.today(),
                    help="start date YYYY-MM-DD (default: today)")
    ap.add_argument("--end", type=_parse_date, default=date.today(),
                    help="end date YYYY-MM-DD (default: today)")
    args = ap.parse_args()

    create_tables()

    codes = [c.strip() for c in args.states.split(",") if c.strip()] or list(STATE_SCRAPERS)
    unknown = [c for c in codes if c not in STATE_SCRAPERS]
    if unknown:
        logger.error(f"Unknown state(s): {unknown}. Available: {list(STATE_SCRAPERS)}")
        sys.exit(1)

    total = 0
    for code in codes:
        scraper = STATE_SCRAPERS[code]()
        if code in SNAPSHOT_STATES and (args.start != date.today() or args.end != date.today()):
            logger.info(f"[{code}] snapshot-only source — ignoring date range, capturing current value")
        try:
            with get_session() as session:
                count = scraper.run(args.start, args.end, session)
                total += count
                logger.info(f"[{code}] {count} new rows")
        except Exception as e:
            logger.error(f"[{code}] failed: {e}")

    # Summary
    with get_session() as session:
        logger.info("=== state_demand totals ===")
        for code in codes:
            cnt = session.query(func.count(StateDemandRecord.id)).filter(
                StateDemandRecord.state_code == code).scalar()
            mx = session.query(func.max(StateDemandRecord.timestamp)).filter(
                StateDemandRecord.state_code == code).scalar()
            logger.info(f"  {code:<16} {cnt:>8,} rows   latest: {mx}")
    logger.info(f"Done. {total} new rows this run.")


if __name__ == "__main__":
    main()

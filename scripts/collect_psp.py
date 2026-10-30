"""Backfill Grid-India daily PSP (per-state demand) for ALL states — the all-India
fallback source.

One source → every state/UT at daily granularity, ~10 years deep. Run this from a
network where `report.grid-india.in` is reachable (it does not resolve from every
environment). Writes to the `state_psp_daily` table (source=grid_india_psp).

Usage:
  python scripts/collect_psp.py --start 2016-01-01 --end 2026-10-29
  python scripts/collect_psp.py --start 2025-01-01            # end defaults to yesterday

Note: this downloads one PDF per day and parses it, so a decade is a long run —
scope the range, or run it in chunks. Re-running is idempotent (upsert by state+date).
"""

import sys
import argparse
import logging
from pathlib import Path
from datetime import date, datetime, timedelta

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.data.db.session import get_session, create_tables
from src.data.db.models import StatePSPDaily
from src.data.scrapers.state_fallback import GridIndiaStatePSPScraper
from sqlalchemy import func

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger("collect_psp")


def _d(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def main():
    ap = argparse.ArgumentParser(description="Backfill Grid-India daily PSP for all states")
    ap.add_argument("--start", type=_d, required=True, help="start date YYYY-MM-DD")
    ap.add_argument("--end", type=_d, default=date.today() - timedelta(days=1),
                    help="end date YYYY-MM-DD (default: yesterday)")
    args = ap.parse_args()

    create_tables()
    scraper = GridIndiaStatePSPScraper()
    logger.info(f"PSP backfill {args.start} .. {args.end} (all states)")
    with get_session() as session:
        count = scraper.run(args.start, args.end, session)
    logger.info(f"Inserted {count} new PSP rows.")

    with get_session() as session:
        rows = (session.query(StatePSPDaily.state_code, func.count(StatePSPDaily.id))
                .group_by(StatePSPDaily.state_code).order_by(StatePSPDaily.state_code).all())
    logger.info("=== state_psp_daily totals ===")
    for code, n in rows:
        logger.info(f"  {code:<18} {n:>6,}")


if __name__ == "__main__":
    main()

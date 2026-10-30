"""Backfill daily PSP (per-state peak/energy) for ALL states — the all-India
fallback source.

One source → every state/UT at daily granularity. The official Grid-India host
(`report.grid-india.in`) is currently NXDOMAIN (dead from every network), so this
pulls the same NLDC PSP data via energymap.in's public API, which mirrors the
official files (each row's source_url points at webcdn.grid-india.in). History runs
~2021-05 onward. Writes `state_psp_daily` (source=energymap_posoco), and never
overwrites rows already collected from an official per-state SLDC. Re-verify against
the official files once that host is reachable again.

Usage:
  python scripts/collect_psp.py --start 2021-01-01 --end 2026-10-29
  python scripts/collect_psp.py --start 2025-01-01            # end defaults to yesterday

Re-running is idempotent (refreshes only energymap rows, by state+date).
"""

import sys
import argparse
import logging
from pathlib import Path
from datetime import date, datetime, timedelta

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.data.db.session import get_session, create_tables
from src.data.db.models import StatePSPDaily
from src.data.scrapers.state_fallback import EnergymapPSPScraper
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
    scraper = EnergymapPSPScraper()
    logger.info(f"PSP backfill {args.start} .. {args.end} (all states, via energymap)")
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

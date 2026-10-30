"""Universal fallback demand source — Grid-India daily PSP, all states.

For the ~29 states/UTs that have no clean per-state SLDC feed (see states.py
`fallback_states()`), Grid-India's **daily Power Supply Position (PSP) report**
is the one source that covers every state uniformly: a "Power Supply Position in
States" table with each state's peak demand met, energy met, and shortage, at
daily granularity. This collector downloads that report and writes one
``state_psp_daily`` row per state per day.

Design:
  * `parse_psp_states()` is a PURE function (DataFrame -> rows) so it can be
    unit-tested without any network — the table layout is the fragile part.
  * Download tries the direct dated PDF URL first (no Selenium). Grid-India's
    report host can be slow/geo-restricted; if the direct URL fails, fall back to
    the Selenium path in grid_india.py (Chrome required).

NOTE: the live download could not be verified from the build environment
(report.grid-india.in was unreachable); run it from a network where that host
resolves. The parser below is verified against a synthetic PSP table in tests.
"""

from __future__ import annotations

import io
import re
from datetime import date, timedelta

import pandas as pd
import requests
from sqlalchemy.orm import Session

from src.data.db.models import StatePSPDaily
from .base import BaseScraper
from .states import INDIAN_STATES

_UA = {"User-Agent": "Mozilla/5.0 (Gridalytics Research Project)"}

# PSP report names vs our state codes. Start from the registry, add known aliases.
_CODE_BY_NAME: dict[str, str] = {s.name.lower(): s.code for s in INDIAN_STATES}
_CODE_BY_NAME.update({
    "jammu and kashmir": "jammu_kashmir",
    "j&k": "jammu_kashmir",
    "dnh": "dnh_dd", "dd": "dnh_dd", "dnh & dd": "dnh_dd",
    "dadra & nagar haveli": "dnh_dd",
    "pondicherry": "puducherry",
    "a&n": "andaman_nicobar", "andaman": "andaman_nicobar",
})


def _match_state(label: str) -> str | None:
    """Map a PSP row label to a state_code (exact, then substring)."""
    s = re.sub(r"\s+", " ", str(label).strip().lower())
    if s in _CODE_BY_NAME:
        return _CODE_BY_NAME[s]
    for name, code in _CODE_BY_NAME.items():
        if name and name in s:
            return code
    return None


def parse_psp_states(df: pd.DataFrame, report_date: date) -> list[dict]:
    """Extract per-state rows from a PSP 'Power Supply Position in States' table.

    Heuristic (mirrors the existing Delhi extractor): for each row whose first
    text cell matches a state, take the numeric cells as [peak_demand_met_mw,
    energy_met_mu, ...]. Pure function — no I/O — so it is unit-tested directly.
    """
    rows: list[dict] = []
    seen: set[str] = set()
    for _, r in df.iterrows():
        cells = [c for c in r.tolist() if pd.notna(c)]
        if not cells:
            continue
        code = _match_state(cells[0])
        if not code or code in seen:
            continue
        nums: list[float] = []
        for v in cells[1:]:
            try:
                nums.append(float(str(v).replace(",", "").strip()))
            except (ValueError, TypeError):
                continue
        if not nums:
            continue
        seen.add(code)
        rows.append({
            "state_code": code,
            "date": report_date,
            "peak_demand_met_mw": nums[0],
            "energy_met_mu": nums[1] if len(nums) > 1 else None,
            "shortage_mw": nums[2] if len(nums) > 2 else None,
        })
    return rows


class GridIndiaStatePSPScraper(BaseScraper):
    """Daily per-state PSP collector (universal fallback)."""

    def __init__(self):
        super().__init__(name="grid_india_state_psp", max_retries=2, retry_delay=3.0)

    # --- direct dated-URL download (no Selenium) ---------------------------
    @staticmethod
    def _psp_urls(d: date) -> list[str]:
        fy = f"{d.year}-{d.year + 1}" if d.month >= 4 else f"{d.year - 1}-{d.year}"
        mon = d.strftime("%b %Y")
        fn = f"{d.strftime('%d.%m.%y')}_NLDC_PSP.pdf"
        base = "https://report.grid-india.in/ReportData/Daily Report/PSP Report"
        return [f"{base}/{fy}/{mon}/{fn}"]

    def _download(self, d: date) -> bytes | None:
        for url in self._psp_urls(d):
            try:
                resp = self._retry_request(requests.get, url, headers=_UA, timeout=40)
                if resp.status_code == 200 and resp.content[:4] == b"%PDF":
                    return resp.content
            except Exception as e:
                self.logger.warning(f"PSP download failed for {d}: {e}")
        return None

    @staticmethod
    def _pdf_tables(content: bytes) -> list[pd.DataFrame]:
        import pdfplumber
        out: list[pd.DataFrame] = []
        with pdfplumber.open(io.BytesIO(content)) as pdf:
            for page in pdf.pages:
                for tbl in (page.extract_tables() or []):
                    out.append(pd.DataFrame(tbl))
        return out

    def scrape(self, start_date: date, end_date: date) -> pd.DataFrame:
        rows: list[dict] = []
        current = start_date
        while current <= end_date:
            content = self._download(current)
            if content:
                for tdf in self._pdf_tables(content):
                    found = parse_psp_states(tdf, current)
                    if found:
                        rows.extend(found)
                        break  # the states table is usually a single table
            else:
                self.logger.warning(
                    f"No PSP report for {current} via direct URL. If report.grid-india.in "
                    f"is unreachable here, run from an Indian network, or use the Selenium "
                    f"path in grid_india.py.")
            current += timedelta(days=1)
        return pd.DataFrame(rows)

    def validate(self, df: pd.DataFrame) -> pd.DataFrame:
        if df is None or df.empty:
            return pd.DataFrame()
        df = df.dropna(subset=["peak_demand_met_mw"])
        df = df[(df["peak_demand_met_mw"] > 1) & (df["peak_demand_met_mw"] <= 80000)]
        return df.drop_duplicates(subset=["state_code", "date"], keep="last").reset_index(drop=True)

    def upsert(self, df: pd.DataFrame, session: Session) -> int:
        if df is None or df.empty:
            return 0
        count = 0
        for _, row in df.iterrows():
            exists = session.query(StatePSPDaily).filter(
                StatePSPDaily.state_code == row["state_code"],
                StatePSPDaily.date == row["date"],
            ).first()
            if exists:
                exists.peak_demand_met_mw = row["peak_demand_met_mw"]
                exists.energy_met_mu = row.get("energy_met_mu")
                exists.shortage_mw = row.get("shortage_mw")
            else:
                session.add(StatePSPDaily(
                    state_code=row["state_code"], date=row["date"],
                    peak_demand_met_mw=row["peak_demand_met_mw"],
                    energy_met_mu=row.get("energy_met_mu"),
                    shortage_mw=row.get("shortage_mw"),
                    source="grid_india_psp",
                ))
                count += 1
        session.flush()
        return count

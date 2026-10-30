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
import time
from datetime import date, datetime, timedelta

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


def _num(v) -> float | None:
    try:
        return float(str(v).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def _psp_upsert(df: pd.DataFrame, session: Session) -> int:
    """Shared upsert into state_psp_daily, keyed on (state_code, date).

    Each row must carry state_code, date, peak_demand_met_mw (+ optional
    energy_met_mu, shortage_mw, source).
    """
    if df is None or df.empty:
        return 0
    count = 0
    for _, row in df.iterrows():
        exists = session.query(StatePSPDaily).filter(
            StatePSPDaily.state_code == row["state_code"],
            StatePSPDaily.date == row["date"]).first()
        if exists:
            exists.peak_demand_met_mw = row["peak_demand_met_mw"]
            if row.get("energy_met_mu") is not None:
                exists.energy_met_mu = row.get("energy_met_mu")
        else:
            session.add(StatePSPDaily(
                state_code=row["state_code"], date=row["date"],
                peak_demand_met_mw=row["peak_demand_met_mw"],
                energy_met_mu=row.get("energy_met_mu"),
                shortage_mw=row.get("shortage_mw"),
                source=row.get("source", "sldc")))
            count += 1
    session.flush()
    return count


def _psp_validate(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    df = df.dropna(subset=["peak_demand_met_mw"])
    df = df[(df["peak_demand_met_mw"] > 1) & (df["peak_demand_met_mw"] <= 80000)]
    return df.drop_duplicates(subset=["state_code", "date"], keep="last").reset_index(drop=True)


def odisha_peak(df: pd.DataFrame) -> float | None:
    """Odisha power-status XLSX: the 'Instantaneous Peak demand' value (MW)."""
    for r in range(len(df)):
        for c in range(df.shape[1]):
            v = df.iat[r, c]
            if isinstance(v, str) and "instantaneous peak demand" in v.strip().lower():
                for cc in range(c + 1, df.shape[1]):
                    n = _num(df.iat[r, cc])
                    if n is not None and n > 100:
                        return n
    return None


class OdishaPSPScraper(BaseScraper):
    """Odisha daily peak from SLDC Odisha's Power-Status-Report XLSX archive.

    The listing page embeds direct .xlsx links for the whole history (~2025+);
    each file's 'Instantaneous Peak demand' is the day peak. -> state_psp_daily.
    """
    LIST_URL = "https://sldcorissa.org.in/report/power-status-report/"

    def __init__(self):
        super().__init__(name="sldc-odisha-psp", max_retries=2, retry_delay=3.0)

    def scrape(self, start_date: date, end_date: date) -> pd.DataFrame:
        resp = self._retry_request(requests.get, self.LIST_URL, headers=_UA, timeout=45)
        if resp.status_code != 200:
            return pd.DataFrame()
        pairs = re.findall(
            r'(https://sldcorissa\.org\.in/[^"\']*Report_Power-Status-Report_(\d{4}-\d{2}-\d{2})[^"\']*\.xlsx)',
            resp.text)
        seen, rows = set(), []
        for url, ds in pairs:
            if ds in seen:
                continue
            seen.add(ds)
            try:
                d = datetime.strptime(ds, "%Y-%m-%d").date()
            except ValueError:
                continue
            if d < start_date or d > end_date:
                continue
            try:
                r = self._retry_request(requests.get, url, headers=_UA, timeout=40)
                if r.status_code == 200 and r.content[:2] == b"PK":
                    df = pd.read_excel(io.BytesIO(r.content), header=None, engine="openpyxl")
                    peak = odisha_peak(df)
                    if peak:
                        rows.append({"state_code": "odisha", "date": d,
                                     "peak_demand_met_mw": peak, "source": "sldc_odisha"})
            except Exception as e:
                self.logger.warning(f"odisha {ds}: {e}")
            time.sleep(0.2)
        return pd.DataFrame(rows)

    def validate(self, df):
        return _psp_validate(df)

    def upsert(self, df, session):
        return _psp_upsert(df, session)


def himachal_peaks(html: str) -> list[dict]:
    """HPSLDC block-demand table -> one daily-peak row per date column.

    The table has 96 15-minute blocks (rows) with one column per date; the day
    peak is the max of that date's column (equals the explicit 'Peak Demand' row).
    """
    tabs = pd.read_html(io.StringIO(html))
    rows = []
    for t in tabs:
        if t.shape[0] < 50:
            continue
        # only the 96 time-block rows (Block Time like "00:00-00:15") — exclude
        # any total/sum/energy rows, which would otherwise inflate the max.
        block_time = t.iloc[:, 1].astype(str)
        mask = block_time.str.match(r"\s*\d{1,2}:\d{2}\s*-\s*\d{1,2}:\d{2}").fillna(False)
        if not mask.any():
            continue
        for ci in range(2, t.shape[1]):
            col = t.columns[ci]
            label = col[-1] if isinstance(col, tuple) else col
            try:
                d = datetime.strptime(str(label).strip(), "%Y-%m-%d").date()
            except ValueError:
                continue
            vals = pd.to_numeric(t.iloc[mask.values, ci], errors="coerce").dropna()
            if len(vals):
                rows.append({"state_code": "himachal_pradesh", "date": d,
                             "peak_demand_met_mw": float(vals.max()), "source": "hpsldc"})
    return rows


class HimachalPSPScraper(BaseScraper):
    """Himachal daily peak from HPSLDC's block-demand admin-ajax endpoint.

    POST action=demand_day_data with seldatagetyr/seldatagetmonth returns a whole
    month of 15-minute block demand; we take each day's max. History ~FY2017+.
    (15-min detail is available from the same source if finer resolution is wanted.)
    -> state_psp_daily.
    """
    URL = "https://hpsldc.com/wp-admin/admin-ajax.php"

    def __init__(self):
        super().__init__(name="hpsldc-psp", max_retries=2, retry_delay=3.0)

    def scrape(self, start_date: date, end_date: date) -> pd.DataFrame:
        rows: list[dict] = []
        y, m = start_date.year, start_date.month
        while (y, m) <= (end_date.year, end_date.month):
            try:
                resp = self._retry_request(
                    requests.post, self.URL, headers=_UA, timeout=40,
                    data={"action": "demand_day_data", "seldatagetyr": y, "seldatagetmonth": m})
                if resp.status_code == 200 and resp.text.strip():
                    for r in himachal_peaks(resp.text):
                        if start_date <= r["date"] <= end_date:
                            rows.append(r)
            except Exception as e:
                self.logger.warning(f"himachal {y}-{m}: {e}")
            time.sleep(0.3)
            m += 1
            if m > 12:
                m, y = 1, y + 1
        return pd.DataFrame(rows)

    def validate(self, df):
        return _psp_validate(df)

    def upsert(self, df, session):
        return _psp_upsert(df, session)


def maharashtra_peak(content: bytes) -> float | None:
    """Daily state peak (MW) from a MahaSLDC daily report PDF.

    The 'STATE DEMAND MET' row lists Morning / Day@17 / Evening / Night-min; the
    day peak is the max of those.
    """
    import pdfplumber
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        txt = "\n".join((p.extract_text() or "") for p in pdf.pages[:2])
    for line in txt.split("\n"):
        if "STATE DEMAND" in line.upper():
            nums = [n for n in (_num(x) for x in re.findall(r"\d{3,6}(?:\.\d+)?", line))
                    if n is not None and 1000 < n < 80000]
            if nums:
                return max(nums)
    return None


class MaharashtraPSPScraper(BaseScraper):
    """Maharashtra daily state peak from MahaSLDC's daily report PDFs.

    Uses the site's CodeIgniter report API to resolve each date's PDF URL (naming
    changed over the years), then extracts the day peak. History ~2014+. The live
    SCADA view is an image, so these PDFs are the history source. -> state_psp_daily.
    """
    REPORTS_PAGE = "https://mahasldc.in/reports/system-operations-daily-reports"
    API = "https://mahasldc.in/report/fetchReports"

    def __init__(self):
        super().__init__(name="mahasldc-psp", max_retries=2, retry_delay=3.0)
        self._sess = requests.Session()

    def _csrf(self) -> str | None:
        r = self._sess.get(self.REPORTS_PAGE, headers=_UA, timeout=30)
        m = re.search(r"csrfHash\s*=\s*'([0-9a-f]{32})'", r.text)
        return m.group(1) if m else None

    def scrape(self, start_date: date, end_date: date) -> pd.DataFrame:
        rows: list[dict] = []
        y, m = start_date.year, start_date.month
        while (y, m) <= (end_date.year, end_date.month):
            token = self._csrf()  # refresh per month (CodeIgniter rotates it)
            if token:
                try:
                    resp = self._sess.post(self.API, headers={
                        **_UA, "X-Requested-With": "XMLHttpRequest",
                        "Referer": self.REPORTS_PAGE, "Origin": "https://mahasldc.in"},
                        data={"t": "system-operations-daily-reports", "m": m, "y": y,
                              "w": "", "d": "", "s": "", "lang": "en", "page": 1,
                              "per_page": 40, "csrf_token": token}, timeout=40)
                    for rep in resp.json().get("reports", []):
                        url = rep.get("attachment_url")
                        dd = rep.get("day") or rep.get("d")
                        if not url or not dd:
                            continue
                        try:
                            d = date(int(y), int(m), int(dd))
                        except (ValueError, TypeError):
                            continue
                        if d < start_date or d > end_date:
                            continue
                        try:
                            pr = self._sess.get(url, headers=_UA, timeout=40)
                            if pr.status_code == 200 and pr.content[:4] == b"%PDF":
                                peak = maharashtra_peak(pr.content)
                                if peak:
                                    rows.append({"state_code": "maharashtra", "date": d,
                                                 "peak_demand_met_mw": peak, "source": "mahasldc"})
                        except Exception as e:
                            self.logger.warning(f"maha {d}: {e}")
                        time.sleep(0.2)
                except Exception as e:
                    self.logger.warning(f"maha {y}-{m} list: {e}")
            m += 1
            if m > 12:
                m, y = 1, y + 1
        return pd.DataFrame(rows)

    def validate(self, df):
        return _psp_validate(df)

    def upsert(self, df, session):
        return _psp_upsert(df, session)


def parse_telangana(df: pd.DataFrame) -> list[dict]:
    """Parse a TGSLDC power-supply-position .xlsx into daily rows.

    Columns are located by header text (robust to shifts): a 'Date' column, the
    'Unrestricted Peak' demand (MW), and energy 'Met' (MU). Pure — unit-testable.
    """
    date_col = peak_col = met_col = None
    for r in range(min(4, len(df))):
        for c in range(df.shape[1]):
            v = str(df.iat[r, c]).strip().lower()
            if v == "date" and date_col is None:
                date_col = c
            elif v == "unrestricted peak":
                peak_col = c
            elif v == "met" and met_col is None:
                met_col = c
    if date_col is None or peak_col is None:
        return []
    out = []
    for r in range(len(df)):
        raw = df.iat[r, date_col]
        try:
            d = pd.to_datetime(raw, dayfirst=True).date()
        except (ValueError, TypeError):
            continue
        peak = _num(df.iat[r, peak_col])
        if peak is None or peak <= 0:
            continue
        out.append({
            "state_code": "telangana", "date": d,
            "peak_demand_met_mw": peak,
            "energy_met_mu": _num(df.iat[r, met_col]) if met_col is not None else None,
            "shortage_mw": None,
        })
    return out


class TelanganaPSPScraper(BaseScraper):
    """Telangana daily peak demand + energy from TGSLDC's by-date-range .xlsx export.

    Source: tgsldc.in/power-supply-position/download?from=&to= — clean daily series
    back to ~2016. Writes to state_psp_daily (source=tgsldc). Needs openpyxl for .xlsx.
    A state-specific daily source (preferred over the generic Grid-India PSP fallback).
    """
    URL = "https://tgsldc.in/power-supply-position/download"

    def __init__(self):
        super().__init__(name="tgsldc-psp", max_retries=2, retry_delay=3.0)

    def scrape(self, start_date: date, end_date: date) -> pd.DataFrame:
        rows: list[dict] = []
        # The export caps each request to ~one month, so fetch month by month.
        cur = date(start_date.year, start_date.month, 1)
        while cur <= end_date:
            nxt = date(cur.year + 1, 1, 1) if cur.month == 12 else date(cur.year, cur.month + 1, 1)
            a, b = max(start_date, cur), min(end_date, nxt - timedelta(days=1))
            try:
                resp = self._retry_request(
                    requests.get, self.URL, headers=_UA, timeout=45,
                    params={"from": a.isoformat(), "to": b.isoformat()})
                if resp.status_code == 200 and resp.content[:2] == b"PK":  # xlsx = zip
                    df = pd.read_excel(io.BytesIO(resp.content), header=None, engine="openpyxl")
                    rows.extend(parse_telangana(df))
            except Exception as e:
                self.logger.warning(f"Telangana {cur:%Y-%m} failed: {e}")
            time.sleep(0.3)
            cur = nxt
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
                StatePSPDaily.state_code == "telangana",
                StatePSPDaily.date == row["date"]).first()
            if exists:
                exists.peak_demand_met_mw = row["peak_demand_met_mw"]
                exists.energy_met_mu = row.get("energy_met_mu")
            else:
                session.add(StatePSPDaily(
                    state_code="telangana", date=row["date"],
                    peak_demand_met_mw=row["peak_demand_met_mw"],
                    energy_met_mu=row.get("energy_met_mu"),
                    source="tgsldc"))
                count += 1
        session.flush()
        return count


def kerala_peak(html: str) -> float | None:
    """KSLDC 'System Statistics' page -> the day's peak demand (MW).

    The page is a dense, malformed stats table where a naive max over 4-digit
    numbers picks up generation/energy figures (e.g. 6648, above Kerala's ~6033
    all-time peak). The day's demand snapshots are the only MW values each paired
    with a grid-frequency reading (~50 Hz), so we scan the compacted numeric
    stream and keep a value only when the next number is a frequency in 49..51;
    the peak is the max of those. Verified: 20/10/2026 -> 4733, 29/10/2026 -> 4953.
    """
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    seq: list[float] = []
    for cell in soup.find_all(["td", "th"]):
        m = re.fullmatch(r"\s*([0-9]{1,5}(?:\.[0-9]+)?)\s*", cell.get_text(" ", strip=True))
        if m:
            seq.append(float(m.group(1)))
    demand = [seq[i] for i in range(len(seq) - 1)
              if 1500 <= seq[i] <= 5800 and 49.0 <= seq[i + 1] <= 51.0]
    return max(demand) if demand else None


class KeralaPSPScraper(BaseScraper):
    """Kerala daily peak from KSLDC's 'System Statistics' page.

    http://www.sldckerala.com/index.php?id=1 serves only the *latest* published
    day (yesterday's full stats) — there is no date archive — so this is a daily
    *snapshot* collector: each run captures that one day's peak and accumulates
    history going forward. The page's own 'SYSTEM STATISTICS - FOR DD/MM/YYYY'
    header dates the row. -> state_psp_daily (source=sldc_kerala).
    """
    URL = "http://www.sldckerala.com/index.php?id=1"

    def __init__(self):
        super().__init__(name="ksldc-psp", max_retries=2, retry_delay=3.0)

    def scrape(self, start_date: date, end_date: date) -> pd.DataFrame:
        try:
            resp = self._retry_request(requests.get, self.URL, headers=_UA, timeout=45)
        except Exception as e:
            self.logger.warning(f"Kerala fetch failed: {e}")
            return pd.DataFrame()
        if resp.status_code != 200:
            return pd.DataFrame()
        m = re.search(r"FOR\s+(\d{1,2})/(\d{1,2})/(\d{4})", resp.text)
        if not m:
            return pd.DataFrame()
        d = date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        if d < start_date or d > end_date:  # snapshot is outside the requested window
            return pd.DataFrame()
        peak = kerala_peak(resp.text)
        if not peak:
            return pd.DataFrame()
        return pd.DataFrame([{"state_code": "kerala", "date": d,
                              "peak_demand_met_mw": peak, "source": "sldc_kerala"}])

    def validate(self, df):
        return _psp_validate(df)

    def upsert(self, df, session):
        return _psp_upsert(df, session)


# energymap.in state slug -> our state_code. energymap mirrors the official NLDC PSP
# (its rows carry the source_url to the real webcdn.grid-india.in NLDC_PSP files), so
# this one API covers every state at daily granularity — the all-India fallback that
# report.grid-india.in used to serve before that host went dark.
_ENERGYMAP_SPECIAL = {"jammu-and-kashmir": "jammu_kashmir", "andaman-nicobar": "andaman_nicobar"}


def _energymap_code(slug: str) -> str:
    return _ENERGYMAP_SPECIAL.get(slug, slug.replace("-", "_"))


def energymap_psp_rows(items: list[dict], state_code: str) -> list[dict]:
    """Collapse energymap posoco-psp items for one state to one row per date.

    Each date can carry two source rows (a PDF-sourced ``peak_demand_mw`` and an
    XLS-sourced ``peak_demand_met_mw``); coalesce to a single daily peak (prefer
    'met', else 'mw', take the max when both rows exist) and the max energy_met.
    """
    by_date: dict = {}
    for it in items:
        ds = it.get("date")
        if not ds:
            continue
        peak = it.get("peak_demand_met_mw") or it.get("peak_demand_mw")
        energy = it.get("energy_met_mu")
        cur = by_date.setdefault(ds, {"peak": None, "energy": None})
        if peak is not None:
            cur["peak"] = peak if cur["peak"] is None else max(cur["peak"], peak)
        if energy is not None:
            cur["energy"] = energy if cur["energy"] is None else max(cur["energy"], energy)
    rows = []
    for ds, v in by_date.items():
        if v["peak"] is None:
            continue
        try:
            d = datetime.strptime(ds, "%Y-%m-%d").date()
        except ValueError:
            continue
        rows.append({"state_code": state_code, "date": d,
                     "peak_demand_met_mw": float(v["peak"]),
                     "energy_met_mu": float(v["energy"]) if v["energy"] is not None else None,
                     "source": "energymap_posoco"})
    return rows


class EnergymapPSPScraper(BaseScraper):
    """All-India daily PSP via energymap.in's public API — one source, every state.

    GET api.energymap.in/api/intelligence/posoco-psp?scope=state&state=<slug>&days=N
    returns that state's daily peak/energy as published in the Grid-India (NLDC) PSP
    reports, ~2021-05 onward (the API's `days` is capped at 2000). The state roster
    comes from /api/states. This stands in for the official report.grid-india.in host
    (currently NXDOMAIN); re-verify against the official files (each row's source_url
    points at webcdn.grid-india.in) once that host is reachable. -> state_psp_daily.
    """
    API = "https://api.energymap.in/api/intelligence/posoco-psp"
    ROSTER = "https://api.energymap.in/api/states"
    MAX_DAYS = 2000

    def __init__(self, states: list[str] | None = None):
        super().__init__(name="energymap-psp", max_retries=3, retry_delay=3.0)
        self._only = set(states) if states else None  # our state_codes to keep

    def _slugs(self) -> list[str]:
        try:
            r = self._retry_request(requests.get, self.ROSTER, headers=_UA, timeout=30)
            if r.status_code == 200:
                return [it["state_slug"] for it in r.json().get("items", []) if it.get("state_slug")]
        except Exception as e:
            self.logger.warning(f"energymap roster failed: {e}")
        return []

    def scrape(self, start_date: date, end_date: date) -> pd.DataFrame:
        days = min(self.MAX_DAYS, (date.today() - start_date).days + 2)
        rows: list[dict] = []
        for slug in self._slugs():
            code = _energymap_code(slug)
            if self._only and code not in self._only:
                continue
            try:
                r = self._retry_request(
                    requests.get, self.API, headers={**_UA, "Accept": "application/json"},
                    timeout=60, params={"days": days, "scope": "state", "state": slug})
                if r.status_code != 200:
                    self.logger.warning(f"energymap {slug}: HTTP {r.status_code}")
                    continue
                for row in energymap_psp_rows(r.json().get("items", []), code):
                    if start_date <= row["date"] <= end_date:
                        rows.append(row)
            except Exception as e:
                self.logger.warning(f"energymap {slug}: {e}")
            time.sleep(0.3)
        return pd.DataFrame(rows)

    def validate(self, df):
        return _psp_validate(df)

    def upsert(self, df: pd.DataFrame, session: Session) -> int:
        """Insert energymap rows, but never overwrite a row from another (official)
        source — deeper SLDC history (e.g. Telangana 2016+) and its provenance win."""
        if df is None or df.empty:
            return 0
        count = 0
        for _, row in df.iterrows():
            exists = session.query(StatePSPDaily).filter(
                StatePSPDaily.state_code == row["state_code"],
                StatePSPDaily.date == row["date"]).first()
            if exists:
                if exists.source == "energymap_posoco":  # refresh our own row only
                    exists.peak_demand_met_mw = row["peak_demand_met_mw"]
                    if row.get("energy_met_mu") is not None:
                        exists.energy_met_mu = row.get("energy_met_mu")
                continue  # a non-energymap (official) row is left untouched
            session.add(StatePSPDaily(
                state_code=row["state_code"], date=row["date"],
                peak_demand_met_mw=row["peak_demand_met_mw"],
                energy_met_mu=row.get("energy_met_mu"), source="energymap_posoco"))
            count += 1
        session.flush()
        return count

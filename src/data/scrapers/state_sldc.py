"""Multi-state SLDC demand scrapers (Phase 1 of the all-India rollout).

Generalizes the Delhi scraper (`sldc.py`) into a per-state driver that writes
to the long-format `state_demand` (+ `state_demand_discom`) tables, so the same
pipeline can feed forecasting models for any state.

Phase 1 ships the three jurisdictions that expose a clean, no-auth feed (all
verified live — see docs/state_grid_data_sources.md):

  * Bihar (BSLDC)  — JSON REST API, ~1-2 min, DISCOM-level (NBPDCL/SBPDCL),
                     with a by-date endpoint for historical backfill.
  * Punjab (PSLDC) — JSON web service, live snapshot (state total). Broken TLS
                     cert → requests with verify=False.
  * Uttar Pradesh (UPSLDC) — static JSON, live snapshot (state total). No
                     timestamp in the feed, so rows are stamped at collection time.

Snapshot sources (Punjab, UP) have no history endpoint: poll them on an interval
(see src/data/scheduler.py) to accumulate a series. Bihar carries its own history.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
import io
import re
import ssl
import time

import numpy as np
import pandas as pd
import requests
import urllib3
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from sqlalchemy.orm import Session

try:
    from urllib3.util.ssl_ import create_urllib3_context
except Exception:  # pragma: no cover
    create_urllib3_context = None

from config import settings
from src.data.db.models import StateDemandRecord, StateDiscomDemandRecord
from .base import BaseScraper

# Punjab's SLDC API has a misconfigured TLS chain; we call it with verify=False,
# so silence the (expected) insecure-request warning for this process.
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

_UA = {"User-Agent": "Mozilla/5.0 (Gridalytics Research Project)"}


class _LegacyTLSAdapter(HTTPAdapter):
    """TLS adapter for old Indian SLDC servers.

    Bihar's API (sldc.bsptcl.co.in) runs an old TLS stack that OpenSSL 3.x
    rejects with UNSAFE_LEGACY_RENEGOTIATION_DISABLED. We always re-enable legacy
    renegotiation (a protocol-compat option, not a verification change). Whether
    certificate verification is skipped is gated on ``settings.SLDC_INSECURE_TLS``
    (default False); Bihar also serves an incomplete cert chain, so verification
    only succeeds with that flag on. InsecureRequestWarning is silenced above.
    """
    def init_poolmanager(self, *args, **kwargs):
        ctx = create_urllib3_context() if create_urllib3_context else ssl.create_default_context()
        ctx.options |= getattr(ssl, "OP_LEGACY_SERVER_CONNECT", 0x4)
        if settings.SLDC_INSECURE_TLS:
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
        kwargs["ssl_context"] = ctx
        return super().init_poolmanager(*args, **kwargs)


def _legacy_session() -> requests.Session:
    s = requests.Session()
    s.mount("https://", _LegacyTLSAdapter())
    return s

# State-level columns the base upsert knows about; any extra column named
# "d__<DISCOM>" is treated as a DISCOM-level series.
_STATE_FIELDS = ("demand_mw", "frequency_hz", "schedule_mw", "drawal_mw")


def _f(v) -> float | None:
    """Best-effort float; returns None for None/blank/non-numeric."""
    if v is None:
        return None
    try:
        return float(str(v).strip().replace(",", ""))
    except (TypeError, ValueError):
        return None


def _dt(s, fmt) -> datetime | None:
    """Parse a timestamp string with the given format; None on failure."""
    if not s:
        return None
    try:
        return datetime.strptime(str(s).strip(), fmt)
    except (TypeError, ValueError):
        return None


class StateSLDCScraper(BaseScraper):
    """Base for per-state demand scrapers.

    Subclasses set ``STATE_CODE`` / ``SOURCE`` and implement ``scrape()`` to
    return a DataFrame with columns: ``state_code, timestamp, demand_mw`` and
    optionally ``frequency_hz, schedule_mw, drawal_mw`` plus any ``d__<DISCOM>``
    columns. ``validate`` and ``upsert`` are shared.
    """

    STATE_CODE: str = ""
    STATE_NAME: str = ""
    SOURCE: str = "sldc"

    # Plausible range for an Indian state/UT total (Maharashtra peaks ~30 GW).
    MIN_MW = 1.0
    MAX_MW = 80000.0

    def __init__(self):
        super().__init__(name=f"sldc-{self.STATE_CODE}", max_retries=3, retry_delay=2.0)
        self.state_code = self.STATE_CODE
        self.source = self.SOURCE

    # --- shared validation --------------------------------------------------
    def validate(self, df: pd.DataFrame) -> pd.DataFrame:
        if df is None or df.empty:
            return pd.DataFrame()

        initial = len(df)
        df = df.dropna(subset=["demand_mw"])
        df = df[(df["demand_mw"] > self.MIN_MW) & (df["demand_mw"] <= self.MAX_MW)]

        # Null-out obviously-bad frequency sentinels (feeds use -1 for missing).
        if "frequency_hz" in df.columns:
            bad = (df["frequency_hz"] <= 0) | (df["frequency_hz"] > 60)
            df.loc[bad, "frequency_hz"] = np.nan

        df = df.drop_duplicates(subset=["state_code", "timestamp"], keep="last")

        dropped = initial - len(df)
        if dropped > 0:
            self.logger.warning(f"Dropped {dropped}/{initial} invalid rows")
        return df.reset_index(drop=True)

    # --- shared upsert ------------------------------------------------------
    def upsert(self, df: pd.DataFrame, session: Session) -> int:
        if df is None or df.empty:
            return 0

        tmin = df["timestamp"].min().to_pydatetime()
        tmax = df["timestamp"].max().to_pydatetime()

        # Pre-load existing keys in range once (fast for Bihar's volume).
        existing_state = {
            r[0] for r in session.query(StateDemandRecord.timestamp).filter(
                StateDemandRecord.state_code == self.state_code,
                StateDemandRecord.timestamp >= tmin,
                StateDemandRecord.timestamp <= tmax,
            ).all()
        }
        discom_cols = [c for c in df.columns if c.startswith("d__")]
        existing_disc = set()
        if discom_cols:
            existing_disc = {
                (r[0], r[1]) for r in session.query(
                    StateDiscomDemandRecord.discom_code,
                    StateDiscomDemandRecord.timestamp,
                ).filter(
                    StateDiscomDemandRecord.state_code == self.state_code,
                    StateDiscomDemandRecord.timestamp >= tmin,
                    StateDiscomDemandRecord.timestamp <= tmax,
                ).all()
            }

        new_state, new_disc = [], []
        for _, row in df.iterrows():
            ts = row["timestamp"]
            ts = ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts

            if ts not in existing_state:
                new_state.append(StateDemandRecord(
                    state_code=self.state_code,
                    timestamp=ts,
                    demand_mw=float(row["demand_mw"]),
                    frequency_hz=_f(row.get("frequency_hz")),
                    schedule_mw=_f(row.get("schedule_mw")),
                    drawal_mw=_f(row.get("drawal_mw")),
                    source=self.source,
                ))
                existing_state.add(ts)

            for col in discom_cols:
                val = _f(row.get(col))
                if val is None or val <= 0:
                    continue
                code = col[3:]
                if (code, ts) in existing_disc:
                    continue
                new_disc.append(StateDiscomDemandRecord(
                    state_code=self.state_code, discom_code=code,
                    timestamp=ts, demand_mw=val, source=self.source,
                ))
                existing_disc.add((code, ts))

        if new_state or new_disc:
            session.bulk_save_objects(new_state + new_disc)
            session.flush()
        return len(new_state)


# ---------------------------------------------------------------------------
# Bihar — JSON REST API, DISCOM-level, with by-date history
# ---------------------------------------------------------------------------
class BiharSLDCScraper(StateSLDCScraper):
    STATE_CODE = "bihar"
    STATE_NAME = "Bihar"
    SOURCE = "bsldc"

    def __init__(self):
        super().__init__()
        self._session = _legacy_session()  # old TLS stack needs legacy renegotiation

    def scrape(self, start_date: date, end_date: date) -> pd.DataFrame:
        rows: list[dict] = []
        current = start_date
        while current <= end_date:
            try:
                data = self._fetch_day(current)
                if data:
                    rows.extend(self._parse(data))
            except Exception as e:
                self.logger.warning(f"Failed {current}: {e}")
            current += timedelta(days=1)
            time.sleep(0.5)
        return pd.DataFrame(rows)

    def _fetch_day(self, d: date) -> list | None:
        base = settings.BIHAR_SLDC_URL.rstrip("/")
        if d >= date.today():
            url = f"{base}/GetAllSCADAData"
        else:
            url = f"{base}/GetAllSCADADataDatewise?date={d.strftime('%d-%B-%Y')}"
        resp = self._retry_request(self._session.get, url, headers=_UA, timeout=45)
        if resp.status_code != 200:
            self.logger.warning(f"HTTP {resp.status_code} for {d}")
            return None
        try:
            return resp.json()
        except ValueError:
            return None

    def _parse(self, data: list) -> list[dict]:
        out = []
        for rec in data:
            ts = self._ts(rec.get("Date"), rec.get("Time"))
            if ts is None:
                continue
            out.append({
                "state_code": self.STATE_CODE,
                "timestamp": ts,
                "demand_mw": _f(rec.get("DemandMet")),
                "frequency_hz": _f(rec.get("Freq")),
                "schedule_mw": _f(rec.get("Scheduled")),
                "drawal_mw": _f(rec.get("Actual")),
                "d__NBPDCL": _f(rec.get("NB_DEMAND_MET")),
                "d__SBPDCL": _f(rec.get("SB_DEMAND_MET")),
            })
        return out

    @staticmethod
    def _ts(dstr, tstr):
        """Bihar: Date='DDMMYY', Time='HHMMSS'."""
        if not dstr or not tstr:
            return None
        try:
            return datetime.strptime(f"{str(dstr).zfill(6)}{str(tstr).zfill(6)}",
                                     "%d%m%y%H%M%S")
        except ValueError:
            return None


# ---------------------------------------------------------------------------
# Punjab — JSON web service, live snapshot (broken TLS → verify=False)
# ---------------------------------------------------------------------------
class PunjabSLDCScraper(StateSLDCScraper):
    STATE_CODE = "punjab"
    STATE_NAME = "Punjab"
    SOURCE = "psldc"

    def scrape(self, start_date: date, end_date: date) -> pd.DataFrame:
        # Snapshot-only source: date range is ignored; returns the current value.
        url = f"{settings.PUNJAB_SLDC_URL.rstrip('/')}/dynamicData"
        resp = self._retry_request(requests.get, url, headers=_UA,
                                   timeout=30, verify=not settings.SLDC_INSECURE_TLS)
        if resp.status_code != 200:
            self.logger.warning(f"HTTP {resp.status_code}")
            return pd.DataFrame()
        j = resp.json()
        ts = self._ts(j.get("updateDate"))
        load = _f(j.get("loadMW"))
        if ts is None or load is None:
            return pd.DataFrame()
        return pd.DataFrame([{
            "state_code": self.STATE_CODE,
            "timestamp": ts,
            "demand_mw": load,
            "frequency_hz": _f(j.get("frequencyHz")),
            "schedule_mw": _f(j.get("scheduleMW")),
            "drawal_mw": _f(j.get("drawalMW")),
        }])

    @staticmethod
    def _ts(s):
        try:
            return datetime.strptime(s, "%d-%m-%Y %H:%M:%S")
        except (TypeError, ValueError):
            return None


# ---------------------------------------------------------------------------
# Uttar Pradesh — static JSON, live snapshot (no timestamp in feed)
# ---------------------------------------------------------------------------
class UPSLDCScraper(StateSLDCScraper):
    STATE_CODE = "uttar_pradesh"
    STATE_NAME = "Uttar Pradesh"
    SOURCE = "upsldc"

    def scrape(self, start_date: date, end_date: date) -> pd.DataFrame:
        url = f"{settings.UP_SLDC_URL.rstrip('/')}/real-time-summary.json"
        resp = self._retry_request(requests.get, url, headers=_UA, timeout=30)
        if resp.status_code != 200:
            self.logger.warning(f"HTTP {resp.status_code}")
            return pd.DataFrame()
        arr = resp.json()
        if not arr:
            return pd.DataFrame()
        j = arr[0]
        demand = _f(j.get("DEMAND_MW"))
        if demand is None:
            return pd.DataFrame()
        # Feed carries no timestamp → stamp at collection time (minute precision).
        ts = datetime.now().replace(second=0, microsecond=0)
        return pd.DataFrame([{
            "state_code": self.STATE_CODE,
            "timestamp": ts,
            "demand_mw": demand,
            "frequency_hz": _f(j.get("FREQUENC_HZ")),
            "schedule_mw": _f(j.get("SCHEDULE_MW")),
            "drawal_mw": _f(j.get("DRAWL_MW")),
        }])


# ---------------------------------------------------------------------------
# Karnataka — server-rendered ASP.NET dashboard, live snapshot, DISCOM-level
# ---------------------------------------------------------------------------
class KarnatakaSLDCScraper(StateSLDCScraper):
    STATE_CODE = "karnataka"
    STATE_NAME = "Karnataka"
    SOURCE = "ksldc"

    # span id -> field, per the current kptclsldc.in Default.aspx layout.
    # (Historical intraday data also lives in daily load-curve Excel files at
    #  loadcurve.kptcl.net — not yet wired here.)
    _DISCOMS = {"Label7": "BESCOM", "Label8": "HESCOM", "Label9": "GESCOM",
                "Label10": "CESC", "Label11": "MESCOM"}

    def scrape(self, start_date: date, end_date: date) -> pd.DataFrame:
        resp = self._retry_request(requests.get, settings.KARNATAKA_SLDC_URL,
                                   headers=_UA, timeout=30)
        if resp.status_code != 200:
            self.logger.warning(f"HTTP {resp.status_code}")
            return pd.DataFrame()
        soup = BeautifulSoup(resp.text, "html.parser")

        def span(i: str):
            el = soup.find("span", id=i)
            return el.get_text(strip=True) if el else None

        ts = _dt(span("Label6"), "%d/%m/%Y %H:%M")
        demand = _f(span("Label5"))          # STATE DEMAND
        if ts is None or demand is None:
            self.logger.warning("Karnataka: demand/timestamp not found (layout changed?)")
            return pd.DataFrame()
        row = {
            "state_code": self.STATE_CODE,
            "timestamp": ts,
            "demand_mw": demand,
            "frequency_hz": _f(span("Label1")),   # FREQUENCY
            "schedule_mw": None,
            "drawal_mw": _f(span("Label3")),       # CGS DRAWAL
        }
        for sid, name in self._DISCOMS.items():
            row[f"d__{name}"] = _f(span(sid))
        return pd.DataFrame([row])


class KarnatakaLoadCurveScraper(StateSLDCScraper):
    """Karnataka HOURLY demand history from KPTCL daily load-curve .xls files.

    Source: loadcurve.kptcl.net/LoadCurveUpload/data/D<DDMMMYYYY>.xls — one file
    per day, back to ~2011. Each file's "LOAD CURVE" sheet has a TIME/LOAD/
    FREQUENCY block (24 hourly rows). This is the *history* source that makes
    Karnataka trainable (the live kptclsldc.in page is only a snapshot). Writes
    hourly rows to state_demand (source=ksldc_loadcurve). Needs `xlrd` for .xls.
    """
    STATE_CODE = "karnataka"
    STATE_NAME = "Karnataka"
    SOURCE = "ksldc_loadcurve"
    BASE = "https://loadcurve.kptcl.net/LoadCurveUpload/data"
    _OLE_MAGIC = b"\xd0\xcf\x11\xe0"  # real .xls (OLE2); a 404 returns HTML instead

    def scrape(self, start_date: date, end_date: date) -> pd.DataFrame:
        rows: list[dict] = []
        current = start_date
        while current <= end_date:
            try:
                rows.extend(self._fetch_day(current))
            except Exception as e:
                self.logger.warning(f"Failed {current}: {e}")
            current += timedelta(days=1)
            time.sleep(0.4)  # be gentle on the server
        return pd.DataFrame(rows)

    def _fetch_day(self, d: date) -> list[dict]:
        url = f"{self.BASE}/D{d.strftime('%d%b%Y').upper()}.xls"
        resp = self._retry_request(requests.get, url, headers=_UA, timeout=40)
        if resp.status_code != 200 or resp.content[:4] != self._OLE_MAGIC:
            return []  # missing day → HTML 404 page, skip quietly
        try:
            df = pd.ExcelFile(io.BytesIO(resp.content), engine="xlrd").parse(0, header=None)
        except Exception as e:
            self.logger.warning(f"xls parse failed {d}: {e}")
            return []
        return self._parse(df, d)

    @staticmethod
    def _parse(df: pd.DataFrame, d: date) -> list[dict]:
        # locate the 'TIME' header cell; LOAD is the next column, FREQUENCY the one after
        pos = None
        for r in range(len(df)):
            for c in range(df.shape[1]):
                v = df.iat[r, c]
                if isinstance(v, str) and v.strip().upper() == "TIME":
                    pos = (r, c)
                    break
            if pos:
                break
        if not pos:
            return []
        r0, c = pos
        out = []
        for r in range(r0 + 1, len(df)):
            try:
                hour = int(float(df.iat[r, c]))
            except (TypeError, ValueError):
                continue
            if hour < 0 or hour > 23:
                continue
            load = _f(df.iat[r, c + 1])
            if load is None:
                continue
            out.append({
                "state_code": "karnataka",
                "timestamp": datetime(d.year, d.month, d.day, hour),
                "demand_mw": load,
                "frequency_hz": _f(df.iat[r, c + 2]) if c + 2 < df.shape[1] else None,
                "schedule_mw": None,
                "drawal_mw": None,
            })
        return out


# ---------------------------------------------------------------------------
# Chhattisgarh — server-rendered table, live snapshot (single DISCOM)
# ---------------------------------------------------------------------------
class ChhattisgarhSLDCScraper(StateSLDCScraper):
    STATE_CODE = "chhattisgarh"
    STATE_NAME = "Chhattisgarh"
    SOURCE = "csldc"

    def scrape(self, start_date: date, end_date: date) -> pd.DataFrame:
        resp = self._retry_request(requests.get, settings.CHHATTISGARH_SLDC_URL,
                                   headers=_UA, timeout=30)
        if resp.status_code != 200:
            self.logger.warning(f"HTTP {resp.status_code}")
            return pd.DataFrame()
        soup = BeautifulSoup(resp.text, "html.parser")

        pairs: dict[str, str] = {}
        for tr in soup.find_all("tr"):
            tds = tr.find_all("td")
            if len(tds) == 2:
                label = tds[0].get_text(" ", strip=True)
                if label and re.search(r"[A-Za-z]", label):
                    pairs.setdefault(label, tds[1].get_text(" ", strip=True))

        node = soup.find(string=re.compile("Updates Latest by"))
        ts = None
        if node:
            m = re.search(r"Updates Latest by\s*(.+)", node.parent.get_text(" ", strip=True))
            if m:
                ts = _dt(m.group(1), "%d-%b-%Y %H:%M")

        demand = _f(pairs.get("CG Demand"))
        if ts is None or demand is None:
            self.logger.warning("Chhattisgarh: demand/timestamp not found (layout changed?)")
            return pd.DataFrame()
        return pd.DataFrame([{
            "state_code": self.STATE_CODE,
            "timestamp": ts,
            "demand_mw": demand,
            "frequency_hz": _f(pairs.get("WR Frequency")),
            "schedule_mw": _f(pairs.get("CG Schedule")),
            "drawal_mw": _f(pairs.get("CG Drawl from Central Sector")),
        }])


# Registry — add new states here as their scrapers land (see the data-source doc).
STATE_SCRAPERS: dict[str, type[StateSLDCScraper]] = {
    "bihar": BiharSLDCScraper,
    "punjab": PunjabSLDCScraper,
    "uttar_pradesh": UPSLDCScraper,
    "karnataka": KarnatakaSLDCScraper,
    "chhattisgarh": ChhattisgarhSLDCScraper,
}

# Which states carry their own history (support date-range backfill) vs. are
# live-snapshot only (must be polled on an interval to build a series).
HISTORICAL_STATES = {"bihar"}
SNAPSHOT_STATES = {"punjab", "uttar_pradesh", "karnataka", "chhattisgarh"}

# Deferred (known but not yet scrapable without extra access):
#   gujarat — sldcguj.com RealTime.php is access-gated (HTTP 403) and the
#     homepage live widget was removed. Needs the official SLDC Android app's
#     backing API or a GETCO data-sharing arrangement. See docs/state_grid_data_sources.md.
DEFERRED_STATES = {"gujarat": "RealTime.php 403-gated; homepage widget removed"}

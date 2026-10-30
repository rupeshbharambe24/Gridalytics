"""Registry of Indian state/UT power grids and how Gridalytics sources each one.

This is the single, self-documenting map of the all-India rollout: every state and
union territory, its regional grid, its distribution companies (DISCOMs), and
**how (and whether) we can collect its demand data**. Browse this file to see the
state-wise coverage at a glance.

Data-acquisition tiers (see docs/state_grid_data_sources.md for the full inventory):

  DIRECT   — a dedicated per-state scraper exists (src/data/scrapers/state_sldc.py
             or sldc.py for Delhi): free, (near) real-time, sometimes DISCOM-level.
  FALLBACK — no clean per-state SLDC feed; covered by the shared national sources
             (Grid-India daily PSP + vidyutpravah) at daily / snapshot granularity
             via src/data/scrapers/state_fallback.py.
  DEFERRED — a feed exists but needs extra access we don't have yet (e.g. Gujarat's
             RealTime.php is auth/bot-gated); listed so it isn't forgotten.

`METHOD` records the concrete mechanism so the right collector is obvious.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Region(str, Enum):
    """India's five regional grids (Regional Load Despatch Centres)."""
    NR = "Northern"
    WR = "Western"
    SR = "Southern"
    ER = "Eastern"
    NER = "North-Eastern"


class Tier(str, Enum):
    DIRECT = "direct"       # dedicated per-state scraper
    FALLBACK = "fallback"   # national PSP / vidyutpravah only
    DEFERRED = "deferred"   # feed exists but needs extra access


class Method(str, Enum):
    JSON_API = "json_api"             # no-auth JSON endpoint (Bihar/Punjab/UP)
    STATIC_HTML = "static_html"       # server-rendered HTML snapshot (Karnataka/Chhattisgarh)
    PSP = "psp"                       # Grid-India daily PSP report (all states)
    VIDYUTPRAVAH = "vidyutpravah"     # MoP live state demand (JS-rendered; headless)
    REPORTS = "reports"               # by-date Excel/PDF reports (Telangana/Kerala/…)
    JS_DASHBOARD = "js_dashboard"     # needs a headless browser
    ACCESS_GATED = "access_gated"     # 403 / login / captcha
    NONE = "none"                     # no public feed found


@dataclass(frozen=True)
class StateGrid:
    code: str                         # snake_case key used in state_demand.state_code
    name: str
    region: Region
    discoms: tuple[str, ...]          # distribution companies (empty = single/dept utility)
    tier: Tier
    method: Method
    scraper: str | None = None        # class in state_sldc.py, or "fallback"/None
    source_url: str = ""
    notes: str = ""
    discom_level: bool = False        # True if we capture per-DISCOM demand


# ---------------------------------------------------------------------------
# The registry — all 28 states + 8 UTs, grouped by regional grid.
# (Delhi is the original, served by sldc.py / the wide demand_5min table.)
# ---------------------------------------------------------------------------
INDIAN_STATES: list[StateGrid] = [
    # ---- Northern Region (NRLDC) ----
    StateGrid("delhi", "Delhi", Region.NR,
              ("BRPL", "BYPL", "NDPL", "NDMC", "MES"), Tier.DIRECT, Method.STATIC_HTML,
              "SLDCScraper", "https://www.delhisldc.org/Loaddata.aspx",
              "5-min, DISCOM-level, by-date history; original data source.", discom_level=True),
    StateGrid("punjab", "Punjab", Region.NR, (), Tier.DIRECT, Method.JSON_API,
              "PunjabSLDCScraper", "https://sldcapi.pstcl.org/wsDataService.asmx",
              "no-auth JSON snapshot (loadMW); broken TLS -> SLDC_INSECURE_TLS."),
    StateGrid("uttar_pradesh", "Uttar Pradesh", Region.NR, (), Tier.DIRECT, Method.JSON_API,
              "UPSLDCScraper", "https://www.upsldc.org/assets/dataset/real-time-summary.json",
              "static JSON snapshot (DEMAND_MW); no timestamp in feed."),
    StateGrid("haryana", "Haryana", Region.NR, ("UHBVN", "DHBVN"), Tier.FALLBACK, Method.PSP,
              "fallback", "https://www.hvpn.org.in/", "HVPN site is a data-free SPA."),
    StateGrid("rajasthan", "Rajasthan", Region.NR, ("JVVNL", "AVVNL", "JdVVNL"),
              Tier.FALLBACK, Method.PSP, "fallback", "https://sldc.rajasthan.gov.in/",
              "SLDC bot-blocked (403) + bad TLS; needs browser verification."),
    StateGrid("himachal_pradesh", "Himachal Pradesh", Region.NR, (), Tier.FALLBACK,
              Method.JS_DASHBOARD, "fallback", "https://hpsldc.com/",
              "rich 15-min data but JS/AJAX (nonce) — headless browser needed."),
    StateGrid("uttarakhand", "Uttarakhand", Region.NR, (), Tier.FALLBACK, Method.PSP,
              "fallback", "https://uksldc.in/", "public SLDC site hosting-suspended."),
    StateGrid("jammu_kashmir", "Jammu & Kashmir", Region.NR, ("JPDCL", "KPDCL"),
              Tier.FALLBACK, Method.PSP, "fallback", "", "SLDC/PDD domains dead."),
    StateGrid("ladakh", "Ladakh", Region.NR, (), Tier.FALLBACK, Method.NONE,
              "fallback", "https://lpdd.ladakh.gov.in/",
              "SLDC/REMC under construction; not even on vidyutpravah."),
    StateGrid("chandigarh", "Chandigarh", Region.NR, ("CPDL",), Tier.FALLBACK, Method.PSP,
              "fallback", "", "No SLDC portal; CPDL is a billing SPA."),

    # ---- Western Region (WRLDC) ----
    StateGrid("karnataka", "Karnataka", Region.SR,
              ("BESCOM", "HESCOM", "GESCOM", "CESC", "MESCOM"), Tier.DIRECT, Method.STATIC_HTML,
              "KarnatakaSLDCScraper", "https://kptclsldc.in/",
              "live HTML incl. DISCOM split; Excel history at loadcurve.kptcl.net.",
              discom_level=True),
    StateGrid("chhattisgarh", "Chhattisgarh", Region.WR, ("CSPDCL",), Tier.DIRECT,
              Method.STATIC_HTML, "ChhattisgarhSLDCScraper", "https://sldccg.com/gen.php",
              "server-rendered table snapshot, 30-sec refresh (single DISCOM)."),
    StateGrid("gujarat", "Gujarat", Region.WR,
              ("UGVCL", "MGVCL", "PGVCL", "DGVCL"), Tier.DEFERRED, Method.ACCESS_GATED,
              None, "https://sldcguj.com/",
              "RealTime.php 403-gated + homepage widget removed; needs app API / GETCO."),
    StateGrid("maharashtra", "Maharashtra", Region.WR,
              ("MSEDCL", "Tata", "Adani", "BEST"), Tier.FALLBACK, Method.REPORTS,
              "fallback", "https://mahasldc.in/",
              "live SCADA is an image (OCR); by-date PDF archive for history."),
    StateGrid("madhya_pradesh", "Madhya Pradesh", Region.WR,
              ("MPPKVVCL", "MPMKVVCL", "MPPoKVVCL"), Tier.FALLBACK, Method.PSP,
              "fallback", "https://www.mptransco.in/", "no public live demand page."),
    StateGrid("goa", "Goa", Region.WR, (), Tier.FALLBACK, Method.PSP,
              "fallback", "https://www.goaelectricity.gov.in/", "no live page."),
    StateGrid("dnh_dd", "Dadra & Nagar Haveli and Daman & Diu", Region.WR,
              ("DNHPDCL",), Tier.FALLBACK, Method.PSP, "fallback", "",
              "privatised (Torrent); no public live data."),

    # ---- Southern Region (SRLDC) ----
    StateGrid("telangana", "Telangana", Region.SR, ("TGSPDCL", "TGNPDCL"),
              Tier.FALLBACK, Method.REPORTS, "fallback", "https://tgsldc.in/power-supply-position/",
              "daily peak + by-date-range Excel export; no public real-time."),
    StateGrid("kerala", "Kerala", Region.SR, (), Tier.FALLBACK, Method.REPORTS,
              "fallback", "https://sldckerala.com/index.php?id=1",
              "daily System Statistics (by-date); live only as SCADA images."),
    StateGrid("tamil_nadu", "Tamil Nadu", Region.SR, (), Tier.FALLBACK, Method.PSP,
              "fallback", "", "official SLDC URL unverified; unofficial energymap.in."),
    StateGrid("andhra_pradesh", "Andhra Pradesh", Region.SR,
              ("APEPDCL", "APSPDCL", "APCPDCL"), Tier.FALLBACK, Method.PSP,
              "fallback", "", "no reachable public SLDC URL."),
    StateGrid("puducherry", "Puducherry", Region.SR, (), Tier.FALLBACK, Method.PSP,
              "fallback", "https://electricity.py.gov.in/", "no live page."),

    # ---- Eastern Region (ERLDC) ----
    StateGrid("bihar", "Bihar", Region.ER, ("NBPDCL", "SBPDCL"), Tier.DIRECT, Method.JSON_API,
              "BiharSLDCScraper", "https://sldc.bsptcl.co.in:8086/api/SCADA/Get",
              "no-auth JSON ~1-2 min, DISCOM-level, by-date history; needs SLDC_INSECURE_TLS.",
              discom_level=True),
    StateGrid("odisha", "Odisha", Region.ER,
              ("TPCODL", "TPWODL", "TPNODL", "TPSODL"), Tier.FALLBACK, Method.REPORTS,
              "fallback", "https://sldcorissa.org.in/",
              "real-time portal login-gated; public report pages give DISCOM drawal."),
    StateGrid("west_bengal", "West Bengal", Region.ER, ("WBSEDCL", "CESC", "DPL"),
              Tier.FALLBACK, Method.REPORTS, "fallback", "https://www.wbsldc.in/",
              "forecasts/monthly reports only; no public live actuals."),
    StateGrid("jharkhand", "Jharkhand", Region.ER, ("JBVNL",), Tier.FALLBACK, Method.PSP,
              "fallback", "https://sldcjharkhand.com/", "placeholder site; no live data."),
    StateGrid("sikkim", "Sikkim", Region.ER, (), Tier.FALLBACK, Method.PSP,
              "fallback", "https://power.sikkim.gov.in/", "no live page; tiny load."),

    # ---- North-Eastern Region (NERLDC) ----
    StateGrid("assam", "Assam", Region.NER, ("APDCL",), Tier.FALLBACK, Method.PSP,
              "fallback", "https://aegcl.co.in/", "no public live page."),
    StateGrid("meghalaya", "Meghalaya", Region.NER, ("MePDCL",), Tier.FALLBACK, Method.PSP,
              "fallback", "https://meecl.nic.in/", "fallback only."),
    StateGrid("tripura", "Tripura", Region.NER, (), Tier.FALLBACK, Method.PSP,
              "fallback", "https://tsecl.in/", "site shows only annual projections."),
    StateGrid("manipur", "Manipur", Region.NER, ("MSPDCL",), Tier.FALLBACK, Method.PSP,
              "fallback", "https://mspcl.in/", "fallback only."),
    StateGrid("mizoram", "Mizoram", Region.NER, (), Tier.FALLBACK, Method.PSP,
              "fallback", "https://power.mizoram.gov.in/", "fallback only."),
    StateGrid("nagaland", "Nagaland", Region.NER, (), Tier.FALLBACK, Method.PSP,
              "fallback", "https://power.nagaland.gov.in/", "fallback only."),
    StateGrid("arunachal_pradesh", "Arunachal Pradesh", Region.NER, (), Tier.FALLBACK,
              Method.PSP, "fallback", "https://power.arunachal.gov.in/",
              "internal 15-min ADMS (not public); best RTI/data-share target."),
    StateGrid("andaman_nicobar", "Andaman & Nicobar Islands", Region.NER, (), Tier.FALLBACK,
              Method.NONE, None, "https://vidyut.andamannicobar.gov.in/",
              "isolated grid; absent from national feeds (RTI only)."),
    StateGrid("lakshadweep", "Lakshadweep", Region.SR, (), Tier.FALLBACK, Method.NONE,
              None, "https://lakshadweep.gov.in/electricity/",
              "isolated diesel micro-grids; no public data (RTI only)."),
]

# Fast lookup by code.
STATES_BY_CODE: dict[str, StateGrid] = {s.code: s for s in INDIAN_STATES}


def states_by_region(region: Region) -> list[StateGrid]:
    return [s for s in INDIAN_STATES if s.region == region]


def direct_states() -> list[StateGrid]:
    """States with a dedicated per-state scraper (highest-fidelity data)."""
    return [s for s in INDIAN_STATES if s.tier is Tier.DIRECT]


def fallback_states() -> list[StateGrid]:
    """States covered only by the shared national PSP / vidyutpravah sources."""
    return [s for s in INDIAN_STATES if s.tier is Tier.FALLBACK]


def discom_level_states() -> list[StateGrid]:
    """States where we capture a per-DISCOM breakdown (Delhi, Bihar, Karnataka)."""
    return [s for s in INDIAN_STATES if s.discom_level]


def coverage_summary() -> dict[str, int]:
    """Counts by tier — handy for a quick 'where are we' readout."""
    out: dict[str, int] = {}
    for s in INDIAN_STATES:
        out[s.tier.value] = out.get(s.tier.value, 0) + 1
    return out

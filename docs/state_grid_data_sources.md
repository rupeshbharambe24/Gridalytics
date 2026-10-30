# Scaling Gridalytics to every Indian state — grid load-data sources

**Purpose:** build spec for extending demand forecasting from Delhi to all Indian states/UTs.
For each jurisdiction: where its grid load/demand data lives and how to acquire it, benchmarked
against the Delhi pattern. Compiled Oct 2026 from five parallel per-region research passes.

## The Delhi benchmark (the bar)
`https://www.delhisldc.org/Loaddata.aspx?mode=DD/MM/YYYY` — free · no-auth · per-day GET ·
static HTML `<table>` · **5-minute** rows · **DISCOM-level** (Delhi + BRPL/BYPL/NDPL/NDMC/MES) ·
**historical by changing the date**. Code: `src/data/scrapers/sldc.py`.

> ⚠️ **Two caveats that apply to everything below.**
> 1. **Geo/DNS:** the research ran from a **US-based node**. Many Indian `.gov.in`/SLDC hosts and
>    `report.grid-india.in` timed out, returned DNS errors, or hit bot/WAF/cert failures from there.
>    **"Unreachable" usually means geo-blocked, not dead.** Every endpoint marked *(verify in India)*
>    must be re-tested from an Indian IP before you build against it.
> 2. **Verified-live vs reported:** endpoints tagged **✅LIVE** were actually fetched and returned real
>    MW during research; everything else is reported/inferred and needs confirmation.

---

## Implementation status (Oct 2026)

**State registry (read this to classify coverage):** [`src/data/scrapers/states.py`](../src/data/scrapers/states.py)
enumerates all **36** states/UTs with region, DISCOMs, tier (`direct` / `fallback` / `deferred`), and the
scraper handling each. Helpers: `direct_states()`, `fallback_states()`, `discom_level_states()`,
`coverage_summary()`. Current coverage: **6 direct, 29 fallback, 1 deferred.**

**Direct per-state scrapers** (`src/data/scrapers/state_sldc.py`; tables `state_demand` /
`state_demand_discom`; CLI `scripts/collect_states.py`): **Bihar, Punjab, Uttar Pradesh** (Phase 1) +
**Karnataka, Chhattisgarh** (Phase 2). Karnataka & Bihar carry DISCOM-level breakdowns. All verified live.

**Universal fallback** (`src/data/scrapers/state_fallback.py`; table `state_psp_daily`): Grid-India daily
PSP, one row per state per day for **all** states — the source for the 29 fallback states. The table
parser (`parse_psp_states`) is unit-verified; ⚠️ the live PDF download needs `report.grid-india.in`
reachable (it was unreachable from the build environment — run from an Indian network, or use the
Selenium path in `grid_india.py`). Scheduled nightly.

**Deferred: Gujarat** — `RealTime.php` is 403-gated and the homepage live widget was removed; needs the
official SLDC app API or GETCO access (not scrapable without it).

**TLS:** Bihar & Punjab need `SLDC_INSECURE_TLS=true` (broken gov TLS); UP/Karnataka/Chhattisgarh work as-is.

## TL;DR acquisition strategy

**Only ~5 jurisdictions are scrape-ready today; the rest need effort or fall back to national feeds.**
Don't build 36 bespoke scrapers — build **3 scraper types + 1 universal fallback**:

- **Type A — direct JSON/API** (easiest, better than Delhi): **Bihar, Punjab, Uttar Pradesh**.
- **Type B — static-HTML snapshot** (Delhi-like parse, poll to build history): **Karnataka** (also
  DISCOM-level + Excel history), **Chhattisgarh**, **Gujarat** (aggregate only).
- **Type C — report/by-date files & JS dashboards** (Excel/PDF parse or headless browser):
  **Telangana, Kerala, Maharashtra, Himachal Pradesh, Odisha, West Bengal** (+ Tamil Nadu unofficial).
- **Universal fallback** for the other ~20 (and as a cross-check for all): **`vidyutpravah.in`**
  (per-state live "Demand Met" MW, snapshot only) + **Grid-India NLDC daily PSP PDFs** (daily,
  state-wise peak/energy) + **CEA monthly** + compiled historical datasets.

**Weather/AQI scales for free:** the Open-Meteo archive/forecast/AQI APIs
(`src/data/scrapers/open_meteo.py`, `aqi.py`) take any lat/long and cover all of India — so the
weather half of the feature pipeline needs **zero** new scraping per state, just coordinates. The
demand series is the only hard part.

### Tiering (all 36 + DVC)
- **EASY (onboard now):** Delhi*, **Karnataka**, **Bihar**, **Punjab**, **Uttar Pradesh**, Chhattisgarh, Gujarat
- **MEDIUM (effort — headless browser / report parsing / by-date files):** Maharashtra, Himachal Pradesh,
  Telangana, Kerala, Odisha, West Bengal, Tamil Nadu
- **HARD (no usable public SLDC feed → fallback only):** Haryana, Rajasthan, Uttarakhand, J&K, Ladakh,
  Chandigarh, Madhya Pradesh, Goa, DNH&DD, Andhra Pradesh, Puducherry, Jharkhand, Sikkim, DVC,
  Assam, Meghalaya, Tripura, Manipur, Mizoram, Nagaland, Arunachal Pradesh, Andaman & Nicobar, Lakshadweep

\* Delhi already built. **Only Delhi, Karnataka, and Bihar offer a DISCOM-level breakdown** — most
states have a single distribution utility, so Delhi-style sub-region splits are impossible there.

---

## Master inventory

Columns: **Jurisdiction · SLDC/operator · Best data source · Granularity · DISCOM split · History · Method · Tier**

### Northern Region (NRLDC)
| Jurisdiction | SLDC / operator | Best source | Gran. | DISCOM | History | Method | Tier |
|---|---|---|---|---|---|---|---|
| **Delhi** (ref) | Delhi SLDC | delhisldc.org/Loaddata.aspx?mode=DD/MM/YYYY | 5-min | ✅ 5 | by-date URL to 2021 | static HTML | **EASY** |
| **Punjab** | PSLDC (PSTCL) | ✅LIVE `sldcapi.pstcl.org/wsDataService.asmx/dynamicData` (`loadMW`) | ~5–6 min | ✗ (single PSPCL) | current-day buffer; poll | no-auth JSON (.asmx); **broken TLS → verify=False** | **EASY** |
| **Uttar Pradesh** | UPSLDC (UPPTCL) | ✅LIVE `upsldc.org/realtimedatap` + `/assets/dataset/*.json` (`DEMAND_MW`) | snapshot | ✗ for demand (gen-side only) | monthly PDFs; poll for series | static JSON | **EASY** |
| **Himachal Pradesh** | HPSLDC (HPSEBL) | `hpsldc.com/real-time-hp-data/` | 15-min | ✗ | date filters + report files | **JS/AJAX (admin-ajax nonce), portal 401 → headless** | MEDIUM |
| **Haryana** | HVPNL | hvpn.org.in (Angular SPA, no data) | — | ✗ | — | none public | HARD |
| **Rajasthan** | RVPN | sldc.rajasthan.gov.in *(403 bot-filter + bad SSL; /mis/ unverified)* | ? | ? | ? | likely JS/login *(verify in India)* | HARD |
| **Uttarakhand** | PTCUL | uksldc.in **hosting-suspended**; sldc.uk.gov.in NXDOMAIN | — | ✗ | PTCUL equipment PDFs only | none now | HARD |
| **Jammu & Kashmir** | JKPTCL/PDD | all SLDC/PDD domains dead (jksldc.in NXDOMAIN) | — | ✗ | — | fallback only | HARD |
| **Ladakh** | LPDD | SLDC/REMC **under construction**; not even on vidyutpravah | — | ✗ | — | none (part of NR aggregate) | HARD |
| **Chandigarh** | UT Eng. Dept / CPDL | no SLDC portal (CPDL = billing SPA) | — | ✗ | — | fallback only | HARD |

### Western Region (WRLDC)
| Jurisdiction | SLDC / operator | Best source | Gran. | DISCOM | History | Method | Tier |
|---|---|---|---|---|---|---|---|
| **Chhattisgarh** | CSLDC (CSPTCL) | ✅LIVE `sldccg.com/gen.php` (CG demand + station gen) | snapshot (30-s refresh) | ✗ (single CSPDCL) | report PDFs; poll for series | static HTML + meta-refresh | **EASY** |
| **Gujarat** | SLDC Gujarat (GETCO) | ✅LIVE `sldcguj.com` index (`Gujarat Catered` MW) + `/RealTime.php` | snapshot | ✗ (aggregate only) | dated report PDFs | static HTML text; (SLDC app has a feed) | EASY–MED |
| **Maharashtra** | MSLDC (MSETCL) | `mahasldc.in/scada/reports/report2` (SCADA **image**) | snapshot | ✗ | ✅ by-date PDFs `mahasldc.in/wp-content/reports/` `dr0_/wr6_/mr6_` to ~2010 | image→OCR for live; PDF for history | MEDIUM |
| **Madhya Pradesh** | MP SLDC (MPPTCL) | mptransco.in (SCADA info page only) | — | ✗ | — | none public | HARD |
| **Goa** | Goa Electricity Dept | goaelectricity.gov.in (no live page) | — | ✗ | — | fallback only | HARD |
| **DNH & DD** (UT) | Elec. Dept (deemed; Torrent) | none | — | ✗ | — | fallback only | HARD |

### Southern Region (SRLDC)
| Jurisdiction | SLDC / operator | Best source | Gran. | DISCOM | History | Method | Tier |
|---|---|---|---|---|---|---|---|
| **Karnataka** | KSLDC (KPTCL) | ✅LIVE `kptclsldc.in` (demand + freq + gen + **DISCOMs**) | snapshot | ✅ BESCOM/HESCOM/GESCOM/CESC/MESCOM/Pavagada | ✅ daily load-curve Excel to 2011 `loadcurve.kptcl.net` | static ASP.NET HTML + Excel | **EASY** |
| **Telangana** | TGSLDC (TGTRANSCO) | `tgsldc.in/power-supply-position/` (+ Excel export `?from=&to=`) | daily peak | ✗ | ✅ by-date-range Excel | HTML table + Excel; homepage WAF-gated | MEDIUM |
| **Kerala** | KSLDC (KSEB) | `sldckerala.com/index.php?id=1` (System Statistics) | daily | ✗ | ✅ date calendar | PHP HTML (daily); live only as SCADA images | MEDIUM |
| **Tamil Nadu** | TN SLDC (TANTRANSCO) | official URL **unverified** (DNS fail); unofficial `energymap.in/states/tamil-nadu` | ? / snapshot | ✗ | via Grid-India/CEA | unofficial JS scrape / fallback | MED–HARD |
| **Andhra Pradesh** | APSLDC (APTRANSCO) | no reachable public SLDC URL (domains DNS/TLS-fail) | — | ✗ | — | fallback only | HARD |
| **Puducherry** (UT) | Elec. Dept | electricity.py.gov.in (no live page) | — | ✗ | — | fallback only | HARD |

### Eastern Region (ERLDC)
| Jurisdiction | SLDC / operator | Best source | Gran. | DISCOM | History | Method | Tier |
|---|---|---|---|---|---|---|---|
| **Bihar** | BSLDC (BSPTCL) | ✅LIVE `sldc.bsptcl.co.in:8086/api/SCADA/Get/GetAllSCADAData` + `...Datewise?date=DD-MonthName-YYYY` | **~1–2 min** | ✅ NBPDCL/SBPDCL | ✅ by-date API (recent months) | **no-auth JSON REST** | **EASY** |
| **Odisha** | SLDC Odisha (OPTCL) | `realtimedata.sldcorissa.org.in` **(login-gated)**; public reports at `sldcorissa.org.in/report/*` | ? / daily | ✅ in reports (TPCODL/TPWODL/TPNODL/TPSODL) | report PDFs | login for live; else report scrape | MED–HARD |
| **West Bengal** | WBSLDC (WBSETCL) | `wbsldc.in` (forecasts/monthly reports; no public live-actuals) | monthly / forecast | partial | reports | JS pages (check XHR); PDF | MEDIUM |
| **Jharkhand** | JSLDC (JUSNL) | sldcjharkhand.com (placeholder; "real-time" links out) | — | ✗ | annual reports | none public | HARD |
| **Sikkim** | Sikkim SLDC (E&P Dept) | power.sikkim.gov.in (no live page) | — | ✗ | — | fallback only | HARD |
| **DVC** (entity) | DVC LDC | dvc.gov.in/cms-web/sldc_web (info only) | — | ✗ | — | ERLDC/WBES fallback | HARD |

### North-Eastern Region (NERLDC) + island UTs
| Jurisdiction | SLDC / operator | Best source | Tier |
|---|---|---|---|
| **Assam** | Assam SLDC (AEGCL) | no public live page → vidyutpravah + Grid-India PSP | HARD (fallback) |
| **Meghalaya** | Meghalaya SLDC (MePTCL) | fallback only | HARD |
| **Tripura** | Tripura SLDC (TSECL) | tsecl.in (only annual projections) → fallback | HARD |
| **Manipur** | SLDC (MSPCL) | fallback only | HARD |
| **Mizoram** | SLDC (P&ED) | fallback only | HARD |
| **Nagaland** | SLDC (Dept of Power) | fallback only | HARD |
| **Arunachal Pradesh** | SLDC (Dept of Power) | internal 15-min ADMS (not public) → fallback; best RTI/data-share target in NE | HARD |
| **Andaman & Nicobar** (UT) | Elec. Dept (isolated grid) | not on national feeds; static figures only → RTI | HARD |
| **Lakshadweep** (UT) | Elec. Dept (isolated micro-grids) | essentially no public data → RTI | HARD |

*All 7 mainland NE states have a single distribution utility (no DISCOM split) and no scrapable live
page; the 2 island UTs are isolated grids absent from national real-time feeds.*

---

## The universal fallback layer (covers every state at low granularity)

1. **vidyutpravah.in** (Ministry of Power) — `https://vidyutpravah.in/state-data/<state-slug>` →
   current + previous-day **"Demand Met" (MW)**, free, no-auth, lightweight. ✅LIVE for several states.
   - Quirks: use the **non-www** host (`www.` serves a cert for grid-india.in). Some pages return the
     number as **inline HTML text** (scrapable), others **JS-inject** it (need headless), and some
     time out — behaviour is per-state and flaky. Snapshot only (no deep archive, no DISCOM).
2. **Grid-India / NLDC daily PSP report PDFs** — path pattern
   `report.grid-india.in/ReportData/Daily Report/PSP Report/<FY>/<Month Year>/<DD.MM.YY>_NLDC_PSP.pdf`
   → "Power Supply Position in States" table: per-state **daily peak demand met, energy met, shortage**.
   This is the authoritative by-date historical backbone. *(verify in India — host DNS-failed from US;
   already used by this project for `psp_daily`, see `src/data/scrapers/grid_india.py`.)*
3. **CEA monthly** peak/energy PDFs (cea.nic.in / npp.gov.in) — monthly state-wise peak demand/met/shortfall.
4. **Compiled historical datasets** — dataful.in (state-wise peak demand/met 1997→2024), indiastat,
   AIKOSH (aikosh.indiaai.gov.in).

## Regional LDC endpoints (per-region, mostly for fallback/cross-check)
- **ERLDC** — ✅LIVE no-auth JSON: `POST https://erldc.in/api/fetchAllEasternmapData` (body `{}`) →
  per-constituent daily peak (Bihar/Jharkhand/DVC/Odisha/West Bengal/Sikkim + ER total). Site itself is
  a React SPA; `/scada/telemetry` may expose richer socket.io feed (check in browser).
- **SRLDC** — `srldc.in` has a "Real Time Data" menu but pages are JS/login-rendered (no clean per-state
  table); best for **daily report PDFs** + energy-accounting "State-Utilities" datasets.
- **WRLDC** — real-time per-state exists only as a **JS dashboard** (`wrldc.in/js/apps_dashboard/index.html`)
  fed by a geo/referer-gated API; needs headless/API capture from an Indian IP.
- **NRLDC** — `nrldc.in/daily/daily-psp-report` (file-served) + login portal `reporting.nrldc.in`; no
  Delhi-like static per-state live page.
- **NERLDC** — `nerldc.in` (couldn't load from US); no evidence of a public scrapable per-state live table.

---

## Recommended build plan (phasing)
1. **Phase 1 — the 3 API states:** Bihar (JSON, DISCOM-level, by-date), Punjab (JSON), Uttar Pradesh
   (JSON). Lowest effort, highest quality. Bihar first — it's the single best source found (sub-2-min,
   DISCOM-level, by-date), richer than Delhi.
2. **Phase 2 — static-HTML snapshots:** Karnataka (also DISCOM + Excel history → effectively tied with
   Bihar for best), Chhattisgarh, Gujarat. Add a poller to accumulate history where only a snapshot exists.
3. **Phase 3 — report/by-date & headless:** Telangana + Kerala (by-date Excel/HTML), Maharashtra (PDF
   archive for history + OCR/feed for live), Himachal (headless browser), Odisha/West Bengal (reports;
   pursue Odisha SLDC login).
4. **Phase 4 — everyone else via the universal fallback:** one generic scraper for vidyutpravah +
   Grid-India NLDC PSP + CEA, covering the ~20 HARD states at snapshot/daily granularity. Accept
   single-number, no-DISCOM data. Pursue data-sharing/RTI for Arunachal (15-min ADMS) and Odisha (login).

### "Verify from an Indian IP" checklist (do before building)
- [ ] `report.grid-india.in` opens and current PSP folder path is correct (national historical backbone).
- [ ] Bihar API port **8086** is reachable from your scrape host; find earliest working `...Datewise` date.
- [ ] Open one Karnataka load-curve `.xls` → confirm time resolution (5/15/60-min).
- [ ] Pass the `tgsldc.in` `/security/` gate; check for a live Telangana SCADA section.
- [ ] Recover the real **Tamil Nadu** SLDC endpoint (SRPC quick-link + inspect energymap network calls).
- [ ] Find the current live **Andhra** APTRANSCO/APSLDC domain; check Rajasthan `sldc.rajasthan.gov.in/mis/`.
- [ ] HP: capture the `admin-ajax` action + file URL (DevTools → Network) or read `portal.hpsldc.com` (401).
- [ ] Inspect WRLDC/SRLDC/ERLDC JS dashboards' Network tab for public JSON/WS endpoints.
- [ ] Re-test suspended/dead NR sites (uksldc.in, jksldc.in) periodically; monitor Ladakh SLDC go-live.

## Reality check for the B2B vision
- **Delhi-grade (5-min + DISCOM + by-date) data is the exception, not the norm** — essentially Delhi,
  Bihar, Karnataka. Pitch/plan around this: ~5 states are forecastable at high fidelity now, ~7 more with
  effort, and the long tail only supports **daily/snapshot state-total** models via national feeds.
- Model design must therefore be **tiered by data availability**: 5-min/DISCOM models where data allows,
  down to daily-peak state-total models on the fallback layer.
- Data provenance/licensing varies (gov open data, SLDC ToS, privatised DISCOMs). Confirm terms before a
  commercial offering.

*Compiled from five regional research passes (NR/WR/SR/ER/NER), Oct 2026. All endpoints need Indian-IP
verification; ✅LIVE = fetched successfully during research.*

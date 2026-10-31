"""Background job: pre-2021 daily per-state PSP from Wayback archives of posoco.in
NLDC PSP PDFs. Fills the gap BELOW energymap's 2021-05 floor (dates < 2021-05-09).
Per-state 'Max Demand Met during the day' -> state_psp_daily, source=nldc_psp_wayback.
Insert-only (never overwrites energymap/SLDC rows). Resumable. Validates each PDF."""
import sys, io, re, time, collections
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import requests
import pdfplumber
from datetime import date
from src.data.db.session import get_session, create_tables
from src.data.db.models import StatePSPDaily
from sqlalchemy import func

UA = {"User-Agent": "Mozilla/5.0 (Gridalytics Research Project)"}
FLOOR = date(2021, 5, 9)  # energymap owns >= this; Wayback fills below

NAME2CODE = {"punjab": "punjab", "haryana": "haryana", "rajasthan": "rajasthan", "delhi": "delhi",
"uttar pradesh": "uttar_pradesh", "up": "uttar_pradesh", "uttarakhand": "uttarakhand",
"himachal pradesh": "himachal_pradesh", "hp": "himachal_pradesh", "jammu & kashmir": "jammu_kashmir",
"j&k": "jammu_kashmir", "chandigarh": "chandigarh", "chhattisgarh": "chhattisgarh", "gujarat": "gujarat",
"madhya pradesh": "madhya_pradesh", "mp": "madhya_pradesh", "maharashtra": "maharashtra", "goa": "goa",
"andhra pradesh": "andhra_pradesh", "telangana": "telangana", "karnataka": "karnataka", "kerala": "kerala",
"tamil nadu": "tamil_nadu", "pondicherry": "puducherry", "puducherry": "puducherry", "bihar": "bihar",
"jharkhand": "jharkhand", "odisha": "odisha", "orissa": "odisha", "west bengal": "west_bengal",
"wb": "west_bengal", "sikkim": "sikkim", "assam": "assam", "meghalaya": "meghalaya", "tripura": "tripura",
"manipur": "manipur", "mizoram": "mizoram", "nagaland": "nagaland", "arunachal pradesh": "arunachal_pradesh"}
NAMES = sorted(NAME2CODE, key=len, reverse=True)


def _cdx_page(rk):
    base = ("http://web.archive.org/cdx/search/cdx?url=posoco.in/download&matchType=prefix"
            "&fl=timestamp,original&filter=statuscode:200&collapse=urlkey&limit=1500"
            "&showResumeKey=true&output=text")
    u = base + (f"&resumeKey={rk}" if rk else "")
    for a in range(5):
        try:
            r = requests.get(u, headers=UA, timeout=90)
            if r.status_code == 200 and "<html" not in r.text[:40].lower():
                return r.text
        except Exception:
            pass
        time.sleep(4 * (a + 1))
    return None


def cdx_all():
    """Paginate all posoco.in/download 200-captures (avoids the broad-query 504),
    keep the nldc_psp ones. Returns list of [timestamp, original]."""
    rk, out, pages = None, [], 0
    while True:
        txt = _cdx_page(rk)
        if txt is None:
            print(f"  CDX page {pages} failed; stopping enumeration", flush=True)
            break
        lines = [l for l in txt.strip().split("\n") if l.strip()]
        rk = None
        if lines and len(lines[-1].split()) == 1:
            rk = lines[-1].split()[0]
            lines = lines[:-1]
        out += [ln.split() for ln in lines if "nldc_psp" in ln.lower()]
        pages += 1
        if pages % 5 == 0:
            print(f"  CDX pages={pages} psp_caps={len(out)}", flush=True)
        if not rk:
            break
        time.sleep(0.3)
    print(f"  CDX done: {pages} pages, {len(out)} nldc_psp captures", flush=True)
    return out


def parse_states(content):
    try:
        with pdfplumber.open(io.BytesIO(content)) as pdf:
            txt = "\n".join((p.extract_text() or "") for p in pdf.pages)
    except Exception:
        return {}
    out = {}
    for ln in txt.split("\n"):
        s = ln.strip()
        low = s.lower()
        for nm in NAMES:
            if low.startswith(nm + " "):
                mi = re.search(r"-?\d+(?:\.\d+)?", s[len(nm):])
                if mi:
                    code = NAME2CODE[nm]
                    val = float(mi.group())
                    if code not in out and 1 < val <= 80000:
                        out[code] = val
                break
    return out


def main():
    create_tables()
    byd = collections.defaultdict(list)
    for p in cdx_all():
        if len(p) < 2:
            continue
        ts, orig = p[0], p[1]
        m = re.search(r"/(\d{2})-(\d{2})-(\d{2})_nldc_psp", orig)
        if not m:
            continue
        dd, mm, yy = m.groups()
        try:
            d = date(2000 + int(yy), int(mm), int(dd))
        except ValueError:
            continue
        if d < FLOOR:
            byd[d].append((ts, orig))
    print(f"dates below floor {FLOOR}: {len(byd)}", flush=True)
    with get_session() as s:
        done = {r[0] for r in s.query(StatePSPDaily.date).filter(
            StatePSPDaily.source == "nldc_psp_wayback").distinct().all()}
        existing = set(s.query(StatePSPDaily.state_code, StatePSPDaily.date).all())
    todo = sorted(d for d in byd if d not in done)
    print(f"dates total={len(byd)} already={len(done)} todo={len(todo)}", flush=True)
    def fetch_ok(ts, orig):
        for _ in range(2):
            try:
                c = requests.get(f"https://web.archive.org/web/{ts}id_/{orig}",
                                 headers=UA, timeout=90).content
            except Exception:
                time.sleep(2)
                continue
            if (c[:5] == b"%PDF-" and b"%%EOF" in c[-5000:]
                    and len(c) != 1048576 and len(c) > 20000):
                return c
            return None  # fetched but truncated/invalid — try a different capture
        return None

    ins = 0
    bad = 0
    for k, d in enumerate(todo):
        # try captures earliest-first (contemporary beats the truncated 2024 re-crawl),
        # up to 5, until one is a complete, parseable PDF
        st = None
        for ts, orig in sorted(byd[d])[:5]:
            c = fetch_ok(ts, orig)
            if c is None:
                continue
            got = parse_states(c)
            if len(got) >= 10:
                st = got
                break
        if not st:
            bad += 1
            if k % 50 == 0:
                print(f"  [{k}/{len(todo)}] {d}: no clean capture (ins={ins}, bad={bad})", flush=True)
            continue
        with get_session() as s:
            for code, peak in st.items():
                if (code, d) in existing:
                    continue
                s.add(StatePSPDaily(state_code=code, date=d, peak_demand_met_mw=peak,
                                    source="nldc_psp_wayback"))
                existing.add((code, d))
                ins += 1
        if k % 50 == 0:
            print(f"  [{k}/{len(todo)}] {d}: {len(st)} states (ins={ins}, bad={bad})", flush=True)
        time.sleep(0.4)
    with get_session() as s:
        tot = s.query(func.count(StatePSPDaily.id)).filter(StatePSPDaily.source == "nldc_psp_wayback").scalar()
        mn = s.query(func.min(StatePSPDaily.date)).filter(StatePSPDaily.source == "nldc_psp_wayback").scalar()
        mx = s.query(func.max(StatePSPDaily.date)).filter(StatePSPDaily.source == "nldc_psp_wayback").scalar()
    print(f"DONE: inserted {ins} rows; bad/skipped files={bad}; wayback total={tot}, span {mn}..{mx}", flush=True)


if __name__ == "__main__":
    main()

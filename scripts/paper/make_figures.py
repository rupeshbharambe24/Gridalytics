"""Generate the three paper figures from the event-study analysis.

Re-runs scripts/paper/festival_eventstudy.py in-process (so the figures are
built from exactly the same regression, counterfactual, and data as the tables)
and writes publication PDFs into docs/paper/figures/:

  festival_effects_forest.pdf  - per-festival effect with 95% HAC CI (Table 1)
  peryear_stability.pdf        - Holi & Diwali per-year deviation, 2015-2024
  event_windows.pdf            - mean deviation around Diwali (d-3..+3) & Holi (d-2..+2)

  python scripts/paper/make_figures.py <db> <era5.json> \
         scripts/paper/festival_eventstudy.py docs/paper/figures
"""
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

DB, WX, ES, OUTDIR = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
OUT = Path(OUTDIR)
OUT.mkdir(parents=True, exist_ok=True)

# Run the event study in-process; it reads sys.argv[1:4] and leaves res/df/ev.
_tmp = tempfile.NamedTemporaryFile(suffix=".csv", delete=False).name
sys.argv = [ES, DB, WX, _tmp]
ns: dict = {"__name__": "_eventstudy"}
exec(compile(open(ES).read(), ES, "exec"), ns)
res, df, ev = ns["res"], ns["df"], ns["ev"]

plt.rcParams.update({
    "font.family": "serif", "font.size": 9, "figure.dpi": 150,
    "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "grid.alpha": 0.25, "grid.linewidth": 0.5,
    "savefig.bbox": "tight", "savefig.pad_inches": 0.03,
})
TEAL, AMBER, INDIGO = "#0f766e", "#d97706", "#4338ca"


def forest():
    r = res.sort_values("effect")
    y = np.arange(len(r))
    colors = [AMBER if e > 0 else TEAL for e in r.effect]
    fig, ax = plt.subplots(figsize=(5.4, 6.0))
    ax.errorbar(r.effect, y, xerr=[r.effect - r.lo, r.hi - r.effect], fmt="none",
                ecolor="#94a3b8", elinewidth=1.1, capsize=2, zorder=1)
    ax.scatter(r.effect, y, c=colors, s=26, zorder=2)
    ax.axvline(0, color="#475569", lw=0.9, ls="--")
    ax.set_yticks(y); ax.set_yticklabels(r.event)
    ax.set_xlabel("Effect on daily peak demand vs. counterfactual (%)")
    ax.set_ylim(-0.6, len(r) - 0.4)
    ax.margins(y=0)
    fig.savefig(OUT / "festival_effects_forest.pdf")
    plt.close(fig)


def peryear():
    years = list(range(2015, 2025))
    fig, ax = plt.subplots(figsize=(5.6, 3.3))
    for name, color, mk in [("Diwali", TEAL, "o"), ("Holi", INDIGO, "s")]:
        pts = {}
        for d in ev[ev.event == name].date:
            if d in df.index:
                pts[d.year] = df.dev.get(d, np.nan)
        xs = [y for y in years if y in pts]
        ax.plot(xs, [pts[y] for y in xs], marker=mk, color=color, lw=1.6, ms=4.5, label=name)
    ax.axhline(0, color="#475569", lw=0.8, ls="--")
    ax.set_xlabel("Year"); ax.set_ylabel("Deviation from counterfactual (%)")
    ax.set_xticks(years); ax.set_xticklabels(years, rotation=45, ha="right")
    ax.legend(frameon=False, loc="lower left")
    fig.savefig(OUT / "peryear_stability.pdf")
    plt.close(fig)


def windows():
    fig, ax = plt.subplots(figsize=(5.6, 3.3))
    for name, color, mk, lo, hi in [("Diwali", TEAL, "o", -3, 3), ("Holi", INDIGO, "s", -2, 2)]:
        dates = ev[ev.event == name].date
        ks = list(range(lo, hi + 1))
        means = []
        for k in ks:
            v = [df.dev.get(d + pd.Timedelta(days=k), np.nan) for d in dates]
            means.append(np.nanmean(v))
        ax.plot(ks, means, marker=mk, color=color, lw=1.6, ms=4.5, label=name)
    ax.axhline(0, color="#475569", lw=0.8, ls="--")
    ax.axvline(0, color="#cbd5e1", lw=0.8)
    ax.set_xlabel("Days relative to festival day (d0)")
    ax.set_ylabel("Mean deviation from counterfactual (%)")
    ax.set_xticks(range(-3, 4))
    ax.legend(frameon=False, loc="lower right")
    fig.savefig(OUT / "event_windows.pdf")
    plt.close(fig)


forest(); peryear(); windows()
print("figures written to", OUT)
for p in sorted(OUT.glob("*.pdf")):
    print("  ", p.name, f"{p.stat().st_size//1024} KB")

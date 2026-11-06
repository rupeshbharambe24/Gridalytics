"""Summarize trained state models (models/states/*/*/served.json) as a markdown table.

Usage:
  python scripts/summarize_state_models.py            # print the table
  python scripts/summarize_state_models.py --csv out.csv
"""

import sys
import json
import argparse
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.data.scrapers.states import STATES_BY_CODE

MODELS = Path(__file__).parent.parent / "models" / "states"


def load() -> pd.DataFrame:
    rows = []
    for p in sorted(MODELS.glob("*/*/served.json")):
        m = json.loads(p.read_text())
        if "seasonal_naive_mape" not in m:   # trained before baselines were scored on CV folds
            continue
        st = STATES_BY_CODE.get(m["state"])
        rows.append({
            "state": st.name if st else m["state"],
            "region": st.region.value if st else "",
            "resolution": m["resolution"],
            "source": m.get("source", "state_demand"),
            "data": f'{m.get("data_start", "?")} – {m.get("data_end", "?")}',
            "rows": m.get("rows"),
            # report the model actually served (champion may have fallen back on save)
            "served": m["served_model"],
            "cv_mape": m["cv_mape"][m["served_model"]],
            "persistence": m["persistence_mape"],
            "seasonal_naive": m["seasonal_naive_mape"],
        })
        rows[-1]["skill"] = 1 - rows[-1]["cv_mape"] / rows[-1]["persistence"]
    return pd.DataFrame(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv")
    args = ap.parse_args()
    df = load().sort_values(["resolution", "region", "state"])
    if args.csv:
        df.to_csv(args.csv, index=False)
    fmt = df.assign(
        cv_mape=df.cv_mape.map("{:.2f}%".format),
        persistence=df.persistence.map("{:.2f}%".format),
        seasonal_naive=df.seasonal_naive.map("{:.2f}%".format),
        skill=df.skill.map("{:+.0%}".format),
    )
    cols = list(fmt.columns)
    print("| " + " | ".join(cols) + " |")
    print("|" + "|".join("---" for _ in cols) + "|")
    for r in fmt.itertuples(index=False):
        print("| " + " | ".join(str(v) for v in r) + " |")


if __name__ == "__main__":
    main()

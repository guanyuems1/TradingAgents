"""Build the datasets used by btc_leadlag_analysis.py.

Two independent sources, chosen because they are reachable from restricted
environments (git + npm registry only) and cross-validate each other:

1. Coin Metrics community data (github.com/coinmetrics/data, master branch).
   The community CSVs keep full USD price history only for BTC/ETH
   (PriceUSD). For SOL/HYPE they keep CapMrktEstUSD, which empirically equals
   `piecewise-constant estimated supply x end-of-day close` (BTC's implied
   supply from CapMrktEstUSD/PriceUSD is constant to 0.002%/day; HYPE's
   implied supply against the 7 days of published ReferenceRate is exactly
   flat at 238.4M). Log-diffs of CapMrktEstUSD are therefore daily price
   returns, except on rare supply-estimate revision days. One HYPE revision
   day was identified (2025-08-28: -23.8% vs BTC +1.1% with no corroborating
   market event, while HYPE traded ~$51 on 8/27 and made a new high three
   weeks later) and is flagged for exclusion.
   GitHub mirror last updated 2026-05-24 -> series end 2026-05-23.

2. fawazahmed0/currency-api daily npm releases (registry.npmjs.org,
   package `@fawazahmed0/currency-api`, one version per date, 2024.3.2 ..
   today). Each tarball's `v1/currencies/btc.min.json` snapshot (~00:00-02:00
   UTC) yields BTC/USD plus BTC/ETH and BTC/SOL crosses taken at the same
   instant, so the BTC-SOL pair is timing-consistent. The 2025-12-06 release
   carries a corrupted BTC rate and is dropped. HYPE and LIT are not in this
   package's (frozen, 341-code) currency list.

Cross-checks performed when this dataset was assembled (2026-08-23):
  - BTC daily returns, CM vs currency-api (aligned api[D+1] ~ CM close[D]):
    corr 0.91; the gap is the api's irregular intra-night sampling jitter,
    which is common to all currencies within one snapshot.
  - SOL returns, CM-mcap-derived vs currency-api: corr 0.92 (same level as
    the BTC cross-source corr, i.e. the mcap derivation adds no extra noise).
  - Current-price sanity checks against public quote pages via web search.

LIT = Lighter (TGE 2025-12-30), per the user's HYPE/perp-DEX context, NOT
Litentry (Coin Metrics carries that as `lit`; Lighter is `lit_lighter`).
For Lighter only 7 daily reference prices exist (2026-05-18..24) plus the
volume history and a handful of web anchors -> descriptive treatment only.

Usage:
  python build_dataset.py --cm-clone /path/to/coinmetrics-data \
                          --snapshot-dir /path/to/capi-json-dir
where snapshot-dir holds one `<version>.json` per npm release, produced by:
  curl https://registry.npmjs.org/@fawazahmed0/currency-api/-/currency-api-<v>.tgz \
    | tar xzO package/v1/currencies/btc.min.json > <v>.json
"""

import argparse
import glob
import json
import os

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "data")

BAD_API_DATES = ["2025-12-06"]          # corrupted btc rate in that release
HYPE_SUPPLY_STEP_DAYS = ["2025-08-28"]  # CM est-supply revision, not a price move


def build_api_panel(snapshot_dir):
    rows = []
    for fp in sorted(glob.glob(os.path.join(snapshot_dir, "*.json"))):
        d = json.load(open(fp))
        b = d["btc"]
        rows.append({"date": d["date"], "btc_usd": b["usd"],
                     "eth_usd": b["usd"] / b["eth"],
                     "sol_usd": b["usd"] / b["sol"]})
    api = (pd.DataFrame(rows).assign(date=lambda x: pd.to_datetime(x["date"]))
           .set_index("date").sort_index())
    api.loc[api.index.isin(pd.to_datetime(BAD_API_DATES)),
            ["btc_usd", "eth_usd"]] = np.nan
    api.round(6).to_csv(os.path.join(OUT, "daily_panel_api.csv"))
    return api


def build_cm_panel(cm_clone):
    csvdir = os.path.join(cm_clone, "csv")

    def load(name):
        df = pd.read_csv(os.path.join(csvdir, f"{name}.csv"), low_memory=False)
        df["time"] = pd.to_datetime(df["time"])
        return df.set_index("time")

    btc, eth = load("btc"), load("eth")
    sol, hype, litl = load("sol"), load("hype"), load("lit_lighter")

    cm = pd.DataFrame({
        "btc": btc["PriceUSD"], "eth": eth["PriceUSD"],
        "sol_mcap": sol["CapMrktEstUSD"], "hype_mcap": hype["CapMrktEstUSD"],
        "btc_vol": btc["volume_reported_spot_usd_1d"],
        "sol_vol": sol["volume_reported_spot_usd_1d"],
        "hype_vol": hype["volume_reported_spot_usd_1d"],
    }).sort_index().loc["2019-01-01":].dropna(how="all")
    cm["hype_supply_step_flag"] = 0
    cm.loc[cm.index.isin(pd.to_datetime(HYPE_SUPPLY_STEP_DAYS)),
           "hype_supply_step_flag"] = 1
    cm.to_csv(os.path.join(OUT, "daily_panel_cm.csv"))

    litl.to_csv(os.path.join(OUT, "lit_lighter_cm.csv"))
    return cm


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cm-clone", required=True)
    ap.add_argument("--snapshot-dir", required=True)
    args = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    api = build_api_panel(args.snapshot_dir)
    cm = build_cm_panel(args.cm_clone)
    print(f"api panel {api.shape} {api.index.min().date()}..{api.index.max().date()}")
    print(f"cm  panel {cm.shape} {cm.index.min().date()}..{cm.index.max().date()}")


if __name__ == "__main__":
    main()

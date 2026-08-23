"""BTC -> alt (HYPE / LIT / SOL) daily lead-lag and alpha study.

Answers: does BTC act as a leading indicator for HYPE, LIT (Lighter) and SOL
at the daily horizon, and does a "BTC moved, buy the alt" rule earn alpha
after costs?

Data (see build_dataset.py):
  data/daily_panel_cm.csv   Coin Metrics community data, end-of-day UTC closes
                            (BTC/ETH = PriceUSD; SOL/HYPE = CapMrktEstUSD which
                            equals piecewise-constant est. supply x EOD close,
                            so its log-diffs are price returns except on
                            supply-revision days, which are flagged).
                            Window: 2019-01-01 .. 2026-05-23.
  data/daily_panel_api.csv  fawazahmed0/currency-api daily snapshots (~00:00
                            UTC), BTC/ETH/SOL. Window: 2024-03-02 .. 2026-08-23.
                            BTC and SOL come from the same snapshot each day,
                            so the pair is timing-consistent.
  data/lit_lighter_cm.csv   LIT (Lighter): only 7 daily reference prices
                            (2026-05-18..24) plus daily volume history.
  data/lit_anchor_points.csv  sparse LIT price anchors (TGE/ATL/web).

Pairs are always built within one source so both legs share the same daily
timestamp convention (a constant cross-source offset would fabricate lead-lag).

Usage: python btc_leadlag_analysis.py [--json results.json]
"""

import argparse
import json
import os
import warnings

import numpy as np
import pandas as pd
import statsmodels.api as sm
from statsmodels.tsa.stattools import grangercausalitytests

warnings.filterwarnings("ignore")

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")

ANN = 365  # crypto trades every day


# --------------------------------------------------------------------------- #
# data loading
# --------------------------------------------------------------------------- #

def load_panels():
    cm = pd.read_csv(os.path.join(DATA, "daily_panel_cm.csv"),
                     parse_dates=["time"], index_col="time").sort_index()
    api = pd.read_csv(os.path.join(DATA, "daily_panel_api.csv"),
                      parse_dates=["date"], index_col="date").sort_index()

    cm_r = pd.DataFrame({
        "btc": np.log(cm["btc"]).diff(),
        "eth": np.log(cm["eth"]).diff(),
        "sol": np.log(cm["sol_mcap"]).diff(),
        "hype": np.log(cm["hype_mcap"]).diff(),
    })
    # supply-estimate revision days: the mcap series steps although price didn't
    cm_r.loc[cm["hype_supply_step_flag"] == 1, "hype"] = np.nan

    api_r = pd.DataFrame({
        "btc": np.log(api["btc_usd"]).diff(),
        "eth": np.log(api["eth_usd"]).diff(),
        "sol": np.log(api["sol_usd"]).diff(),
    })
    return cm, api, cm_r, api_r


# --------------------------------------------------------------------------- #
# statistics
# --------------------------------------------------------------------------- #

def ccf_table(x, y, max_lag=7):
    """corr(x_t, y_{t+k}) for k=-max_lag..max_lag. k>0 means x leads y."""
    rows = []
    for k in range(-max_lag, max_lag + 1):
        j = pd.DataFrame({"x": x, "y": y.shift(-k)}).dropna()
        n = len(j)
        c = j["x"].corr(j["y"])
        rows.append({"lag": k, "corr": c, "n": n,
                     "se": 1 / np.sqrt(n), "t": c * np.sqrt(n)})
    return pd.DataFrame(rows).set_index("lag")


def granger_pvals(x, y, maxlag=5):
    """p-values that x does NOT Granger-cause y, for lags 1..maxlag."""
    j = pd.DataFrame({"y": y, "x": x}).dropna()
    try:
        import contextlib, io
        with contextlib.redirect_stdout(io.StringIO()):
            res = grangercausalitytests(j[["y", "x"]], maxlag=maxlag)
        return {str(lag): round(float(res[lag][0]["ssr_ftest"][1]), 4)
                for lag in res}
    except Exception:
        return {}


def nw_reg(dep, regs, lags=5):
    """OLS with Newey-West errors; returns dict of coef, t, p per regressor."""
    j = pd.concat([dep] + regs, axis=1).dropna()
    if len(j) < 30:
        return None
    yv = j.iloc[:, 0]
    X = sm.add_constant(j.iloc[:, 1:])
    m = sm.OLS(yv, X).fit(cov_type="HAC", cov_kwds={"maxlags": lags})
    return {name: {"coef": float(m.params[name]), "t": float(m.tvalues[name]),
                   "p": float(m.pvalues[name])} for name in m.params.index}


def event_study(btc, alt, thresholds=(0.02, 0.03, -0.02, -0.03),
                horizons=(1, 2, 3, 5)):
    """Forward alt returns after big BTC days (event day excluded)."""
    out = []
    j = pd.DataFrame({"btc": btc, "alt": alt}).dropna()
    uncond = {h: j["alt"].rolling(h).sum().shift(-h).dropna().mean()
              for h in horizons}
    for thr in thresholds:
        ev = j.index[j["btc"] > thr] if thr > 0 else j.index[j["btc"] < thr]
        row = {"event": f"BTC {'>' if thr > 0 else '<'} {thr:+.0%}",
               "n_events": len(ev),
               "same_day_alt": float(j.loc[ev, "alt"].mean()) if len(ev) else np.nan}
        for h in horizons:
            fwd = j["alt"].rolling(h).sum().shift(-h)  # t+1..t+h cum return
            vals = fwd.reindex(ev).dropna()
            if len(vals) < 5:
                row[f"fwd{h}d"] = np.nan
                row[f"fwd{h}d_t"] = np.nan
                row[f"fwd{h}d_excess"] = np.nan
                continue
            m, s = vals.mean(), vals.std(ddof=1) / np.sqrt(len(vals))
            row[f"fwd{h}d"] = float(m)
            row[f"fwd{h}d_t"] = float(m / s)
            row[f"fwd{h}d_excess"] = float(m - uncond[h])
        out.append(row)
    return pd.DataFrame(out).set_index("event")


def backtest(btc, alt, rule, cost_bps=0.0):
    """Daily strategy: position for day t+1 decided from info through day t.

    rule(btc_returns) -> position series in [ -1 .. 1 ] indexed like btc.
    Execution at the close that ends day t (so the alt return earned is day
    t+1); costs charged on position changes.
    """
    j = pd.DataFrame({"btc": btc, "alt": alt}).dropna()
    pos = rule(j["btc"]).shift(1).fillna(0.0)     # earn day t+1 with signal(t)
    gross = pos * j["alt"]
    turn = pos.diff().abs().fillna(pos.abs())
    net = gross - turn * cost_bps / 1e4
    eq = net.cumsum()
    years = len(j) / ANN
    cagr = float(np.expm1(eq.iloc[-1]) ** (1 / years) - 1) if years > 0 and eq.iloc[-1] > -1 else np.nan
    vol = float(net.std() * np.sqrt(ANN))
    sharpe = float(net.mean() / net.std() * np.sqrt(ANN)) if net.std() > 0 else np.nan
    dd = float((eq - eq.cummax()).min())
    exposure = float((pos != 0).mean())
    hit = float((net[pos != 0] > 0).mean()) if (pos != 0).any() else np.nan
    # alpha vs buy & hold of the alt (daily OLS, HAC)
    reg = nw_reg(net, [j["alt"].rename("bh")])
    alpha_ann = reg["const"]["coef"] * ANN if reg else np.nan
    alpha_t = reg["const"]["t"] if reg else np.nan
    bh_total = float(j["alt"].sum())
    return {"total_logret": float(eq.iloc[-1]), "bh_alt_logret": bh_total,
            "ann_vol": vol, "sharpe": sharpe, "max_dd_log": dd,
            "exposure": exposure, "hit_rate": hit,
            "n_switches": int((turn > 0).sum()),
            "alpha_ann_vs_bh": float(alpha_ann), "alpha_t": float(alpha_t),
            "cagr": cagr}


RULES = {
    "L_btc_up_1d": lambda b: (b > 0).astype(float),
    "L_btc_up_2pct": lambda b: (b > 0.02).astype(float),
    "L_btc_up_2pct_hold3": lambda b: ((b > 0.02).rolling(3, min_periods=1).max()).astype(float),
    "LS_btc_sign": lambda b: np.sign(b),
    "L_btc_mom_3d": lambda b: (b.rolling(3).sum() > 0).astype(float),
    "L_btc_dip_2pct": lambda b: (b < -0.02).astype(float),   # mean-reversion buy
}


# --------------------------------------------------------------------------- #
# report
# --------------------------------------------------------------------------- #

def pair_report(name, btc, alt, results, max_lag=7):
    res = {}
    j = pd.DataFrame({"btc": btc, "alt": alt}).dropna()
    res["n"] = len(j)
    res["window"] = [str(j.index.min().date()), str(j.index.max().date())]
    res["contemporaneous_corr"] = float(j["btc"].corr(j["alt"]))
    beta = nw_reg(j["alt"], [j["btc"].rename("btc")])
    res["beta"] = beta["btc"] if beta else None
    res["alt_vol_ann"] = float(j["alt"].std() * np.sqrt(ANN))
    res["btc_autocorr1"] = float(j["btc"].autocorr(1))
    res["alt_autocorr1"] = float(j["alt"].autocorr(1))

    cc = ccf_table(j["btc"], j["alt"], max_lag)
    res["ccf"] = {int(k): {"corr": round(float(v["corr"]), 4),
                           "t": round(float(v["t"]), 2)}
                  for k, v in cc.iterrows()}

    res["granger_btc_to_alt_p"] = granger_pvals(j["btc"], j["alt"])
    res["granger_alt_to_btc_p"] = granger_pvals(j["alt"], j["btc"])

    pred = nw_reg(j["alt"].shift(-1), [j["btc"].rename("btc_t"),
                                       j["alt"].rename("alt_t")])
    res["predictive_reg_t+1"] = pred

    ev = event_study(j["btc"], j["alt"])
    res["event_study"] = json.loads(ev.to_json(orient="index"))

    res["backtests"] = {}
    for rn, rule in RULES.items():
        res["backtests"][rn] = {
            f"cost{c}bps": backtest(j["btc"], j["alt"], rule, c)
            for c in (0, 10, 20)}

    # subsample stability of lag-1 correlation and predictive t-stat
    halves = np.array_split(j.index, 2)
    res["subsamples"] = {}
    for tag, idx in zip(("H1", "H2"), halves):
        sj = j.loc[idx]
        cc1 = sj["btc"].corr(sj["alt"].shift(-1))
        res["subsamples"][tag] = {
            "window": [str(idx.min().date()), str(idx.max().date())],
            "corr0": round(float(sj["btc"].corr(sj["alt"])), 3),
            "lag1_corr": round(float(cc1), 3),
            "lag1_t": round(float(cc1 * np.sqrt(len(sj))), 2)}

    results[name] = res


def extras_report(name, btc, alt, results):
    """Weekly-horizon lead-lag, up/down beta, and the BTC->alt rotation test."""
    res = {}
    j = pd.DataFrame({"btc": btc, "alt": alt}).dropna()

    # weekly (7d, Sunday-anchored) cross-correlation: does a strong BTC week
    # predict the alt's next weeks ("rotation" folk thesis)?
    w = j.resample("W-SUN").sum(min_count=4).dropna()
    cc = ccf_table(w["btc"], w["alt"], max_lag=4)
    res["weekly_ccf"] = {int(k): {"corr": round(float(v["corr"]), 3),
                                  "t": round(float(v["t"]), 2), "n": int(v["n"])}
                         for k, v in cc.iterrows()}

    # conditional beta: alt response on BTC up-days vs down-days
    up, dn = j[j["btc"] > 0], j[j["btc"] < 0]
    res["beta_up"] = float(up["alt"].cov(up["btc"]) / up["btc"].var())
    res["beta_down"] = float(dn["alt"].cov(dn["btc"]) / dn["btc"].var())

    # rotation regression: trailing 21d BTC return -> forward 21d alt-minus-btc
    trail = j["btc"].rolling(21).sum()
    fwd_rel = (j["alt"] - j["btc"]).rolling(21).sum().shift(-21)
    reg = nw_reg(fwd_rel.rename("fwd_rel21"), [trail.rename("btc_trail21")],
                 lags=25)
    res["rotation_reg_21d"] = reg
    q = pd.qcut(trail.dropna(), 4, labels=["Q1_weak", "Q2", "Q3", "Q4_strong"])
    res["rotation_quartiles_fwd_rel21_pct"] = {
        str(k): round(float(v) * 100, 1)
        for k, v in fwd_rel.groupby(q).mean().items()}

    # rolling 60d correlation (saved for figures)
    roll = j["btc"].rolling(60, min_periods=45).corr(j["alt"]).dropna()
    roll.to_csv(os.path.join(DATA, f"rolling60_corr_{name}.csv"),
                header=["corr60"])
    res["rolling60_last"] = round(float(roll.iloc[-1]), 3)
    res["rolling60_min"] = round(float(roll.min()), 3)
    res["rolling60_max"] = round(float(roll.max()), 3)
    results[name]["extras"] = res


def lit_report(results):
    lit = pd.read_csv(os.path.join(DATA, "lit_lighter_cm.csv"),
                      parse_dates=["time"], index_col="time")
    api = pd.read_csv(os.path.join(DATA, "daily_panel_api.csv"),
                      parse_dates=["date"], index_col="date").sort_index()
    anchors = pd.read_csv(os.path.join(DATA, "lit_anchor_points.csv"),
                          parse_dates=["date"])
    res = {"note": "LIT (Lighter) has only 7 daily reference prices "
                   "(2026-05-18..24) in accessible data; the rest are sparse "
                   "anchors. No statistical lead-lag test is possible."}
    p7 = lit["ReferenceRateUSD"].dropna()
    r_lit = np.log(p7).diff().dropna()
    r_btc = np.log(api["btc_usd"]).diff().shift(-1).reindex(r_lit.index)
    res["seven_day_window"] = {
        "lit_prices": {str(k.date()): round(float(v), 4) for k, v in p7.items()},
        "lit_vs_btc_daily": {str(k.date()): [round(float(r_lit[k]) * 100, 2),
                                             round(float(r_btc[k]) * 100, 2)]
                             for k in r_lit.index}}
    # episode comparison at anchor dates
    ep = []
    a = anchors.set_index("date")["lit_usd"]
    btc_px = api["btc_usd"].dropna()
    for i in range(1, len(a)):
        d0, d1 = a.index[i - 1], a.index[i]
        b0 = btc_px.asof(d0)
        b1 = btc_px.asof(d1)
        ep.append({"from": str(d0.date()), "to": str(d1.date()),
                   "lit_ret_pct": round((a.iloc[i] / a.iloc[i - 1] - 1) * 100, 1),
                   "btc_ret_pct": round((b1 / b0 - 1) * 100, 1)})
    res["anchor_episodes"] = ep
    v = lit["volume_reported_spot_usd_1d"].dropna()
    res["volume"] = {"first": str(v.index.min().date()),
                     "last": str(v.index.max().date()),
                     "mean_usd_m": round(float(v.mean()) / 1e6, 1),
                     "last_usd_m": round(float(v.iloc[-1]) / 1e6, 1)}
    results["LIT_lighter"] = res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default=os.path.join(HERE, "results.json"))
    args = ap.parse_args()

    cm, api, cm_r, api_r = load_panels()
    results = {"meta": {
        "cm_window": [str(cm_r.dropna(how="all").index.min().date()),
                      str(cm_r.index.max().date())],
        "api_window": [str(api_r.index.min().date()),
                       str(api_r.index.max().date())],
        "conventions": "CM = end-of-day UTC close; API = ~00:00 UTC snapshot. "
                       "Pairs are always within one source.",
    }}

    # HYPE vs BTC on the CM panel (both EOD closes)
    pair_report("HYPE_vs_BTC_cm", cm_r["btc"], cm_r["hype"], results)
    extras_report("HYPE_vs_BTC_cm", cm_r["btc"], cm_r["hype"], results)
    # SOL vs BTC on the API panel (freshest, through 2026-08-23)
    pair_report("SOL_vs_BTC_api", api_r["btc"], api_r["sol"], results)
    extras_report("SOL_vs_BTC_api", api_r["btc"], api_r["sol"], results)
    # SOL vs BTC long sample on CM (2020-04 ..)
    pair_report("SOL_vs_BTC_cm_long", cm_r["btc"], cm_r["sol"], results)
    extras_report("SOL_vs_BTC_cm_long", cm_r["btc"], cm_r["sol"], results)
    # ETH control
    pair_report("ETH_vs_BTC_api", api_r["btc"], api_r["eth"], results)
    extras_report("ETH_vs_BTC_api", api_r["btc"], api_r["eth"], results)
    # LIT descriptive
    lit_report(results)

    def jsonable(o):
        if isinstance(o, dict):
            return {str(k): jsonable(v) for k, v in o.items()}
        if isinstance(o, (list, tuple)):
            return [jsonable(v) for v in o]
        if isinstance(o, (np.integer,)):
            return int(o)
        if isinstance(o, (np.floating,)):
            return float(o)
        return o

    with open(args.json, "w") as f:
        json.dump(jsonable(results), f, indent=1, default=str)
    print(f"wrote {args.json}")

    # console digest
    for k in ("HYPE_vs_BTC_cm", "SOL_vs_BTC_api", "SOL_vs_BTC_cm_long",
              "ETH_vs_BTC_api"):
        r = results[k]
        print(f"\n=== {k}  n={r['n']}  {r['window'][0]}..{r['window'][1]}")
        print(f"  corr0={r['contemporaneous_corr']:.3f}  "
              f"beta={r['beta']['coef']:.2f} (t={r['beta']['t']:.1f})")
        cc = r["ccf"]
        line = "  CCF k=-3..+3: " + "  ".join(
            f"{k2:+d}:{cc[k2]['corr']:+.3f}({cc[k2]['t']:+.1f})"
            for k2 in range(-3, 4))
        print(line)
        print(f"  granger btc->alt p (lag1..5): {r['granger_btc_to_alt_p']}")
        print(f"  granger alt->btc p (lag1..5): {r['granger_alt_to_btc_p']}")
        pr = r["predictive_reg_t+1"]
        if pr:
            print(f"  pred t+1: btc_t coef={pr['btc_t']['coef']:+.3f} "
                  f"t={pr['btc_t']['t']:+.2f} | alt_t coef={pr['alt_t']['coef']:+.3f} "
                  f"t={pr['alt_t']['t']:+.2f}")
        print("  subsamples:", r["subsamples"])
        for rn in RULES:
            b0 = r["backtests"][rn]["cost0bps"]
            b10 = r["backtests"][rn]["cost10bps"]
            print(f"  BT {rn:22s} gross={b0['total_logret']:+.2f} "
                  f"(B&H {b0['bh_alt_logret']:+.2f}) sharpe={b0['sharpe']:+.2f} "
                  f"alpha_ann={b0['alpha_ann_vs_bh']:+.1%} (t={b0['alpha_t']:+.1f}) "
                  f"| net10bps={b10['total_logret']:+.2f}")


if __name__ == "__main__":
    main()

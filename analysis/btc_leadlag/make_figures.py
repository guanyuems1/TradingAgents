"""Figures for the BTC lead-lag study. Reads data/ and writes figures/*.png."""

import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
FIGS = os.path.join(HERE, "figures")

# reference dataviz palette (light mode)
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
BASE = "#c3c2b7"
BLUE = "#2a78d6"
ORANGE = "#eb6834"
RED = "#e34948"

plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE,
    "savefig.facecolor": SURFACE, "font.family": "sans-serif",
    "font.size": 10, "text.color": INK, "axes.edgecolor": BASE,
    "axes.labelcolor": INK2, "xtick.color": MUTED, "ytick.color": MUTED,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8,
    "axes.axisbelow": True, "axes.spines.top": False,
    "axes.spines.right": False, "axes.spines.left": False,
})


def load():
    cm = pd.read_csv(os.path.join(DATA, "daily_panel_cm.csv"),
                     parse_dates=["time"], index_col="time").sort_index()
    api = pd.read_csv(os.path.join(DATA, "daily_panel_api.csv"),
                      parse_dates=["date"], index_col="date").sort_index()
    cm_r = pd.DataFrame({
        "btc": np.log(cm["btc"]).diff(),
        "hype": np.log(cm["hype_mcap"]).diff(),
        "sol": np.log(cm["sol_mcap"]).diff(),
    })
    cm_r.loc[cm["hype_supply_step_flag"] == 1, "hype"] = np.nan
    api_r = pd.DataFrame({
        "btc": np.log(api["btc_usd"]).diff(),
        "sol": np.log(api["sol_usd"]).diff(),
        "eth": np.log(api["eth_usd"]).diff(),
    })
    return cm_r, api_r


def ccf(x, y, k):
    j = pd.DataFrame({"x": x, "y": y.shift(-k)}).dropna()
    return j["x"].corr(j["y"]), len(j)


def fig_ccf(cm_r, api_r):
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2), sharey=True)
    hype_uni, splice = unified_hype(cm_r)
    hype_btc = api_r["btc"] if splice is not None else cm_r["btc"]
    hype_title = ("HYPE vs BTC  (daily, Dec 2024 - Aug 2026)" if splice is not None
                  else "HYPE vs BTC  (daily, Dec 2024 - May 2026)")
    panels = [(hype_title, hype_btc, hype_uni),
              ("SOL vs BTC  (daily, Mar 2024 - Aug 2026)",
               api_r["btc"], api_r["sol"])]
    lags = range(-7, 8)
    for ax, (title, b, a) in zip(axes, panels):
        vals, ns = zip(*[ccf(b, a, k) for k in lags])
        band = 1.96 / np.sqrt(min(ns))
        ax.axhspan(-band, band, color=GRID, alpha=0.55, zorder=0)
        colors = [BLUE if v >= 0 else RED for v in vals]
        ax.bar(list(lags), vals, width=0.62, color=colors, zorder=3)
        ax.axhline(0, color=BASE, lw=1)
        for k, v in zip(lags, vals):
            if k == 0:
                ax.annotate(f"{v:+.2f}", (k, v), xytext=(0, 3),
                            textcoords="offset points", ha="center",
                            fontsize=9, color=INK2)
            if k == 1:
                ax.annotate(f"{v:+.2f}", (k, min(v, 0)), xytext=(0, -12),
                            textcoords="offset points", ha="center",
                            fontsize=9, color=INK2)
        ax.set_title(title, fontsize=10.5, color=INK, loc="left")
        ax.set_xlabel("lag k (days)  ·  k>0 : BTC leads by k days")
        ax.set_xticks(list(lags))
    axes[0].set_ylabel("corr( BTC day t , alt day t+k )")
    axes[0].set_ylim(-0.15, 0.9)
    fig.text(0.01, 0.012,
             "Shaded band = 95% no-correlation interval. Same-day bar is large; "
             "every other lag sits at or inside the band -> co-movement, not lead.",
             fontsize=8.5, color=MUTED)
    fig.tight_layout(rect=(0, 0.045, 1, 1))
    fig.savefig(os.path.join(FIGS, "fig1_ccf_daily.png"), dpi=150)
    plt.close(fig)


def fig_event(cm_r, api_r):
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2), sharey=True)
    hype_uni, splice = unified_hype(cm_r)
    hype_btc = api_r["btc"] if splice is not None else cm_r["btc"]
    panels = [("HYPE after big BTC days", hype_btc, hype_uni),
              ("SOL after big BTC days", api_r["btc"], api_r["sol"])]
    for ax, (title, b, a) in zip(axes, panels):
        j = pd.DataFrame({"b": b, "a": a}).dropna()
        for thr, color, lab in [(0.03, ORANGE, "after BTC > +3%"),
                                (-0.03, BLUE, "after BTC < -3%")]:
            ev = j.index[j["b"] > thr] if thr > 0 else j.index[j["b"] < thr]
            path = [0.0]
            for h in (1, 2, 3, 4, 5):
                fwd = j["a"].rolling(h).sum().shift(-h)
                path.append(fwd.reindex(ev).dropna().mean() * 100)
            ax.plot(range(6), path, color=color, lw=2, marker="o", ms=5,
                    label=f"{lab}  (n={len(ev)})")
            ax.annotate(f"{path[-1]:+.1f}%", (5, path[-1]),
                        xytext=(6, -3), textcoords="offset points",
                        fontsize=9, color=color)
        ax.axhline(0, color=BASE, lw=1)
        ax.set_title(title, fontsize=10.5, color=INK, loc="left")
        ax.set_xlabel("days after the BTC event day")
        ax.legend(frameon=False, fontsize=9, loc="upper left")
    axes[0].set_ylabel("avg cumulative alt return, %  (event day excluded)")
    fig.text(0.01, 0.012,
             "Chasing BTC up-days earned nothing (HYPE: negative). The only "
             "positive drift follows BTC dumps - a fading, marginal rebound effect.",
             fontsize=8.5, color=MUTED)
    fig.tight_layout(rect=(0, 0.045, 1, 1))
    fig.savefig(os.path.join(FIGS, "fig2_event_study.png"), dpi=150)
    plt.close(fig)


def fig_equity(cm_r, api_r):
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.4))
    cost = 10 / 1e4
    hype_uni, splice = unified_hype(cm_r)
    hype_btc = api_r["btc"] if splice is not None else cm_r["btc"]
    panels = [("HYPE strategies (net 10 bps/switch)", hype_btc, hype_uni),
              ("SOL strategies (net 10 bps/switch)", api_r["btc"], api_r["sol"])]
    for ax, (title, b, a) in zip(axes, panels):
        j = pd.DataFrame({"b": b, "a": a}).dropna()
        curves = {
            "buy & hold": (pd.Series(1.0, index=j.index), MUTED, 1.6),
            "long day after BTC up-day": ((j["b"] > 0).astype(float), ORANGE, 2),
            "long day after BTC < -2%": ((j["b"] < -0.02).astype(float), BLUE, 2),
        }
        for lab, (pos_sig, color, lw) in curves.items():
            pos = pos_sig.shift(1).fillna(0.0)
            turn = pos.diff().abs().fillna(pos.abs())
            net = pos * j["a"] - (turn * cost if lab != "buy & hold" else 0)
            eq = net.cumsum()
            ax.plot(eq.index, eq.values, color=color, lw=lw, label=lab)
            ax.annotate(f"{eq.iloc[-1]:+.2f}", (eq.index[-1], eq.iloc[-1]),
                        xytext=(4, -3), textcoords="offset points",
                        fontsize=8.5, color=color)
        ax.axhline(0, color=BASE, lw=1)
        ax.set_title(title, fontsize=10.5, color=INK, loc="left")
        ax.legend(frameon=True, facecolor=SURFACE, edgecolor="none",
                  fontsize=8.5, loc="upper left")
        loc = mdates.AutoDateLocator(maxticks=7)
        ax.xaxis.set_major_locator(loc)
        ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(loc))
    axes[0].set_ylabel("cumulative log return")
    fig.text(0.01, 0.012,
             "Signal known at close of day t, position held for day t+1. "
             "Chasing (orange) lags buy & hold; the contrarian rule (blue) is the "
             "only one ahead, on thin and fading evidence.",
             fontsize=8.5, color=MUTED)
    fig.tight_layout(rect=(0, 0.045, 1, 1))
    fig.savefig(os.path.join(FIGS, "fig3_equity_curves.png"), dpi=150)
    plt.close(fig)


def load_hype_extension():
    """Daily HYPE log-returns from data/hype_daily_extension.csv, or None.

    Produced by fetch_hype_extension.py. A trailing duplicate date (an
    intraday "current" point appended to the daily series) is dropped. The
    prices sit on the API panel's daily grid, so they pair same-day with
    api_r["btc"] — verified on the 87-day overlap with the CM panel.
    """
    ext_path = os.path.join(DATA, "hype_daily_extension.csv")
    if not os.path.exists(ext_path):
        return None
    ext = pd.read_csv(ext_path, parse_dates=["date"])
    ext = ext.drop_duplicates("date", keep="first").set_index("date").sort_index()
    return np.log(ext["hype_usd"]).diff()


def unified_hype(cm_r):
    """HYPE returns spliced onto the API panel's grid; see the analysis module.

    CM rows carry the price CM labels as reference rate D+1, so CM returns
    shift forward one day to sit on the API grid (overlap corr 0.994).
    """
    ext = load_hype_extension()
    cm_aligned = cm_r["hype"].shift(1)
    if ext is None:
        return cm_aligned.dropna(), None
    splice = ext.dropna().index.min()
    uni = pd.concat([cm_aligned.loc[:splice - pd.Timedelta(days=1)],
                     ext.dropna()]).sort_index()
    return uni.dropna(), splice


def fig_rolling(cm_r, api_r):
    fig, ax = plt.subplots(figsize=(11, 4.0))
    hype_uni, splice = unified_hype(cm_r)
    btc = api_r["btc"] if splice is not None else cm_r["btc"]
    series = [
        ("SOL-BTC", api_r["btc"].rolling(60, min_periods=45).corr(api_r["sol"]), BLUE),
        ("ETH-BTC", api_r["btc"].rolling(60, min_periods=45).corr(api_r["eth"]), MUTED),
        ("HYPE-BTC", btc.rolling(60, min_periods=45).corr(hype_uni), ORANGE),
    ]
    for lab, s, color in series:
        s = s.dropna()
        ax.plot(s.index, s.values, color=color, lw=2, label=lab)
        ax.annotate(f"{lab}  {s.iloc[-1]:.2f}", (s.index[-1], s.iloc[-1]),
                    xytext=(6, -3), textcoords="offset points",
                    fontsize=9, color=color)
    hype_roll = series[2][1].dropna()
    if splice is not None:
        # mark where the HYPE series hands over between the two sources
        cm_end = cm_r["hype"].dropna().index[-1]
        ax.axvline(cm_end, color=ORANGE, lw=1, ls=":", alpha=0.8)
        ax.annotate("source handover", (cm_end, 0.06), xytext=(-4, 0),
                    textcoords="offset points", fontsize=8, color=ORANGE,
                    ha="right")
        title_note = "HYPE now runs through 2026-08-23"
    else:
        title_note = "HYPE daily data ends 2026-05-23"
    ax.axhline(0, color=BASE, lw=1)
    ax.set_ylim(-0.1, 1.05)
    ax.set_xlim(right=hype_roll.index[-1] + pd.Timedelta(days=95))
    ax.set_ylabel("rolling 60-day correlation of daily returns")
    ax.set_title(f"How tightly do they track BTC?  ({title_note})",
                 fontsize=10.5, color=INK, loc="left")
    ax.legend(frameon=True, facecolor=SURFACE, edgecolor="none", fontsize=9,
              loc="lower left")
    loc = mdates.AutoDateLocator(maxticks=9)
    ax.xaxis.set_major_locator(loc)
    ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(loc))
    fig.text(0.01, 0.012,
             f"HYPE runs {hype_roll.min():.2f}-{hype_roll.max():.2f} "
             f"(now {hype_roll.iloc[-1]:.2f}): BTC explains under a third of its "
             "variance. SOL/ETH stay 0.55-0.95 - tight same-day coupling.",
             fontsize=8.5, color=MUTED)
    fig.tight_layout(rect=(0, 0.05, 1, 1))
    fig.savefig(os.path.join(FIGS, "fig4_rolling_corr.png"), dpi=150)
    plt.close(fig)


if __name__ == "__main__":
    cm_r, api_r = load()
    os.makedirs(FIGS, exist_ok=True)
    fig_ccf(cm_r, api_r)
    fig_event(cm_r, api_r)
    fig_equity(cm_r, api_r)
    fig_rolling(cm_r, api_r)
    print("figures written to", FIGS)

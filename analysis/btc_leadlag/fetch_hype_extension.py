"""Fetch daily HYPE closes to fill the post-2026-05-23 gap.

Run this OUTSIDE the restricted analysis sandbox (normal internet needed):

    python fetch_hype_extension.py

It writes data/hype_daily_extension.csv (columns: date, hype_usd — daily
~00:00 UTC prices from CoinGecko, the same timestamp convention as
data/daily_panel_api.csv). Once the file exists, btc_leadlag_analysis.py
and make_figures.py automatically extend the HYPE-BTC pair and the
rolling-correlation chart through the gap. Any other source works too, as
long as the CSV has one row per day with a date and a USD close.
"""
import csv
import datetime as dt
import json
import os
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
URL = ("https://api.coingecko.com/api/v3/coins/hyperliquid/market_chart"
       "?vs_currency=usd&days=180&interval=daily")

req = urllib.request.Request(URL, headers={"User-Agent": "btc-leadlag-study"})
data = json.load(urllib.request.urlopen(req, timeout=30))
out = os.path.join(HERE, "data", "hype_daily_extension.csv")
with open(out, "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["date", "hype_usd"])
    for ts_ms, px in data["prices"]:
        day = dt.datetime.fromtimestamp(ts_ms / 1000, dt.timezone.utc)
        w.writerow([day.strftime("%Y-%m-%d"), round(px, 6)])
print("wrote", out)

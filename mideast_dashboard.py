#!/usr/bin/env python3
"""
Middle East Conflict — Malaysia High-Frequency Indicators Dashboard
Interactive browser dashboard — run: python3 mideast_dashboard.py
Then open: http://127.0.0.1:8051
"""

import os
import requests
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from dash import Dash, dcc, html, Input, Output
from datetime import datetime, timedelta

# ── Config ────────────────────────────────────────────────────────────────────

SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://irzjxcwgihjdootxjyuu.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_ANON_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imlyemp4Y3dnaWhqZG9vdHhqeXV1Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzM2MDgwNDAsImV4cCI6MjA4OTE4NDA0MH0.GspfvUpfb5RLLdUWxbsf-JOGCk_oVveLF_HM3M6of6U")

COLORS = {
    "primary":   "#1a5276",
    "secondary": "#2980b9",
    "accent":    "#e74c3c",
    "gold":      "#f39c12",
    "green":     "#27ae60",
    "orange":    "#e67e22",
    "purple":    "#8e44ad",
    "bg":        "#0f1b2d",
    "card":      "#162033",
    "text":      "#ecf0f1",
    "subtext":   "#95a5a6",
    "border":    "#1e3a5f",
    "up":        "#27ae60",
    "down":      "#e74c3c",
}
FONT = "Inter, Segoe UI, sans-serif"


# ── Data loading (from Supabase) ─────────────────────────────────────────────

def load_supabase(table, order_col="date", limit=1000, date_gte=None):
    """Fetch a table from Supabase REST API. Use date_gte to filter server-side."""
    try:
        headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
        url = (f"{SUPABASE_URL}/rest/v1/{table}"
               f"?order={order_col}.asc&limit={limit}")
        if date_gte:
            url += f"&date=gte.{date_gte}"
        r = requests.get(url, headers=headers, timeout=30)
        if r.status_code != 200:
            print(f"  Warning: {table} returned {r.status_code}")
            return pd.DataFrame()
        data = r.json()
        if not data:
            return pd.DataFrame()
        df = pd.DataFrame(data)
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"])
            df = df.sort_values("date").reset_index(drop=True)
        if "id" in df.columns:
            df = df.drop(columns=["id"])
        return df
    except Exception as e:
        print(f"  Warning: Could not fetch {table}: {e}")
        return pd.DataFrame()


print("Loading data from Supabase...")

# Only fetch data needed for display — server-side date filtering keeps responses small & fast

# 1. Exchange rates — last 10 years (charts show max "Since 2015")
fx = load_supabase("exchange_rates", date_gte="2015-01-01")

# 1b. Daily USD/MYR for 2026
usd_myr_daily = load_supabase("usd_myr_daily")
if not usd_myr_daily.empty:
    usd_myr_daily["mid"] = (usd_myr_daily["buying"] + usd_myr_daily["selling"]) / 2

# 2. CPI — since 2022 (14 divisions × ~48 months = ~672 rows, well under 1000)
cpi_headline = load_supabase("cpi_headline", date_gte="2022-01-01")
cpi_core = load_supabase("cpi_core", date_gte="2022-01-01")

# 3. Trade — last 5 years
trade = load_supabase("trade_by_commodity", date_gte="2020-01-01")

# 4. GDP — since 2015
gdp_sector = load_supabase("gdp_by_sector", date_gte="2015-01-01")
gdp_expenditure = load_supabase("gdp_by_expenditure", date_gte="2015-01-01")
gdp_quarterly = load_supabase("gdp_quarterly", date_gte="2015-01-01")

# 5. Interest rates
opr = load_supabase("opr_historical")

# 6. PPI — since 2020
ppi = load_supabase("ppi", date_gte="2020-01-01")
ppi_1d = load_supabase("ppi_1d", date_gte="2020-01-01")

# 7. Fuel prices — since 2022
fuel_prices = load_supabase("fuelprice", date_gte="2022-01-01")

# 8. Energy benchmark prices (Brent crude + Henry Hub natural gas) from Yahoo Finance
def fetch_yahoo_energy(ticker, period="ytd"):
    """Fetch energy commodity prices from Yahoo Finance chart API."""
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?range={period}&interval=1d"
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
        if r.status_code != 200:
            return pd.DataFrame()
        data = r.json().get("chart", {}).get("result", [{}])[0]
        ts = data.get("timestamp", [])
        closes = data.get("indicators", {}).get("quote", [{}])[0].get("close", [])
        if not ts or not closes:
            return pd.DataFrame()
        df = pd.DataFrame({"date": pd.to_datetime(ts, unit="s"), "close": closes})
        df["date"] = df["date"].dt.normalize()
        return df.dropna().reset_index(drop=True)
    except Exception as e:
        print(f"  Warning: Yahoo Finance {ticker}: {e}")
        return pd.DataFrame()

brent = fetch_yahoo_energy("BZ=F", "1y")
wti = fetch_yahoo_energy("CL=F", "1y")
henryhub = fetch_yahoo_energy("NG=F", "1y")
ttf = fetch_yahoo_energy("TTF=F", "1y")

print("Data ready.\n")


# ── Data prep ─────────────────────────────────────────────────────────────────

# USD/MYR monthly time series
usd_myr = pd.DataFrame()
if not fx.empty and "usd" in [c.lower() for c in fx.columns]:
    usd_col = [c for c in fx.columns if c.lower() == "usd"][0]
    avg_fx = fx[fx["indicator"] == "avg"] if "indicator" in fx.columns else fx
    usd_myr = avg_fx[["date", usd_col]].dropna().copy()
    usd_myr.columns = ["date", "usd_myr"]
    usd_myr["usd_myr"] = pd.to_numeric(usd_myr["usd_myr"], errors="coerce")

# SAR/MYR (proxy for Gulf exposure)
sar_myr = pd.DataFrame()
if not fx.empty and "sar" in [c.lower() for c in fx.columns]:
    sar_col = [c for c in fx.columns if c.lower() == "sar"][0]
    avg_fx = fx[fx["indicator"] == "avg"] if "indicator" in fx.columns else fx
    sar_myr = avg_fx[["date", sar_col]].dropna().copy()
    sar_myr.columns = ["date", "sar_myr"]
    sar_myr["sar_myr"] = pd.to_numeric(sar_myr["sar_myr"], errors="coerce")

# CPI transport & food components
cpi_transport = pd.DataFrame()
cpi_food = pd.DataFrame()
cpi_housing = pd.DataFrame()
cpi_overall = pd.DataFrame()
# COICOP division codes: 01=Food, 04=Housing/Utilities, 07=Transport, overall=headline
CPI_DIVISION_LABELS = {
    "01": "Food & Non-Alcoholic Beverages",
    "02": "Alcoholic Beverages & Tobacco",
    "03": "Clothing & Footwear",
    "04": "Housing, Water, Electricity & Gas",
    "05": "Furnishings & Household Equipment",
    "06": "Health",
    "07": "Transport",
    "08": "Information & Communication",
    "09": "Recreation, Sport & Culture",
    "10": "Education",
    "11": "Restaurants & Accommodation",
    "12": "Insurance & Financial Services",
    "13": "Personal Care & Miscellaneous",
    "overall": "Overall",
}

if not cpi_headline.empty:
    div_col = "division" if "division" in cpi_headline.columns else None
    if div_col:
        # Transport (COICOP 07)
        transport_mask = cpi_headline[div_col] == "07"
        if transport_mask.any():
            cpi_transport = cpi_headline[transport_mask][["date", "inflation_yoy"]].dropna().copy()
            cpi_transport.columns = ["date", "transport_yoy"]
        # Food (COICOP 01)
        food_mask = cpi_headline[div_col] == "01"
        if food_mask.any():
            cpi_food = cpi_headline[food_mask][["date", "inflation_yoy"]].dropna().copy()
            cpi_food.columns = ["date", "food_yoy"]
        # Housing/Utilities (COICOP 04) — electricity/gas cost channel
        housing_mask = cpi_headline[div_col] == "04"
        cpi_housing = pd.DataFrame()
        if housing_mask.any():
            cpi_housing = cpi_headline[housing_mask][["date", "inflation_yoy"]].dropna().copy()
            cpi_housing.columns = ["date", "housing_yoy"]
        # Overall
        overall_mask = cpi_headline[div_col] == "overall"
        if overall_mask.any():
            cpi_overall = cpi_headline[overall_mask][["date", "inflation_yoy"]].dropna().copy()
            cpi_overall.columns = ["date", "headline_yoy"]

# Core CPI
cpi_core_ts = pd.DataFrame()
if not cpi_core.empty:
    div_col = "division" if "division" in cpi_core.columns else None
    if div_col:
        overall_mask = cpi_core[div_col].str.lower() == "overall"
        if overall_mask.any():
            cpi_core_ts = cpi_core[overall_mask][["date", "inflation_yoy"]].dropna().copy()
            cpi_core_ts.columns = ["date", "core_yoy"]

# Trade — overall and petroleum
trade_overall = pd.DataFrame()
trade_petroleum = pd.DataFrame()
if not trade.empty:
    sec_col = "section" if "section" in trade.columns else None
    if sec_col:
        # Overall
        ov_mask = trade[sec_col].str.lower().str.contains("overall", na=False)
        if ov_mask.any():
            trade_overall = trade[ov_mask][["date", "exports", "imports"]].dropna().copy()
            trade_overall["balance"] = trade_overall["exports"] - trade_overall["imports"]

        # Mineral fuels (SITC 3) — closest proxy for petroleum
        fuel_mask = trade[sec_col].str.contains("3", na=False)
        if fuel_mask.any():
            trade_petroleum = trade[fuel_mask][["date", "exports", "imports"]].dropna().copy()
            trade_petroleum["balance"] = trade_petroleum["exports"] - trade_petroleum["imports"]

# Fuel prices (RON95, RON97, diesel)
fuel_ts = pd.DataFrame()
if not fuel_prices.empty:
    fuel_ts = fuel_prices.copy()

# MSIC section labels (used for PPI)
MSIC_LABELS = {
    "A": "Agriculture",
    "B": "Mining & Quarrying",
    "C": "Manufacturing",
    "D": "Electricity & Gas",
    "E": "Water & Waste",
}

# PPI — headline YoY growth
ppi_ts = pd.DataFrame()
if not ppi.empty and "series" in ppi.columns:
    ppi_yoy = ppi[ppi["series"] == "growth_yoy"].copy()
    if not ppi_yoy.empty:
        ppi_ts = ppi_yoy[["date", "index"]].dropna().copy()
        ppi_ts.columns = ["date", "value"]
        ppi_ts["value"] = pd.to_numeric(ppi_ts["value"], errors="coerce")

# PPI by section — YoY growth (A-E)
ppi_sections = pd.DataFrame()
if not ppi_1d.empty and "series" in ppi_1d.columns:
    ppi_sections = ppi_1d[ppi_1d["series"] == "growth_yoy"].copy()
    ppi_sections["index"] = pd.to_numeric(ppi_sections["index"], errors="coerce")
    ppi_sections["label"] = ppi_sections["section"].map(MSIC_LABELS)

# GDP quarterly growth
gdp_growth = pd.DataFrame()
if not gdp_quarterly.empty:
    yoy = gdp_quarterly[gdp_quarterly["series"] == "growth_yoy"] if "series" in gdp_quarterly.columns else pd.DataFrame()
    if not yoy.empty:
        gdp_growth = yoy[["date", "value"]].dropna().copy()
        gdp_growth.columns = ["date", "gdp_yoy"]


# ── Helper: latest values for KPI cards ───────────────────────────────────────

def latest_val(df, col, fmt="{:.2f}"):
    if df.empty or col not in df.columns:
        return "N/A", ""
    last = df.dropna(subset=[col]).iloc[-1]
    date_str = last["date"].strftime("%b %Y") if "date" in df.columns else ""
    return fmt.format(last[col]), date_str


def latest_change(df, col):
    """Return latest value and month-on-month change."""
    if df.empty or col not in df.columns or len(df) < 2:
        return "N/A", "", ""
    clean = df.dropna(subset=[col])
    if len(clean) < 2:
        return "N/A", "", ""
    curr = clean.iloc[-1][col]
    prev = clean.iloc[-2][col]
    chg = curr - prev
    arrow = "+" if chg >= 0 else ""
    date_str = clean.iloc[-1]["date"].strftime("%b %Y") if "date" in clean.columns else ""
    return f"{curr:.4f}", f"{arrow}{chg:.4f} m/m", date_str


# ── Compute KPIs ──────────────────────────────────────────────────────────────

# Use daily rate for KPI with YTD, since Feb 28, and d/d change
if not usd_myr_daily.empty:
    last_daily = usd_myr_daily.iloc[-1]
    prev_daily = usd_myr_daily.iloc[-2] if len(usd_myr_daily) >= 2 else last_daily
    ytd_start = usd_myr_daily.iloc[0]["mid"]
    usd_val = f"{last_daily['mid']:.4f}"
    # Day-on-day
    dd_chg = last_daily["mid"] - prev_daily["mid"]
    # YTD
    ytd_chg = last_daily["mid"] - ytd_start
    ytd_pct = (ytd_chg / ytd_start) * 100
    # Since Feb 28
    feb28_df = usd_myr_daily[usd_myr_daily["date"] >= pd.to_datetime("2026-02-28")]
    if not feb28_df.empty:
        feb28_rate = feb28_df.iloc[0]["mid"]
        feb_chg = last_daily["mid"] - feb28_rate
        feb_pct = (feb_chg / feb28_rate) * 100
        feb_str = f"Since 28 Feb: {feb_chg:+.4f} ({feb_pct:+.1f}%)"
    else:
        feb_str = ""
    usd_chg = (f"d/d: {dd_chg:+.4f}  |  YTD: {ytd_pct:+.1f}%\n"
               f"{feb_str}")
    usd_date = last_daily["date"].strftime("%d %b %Y")
else:
    usd_val, usd_chg, usd_date = latest_change(usd_myr, "usd_myr")
headline_val, headline_date = latest_val(cpi_overall, "headline_yoy", "{:.1f}%")
transport_val, transport_date = latest_val(cpi_transport, "transport_yoy", "{:.1f}%")
food_val, food_date = latest_val(cpi_food, "food_yoy", "{:.1f}%")

# Latest trade balance for SITC 3 (mineral fuels)
petro_bal_val, petro_bal_date = "N/A", ""
if not trade_petroleum.empty:
    last_petro = trade_petroleum.iloc[-1]
    petro_bal_val = f"RM {last_petro['balance']/1e9:.1f}bn"
    petro_bal_date = last_petro["date"].strftime("%b %Y")

# OPR
opr_val, opr_date = "N/A", ""
if not opr.empty:
    opr_val = f"{opr.iloc[-1].get('opr_pct', 'N/A')}%"
    opr_date = str(opr.iloc[-1].get("date", ""))[:10]

# Fuel prices — use BUDI subsidized rate for RON95, targeted rate for diesel
ron95_val, ron95_market_val, diesel_val, diesel_market_val, fuel_date_str = "N/A", "N/A", "N/A", "N/A", ""
if not fuel_ts.empty:
    fuel_levels = fuel_ts[fuel_ts["series_type"] == "level"] if "series_type" in fuel_ts.columns else fuel_ts
    if not fuel_levels.empty:
        last_fuel = fuel_levels.iloc[-1]
        # BUDI95 = subsidized pump price for eligible users
        if "ron95_budi95" in fuel_levels.columns and pd.notna(last_fuel.get("ron95_budi95")):
            ron95_val = f"RM {float(last_fuel['ron95_budi95']):.2f}"
        # RON95 ceiling/market price
        if "ron95" in fuel_levels.columns:
            ron95_market_val = f"RM {float(last_fuel['ron95']):.2f}"
        # Diesel East Malaysia / targeted subsidized rate
        if "diesel_eastmsia" in fuel_levels.columns and pd.notna(last_fuel.get("diesel_eastmsia")):
            diesel_val = f"RM {float(last_fuel['diesel_eastmsia']):.2f}"
        # Diesel market/unsubsidized
        if "diesel" in fuel_levels.columns:
            diesel_market_val = f"RM {float(last_fuel['diesel']):.2f}"
        fuel_date_str = last_fuel["date"].strftime("%d %b %Y") if "date" in fuel_levels.columns else ""

# Energy benchmarks — Brent and Henry Hub with YTD and since-Feb-28 changes
def energy_kpi(df, label):
    """Compute current price, YTD change, and change since Feb 28."""
    if df.empty:
        return "N/A", "", "", ""
    current = df.iloc[-1]["close"]
    ytd_start = df.iloc[0]["close"]
    ytd_chg = ((current / ytd_start) - 1) * 100

    feb28 = pd.to_datetime("2026-02-28")
    since_feb = df[df["date"] >= feb28]
    feb_chg_str = ""
    if not since_feb.empty:
        feb_start = since_feb.iloc[0]["close"]
        feb_chg = ((current / feb_start) - 1) * 100
        feb_chg_str = f"Since 28 Feb: {feb_chg:+.1f}%"

    date_str = df.iloc[-1]["date"].strftime("%d %b %Y")
    return f"${current:.2f}", f"YTD: {ytd_chg:+.1f}%", feb_chg_str, date_str

brent_val, brent_ytd, brent_feb, brent_date = energy_kpi(brent, "Brent")
wti_val, wti_ytd, wti_feb, wti_date = energy_kpi(wti, "WTI")
ng_val, ng_ytd, ng_feb, ng_date = energy_kpi(henryhub, "Henry Hub")
ttf_val, ttf_ytd, ttf_feb, ttf_date = energy_kpi(ttf, "TTF")


# ── Layout helpers ────────────────────────────────────────────────────────────

def card(children, style=None):
    base = {
        "background": COLORS["card"],
        "borderRadius": "12px",
        "padding": "16px 16px",
        "border": f"1px solid {COLORS['border']}",
        "boxShadow": "0 4px 20px rgba(0,0,0,0.3)",
        "minWidth": "140px",
        "overflow": "hidden",
        "boxSizing": "border-box",
    }
    if style:
        base.update(style)
    return html.Div(children, style=base)


def kpi(label, value, sub="", color=COLORS["secondary"]):
    return html.Div([
        html.Div(label, style={"color": COLORS["subtext"], "fontSize": "11px",
                                "textTransform": "uppercase", "letterSpacing": "1px",
                                "marginBottom": "6px"}),
        html.Div(value, className="kpi-value",
                 style={"color": color, "fontSize": "26px",
                         "fontWeight": "700", "lineHeight": "1"}),
        html.Div(sub, style={"color": COLORS["subtext"], "fontSize": "11px",
                              "marginTop": "4px"}),
    ], style={"padding": "4px 0"})


def section_header(title, subtitle=""):
    children = [
        html.H2(title, style={"margin": "0 0 4px", "fontSize": "16px",
                               "fontWeight": "700", "color": COLORS["text"],
                               "textTransform": "uppercase", "letterSpacing": "1px"}),
    ]
    if subtitle:
        children.append(
            html.Div(subtitle, style={"color": COLORS["subtext"], "fontSize": "12px"})
        )
    return html.Div(children, style={"marginBottom": "12px", "marginTop": "28px",
                                      "borderBottom": f"2px solid {COLORS['border']}",
                                      "paddingBottom": "8px"})


def mark_latest(fig, x, y, label="", color=COLORS["text"], fmt="{:.2f}"):
    """Add a prominent marker and label on the latest data point."""
    if x is None or y is None or pd.isna(y):
        return
    val_str = fmt.format(y) if not label else label
    fig.add_trace(go.Scatter(
        x=[x], y=[y], mode="markers",
        marker=dict(size=12, color=color, symbol="circle",
                    line=dict(width=2, color="white")),
        showlegend=False, hoverinfo="skip",
    ))
    fig.add_annotation(
        x=x, y=y, text=f"<b>{val_str}</b>",
        showarrow=True, arrowhead=0, arrowcolor=color,
        ax=40, ay=-20,
        font=dict(color=color, size=11),
        bgcolor="rgba(0,0,0,0.6)", borderpad=3,
    )


LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family=FONT, color=COLORS["text"], size=11),
    margin=dict(t=30, b=35, l=45, r=15),
    legend=dict(bgcolor="rgba(0,0,0,0)", bordercolor=COLORS["border"],
                borderwidth=0, font=dict(size=10),
                orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
    xaxis=dict(gridcolor=COLORS["border"], showgrid=True, zeroline=False),
    yaxis=dict(gridcolor=COLORS["border"], showgrid=True, zeroline=False),
    autosize=True,
)


# ── App ───────────────────────────────────────────────────────────────────────

app = Dash(
    __name__,
    title="Middle East Conflict — Malaysia HF Indicators",
    meta_tags=[{"name": "viewport", "content": "width=device-width, initial-scale=1.0"}],
)

# ── Responsive CSS for mobile ────────────────────────────────────────────────
app.index_string = '''<!DOCTYPE html>
<html>
    <head>
        {%metas%}
        <title>{%title%}</title>
        {%favicon%}
        {%css%}
        <style>
            html, body { overflow-x: hidden; max-width: 100vw; margin: 0; }

            @media screen and (max-width: 768px) {
                /* Page padding */
                #react-entry-point > div > div {
                    padding: 10px 8px !important;
                    max-width: 100vw !important;
                }

                /* Typography */
                h1 { font-size: 16px !important; }
                h2 { font-size: 13px !important; }
                h3 { font-size: 10px !important; }
                .kpi-value { font-size: 18px !important; }

                /* All flex rows: stack vertically */
                div[style*="display: flex"] {
                    flex-direction: column !important;
                    gap: 8px !important;
                }

                /* All direct children of flex rows: full width */
                div[style*="display: flex"] > div {
                    min-width: 0 !important;
                    max-width: 100% !important;
                    flex: none !important;
                    width: 100% !important;
                    padding: 12px 10px !important;
                }

                /* Charts: force reasonable height */
                .js-plotly-plot, .dash-graph {
                    min-width: 0 !important;
                    width: 100% !important;
                }
                .dash-graph > div > div {
                    width: 100% !important;
                }

                /* Plotly modebar hide on mobile */
                .modebar-container { display: none !important; }
            }

            @media screen and (max-width: 1024px) {
                #react-entry-point > div > div { padding: 14px 14px !important; }
            }
        </style>
    </head>
    <body>
        {%app_entry%}
        <footer>
            {%config%}
            {%scripts%}
            {%renderer%}
        </footer>
    </body>
</html>'''

app.layout = html.Div(style={
    "background": COLORS["bg"], "minHeight": "100vh",
    "fontFamily": FONT, "color": COLORS["text"], "padding": "24px 32px",
    "maxWidth": "1400px", "margin": "0 auto", "width": "100%", "boxSizing": "border-box",
}, children=[

    # ── Header ────────────────────────────────────────────────────────────────
    html.Div([
        html.H1("Middle East Conflict — Malaysia HF Indicators",
                style={"margin": "0 0 4px", "fontSize": "24px", "fontWeight": "700"}),
        html.Div(
            "Transmission channels: Energy prices · FX & capital flows · Trade · Inflation · Fiscal · Financial markets · Real activity",
            style={"color": COLORS["subtext"], "fontSize": "12px"}
        ),
        html.Div(
            f"Last data refresh: {datetime.now().strftime('%d %b %Y %H:%M')}  |  Sources: BNM, DOSM",
            style={"color": COLORS["subtext"], "fontSize": "11px", "marginTop": "4px"}
        ),
    ], style={"marginBottom": "20px"}),

    # ── KPI Row 1 — Macro snapshot ──────────────────────────────────────────
    html.Div([
        card([kpi("USD/MYR", usd_val, f"{usd_chg}  ({usd_date})",
                  COLORS["up"] if not usd_myr_daily.empty and dd_chg < 0 else COLORS["down"]),
              html.Div("Source: BNM", style={"color": COLORS["border"], "fontSize": "9px", "marginTop": "4px"})],
             {"flex": "1"}),
        card([kpi("Headline CPI (YoY)", headline_val, headline_date, COLORS["accent"]),
              html.Div("Source: DOSM", style={"color": COLORS["border"], "fontSize": "9px", "marginTop": "4px"})],
             {"flex": "1"}),
        card([kpi("Transport CPI (YoY)", transport_val, transport_date, COLORS["orange"]),
              html.Div("Source: DOSM", style={"color": COLORS["border"], "fontSize": "9px", "marginTop": "4px"})],
             {"flex": "1"}),
        card([kpi("Food CPI (YoY)", food_val, food_date, COLORS["gold"]),
              html.Div("Source: DOSM", style={"color": COLORS["border"], "fontSize": "9px", "marginTop": "4px"})],
             {"flex": "1"}),
    ], style={"display": "flex", "gap": "12px", "marginBottom": "8px", "flexWrap": "wrap"}),

    # KPI Row 2 — Energy benchmarks
    html.Div([
        card([kpi("Brent Crude", brent_val, f"{brent_ytd}  |  {brent_feb}\n{brent_date}",
                  COLORS["accent"]),
              html.Div("Source: Yahoo Finance (BZ=F)", style={"color": COLORS["border"], "fontSize": "9px", "marginTop": "4px"})],
             {"flex": "1"}),
        card([kpi("Henry Hub NG (US)", ng_val, f"{ng_ytd}  |  {ng_feb}\n{ng_date}",
                  COLORS["gold"]),
              html.Div("Source: Yahoo Finance (NG=F)", style={"color": COLORS["border"], "fontSize": "9px", "marginTop": "4px"})],
             {"flex": "1"}),
        card([kpi("TTF NG (Europe)", ttf_val, f"{ttf_ytd}  |  {ttf_feb}\n{ttf_date}",
                  COLORS["purple"]),
              html.Div("Source: Yahoo Finance (TTF=F)", style={"color": COLORS["border"], "fontSize": "9px", "marginTop": "4px"})],
             {"flex": "1"}),
        card([kpi("Fuel Trade Balance", petro_bal_val, f"SITC 3 · {petro_bal_date}", COLORS["green"]),
              html.Div("Source: DOSM", style={"color": COLORS["border"], "fontSize": "9px", "marginTop": "4px"})],
             {"flex": "1"}),
        card([kpi("OPR", opr_val, opr_date, COLORS["secondary"]),
              html.Div("Source: BNM", style={"color": COLORS["border"], "fontSize": "9px", "marginTop": "4px"})],
             {"flex": "1"}),
    ], style={"display": "flex", "gap": "12px", "marginBottom": "8px", "flexWrap": "wrap"}),

    # KPI Row 3 — fuel prices (subsidized + market)
    html.Div([
        card([kpi("RON95 (BUDI)", ron95_val, f"Subsidized · {fuel_date_str}", COLORS["green"]),
              html.Div("Source: DOSM/KPDNHEP", style={"color": COLORS["border"], "fontSize": "9px", "marginTop": "4px"})],
             {"flex": "1"}),
        card([kpi("RON95 (Market)", ron95_market_val, f"Market · {fuel_date_str}", COLORS["orange"]),
              html.Div("Source: DOSM/KPDNHEP", style={"color": COLORS["border"], "fontSize": "9px", "marginTop": "4px"})],
             {"flex": "1"}),
        card([kpi("Diesel (Targeted)", diesel_val, f"Subsidized · {fuel_date_str}", COLORS["green"]),
              html.Div("Source: DOSM/KPDNHEP", style={"color": COLORS["border"], "fontSize": "9px", "marginTop": "4px"})],
             {"flex": "1"}),
        card([kpi("Diesel (Market)", diesel_market_val, f"Unsubsidized · {fuel_date_str}", COLORS["orange"]),
              html.Div("Source: DOSM/KPDNHEP", style={"color": COLORS["border"], "fontSize": "9px", "marginTop": "4px"})],
             {"flex": "1"}),
    ], style={"display": "flex", "gap": "12px", "marginBottom": "8px",
              "maxWidth": "100%", "flexWrap": "wrap"}),

    # ══════════════════════════════════════════════════════════════════════════
    # SPOTLIGHT: USD/MYR DAILY TRACKING (YTD & Since ME Conflict Escalation)
    # ══════════════════════════════════════════════════════════════════════════
    section_header("USD/MYR Daily Tracker",
                   "Year-to-date and since Middle East conflict escalation (late February 2026)  |  Source: BNM daily rates"),

    html.Div(
        "The ringgit is a commodity-linked currency sensitive to oil prices, risk aversion, and US dollar strength. "
        "The daily tracker captures immediate FX market reaction to the Middle East conflict escalation and subsequent geopolitical developments.",
        style={"color": COLORS["subtext"], "fontSize": "11px", "lineHeight": "1.5",
               "marginBottom": "12px"}
    ),

    html.Div([
        card([
            html.H3("USD/MYR — Year to Date (2026)",
                    style={"margin": "0 0 12px", "fontSize": "13px", "color": COLORS["subtext"],
                           "fontWeight": "600", "textTransform": "uppercase"}),
            dcc.Graph(id="usd-myr-ytd", style={"height": "340px"},
                      config={"displayModeBar": False}),
        ], {"flex": "1"}),

        card([
            html.H3("USD/MYR — Since ME Conflict Escalation (28 Feb 2026)",
                    style={"margin": "0 0 12px", "fontSize": "13px", "color": COLORS["subtext"],
                           "fontWeight": "600", "textTransform": "uppercase"}),
            dcc.Graph(id="usd-myr-iran", style={"height": "340px"},
                      config={"displayModeBar": False}),
        ], {"flex": "1"}),
    ], style={"display": "flex", "gap": "16px", "marginBottom": "20px", "flexWrap": "wrap"}),

    # ══════════════════════════════════════════════════════════════════════════
    # SPOTLIGHT: ENERGY PRICES
    # ══════════════════════════════════════════════════════════════════════════
    section_header("Global Energy Prices",
                   "Oil and natural gas benchmarks — primary transmission channel from Middle East conflict"),

    html.Div(
        "Brent is the global oil benchmark most relevant for Malaysia (MOPS pricing is Brent-linked). "
        "WTI reflects US market conditions. TTF is the European gas benchmark and best available proxy "
        "for Asian LNG prices (JKM). Henry Hub reflects US domestic gas.",
        style={"color": COLORS["subtext"], "fontSize": "11px", "lineHeight": "1.5",
               "marginBottom": "12px"}
    ),

    html.Div([
        card([
            html.H3("Oil Prices — Brent & WTI  ($/bbl)",
                    style={"margin": "0 0 12px", "fontSize": "13px", "color": COLORS["subtext"],
                           "fontWeight": "600", "textTransform": "uppercase"}),
            dcc.Graph(id="oil-prices-chart", style={"height": "340px"},
                      config={"displayModeBar": False}),
            html.Div("Source: Yahoo Finance (BZ=F, CL=F)", style={"color": COLORS["border"], "fontSize": "9px", "marginTop": "4px"}),
        ], {"flex": "1"}),

        card([
            html.H3("Natural Gas Prices — TTF & Henry Hub  ($/MMBtu)",
                    style={"margin": "0 0 12px", "fontSize": "13px", "color": COLORS["subtext"],
                           "fontWeight": "600", "textTransform": "uppercase"}),
            dcc.Graph(id="gas-prices-chart", style={"height": "340px"},
                      config={"displayModeBar": False}),
            html.Div("Source: Yahoo Finance (TTF=F, NG=F)", style={"color": COLORS["border"], "fontSize": "9px", "marginTop": "4px"}),
        ], {"flex": "1"}),
    ], style={"display": "flex", "gap": "16px", "marginBottom": "20px", "flexWrap": "wrap"}),

    # ══════════════════════════════════════════════════════════════════════════
    # SECTION 1: EXCHANGE RATE & CAPITAL FLOWS
    # ══════════════════════════════════════════════════════════════════════════
    section_header("1. Exchange Rate & Capital Flows",
                   "MYR sensitivity to global risk aversion and oil prices"),

    html.Div(
        "The MYR typically weakens when global risk aversion rises (flight to USD) but benefits from higher oil prices "
        "as a net energy exporter. The SAR/MYR rate proxies Gulf economic linkages — remittance flows and bilateral trade.",
        style={"color": COLORS["subtext"], "fontSize": "11px", "lineHeight": "1.5",
               "marginBottom": "12px"}
    ),

    html.Div([
        card([
            html.H3("USD/MYR Exchange Rate",
                    style={"margin": "0 0 12px", "fontSize": "13px", "color": COLORS["subtext"],
                           "fontWeight": "600", "textTransform": "uppercase"}),
            dcc.Dropdown(
                id="fx-range",
                options=[
                    {"label": "Last 2 years", "value": "2Y"},
                    {"label": "Last 5 years", "value": "5Y"},
                    {"label": "Since 2015", "value": "10Y"},
                    {"label": "All", "value": "ALL"},
                ],
                value="5Y",
                clearable=False,
                style={"background": COLORS["card"], "color": "#000",
                       "marginBottom": "8px", "maxWidth": "200px"},
            ),
            dcc.Graph(id="usd-myr-chart", style={"height": "300px"},
                      config={"displayModeBar": False}),
        ], {"flex": "2"}),

        card([
            html.H3("SAR/MYR (Gulf Exposure Proxy)",
                    style={"margin": "0 0 12px", "fontSize": "13px", "color": COLORS["subtext"],
                           "fontWeight": "600", "textTransform": "uppercase"}),
            dcc.Graph(id="sar-myr-chart", style={"height": "340px"},
                      config={"displayModeBar": False}),
        ], {"flex": "1"}),
    ], style={"display": "flex", "gap": "16px", "marginBottom": "20px", "flexWrap": "wrap"}),

    # Multi-currency panel
    card([
        html.H3("Key Currencies vs MYR  (Monthly Average)",
                style={"margin": "0 0 12px", "fontSize": "13px", "color": COLORS["subtext"],
                       "fontWeight": "600", "textTransform": "uppercase"}),
        dcc.Dropdown(
            id="currency-selector",
            options=[{"label": c.upper(), "value": c}
                     for c in ["usd", "eur", "gbp", "jpy", "cny", "sgd", "idr", "thb", "sar"]
                     if c in [col.lower() for col in fx.columns]] if not fx.empty else [],
            value=["usd", "eur", "sgd", "cny"],
            multi=True,
            style={"background": COLORS["card"], "color": "#000", "marginBottom": "8px"},
        ),
        dcc.Graph(id="multi-fx-chart", style={"height": "300px"},
                  config={"displayModeBar": False}),
    ], {"marginBottom": "20px"}),

    # ══════════════════════════════════════════════════════════════════════════
    # SECTION 2: INFLATION & DOMESTIC PRICES
    # ══════════════════════════════════════════════════════════════════════════
    section_header("2. Inflation & Domestic Prices",
                   "CPI, PPI & fuel prices — pass-through from energy and import costs"),

    html.Div(
        "Transport CPI is the most direct pass-through channel from energy prices. Food inflation captures indirect effects "
        "via logistics and imported input costs. The headline-core gap signals whether price pressure is supply-driven (energy) "
        "or demand-driven. PPI leads CPI by 1-3 months as producer costs pass through to consumers.",
        style={"color": COLORS["subtext"], "fontSize": "11px", "lineHeight": "1.5",
               "marginBottom": "12px"}
    ),

    html.Div([
        card([
            html.H3("CPI Inflation — Headline, Transport & Food  (% YoY)",
                    style={"margin": "0 0 12px", "fontSize": "13px", "color": COLORS["subtext"],
                           "fontWeight": "600", "textTransform": "uppercase"}),
            dcc.Graph(id="cpi-components-chart", style={"height": "320px"},
                      config={"displayModeBar": False}),
        ], {"flex": "3"}),

        card([
            html.H3("Headline vs Core CPI  (% YoY)",
                    style={"margin": "0 0 12px", "fontSize": "13px", "color": COLORS["subtext"],
                           "fontWeight": "600", "textTransform": "uppercase"}),
            dcc.Graph(id="headline-core-chart", style={"height": "320px"},
                      config={"displayModeBar": False}),
        ], {"flex": "2"}),
    ], style={"display": "flex", "gap": "16px", "marginBottom": "20px", "flexWrap": "wrap"}),

    # Fuel prices
    html.Div([
        card([
            html.H3("Fuel Prices — Market vs Subsidized  (Source: DOSM/KPDNHEP)",
                    style={"margin": "0 0 12px", "fontSize": "13px", "color": COLORS["subtext"],
                           "fontWeight": "600", "textTransform": "uppercase"}),
            dcc.Graph(id="fuel-price-chart", style={"height": "360px"},
                      config={"displayModeBar": False}),
        ]),
    ], style={"marginBottom": "20px"}),

    # CPI heatmap by division
    card([
        html.H3("CPI Inflation by Division  (% YoY, Last 24 Months)",
                style={"margin": "0 0 12px", "fontSize": "13px", "color": COLORS["subtext"],
                       "fontWeight": "600", "textTransform": "uppercase"}),
        dcc.Graph(id="cpi-heatmap", style={"height": "400px"},
                  config={"displayModeBar": False}),
    ], {"marginBottom": "20px"}),

    # PPI row — producer price pass-through
    html.Div([
        card([
            html.H3("PPI Headline  (% YoY, Monthly)",
                    style={"margin": "0 0 8px", "fontSize": "13px", "color": COLORS["subtext"],
                           "fontWeight": "600", "textTransform": "uppercase"}),
            dcc.Dropdown(
                id="ppi-headline-range",
                options=[
                    {"label": "Last 12 months", "value": "12M"},
                    {"label": "Last 2 years", "value": "2Y"},
                    {"label": "Since 2022", "value": "2022"},
                    {"label": "Since 2020", "value": "2020"},
                    {"label": "All (since 2010)", "value": "2010"},
                ],
                value="2Y",
                clearable=False,
                style={"background": COLORS["card"], "color": "#000",
                       "marginBottom": "8px", "maxWidth": "180px"},
            ),
            dcc.Graph(id="ppi-headline-chart", style={"height": "300px"},
                      config={"displayModeBar": False}),
            html.Div("Source: DOSM", style={"color": COLORS["border"], "fontSize": "9px", "marginTop": "4px"}),
        ], {"flex": "1"}),

        card([
            html.H3("PPI by Sector  (% YoY, Monthly)",
                    style={"margin": "0 0 8px", "fontSize": "13px", "color": COLORS["subtext"],
                           "fontWeight": "600", "textTransform": "uppercase"}),
            dcc.Dropdown(
                id="ppi-sections-range",
                options=[
                    {"label": "Last 12 months", "value": "12M"},
                    {"label": "Last 2 years", "value": "2Y"},
                    {"label": "Since 2022", "value": "2022"},
                    {"label": "Since 2020", "value": "2020"},
                    {"label": "All (since 2010)", "value": "2010"},
                ],
                value="2Y",
                clearable=False,
                style={"background": COLORS["card"], "color": "#000",
                       "marginBottom": "8px", "maxWidth": "180px"},
            ),
            dcc.Graph(id="ppi-sections-chart", style={"height": "300px"},
                      config={"displayModeBar": False}),
            html.Div("Source: DOSM", style={"color": COLORS["border"], "fontSize": "9px", "marginTop": "4px"}),
        ], {"flex": "1"}),
    ], style={"display": "flex", "gap": "16px", "marginBottom": "20px", "flexWrap": "wrap"}),

    # ══════════════════════════════════════════════════════════════════════════
    # SECTION 3: TRADE & EXTERNAL SECTOR
    # ══════════════════════════════════════════════════════════════════════════
    section_header("3. Trade & External Sector",
                   "Petroleum trade balance, overall trade — terms-of-trade channel"),

    html.Div(
        "Malaysia is a net energy exporter — higher oil prices improve the mineral fuels trade balance (SITC 3). "
        "However, sustained conflict can disrupt shipping through the Strait of Malacca and raise freight costs, "
        "offsetting price gains. The overall trade balance reflects both direct energy effects and broader demand shifts.",
        style={"color": COLORS["subtext"], "fontSize": "11px", "lineHeight": "1.5",
               "marginBottom": "12px"}
    ),

    # Row 1: Exports & Imports bars
    html.Div([
        card([
            html.H3("Overall Exports & Imports  (RM billion)",
                    style={"margin": "0 0 12px", "fontSize": "13px", "color": COLORS["subtext"],
                           "fontWeight": "600", "textTransform": "uppercase"}),
            dcc.Graph(id="trade-overall-chart", style={"height": "340px"},
                      config={"displayModeBar": False}),
        ], {"flex": "1"}),

        card([
            html.H3("Mineral Fuels Exports & Imports  (SITC 3, RM billion)",
                    style={"margin": "0 0 12px", "fontSize": "13px", "color": COLORS["subtext"],
                           "fontWeight": "600", "textTransform": "uppercase"}),
            dcc.Graph(id="trade-petroleum-chart", style={"height": "340px"},
                      config={"displayModeBar": False}),
        ], {"flex": "1"}),
    ], style={"display": "flex", "gap": "16px", "marginBottom": "16px", "flexWrap": "wrap"}),

    # Row 2: Trade balance lines
    html.Div([
        card([
            html.H3("Overall Trade Balance  (RM billion)",
                    style={"margin": "0 0 12px", "fontSize": "13px", "color": COLORS["subtext"],
                           "fontWeight": "600", "textTransform": "uppercase"}),
            dcc.Graph(id="trade-balance-chart", style={"height": "280px"},
                      config={"displayModeBar": False}),
        ], {"flex": "1"}),

        card([
            html.H3("Mineral Fuels Net Balance  (SITC 3, RM billion)",
                    style={"margin": "0 0 12px", "fontSize": "13px", "color": COLORS["subtext"],
                           "fontWeight": "600", "textTransform": "uppercase"}),
            dcc.Graph(id="fuel-balance-chart", style={"height": "280px"},
                      config={"displayModeBar": False}),
        ], {"flex": "1"}),
    ], style={"display": "flex", "gap": "16px", "marginBottom": "20px", "flexWrap": "wrap"}),

    # Trade composition — key conflict-sensitive categories
    card([
        html.H3("Conflict-Sensitive Exports — Mineral Fuels, Food, Chemicals & Palm Oil  (RM billion)",
                style={"margin": "0 0 4px", "fontSize": "13px", "color": COLORS["subtext"],
                       "fontWeight": "600", "textTransform": "uppercase"}),
        html.Div(
            "These four SITC categories are most exposed to Middle East disruption. "
            "Mineral fuels (SITC 3) dominate Malaysia's conflict-sensitive exports at RM 14–18bn/month. "
            "Palm oil and chemicals face indirect risk via shipping disruption through the Strait of Malacca. "
            "Food imports could rise in cost if global supply chains are strained.",
            style={"color": COLORS["subtext"], "fontSize": "11px", "lineHeight": "1.5",
                   "marginBottom": "12px"}
        ),
        dcc.Graph(id="trade-composition-chart", style={"height": "360px"},
                  config={"displayModeBar": False}),
    ], {"marginBottom": "20px"}),

    # ══════════════════════════════════════════════════════════════════════════
    # SECTION 4: REAL ACTIVITY
    # ══════════════════════════════════════════════════════════════════════════
    section_header("4. Real Activity",
                   "GDP — demand-side impact of the conflict"),

    html.Div(
        "GDP is a lagging indicator but captures the net demand-side impact. Conflict-driven energy price spikes "
        "can boost mining sector output while weighing on manufacturing and consumer spending through higher input costs.",
        style={"color": COLORS["subtext"], "fontSize": "11px", "lineHeight": "1.5",
               "marginBottom": "12px"}
    ),

    card([
        html.H3("GDP Growth  (% YoY, Quarterly)",
                style={"margin": "0 0 12px", "fontSize": "13px", "color": COLORS["subtext"],
                       "fontWeight": "600", "textTransform": "uppercase"}),
        dcc.Graph(id="gdp-growth-chart", style={"height": "300px"},
                  config={"displayModeBar": False}),
    ], {"marginBottom": "16px"}),

    # Supply-side: GDP by sector
    html.Div([
        card([
            html.H3("Agriculture",
                    style={"margin": "0 0 8px", "fontSize": "12px", "color": COLORS["green"],
                           "fontWeight": "600", "textTransform": "uppercase"}),
            dcc.Graph(id="gdp-agri-chart", style={"height": "220px"},
                      config={"displayModeBar": False}),
        ], {"flex": "1"}),
        card([
            html.H3("Mining & Quarrying",
                    style={"margin": "0 0 8px", "fontSize": "12px", "color": COLORS["gold"],
                           "fontWeight": "600", "textTransform": "uppercase"}),
            dcc.Graph(id="gdp-mining-chart", style={"height": "220px"},
                      config={"displayModeBar": False}),
        ], {"flex": "1"}),
        card([
            html.H3("Manufacturing",
                    style={"margin": "0 0 8px", "fontSize": "12px", "color": COLORS["secondary"],
                           "fontWeight": "600", "textTransform": "uppercase"}),
            dcc.Graph(id="gdp-mfg-chart", style={"height": "220px"},
                      config={"displayModeBar": False}),
        ], {"flex": "1"}),
    ], style={"display": "flex", "gap": "12px", "marginBottom": "12px", "flexWrap": "wrap"}),

    html.Div([
        card([
            html.H3("Construction",
                    style={"margin": "0 0 8px", "fontSize": "12px", "color": COLORS["orange"],
                           "fontWeight": "600", "textTransform": "uppercase"}),
            dcc.Graph(id="gdp-cons-chart", style={"height": "220px"},
                      config={"displayModeBar": False}),
        ], {"flex": "1"}),
        card([
            html.H3("Services",
                    style={"margin": "0 0 8px", "fontSize": "12px", "color": COLORS["purple"],
                           "fontWeight": "600", "textTransform": "uppercase"}),
            dcc.Graph(id="gdp-services-chart", style={"height": "220px"},
                      config={"displayModeBar": False}),
        ], {"flex": "1"}),
    ], style={"display": "flex", "gap": "12px", "marginBottom": "20px", "flexWrap": "wrap"}),

    # ══════════════════════════════════════════════════════════════════════════
    # SECTION 5: FISCAL VULNERABILITY
    # ══════════════════════════════════════════════════════════════════════════
    section_header("5. Fiscal Vulnerability Assessment",
                   "Malaysia's unique position: net energy exporter + net fuel subsidy provider"),

    card([
        html.Div([
            html.H3("Oil Price — Fiscal Transmission Framework",
                    style={"margin": "0 0 16px", "fontSize": "14px", "color": COLORS["text"],
                           "fontWeight": "600"}),
            html.Div([
                html.Div([
                    html.Div("REVENUE UPSIDE", style={"color": COLORS["green"], "fontWeight": "700",
                             "fontSize": "13px", "marginBottom": "8px"}),
                    html.Ul([
                        html.Li("Petroleum Income Tax (PITA)"),
                        html.Li("Petroleum royalties to states"),
                        html.Li("Oil-related export duties"),
                        html.Li("SST on petroleum products"),
                    ], style={"color": COLORS["text"], "fontSize": "12px", "lineHeight": "1.8"}),
                ], style={"flex": "1", "padding": "12px", "background": "rgba(39,174,96,0.1)",
                          "borderRadius": "8px", "border": f"1px solid {COLORS['green']}"}),

                html.Div([
                    html.Div("vs", style={"color": COLORS["subtext"], "fontWeight": "700",
                             "fontSize": "18px", "padding": "30px 12px"}),
                ]),

                html.Div([
                    html.Div("EXPENDITURE DOWNSIDE", style={"color": COLORS["accent"], "fontWeight": "700",
                             "fontSize": "13px", "marginBottom": "8px"}),
                    html.Ul([
                        html.Li("RON95 fuel subsidy (blanket)"),
                        html.Li("Diesel targeted subsidy (post-rationalisation)"),
                        html.Li("Electricity subsidy (via gas cost)"),
                        html.Li("Cooking oil & food subsidy pressure"),
                    ], style={"color": COLORS["text"], "fontSize": "12px", "lineHeight": "1.8"}),
                ], style={"flex": "1", "padding": "12px", "background": "rgba(231,76,60,0.1)",
                          "borderRadius": "8px", "border": f"1px solid {COLORS['accent']}"}),
            ], style={"display": "flex", "gap": "8px", "alignItems": "center"}),

            html.Div([
                html.Div("Sweet Spot: Brent USD 75–85/bbl", style={
                    "color": COLORS["gold"], "fontWeight": "700", "fontSize": "14px",
                    "textAlign": "center", "marginTop": "16px",
                }),
                html.Div(
                    "Petroleum-related fiscal revenue rises while RON95 subsidy cost remains manageable. "
                    "Above ~USD 90/bbl, subsidy rationalisation pressure intensifies.",
                    style={"color": COLORS["subtext"], "fontSize": "12px",
                           "textAlign": "center", "marginTop": "4px"}
                ),
            ]),
        ]),
    ], {"marginBottom": "20px"}),

    # ══════════════════════════════════════════════════════════════════════════
    # SECTION 6: MONITORING CHECKLIST
    # ══════════════════════════════════════════════════════════════════════════
    section_header("6. Monitoring Checklist",
                   "Key indicators, frequency, and data sources for ongoing monitoring"),

    card([
        dcc.Graph(id="checklist-table", style={"height": "480px"},
                  config={"displayModeBar": False}),
    ], {"marginBottom": "20px"}),

    # ── Footer ────────────────────────────────────────────────────────────────
    html.Div([
        html.Div(
            "Data: BNM API · DOSM Open API (data.gov.my) · World Bank  |  "
            "Dashboard: Malaysia Economic Monitor Team",
            style={"color": COLORS["subtext"], "fontSize": "11px", "textAlign": "center"}
        ),
        html.Div(
            "Note: For Brent crude oil prices, add a live feed via Yahoo Finance or Bloomberg. "
            "For KLCI data, consider Bursa Malaysia or Bloomberg terminal.",
            style={"color": COLORS["subtext"], "fontSize": "10px",
                   "textAlign": "center", "marginTop": "4px", "fontStyle": "italic"}
        ),
    ], style={"paddingTop": "12px"}),

    # Hidden interval for potential auto-refresh
    dcc.Interval(id="refresh-interval", interval=300_000, n_intervals=0),
])


# ── Callbacks ─────────────────────────────────────────────────────────────────

# --- USD/MYR Daily Tracker: YTD ---
@app.callback(Output("usd-myr-ytd", "figure"), Input("refresh-interval", "n_intervals"))
def usd_myr_ytd(_):
    fig = go.Figure()
    if usd_myr_daily.empty:
        fig.add_annotation(text="No daily USD/MYR data — run BNM fetcher",
                          xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False,
                          font=dict(color=COLORS["subtext"]))
        fig.update_layout(**LAYOUT)
        return fig

    df = usd_myr_daily.copy()
    iran_date = pd.to_datetime("2026-02-28")

    # Midpoint line
    fig.add_trace(go.Scatter(
        x=df["date"], y=df["mid"],
        mode="lines+markers",
        line=dict(color=COLORS["secondary"], width=2.5),
        marker=dict(size=5, color=COLORS["secondary"]),
        name="Mid rate",
        hovertemplate="<b>%{x|%d %b %Y}</b><br>USD/MYR: %{y:.4f}<extra></extra>",
    ))
    # Buying/selling band
    fig.add_trace(go.Scatter(
        x=df["date"], y=df["selling"],
        mode="lines", line=dict(width=0), showlegend=False,
        hoverinfo="skip",
    ))
    fig.add_trace(go.Scatter(
        x=df["date"], y=df["buying"],
        mode="lines", line=dict(width=0), showlegend=False,
        fill="tonexty", fillcolor="rgba(41,128,185,0.15)",
        hoverinfo="skip",
    ))

    # ME conflict escalation marker
    fig.add_vline(x=iran_date, line_dash="dash", line_color=COLORS["accent"], line_width=1.5)
    fig.add_annotation(x=iran_date, y=df["mid"].max(),
                      text="ME conflict\nescalation", showarrow=True, arrowhead=2,
                      font=dict(color=COLORS["accent"], size=10),
                      arrowcolor=COLORS["accent"], yshift=10)

    # YTD change annotation
    ytd_start = df.iloc[0]["mid"]
    ytd_end = df.iloc[-1]["mid"]
    ytd_chg = ytd_end - ytd_start
    ytd_pct = (ytd_chg / ytd_start) * 100
    chg_color = COLORS["up"] if ytd_chg < 0 else COLORS["down"]  # MYR strengthening = good
    fig.add_annotation(
        text=f"YTD: {ytd_chg:+.4f} ({ytd_pct:+.1f}%)<br>"
             f"{ytd_start:.4f} → {ytd_end:.4f}",
        xref="paper", yref="paper", x=0.02, y=0.98,
        showarrow=False, font=dict(color=chg_color, size=12),
        align="left", bgcolor="rgba(0,0,0,0.5)", borderpad=6,
    )

    fig.update_layout(**LAYOUT, yaxis_title="MYR per USD")
    fig.update_xaxes(gridcolor=COLORS["border"], dtick="M1",
                     tickformat="%b", showgrid=True)
    return fig


# --- USD/MYR Daily Tracker: Since ME Conflict Escalation ---
@app.callback(Output("usd-myr-iran", "figure"), Input("refresh-interval", "n_intervals"))
def usd_myr_iran(_):
    fig = go.Figure()
    iran_date = pd.to_datetime("2026-02-28")

    if usd_myr_daily.empty:
        fig.add_annotation(text="No daily USD/MYR data — run BNM fetcher",
                          xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False,
                          font=dict(color=COLORS["subtext"]))
        fig.update_layout(**LAYOUT)
        return fig

    # Filter from a few days before the event for context
    df = usd_myr_daily[usd_myr_daily["date"] >= iran_date - timedelta(days=5)].copy()
    if df.empty:
        fig.add_annotation(text="No data available for this period",
                          xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False,
                          font=dict(color=COLORS["subtext"]))
        fig.update_layout(**LAYOUT)
        return fig

    # Color bars by day — green if MYR strengthened vs previous day
    colors = []
    for i in range(len(df)):
        if i == 0:
            colors.append(COLORS["subtext"])
        elif df.iloc[i]["mid"] < df.iloc[i-1]["mid"]:
            colors.append(COLORS["up"])    # MYR strengthened
        else:
            colors.append(COLORS["down"])  # MYR weakened

    # Candlestick-style with buying/selling
    fig.add_trace(go.Bar(
        x=df["date"],
        y=df["selling"] - df["buying"],
        base=df["buying"],
        marker_color=colors,
        opacity=0.6,
        name="Bid-Ask Spread",
        hovertemplate="<b>%{x|%d %b}</b><br>Buy: %{base:.4f}<br>Sell: %{customdata:.4f}<extra></extra>",
        customdata=df["selling"],
    ))
    fig.add_trace(go.Scatter(
        x=df["date"], y=df["mid"],
        mode="lines+markers",
        line=dict(color=COLORS["text"], width=2),
        marker=dict(size=6, color=colors),
        name="Mid rate",
        hovertemplate="<b>%{x|%d %b %Y}</b><br>Mid: %{y:.4f}<extra></extra>",
    ))

    # ME conflict escalation marker
    fig.add_vline(x=iran_date, line_dash="dash", line_color=COLORS["accent"], line_width=1.5)
    fig.add_annotation(x=iran_date, y=df["mid"].max(),
                      text="ME conflict\nescalation", showarrow=True, arrowhead=2,
                      font=dict(color=COLORS["accent"], size=10),
                      arrowcolor=COLORS["accent"], yshift=10)

    # Pre vs post event with percentage change
    pre = df[df["date"] < iran_date]
    post = df[df["date"] >= iran_date]
    if not pre.empty and not post.empty:
        pre_avg = pre["mid"].mean()
        post_avg = post["mid"].mean()
        chg = post_avg - pre_avg
        pct_chg = (chg / pre_avg) * 100
        # Rate on event date vs latest
        event_rate = post.iloc[0]["mid"]
        latest_rate = post.iloc[-1]["mid"]
        since_chg = latest_rate - event_rate
        since_pct = (since_chg / event_rate) * 100
        chg_color = COLORS["down"] if since_pct > 0 else COLORS["up"]
        fig.add_annotation(
            text=f"On 28 Feb: {event_rate:.4f}<br>"
                 f"Latest: {latest_rate:.4f}<br>"
                 f"Change: {since_chg:+.4f} ({since_pct:+.1f}%)",
            xref="paper", yref="paper", x=0.98, y=0.98,
            showarrow=False, font=dict(color=chg_color, size=11),
            align="right", bgcolor="rgba(0,0,0,0.5)", borderpad=6,
        )

    fig.update_layout(**LAYOUT, yaxis_title="MYR per USD", bargap=0.3)
    fig.update_xaxes(gridcolor=COLORS["border"], dtick="D1",
                     tickformat="%d %b", showgrid=True)
    return fig


# --- Oil Prices: Brent & WTI ---
@app.callback(Output("oil-prices-chart", "figure"), Input("refresh-interval", "n_intervals"))
def oil_prices_chart(_):
    fig = go.Figure()
    feb28 = pd.to_datetime("2026-02-28")
    jan1 = pd.to_datetime("2026-01-01")

    for df, name, color in [(brent, "Brent Crude", COLORS["accent"]),
                             (wti, "WTI Crude", COLORS["gold"])]:
        if df.empty:
            continue
        fig.add_trace(go.Scatter(
            x=df["date"], y=df["close"],
            mode="lines", name=name,
            line=dict(color=color, width=2.5),
            hovertemplate=f"<b>{name}</b><br>%{{x|%d %b %Y}}: $%{{y:.2f}}<extra></extra>",
        ))
        # YTD and since-28-Feb annotations
        ytd_df = df[df["date"] >= jan1]
        feb_df = df[df["date"] >= feb28]
        if not ytd_df.empty:
            ytd_chg = ((ytd_df.iloc[-1]["close"] / ytd_df.iloc[0]["close"]) - 1) * 100
        if not feb_df.empty:
            feb_chg = ((feb_df.iloc[-1]["close"] / feb_df.iloc[0]["close"]) - 1) * 100
            mark_latest(fig, df.iloc[-1]["date"], df.iloc[-1]["close"],
                       f"${df.iloc[-1]['close']:.1f}", color)

    # ME conflict escalation marker
    fig.add_vline(x=feb28, line_dash="dash", line_color=COLORS["accent"], line_width=1.5)
    fig.add_annotation(x=feb28, y=0.98, yref="paper",
                      text="ME conflict\nescalation", showarrow=False,
                      font=dict(color=COLORS["accent"], size=9))

    # YTD start marker
    fig.add_vline(x=jan1, line_dash="dot", line_color=COLORS["subtext"], line_width=1)

    # Summary box
    summaries = []
    for df, name in [(brent, "Brent"), (wti, "WTI")]:
        if df.empty:
            continue
        ytd_df = df[df["date"] >= jan1]
        feb_df = df[df["date"] >= feb28]
        if not ytd_df.empty and not feb_df.empty:
            ytd_pct = ((ytd_df.iloc[-1]["close"] / ytd_df.iloc[0]["close"]) - 1) * 100
            feb_pct = ((feb_df.iloc[-1]["close"] / feb_df.iloc[0]["close"]) - 1) * 100
            summaries.append(f"<b>{name}</b>: YTD {ytd_pct:+.1f}%  |  Since 28 Feb {feb_pct:+.1f}%")
    if summaries:
        fig.add_annotation(
            text="<br>".join(summaries),
            xref="paper", yref="paper", x=0.02, y=0.02,
            showarrow=False, font=dict(size=10, color=COLORS["text"]),
            align="left", bgcolor="rgba(0,0,0,0.6)", borderpad=6,
        )

    fig.update_layout(**LAYOUT, yaxis_title="$/bbl")
    return fig


# --- Gas Prices: TTF & Henry Hub ---
@app.callback(Output("gas-prices-chart", "figure"), Input("refresh-interval", "n_intervals"))
def gas_prices_chart(_):
    fig = go.Figure()
    feb28 = pd.to_datetime("2026-02-28")
    jan1 = pd.to_datetime("2026-01-01")

    for df, name, color in [(ttf, "TTF (Europe)", COLORS["purple"]),
                             (henryhub, "Henry Hub (US)", COLORS["gold"])]:
        if df.empty:
            continue
        fig.add_trace(go.Scatter(
            x=df["date"], y=df["close"],
            mode="lines", name=name,
            line=dict(color=color, width=2.5),
            hovertemplate=f"<b>{name}</b><br>%{{x|%d %b %Y}}: $%{{y:.2f}}<extra></extra>",
        ))
        if not df.empty:
            mark_latest(fig, df.iloc[-1]["date"], df.iloc[-1]["close"],
                       f"${df.iloc[-1]['close']:.2f}", color)

    # ME conflict escalation marker
    fig.add_vline(x=feb28, line_dash="dash", line_color=COLORS["accent"], line_width=1.5)
    fig.add_annotation(x=feb28, y=0.98, yref="paper",
                      text="ME conflict\nescalation", showarrow=False,
                      font=dict(color=COLORS["accent"], size=9))
    fig.add_vline(x=jan1, line_dash="dot", line_color=COLORS["subtext"], line_width=1)

    # Summary box
    summaries = []
    for df, name in [(ttf, "TTF"), (henryhub, "Henry Hub")]:
        if df.empty:
            continue
        ytd_df = df[df["date"] >= jan1]
        feb_df = df[df["date"] >= feb28]
        if not ytd_df.empty and not feb_df.empty:
            ytd_pct = ((ytd_df.iloc[-1]["close"] / ytd_df.iloc[0]["close"]) - 1) * 100
            feb_pct = ((feb_df.iloc[-1]["close"] / feb_df.iloc[0]["close"]) - 1) * 100
            summaries.append(f"<b>{name}</b>: YTD {ytd_pct:+.1f}%  |  Since 28 Feb {feb_pct:+.1f}%")
    if summaries:
        fig.add_annotation(
            text="<br>".join(summaries),
            xref="paper", yref="paper", x=0.02, y=0.02,
            showarrow=False, font=dict(size=10, color=COLORS["text"]),
            align="left", bgcolor="rgba(0,0,0,0.6)", borderpad=6,
        )

    fig.update_layout(**LAYOUT, yaxis_title="$/MMBtu")
    return fig


@app.callback(Output("usd-myr-chart", "figure"),
              [Input("fx-range", "value"), Input("refresh-interval", "n_intervals")])
def usd_myr_chart(range_val, _):
    fig = go.Figure()
    if usd_myr.empty:
        fig.add_annotation(text="No USD/MYR data available", xref="paper", yref="paper",
                          x=0.5, y=0.5, showarrow=False, font=dict(color=COLORS["subtext"]))
        fig.update_layout(**LAYOUT)
        return fig

    df = usd_myr.copy()
    cutoff = {
        "2Y": datetime.now() - timedelta(days=730),
        "5Y": datetime.now() - timedelta(days=1825),
        "10Y": datetime(2015, 1, 1),
    }
    if range_val in cutoff:
        df = df[df["date"] >= cutoff[range_val]]

    fig.add_trace(go.Scatter(
        x=df["date"], y=df["usd_myr"],
        mode="lines",
        line=dict(color=COLORS["secondary"], width=2),
        hovertemplate="<b>%{x|%b %Y}</b><br>USD/MYR: %{y:.4f}<extra></extra>",
    ))

    # Add key event annotations if in range
    events = [
        ("2023-10-07", "Hamas attack"),
        ("2024-04-13", "ME escalation"),
        ("2024-10-01", "Lebanon ops"),
    ]
    for date_str, label in events:
        evt_date = pd.to_datetime(date_str)
        if not df.empty and evt_date >= df["date"].min() and evt_date <= df["date"].max():
            fig.add_vline(x=evt_date, line_dash="dash", line_color=COLORS["accent"],
                         line_width=1)
            fig.add_annotation(x=evt_date, y=df["usd_myr"].max(),
                             text=label, showarrow=False,
                             font=dict(color=COLORS["accent"], size=9),
                             yshift=10)

    fig.update_layout(**LAYOUT, yaxis_title="MYR per USD")
    # Dynamic y-axis range with padding
    ymin, ymax = df["usd_myr"].min(), df["usd_myr"].max()
    pad = (ymax - ymin) * 0.1 or 0.05
    fig.update_yaxes(range=[ymin - pad, ymax + pad])
    return fig


@app.callback(Output("sar-myr-chart", "figure"), Input("refresh-interval", "n_intervals"))
def sar_myr_chart(_):
    fig = go.Figure()
    if sar_myr.empty:
        fig.add_annotation(text="No SAR/MYR data available", xref="paper", yref="paper",
                          x=0.5, y=0.5, showarrow=False, font=dict(color=COLORS["subtext"]))
        fig.update_layout(**LAYOUT)
        return fig

    df = sar_myr[sar_myr["date"] >= datetime.now() - timedelta(days=1825)]
    fig.add_trace(go.Scatter(
        x=df["date"], y=df["sar_myr"],
        mode="lines",
        line=dict(color=COLORS["gold"], width=2),
        hovertemplate="<b>%{x|%b %Y}</b><br>SAR/MYR: %{y:.4f}<extra></extra>",
    ))
    fig.update_layout(**LAYOUT, yaxis_title="MYR per SAR")
    # Dynamic y-axis range with padding
    ymin, ymax = df["sar_myr"].min(), df["sar_myr"].max()
    pad = (ymax - ymin) * 0.1 or 0.01
    fig.update_yaxes(range=[ymin - pad, ymax + pad])
    return fig


@app.callback(Output("multi-fx-chart", "figure"),
              [Input("currency-selector", "value"), Input("refresh-interval", "n_intervals")])
def multi_fx_chart(selected, _):
    fig = go.Figure()
    if fx.empty or not selected:
        fig.update_layout(**LAYOUT)
        return fig

    avg_fx = fx[fx["indicator"] == "avg"] if "indicator" in fx.columns else fx
    avg_fx = avg_fx[avg_fx["date"] >= datetime.now() - timedelta(days=1825)]
    palette = px.colors.qualitative.Plotly

    for i, curr in enumerate(selected):
        col = [c for c in avg_fx.columns if c.lower() == curr.lower()]
        if col:
            d = avg_fx[["date", col[0]]].dropna()
            vals = pd.to_numeric(d[col[0]], errors="coerce")
            # Normalize to 100 at start for comparison
            if len(vals) > 0 and vals.iloc[0] != 0:
                normalized = (vals / vals.iloc[0]) * 100
                fig.add_trace(go.Scatter(
                    x=d["date"], y=normalized,
                    mode="lines",
                    name=curr.upper(),
                    line=dict(color=palette[i % len(palette)], width=2),
                    hovertemplate=f"<b>{curr.upper()}</b><br>%{{x|%b %Y}}: %{{y:.1f}} (indexed)<extra></extra>",
                ))

    fig.add_hline(y=100, line_dash="dash", line_color=COLORS["subtext"], line_width=1)
    fig.update_layout(**LAYOUT, yaxis_title="Index (start = 100)")
    return fig


@app.callback(Output("cpi-components-chart", "figure"), Input("refresh-interval", "n_intervals"))
def cpi_components(_):
    fig = go.Figure()
    cutoff = pd.to_datetime("2022-01-01")

    for df, col, color, name in [
        (cpi_overall, "headline_yoy", COLORS["secondary"], "Headline"),
        (cpi_transport, "transport_yoy", COLORS["orange"], "Transport"),
        (cpi_food, "food_yoy", COLORS["gold"], "Food & Beverages"),
        (cpi_housing, "housing_yoy", COLORS["purple"], "Housing, Utilities & Gas"),
    ]:
        if not df.empty:
            d = df[df["date"] >= cutoff]
            fig.add_trace(go.Scatter(
                x=d["date"], y=d[col],
                mode="lines",
                name=name,
                line=dict(color=color, width=2),
                hovertemplate=f"<b>{name}</b><br>%{{x|%b %Y}}: %{{y:.1f}}%<extra></extra>",
            ))

    # Event annotations
    events = [("2023-10-07", "ME conflict"), ("2024-04-13", "ME escalation")]
    for date_str, label in events:
        fig.add_vline(x=pd.to_datetime(date_str), line_dash="dot",
                     line_color=COLORS["accent"], line_width=1)

    # Mark latest point for headline
    for df, col, color, name in [
        (cpi_overall, "headline_yoy", COLORS["secondary"], "Headline"),
        (cpi_transport, "transport_yoy", COLORS["orange"], "Transport"),
        (cpi_food, "food_yoy", COLORS["gold"], "Food"),
    ]:
        if not df.empty:
            d = df[df["date"] >= cutoff].dropna(subset=[col])
            if not d.empty:
                last = d.iloc[-1]
                mark_latest(fig, last["date"], last[col], f"{last[col]:.1f}%", color)

    fig.add_hline(y=0, line_dash="dash", line_color=COLORS["subtext"], line_width=1)
    fig.update_layout(**LAYOUT, yaxis_title="% YoY")
    return fig


@app.callback(Output("headline-core-chart", "figure"), Input("refresh-interval", "n_intervals"))
def headline_core(_):
    fig = go.Figure()
    cutoff = pd.to_datetime("2022-01-01")

    if not cpi_overall.empty:
        d = cpi_overall[cpi_overall["date"] >= cutoff]
        fig.add_trace(go.Scatter(
            x=d["date"], y=d["headline_yoy"],
            mode="lines", name="Headline",
            line=dict(color=COLORS["secondary"], width=2),
        ))
        if not d.empty:
            last = d.dropna(subset=["headline_yoy"]).iloc[-1]
            mark_latest(fig, last["date"], last["headline_yoy"],
                       f"{last['headline_yoy']:.1f}%", COLORS["secondary"])

    if not cpi_core_ts.empty:
        d = cpi_core_ts[cpi_core_ts["date"] >= cutoff]
        fig.add_trace(go.Scatter(
            x=d["date"], y=d["core_yoy"],
            mode="lines", name="Core",
            line=dict(color=COLORS["green"], width=2, dash="dash"),
        ))
        if not d.empty:
            last = d.dropna(subset=["core_yoy"]).iloc[-1]
            mark_latest(fig, last["date"], last["core_yoy"],
                       f"{last['core_yoy']:.1f}%", COLORS["green"])

    fig.add_hline(y=0, line_dash="dash", line_color=COLORS["subtext"], line_width=1)
    fig.update_layout(**LAYOUT, yaxis_title="% YoY")
    return fig


@app.callback(Output("fuel-price-chart", "figure"), Input("refresh-interval", "n_intervals"))
def fuel_price_chart(_):
    fig = go.Figure()
    if fuel_ts.empty:
        fig.add_annotation(text="No fuel price data available — add DOSM fuelprice dataset",
                          xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False,
                          font=dict(color=COLORS["subtext"]))
        fig.update_layout(**LAYOUT)
        return fig

    # Filter for price levels only, from Jan 2024
    df = fuel_ts.copy()
    if "series_type" in df.columns:
        df = df[df["series_type"] == "level"]
    df = df[df["date"] >= pd.to_datetime("2024-01-01")]

    # Color scheme: same fuel = same color, market = solid, subsidized = dashed
    RON95_COLOR = COLORS["accent"]   # red family
    RON97_COLOR = COLORS["gold"]     # yellow/gold
    DIESEL_COLOR = COLORS["secondary"]  # blue family

    # RON95 market/ceiling price (solid)
    if "ron95" in df.columns:
        fig.add_trace(go.Scatter(
            x=df["date"], y=pd.to_numeric(df["ron95"], errors="coerce"),
            mode="lines", name="RON95 (Ceiling)",
            line=dict(color=RON95_COLOR, width=2.5),
            hovertemplate="<b>RON95 Market</b><br>%{x|%d %b %Y}: RM%{y:.2f}<extra></extra>",
        ))

    # RON95 BUDI subsidized price (dashed, same color)
    if "ron95_budi95" in df.columns:
        budi = pd.to_numeric(df["ron95_budi95"], errors="coerce")
        fig.add_trace(go.Scatter(
            x=df["date"], y=budi,
            mode="lines", name="RON95 (BUDI Subsidy)",
            line=dict(color=RON95_COLOR, width=2.5, dash="dash"),
            hovertemplate="<b>RON95 BUDI</b><br>%{x|%d %b %Y}: RM%{y:.2f}<extra></extra>",
        ))

    # RON97 (fully market-determined, solid)
    if "ron97" in df.columns:
        fig.add_trace(go.Scatter(
            x=df["date"], y=pd.to_numeric(df["ron97"], errors="coerce"),
            mode="lines", name="RON97 (Market)",
            line=dict(color=RON97_COLOR, width=2),
            hovertemplate="<b>RON97</b><br>%{x|%d %b %Y}: RM%{y:.2f}<extra></extra>",
        ))

    # Diesel market/unsubsidized (solid)
    if "diesel" in df.columns:
        fig.add_trace(go.Scatter(
            x=df["date"], y=pd.to_numeric(df["diesel"], errors="coerce"),
            mode="lines", name="Diesel (Market)",
            line=dict(color=DIESEL_COLOR, width=2),
            hovertemplate="<b>Diesel Market</b><br>%{x|%d %b %Y}: RM%{y:.2f}<extra></extra>",
        ))

    # Diesel subsidized (dashed, same color as diesel market)
    if "diesel_eastmsia" in df.columns:
        d_sub = pd.to_numeric(df["diesel_eastmsia"], errors="coerce")
        fig.add_trace(go.Scatter(
            x=df["date"], y=d_sub,
            mode="lines", name="Diesel (Targeted Subsidy)",
            line=dict(color=DIESEL_COLOR, width=2, dash="dash"),
            hovertemplate="<b>Diesel Targeted</b><br>%{x|%d %b %Y}: RM%{y:.2f}<extra></extra>",
        ))

    # Key event markers
    events = [
        ("2024-06-10", "Diesel subsidy\nrationalisation"),
        ("2025-09-30", "RON95 subsidy\nrationalisation"),
    ]
    for date_str, label in events:
        evt = pd.to_datetime(date_str)
        if not df.empty and evt >= df["date"].min():
            fig.add_vline(x=evt, line_dash="dot", line_color=COLORS["subtext"], line_width=1)
            fig.add_annotation(x=evt, y=4.5,
                             text=label, showarrow=False,
                             font=dict(color=COLORS["subtext"], size=9), yshift=0)

    # Highlight diesel > RON97 crossover
    if "diesel" in df.columns and "ron97" in df.columns:
        d_diesel = pd.to_numeric(df["diesel"], errors="coerce")
        d_ron97 = pd.to_numeric(df["ron97"], errors="coerce")
        cross = df[(d_diesel > d_ron97) & d_diesel.notna() & d_ron97.notna()]
        if not cross.empty:
            first_cross = cross.iloc[0]
            fig.add_annotation(
                x=first_cross["date"],
                y=float(d_diesel[cross.index[0]]),
                text="Diesel surpasses RON97",
                showarrow=True, arrowhead=2, arrowcolor=COLORS["gold"],
                font=dict(color=COLORS["gold"], size=10),
                ax=-60, ay=-30,
                bgcolor="rgba(0,0,0,0.6)", borderpad=4,
            )
            # Shade the crossover region
            fig.add_annotation(
                text=f"Diesel-RON97 inversion: reflects global gasoil tightness<br>"
                     f"from Middle East refinery disruptions and shipping rerouting",
                xref="paper", yref="paper", x=0.02, y=0.02,
                showarrow=False, font=dict(color=COLORS["gold"], size=9),
                align="left", bgcolor="rgba(0,0,0,0.5)", borderpad=6,
            )

    fig.update_layout(**LAYOUT, yaxis_title="RM per litre")
    fig.update_layout(legend=dict(orientation="h", yanchor="bottom", y=1.02,
                                  xanchor="left", x=0,
                                  bgcolor="rgba(0,0,0,0)", borderwidth=0))
    return fig


@app.callback(Output("cpi-heatmap", "figure"), Input("refresh-interval", "n_intervals"))
def cpi_heatmap(_):
    fig = go.Figure()
    if cpi_headline.empty:
        fig.update_layout(**LAYOUT)
        return fig

    cutoff = datetime.now() - timedelta(days=730)
    d = cpi_headline[cpi_headline["date"] >= cutoff].copy()

    if "division" in d.columns and "inflation_yoy" in d.columns:
        d["inflation_yoy"] = pd.to_numeric(d["inflation_yoy"], errors="coerce")
        d["month"] = d["date"].dt.strftime("%Y-%m")
        d["division_label"] = d["division"].map(
            lambda x: CPI_DIVISION_LABELS.get(x, x))
        pivot = d.pivot_table(index="division_label", columns="month", values="inflation_yoy")
        # Drop columns (months) where more than half the divisions have no data
        pivot = pivot.dropna(axis=1, thresh=len(pivot) // 2)
        pivot = pivot.sort_index()

        fig = go.Figure(go.Heatmap(
            z=pivot.values,
            x=pivot.columns.tolist(),
            y=pivot.index.tolist(),
            colorscale="RdYlBu_r",
            text=[[f"{v:.1f}%" if not pd.isna(v) else "" for v in row] for row in pivot.values],
            texttemplate="%{text}",
            textfont=dict(size=8),
            hovertemplate="<b>%{y}</b><br>%{x}: %{z:.1f}%<extra></extra>",
            colorbar=dict(title=dict(text="% YoY", font=dict(color=COLORS["text"])),
                          tickfont=dict(color=COLORS["text"])),
        ))

    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family=FONT, color=COLORS["text"]),
        margin=dict(t=10, b=40, l=160, r=10),
        xaxis=dict(side="bottom", tickangle=-45),
        yaxis=dict(autorange="reversed"),
    )
    return fig


@app.callback(Output("trade-overall-chart", "figure"), Input("refresh-interval", "n_intervals"))
def trade_overall_chart(_):
    fig = go.Figure()
    if trade_overall.empty:
        fig.update_layout(**LAYOUT)
        return fig

    d = trade_overall[trade_overall["date"] >= datetime.now() - timedelta(days=365)].copy()

    fig.add_trace(go.Bar(x=d["date"], y=d["exports"] / 1e9,
                        name="Exports", marker_color=COLORS["green"]))
    fig.add_trace(go.Bar(x=d["date"], y=d["imports"] / 1e9,
                        name="Imports", marker_color=COLORS["accent"]))

    fig.update_layout(**LAYOUT, barmode="group", yaxis_title="RM billion")
    # Dynamic y-axis: start near the data minimum
    all_vals = pd.concat([d["exports"], d["imports"]]) / 1e9
    ymin = all_vals.min() * 0.85
    fig.update_yaxes(range=[ymin, all_vals.max() * 1.05])
    return fig


@app.callback(Output("trade-petroleum-chart", "figure"), Input("refresh-interval", "n_intervals"))
def trade_petroleum_chart(_):
    fig = go.Figure()
    if trade_petroleum.empty:
        fig.add_annotation(text="No SITC 3 trade data", xref="paper", yref="paper",
                          x=0.5, y=0.5, showarrow=False, font=dict(color=COLORS["subtext"]))
        fig.update_layout(**LAYOUT)
        return fig

    d = trade_petroleum[trade_petroleum["date"] >= datetime.now() - timedelta(days=365)].copy()

    fig.add_trace(go.Bar(x=d["date"], y=d["exports"] / 1e9,
                        name="Fuel Exports", marker_color=COLORS["green"]))
    fig.add_trace(go.Bar(x=d["date"], y=d["imports"] / 1e9,
                        name="Fuel Imports", marker_color=COLORS["accent"]))

    fig.update_layout(**LAYOUT, barmode="group", yaxis_title="RM billion")
    # Dynamic y-axis
    all_vals = pd.concat([d["exports"], d["imports"]]) / 1e9
    ymin = all_vals.min() * 0.85
    fig.update_yaxes(range=[ymin, all_vals.max() * 1.05])
    return fig


# --- Trade Balance (separate line chart) ---
@app.callback(Output("trade-balance-chart", "figure"), Input("refresh-interval", "n_intervals"))
def trade_balance_chart(_):
    fig = go.Figure()
    if trade_overall.empty:
        fig.update_layout(**LAYOUT)
        return fig

    d = trade_overall[trade_overall["date"] >= datetime.now() - timedelta(days=365)].copy()

    # Area fill — green above zero, red below
    fig.add_trace(go.Scatter(
        x=d["date"], y=d["balance"] / 1e9,
        mode="lines+markers", name="Trade Balance",
        line=dict(color=COLORS["gold"], width=2.5),
        marker=dict(size=5, color=COLORS["gold"]),
        fill="tozeroy", fillcolor="rgba(243,156,18,0.15)",
        hovertemplate="<b>%{x|%b %Y}</b><br>Balance: RM%{y:+.1f}bn<extra></extra>",
    ))

    if not d.empty:
        last = d.iloc[-1]
        fig.add_annotation(
            text=f"Latest: RM {last['balance']/1e9:+.1f}bn  ({last['date'].strftime('%b %Y')})",
            xref="paper", yref="paper", x=0.02, y=0.98,
            showarrow=False, font=dict(color=COLORS["gold"], size=11),
            align="left", bgcolor="rgba(0,0,0,0.5)", borderpad=6,
        )

    fig.add_hline(y=0, line_dash="dash", line_color=COLORS["subtext"], line_width=1)
    fig.update_layout(**LAYOUT, yaxis_title="RM billion")
    return fig


# --- Fuel Net Balance (separate line chart) ---
@app.callback(Output("fuel-balance-chart", "figure"), Input("refresh-interval", "n_intervals"))
def fuel_balance_chart(_):
    fig = go.Figure()
    if trade_petroleum.empty:
        fig.add_annotation(text="No SITC 3 data", xref="paper", yref="paper",
                          x=0.5, y=0.5, showarrow=False, font=dict(color=COLORS["subtext"]))
        fig.update_layout(**LAYOUT)
        return fig

    d = trade_petroleum[trade_petroleum["date"] >= datetime.now() - timedelta(days=365)].copy()

    fig.add_trace(go.Scatter(
        x=d["date"], y=d["balance"] / 1e9,
        mode="lines+markers", name="Net Fuel Balance",
        line=dict(color=COLORS["green"], width=2.5),
        marker=dict(size=5, color=COLORS["green"]),
        fill="tozeroy", fillcolor="rgba(39,174,96,0.15)",
        hovertemplate="<b>%{x|%b %Y}</b><br>Net: RM%{y:+.1f}bn<extra></extra>",
    ))

    if not d.empty:
        last = d.iloc[-1]
        fig.add_annotation(
            text=f"Net fuel: RM {last['balance']/1e9:+.1f}bn  ({last['date'].strftime('%b %Y')})",
            xref="paper", yref="paper", x=0.02, y=0.98,
            showarrow=False, font=dict(color=COLORS["green"], size=11),
            align="left", bgcolor="rgba(0,0,0,0.5)", borderpad=6,
        )

    fig.add_hline(y=0, line_dash="dash", line_color=COLORS["subtext"], line_width=1)
    fig.update_layout(**LAYOUT, yaxis_title="RM billion")
    return fig


@app.callback(Output("trade-composition-chart", "figure"), Input("refresh-interval", "n_intervals"))
def trade_composition(_):
    fig = go.Figure()
    if trade.empty:
        fig.update_layout(**LAYOUT)
        return fig

    sec_col = "section" if "section" in trade.columns else None
    if not sec_col:
        fig.update_layout(**LAYOUT)
        return fig

    # SITC section labels — conflict-relevant categories only
    SITC_LABELS = {
        "3": "Mineral Fuels & Lubricants",
        "0": "Food & Live Animals",
        "5": "Chemicals",
        "4": "Animal & Vegetable Oils (Palm Oil)",
    }

    d = trade[(trade["date"] >= datetime.now() - timedelta(days=730)) &
              (trade[sec_col].isin(SITC_LABELS.keys()))].copy()
    d["exports"] = pd.to_numeric(d["exports"], errors="coerce")
    d["label"] = d[sec_col].map(SITC_LABELS)

    colors = {
        "Mineral Fuels & Lubricants": COLORS["accent"],
        "Food & Live Animals": COLORS["gold"],
        "Chemicals": COLORS["purple"],
        "Animal & Vegetable Oils (Palm Oil)": COLORS["green"],
    }

    for label, color in colors.items():
        sub = d[d["label"] == label].sort_values("date")
        if sub.empty:
            continue
        fig.add_trace(go.Scatter(
            x=sub["date"], y=sub["exports"] / 1e9,
            mode="lines", name=label,
            line=dict(color=color, width=2.5),
            hovertemplate=f"<b>{label}</b><br>%{{x|%b %Y}}: RM%{{y:.1f}}bn<extra></extra>",
        ))

    # ME conflict escalation event marker with label
    iran_date = pd.to_datetime("2026-02-28")
    if not d.empty and iran_date >= d["date"].min():
        fig.add_vline(x=iran_date, line_dash="dot", line_color=COLORS["accent"], line_width=1)
        fig.add_annotation(x=iran_date, y=d["exports"].max() / 1e9 * 0.95,
                          text="ME conflict\nescalation\n28 Feb 2026", showarrow=False,
                          font=dict(color=COLORS["accent"], size=9))

    fig.update_layout(**LAYOUT, yaxis_title="RM billion")
    fig.update_layout(legend=dict(orientation="h", yanchor="bottom", y=1.02,
                                  xanchor="left", x=0,
                                  bgcolor="rgba(0,0,0,0)", borderwidth=0))
    return fig


@app.callback(Output("gdp-growth-chart", "figure"), Input("refresh-interval", "n_intervals"))
def gdp_growth_chart(_):
    fig = go.Figure()
    if gdp_growth.empty:
        fig.update_layout(**LAYOUT)
        return fig

    d = gdp_growth[gdp_growth["date"] >= datetime(2019, 1, 1)]
    colors = [COLORS["green"] if v >= 0 else COLORS["accent"] for v in d["gdp_yoy"]]

    fig.add_trace(go.Bar(
        x=d["date"], y=d["gdp_yoy"],
        marker_color=colors,
        hovertemplate="<b>%{x|%Y Q}</b><br>GDP: %{y:.1f}% YoY<extra></extra>",
    ))
    fig.add_hline(y=0, line_color=COLORS["subtext"], line_width=1)
    # Mark latest GDP bar
    if not d.empty:
        last = d.iloc[-1]
        mark_latest(fig, last["date"], last["gdp_yoy"],
                   f"{last['gdp_yoy']:.1f}%", COLORS["text"])
    fig.update_layout(**LAYOUT, yaxis_title="% YoY")
    return fig


# --- GDP by Sector (individual sparkline charts) ---
GDP_SECTORS = {
    "gdp-agri-chart": ("p1", COLORS["green"], "Agriculture"),
    "gdp-mining-chart": ("p2", COLORS["gold"], "Mining & Quarrying"),
    "gdp-mfg-chart": ("p3", COLORS["secondary"], "Manufacturing"),
    "gdp-cons-chart": ("p4", COLORS["orange"], "Construction"),
    "gdp-services-chart": ("p5", COLORS["purple"], "Services"),
}

def make_sector_chart(sector_code, color, label):
    fig = go.Figure()
    if gdp_sector.empty or "series" not in gdp_sector.columns:
        fig.update_layout(**LAYOUT)
        return fig

    d = gdp_sector[(gdp_sector["sector"] == sector_code) &
                   (gdp_sector["series"] == "growth_yoy") &
                   (gdp_sector["date"] >= datetime(2019, 1, 1))].copy()
    d["value"] = pd.to_numeric(d["value"], errors="coerce")

    if d.empty:
        fig.update_layout(**LAYOUT)
        return fig

    colors = [color if v >= 0 else COLORS["accent"] for v in d["value"]]
    fig.add_trace(go.Bar(
        x=d["date"], y=d["value"],
        marker_color=colors,
        hovertemplate=f"<b>{label}</b><br>%{{x|%Y Q}}: %{{y:.1f}}%<extra></extra>",
    ))
    fig.add_hline(y=0, line_color=COLORS["subtext"], line_width=1)

    # Latest value
    if not d.empty:
        last = d.iloc[-1]
        mark_latest(fig, last["date"], last["value"],
                   f"{last['value']:.1f}%", color)

    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family=FONT, color=COLORS["text"]),
        margin=dict(t=10, b=30, l=40, r=10),
        xaxis=dict(gridcolor=COLORS["border"], showgrid=False),
        yaxis=dict(gridcolor=COLORS["border"], showgrid=True, zeroline=False,
                   title="% YoY"),
        showlegend=False,
    )
    return fig

for chart_id, (code, color, label) in GDP_SECTORS.items():
    @app.callback(Output(chart_id, "figure"), Input("refresh-interval", "n_intervals"))
    def _sector_cb(_, _code=code, _color=color, _label=label):
        return make_sector_chart(_code, _color, _label)


@app.callback(Output("ppi-headline-chart", "figure"),
              [Input("ppi-headline-range", "value"), Input("refresh-interval", "n_intervals")])
def ppi_headline_chart(year_start, _):
    fig = go.Figure()
    if ppi_ts.empty:
        fig.add_annotation(text="PPI data not available",
                          xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False,
                          font=dict(color=COLORS["subtext"]))
        fig.update_layout(**LAYOUT)
        return fig

    if year_start == "12M":
        cutoff = datetime.now() - timedelta(days=365)
    elif year_start == "2Y":
        cutoff = datetime.now() - timedelta(days=730)
    else:
        cutoff = datetime(int(year_start), 1, 1)
    d = ppi_ts[ppi_ts["date"] >= cutoff]

    fig.add_trace(go.Scatter(
        x=d["date"], y=d["value"],
        mode="lines",
        line=dict(color=COLORS["orange"], width=2.5),
        fill="tozeroy",
        fillcolor="rgba(230,126,34,0.15)",
        name="PPI Overall",
        hovertemplate="<b>%{x|%b %Y}</b><br>PPI: %{y:.1f}% YoY<extra></extra>",
    ))

    fig.add_hline(y=0, line_color=COLORS["subtext"], line_width=1)

    if not d.empty:
        last = d.iloc[-1]
        mark_latest(fig, last["date"], last["value"],
                   f"{last['value']:+.1f}%", COLORS["orange"])

    fig.update_layout(**LAYOUT, yaxis_title="% YoY")
    return fig


@app.callback(Output("ppi-sections-chart", "figure"),
              [Input("ppi-sections-range", "value"), Input("refresh-interval", "n_intervals")])
def ppi_sections_chart(year_start, _):
    fig = go.Figure()
    if ppi_sections.empty:
        fig.add_annotation(text="PPI sectoral data not available",
                          xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False,
                          font=dict(color=COLORS["subtext"]))
        fig.update_layout(**LAYOUT)
        return fig

    if year_start == "12M":
        cutoff = datetime.now() - timedelta(days=365)
    elif year_start == "2Y":
        cutoff = datetime.now() - timedelta(days=730)
    else:
        cutoff = datetime(int(year_start), 1, 1)
    section_colors = {
        "A": COLORS["green"],       # Agriculture
        "B": COLORS["gold"],        # Mining — oil/gas upstream
        "C": COLORS["secondary"],   # Manufacturing
        "D": COLORS["purple"],      # Electricity & Gas — utility cost
        "E": COLORS["orange"],      # Water & Waste
    }

    for sec, color in section_colors.items():
        sub = ppi_sections[(ppi_sections["section"] == sec) &
                          (ppi_sections["date"] >= cutoff)]
        if sub.empty:
            continue
        fig.add_trace(go.Scatter(
            x=sub["date"], y=sub["index"],
            mode="lines", name=MSIC_LABELS.get(sec, sec),
            line=dict(color=color, width=2),
            hovertemplate=f"<b>{MSIC_LABELS.get(sec, sec)}</b><br>"
                         f"%{{x|%b %Y}}: %{{y:.1f}}%<extra></extra>",
        ))

    fig.add_hline(y=0, line_color=COLORS["subtext"], line_width=1)
    fig.update_layout(**LAYOUT, yaxis_title="% YoY")
    return fig


@app.callback(Output("checklist-table", "figure"), Input("refresh-interval", "n_intervals"))
def checklist_table(_):
    indicators = [
        ["Brent crude oil", "Daily", "Bloomberg / Yahoo Finance / EIA", "Energy", "Terms-of-trade, fiscal revenue, subsidy cost"],
        ["LNG spot (JKM)", "Daily", "S&P Global Platts / Bloomberg", "Energy", "LNG export earnings (Petronas)"],
        ["Palm oil futures (CPO)", "Daily", "Bursa Malaysia Derivatives", "Energy", "Biodiesel substitution, export revenue"],
        ["USD/MYR", "Daily", "BNM API", "FX / Capital", "Risk aversion, oil-FX nexus"],
        ["Foreign MGS holdings", "Fortnightly", "BNM Monthly Statistical Bulletin", "FX / Capital", "Portfolio flow reversals"],
        ["BNM foreign reserves", "Fortnightly", "BNM", "FX / Capital", "Intervention pressure gauge"],
        ["RON95 / Diesel pump price", "Weekly", "KPDNHEP / DOSM", "Inflation", "Fiscal subsidy cost, administered price signal"],
        ["CPI — Transport", "Monthly", "DOSM API (cpi_headline_inflation)", "Inflation", "Direct energy pass-through"],
        ["CPI — Food & Beverages", "Monthly", "DOSM API", "Inflation", "Imported food inflation"],
        ["CPI — Headline vs Core", "Monthly", "DOSM API", "Inflation", "Supply shock vs demand pressure"],
        ["Trade — SITC 3 (fuels)", "Monthly", "DOSM API (trade_sitc_1d)", "Trade", "Net fuel exporter position"],
        ["Strait of Malacca freight", "Weekly", "Freightos / Drewry", "Trade", "Shipping disruption, war risk premium"],
        ["Federal revenue (petro)", "Monthly/Qtr", "MOF / Treasury", "Fiscal", "PITA + Petronas dividend + royalties"],
        ["Subsidy spending", "Monthly/Qtr", "MOF / Treasury", "Fiscal", "RON95 + electricity subsidy bill"],
        ["KLCI (O&G, Plantation)", "Daily", "Bursa Malaysia / Bloomberg", "Markets", "Sectoral risk pricing"],
        ["MY 5Y CDS spread", "Daily", "Bloomberg / Reuters", "Markets", "Sovereign risk premium"],
        ["OPR expectations (OIS)", "Daily", "Bloomberg", "Markets", "Monetary policy expectations"],
        ["GDP (quarterly)", "Quarterly", "DOSM API", "Activity", "Demand-side impact"],
    ]

    fig = go.Figure(go.Table(
        header=dict(
            values=["<b>Indicator</b>", "<b>Frequency</b>", "<b>Source</b>",
                    "<b>Channel</b>", "<b>Why it matters</b>"],
            fill_color=COLORS["primary"],
            font=dict(color="white", size=11),
            align="left", height=36,
            line_color=COLORS["border"],
        ),
        cells=dict(
            values=list(zip(*indicators)),
            fill_color=[
                [COLORS["card"]] * len(indicators),
                [COLORS["card"]] * len(indicators),
                [COLORS["card"]] * len(indicators),
                # Color by channel
                ["rgba(231,76,60,0.15)" if row[3] == "Energy"
                 else "rgba(41,128,185,0.15)" if row[3] == "FX / Capital"
                 else "rgba(243,156,18,0.15)" if row[3] == "Inflation"
                 else "rgba(39,174,96,0.15)" if row[3] == "Trade"
                 else "rgba(142,68,173,0.15)" if row[3] == "Fiscal"
                 else "rgba(230,126,34,0.15)" if row[3] == "Markets"
                 else COLORS["card"]
                 for row in indicators],
                [COLORS["card"]] * len(indicators),
            ],
            font=dict(color=COLORS["text"], size=11),
            align="left", height=26,
            line_color=COLORS["border"],
        ),
    ))
    fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", margin=dict(t=0, b=0, l=0, r=0))
    return fig


# ── WSGI server (for Vercel / gunicorn) ───────────────────────────────────────
server = app.server

# ── Run ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Dashboard running at http://127.0.0.1:8051")
    print("Press Ctrl+C to stop.\n")
    app.run(debug=False, port=8051)

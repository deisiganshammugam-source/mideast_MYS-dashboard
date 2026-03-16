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

def load_supabase(table, order_col="date", limit=10000):
    """Fetch a table from Supabase REST API with pagination (default max 1000 rows per request)."""
    try:
        headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
        all_data = []
        page_size = 1000
        offset = 0
        while offset < limit:
            url = (f"{SUPABASE_URL}/rest/v1/{table}"
                   f"?order={order_col}.asc&limit={page_size}&offset={offset}")
            r = requests.get(url, headers=headers, timeout=30)
            if r.status_code != 200:
                print(f"  Warning: {table} returned {r.status_code}")
                break
            data = r.json()
            if not data:
                break
            all_data.extend(data)
            if len(data) < page_size:
                break  # last page
            offset += page_size
        if not all_data:
            return pd.DataFrame()
        df = pd.DataFrame(all_data)
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

# 1. Exchange rates (monthly since 1997)
fx = load_supabase("exchange_rates")

# 1b. Daily USD/MYR for 2026
usd_myr_daily = load_supabase("usd_myr_daily")
if not usd_myr_daily.empty:
    usd_myr_daily["mid"] = (usd_myr_daily["buying"] + usd_myr_daily["selling"]) / 2

# 2. CPI inflation (monthly since 2000)
cpi_headline = load_supabase("cpi_headline")
cpi_core = load_supabase("cpi_core")

# 3. Trade by commodity (monthly since 2000)
trade = load_supabase("trade_by_commodity")

# 4. GDP
gdp_sector = load_supabase("gdp_by_sector")
gdp_expenditure = load_supabase("gdp_by_expenditure")
gdp_quarterly = load_supabase("gdp_quarterly")

# 5. Interest rates
opr = load_supabase("opr_historical")

# 6. PPI
ppi = load_supabase("ppi")
ppi_1d = load_supabase("ppi_1d")

# 7. Fuel prices
fuel_prices = load_supabase("fuelprice")

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


# ── Layout helpers ────────────────────────────────────────────────────────────

def card(children, style=None):
    base = {
        "background": COLORS["card"],
        "borderRadius": "12px",
        "padding": "20px 24px",
        "border": f"1px solid {COLORS['border']}",
        "boxShadow": "0 4px 20px rgba(0,0,0,0.3)",
        "minWidth": "260px",
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


LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family=FONT, color=COLORS["text"]),
    margin=dict(t=40, b=40, l=50, r=20),
    legend=dict(bgcolor="rgba(0,0,0,0)", bordercolor=COLORS["border"],
                borderwidth=1, font=dict(size=11)),
    xaxis=dict(gridcolor=COLORS["border"], showgrid=True, zeroline=False),
    yaxis=dict(gridcolor=COLORS["border"], showgrid=True, zeroline=False),
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
            /* Prevent horizontal overflow */
            html, body { overflow-x: hidden; max-width: 100vw; }

            /* Mobile-responsive overrides */
            @media screen and (max-width: 768px) {
                /* Reduce page padding on small screens */
                #react-entry-point > div { padding: 12px 10px !important; }

                /* Make header text smaller */
                h1 { font-size: 18px !important; }
                h2 { font-size: 15px !important; }
                h3 { font-size: 12px !important; }

                /* Cards: reduce padding, let them fill width */
                #react-entry-point > div > div > div {
                    min-width: 0 !important;
                }

                /* Reduce chart heights on mobile */
                .js-plotly-plot, .dash-graph {
                    min-width: 0 !important;
                }
                .dash-graph > div { height: auto !important; min-height: 220px; }

                /* KPI value text smaller on mobile */
                .kpi-value { font-size: 20px !important; }
            }

            /* Tablet adjustments */
            @media screen and (max-width: 1024px) {
                #react-entry-point > div { padding: 16px 16px !important; }
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

    # ── KPI Row ───────────────────────────────────────────────────────────────
    html.Div([
        card(kpi("USD/MYR", usd_val, f"{usd_chg}  ({usd_date})",
                 COLORS["down"] if usd_chg.startswith("+") else COLORS["up"]), {"flex": "1"}),
        card(kpi("Headline CPI (YoY)", headline_val, headline_date, COLORS["accent"]), {"flex": "1"}),
        card(kpi("Transport CPI (YoY)", transport_val, transport_date, COLORS["orange"]), {"flex": "1"}),
        card(kpi("Food CPI (YoY)", food_val, food_date, COLORS["gold"]), {"flex": "1"}),
        card(kpi("Fuel Trade Balance", petro_bal_val, f"SITC 3 · {petro_bal_date}", COLORS["green"]), {"flex": "1"}),
        card(kpi("OPR", opr_val, opr_date, COLORS["secondary"]), {"flex": "1"}),
    ], style={"display": "flex", "gap": "12px", "marginBottom": "8px", "flexWrap": "wrap"}),

    # KPI Row 2 — fuel prices (subsidized + market)
    html.Div([
        card(kpi("RON95 (BUDI)", ron95_val, f"Subsidized · {fuel_date_str}", COLORS["green"]), {"flex": "1"}),
        card(kpi("RON95 (Market)", ron95_market_val, f"Ceiling · {fuel_date_str}", COLORS["orange"]), {"flex": "1"}),
        card(kpi("Diesel (Targeted)", diesel_val, f"Subsidized · {fuel_date_str}", COLORS["green"]), {"flex": "1"}),
        card(kpi("Diesel (Market)", diesel_market_val, f"Unsubsidized · {fuel_date_str}", COLORS["orange"]), {"flex": "1"}),
    ], style={"display": "flex", "gap": "12px", "marginBottom": "8px",
              "maxWidth": "100%", "flexWrap": "wrap"}),

    # ══════════════════════════════════════════════════════════════════════════
    # SPOTLIGHT: USD/MYR DAILY TRACKING (YTD & Since Iran Bombing)
    # ══════════════════════════════════════════════════════════════════════════
    section_header("USD/MYR Daily Tracker",
                   "Year-to-date and since Iran bombing (late February 2026)  |  Source: BNM daily rates"),

    html.Div([
        card([
            html.H3("USD/MYR — Year to Date (2026)",
                    style={"margin": "0 0 12px", "fontSize": "13px", "color": COLORS["subtext"],
                           "fontWeight": "600", "textTransform": "uppercase"}),
            dcc.Graph(id="usd-myr-ytd", style={"height": "340px"},
                      config={"displayModeBar": False}),
        ], {"flex": "1"}),

        card([
            html.H3("USD/MYR — Since Iran Bombing (25 Feb 2026)",
                    style={"margin": "0 0 12px", "fontSize": "13px", "color": COLORS["subtext"],
                           "fontWeight": "600", "textTransform": "uppercase"}),
            dcc.Graph(id="usd-myr-iran", style={"height": "340px"},
                      config={"displayModeBar": False}),
        ], {"flex": "1"}),
    ], style={"display": "flex", "gap": "16px", "marginBottom": "20px", "flexWrap": "wrap"}),

    # ══════════════════════════════════════════════════════════════════════════
    # SECTION 1: EXCHANGE RATE & CAPITAL FLOWS
    # ══════════════════════════════════════════════════════════════════════════
    section_header("1. Exchange Rate & Capital Flows",
                   "MYR sensitivity to global risk aversion and oil prices"),

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
                    style={"margin": "0 0 12px", "fontSize": "13px", "color": COLORS["subtext"],
                           "fontWeight": "600", "textTransform": "uppercase"}),
            dcc.Graph(id="ppi-headline-chart", style={"height": "300px"},
                      config={"displayModeBar": False}),
        ], {"flex": "1"}),

        card([
            html.H3("PPI by Sector  (% YoY, Monthly)",
                    style={"margin": "0 0 12px", "fontSize": "13px", "color": COLORS["subtext"],
                           "fontWeight": "600", "textTransform": "uppercase"}),
            dcc.Graph(id="ppi-sections-chart", style={"height": "300px"},
                      config={"displayModeBar": False}),
        ], {"flex": "1"}),
    ], style={"display": "flex", "gap": "16px", "marginBottom": "20px", "flexWrap": "wrap"}),

    # ══════════════════════════════════════════════════════════════════════════
    # SECTION 3: TRADE & EXTERNAL SECTOR
    # ══════════════════════════════════════════════════════════════════════════
    section_header("3. Trade & External Sector",
                   "Petroleum trade balance, overall trade — terms-of-trade channel"),

    html.Div([
        card([
            html.H3("Overall Trade Balance  (RM)",
                    style={"margin": "0 0 12px", "fontSize": "13px", "color": COLORS["subtext"],
                           "fontWeight": "600", "textTransform": "uppercase"}),
            dcc.Graph(id="trade-overall-chart", style={"height": "300px"},
                      config={"displayModeBar": False}),
        ], {"flex": "1"}),

        card([
            html.H3("Mineral Fuels Trade  (SITC 3, RM)",
                    style={"margin": "0 0 12px", "fontSize": "13px", "color": COLORS["subtext"],
                           "fontWeight": "600", "textTransform": "uppercase"}),
            dcc.Graph(id="trade-petroleum-chart", style={"height": "300px"},
                      config={"displayModeBar": False}),
        ], {"flex": "1"}),
    ], style={"display": "flex", "gap": "16px", "marginBottom": "20px", "flexWrap": "wrap"}),

    # Trade composition — key conflict-sensitive categories
    card([
        html.H3("Conflict-Sensitive Exports — Mineral Fuels, Food, Chemicals & Palm Oil  (RM billion)",
                style={"margin": "0 0 12px", "fontSize": "13px", "color": COLORS["subtext"],
                       "fontWeight": "600", "textTransform": "uppercase"}),
        dcc.Graph(id="trade-composition-chart", style={"height": "360px"},
                  config={"displayModeBar": False}),
    ], {"marginBottom": "20px"}),

    # ══════════════════════════════════════════════════════════════════════════
    # SECTION 4: REAL ACTIVITY
    # ══════════════════════════════════════════════════════════════════════════
    section_header("4. Real Activity",
                   "GDP — demand-side impact of the conflict"),

    card([
        html.H3("GDP Growth  (% YoY, Quarterly)",
                style={"margin": "0 0 12px", "fontSize": "13px", "color": COLORS["subtext"],
                       "fontWeight": "600", "textTransform": "uppercase"}),
        dcc.Graph(id="gdp-growth-chart", style={"height": "300px"},
                  config={"displayModeBar": False}),
    ], {"marginBottom": "20px"}),

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
                        html.Li("Petronas dividends & special dividends"),
                        html.Li("Petroleum Income Tax (PITA)"),
                        html.Li("Petroleum royalties to states"),
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
                    "Petronas revenues rise while RON95 subsidy cost remains manageable. "
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
    iran_date = pd.to_datetime("2026-02-25")

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

    # Iran bombing marker
    fig.add_vline(x=iran_date, line_dash="dash", line_color=COLORS["accent"], line_width=1.5)
    fig.add_annotation(x=iran_date, y=df["mid"].max(),
                      text="Iran bombing", showarrow=True, arrowhead=2,
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


# --- USD/MYR Daily Tracker: Since Iran Bombing ---
@app.callback(Output("usd-myr-iran", "figure"), Input("refresh-interval", "n_intervals"))
def usd_myr_iran(_):
    fig = go.Figure()
    iran_date = pd.to_datetime("2026-02-25")

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

    # Iran bombing marker
    fig.add_vline(x=iran_date, line_dash="dash", line_color=COLORS["accent"], line_width=1.5)
    fig.add_annotation(x=iran_date, y=df["mid"].max(),
                      text="Iran bombing", showarrow=True, arrowhead=2,
                      font=dict(color=COLORS["accent"], size=10),
                      arrowcolor=COLORS["accent"], yshift=10)

    # Pre vs post event
    pre = df[df["date"] < iran_date]
    post = df[df["date"] >= iran_date]
    if not pre.empty and not post.empty:
        pre_avg = pre["mid"].mean()
        post_avg = post["mid"].mean()
        chg = post_avg - pre_avg
        fig.add_annotation(
            text=f"Pre-event avg: {pre_avg:.4f}<br>"
                 f"Post-event avg: {post_avg:.4f}<br>"
                 f"Shift: {chg:+.4f}",
            xref="paper", yref="paper", x=0.98, y=0.98,
            showarrow=False, font=dict(color=COLORS["text"], size=11),
            align="right", bgcolor="rgba(0,0,0,0.5)", borderpad=6,
        )

    fig.update_layout(**LAYOUT, yaxis_title="MYR per USD", bargap=0.3)
    fig.update_xaxes(gridcolor=COLORS["border"], dtick="D1",
                     tickformat="%d %b", showgrid=True)
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
        fill="tozeroy",
        fillcolor="rgba(41,128,185,0.1)",
        hovertemplate="<b>%{x|%b %Y}</b><br>USD/MYR: %{y:.4f}<extra></extra>",
    ))

    # Add key event annotations if in range
    events = [
        ("2023-10-07", "Hamas attack"),
        ("2024-04-13", "Iran strikes"),
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
        fill="tozeroy",
        fillcolor="rgba(243,156,18,0.1)",
        hovertemplate="<b>%{x|%b %Y}</b><br>SAR/MYR: %{y:.4f}<extra></extra>",
    ))
    fig.update_layout(**LAYOUT, yaxis_title="MYR per SAR")
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
    cutoff = datetime.now() - timedelta(days=1825)

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
    events = [("2023-10-07", "Hamas"), ("2024-04-13", "Iran")]
    for date_str, label in events:
        fig.add_vline(x=pd.to_datetime(date_str), line_dash="dot",
                     line_color=COLORS["accent"], line_width=1)

    fig.add_hline(y=0, line_dash="dash", line_color=COLORS["subtext"], line_width=1)
    fig.update_layout(**LAYOUT, yaxis_title="% YoY")
    return fig


@app.callback(Output("headline-core-chart", "figure"), Input("refresh-interval", "n_intervals"))
def headline_core(_):
    fig = go.Figure()
    cutoff = datetime.now() - timedelta(days=1825)

    if not cpi_overall.empty:
        d = cpi_overall[cpi_overall["date"] >= cutoff]
        fig.add_trace(go.Scatter(
            x=d["date"], y=d["headline_yoy"],
            mode="lines", name="Headline",
            line=dict(color=COLORS["secondary"], width=2),
        ))

    if not cpi_core_ts.empty:
        d = cpi_core_ts[cpi_core_ts["date"] >= cutoff]
        fig.add_trace(go.Scatter(
            x=d["date"], y=d["core_yoy"],
            mode="lines", name="Core",
            line=dict(color=COLORS["green"], width=2, dash="dash"),
        ))

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

    # Filter for price levels only (exclude weekly change rows)
    df = fuel_ts.copy()
    if "series_type" in df.columns:
        df = df[df["series_type"] == "level"]

    # Show from 2022 onwards (subsidized price era)
    df = df[df["date"] >= pd.to_datetime("2022-01-01")]

    # RON95 market/ceiling price
    if "ron95" in df.columns:
        fig.add_trace(go.Scatter(
            x=df["date"], y=pd.to_numeric(df["ron95"], errors="coerce"),
            mode="lines", name="RON95 (Ceiling)",
            line=dict(color=COLORS["accent"], width=2.5),
            hovertemplate="<b>RON95 Ceiling</b><br>%{x|%d %b %Y}: RM%{y:.2f}<extra></extra>",
        ))

    # RON95 BUDI subsidized price
    if "ron95_budi95" in df.columns:
        budi = pd.to_numeric(df["ron95_budi95"], errors="coerce")
        fig.add_trace(go.Scatter(
            x=df["date"], y=budi,
            mode="lines", name="RON95 (BUDI Subsidy)",
            line=dict(color=COLORS["green"], width=2.5, dash="dash"),
            hovertemplate="<b>RON95 BUDI</b><br>%{x|%d %b %Y}: RM%{y:.2f}<extra></extra>",
        ))

    # RON97 (fully market-determined)
    if "ron97" in df.columns:
        fig.add_trace(go.Scatter(
            x=df["date"], y=pd.to_numeric(df["ron97"], errors="coerce"),
            mode="lines", name="RON97 (Market)",
            line=dict(color=COLORS["gold"], width=2),
            hovertemplate="<b>RON97</b><br>%{x|%d %b %Y}: RM%{y:.2f}<extra></extra>",
        ))

    # Diesel market/unsubsidized
    if "diesel" in df.columns:
        fig.add_trace(go.Scatter(
            x=df["date"], y=pd.to_numeric(df["diesel"], errors="coerce"),
            mode="lines", name="Diesel (Market)",
            line=dict(color=COLORS["orange"], width=2),
            hovertemplate="<b>Diesel Market</b><br>%{x|%d %b %Y}: RM%{y:.2f}<extra></extra>",
        ))

    # Diesel subsidized (East Malaysia / targeted)
    if "diesel_eastmsia" in df.columns:
        d_sub = pd.to_numeric(df["diesel_eastmsia"], errors="coerce")
        fig.add_trace(go.Scatter(
            x=df["date"], y=d_sub,
            mode="lines", name="Diesel (Targeted Subsidy)",
            line=dict(color=COLORS["secondary"], width=2, dash="dash"),
            hovertemplate="<b>Diesel Targeted</b><br>%{x|%d %b %Y}: RM%{y:.2f}<extra></extra>",
        ))

    # Key event markers
    events = [
        ("2023-10-07", "Hamas attack"),
        ("2024-06-10", "Diesel subsidy\nrationalisation"),
        ("2025-09-30", "RON95 subsidy\nrationalisation"),
    ]
    for date_str, label in events:
        evt = pd.to_datetime(date_str)
        if not df.empty and evt >= df["date"].min():
            fig.add_vline(x=evt, line_dash="dot", line_color=COLORS["accent"], line_width=1)
            fig.add_annotation(x=evt, y=4.5,
                             text=label, showarrow=False,
                             font=dict(color=COLORS["accent"], size=9), yshift=0)

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
        margin=dict(t=10, b=40, l=200, r=10),
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

    d = trade_overall[trade_overall["date"] >= datetime.now() - timedelta(days=730)].copy()
    recent_cutoff = d["date"].max() - timedelta(days=180)

    # Older months — muted
    older = d[d["date"] < recent_cutoff]
    if not older.empty:
        fig.add_trace(go.Bar(x=older["date"], y=older["exports"] / 1e9,
                            name="Exports", marker_color=COLORS["green"], opacity=0.3,
                            showlegend=False))
        fig.add_trace(go.Bar(x=older["date"], y=older["imports"] / 1e9,
                            name="Imports", marker_color=COLORS["accent"], opacity=0.3,
                            showlegend=False))

    # Recent 6 months — bold
    recent = d[d["date"] >= recent_cutoff]
    if not recent.empty:
        fig.add_trace(go.Bar(x=recent["date"], y=recent["exports"] / 1e9,
                            name="Exports", marker_color=COLORS["green"], opacity=0.9))
        fig.add_trace(go.Bar(x=recent["date"], y=recent["imports"] / 1e9,
                            name="Imports", marker_color=COLORS["accent"], opacity=0.9))

    # Balance line + 3-month MA
    fig.add_trace(go.Scatter(
        x=d["date"], y=d["balance"] / 1e9, name="Balance",
        mode="lines", line=dict(color=COLORS["gold"], width=1, dash="dot"), opacity=0.5,
    ))
    d["balance_ma"] = d["balance"].rolling(3, min_periods=1).mean()
    fig.add_trace(go.Scatter(
        x=d["date"], y=d["balance_ma"] / 1e9, name="Balance (3m MA)",
        mode="lines", line=dict(color=COLORS["gold"], width=3),
    ))

    events = [("2023-10-07", "Hamas"), ("2024-04-13", "Iran"), ("2026-02-25", "Iran bombing")]
    for date_str, label in events:
        evt = pd.to_datetime(date_str)
        if not d.empty and evt >= d["date"].min() and evt <= d["date"].max():
            fig.add_vline(x=evt, line_dash="dot", line_color=COLORS["accent"], line_width=1)
            fig.add_annotation(x=evt, y=d["exports"].max() / 1e9, text=label,
                             showarrow=False, font=dict(color=COLORS["accent"], size=9), yshift=10)

    fig.update_layout(**LAYOUT, barmode="group", yaxis_title="RM billion")
    return fig


@app.callback(Output("trade-petroleum-chart", "figure"), Input("refresh-interval", "n_intervals"))
def trade_petroleum_chart(_):
    fig = go.Figure()
    if trade_petroleum.empty:
        fig.add_annotation(text="No SITC 3 trade data", xref="paper", yref="paper",
                          x=0.5, y=0.5, showarrow=False, font=dict(color=COLORS["subtext"]))
        fig.update_layout(**LAYOUT)
        return fig

    d = trade_petroleum[trade_petroleum["date"] >= datetime.now() - timedelta(days=730)].copy()
    recent_cutoff = d["date"].max() - timedelta(days=180)

    # Older months — muted
    older = d[d["date"] < recent_cutoff]
    if not older.empty:
        fig.add_trace(go.Bar(x=older["date"], y=older["exports"] / 1e9,
                            name="Fuel Exports", marker_color=COLORS["green"], opacity=0.3,
                            showlegend=False))
        fig.add_trace(go.Bar(x=older["date"], y=older["imports"] / 1e9,
                            name="Fuel Imports", marker_color=COLORS["accent"], opacity=0.3,
                            showlegend=False))

    # Recent 6 months — bold
    recent = d[d["date"] >= recent_cutoff]
    if not recent.empty:
        fig.add_trace(go.Bar(x=recent["date"], y=recent["exports"] / 1e9,
                            name="Fuel Exports", marker_color=COLORS["green"], opacity=0.9))
        fig.add_trace(go.Bar(x=recent["date"], y=recent["imports"] / 1e9,
                            name="Fuel Imports", marker_color=COLORS["accent"], opacity=0.9))

    # Net balance line + 3m MA
    fig.add_trace(go.Scatter(
        x=d["date"], y=d["balance"] / 1e9, name="Net Balance",
        mode="lines", line=dict(color=COLORS["gold"], width=1, dash="dot"), opacity=0.5,
    ))
    d["balance_ma"] = d["balance"].rolling(3, min_periods=1).mean()
    fig.add_trace(go.Scatter(
        x=d["date"], y=d["balance_ma"] / 1e9, name="Net Balance (3m MA)",
        mode="lines", line=dict(color=COLORS["gold"], width=3),
    ))

    # Latest net position annotation
    if not d.empty:
        last = d.iloc[-1]
        net = last["balance"] / 1e9
        fig.add_annotation(
            text=f"Latest: RM {net:+.1f}bn",
            xref="paper", yref="paper", x=0.98, y=0.98,
            showarrow=False, font=dict(color=COLORS["gold"], size=12, weight="bold"),
            align="right", bgcolor="rgba(0,0,0,0.5)", borderpad=6,
        )

    fig.update_layout(**LAYOUT, barmode="group", yaxis_title="RM billion")
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

    # Event marker
    iran_date = pd.to_datetime("2026-02-25")
    if not d.empty and iran_date >= d["date"].min():
        fig.add_vline(x=iran_date, line_dash="dot", line_color=COLORS["accent"], line_width=1)

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
    fig.update_layout(**LAYOUT, yaxis_title="% YoY")
    return fig


@app.callback(Output("ppi-headline-chart", "figure"), Input("refresh-interval", "n_intervals"))
def ppi_headline_chart(_):
    fig = go.Figure()
    if ppi_ts.empty:
        fig.add_annotation(text="PPI data not available",
                          xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False,
                          font=dict(color=COLORS["subtext"]))
        fig.update_layout(**LAYOUT)
        return fig

    d = ppi_ts[ppi_ts["date"] >= datetime(2021, 1, 1)]

    # Area fill — positive green, negative red
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

    # Latest value annotation
    if not d.empty:
        last = d.iloc[-1]
        fig.add_annotation(
            text=f"Latest: {last['value']:+.1f}%  ({last['date'].strftime('%b %Y')})",
            xref="paper", yref="paper", x=0.98, y=0.98,
            showarrow=False, font=dict(color=COLORS["orange"], size=11),
            align="right", bgcolor="rgba(0,0,0,0.5)", borderpad=6,
        )

    fig.update_layout(**LAYOUT, yaxis_title="% YoY")
    return fig


@app.callback(Output("ppi-sections-chart", "figure"), Input("refresh-interval", "n_intervals"))
def ppi_sections_chart(_):
    fig = go.Figure()
    if ppi_sections.empty:
        fig.add_annotation(text="PPI sectoral data not available",
                          xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False,
                          font=dict(color=COLORS["subtext"]))
        fig.update_layout(**LAYOUT)
        return fig

    section_colors = {
        "A": COLORS["green"],       # Agriculture
        "B": COLORS["gold"],        # Mining — oil/gas upstream
        "C": COLORS["secondary"],   # Manufacturing
        "D": COLORS["purple"],      # Electricity & Gas — utility cost
        "E": COLORS["orange"],      # Water & Waste
    }

    for sec, color in section_colors.items():
        sub = ppi_sections[(ppi_sections["section"] == sec) &
                          (ppi_sections["date"] >= datetime(2021, 1, 1))]
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
    fig.update_layout(legend=dict(orientation="h", yanchor="bottom", y=1.02,
                                  xanchor="left", x=0,
                                  bgcolor="rgba(0,0,0,0)", borderwidth=0))
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

"""
Vercel Cron endpoint — fetches latest data from BNM/DOSM APIs and upserts into Supabase.
Triggered daily at 8am MYT (midnight UTC) via vercel.json cron config.
"""
import os
import json
import requests
import pandas as pd
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler

SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://irzjxcwgihjdootxjyuu.supabase.co")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
DOSM_BASE = "https://api.data.gov.my/data-catalogue"
BNM_BASE = "https://api.bnm.gov.my/public"
BNM_HEADERS = {"Accept": "application/vnd.BNM.API.v1+json"}
CRON_SECRET = os.environ.get("CRON_SECRET", "")


def supabase_headers():
    return {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates,return=minimal",
    }


def upsert(table, records):
    """Upsert records into a Supabase table (relies on unique indexes for conflict resolution)."""
    if not records:
        return 0
    r = requests.post(
        f"{SUPABASE_URL}/rest/v1/{table}",
        headers=supabase_headers(),
        json=records,
    )
    if r.status_code not in (200, 201):
        print(f"  ERROR upserting {table}: {r.status_code} {r.text[:300]}")
        return 0
    return len(records)


def fetch_dosm(dataset_id, limit=2000):
    """Fetch data from DOSM open API."""
    try:
        r = requests.get(f"{DOSM_BASE}?id={dataset_id}&limit={limit}", timeout=60)
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        print(f"  Warning: DOSM {dataset_id}: {e}")
    return []


def fetch_bnm_exchange_rates():
    """Fetch daily USD/MYR from BNM for current year."""
    rows = []
    try:
        year = datetime.now().year
        r = requests.get(
            f"{BNM_BASE}/exchange-rate/usd/year/{year}",
            headers=BNM_HEADERS, timeout=30,
        )
        if r.status_code == 200:
            data = r.json().get("data", [])
            for entry in data:
                rate = entry.get("rate", {})
                rows.append({
                    "date": entry.get("date"),
                    "buying": rate.get("buying"),
                    "selling": rate.get("selling"),
                })
    except Exception as e:
        print(f"  Warning: BNM exchange rates: {e}")
    return rows


def refresh_usd_myr_daily():
    """Refresh daily USD/MYR rates."""
    rows = fetch_bnm_exchange_rates()
    return upsert("usd_myr_daily", rows)


def refresh_cpi():
    """Refresh CPI headline and core from DOSM."""
    count = 0
    # CPI headline
    data = fetch_dosm("cpi_headline_inflation", limit=5000)
    if data:
        df = pd.DataFrame(data)
        records = json.loads(df.to_json(orient="records"))
        count += upsert("cpi_headline", records)

    # CPI core
    data = fetch_dosm("cpi_core_inflation", limit=2000)
    if data:
        df = pd.DataFrame(data)
        records = json.loads(df.to_json(orient="records"))
        count += upsert("cpi_core", records)
    return count


def refresh_ppi():
    """Refresh PPI headline and by section from DOSM."""
    count = 0
    data = fetch_dosm("ppi", limit=1000)
    if data:
        df = pd.DataFrame(data)
        records = json.loads(df.to_json(orient="records"))
        count += upsert("ppi", records)

    data = fetch_dosm("ppi_1d", limit=5000)
    if data:
        df = pd.DataFrame(data)
        records = json.loads(df.to_json(orient="records"))
        count += upsert("ppi_1d", records)
    return count


def refresh_fuelprice():
    """Refresh fuel prices from DOSM."""
    data = fetch_dosm("fuelprice", limit=2000)
    if data:
        df = pd.DataFrame(data)
        # Only keep level rows
        if "series_type" in df.columns:
            df = df[df["series_type"] == "level"]
        records = json.loads(df.to_json(orient="records"))
        return upsert("fuelprice", records)
    return 0


def refresh_trade():
    """Refresh trade by commodity from DOSM."""
    data = fetch_dosm("trade_sitc_1d", limit=5000)
    if data:
        df = pd.DataFrame(data)
        records = json.loads(df.to_json(orient="records"))
        return upsert("trade_by_commodity", records)
    return 0


def refresh_gdp():
    """Refresh GDP data from DOSM."""
    count = 0
    for dataset, table in [
        ("gdp_quarterly", "gdp_quarterly"),
        ("gdp_1d", "gdp_by_sector"),
        ("gdp_expenditure_1d", "gdp_by_expenditure"),
    ]:
        data = fetch_dosm(dataset, limit=2000)
        if data:
            df = pd.DataFrame(data)
            records = json.loads(df.to_json(orient="records"))
            count += upsert(table, records)
    return count


def refresh_exchange_rates():
    """Refresh monthly exchange rates from DOSM."""
    data = fetch_dosm("exchangerates", limit=5000)
    if data:
        df = pd.DataFrame(data)
        records = json.loads(df.to_json(orient="records"))
        return upsert("exchange_rates", records)
    return 0


def refresh_opr():
    """Refresh OPR from BNM."""
    try:
        r = requests.get(f"{BNM_BASE}/opr", headers=BNM_HEADERS, timeout=30)
        if r.status_code == 200:
            data = r.json().get("data", {})
            row = {
                "date": data.get("effective_date") or datetime.now().strftime("%Y-%m-%d"),
                "opr_pct": data.get("opr"),
                "change_in_opr": data.get("change_in_opr", 0),
            }
            return upsert("opr_historical", [row])
    except Exception as e:
        print(f"  Warning: BNM OPR: {e}")
    return 0


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        # Verify cron secret if set
        if CRON_SECRET:
            auth = self.headers.get("Authorization", "")
            if auth != f"Bearer {CRON_SECRET}":
                self.send_response(401)
                self.end_headers()
                self.wfile.write(b'{"error": "Unauthorized"}')
                return

        results = {}
        try:
            results["usd_myr_daily"] = refresh_usd_myr_daily()
            results["cpi"] = refresh_cpi()
            results["ppi"] = refresh_ppi()
            results["fuelprice"] = refresh_fuelprice()
            results["trade"] = refresh_trade()
            results["gdp"] = refresh_gdp()
            results["exchange_rates"] = refresh_exchange_rates()
            results["opr"] = refresh_opr()
        except Exception as e:
            results["error"] = str(e)

        results["timestamp"] = datetime.utcnow().isoformat()
        body = json.dumps(results).encode()

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

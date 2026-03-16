-- Supabase schema for Malaysia Economic Dashboard
-- Run this in the Supabase SQL Editor (Dashboard → SQL Editor → New Query)

CREATE TABLE exchange_rates (
  id BIGSERIAL PRIMARY KEY,
  date DATE NOT NULL,
  indicator TEXT,
  usd NUMERIC, eur NUMERIC, gbp NUMERIC, jpy NUMERIC, cny NUMERIC,
  sgd NUMERIC, idr NUMERIC, thb NUMERIC, sar NUMERIC, aud NUMERIC,
  nzd NUMERIC, cad NUMERIC, chf NUMERIC, hkd NUMERIC, krw NUMERIC,
  inr NUMERIC, php NUMERIC, twd NUMERIC, bnd NUMERIC, vnd NUMERIC,
  aed NUMERIC, egp NUMERIC, khr NUMERIC, mmk NUMERIC, npr NUMERIC,
  pkr NUMERIC, xdr NUMERIC
);

CREATE TABLE usd_myr_daily (
  id BIGSERIAL PRIMARY KEY,
  date DATE NOT NULL,
  buying NUMERIC,
  selling NUMERIC
);

CREATE TABLE cpi_headline (
  id BIGSERIAL PRIMARY KEY,
  date DATE NOT NULL,
  division TEXT,
  inflation_mom NUMERIC,
  inflation_yoy NUMERIC
);

CREATE TABLE cpi_core (
  id BIGSERIAL PRIMARY KEY,
  date DATE NOT NULL,
  division TEXT,
  inflation_mom NUMERIC,
  inflation_yoy NUMERIC
);

CREATE TABLE ppi (
  id BIGSERIAL PRIMARY KEY,
  date DATE NOT NULL,
  index NUMERIC,
  series TEXT,
  index_sa NUMERIC
);

CREATE TABLE ppi_1d (
  id BIGSERIAL PRIMARY KEY,
  date DATE NOT NULL,
  index NUMERIC,
  series TEXT,
  section TEXT,
  index_sa NUMERIC
);

CREATE TABLE fuelprice (
  id BIGSERIAL PRIMARY KEY,
  date DATE NOT NULL,
  ron95 NUMERIC,
  ron97 NUMERIC,
  diesel NUMERIC,
  series_type TEXT,
  ron95_budi95 NUMERIC,
  diesel_eastmsia NUMERIC
);

CREATE TABLE trade_by_commodity (
  id BIGSERIAL PRIMARY KEY,
  date DATE NOT NULL,
  exports NUMERIC,
  imports NUMERIC,
  section TEXT
);

CREATE TABLE gdp_quarterly (
  id BIGSERIAL PRIMARY KEY,
  date DATE NOT NULL,
  value NUMERIC,
  series TEXT
);

CREATE TABLE gdp_by_sector (
  id BIGSERIAL PRIMARY KEY,
  date DATE NOT NULL,
  value NUMERIC,
  sector TEXT,
  series TEXT
);

CREATE TABLE gdp_by_expenditure (
  id BIGSERIAL PRIMARY KEY,
  date DATE NOT NULL,
  type TEXT,
  value NUMERIC,
  series TEXT
);

CREATE TABLE opr_historical (
  id BIGSERIAL PRIMARY KEY,
  date DATE NOT NULL,
  opr_pct NUMERIC,
  change_in_opr NUMERIC
);

-- Create unique constraints to support upserts during daily refresh
CREATE UNIQUE INDEX idx_exchange_rates_date_ind ON exchange_rates(date, indicator);
CREATE UNIQUE INDEX idx_usd_myr_daily_date ON usd_myr_daily(date);
CREATE UNIQUE INDEX idx_cpi_headline_date_div ON cpi_headline(date, division);
CREATE UNIQUE INDEX idx_cpi_core_date_div ON cpi_core(date, division);
CREATE UNIQUE INDEX idx_ppi_date_series ON ppi(date, series);
CREATE UNIQUE INDEX idx_ppi_1d_date_series_sec ON ppi_1d(date, series, section);
CREATE UNIQUE INDEX idx_fuelprice_date ON fuelprice(date);
CREATE UNIQUE INDEX idx_trade_date_section ON trade_by_commodity(date, section);
CREATE UNIQUE INDEX idx_gdp_q_date_series ON gdp_quarterly(date, series);
CREATE UNIQUE INDEX idx_gdp_sector_date ON gdp_by_sector(date, sector, series);
CREATE UNIQUE INDEX idx_gdp_exp_date ON gdp_by_expenditure(date, type, series);
CREATE UNIQUE INDEX idx_opr_date ON opr_historical(date);

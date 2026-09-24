-- create_installed_pv.sql
--
-- Table for the HECO quarterly "Cumulative Installed PV" summaries, loaded
-- from output\heco_installed_pv.csv (built by scripts\02_extract_pv_data.py).
-- One row per utility per quarter.
--
-- Run once against the hnei_heco database:
--     psql hnei_heco -f heco_installed_solar/sql/create_installed_pv.sql

CREATE SCHEMA IF NOT EXISTS statewide;

CREATE TABLE IF NOT EXISTS statewide.installed_pv (
    "date"                   date         NOT NULL,  -- quarter-end "as of" date
    utility                  text         NOT NULL
        CHECK (utility IN ('heco', 'helco', 'meco')),
    num_systems              integer      NOT NULL CHECK (num_systems >= 0),
    pct_systems_residential  smallint     CHECK (pct_systems_residential BETWEEN 0 AND 100),
    pct_systems_commercial   smallint     CHECK (pct_systems_commercial BETWEEN 0 AND 100),
    capacity_mw              numeric(8,1) NOT NULL CHECK (capacity_mw >= 0),
    pct_capacity_residential smallint     CHECK (pct_capacity_residential BETWEEN 0 AND 100),
    pct_capacity_commercial  smallint     CHECK (pct_capacity_commercial BETWEEN 0 AND 100),
    PRIMARY KEY ("date", utility)
);

COMMENT ON TABLE statewide.installed_pv IS
    'HECO quarterly cumulative installed PV by utility, from the pv_summary PDFs. '
    'Values are as reported each quarter; HECO revises past figures ("data subject to change").';
COMMENT ON COLUMN statewide.installed_pv.utility IS
    'heco = Hawaiian Electric (Oahu), helco = Hawai''i Electric Light, meco = Maui Electric';
COMMENT ON COLUMN statewide.installed_pv.pct_systems_residential IS
    'Whole-number percent (97 = 97%). NULL for 2012 Q3, which did not report percentages.';
COMMENT ON COLUMN statewide.installed_pv.capacity_mw IS
    'Megawatts as printed: one decimal in early reports, whole MW in later ones.';

# Freight nowcast — as of 2026-09-30

**Synthetic demo data — not real statistics.**

**Composite real-economy momentum: -0.99 z** in 2026-08 (provisional: month-to-date or incomplete coverage), falling over 3 months → **Contraction** (conviction: low).

## By geography

| Geography | Month | z | 3m change | Phase | Turning point | Conviction | Coverage |
|---|---|---|---|---|---|---|---|
| Germany (DE) | 2026-09* | -1.22 | -1.05 | Contraction | provisional peak 2026-05 | medium | 67% |
| Eurozone (EA) | 2026-07 | +0.47 | +0.49 | Expansion | provisional trough 2026-03 | low | 100% |
| United States (US) | 2026-08* | -1.04 | -0.49 | Contraction | confirmed trough 2025-11 | medium | 69% |
| Arabia (GCC) (GCC) | 2026-07 | -1.10 | -0.28 | Contraction |  | medium | 100% |
| World sea trade (WORLD) | 2026-07 | -1.10 | -0.54 | Contraction |  | medium | 100% |

\* provisional

## Indicators (latest)

| Series | Geography | Mode | Last obs | Momentum | z |
|---|---|---|---|---|---|
| Truck toll mileage index (sa) | DE | road | 2026-09-30 | -9.81 % (3m3m) | -1.22 |
| Port calls, Germany (IMF PortWatch, AIS) | DE | sea | 2026-08-01 | -0.15 % (yoy) | -0.38 |
| Port calls, Eurozone ports (IMF PortWatch, AIS) | EA | sea | 2026-08-01 | +2.02 % (yoy) | +0.47 |
| Port calls, world (IMF PortWatch, AIS) | WORLD | sea | 2026-08-01 | -2.11 % (yoy) | -1.21 |
| Dry-bulk freight (Breakwave BDRY, BDI futures) | WORLD | sea | 2026-09-30 | -17.24 % (yoy) | -0.53 |
| Freight Transportation Services Index (BTS) | US | road/rail | 2026-08-01 | -5.48 % (3m3m) | -1.11 |
| Cass Freight Index, shipments | US | road | 2026-08-01 | -1.42 % (yoy) | -1.00 |
| Rail freight carloads | US | rail | 2026-08-01 | -9.17 % (3m3m) | -0.98 |
| Port calls, United States (IMF PortWatch, AIS) | US | sea | 2026-08-01 | -6.80 % (yoy) | -0.85 |
| Port calls, Gulf states (IMF PortWatch, AIS) | GCC | sea | 2026-08-01 | -3.35 % (yoy) | -1.07 |
| Strait of Hormuz transits (IMF PortWatch) | GCC | sea | 2026-08-01 | +0.37 % (yoy) | -1.17 |
| Bab el-Mandeb transits (IMF PortWatch) | GCC | sea | 2026-08-01 | -6.02 % (yoy) | -1.05 |

## Evidence: does each signal track what it claims to lead?

| Indicator → target | Months | Best lead | corr | β (HAC t) | R² | OOS RMSE vs AR | DM p | Hit rate | Publication lead | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| de_toll_mileage → de_manufacturing_production (mom) | 174 | 0m | +0.77 | +1.01 (+15.4) | 0.60 | 0.67 | 0.055 | 69% | 29 days | **evidenced** |
| de_port_calls → de_exports (yoy) | 163 | 0m | +0.77 | +0.90 (+9.2) | 0.59 | 0.97 | 0.170 | 61% | 28 days | **partial** |
| ea_port_calls → ea_manufacturing_production (yoy) | 163 | 1m | +0.70 | +0.65 (+9.3) | 0.49 | 1.00 | 0.518 | 65% | 35 days | **partial** |
| world_port_calls → world_trade_volume (yoy) | 163 | 0m | +0.85 | +0.83 (+11.6) | 0.72 | 0.96 | 0.187 | 56% | 45 days | **partial** |
| dry_bulk_freight → world_trade_volume (yoy) | 163 | 6m | +0.27 | +0.01 (+1.5) | 0.03 | 1.01 | 0.735 | 51% | 54 days | **not evidenced** |
| us_freight_tsi → us_manufacturing_production (mom) | 174 | 0m | +0.79 | +0.90 (+11.1) | 0.63 | 0.69 | 0.061 | 72% | -29 days | **evidenced** |
| us_cass_shipments → us_manufacturing_production (yoy) | 163 | 0m | +0.74 | +0.71 (+8.8) | 0.55 | 1.04 | 0.899 | 42% | 1 days | **partial** |
| us_rail_carloads → us_manufacturing_production (mom) | 174 | 0m | +0.58 | +0.59 (+4.3) | 0.33 | 0.87 | 0.129 | 66% | -24 days | **partial** |
| us_port_calls → us_goods_imports (yoy) | 163 | 0m | +0.83 | +0.89 (+9.6) | 0.69 | 0.94 | 0.011 | 64% | 25 days | **evidenced** |
| ea_port_calls → ea_exports (yoy) | 163 | 0m | +0.80 | +0.87 (+14.7) | 0.64 | 1.00 | 0.488 | 63% | 35 days | **partial** |
| gcc_port_calls → gcc_exports (yoy) | 163 | 0m | +0.77 | +0.95 (+8.4) | 0.60 | 1.00 | 0.555 | 50% | 50 days | **partial** |
| hormuz_transits → gcc_exports (yoy) | 163 | 3m | +0.28 | +0.30 (+1.2) | 0.03 | 1.02 | 0.689 | 53% | 50 days | **not evidenced** |
| bab_el_mandeb_transits → world_trade_volume (yoy) | 163 | 0m | +0.35 | +0.20 (+2.2) | 0.13 | 1.03 | 0.985 | 48% | 45 days | **partial** |

- de_port_calls → de_exports: significant in sample but no reliable out-of-sample gain
- ea_port_calls → ea_manufacturing_production: significant in sample but no reliable out-of-sample gain
- world_port_calls → world_trade_volume: significant in sample but no reliable out-of-sample gain
- us_cass_shipments → us_manufacturing_production: significant in sample but no reliable out-of-sample gain
- us_rail_carloads → us_manufacturing_production: significant in sample but no reliable out-of-sample gain
- ea_port_calls → ea_exports: significant in sample but no reliable out-of-sample gain
- gcc_port_calls → gcc_exports: significant in sample but no reliable out-of-sample gain
- bab_el_mandeb_transits → world_trade_volume: significant in sample but no reliable out-of-sample gain

*Evidenced* = significant in-sample link with the expected sign **and** a better pseudo real-time nowcast than the target's own lag (RMSE ratio < 1, Diebold-Mariano p < 0.10).

## Recent composite turning points

| Month | Kind | Status | z | Flagged |
|---|---|---|---|---|
| 2018-09 | trough | confirmed | +0.17 | 2019-02 |
| 2019-11 | peak | confirmed | +1.83 | 2020-04 |
| 2021-09 | trough | confirmed | -1.61 | 2022-02 |
| 2023-04 | peak | confirmed | +0.80 | 2023-09 |
| 2024-02 | trough | confirmed | -1.52 | 2024-07 |
| 2025-05 | peak | confirmed | +0.73 | 2025-10 |

## Tier 2 cycle / sector tilt

Phase **Contraction**, conviction low; cyclicals minus defensives -0.66.

| Sector | Tilt |
|---|---|
| healthcare | +0.33 |
| consumer staples | +0.33 |
| utilities | +0.33 |
| financials | -0.17 |
| technology | -0.17 |
| energy | -0.17 |
| industrials | -0.33 |
| materials | -0.33 |
| transport logistics | -0.33 |
| consumer discretionary | -0.33 |

## Data

| Series | Role | Last observation | Fetched | Origin |
|---|---|---|---|---|
| Truck toll mileage index (sa) | indicator | 2026-09-30 | – | genesis |
| Port calls, Germany (IMF PortWatch, AIS) | indicator | 2026-08-01 | – | portwatch |
| Port calls, Eurozone ports (IMF PortWatch, AIS) | indicator | 2026-08-01 | – | portwatch |
| Port calls, world (IMF PortWatch, AIS) | indicator | 2026-08-01 | – | portwatch |
| Dry-bulk freight (Breakwave BDRY, BDI futures) | indicator | 2026-09-30 | – | yahoo_chart |
| Freight Transportation Services Index (BTS) | indicator | 2026-08-01 | – | fred |
| Cass Freight Index, shipments | indicator | 2026-08-01 | – | fred |
| Rail freight carloads | indicator | 2026-08-01 | – | fred |
| Port calls, United States (IMF PortWatch, AIS) | indicator | 2026-08-01 | – | portwatch |
| Port calls, Gulf states (IMF PortWatch, AIS) | indicator | 2026-08-01 | – | portwatch |
| Strait of Hormuz transits (IMF PortWatch) | indicator | 2026-08-01 | – | portwatch |
| Bab el-Mandeb transits (IMF PortWatch) | indicator | 2026-08-01 | – | portwatch |
| Manufacturing production, Germany (sca) | target | 2026-07-01 | – | sdmx |
| Manufacturing production, euro area (sca) | target | 2026-07-01 | – | sdmx |
| Exports, Germany (foreign trade statistics) | target | 2026-07-01 | – | genesis |
| World trade volume (CPB World Trade Monitor) | target | 2026-07-01 | – | cpb |
| Manufacturing production, United States | target | 2026-07-01 | – | fred |
| Goods imports, United States (BOP basis) | target | 2026-07-01 | – | fred |
| Extra-euro-area export volume (sa) | target | 2026-07-01 | – | eurostat_jsonstat |
| Merchandise exports, Saudi Arabia | target | 2026-07-01 | – | fred |

## Data warnings

- SYNTHETIC DEMO DATA: these outputs are not real statistics
- de_ais_stationary: optional, no data cached yet (skipped)

# Freight nowcast — as of 2026-10-06

Live data, fetched 2026-10-06T22:52:23+00:00.

**Composite real-economy momentum: -0.14 z** in 2026-09 (provisional: month-to-date or incomplete coverage), rising over 3 months → **Recovery** (conviction: low).

⚑ Turning point: **confirmed trough** at 2026-01 (flagged 2026-06).

## By geography

| Geography | Month | z | 3m change | Phase | Turning point | Conviction | Coverage |
|---|---|---|---|---|---|---|---|
| Germany (DE) | 2026-09* | +1.22 | +0.16 | Expansion |  | low | 100% |
| Eurozone (EA) | 2026-09 | +0.13 | +0.35 | Expansion | confirmed trough 2026-01 | low | 100% |
| United States (US) | 2026-08* | -0.27 | -0.71 | Contraction | confirmed trough 2025-12 | low | 54% |
| Arabia (GCC) | 2026-09 | -2.26 | -0.16 | Contraction |  | medium | 100% |
| World sea trade (WORLD) | 2026-09 | -0.96 | -0.30 | Contraction |  | low | 100% |

\* provisional

## Indicators (latest)

| Series | Geography | Mode | Last obs | Momentum | z |
|---|---|---|---|---|---|
| Truck toll mileage index (sa) | DE | road | 2026-09-26 | +4.29 % (3m3m) | +1.26 |
| Port calls, Germany (IMF PortWatch, AIS) | DE | sea | 2026-10-02 | +3.67 % (yoy) | +1.14 |
| Port calls, Eurozone ports (IMF PortWatch, AIS) | EA | sea | 2026-10-02 | -0.56 % (yoy) | +0.13 |
| Port calls, world (IMF PortWatch, AIS) | WORLD | sea | 2026-10-02 | -6.18 % (yoy) | -1.82 |
| Dry-bulk freight (Breakwave BDRY, BDI futures) | WORLD | sea | 2026-10-06 | +93.56 % (yoy) | +0.76 |
| Freight Transportation Services Index (BTS) | US | road/rail | 2026-07-01 | -7.75 % (3m3m) | -2.00 |
| Cass Freight Index, shipments | US | road | 2026-08-01 | +2.06 % (yoy) | +1.28 |
| Rail freight carloads | US | rail | 2026-07-01 | -0.42 % (3m3m) | -0.12 |
| Port calls, United States (IMF PortWatch, AIS) | US | sea | 2026-10-02 | -2.46 % (yoy) | -1.27 |
| Port calls, Gulf states (IMF PortWatch, AIS) | GCC | sea | 2026-10-02 | -57.32 % (yoy) | -2.82 |
| Strait of Hormuz transits (IMF PortWatch) | GCC | sea | 2026-10-04 | -95.87 % (yoy) | -2.61 |
| Bab el-Mandeb transits (IMF PortWatch) | GCC | sea | 2026-10-04 | -21.71 % (yoy) | -0.62 |

## Evidence: does each signal track what it claims to lead?

| Indicator → target | Months | Best lead | corr | β (HAC t) | R² | OOS RMSE vs AR | DM p | Hit rate | Publication lead | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| de_toll_mileage → de_manufacturing_production (mom) | 222 | 0m | +0.52 | +0.77 (+2.1) | 0.27 | 0.84 | 0.117 | 82% | 29 days | **partial** |
| de_port_calls → de_exports (yoy) | 78 | 0m | +0.54 | +0.88 (+3.1) | 0.29 | 0.97 | 0.081 | 69% | 28 days | **evidenced** |
| ea_port_calls → ea_manufacturing_production (yoy) | 79 | 0m | +0.72 | +1.76 (+4.0) | 0.52 | 1.44 | 0.989 | 60% | 35 days | **partial** |
| world_port_calls → world_trade_volume (yoy) | 79 | 0m | +0.43 | +0.80 (+1.8) | 0.19 | 1.31 | 1.000 | 44% | 45 days | **not evidenced** |
| dry_bulk_freight → world_trade_volume (yoy) | 89 | 0m | +0.62 | +0.03 (+3.6) | 0.38 | 0.99 | 0.337 | 68% | 54 days | **partial** |
| us_freight_tsi → us_manufacturing_production (mom) | 318 | 0m | +0.51 | +0.52 (+2.3) | 0.26 | 0.87 | 0.097 | 75% | -29 days | **evidenced** |
| us_cass_shipments → us_manufacturing_production (yoy) | 116 | 0m | +0.75 | +0.37 (+4.6) | 0.56 | 0.84 | 0.191 | 64% | 1 days | **partial** |
| us_rail_carloads → us_manufacturing_production (mom) | 318 | 0m | +0.55 | +0.29 (+3.1) | 0.30 | 0.88 | 0.060 | 76% | -24 days | **evidenced** |
| us_port_calls → us_goods_imports (yoy) | 80 | 0m | +0.47 | +1.32 (+4.1) | 0.23 | 1.00 | 0.716 | 52% | 25 days | **partial** |
| ea_port_calls → ea_exports (yoy) | 78 | 0m | +0.74 | +1.69 (+3.9) | 0.54 | 1.00 | 0.501 | 64% | 35 days | **partial** |
| gcc_port_calls → gcc_exports (yoy) | 78 | 1m | +0.04 | +0.07 (+0.3) | 0.00 | 1.20 | 0.929 | 52% | 50 days | **not evidenced** |
| hormuz_transits → gcc_exports (yoy) | 78 | 3m | +0.36 | +0.30 (+1.2) | 0.03 | 1.29 | 0.856 | 57% | 50 days | **not evidenced** |
| bab_el_mandeb_transits → world_trade_volume (yoy) | 79 | 0m | +0.02 | +0.00 (+0.3) | 0.00 | 1.49 | 0.950 | 47% | 45 days | **not evidenced** |

- de_toll_mileage → de_manufacturing_production: significant in sample but no reliable out-of-sample gain
- ea_port_calls → ea_manufacturing_production: significant in sample but no reliable out-of-sample gain
- dry_bulk_freight → world_trade_volume: significant in sample but no reliable out-of-sample gain
- us_cass_shipments → us_manufacturing_production: significant in sample but no reliable out-of-sample gain
- us_port_calls → us_goods_imports: significant in sample but no reliable out-of-sample gain
- ea_port_calls → ea_exports: significant in sample but no reliable out-of-sample gain

*Evidenced* = significant in-sample link with the expected sign **and** a better pseudo real-time nowcast than the target's own lag (RMSE ratio < 1, Diebold-Mariano p < 0.10).

## Recent composite turning points

| Month | Kind | Status | z | Flagged |
|---|---|---|---|---|
| 2021-12 | peak | confirmed | +0.77 | 2022-05 |
| 2023-08 | trough | confirmed | -0.53 | 2024-01 |
| 2024-11 | peak | confirmed | +0.28 | 2025-04 |
| 2026-01 | trough | confirmed | -0.89 | 2026-06 |

## Tier 2 cycle / sector tilt

Phase **Recovery**, conviction low; cyclicals minus defensives +0.61.

| Sector | Tilt |
|---|---|
| industrials | +0.33 |
| materials | +0.33 |
| transport logistics | +0.33 |
| consumer discretionary | +0.33 |
| financials | +0.17 |
| technology | +0.17 |
| energy | +0.00 |
| healthcare | -0.17 |
| consumer staples | -0.33 |
| utilities | -0.33 |

## Data

| Series | Role | Last observation | Fetched | Origin |
|---|---|---|---|---|
| Truck toll mileage index (sa) | indicator | 2026-09-26 | 2026-10-06T22:51:55+00:00 | destatis:daily-toll-xlsx |
| Port calls, Germany (IMF PortWatch, AIS) | indicator | 2026-10-02 | 2026-10-06T22:52:03+00:00 | imf:portwatch |
| Port calls, Eurozone ports (IMF PortWatch, AIS) | indicator | 2026-10-02 | 2026-10-06T22:52:04+00:00 | imf:portwatch |
| Port calls, world (IMF PortWatch, AIS) | indicator | 2026-10-02 | 2026-10-06T22:52:05+00:00 | imf:portwatch |
| Dry-bulk freight (Breakwave BDRY, BDI futures) | indicator | 2026-10-06 | 2026-10-06T22:52:07+00:00 | yahoo:BDRY |
| Freight Transportation Services Index (BTS) | indicator | 2026-07-01 | 2026-10-06T22:52:07+00:00 | fred:TSIFRGHT |
| Cass Freight Index, shipments | indicator | 2026-08-01 | 2026-10-06T22:52:07+00:00 | fred:FRGSHPUSM649NCIS |
| Rail freight carloads | indicator | 2026-07-01 | 2026-10-06T22:52:07+00:00 | fred:RAILFRTCARLOADSD11 |
| Port calls, United States (IMF PortWatch, AIS) | indicator | 2026-10-02 | 2026-10-06T22:52:07+00:00 | imf:portwatch |
| Port calls, Gulf states (IMF PortWatch, AIS) | indicator | 2026-10-02 | 2026-10-06T22:52:09+00:00 | imf:portwatch |
| Strait of Hormuz transits (IMF PortWatch) | indicator | 2026-10-04 | 2026-10-06T22:52:10+00:00 | imf:portwatch |
| Bab el-Mandeb transits (IMF PortWatch) | indicator | 2026-10-04 | 2026-10-06T22:52:11+00:00 | imf:portwatch |
| Manufacturing production, Germany (sca) | target | 2026-07-01 | 2026-10-06T22:52:13+00:00 | sdmx:eurostat |
| Manufacturing production, euro area (sca) | target | 2026-07-01 | 2026-10-06T22:52:14+00:00 | sdmx:eurostat |
| Exports, Germany (foreign trade statistics) | target | 2026-06-01 | 2026-10-06T22:52:14+00:00 | eurostat:jsonstat |
| World trade volume (CPB World Trade Monitor) | target | 2026-07-01 | 2026-10-06T22:52:17+00:00 | cpb:world-trade-monitor |
| Manufacturing production, United States | target | 2026-08-01 | 2026-10-06T22:52:21+00:00 | fred:IPMAN |
| Goods imports, United States (BOP basis) | target | 2026-08-01 | 2026-10-06T22:52:21+00:00 | fred:BOPGIMP |
| Extra-EU export volume, sa (Eurozone proxy) | target | 2026-06-01 | 2026-10-06T22:52:21+00:00 | eurostat:jsonstat |
| Merchandise exports, Saudi Arabia (IMF IMTS) | target | 2026-06-01 | 2026-10-06T22:52:22+00:00 | sdmx:imf |

## Data warnings

- de_ais_stationary: optional, no data cached yet (skipped)

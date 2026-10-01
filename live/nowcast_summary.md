# Freight nowcast — as of 2026-10-01

Live data, fetched 2026-10-01T11:05:28+00:00.

**Composite real-economy momentum: +0.15 z** in 2026-09 (provisional: month-to-date or incomplete coverage), falling over 3 months → **Slowdown** (conviction: low).

⚑ Turning point: **confirmed trough** at 2026-01 (flagged 2026-06).

## By geography

| Geography | Month | z | 3m change | Phase | Turning point | Conviction | Coverage |
|---|---|---|---|---|---|---|---|
| Germany (DE) | 2026-09* | +1.07 | +0.01 | Expansion |  | low | 100% |
| Euro area (EA) | 2026-09* | +0.09 | +0.31 | Expansion | confirmed trough 2026-01 | low | 100% |
| World sea trade (WORLD) | 2026-09* | -1.01 | -0.33 | Contraction |  | low | 100% |

\* provisional

## Indicators (latest)

| Series | Geography | Mode | Last obs | Momentum | z |
|---|---|---|---|---|---|
| Truck toll mileage index (sa) | DE | road | 2026-09-26 | +4.29 % (3m3m) | +1.26 |
| Port calls, Germany (IMF PortWatch, AIS) | DE | sea | 2026-09-25 | +1.61 % (yoy) | +0.69 |
| Port calls, euro-area ports (IMF PortWatch, AIS) | EA | sea | 2026-09-25 | -0.64 % (yoy) | +0.09 |
| Port calls, world (IMF PortWatch, AIS) | WORLD | sea | 2026-09-25 | -6.42 % (yoy) | -1.89 |
| Dry-bulk freight (Breakwave BDRY, BDI futures) | WORLD | sea | 2026-09-30 | +90.04 % (yoy) | +0.73 |

## Evidence: does each signal track what it claims to lead?

| Indicator → target | Months | Best lead | corr | β (HAC t) | R² | OOS RMSE vs AR | DM p | Hit rate | Publication lead | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| de_toll_mileage → de_manufacturing_production (mom) | 222 | 0m | +0.52 | +0.77 (+2.1) | 0.27 | 0.84 | 0.117 | 82% | 29 days | **partial** |
| de_port_calls → de_exports (yoy) | 78 | 0m | +0.54 | +0.88 (+3.1) | 0.29 | 0.97 | 0.081 | 69% | 28 days | **evidenced** |
| ea_port_calls → ea_manufacturing_production (yoy) | 79 | 0m | +0.72 | +1.76 (+4.0) | 0.52 | 1.44 | 0.989 | 60% | 35 days | **partial** |
| world_port_calls → world_trade_volume (yoy) | 78 | 0m | +0.57 | +1.34 (+2.5) | 0.32 | 1.19 | 0.981 | 52% | 45 days | **partial** |
| dry_bulk_freight → world_trade_volume (yoy) | 88 | 0m | +0.43 | +0.03 (+1.8) | 0.19 | 1.01 | 0.760 | 58% | 54 days | **not evidenced** |
| world_dry_bulk_calls → world_trade_volume (yoy) | 0 | – | – | – (–) | – | – | – | – | – | **not run** |

- de_toll_mileage → de_manufacturing_production: significant in sample but no reliable out-of-sample gain
- ea_port_calls → ea_manufacturing_production: significant in sample but no reliable out-of-sample gain
- world_port_calls → world_trade_volume: significant in sample but no reliable out-of-sample gain
- world_dry_bulk_calls → world_trade_volume: missing data for world_dry_bulk_calls

*Evidenced* = significant in-sample link with the expected sign **and** a better pseudo real-time nowcast than the target's own lag (RMSE ratio < 1, Diebold-Mariano p < 0.10).

## Recent composite turning points

| Month | Kind | Status | z | Flagged |
|---|---|---|---|---|
| 2024-04 | peak | confirmed | +0.35 | 2024-09 |
| 2026-01 | trough | confirmed | -0.97 | 2026-06 |

## Tier 2 cycle / sector tilt

Phase **Slowdown**, conviction low; cyclicals minus defensives -0.43.

| Sector | Tilt |
|---|---|
| healthcare | +0.33 |
| energy | +0.17 |
| consumer staples | +0.17 |
| utilities | +0.17 |
| technology | +0.00 |
| industrials | -0.17 |
| materials | -0.17 |
| consumer discretionary | -0.17 |
| financials | -0.17 |
| transport logistics | -0.33 |

## Data

| Series | Role | Last observation | Fetched | Origin |
|---|---|---|---|---|
| Truck toll mileage index (sa) | indicator | 2026-09-26 | 2026-10-01T11:03:35+00:00 | destatis:daily-toll-xlsx |
| Port calls, Germany (IMF PortWatch, AIS) | indicator | 2026-09-25 | 2026-10-01T11:03:41+00:00 | imf:portwatch |
| Port calls, euro-area ports (IMF PortWatch, AIS) | indicator | 2026-09-25 | 2026-10-01T11:03:42+00:00 | imf:portwatch |
| Port calls, world (IMF PortWatch, AIS) | indicator | 2026-09-25 | 2026-10-01T11:03:43+00:00 | imf:portwatch |
| Dry-bulk freight (Breakwave BDRY, BDI futures) | indicator | 2026-09-30 | 2026-10-01T11:03:43+00:00 | yahoo:BDRY |
| Manufacturing production, Germany (sca) | target | 2026-07-01 | 2026-10-01T11:05:25+00:00 | sdmx:eurostat |
| Manufacturing production, euro area (sca) | target | 2026-07-01 | 2026-10-01T11:05:25+00:00 | sdmx:eurostat |
| Exports, Germany (foreign trade statistics) | target | 2026-06-01 | 2026-10-01T11:05:26+00:00 | eurostat:jsonstat |
| World trade volume (CPB World Trade Monitor) | target | 2026-06-01 | 2026-10-01T11:05:27+00:00 | eurostat:jsonstat |

## Data warnings

- world_dry_bulk_calls: optional, no data cached yet (skipped)
- de_ais_stationary: optional, no data cached yet (skipped)

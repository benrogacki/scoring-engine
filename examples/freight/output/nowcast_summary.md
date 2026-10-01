# Freight nowcast — as of 2026-09-30

**Synthetic demo data — not real statistics.**

**Composite real-economy momentum: -0.30 z** in 2026-07, falling over 3 months → **Contraction** (conviction: low).

## By geography

| Geography | Month | z | 3m change | Phase | Turning point | Conviction | Coverage |
|---|---|---|---|---|---|---|---|
| Germany (DE) | 2026-09* | -1.22 | -1.05 | Contraction | provisional peak 2026-05 | medium | 67% |
| Euro area (EA) | 2026-07 | +0.47 | +0.49 | Expansion | provisional trough 2026-03 | low | 100% |
| World sea trade (WORLD) | 2026-07 | -0.90 | -0.69 | Contraction |  | low | 100% |

\* provisional

## Indicators (latest)

| Series | Geography | Mode | Last obs | Momentum | z |
|---|---|---|---|---|---|
| Truck toll mileage index (sa) | DE | road | 2026-09-30 | -9.81 % (3m3m) | -1.22 |
| Port calls, Germany (IMF PortWatch, AIS) | DE | sea | 2026-08-01 | -0.15 % (yoy) | -0.38 |
| Port calls, euro-area ports (IMF PortWatch, AIS) | EA | sea | 2026-08-01 | +2.02 % (yoy) | +0.47 |
| Port calls, world (IMF PortWatch, AIS) | WORLD | sea | 2026-08-01 | -2.11 % (yoy) | -1.21 |
| Baltic Dry Index | WORLD | sea | 2026-09-30 | -9.58 % (yoy) | -0.38 |

## Evidence: does each signal track what it claims to lead?

| Indicator → target | Months | Best lead | corr | β (HAC t) | R² | OOS RMSE vs AR | DM p | Hit rate | Publication lead | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| de_toll_mileage → de_manufacturing_production (mom) | 174 | 0m | +0.77 | +1.01 (+15.4) | 0.60 | 0.67 | 0.055 | 69% | 29 days | **evidenced** |
| de_port_calls → de_exports (yoy) | 163 | 0m | +0.77 | +0.90 (+9.2) | 0.59 | 0.97 | 0.170 | 61% | 28 days | **partial** |
| ea_port_calls → ea_manufacturing_production (yoy) | 163 | 1m | +0.70 | +0.65 (+9.3) | 0.49 | 1.00 | 0.518 | 65% | 35 days | **partial** |
| world_port_calls → world_trade_volume (yoy) | 163 | 0m | +0.85 | +0.83 (+11.6) | 0.72 | 0.96 | 0.187 | 56% | 45 days | **partial** |
| baltic_dry → world_trade_volume (yoy) | 163 | 0m | +0.09 | +0.01 (+0.8) | 0.01 | 1.00 | 0.637 | 50% | 54 days | **not evidenced** |

- de_port_calls → de_exports: significant in sample but no reliable out-of-sample gain
- ea_port_calls → ea_manufacturing_production: significant in sample but no reliable out-of-sample gain
- world_port_calls → world_trade_volume: significant in sample but no reliable out-of-sample gain

*Evidenced* = significant in-sample link with the expected sign **and** a better pseudo real-time nowcast than the target's own lag (RMSE ratio < 1, Diebold-Mariano p < 0.10).

## Recent composite turning points

| Month | Kind | Status | z | Flagged |
|---|---|---|---|---|
| 2018-08 | trough | confirmed | -0.09 | 2019-01 |
| 2019-08 | peak | confirmed | +1.85 | 2020-01 |
| 2021-09 | trough | confirmed | -1.65 | 2022-02 |
| 2023-04 | peak | confirmed | +0.80 | 2023-09 |
| 2024-02 | trough | confirmed | -1.64 | 2024-07 |
| 2025-06 | peak | confirmed | +1.04 | 2025-11 |

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
| Port calls, euro-area ports (IMF PortWatch, AIS) | indicator | 2026-08-01 | – | portwatch |
| Port calls, world (IMF PortWatch, AIS) | indicator | 2026-08-01 | – | portwatch |
| Baltic Dry Index | indicator | 2026-09-30 | – | csv |
| Manufacturing production, Germany (sca) | target | 2026-07-01 | – | sdmx |
| Manufacturing production, euro area (sca) | target | 2026-07-01 | – | sdmx |
| Exports, Germany (foreign trade statistics) | target | 2026-07-01 | – | genesis |
| World trade volume (CPB World Trade Monitor) | target | 2026-07-01 | – | csv |

## Data warnings

- SYNTHETIC DEMO DATA: these outputs are not real statistics
- de_ais_stationary: optional, no data cached yet (skipped)

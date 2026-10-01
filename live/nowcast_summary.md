# Freight nowcast — as of 2026-10-01

Live data, fetched 2026-10-01T10:13:18+00:00.

**Composite real-economy momentum: -0.11 z** in 2026-09 (provisional: month-to-date or incomplete coverage), falling over 3 months → **Contraction** (conviction: low).

⚑ Turning point: **confirmed trough** at 2026-01 (flagged 2026-06).

## By geography

| Geography | Month | z | 3m change | Phase | Turning point | Conviction | Coverage |
|---|---|---|---|---|---|---|---|
| Germany (DE) | 2026-09* | +1.07 | +0.01 | Expansion |  | low | 100% |
| Euro area (EA) | 2026-09* | +0.09 | +0.31 | Expansion | confirmed trough 2026-01 | low | 100% |
| World sea trade (WORLD) | 2026-09* | -1.89 | -0.48 | Contraction |  | low | 100% |

\* provisional

## Indicators (latest)

| Series | Geography | Mode | Last obs | Momentum | z |
|---|---|---|---|---|---|
| Truck toll mileage index (sa) | DE | road | 2026-09-26 | +4.29 % (3m3m) | +1.26 |
| Port calls, Germany (IMF PortWatch, AIS) | DE | sea | 2026-09-25 | +1.61 % (yoy) | +0.69 |
| Port calls, euro-area ports (IMF PortWatch, AIS) | EA | sea | 2026-09-25 | -0.64 % (yoy) | +0.09 |
| Port calls, world (IMF PortWatch, AIS) | WORLD | sea | 2026-09-25 | -6.42 % (yoy) | -1.89 |

## Evidence: does each signal track what it claims to lead?

| Indicator → target | Months | Best lead | corr | β (HAC t) | R² | OOS RMSE vs AR | DM p | Hit rate | Publication lead | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| de_toll_mileage → de_manufacturing_production (mom) | 222 | 0m | +0.52 | +0.77 (+2.1) | 0.27 | 0.84 | 0.117 | 82% | 29 days | **partial** |
| de_port_calls → de_exports (yoy) | 0 | – | – | – (–) | – | – | – | – | – | **not run** |
| ea_port_calls → ea_manufacturing_production (yoy) | 79 | 0m | +0.72 | +1.76 (+4.0) | 0.52 | 1.44 | 0.989 | 60% | 35 days | **partial** |
| world_port_calls → world_trade_volume (yoy) | 0 | – | – | – (–) | – | – | – | – | – | **not run** |
| baltic_dry → world_trade_volume (yoy) | 0 | – | – | – (–) | – | – | – | – | – | **not run** |

- de_toll_mileage → de_manufacturing_production: significant in sample but no reliable out-of-sample gain
- de_port_calls → de_exports: missing data for de_exports
- ea_port_calls → ea_manufacturing_production: significant in sample but no reliable out-of-sample gain
- world_port_calls → world_trade_volume: missing data for world_trade_volume
- baltic_dry → world_trade_volume: missing data for baltic_dry, world_trade_volume

*Evidenced* = significant in-sample link with the expected sign **and** a better pseudo real-time nowcast than the target's own lag (RMSE ratio < 1, Diebold-Mariano p < 0.10).

## Recent composite turning points

| Month | Kind | Status | z | Flagged |
|---|---|---|---|---|
| 2024-04 | peak | confirmed | +0.36 | 2024-09 |
| 2026-01 | trough | confirmed | -1.14 | 2026-06 |

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
| Truck toll mileage index (sa) | indicator | 2026-09-26 | 2026-10-01T10:13:03+00:00 | destatis:daily-toll-xlsx |
| Port calls, Germany (IMF PortWatch, AIS) | indicator | 2026-09-25 | 2026-10-01T10:13:11+00:00 | imf:portwatch |
| Port calls, euro-area ports (IMF PortWatch, AIS) | indicator | 2026-09-25 | 2026-10-01T10:13:12+00:00 | imf:portwatch |
| Port calls, world (IMF PortWatch, AIS) | indicator | 2026-09-25 | 2026-10-01T10:13:12+00:00 | imf:portwatch |
| Manufacturing production, Germany (sca) | target | 2026-07-01 | 2026-10-01T10:13:13+00:00 | sdmx:eurostat |
| Manufacturing production, euro area (sca) | target | 2026-07-01 | 2026-10-01T10:13:13+00:00 | sdmx:eurostat |

## Data warnings

- baltic_dry: optional, no data cached yet (skipped)
- de_ais_stationary: optional, no data cached yet (skipped)
- de_exports: optional, no data cached yet (skipped)
- world_trade_volume: optional, no data cached yet (skipped)

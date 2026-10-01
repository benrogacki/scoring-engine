# Freight nowcaster

`freight_nowcast` measures real-economy momentum from published freight series. It does not
run its own AIS pipeline. It reads series that publishers have already aggregated, turns each one
into a momentum z-score, and combines them into a composite for each geography. It then flags cycle
phases and turning points, and tests each signal against the official statistic it is meant to lead.

It works separately from the credit-scoring engine. It reads external macro data, not the debtor
ledger, and shares no code or data model with `scoring_engine`. Its only output to the rest of
the stack is `capstone_feed.json`:

- **Tier 1** reads the real economy next to the yield curve.
- **Tier 2** gets the cycle and sector tilt.

```
 Destatis GENESIS ── truck toll mileage (monthly, + working-daily) ─┐
 OECD AIS dashboard ─ port calls (DE / euro area / world) ──────────┤   per series:        per geography:     ┌─ capstone_feed.json (Tier 1 / Tier 2)
 Baltic Dry ───────── dry-bulk freight rates ───────────────────────┼─► momentum → z ─► weighted z ─► phase ─┼─ composite.csv, turning_points.csv
 aisstream.io ─────── vessels in port, a few ports (optional) ──────┘   (no look-ahead)    + turning points   ├─ validation.json  (evidence)
 Eurostat / GENESIS / CPB ── production & trade (validation targets) ─────────────────────────────────────►└─ nowcast_summary.md, dashboard.html
```

## Two modes: live and sandbox

| | **Live** | **Sandbox (synthetic)** |
|---|---|---|
| Command | `freight-nowcast live` (= `fetch` + `run`) | `freight-nowcast demo` |
| Data | fetched from Destatis, IMF PortWatch, Eurostat (plus any CSV exports you add) | generated from one latent cycle with known links |
| Cache | `data/freight/live/` with `_manifest.json` (what was fetched, when, from where) | `out/freight-demo-cache/`, marked `_SYNTHETIC_DEMO_DATA` |
| Outputs | `out/freight/live/`; the scheduled job publishes them to the `freight-live` branch; a snapshot is in `examples/freight/live/` | `examples/freight/output/` |
| Labelled | "Live data · fetched …" plus a per-series data table | "Synthetic demo data — not real statistics" everywhere |

The two caches cannot be mixed. `fetch` refuses a cache that holds demo data, and `demo` refuses
one that has a live manifest. The sandbox stays useful wherever there's no network: in tests, in
this repository's examples, and as a check that the method finds a link that is known to exist.

### Running live

```bash
python -m freight_nowcast live --out out/freight/live         # fetch everything, then run
python -m freight_nowcast probe                                # check each source, show GENESIS codes
python -m freight_nowcast fetch --only de_toll_mileage         # refresh one series
python -m freight_nowcast run --as-of 2026-09-30               # re-run from the cache, offline
```

If a publisher is down, the last good copy of that series stays in the cache. The manifest and the
outputs record the failure as a warning. A required series that fails makes `fetch` (and
`live --strict`) exit with code 1.

**Scheduled live run.** [`.github/workflows/freight-nowcast.yml`](../.github/workflows/freight-nowcast.yml)
runs the live nowcast on weekdays at 09:41 UTC, on demand (Actions → *Freight nowcast* → *Run
workflow*), and on any push that changes the nowcaster. Each run:

1. runs the unit tests and probes every source
2. writes the summary to the job page and uploads the outputs and cache as an artifact
3. on scheduled and manual runs, commits the outputs to the **`freight-live`** branch

The Actions cache carries the data between runs. To use your own GENESIS account instead of the
rate-limited guest login, add a repository secret `DESTATIS_TOKEN`.

The sandbox:

```bash
python -m freight_nowcast demo --as-of 2026-09-30 --out out/freight-demo
```

Optional series with no data (CSV exports you haven't added) are skipped with a warning, and the
composite is reweighted over whatever is available.

## Data sources

| Series | Source | How it gets in | Auto? |
|---|---|---|---|
| Truck toll mileage index, Germany (monthly, seasonally adjusted) | Destatis GENESIS table **42191-0001** | `genesis`: REST `genesisWS/rest/2020` `data/tablefile`, flat-file CSV; needs `DESTATIS_TOKEN` (the guest login gets HTTP 401). **Without a token** it falls back to the monthly mean of the Destatis daily index, which is the same index from the same publisher | ✔ |
| Truck toll mileage index, working-daily | Destatis experimental statistics (xlsx) | `destatis_daily`: follows the xlsx link on the table page and reads the seasonally adjusted column; spliced onto the monthly index at the ragged edge | ✔ |
| Port calls: Germany, euro area (EA20), world | IMF PortWatch (UN Global Platform AIS) | `portwatch`: public ArcGIS API, summed by day on the server, no key | ✔ |
| Port calls (alternative) | OECD AIS vessel-tracking dashboard | CSV export; `oecd_*` entries are in the catalog with `"enabled": false`, so you can switch them on in place of PortWatch | manual |
| Baltic Dry Index | Baltic Exchange (licensed) or a market-data export | CSV (`Date`, `Close`/`Price`) | manual |
| Vessels in port, a handful of ports | aisstream.io free WebSocket | `ais-listen` → CSV | cron |
| Manufacturing production, DE and euro area | Eurostat `sts_inpr_m` | `sdmx` | ✔ |
| Exports, Germany | GENESIS 51000-0002, or the Eurostat `ext_st_eu27_2020sitc` export volume index (`IVOL_SCA`) as fallback | `genesis`, falling back to `eurostat_jsonstat` (dimensions passed by name) | ✔ |
| World trade volume | CPB World Trade Monitor | CSV | manual |

Neither the Baltic Dry nor CPB world trade has a free, stable API. Drop an export at the path given
in the catalog and it's picked up on the next run. Until then, their validation pairs show as not
run.

**Codes.** I set table codes, filters and keys from the publishers' documentation; the ones I
haven't confirmed against a live response are marked `_verify` in
[`config/freight_nowcast.json`](../config/freight_nowcast.json). `probe` prints what each source
returns. For GENESIS tables it also prints the table's variables and attribute codes. A wrong code
makes the fetch fail with a message saying what to pin; it never picks a series silently.

### GENESIS credentials

The GENESIS API only accepts credentials in POST **headers**. Set `DESTATIS_TOKEN` (the token goes
in `username`, with an empty `password`), or set `DESTATIS_USERNAME` and `DESTATIS_PASSWORD`.
Without either, the client uses the guest login. To override the endpoint, set
`DESTATIS_GENESIS_URL`.

### Live AIS layer (optional)

```bash
pip install -e .[ais]
export AISSTREAM_API_KEY=...
freight-nowcast ais-listen --minutes 10       # appends to data/freight/ais_port_counts.csv
```

`ais-listen` samples the port bounding boxes in the catalog's `ais.ports`, up to 10 ports
(Hamburg, Bremerhaven, Rotterdam and Antwerp by default). For each port it counts the distinct
vessels and the stationary ones (moored, at anchor, or SOG ≤ 0.5 kn). Schedule it at the same UTC
time every day so the counts are comparable.

These counts are snapshots, not port calls. The free feed's terrestrial coverage is uneven, so the
series has a small weight and only enters the composite once it has enough history for a z-score.

## Method

**Monthly alignment.** Daily and weekly series are averaged to calendar months. The latest month of
a daily series is a month-to-date reading. It is kept, but its coverage is recorded so it shows as
**provisional**.

**Ragged edge.** A spec with `"extends": "de_toll_mileage"` contributes only the months after the
parent's last release. Those months are rebased onto the parent's level using the median ratio over
the last 12 overlapping months. The working-daily toll index therefore gives a provisional reading
for the current month about five weeks before production data covers it.

**Momentum.** Each series is transformed into a growth rate:

- `3m3m`: the 3-month average versus the prior 3 months, annualised. This is the default for
  seasonally adjusted indices.
- `yoy`: year-on-year growth, for unadjusted or noisy series such as port calls and the Baltic Dry.
- `mom`: month-on-month growth.
- `diff`: the month-on-month difference.
- `level`: no transform.

**Z-scores.** Each momentum series is standardised against its trailing 60 months, with a minimum
of 24, and clipped at ±4. Only past data enters each z-score, so historical readings show what a
real-time reader would have seen, apart from data revisions.

**Composites.** A geography's composite is the weighted mean of the z-scores available that month.
It needs at least 50% of the geography's weight to be present. The overall composite weights the
geographies (DE 0.4, euro area 0.3, world 0.3).

**Cycle phase.** The phase combines the level against zero with the direction over 3 months:

| | rising | falling |
|---|---|---|
| **z ≥ 0** | Expansion | Slowdown |
| **z < 0** | Recovery | Contraction |

**Turning points.**

- **Confirmed** (Bry-Boschan style): a local extreme within ±5 months, with peaks and troughs
  alternating, phases of at least 5 months, cycles of at least 15 months and an amplitude of at
  least 0.5 z. A confirmed point needs 5 months of data after it.
- **Provisional:** the composite has moved at least 0.5 z off its 12-month extreme and kept going
  for 2 months. This is the flag you can act on at the ragged edge.
- **Zero-crossings** are listed as events.

## Validation: the signal has to be backed by evidence

Each `indicator → target` pair in `validation` gets four checks:

1. **Lead/lag profile.** The correlation of the indicator `L` months earlier with the target, for
   `L` from −3 to +3 (or up to 6).
2. **In-sample fit.** `target_t = a + b·indicator_t`, with **Newey-West (HAC)** errors. Overlapping
   growth rates are autocorrelated, so plain OLS errors would overstate the evidence.
3. **Pseudo real-time nowcast.** Expanding-window forecasts of `target_t` from `target_{t−1}` plus
   `indicator_t` are compared with `target_{t−1}` alone. The comparison reports the RMSE ratio, a
   one-sided **Diebold-Mariano** test, and the hit rate on the direction of change.
4. **Timing.** The publication lead in days (target lag minus indicator lag). For example, the toll
   index is out about 9 days after the month ends, against about 38 for production.

The verdicts:

- **evidenced**: the in-sample link is significant (p < 0.05) with the expected sign, **and** the
  out-of-sample RMSE ratio is below 1 with DM p < 0.10.
- **partial**: only one of those two conditions holds.
- **not evidenced**: neither holds.

Verdicts feed into conviction. A reading that rests mostly (under 50% of its weight) on indicators
that are not evidenced is marked down one level. So is a provisional reading.

## Capstone feed (`capstone_feed.json`, schema `freight_nowcast/capstone_feed@1`)

```jsonc
{
  "tier1": {                       // real-economy read, alongside the yield curve
    "composite_z": -0.53, "change_3m": -0.38, "direction": "falling",
    "phase": "Contraction", "provisional": false, "turning_point": null,
    "evidence": {"de_toll_mileage->de_manufacturing_production": "evidenced", ...},
    "evidenced_weight_share": 0.25, "conviction": "low",
    "by_geography": {"DE": {...}, "EA": {...}, "WORLD": {...}}
  },
  "tier2": {                       // cycle / sector tilt
    "cycle_phase": "Contraction", "conviction": "low",
    "tilt": {"sectors": {"industrials": -0.33, "utilities": 0.33, ...}, "cyclical_minus_defensive": -0.66},
    "by_geography": {...}
  },
  "validation": [...], "series": {...}, "warnings": [...]
}
```

Tilts are directional and range from −1 to 1. Each one is the phase's tilt from `DEFAULT_TILTS` in
`feed.py` (override it with `tier2_tilts` in the catalog), multiplied by conviction: 1 for high, ⅔
for medium, ⅓ for low. The capstone decides how large the positions are.

## Outputs

| File | Contents |
|---|---|
| `composite.csv` | Monthly composite z, phase, coverage and provisional flag, plus each geography's z and phase |
| `indicator_panel.csv` | For every indicator: monthly level, momentum and z |
| `turning_points.csv` | Confirmed and provisional peaks and troughs, and zero-crossings, for the composite and each geography |
| `validation.json` | Full evidence results for each pair |
| `capstone_feed.json` | The Tier 1 / Tier 2 contract above |
| `nowcast_summary.md` | A one-page read |
| `dashboard.html` | Interactive charts (composite with contraction shading and turning points, a small chart per geography), evidence table and tilt bars |

## Code

- `series.py`: monthly alignment, transforms, rolling z-scores
- `stats.py`: OLS with Newey-West errors, Diebold-Mariano (standard library only)
- `sources/`: `genesis.py` (Destatis REST + ffcsv parser + `inspect`), `destatis_daily.py` + `xlsx.py`
  (daily toll index), `portwatch.py` (IMF PortWatch), `sdmx.py` (OECD, Eurostat, ECB), `ais.py` (aisstream.io
  port counter), and the CSV reader and cache in `__init__.py`
- `live.py`: live fetch with manifest, `probe`
- `composite.py`, `turning.py`, `validation.py`: the method
- `engine.py`: the pipeline, including the daily→monthly splice
- `feed.py`: the capstone contract
- `report.py`, `dashboard.py`: outputs
- `demo.py`: synthetic series for offline trials and tests (never mixed with real data, and
  flagged in every output)

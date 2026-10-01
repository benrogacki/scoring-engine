"""Synthetic freight data for trying the pipeline offline and for tests.

Not real data. Every series is driven by one latent business cycle with known
links (toll mileage and port calls move with production and trade; Baltic Dry is
noisy), so the validation should come out *evidenced* for the clean pairs and
weaker for the noisy one. Includes a pandemic-style collapse so turning points
have something to find, and a month-to-date daily toll series for the ragged edge.
"""
from __future__ import annotations

import math
import random
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, List, Tuple

from .series import Series, add_months
from .sources import write_cache

MARKER = "_SYNTHETIC_DEMO_DATA"


def _cycle(n: int, rng: random.Random) -> List[float]:
    """AR(2) with complex roots: a ~4-year cycle, plus a 2020-style shock."""
    c = [0.0, 0.0]
    for _ in range(n - 2):
        c.append(1.82 * c[-1] - 0.87 * c[-2] + rng.gauss(0, 0.12))
    return c


def _level(growth: List[float], start: float = 100.0) -> List[float]:
    out, lvl = [], start
    for g in growth:
        lvl *= 1 + g / 100.0
        out.append(lvl)
    return out


def generate(as_of: date, seed: int = 11, start: Tuple[int, int] = (2012, 1)) -> Dict[str, Series]:
    rng = random.Random(seed)
    last_full = add_months((as_of.year, as_of.month), -1)
    months = []
    m = start
    while m <= last_full:
        months.append(m)
        m = add_months(m, 1)
    n = len(months)
    c = _cycle(n, rng)
    for i, mo in enumerate(months):  # pandemic-style collapse and rebound
        if mo == (2020, 4):
            c[i] -= 9.0
        elif mo == (2020, 5):
            c[i] -= 3.0
        elif mo == (2020, 6):
            c[i] += 6.0
        elif mo == (2020, 7):
            c[i] += 4.0

    def mk(sid, drift, beta, noise, lag=0, start_level=100.0):
        g = [drift + beta * (c[i - lag] if i >= lag else 0.0) + rng.gauss(0, noise) for i in range(n)]
        return Series(sid, [(date(y, mo, 1), v) for (y, mo), v in zip(months, _level(g, start_level))], "M", "synthetic")

    out = {
        "de_toll_mileage": mk("de_toll_mileage", 0.03, 0.9, 0.35),
        "de_manufacturing_production": mk("de_manufacturing_production", 0.0, 1.0, 0.9),
        "de_port_calls": mk("de_port_calls", 0.02, 0.8, 1.2),
        "de_exports": mk("de_exports", 0.1, 0.9, 1.1),
        "ea_port_calls": mk("ea_port_calls", 0.05, 0.7, 1.0),
        "ea_manufacturing_production": mk("ea_manufacturing_production", 0.05, 0.8, 0.7),
        "world_port_calls": mk("world_port_calls", 0.15, 0.6, 0.9),
        "world_trade_volume": mk("world_trade_volume", 0.2, 0.7, 0.8),
    }
    # the US-style partial last month is dropped from the monthly series: those
    # are "not yet published"; the daily toll series carries the ragged edge
    toll = dict(out["de_toll_mileage"].observations)
    daily = []
    d = date(2023, 1, 2)
    prev_level = None
    while d <= as_of:
        if d.weekday() < 5:
            key = date(d.year, d.month, 1)
            base = toll.get(key)
            if base is None:  # months after the last monthly release: carry the cycle on
                base = (prev_level or 100.0) * (1 + (0.03 + 0.9 * c[-1] * 0.8) / 100.0)
                toll[key] = base
            prev_level = base
            daily.append((d, base * 1.02 * (1 + rng.gauss(0, 0.015))))
        d += timedelta(days=1)
    # the monthly release for the latest full month is "not out yet" (published ~day 9)
    last = date(last_full[0], last_full[1], 1)
    if as_of.day < 10:
        out["de_toll_mileage"] = Series("de_toll_mileage",
                                        [o for o in out["de_toll_mileage"].observations if o[0] < last], "M", "synthetic")
    out["de_toll_mileage_daily"] = Series("de_toll_mileage_daily", daily, "D", "synthetic")
    # industrial production is published ~5 weeks after the month: drop the last month
    for sid in ("de_manufacturing_production", "ea_manufacturing_production", "de_exports", "world_trade_volume"):
        s = out[sid]
        out[sid] = Series(sid, s.observations[:-1], "M", "synthetic")
    # Baltic Dry: working-daily, volatile, loosely tied to the world cycle
    bdi, lvl = [], 1500.0
    d = date(2012, 1, 2)
    month_idx = {mo: i for i, mo in enumerate(months)}
    while d <= as_of:
        if d.weekday() < 5:
            i = month_idx.get((d.year, d.month), n - 1)
            lvl *= math.exp(0.004 * c[i] + rng.gauss(0, 0.025))
            lvl = min(max(lvl, 300.0), 6000.0)
            bdi.append((d, round(lvl)))
        d += timedelta(days=1)
    out["baltic_dry"] = Series("baltic_dry", bdi, "D", "synthetic")
    return out


def write_demo_cache(cache_dir: Path, as_of: date, seed: int = 11) -> Dict[str, Series]:
    series = generate(as_of, seed)
    cache_dir = Path(cache_dir)
    if (cache_dir / "_manifest.json").exists():
        raise ValueError(f"{cache_dir} holds live data; write the demo to a separate cache")
    cache_dir.mkdir(parents=True, exist_ok=True)
    for s in series.values():
        write_cache(cache_dir, s)
    (cache_dir / MARKER).write_text("Synthetic demo data generated by `freight-nowcast demo`. Not real statistics.\n")
    return series

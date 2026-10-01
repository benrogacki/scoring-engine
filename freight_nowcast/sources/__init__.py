"""Where the freight series come from, and the local cache they land in.

Every connector returns a :class:`~freight_nowcast.series.Series`. ``fetch`` saves
each one as ``<cache>/<series id>.csv`` (``date,value``) so ``run`` works offline,
is reproducible, and can be audited against the source.

Sources:
- ``genesis``  Destatis GENESIS-Online REST API (truck toll mileage, production)
- ``sdmx``     any SDMX REST endpoint returning SDMX-CSV (OECD, Eurostat, ECB, IMF)
- ``csv``      a file you downloaded (OECD AIS dashboard export, Baltic Dry,
               the aisstream.io port counts written by ``ais-listen``)
"""
from __future__ import annotations

import csv
import io
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple

from ..series import Series


class SourceError(RuntimeError):
    pass


_MONTHS = {m: i + 1 for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}


def parse_period(text: str, date_format: Optional[str] = None) -> Optional[date]:
    """Parse the period formats statistical sources use into a date.

    Monthly/quarterly periods map to the first day of the period, weeks to
    their Monday. Handles ``2026-09-14``, ``2026-09``, ``2026-M09``, ``2026M09``,
    ``2026-Q3``, ``2026-W38``, ``14.09.2026``, ``14/09/2026``, ``Sep 2026``,
    ``Sep 14, 2026`` and a pinned ``date_format`` for ambiguous exports.
    """
    s = (text or "").strip().strip('"')
    if not s:
        return None
    if date_format:
        return datetime.strptime(s, date_format).date()
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})(?:[T ].*)?", s)
    if m:
        return date(int(m[1]), int(m[2]), int(m[3]))
    m = re.fullmatch(r"(\d{4})-?M?(\d{2})", s)
    if m and 1 <= int(m[2]) <= 12:
        return date(int(m[1]), int(m[2]), 1)
    m = re.fullmatch(r"(\d{4})-?Q([1-4])", s)
    if m:
        return date(int(m[1]), 3 * int(m[2]) - 2, 1)
    m = re.fullmatch(r"(\d{4})-?W(\d{2})", s)
    if m:
        return date.fromisocalendar(int(m[1]), int(m[2]), 1)
    m = re.fullmatch(r"(\d{1,2})[./](\d{1,2})[./](\d{4})", s)
    if m:  # European day-first; pin date_format for US-style exports
        return date(int(m[3]), int(m[2]), int(m[1]))
    m = re.fullmatch(r"([A-Za-z]{3})[a-z]*\.? (\d{1,2}), (\d{4})", s)
    if m and m[1].lower() in _MONTHS:
        return date(int(m[3]), _MONTHS[m[1].lower()], int(m[2]))
    m = re.fullmatch(r"([A-Za-z]{3})[a-z]*\.?[ -](\d{4})", s)
    if m and m[1].lower() in _MONTHS:
        return date(int(m[2]), _MONTHS[m[1].lower()], 1)
    raise SourceError(f"unrecognised period {text!r}")


def parse_number(text: Any, decimal: str = ".") -> Optional[float]:
    """Parse a published number. Placeholders (``.``, ``-``, ``...``, ``x``, ``NaN``) become None."""
    if text is None:
        return None
    if isinstance(text, (int, float)):
        return float(text)
    s = str(text).strip().strip('"').replace(" ", "").replace(" ", "")
    if s in {"", ".", "-", "...", "x", "/", "NaN", "nan", "NA", "n/a", "…"}:
        return None
    s = re.sub(r"[%$€£]", "", s)
    if decimal == ",":
        s = s.replace(".", "").replace(",", ".")
    else:
        s = s.replace(",", "")
    # GENESIS marks values with trailing quality flags, e.g. "103.4p" (provisional)
    s = re.sub(r"[a-zA-Z]+$", "", s)
    try:
        return float(s)
    except ValueError:
        raise SourceError(f"unparseable number {text!r}")


def sniff_dialect(text: str) -> str:
    head = text[:2048]
    return ";" if head.count(";") > head.count(",") else ","


def read_csv_series(series_id: str, text: str, frequency: str = "M", date_col: Optional[str] = None,
                    value_col: Optional[str] = None, decimal: Optional[str] = None,
                    date_format: Optional[str] = None, filters: Optional[Mapping[str, str]] = None,
                    source: str = "csv") -> Series:
    """Read one series from a CSV export, guessing the date/value columns if not given."""
    delim = sniff_dialect(text)
    if decimal is None:
        decimal = "," if delim == ";" else "."
    rows = list(csv.DictReader(io.StringIO(text.lstrip("﻿")), delimiter=delim))
    if not rows:
        raise SourceError(f"{series_id}: CSV has no rows")
    cols = list(rows[0].keys())
    lower = {c.lower().strip(): c for c in cols}

    def pick(wanted: Optional[str], candidates: List[str], what: str) -> str:
        if wanted:
            if wanted in cols:
                return wanted
            if wanted.lower() in lower:
                return lower[wanted.lower()]
            raise SourceError(f"{series_id}: column {wanted!r} not in {cols}")
        for c in candidates:
            if c in lower:
                return lower[c]
        raise SourceError(f"{series_id}: cannot tell which column is the {what}; set it in the catalog ({cols})")

    dcol = pick(date_col, ["date", "time_period", "period", "time", "datum", "day", "month", "week"], "date")
    vcol = pick(value_col, ["value", "obs_value", "close", "price", "index", "wert", "count", "port_calls"], "value")
    obs: List[Tuple[date, float]] = []
    for r in rows:
        if filters and any((r.get(k) or "").strip() != v for k, v in filters.items()):
            continue
        d = parse_period(r.get(dcol, ""), date_format)
        v = parse_number(r.get(vcol), decimal)
        if d is not None and v is not None:
            obs.append((d, v))
    if not obs:
        raise SourceError(f"{series_id}: no observations after filtering {dict(filters or {})}")
    return Series(series_id, obs, frequency, source)


def cache_path(cache_dir: Path, series_id: str) -> Path:
    return Path(cache_dir) / f"{series_id}.csv"


def write_cache(cache_dir: Path, s: Series) -> Path:
    path = cache_path(cache_dir, s.id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["date", "value"])
        for d, v in s.observations:
            w.writerow([d.isoformat(), repr(v)])
    return path


def read_cache(cache_dir: Path, series_id: str, frequency: str, source: str = "cache") -> Series:
    path = cache_path(cache_dir, series_id)
    if not path.exists():
        raise SourceError(f"{series_id}: no cached data at {path}; run `freight-nowcast fetch` first")
    return read_csv_series(series_id, path.read_text(encoding="utf-8"), frequency,
                           "date", "value", ".", "%Y-%m-%d", source=source)


def fetch_series(spec: Mapping[str, Any], base_dir: Path = Path(".")) -> Series:
    """Fetch one catalog entry from its source."""
    kind = spec.get("source")
    sid, freq = spec["id"], spec.get("frequency", "M")
    params: Dict[str, Any] = dict(spec.get("params", {}))
    if kind == "genesis":
        from . import genesis
        return genesis.fetch(sid, freq, **params)
    if kind == "sdmx":
        from . import sdmx
        return sdmx.fetch(sid, freq, **params)
    if kind == "csv":
        path = Path(params.pop("path"))
        if not path.is_absolute():
            path = base_dir / path
        if not path.exists():
            raise SourceError(f"{sid}: file {path} not found ({spec.get('how_to_get', 'see docs')})")
        return read_csv_series(sid, path.read_text(encoding="utf-8-sig"), freq, source=f"csv:{path.name}", **params)
    raise SourceError(f"{sid}: unknown source {kind!r}")

"""SDMX REST sources (OECD Data Explorer, Eurostat, ECB, IMF) via SDMX-CSV.

SDMX-CSV always carries ``TIME_PERIOD`` and ``OBS_VALUE`` plus one column per
dimension, so one parser covers every agency. Give either a full ``url`` or the
agency shortcut with ``flow`` and ``key``:

    {"agency": "eurostat", "flow": "sts_inpr_m", "key": "M.PRD.C.SCA.I21.DE"}
    {"agency": "oecd", "flow": "OECD.SDD.STES,DSD_STES@DF_INDSERV,4.0", "key": "DEU.M.PRVM...."}

Dimensions left blank in the key come back as several series; pin them with
``filters`` (``{"geo": "DE"}``) or the fetch fails listing what came back.

For Eurostat there is also ``eurostat_jsonstat``: dimensions are passed *by name*
(``{"dims": {"geo": "DE", "unit": "I21", ...}}``), so no positional key to get
wrong, and an incomplete query fails listing every dimension and its codes.
"""
from __future__ import annotations

import csv
import io
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from typing import Callable, Dict, List, Mapping, Optional, Tuple

from ..series import Series
from . import SourceError, parse_number, parse_period

AGENCIES = {
    "oecd": ("https://sdmx.oecd.org/public/rest/data/{flow}/{key}", {"format": "csvfile"}),
    "eurostat": ("https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/data/{flow}/{key}",
                 {"format": "SDMX-CSV"}),
    "ecb": ("https://data-api.ecb.europa.eu/service/data/{flow}/{key}", {"format": "csvdata"}),
}
_NON_DIMENSIONS = {"time_period", "obs_value", "obs_status", "obs_flag", "conf_status", "unit_mult",
                   "decimals", "dataflow", "structure", "structure_id", "action", "obs_conf",
                   "last update", "last_update", "freq_label"}

Getter = Callable[[str], bytes]


def _urllib_get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.sdmx.data+csv, text/csv"})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return resp.read()
    except urllib.error.HTTPError as exc:
        raise SourceError(f"SDMX HTTP {exc.code} for {url}: {exc.read()[:200]!r}") from exc
    except urllib.error.URLError as exc:
        raise SourceError(f"SDMX source unreachable ({url}): {exc.reason}") from exc


def build_url(agency: Optional[str] = None, flow: Optional[str] = None, key: str = "all",
              url: Optional[str] = None, start: Optional[str] = None) -> str:
    if url:
        base, query = url, {}
    else:
        if agency not in AGENCIES:
            raise SourceError(f"unknown SDMX agency {agency!r}; give a full url or one of {sorted(AGENCIES)}")
        if not flow:
            raise SourceError("SDMX source needs a flow (dataflow id)")
        tmpl, query = AGENCIES[agency]
        base = tmpl.format(flow=flow, key=key or "all")
        query = dict(query)
    if start:
        query["startPeriod"] = start
    if not query:
        return base
    return base + ("&" if "?" in base else "?") + urllib.parse.urlencode(query)


def parse_sdmx_csv(text: str, filters: Optional[Mapping[str, str]] = None) -> List[Tuple[date, float]]:
    rows = list(csv.DictReader(io.StringIO(text.lstrip("﻿"))))
    if not rows:
        return []
    cols = {c.lower(): c for c in rows[0].keys()}
    if "time_period" not in cols or "obs_value" not in cols:
        raise SourceError(f"not SDMX-CSV (no TIME_PERIOD/OBS_VALUE): {list(rows[0])[:8]}")
    flt = {cols.get(k.lower(), k): v for k, v in (filters or {}).items()}
    dims = [c for lc, c in cols.items() if lc not in _NON_DIMENSIONS and c not in flt]
    by_key: Dict[Tuple[str, ...], Dict[date, float]] = {}
    for r in rows:
        if any((r.get(k) or "").split(":")[0].strip() != v for k, v in flt.items()):
            continue
        d = parse_period(r[cols["time_period"]])
        v = parse_number(r[cols["obs_value"]])
        if d is None or v is None:
            continue
        by_key.setdefault(tuple(r.get(c, "") for c in dims), {})[d] = v
    if len(by_key) > 1:
        varying = {c: sorted({k[i] for k in by_key})[:8] for i, c in enumerate(dims) if len({k[i] for k in by_key}) > 1}
        raise SourceError(f"query returned {len(by_key)} series; pin these in the key or filters: {varying}")
    return sorted(next(iter(by_key.values())).items()) if by_key else []


def fetch(series_id: str, frequency: str, agency: Optional[str] = None, flow: Optional[str] = None,
          key: str = "all", url: Optional[str] = None, start: Optional[str] = None,
          filters: Optional[Mapping[str, str]] = None, getter: Optional[Getter] = None) -> Series:
    full = build_url(agency, flow, key, url, start)
    text = (getter or _urllib_get)(full).decode("utf-8-sig", errors="replace")
    obs = parse_sdmx_csv(text, filters)
    if not obs:
        raise SourceError(f"{series_id}: no observations from {full}")
    return Series(series_id, obs, frequency, f"sdmx:{agency or 'url'}", {"url": full})


JSONSTAT_URL = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/{flow}"


def parse_jsonstat(payload: Dict, flow: str = "") -> List[Tuple[date, float]]:
    """Parse a Eurostat JSON-stat 2.0 response that must hold exactly one series."""
    if "error" in payload:
        err = payload["error"]
        err = err[0] if isinstance(err, list) and err else err
        raise SourceError(f"Eurostat {flow}: {err.get('label') if isinstance(err, dict) else err}")
    ids, sizes, dims = payload["id"], payload["size"], payload["dimension"]
    time_dim = next((d for d in ids if d.lower() in ("time", "time_period")), ids[-1])
    multi = {d: list(dims[d]["category"]["index"])[:10] for d, n in zip(ids, sizes) if n > 1 and d != time_dim}
    if multi:
        raise SourceError(f"Eurostat {flow}: pin these dimensions in dims: {multi}")
    index = dims[time_dim]["category"]["index"]
    positions = sorted(index, key=index.get) if isinstance(index, dict) else list(index)
    values = payload.get("value", {})
    out = []
    for i, period in enumerate(positions):
        v = values.get(str(i)) if isinstance(values, dict) else (values[i] if i < len(values) else None)
        if v is not None:
            out.append((parse_period(period), float(v)))
    return out


def fetch_eurostat_jsonstat(series_id: str, frequency: str, flow: str, dims: Mapping[str, str],
                            start: Optional[str] = None, getter: Optional[Getter] = None) -> Series:
    import json

    query = [("format", "JSON"), ("lang", "EN")] + [(k, v) for k, v in dims.items()]
    if start:
        query.append(("sinceTimePeriod", start))
    url = JSONSTAT_URL.format(flow=flow) + "?" + urllib.parse.urlencode(query)
    def _get(u: str) -> Dict:
        if getter:
            return json.loads(getter(u).decode("utf-8"))
        from .http import get
        return json.loads(get(u, {"Accept": "application/json"}).decode("utf-8"))

    try:
        payload = _get(url)
    except SourceError as exc:
        if "413" not in str(exc):
            raise
        # too big: ask for one period only, which is small, and report the open dimensions
        probe_url = JSONSTAT_URL.format(flow=flow) + "?" + urllib.parse.urlencode(
            [("format", "JSON"), ("lang", "EN")] + list(dims.items()) + [("lastTimePeriod", "1")])
        try:
            parse_jsonstat(_get(probe_url), flow)
        except SourceError as detail:
            raise SourceError(f"query too big; {detail}") from exc
        raise
    obs = parse_jsonstat(payload, flow)
    if not obs:
        raise SourceError(f"{series_id}: no observations from {url}")
    return Series(series_id, obs, frequency, "eurostat:jsonstat", {"url": url})

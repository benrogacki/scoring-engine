"""IMF PortWatch daily port calls (UN Global Platform AIS), via its public ArcGIS API.

No key needed. The ``Daily_Ports_Data`` layer has one row per port per day; the
connector asks the server to sum ``portcalls`` (or another numeric field) by day
for a country, a list of countries, or the world, one year per request so each
response stays under the server's record limit. The result is a daily series;
the pipeline averages it to months and marks the latest month as month-to-date.
PortWatch publishes weekly (Tuesdays) with a lag of about a week.
"""
from __future__ import annotations

import json
import urllib.parse
from datetime import date, datetime, timezone
from typing import Callable, Dict, Optional, Sequence

from ..series import Series
from . import SourceError
from .http import get

LAYER_URL = ("https://services9.arcgis.com/weJ1QsnbMYJlCHdG/ArcGIS/rest/services/"
             "Daily_Ports_Data/FeatureServer/0/query")


def _where(countries: Optional[Sequence[str]], year: int, iso_field: str, year_field: str) -> str:
    clauses = [f"{year_field}={int(year)}"]
    if countries:
        codes = ",".join("'" + c.replace("'", "") + "'" for c in countries)
        clauses.append(f"{iso_field} IN ({codes})")
    return " AND ".join(clauses)


def build_query(countries: Optional[Sequence[str]], year: int, field: str = "portcalls",
                iso_field: str = "ISO3", year_field: str = "year", layer_url: str = LAYER_URL) -> str:
    stats = [{"statisticType": "sum", "onStatisticField": field, "outStatisticFieldName": "total"},
             {"statisticType": "count", "onStatisticField": field, "outStatisticFieldName": "n_ports"}]
    params = {
        "where": _where(countries, year, iso_field, year_field),
        "groupByFieldsForStatistics": "year,month,day",
        "outStatistics": json.dumps(stats, separators=(",", ":")),
        "orderByFields": "year,month,day",
        "f": "json",
    }
    return layer_url + "?" + urllib.parse.urlencode(params)


def parse_response(payload: Dict) -> Dict[date, float]:
    if "error" in payload:
        err = payload["error"]
        raise SourceError(f"PortWatch: {err.get('message')} {err.get('details') or ''}".strip())
    out = {}
    for feat in payload.get("features", []):
        a = {k.lower(): v for k, v in feat.get("attributes", {}).items()}
        try:
            d = date(int(a["year"]), int(a["month"]), int(a["day"]))
        except (KeyError, TypeError, ValueError):
            continue
        if a.get("total") is not None:
            out[d] = float(a["total"])
    return out


def _field_hint(layer_url: str, field: str, getter) -> str:
    """List the layer's numeric fields when a query fails (usually a wrong field name)."""
    try:
        meta = json.loads(getter(layer_url.rsplit("/query", 1)[0] + "?f=json").decode("utf-8"))
        fields = [f"{f['name']}:{f.get('type', '').replace('esriFieldType', '')}" for f in meta.get("fields", [])]
    except (SourceError, ValueError, KeyError) as exc:
        return f" (could not read layer fields: {exc})"
    return f" (layer fields: {fields[:80]})"


def fetch(series_id: str, frequency: str = "D", countries: Optional[Sequence[str]] = None,
          field: str = "portcalls", start_year: int = 2019, end_year: Optional[int] = None,
          layer_url: str = LAYER_URL, getter: Optional[Callable[[str], bytes]] = None) -> Series:
    getter = getter or get
    end_year = end_year or datetime.now(timezone.utc).year
    obs: Dict[date, float] = {}
    for y in range(start_year, end_year + 1):
        url = build_query(countries, y, field, layer_url=layer_url)
        payload = json.loads(getter(url).decode("utf-8"))
        try:
            part = parse_response(payload)
        except SourceError as exc:
            raise SourceError(f"{exc}{_field_hint(layer_url, field, getter)}") from exc
        if payload.get("exceededTransferLimit"):
            raise SourceError(f"PortWatch truncated the {y} response; narrow the query")
        obs.update(part)
    if not obs:
        raise SourceError(f"{series_id}: PortWatch returned no rows for {countries or 'world'}")
    days = sorted(obs)
    return Series(series_id, [(d, obs[d]) for d in days], frequency, "imf:portwatch",
                  {"countries": ",".join(countries or ["WORLD"]), "field": field})

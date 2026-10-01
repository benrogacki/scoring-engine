"""Destatis GENESIS-Online REST API (``genesisWS/rest/2020``).

Credentials come from the environment and travel in request *headers*, as the
API requires for POST requests:

    DESTATIS_TOKEN               API token from your GENESIS-Online profile, or
    DESTATIS_USERNAME / DESTATIS_PASSWORD
    DESTATIS_GENESIS_URL         optional, overrides the base URL

Without credentials the client falls back to the GENESIS guest login
(``GAST``/``GAST``), which is rate-limited; a free account is more reliable.

Tables are downloaded with ``data/tablefile`` as flat-file CSV (``ffcsv``): one
row per cell, with each classifying variable as code/label/attribute columns.
``parse_ffcsv`` turns that into a single series by filtering on attribute codes
(e.g. ``{"WERTE4": "X13JDKSB"}`` for the calendar and seasonally adjusted line).
Table layouts differ, so run ``freight-nowcast inspect --genesis <table>`` to see
the variables and codes before setting filters in the catalog.
"""
from __future__ import annotations

import csv
import io
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from datetime import date
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple

from ..series import Series
from . import SourceError, parse_number, parse_period

DEFAULT_BASE_URL = "https://genesis.destatis.de/genesisWS/rest/2020"

_DE_HEADERS = [  # German ffcsv headers -> English
    ("statistik", "statistics"), ("zeit", "time"), ("auspraegung", "variable_attribute"),
    ("merkmal", "variable"), ("wert", "value"), ("einheit", "unit"),
]
_MONTH_CODE = re.compile(r"MONAT(\d{2})$")
_QUARTER_CODE = re.compile(r"QUART(\d)$")


def _norm_header(h: str) -> str:
    h = h.strip().strip('"').lower()
    if "__" in h:  # value-variable column, keep as is
        return h
    for de, en in _DE_HEADERS:
        h = h.replace(de, en)
    return h


Transport = Callable[[str, Dict[str, str], Dict[str, str]], bytes]


def _urllib_post(url: str, headers: Dict[str, str], form: Dict[str, str]) -> bytes:
    req = urllib.request.Request(url, data=urllib.parse.urlencode(form).encode(), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return resp.read()
    except urllib.error.HTTPError as exc:
        raise SourceError(f"GENESIS HTTP {exc.code}: {exc.read()[:300]!r}") from exc
    except urllib.error.URLError as exc:
        raise SourceError(f"GENESIS unreachable: {exc.reason}") from exc


class GenesisClient:
    def __init__(self, username: str, password: str = "", base_url: str = DEFAULT_BASE_URL,
                 transport: Optional[Transport] = None):
        self.username, self.password = username, password
        self.base_url = base_url.rstrip("/")
        self.transport = transport or _urllib_post
        self.guest = False

    @classmethod
    def from_env(cls, transport: Optional[Transport] = None) -> "GenesisClient":
        base = os.environ.get("DESTATIS_GENESIS_URL", DEFAULT_BASE_URL)
        token = os.environ.get("DESTATIS_TOKEN")
        if token:
            return cls(token, "", base, transport)
        user, pw = os.environ.get("DESTATIS_USERNAME"), os.environ.get("DESTATIS_PASSWORD")
        if user and pw:
            return cls(user, pw, base, transport)
        client = cls("GAST", "GAST", base, transport)
        client.guest = True
        return client

    def post(self, endpoint: str, form: Dict[str, str]) -> bytes:
        headers = {"Content-Type": "application/x-www-form-urlencoded",
                   "username": self.username, "password": self.password}
        return self.transport(f"{self.base_url}/{endpoint}", headers, form)

    def tablefile(self, name: str, startyear: Optional[int] = None, endyear: Optional[int] = None,
                  language: str = "en", **extra: str) -> str:
        form = {"name": name, "area": "all", "compress": "false", "format": "ffcsv",
                "language": language, "job": "false"}
        if startyear:
            form["startyear"] = str(startyear)
        if endyear:
            form["endyear"] = str(endyear)
        form.update({k: str(v) for k, v in extra.items()})
        body = self.post("data/tablefile", form)
        if body[:2] == b"PK":  # zipped download
            with zipfile.ZipFile(io.BytesIO(body)) as zf:
                body = zf.read(zf.namelist()[0])
        text = body.decode("utf-8-sig", errors="replace")
        if text.lstrip().startswith("{"):
            # JSON means a status message rather than data (bad login, job queued, no data)
            try:
                status = json.loads(text).get("Status", {})
            except json.JSONDecodeError:
                status = {}
            hint = (" (guest login; set DESTATIS_TOKEN from a free genesis.destatis.de account)"
                    if self.guest else "")
            raise SourceError(f"GENESIS {name}: {status.get('Content') or text[:300]}{hint}")
        return text


def _rows(text: str) -> List[Dict[str, str]]:
    reader = csv.reader(io.StringIO(text.lstrip("﻿")), delimiter=";")
    header = [_norm_header(h) for h in next(reader)]
    return [dict(zip(header, r)) for r in reader if r]


def _variables(row: Mapping[str, str]) -> Dict[str, Tuple[str, str]]:
    """``{variable code: (attribute code, attribute label)}`` for one ffcsv row."""
    out = {}
    for k, v in row.items():
        m = re.fullmatch(r"(\d+)_variable_code", k)
        if m and v:
            i = m[1]
            out[v.strip()] = (row.get(f"{i}_variable_attribute_code", "").strip(),
                              row.get(f"{i}_variable_attribute_label", "").strip())
    return out


def _period(row: Mapping[str, str], variables: Mapping[str, Tuple[str, str]]) -> Optional[date]:
    t = (row.get("time") or "").strip()
    if not t:
        return None
    if len(t) > 4:
        return parse_period(t)
    year = int(t)
    for code, _ in variables.values():
        m = _MONTH_CODE.match(code)
        if m:
            return date(year, int(m[1]), 1)
        m = _QUARTER_CODE.match(code)
        if m:
            return date(year, 3 * int(m[1]) - 2, 1)
    return date(year, 1, 1)


def _value_columns(header: List[str]) -> List[str]:
    return [h for h in header if "__" in h]


def parse_ffcsv(text: str, filters: Optional[Mapping[str, str]] = None,
                value_variable: Optional[str] = None) -> List[Tuple[date, float]]:
    """Extract one series from a GENESIS flat-file CSV.

    ``filters`` maps variable code -> attribute code (both as shown by
    ``inspect``); every row must match all of them. ``value_variable`` picks the
    measure when the table has several (a ``value_variable_code`` row field, or a
    ``CODE__label`` column in the wide layout).
    """
    rows = _rows(text)
    if not rows:
        return []
    header = list(rows[0].keys())
    wide = _value_columns(header)
    filters = {k.upper(): v.upper() for k, v in (filters or {}).items()}
    out: Dict[date, float] = {}
    for r in rows:
        vars_ = _variables(r)
        if any(vars_.get(k, ("", ""))[0].upper() != v for k, v in filters.items()):
            continue
        d = _period(r, vars_)
        if d is None:
            continue
        if "value" in r:
            vv = (r.get("value_variable_code") or "").strip()
            if value_variable and vv and vv.upper() != value_variable.upper():
                continue
            val = parse_number(r["value"], ",") if "," in r["value"] else parse_number(r["value"])
        else:
            cols = [c for c in wide if not value_variable or c.split("__")[0].upper() == value_variable.upper()]
            if len(cols) != 1:
                raise SourceError(f"choose value_variable from {[c.split('__')[0] for c in wide]}")
            raw = r[cols[0]]
            val = parse_number(raw, ",") if "," in raw else parse_number(raw)
        if val is None:
            continue
        if d in out and out[d] != val:
            raise SourceError(f"several values for {d}: add filters to pick one line "
                              f"(variables in this table: {sorted(vars_)})")
        out[d] = val
    return sorted(out.items())


def inspect_ffcsv(text: str) -> Dict[str, Any]:
    """Summarise a table: its classifying variables, attribute codes and measures."""
    rows = _rows(text)
    variables: Dict[str, Dict[str, str]] = {}
    measures = set()
    times = set()
    for r in rows:
        for code, (attr, label) in _variables(r).items():
            if not _MONTH_CODE.match(attr) and not _QUARTER_CODE.match(attr):
                variables.setdefault(code, {})[attr] = label
        if r.get("value_variable_code"):
            measures.add(f"{r['value_variable_code']} | {r.get('value_variable_label', '')}")
        times.add(r.get("time", ""))
    if rows:
        measures |= {c for c in _value_columns(list(rows[0].keys()))}
    return {"rows": len(rows), "time": f"{min(times)} .. {max(times)}" if times else "",
            "variables": variables, "measures": sorted(measures)}


def fetch(series_id: str, frequency: str, table: str, filters: Optional[Mapping[str, str]] = None,
          value_variable: Optional[str] = None, startyear: Optional[int] = None,
          client: Optional[GenesisClient] = None, **extra: str) -> Series:
    client = client or GenesisClient.from_env()
    text = client.tablefile(table, startyear=startyear, **extra)
    obs = parse_ffcsv(text, filters, value_variable)
    if not obs:
        raise SourceError(f"{series_id}: GENESIS table {table} returned no rows for filters {filters}; "
                          f"run `freight-nowcast inspect --genesis {table}`")
    return Series(series_id, obs, frequency, f"genesis:{table}", {"table": table})

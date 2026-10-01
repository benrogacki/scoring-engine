"""Free market and statistics endpoints that need no key.

- ``yahoo_chart``  daily closes from Yahoo's public chart endpoint (used for the
  Breakwave Dry Bulk Shipping ETF, BDRY, which holds the near-dated
  Capesize/Panamax/Supramax freight futures, the market behind the Baltic Dry).
  Unofficial endpoint, so it has CSV fallbacks in the catalog.
- ``fred``         any FRED series as ``fredgraph.csv`` (no API key needed).
- ``csv_url``      any CSV on the web (e.g. Stooq daily downloads).
"""
from __future__ import annotations

import json
import urllib.parse
from datetime import datetime, timezone
from typing import Callable, Dict, Optional

from ..series import Series
from . import SourceError, read_csv_series
from .http import get

YAHOO_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
FRED_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"


def parse_yahoo(payload: Dict, symbol: str = ""):
    chart = payload.get("chart") or {}
    if chart.get("error"):
        raise SourceError(f"Yahoo {symbol}: {chart['error'].get('description') or chart['error']}")
    res = (chart.get("result") or [None])[0]
    if not res or not res.get("timestamp"):
        raise SourceError(f"Yahoo {symbol}: empty response")
    ind = res.get("indicators", {})
    closes = ((ind.get("adjclose") or [{}])[0].get("adjclose")
              or (ind.get("quote") or [{}])[0].get("close") or [])
    out = {}
    for ts, c in zip(res["timestamp"], closes):
        if c is not None:
            out[datetime.fromtimestamp(ts, timezone.utc).date()] = float(c)
    return sorted(out.items())


def fetch_yahoo(series_id: str, frequency: str = "D", symbol: str = "BDRY", range_: str = "max",
                getter: Optional[Callable[[str], bytes]] = None) -> Series:
    url = YAHOO_URL.format(symbol=urllib.parse.quote(symbol)) + "?" + urllib.parse.urlencode(
        {"range": range_, "interval": "1d", "includeAdjustedClose": "true"})
    raw = (getter or (lambda u: get(u, {"Accept": "application/json"})))(url)
    obs = parse_yahoo(json.loads(raw.decode("utf-8")), symbol)
    return Series(series_id, obs, frequency, f"yahoo:{symbol}", {"url": url})


def fetch_fred(series_id: str, frequency: str = "M", fred_id: str = "",
               getter: Optional[Callable[[str], bytes]] = None) -> Series:
    if not fred_id:
        raise SourceError(f"{series_id}: fred source needs fred_id")
    url = FRED_URL + "?" + urllib.parse.urlencode({"id": fred_id})
    text = (getter or get)(url).decode("utf-8-sig", errors="replace")
    s = read_csv_series(series_id, text, frequency, value_col=fred_id, source=f"fred:{fred_id}")
    s.meta["url"] = url
    return s


def fetch_csv_url(series_id: str, frequency: str = "D", url: str = "",
                  getter: Optional[Callable[[str], bytes]] = None, **csv_args) -> Series:
    if not url:
        raise SourceError(f"{series_id}: csv_url source needs url")
    text = (getter or get)(url).decode("utf-8-sig", errors="replace")
    if text.lstrip().startswith("<") or "," not in text[:200] and ";" not in text[:200]:
        raise SourceError(f"{series_id}: {url} did not return CSV: {text[:120]!r}")
    s = read_csv_series(series_id, text, frequency, source=f"csv:{urllib.parse.urlsplit(url).netloc}", **csv_args)
    s.meta["url"] = url
    return s

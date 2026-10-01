"""Destatis working-daily truck toll mileage index (experimental statistics, xlsx download).

Destatis publishes the daily index as an Excel file linked from a table page
(updated weekly, daily in high-frequency periods). The connector loads the page,
follows the first ``.xlsx`` link, finds the header row that has a date column, and
takes the column whose header contains ``column_match`` (default: the calendar-
and seasonally adjusted series). ``freight-nowcast probe`` prints the headers it
saw so the match can be tightened if Destatis renames a column.
"""
from __future__ import annotations

import html
import re
import urllib.parse
from datetime import date, datetime
from typing import Callable, List, Optional, Sequence, Tuple

from ..series import Series
from . import SourceError, parse_number, parse_period
from .http import get
from .xlsx import excel_date, read_sheet, sheet_names

PAGE_URL = ("https://www.destatis.de/DE/Themen/Branchen-Unternehmen/Industrie-Verarbeitendes-Gewerbe/"
            "Tabellen/Lkw-Maut-Fahrleistungsindex-Daten.html")
DATE_HEADER = re.compile(r"^(datum|date|tag|day)\b", re.I)
DEFAULT_MATCH = ("kalender- und saisonbereinigt", "saisonbereinigt", "seasonally", "x13", "ksb")


def find_xlsx_link(page_html: str, base_url: str) -> str:
    hrefs = re.findall(r'href="([^"]+)"', page_html)
    cands = [html.unescape(h) for h in hrefs if ".xlsx" in h.lower()]
    if not cands:
        raise SourceError(f"no .xlsx link on {base_url}")
    return urllib.parse.urljoin(base_url, cands[0])


def _as_date(v: object) -> Optional[date]:
    if isinstance(v, float):
        return excel_date(v) if v > 20000 else None
    if isinstance(v, str) and v.strip():
        try:
            return parse_period(v)
        except SourceError:
            return None
    return None


def parse_rows(rows: Sequence[Sequence[object]], column_match: Sequence[str] = DEFAULT_MATCH
               ) -> Tuple[List[Tuple[date, float]], List[str], str]:
    """Locate the header row and value column; return (observations, headers, chosen header)."""
    for hi, row in enumerate(rows[:40]):
        heads = [str(c or "").strip() for c in row]
        low = [h.lower() for h in heads]
        dcol = next((i for i, h in enumerate(low) if DATE_HEADER.match(h)), None)
        if dcol is None or len([h for h in heads if h]) < 2:
            continue
        # headers can span two rows (measure on one row, variant on the next)
        if hi + 1 < len(rows):
            nxt = [str(c or "").strip().lower() for c in rows[hi + 1]]
            low = [f"{a} {nxt[i] if i < len(nxt) else ''}".strip() for i, a in enumerate(low)]
        vcol = None
        for pat in column_match:
            vcol = next((i for i, h in enumerate(low) if i != dcol and pat.lower() in h), None)
            if vcol is not None:
                break
        if vcol is None:
            raise SourceError(f"no column matching {list(column_match)} in headers {heads}")
        obs = []
        for r in rows[hi + 1:]:
            d = _as_date(r[dcol]) if dcol < len(r) else None
            v = r[vcol] if vcol < len(r) else None
            v = v if isinstance(v, float) else parse_number(v, ",") if isinstance(v, str) and v.strip() else None
            if d and v is not None:
                obs.append((d, float(v)))
        return obs, heads, low[vcol]
    sample = [[c for c in r if c not in (None, "")][:6] for r in rows[:12]]
    raise SourceError(f"no header row with a date column in the first 40 rows; first rows: {sample}")


def fetch(series_id: str, frequency: str = "D", page_url: str = PAGE_URL, xlsx_url: Optional[str] = None,
          sheet: Optional[str] = None, column_match: Optional[Sequence[str]] = None,
          getter: Optional[Callable[[str], bytes]] = None) -> Series:
    getter = getter or get
    if not xlsx_url:
        xlsx_url = find_xlsx_link(getter(page_url).decode("utf-8", errors="replace"), page_url)
    data = getter(xlsx_url)
    if data[:2] != b"PK":
        raise SourceError(f"{xlsx_url} did not return an xlsx file")
    errors = []
    for name in ([sheet] if sheet else sheet_names(data)):
        try:
            obs, heads, chosen = parse_rows(read_sheet(data, name), column_match or DEFAULT_MATCH)
            break
        except SourceError as exc:
            errors.append(f"[{name}] {exc}")
    else:
        raise SourceError(f"{series_id}: no usable sheet in {xlsx_url}: " + " | ".join(errors)[:1500])
    if not obs:
        raise SourceError(f"{series_id}: no rows parsed from {xlsx_url} (headers {heads})")
    return Series(series_id, obs, frequency, "destatis:daily-toll-xlsx",
                  {"url": xlsx_url, "sheet": name, "column": chosen})

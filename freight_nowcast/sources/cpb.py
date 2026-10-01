"""CPB World Trade Monitor (free monthly xlsx; no API, so we follow the download link).

The connector loads the World Trade Monitor page, follows the newest ``.xlsx``
link, finds a header row of months (``2000m01``-style codes, dates or Excel
serials) and returns the row whose label contains every word in ``row_match``
(default: world trade volume). If it cannot find the row, the error lists the
row labels it saw so ``row_match`` can be tightened.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Callable, List, Optional, Sequence, Tuple

from ..series import Series
from . import SourceError, parse_number
from .destatis_daily import find_xlsx_link
from .http import get
from .xlsx import excel_date, read_sheet, sheet_names

PAGE_URL = "https://www.cpb.nl/en/worldtrademonitor"
DEFAULT_MATCH = ("world", "trade")
_MONTH = re.compile(r"^(\d{4})\s*[mM-]\s*(\d{1,2})$")


def _month(v: object) -> Optional[date]:
    if isinstance(v, float) and 20000 < v < 80000:
        d = excel_date(v)
        return date(d.year, d.month, 1)
    if isinstance(v, str):
        m = _MONTH.match(v.strip())
        if m and 1 <= int(m[2]) <= 12:
            return date(int(m[1]), int(m[2]), 1)
    return None


def parse_rows(rows: Sequence[Sequence[object]], row_match: Sequence[str] = DEFAULT_MATCH,
               exclude: Sequence[str] = ("price", "value", "import", "export")) -> Tuple[List[Tuple[date, float]], str]:
    hdr_i, months = None, {}
    for i, row in enumerate(rows[:60]):
        found = {j: _month(c) for j, c in enumerate(row)}
        found = {j: d for j, d in found.items() if d}
        if len(found) >= 24:
            hdr_i, months = i, found
            break
    if hdr_i is None:
        raise SourceError("no header row of months found")
    labels = []
    want = [w.lower() for w in row_match]
    for row in rows[hdr_i + 1:]:
        label = " ".join(str(c) for j, c in enumerate(row) if j < min(months) and c not in (None, "")).strip()
        if not label:
            continue
        labels.append(label)
        low = label.lower()
        if all(w in low for w in want) and not any(x in low for x in exclude):
            obs = []
            for j, d in months.items():
                v = row[j] if j < len(row) else None
                v = v if isinstance(v, float) else parse_number(v) if isinstance(v, str) and v.strip() else None
                if v is not None:
                    obs.append((d, float(v)))
            if obs:
                return sorted(obs), label
    raise SourceError(f"no row matching {list(row_match)}; labels: {labels[:40]}")


def fetch(series_id: str, frequency: str = "M", page_url: str = PAGE_URL, xlsx_url: Optional[str] = None,
          row_match: Sequence[str] = DEFAULT_MATCH, exclude: Sequence[str] = ("price", "value", "import", "export"),
          sheet: Optional[str] = None, getter: Optional[Callable[[str], bytes]] = None) -> Series:
    getter = getter or get
    if not xlsx_url:
        xlsx_url = find_xlsx_link(getter(page_url).decode("utf-8", errors="replace"), page_url)
    data = getter(xlsx_url)
    if data[:2] != b"PK":
        raise SourceError(f"{xlsx_url} did not return an xlsx file")
    errors = []
    for name in ([sheet] if sheet else sheet_names(data)):
        try:
            obs, label = parse_rows(read_sheet(data, name), row_match, exclude)
            return Series(series_id, obs, frequency, "cpb:world-trade-monitor",
                          {"url": xlsx_url, "sheet": name, "row": label})
        except SourceError as exc:
            errors.append(f"[{name}] {exc}")
    raise SourceError(f"{series_id}: " + " | ".join(errors)[:2500])

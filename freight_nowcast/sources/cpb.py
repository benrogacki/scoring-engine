"""CPB World Trade Monitor (free monthly xlsx; no API, so we follow the download link).

The connector looks for the newest monthly release page (CPB publishes one page
per release under /en/world-trade-monitor/), follows its ``.xlsx`` link, finds a header row of months (``2000m01``-style codes, dates or Excel
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

INDEX_URL = "https://www.cpb.nl/en/world-trade-monitor"
MONTH_NAMES = ["january", "february", "march", "april", "may", "june", "july", "august",
               "september", "october", "november", "december"]
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


def release_pages(index_html: str, today: date, lookback: int = 8) -> List[str]:
    """Candidate release pages, newest first: links found on the index page, then
    the ``cpb-world-trade-monitor-<month>-<year>`` slug for recent months."""
    import html as _html
    import urllib.parse

    found = []
    for h in re.findall(r'href="([^"]+)"', index_html):
        h = _html.unescape(h)
        if re.search(r"(world-trade-monitor|wereldhandelsmonitor)[^/]*-\d{4}", h):
            u = urllib.parse.urljoin(INDEX_URL, h)
            if u not in found:
                found.append(u)
    built = []
    y, m = today.year, today.month
    for _ in range(lookback):
        m -= 1
        if m == 0:
            y, m = y - 1, 12
        built.append(f"{INDEX_URL}/cpb-world-trade-monitor-{MONTH_NAMES[m - 1]}-{y}")

    def key(u: str):
        mm = re.search(r"-(" + "|".join(MONTH_NAMES + ["januari", "februari", "maart", "mei", "juni", "juli",
                                                        "augustus", "oktober"]) + r")-(\d{4})", u)
        if not mm:
            return (0, 0)
        nl = {"januari": 1, "februari": 2, "maart": 3, "mei": 5, "juni": 6, "juli": 7, "augustus": 8, "oktober": 10}
        mon = MONTH_NAMES.index(mm[1]) + 1 if mm[1] in MONTH_NAMES else nl[mm[1]]
        return (int(mm[2]), mon)

    return sorted(dict.fromkeys(found + built), key=key, reverse=True)


def find_latest_xlsx(getter: Callable[[str], bytes], today: Optional[date] = None) -> str:
    today = today or date.today()
    try:
        index = getter(INDEX_URL).decode("utf-8", errors="replace")
    except SourceError:
        index = ""
    tried = []
    for page in release_pages(index, today):
        try:
            return find_xlsx_link(getter(page).decode("utf-8", errors="replace"), page)
        except SourceError as exc:
            tried.append(f"{page.rsplit('/', 1)[-1]}: {str(exc)[:60]}")
    raise SourceError("no World Trade Monitor xlsx found; tried " + "; ".join(tried[:10]))


def fetch(series_id: str, frequency: str = "M", xlsx_url: Optional[str] = None,
          row_match: Sequence[str] = DEFAULT_MATCH, exclude: Sequence[str] = ("price", "value", "import", "export"),
          sheet: Optional[str] = None, getter: Optional[Callable[[str], bytes]] = None) -> Series:
    getter = getter or get
    if not xlsx_url:
        xlsx_url = find_latest_xlsx(getter)
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

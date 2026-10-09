"""``brg-tax params-update``: confirm each parameter against its GOV.UK source page.

For every value with a ``verify`` spec, the cited page is fetched and its text is searched for the
expected figure (e.g. "£90,000") within a window of the label text (e.g. "threshold"). A match marks
the value ``verified: true`` with today's date as ``retrieved``; a miss leaves it unverified and
records why in ``verify_result``. This is a presence check, not a parser: a page that changes its
wording will show as unverified until the ``verify`` spec is updated. Values are never changed
automatically - a figure that cannot be confirmed must be checked and edited by hand.
"""
from __future__ import annotations

import html
import json
import re
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path
from typing import Callable, Dict, List, Optional

from .params import PARAMS_DIR

UA = "brg-tax-params-update/1.0 (BRG Accounts working papers)"
WINDOW = 600


def page_text(raw: str) -> str:
    raw = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", raw)
    text = re.sub(r"(?s)<[^>]+>", " ", raw)
    text = html.unescape(text).replace(" ", " ")
    return re.sub(r"\s+", " ", text)


def fetch(url: str, timeout: int = 25) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def check(text: str, expect: str, near: Optional[str]) -> Optional[str]:
    """Return None when ``expect`` is found (near ``near`` if given), otherwise a reason."""
    norm = lambda s: re.sub(r"\s+", " ", s).lower()   # noqa: E731
    t, e = norm(text), norm(expect)
    hits = [m.start() for m in re.finditer(re.escape(e), t)]
    if not hits:
        return f"'{expect}' not found on the page"
    if not near:
        return None
    n = norm(near)
    labels = [m.start() for m in re.finditer(re.escape(n), t)]
    if not labels:
        return f"label '{near}' not found on the page"
    if any(abs(h - l) <= WINDOW for h in hits for l in labels):
        return None
    return f"'{expect}' found, but not within {WINDOW} characters of '{near}'"


def update(years: Optional[List[str]] = None, directory: Optional[Path] = None, fetcher: Callable[[str], str] = fetch,
           today: Optional[date] = None, dry_run: bool = False) -> Dict[str, Dict[str, int]]:
    directory = Path(directory or PARAMS_DIR)
    today = today or date.today()
    cache: Dict[str, object] = {}
    summary: Dict[str, Dict[str, int]] = {}
    for path in sorted(directory.glob("*.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        if years and doc["label"] not in years:
            continue
        s = {"verified": 0, "unverified": 0, "no_check": 0, "fetch_failed": 0}
        for key, e in doc["params"].items():
            spec = e.get("verify")
            if not spec or not spec.get("text"):
                s["no_check"] += 1
                e["verified"] = bool(e.get("verified"))
                continue
            url = e["source_url"]
            if url not in cache:
                try:
                    cache[url] = page_text(fetcher(url))
                except (urllib.error.URLError, OSError, ValueError) as exc:
                    cache[url] = exc
            got = cache[url]
            if isinstance(got, Exception):
                e["verified"] = False
                e["verify_result"] = f"fetch failed {today.isoformat()}: {got}"
                s["fetch_failed"] += 1
                continue
            reason = check(got, spec["text"], spec.get("near"))
            e["verified"] = reason is None
            e["verify_result"] = "confirmed on source page" if reason is None else reason
            if reason is None:
                e["retrieved"] = today.isoformat()
                s["verified"] += 1
            else:
                s["unverified"] += 1
        doc["last_params_update"] = today.isoformat()
        if not dry_run:
            path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        summary[doc["label"]] = s
    return summary

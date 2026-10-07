"""One place for outbound HTTP so every connector reports failures the same way."""
from __future__ import annotations

import time
import urllib.error
import urllib.request
from typing import Dict, Optional

from . import SourceError

USER_AGENT = "freight-nowcast/0.2 (+https://github.com/benrogacki/global-freight-tracker)"


def get(url: str, headers: Optional[Dict[str, str]] = None, timeout: int = 120, retries: int = 2) -> bytes:
    h = {"User-Agent": USER_AGENT, **(headers or {})}
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as exc:
            if exc.code in (429, 500, 502, 503, 504) and attempt < retries:
                time.sleep(2 ** (attempt + 1))
                continue
            raise SourceError(f"HTTP {exc.code} for {url}: {exc.read()[:200]!r}") from exc
        except urllib.error.URLError as exc:
            if attempt < retries:
                time.sleep(2 ** (attempt + 1))
                continue
            raise SourceError(f"unreachable: {url} ({exc.reason})") from exc
    raise SourceError(f"unreachable: {url}")

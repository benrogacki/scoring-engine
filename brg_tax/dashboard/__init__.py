"""Build the single self-contained HTML dashboard: the run payload and the JS engine mirror are
embedded inline, so the file works offline (Google Fonts are the only external request)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

HERE = Path(__file__).parent
TEMPLATE = HERE / "template.html"
MIRROR = HERE / "engine_mirror.js"
STANDALONE_HEAD = (
    '<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
    '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
    "</head>\n<body>\n"
)


def payload(run: Dict[str, Any]) -> Dict[str, Any]:
    from ..report import DOWNLOADS
    p = json.loads(json.dumps(run, default=str))
    for c in p["clients"]:
        for t in c["treatments"]:
            t["params"] = [{"key": u["key"], "year": u["year"]} for u in t["params"]]
        c.pop("profile", None)
    p["downloads"] = DOWNLOADS
    return p


def render(run: Dict[str, Any], standalone: bool = True) -> str:
    data = json.dumps(payload(run), separators=(",", ":")).replace("</", "<\\/")
    mirror = MIRROR.read_text(encoding="utf-8").replace("</", "<\\/")
    page = TEMPLATE.read_text(encoding="utf-8").replace("__PAYLOAD__", data).replace("/*__MIRROR__*/", mirror)
    return STANDALONE_HEAD + page + "\n</body>\n</html>\n" if standalone else page

"""Minimal .xlsx reader (standard library only): enough to read a statistics office's data sheet."""
from __future__ import annotations

import io
import re
import zipfile
import xml.etree.ElementTree as ET
from datetime import date, timedelta
from typing import Dict, List, Optional

NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
      "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"}
REL_NS = "{http://schemas.openxmlformats.org/package/2006/relationships}"


def _col_index(ref: str) -> int:
    letters = re.match(r"[A-Z]+", ref).group(0)
    n = 0
    for ch in letters:
        n = n * 26 + ord(ch) - 64
    return n - 1


def excel_date(serial: float) -> date:
    return date(1899, 12, 30) + timedelta(days=int(serial))


def sheet_names(data: bytes) -> List[str]:
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        wb = ET.fromstring(zf.read("xl/workbook.xml"))
        return [s.get("name") for s in wb.find("m:sheets", NS)]


def read_sheet(data: bytes, sheet: Optional[str] = None) -> List[List[object]]:
    """Return the rows of one sheet (default: the first) as lists of str/float/None."""
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        shared: List[str] = []
        if "xl/sharedStrings.xml" in zf.namelist():
            for si in ET.fromstring(zf.read("xl/sharedStrings.xml")).findall("m:si", NS):
                shared.append("".join(t.text or "" for t in si.iter(f"{{{NS['m']}}}t")))
        wb = ET.fromstring(zf.read("xl/workbook.xml"))
        sheets = wb.find("m:sheets", NS)
        target = None
        for s in sheets:
            if sheet is None or s.get("name") == sheet:
                target = s.get(f"{{{NS['r']}}}id")
                break
        if target is None:
            raise ValueError(f"sheet {sheet!r} not found; sheets: {[s.get('name') for s in sheets]}")
        rels = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
        path = next(r.get("Target") for r in rels.iter(f"{REL_NS}Relationship") if r.get("Id") == target)
        path = path.lstrip("/")
        if not path.startswith("xl/"):
            path = "xl/" + path
        root = ET.fromstring(zf.read(path))
    rows: List[List[object]] = []
    for row in root.iter(f"{{{NS['m']}}}row"):
        cells: Dict[int, object] = {}
        for c in row.findall("m:c", NS):
            t, v = c.get("t"), c.find("m:v", NS)
            if t == "s" and v is not None:
                val: object = shared[int(v.text)]
            elif t == "inlineStr":
                val = "".join(x.text or "" for x in c.iter(f"{{{NS['m']}}}t"))
            elif t in ("str", "e") and v is not None:
                val = v.text
            elif v is not None and v.text is not None:
                try:
                    val = float(v.text)
                except ValueError:
                    val = v.text
            else:
                val = None
            cells[_col_index(c.get("r"))] = val
        if cells:
            rows.append([cells.get(i) for i in range(max(cells) + 1)])
    return rows

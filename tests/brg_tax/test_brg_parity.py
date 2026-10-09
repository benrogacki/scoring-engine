"""Parity: the dashboard's JS mirror (run under Node) must reproduce the Python engine exactly."""
import itertools
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from brg_tax.engine import extraction, taxmath
from brg_tax.money import to_pence
from helpers import client, ctx

MIRROR = Path(__file__).resolve().parents[2] / "brg_tax" / "dashboard" / "engine_mirror.js"
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="Node.js is not installed")

RUNNER = """
const M = require(process.argv[1]);
let buf = ""; process.stdin.on("data", d => buf += d); process.stdin.on("end", () => {
  const cases = JSON.parse(buf);
  const out = cases.map(c => {
    if (c.fn === "scenario") return M.scenario(c.model, c.sc);
    if (c.fn === "optimise") { const b = M.optimise(c.model); return { salary: b.salary, result: b.result }; }
    if (c.fn === "compare") return M.compareStructures(c.profit, c.cm);
    if (c.fn === "vat") return M.vatCompare(c.v);
    if (c.fn === "income_tax") return M.incomeTax(c.ns, c.div, c.bands, c.ty);
    throw new Error("unknown " + c.fn);
  });
  process.stdout.write(JSON.stringify(out));
});
"""


def node(cases):
    res = subprocess.run([NODE, "-e", RUNNER, str(MIRROR)], input=json.dumps(cases), capture_output=True, text=True, check=True)
    return json.loads(res.stdout)


def python(c):
    if c["fn"] == "scenario":
        return taxmath.scenario(c["model"], c["sc"])
    if c["fn"] == "optimise":
        b = taxmath.optimise(c["model"])
        return {"salary": b["salary"], "result": b["result"]}
    if c["fn"] == "compare":
        return taxmath.compare_structures(c["profit"], c["cm"])
    if c["fn"] == "vat":
        return taxmath.vat_compare(c["v"])
    return taxmath.income_tax(c["ns"], c["div"], c["bands"], c["ty"])


def norm(x):
    return json.loads(json.dumps(x))


def test_parity_extraction_grid(run):
    cases = []
    P = to_pence
    for c in run["clients"]:
        if not c.get("extraction"):
            continue
        m = c["extraction"]["model"]
        dirs = [p["id"] for p in m["people"] if p["director"]]
        for sal, div, pen, clear in itertools.product([0, P(6708), P(12570), P(30000), P(60000), P(130000)],
                                                      [0, P(20000), P(80000), P(400000)], [0, P(15000)], [False, True]):
            sc = {"salaries": {d: sal for d in dirs}, "pensions": {d: pen for d in dirs}, "dividend_total": div, "clear_dla": clear}
            cases.append({"fn": "scenario", "model": m, "sc": sc})
        cases.append({"fn": "optimise", "model": m})
    js = node(cases)
    assert len(js) == len(cases) > 100
    for c, j in zip(cases, js):
        assert norm(python(c)) == j


def test_parity_comparator_vat_and_income_tax(run):
    P = to_pence
    cases = []
    for c in run["clients"]:
        if c.get("sa"):
            for profit in [0, P(8000), P(12570), P(30000), P(50270), P(72230), P(100000), P(125140), P(180000), P(400000)]:
                for admin in [0, P(1500), P(4000)]:
                    cases.append({"fn": "compare", "profit": profit, "cm": dict(c["sa"]["comparator_model"], admin_cost=admin)})
        if c["vat"].get("model"):
            v = c["vat"]["model"]
            for sector, first in itertools.product(list(v["sectors"].values()), [False, True]):
                cases.append({"fn": "vat", "v": dict(v, sector_bp=sector, first_year=first)})
    for label in ("2023-24", "2024-25", "2025-26", "2026-27"):
        ty = extraction.ty_model(ctx(client()), label)[0]
        for region in ("england", "scotland", "wales"):
            bands = extraction.region_bands(ctx(client()), region, label)[0]
            for ns, div in itertools.product([0, P(9000), P(12570), P(45000), P(99999), P(110001), P(160000)], [0, P(400), P(30000), P(150000)]):
                cases.append({"fn": "income_tax", "ns": ns, "div": div, "bands": bands, "ty": ty})
    js = node(cases)
    assert len(js) == len(cases) > 300
    for c, j in zip(cases, js):
        assert norm(python(c)) == j

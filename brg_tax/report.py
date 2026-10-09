"""Write a run's outputs: dashboard, computations, treatments, review queue, calendar, health, changes, summary."""
from __future__ import annotations

import csv
import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from .money import fmt

DISCLAIMER = ("Outputs are working papers to support professional review and are not advice until reviewed and signed off. "
              "Synthetic sample clients contain no real data.")
DOWNLOADS = [
    ["summary.md", "Practice summary"],
    ["treatments.csv", "Every transaction's tax and VAT treatment with rules and authorities"],
    ["review_queue.json", "Judgment, missing-fact and anti-avoidance items (import decisions with --decisions)"],
    ["deadlines.ics", "Deadline calendar"],
    ["health.json", "Data health checks, parameter verification and rule validation"],
    ["changes.json", "Changes since the previous run"],
    ["run.json", "Full run results (used by brg-tax diff)"],
]


def _status_word(c: Dict[str, Any]) -> str:
    return {"ready": "Ready", "review": "Needs review", "attention": "Needs attention", "blocked": "Blocked - data health failed"}[c["status"]]


def computation_md(run: Dict[str, Any], c: Dict[str, Any]) -> str:
    comp = c["computation"]
    per = c["period"]
    head = "Corporation tax computation" if comp["kind"] == "ct" else f"Self-employment computation {comp.get('tax_year', '')}"
    out = [f"# {c['name']} - {head}", "",
           f"Period {per['start']} to {per['end']} ({per['days']} days) · as of {run['as_of']} · status: **{_status_word(c)}**"
           + (" · **provisional** (open review items)" if comp["provisional"] else ""), "",
           "| Line | £ | Rules | Authority |", "|---|---:|---|---|"]
    for ln in comp["lines"]:
        label = ln["label"] if ln["kind"] == "line" else f"**{ln['label']}**"
        amt = "" if ln["kind"] == "note" and ln["amount"] == 0 else fmt(ln["amount"])
        if ln["kind"] in ("subtotal", "total"):
            amt = f"**{amt}**"
        flag = " ⚠ provisional" if ln.get("provisional") else ""
        out.append(f"| {label}{flag} | {amt} | {', '.join(ln['rules'])} | {'; '.join(ln['authority'][:4])} |")
    out += ["", "## Line detail", ""]
    for ln in comp["lines"]:
        if not (ln["detail"] or ln["params"] or ln["review_ids"]):
            continue
        out.append(f"**{ln['label']}**")
        out += [f"- {d}" for d in ln["detail"][:12]]
        for p in ln["params"]:
            out.append(f"- Parameter `{p['key']}` ({p['year']}) = {json.dumps(p['value'])} - {p['authority']} - "
                       f"{'verified' if p['verified'] else 'UNVERIFIED'} - {p['source_url']}")
        for r in ln["review_ids"]:
            out.append(f"- Review item `{r}`")
        out.append("")
    if c.get("ca", {}).get("lines"):
        out += ["## Capital allowances", "", "| Allowance | £ | Rules |", "|---|---:|---|"]
        out += [f"| {ln['label']} | {fmt(ln['amount'])} | {', '.join(ln['rules'])} |" for ln in c["ca"]["lines"]]
        out += ["", "Pools carried forward: " + ", ".join(f"{k} {fmt(v)}" for k, v in c["ca"]["pools_cf"].items()), ""]
    if c.get("dla", {}).get("people"):
        out += ["## Director's loan account", ""]
        for p in c["dla"]["people"]:
            out.append(f"- {p['name']}: year-end balance {fmt(p['year_end_balance'])}; s455 base {fmt(p['s455_base'])} at {p['s455_rate']}% = "
                       f"**{fmt(p['s455'])}** ({p['status']}, due {c['dla']['due_date']}). Peak {fmt(p['max_balance'])}.")
            b = p["bik"]
            if b.get("applies"):
                out.append(f"  - Beneficial loan {b['tax_year']}: averaging {fmt(b['averaging'])}, alternative method {fmt(b['alternative'])}; "
                           f"benefit {fmt(b['benefit'])}, Class 1A {fmt(b['class1a'])}")
            for f in p["findings"]:
                out.append(f"  - {f['rule']}: repayment {fmt(f['amount'])} on {f['repayment']} matched {fmt(f['matched'])} ({f['review_id']})")
        out.append("")
    if c.get("extraction"):
        e = c["extraction"]
        d, b = e["default"]["result"], e["best"]["result"]
        out += ["## Profit extraction (planning, " + e["model"]["tax_year"] + ")", "",
                "| | Current position | Optimised |", "|---|---:|---:|",
                f"| Salary per director | {', '.join(fmt(v) for v in e['default']['scenario']['salaries'].values())} | {fmt(e['best']['salary'])} |",
                f"| Dividends | {fmt(d['dividend_total'])} | {fmt(b['dividend_total'])} |",
                f"| Corporation tax | {fmt(d['ct'])} | {fmt(b['ct'])} |",
                f"| Income tax incl. dividend tax | {fmt(d['income_tax'])} | {fmt(b['income_tax'])} |",
                f"| Employee + employer NIC | {fmt(d['ee_nic'] + d['er_nic_net'])} | {fmt(b['ee_nic'] + b['er_nic_net'])} |",
                f"| Total tax | {fmt(d['total_tax'])} | {fmt(b['total_tax'])} |",
                f"| Net value to shareholders | {fmt(d['value'])} | {fmt(b['value'])} |", "",
                f"Difference: {fmt(e['saving'])}. Elections only (EXT-SAL-01, EXT-PEN-01, EXT-DIV-01); anti-avoidance screened (AA-GAAR-01).", ""]
    if c.get("sa"):
        cmp = c["sa"]["comparator"]
        out += ["## Sole trader vs limited company (illustrative, SA-INC-01)", "",
                f"At a profit of {fmt(cmp['profit'])}: sole trader tax {fmt(cmp['sole_trader']['total'])}, net {fmt(cmp['sole_trader']['net'])}; "
                f"company route total tax and admin {fmt(cmp['company']['total'])} (salary {fmt(cmp['company']['salary'])}), net {fmt(cmp['company']['net'])}. "
                f"Difference {fmt(cmp['difference'])}.", ""]
        m = c["sa"]["mtd"]
        out += [f"MTD for Income Tax: mandated from {m['mandated_from'] or 'not yet'}; software recorded: {'yes' if m['software'] else 'no'}.", ""]
    if c["review"]:
        out += ["## Review queue", ""]
        for r in c["review"]:
            out.append(f"- [{r['status']}] **{r['title']}** ({r['rule_id']}, {r['kind']}) - {r['question']}")
            if r.get("reasoning"):
                out.append(f"  - Proposed: {json.dumps(r['proposed'])}. {r['reasoning']}")
            if r.get("impact"):
                out.append(f"  - Impact: {r['impact']}")
        out.append("")
    if c["flags"]:
        out += ["## Alerts", ""] + [f"- **{f['severity']}** ({f['rule']}): {f['message']}" for f in c["flags"]] + [""]
    out += ["## Data health", ""] + [f"- {k['status'].upper()} {k['name']}: {k['detail']}" for k in c["health"]["checks"]] + ["", f"_{DISCLAIMER}_", ""]
    return "\n".join(out)


def treatments_rows(run: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows = []
    for c in run["clients"]:
        for t in c["treatments"]:
            rows.append({"client": c["id"], "txn_id": t["txn_id"], "date": t["date"], "description": t["description"], "category": t["category"],
                         "amount": f"{t['amount'] / 100:.2f}", "vat": f"{t['vat'] / 100:.2f}", "tax_treatment": t["ct"],
                         "allowable": f"{t['allowable'] / 100:.2f}", "disallowed": f"{t['disallowed'] / 100:.2f}", "vat_treatment": t["vat_treatment"],
                         "vat_recoverable": f"{t['vat_recoverable'] / 100:.2f}", "rules": " ".join(t["rules"]), "authority": "; ".join(t["authority"]),
                         "params": "; ".join(f"{p['key']}@{p['year']}" for p in t["params"]), "review_id": t["review_id"] or "",
                         "provisional": "yes" if t["provisional"] else "", "note": t["note"]})
    return rows


def ics(run: Dict[str, Any]) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//BRG Accounts//BRG Tax Engine//EN", "CALSCALE:GREGORIAN"]
    for e in run["deadlines"]:
        d = date.fromisoformat(e["date"])
        end = date.fromordinal(d.toordinal() + 1)
        summary = f"{e['client']}: {e['title']}".replace(",", "\\,")
        desc = f"{e['for']}. Authority: {'; '.join(e['authority'])}. Rule {e['rule']}.".replace(",", "\\,")
        lines += ["BEGIN:VEVENT", f"UID:{e['id']}@brg-tax", f"DTSTAMP:{stamp}", f"DTSTART;VALUE=DATE:{d.strftime('%Y%m%d')}",
                  f"DTEND;VALUE=DATE:{end.strftime('%Y%m%d')}", f"SUMMARY:{summary}", f"DESCRIPTION:{desc}", "END:VEVENT"]
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"


def summary_md(run: Dict[str, Any]) -> str:
    t = run["totals"]
    pv = run["params"]
    out = [f"# BRG Tax Engine - practice summary as of {run['as_of']}", "",
           f"Run fingerprint `{run['fingerprint']}` · {t['clients']} clients · estimated liabilities {fmt(t['liability'])} "
           f"(plus s455 exposure {fmt(t['s455'])}) · {t['open_review']} open review items · parameters verified {pv['verified']}/{pv['total']}", ""]
    if pv["verified"] < pv["total"]:
        out += [f"> **Parameters not verified:** {pv['total'] - pv['verified']} values have not been confirmed against GOV.UK. "
                "Run `brg-tax params-update` with network access before relying on any figure.", ""]
    if run["rules"]["problems"]:
        out += ["> **Rules library has problems:** " + "; ".join(f"{p['rule']}: {p['problem']}" for p in run["rules"]["problems"]), ""]
    out += ["| Client | Type | Period end | Status | Liability | Open review | Alerts |", "|---|---|---|---|---:|---:|---|"]
    for c in run["clients"]:
        worst = [f for f in c["flags"] if f["severity"] in ("critical", "serious")]
        out.append(f"| {c['name']} | {c['entity_type'].replace('_', ' ')} | {c['period']['end']} | {_status_word(c)} | {fmt(c['liability'])} | "
                   f"{c['open_review']} | {'; '.join(f['message'][:90] for f in worst) or '-'} |")
    soon = [e for e in run["deadlines"] if e["status"] in ("due_soon", "upcoming") and e["days"] <= 90]
    out += ["", "## Deadlines in the next 90 days", ""] + [f"- {e['date']} · {e['client']} · {e['title']} ({e['for']})" for e in soon] + [""]
    ch = run.get("changes", {}).get("changes", [])
    if ch:
        out += ["## Changes since the last run", ""] + [f"- **{x['severity']}** {x['title']}: {x['detail']}" for x in ch[:30]] + [""]
    out += [f"_{DISCLAIMER}_", ""]
    return "\n".join(out)


def write_outputs(run: Dict[str, Any], out: Path, dashboard_html: str) -> List[Path]:
    out = Path(out)
    (out / "computations").mkdir(parents=True, exist_ok=True)
    written = []

    def w(name: str, text: str) -> None:
        p = out / name
        p.write_text(text, encoding="utf-8")
        written.append(p)

    for c in run["clients"]:
        w(f"computations/{c['id']}.md", computation_md(run, c))
    rows = treatments_rows(run)
    with (out / "treatments.csv").open("w", newline="", encoding="utf-8") as fh:
        wr = csv.DictWriter(fh, fieldnames=list(rows[0].keys()) if rows else ["client"])
        wr.writeheader()
        wr.writerows(rows)
    written.append(out / "treatments.csv")
    w("review_queue.json", json.dumps({"schema": "brg_tax/review_queue@1", "as_of": run["as_of"], "fingerprint": run["fingerprint"],
                                       "items": run["review_queue"]}, indent=2))
    w("deadlines.ics", ics(run))
    w("health.json", json.dumps({"as_of": run["as_of"], "clients": {c["id"]: c["health"] for c in run["clients"]},
                                 "params": {k: v for k, v in run["params"].items() if k != "rows"} | {"unverified": [r for r in run["params"]["rows"] if not r["verified"]]},
                                 "rules": {"problems": run["rules"]["problems"], "coverage": run["rules"]["coverage"]}}, indent=2, default=str))
    w("changes.json", json.dumps(run.get("changes", {}), indent=2))
    w("summary.md", summary_md(run))
    w("run.json", json.dumps(run, default=str))
    w("run_fingerprint.txt", run["fingerprint"] + "\n")
    w("dashboard.html", dashboard_html)
    return written

"""End to end: the CLI writes every output, decisions round-trip, and the diff finds changes."""
import json
from pathlib import Path

from brg_tax.cli import main

ROOT = Path(__file__).resolve().parents[2]
OUTPUTS = ["dashboard.html", "treatments.csv", "review_queue.json", "deadlines.ics", "health.json", "changes.json",
           "summary.md", "run.json", "run_fingerprint.txt"]


def run_cli(clients_dir, out, *extra):
    return main(["run", "--clients", str(clients_dir), "--policy", str(ROOT / "policy.json"), "--as-of", "2026-10-09", "--out", str(out), *extra])


def test_check_passes():
    assert main(["check"]) == 0


def test_run_writes_outputs_and_decisions_roundtrip(clients_dir, tmp_path):
    first = tmp_path / "first"
    assert run_cli(clients_dir, first) == 0
    for name in OUTPUTS:
        assert (first / name).exists(), name
    assert len(list((first / "computations").glob("*.md"))) == 6
    html = (first / "dashboard.html").read_text()
    assert "__PAYLOAD__" not in html and "BRGMirror" in html and "not advice until reviewed" in html
    queue = json.loads((first / "review_queue.json").read_text())["items"]
    home = next(i for i in queue if i["rule_id"] == "EXP-HOME-02")

    # A reviewer disallows the use-of-home payment in the dashboard and exports the decision.
    decisions = tmp_path / "decisions.json"
    decisions.write_text(json.dumps({"schema": "brg_tax/decisions@1", "decisions": {
        home["id"]: {"decision": "override", "outcome": {"ct": "disallow"}, "reviewer": "BR", "note": "No evidence of extra costs", "date": "2026-10-09"}}}))
    second = tmp_path / "second"
    assert run_cli(clients_dir, second, "--decisions", str(decisions), "--previous", str(first)) == 0
    run1 = json.loads((first / "run.json").read_text())
    run2 = json.loads((second / "run.json").read_text())
    k1 = next(c for c in run1["clients"] if c["id"] == "c05-kestrel")
    k2 = next(c for c in run2["clients"] if c["id"] == "c05-kestrel")
    assert k2["computation"]["ttp"] == k1["computation"]["ttp"] + 120000          # £1,200 now disallowed
    item = next(r for r in k2["review"] if r["id"] == home["id"])
    assert item["status"] == "decided" and item["decision"]["reviewer"] == "BR"
    t = next(t for t in k2["treatments"] if t["review_id"] == home["id"])
    assert t["ct"] == "disallow" and not t["provisional"]
    changes = json.loads((second / "changes.json").read_text())["changes"]
    assert any(c["title"] == "Review items decided" and c["client_id"] == "c05-kestrel" for c in changes)
    assert any(c["title"] == "Estimated liability moved" and c["client_id"] == "c05-kestrel" for c in changes)


def test_diff_command(clients_dir, tmp_path, capsys):
    a, b = tmp_path / "a", tmp_path / "b"
    run_cli(clients_dir, a)
    main(["run", "--clients", str(clients_dir), "--policy", str(ROOT / "policy.json"), "--as-of", "2026-12-01", "--out", str(b)])
    assert main(["diff", str(a), str(b)]) == 0
    out = capsys.readouterr().out
    assert "Changes from 2026-10-09 to 2026-12-01" in out


def test_ics_is_valid_calendar(clients_dir, tmp_path):
    run_cli(clients_dir, tmp_path / "o")
    ics = (tmp_path / "o" / "deadlines.ics").read_text()
    assert ics.startswith("BEGIN:VCALENDAR") and ics.rstrip().endswith("END:VCALENDAR")
    assert ics.count("BEGIN:VEVENT") == ics.count("END:VEVENT") > 20

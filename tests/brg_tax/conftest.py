"""Shared fixtures: the synthetic sample clients, run once per test session."""
import json
from datetime import date
from pathlib import Path

import pytest

from brg_tax.engine.run import run_all
from brg_tax.params import ParamStore
from brg_tax.rules import RuleBook
from brg_tax.samples import generate

ROOT = Path(__file__).resolve().parents[2]
AS_OF = date(2026, 10, 9)


@pytest.fixture(scope="session")
def store():
    return ParamStore.load()


@pytest.fixture(scope="session")
def book():
    return RuleBook.load()


@pytest.fixture(scope="session")
def policy():
    return json.loads((ROOT / "policy.json").read_text())


@pytest.fixture(scope="session")
def clients_dir(tmp_path_factory):
    d = tmp_path_factory.mktemp("clients")
    generate(d)
    return d


@pytest.fixture(scope="session")
def run(clients_dir, policy):
    return run_all(clients_dir, policy, {}, AS_OF)


@pytest.fixture(scope="session")
def by_id(run):
    return {c["id"]: c for c in run["clients"]}

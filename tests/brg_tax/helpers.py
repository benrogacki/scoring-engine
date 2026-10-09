"""Small builders for unit tests."""
from datetime import date

from brg_tax.engine.context import Ctx
from brg_tax.models import Client, Transaction
from brg_tax.params import ParamStore
from brg_tax.rules import RuleBook

_STORE = ParamStore.load()
_BOOK = RuleBook.load()


def client(entity="company", **kw):
    base = {"id": "t", "name": "Test", "entity_type": entity, "package": "xero",
            "periods": [{"start": "2025-04-01", "end": "2026-03-31"}], "associated_companies": 0}
    base.update(kw)
    return Client(**base)


def ctx(c=None, decisions=None, as_of=date(2026, 10, 9), policy=None):
    _STORE.used.clear()
    return Ctx(params=_STORE, rules=_BOOK, policy=policy or {}, decisions=decisions or {}, as_of=as_of, client=c or client())


def txn(category, net, vat=0, d=date(2025, 10, 1), side="expense", **facts):
    return Transaction(id=f"x:{category}:{net}", date=d, code="x", description=category, net=net, vat=vat,
                       category=category, side=side, facts=facts)

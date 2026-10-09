"""Shared state for one client's computation: parameters, rules, policy, decisions and the review queue."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, List, Optional

from ..models import Client, ReviewItem
from ..params import ParamStore
from ..rules import Rule, RuleBook


@dataclass
class Ctx:
    params: ParamStore
    rules: RuleBook
    policy: Dict[str, Any]
    decisions: Dict[str, Dict[str, Any]]
    as_of: date
    client: Client
    review: List[ReviewItem] = field(default_factory=list)
    flags: List[Dict[str, Any]] = field(default_factory=list)

    def rule(self, rule_id: str, on: Optional[date] = None) -> Rule:
        return self.rules.get(rule_id, on)

    def decision(self, review_id: str) -> Optional[Dict[str, Any]]:
        return self.decisions.get(review_id)

    def add_review(self, rule: Rule, key: str, title: str, *, kind: str = "judgment", proposed: Optional[Dict[str, Any]] = None,
                   reasoning: str = "", amount: int = 0, txn_ids: Optional[List[str]] = None, question: str = "",
                   impact: str = "", extra_factors: Optional[List[str]] = None) -> ReviewItem:
        rid = f"{self.client.id}:{rule.id}:{key}"
        for existing in self.review:
            if existing.id == rid:
                return existing
        dec = self.decision(rid)
        item = ReviewItem(
            id=rid, client_id=self.client.id, kind=kind, rule_id=rule.id, title=title,
            question=question or rule.question, factors=list(rule.factors) + list(extra_factors or []),
            authorities=list(rule.authorities), authority=list(rule.authority), guidance=list(rule.guidance),
            proposed=proposed if proposed is not None else dict(rule.default), reasoning=reasoning or rule.reasoning,
            amount=amount, txn_ids=list(txn_ids or []), status="decided" if dec else "open", decision=dec, impact=impact,
        )
        self.review.append(item)
        return item

    def flag(self, rule_id: str, severity: str, message: str, **extra: Any) -> None:
        """A finding that is not a review item: an alert on the client (severity: info | warning | serious | critical)."""
        self.flags.append({"rule": rule_id, "severity": severity, "message": message, **extra})

    def pol(self, path: str, default: Any = None) -> Any:
        cur: Any = self.policy
        for part in path.split("."):
            if not isinstance(cur, dict) or part not in cur:
                return default
            cur = cur[part]
        return cur

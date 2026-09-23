"""Collection priority: who to chase first, and how.

Priority score = urgency-weighted overdue value x risk multiplier, where the
risk multiplier grows as the composite credit score falls. Customers are then
placed in tiers by the age of their oldest debt and their grade, and ranked
within tier by priority score.
"""
from __future__ import annotations

from typing import Any, Dict, List

from .models import CustomerScore

TIER_ACTIONS = {
    "P1": "Escalate: stop supply, final demand, consider agency/legal referral",
    "P2": "Senior call + formal demand letter; agree dated payment plan",
    "P3": "Phone call to accounts payable; confirm payment date",
    "P4": "Automated reminder / statement",
}


def _tier(score: CustomerScore, min_balance: float) -> str:
    f = score.features
    if f.overdue < min_balance:
        return "P4"
    if f.ageing.get("90_plus", 0) >= min_balance or score.grade == "E":
        return "P1"
    if f.ageing.get("61_90", 0) >= min_balance or score.grade == "D":
        return "P2"
    if f.ageing.get("31_60", 0) >= min_balance:
        return "P3"
    return "P4"


def prioritise_collections(scores: List[CustomerScore], cfg: Dict[str, Any]) -> List[CustomerScore]:
    """Populate collection fields and return the overdue customers in work order."""
    c = cfg["collections"]
    worklist = []
    for s in scores:
        f = s.features
        if f.overdue <= 0:
            continue
        weighted = sum(f.ageing.get(b, 0.0) * u for b, u in c["bucket_urgency"].items())
        risk_multiplier = 1 + (100 - s.composite_score) / 100
        s.collection_priority_score = round(weighted * risk_multiplier, 2)
        s.collection_tier = _tier(s, c["min_balance"])
        action = TIER_ACTIONS[s.collection_tier]
        if f.disputed_amount > 0:
            action += f"; resolve dispute ({f.disputed_amount:,.0f})"
        s.collection_action = action
        worklist.append(s)

    worklist.sort(key=lambda s: (s.collection_tier, -s.collection_priority_score))
    for rank, s in enumerate(worklist, start=1):
        s.collection_rank = rank
    return worklist

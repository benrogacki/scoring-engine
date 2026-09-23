"""Core data structures for the debtor ledger and scoring outputs."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Optional

SETTLED_TOLERANCE = 0.01


@dataclass
class Invoice:
    invoice_id: str
    customer_id: str
    invoice_date: date
    due_date: date
    amount: float
    amount_paid: float = 0.0
    paid_date: Optional[date] = None
    disputed: bool = False

    @property
    def outstanding(self) -> float:
        return max(0.0, round(self.amount - self.amount_paid, 2))

    @property
    def is_settled(self) -> bool:
        return self.outstanding <= SETTLED_TOLERANCE

    def days_overdue(self, as_of: date) -> int:
        """Days past due for an open invoice as at ``as_of`` (0 if not yet due)."""
        return max(0, (as_of - self.due_date).days)

    def days_late_paid(self) -> Optional[int]:
        """Days paid after due date for a settled invoice (negative = early)."""
        if self.paid_date is None:
            return None
        return (self.paid_date - self.due_date).days


@dataclass
class Customer:
    customer_id: str
    name: str
    credit_limit: float = 0.0
    payment_terms_days: int = 30
    industry: str = ""


@dataclass
class CustomerFeatures:
    """Raw measurements for one customer, before they are turned into scores."""

    customer_id: str
    # Payment history
    paid_invoice_count: int = 0
    weighted_avg_days_late: Optional[float] = None
    on_time_rate: Optional[float] = None
    recent_days_late: Optional[float] = None
    prior_days_late: Optional[float] = None
    # Ageing (open balances)
    outstanding: float = 0.0
    ageing: Dict[str, float] = field(default_factory=dict)
    overdue: float = 0.0
    oldest_days_overdue: int = 0
    disputed_amount: float = 0.0
    # Concentration / exposure
    share_of_portfolio: float = 0.0
    credit_limit: float = 0.0
    limit_utilisation: Optional[float] = None
    # Trading volume
    sales_lookback: float = 0.0
    months_observed: float = 0.0

    @property
    def dpd_trend(self) -> Optional[float]:
        """Positive = paying later recently than before (deteriorating)."""
        if self.recent_days_late is None or self.prior_days_late is None:
            return None
        return self.recent_days_late - self.prior_days_late

    @property
    def avg_monthly_sales(self) -> float:
        if self.months_observed <= 0:
            return 0.0
        return self.sales_lookback / self.months_observed


@dataclass
class CustomerScore:
    customer: Customer
    features: CustomerFeatures
    payment_score: float
    ageing_score: float
    concentration_score: float
    composite_score: float
    grade: str
    reasons: List[str] = field(default_factory=list)
    # Credit limit recommendation
    recommended_limit: float = 0.0
    limit_action: str = ""
    # Collection priority
    collection_priority_score: float = 0.0
    collection_tier: str = ""
    collection_action: str = ""
    collection_rank: Optional[int] = None

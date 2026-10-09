"""Pydantic models for clients, their records and the engine's audit objects.

Money fields are held as integer pence. In input files (JSON profiles, CSVs) they are written in
pounds, e.g. ``"opening_reserves": 15000`` or ``"12,570.00"``.
"""
from __future__ import annotations

from datetime import date
from typing import Annotated, Any, Dict, List, Literal, Optional

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, model_validator

from .money import to_pence


def _pence(v: Any) -> int:
    if isinstance(v, int) and not isinstance(v, bool):
        return v * 100
    return to_pence(v)


def _opt_pence(v: Any) -> Optional[int]:
    if v is None or (isinstance(v, str) and not v.strip()):
        return None
    return _pence(v)


Pence = Annotated[int, BeforeValidator(_pence)]
OptPence = Annotated[Optional[int], BeforeValidator(_opt_pence)]
Region = Literal["england", "scotland", "wales", "northern_ireland"]
EntityType = Literal["company", "sole_trader"]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --------------------------------------------------------------------------- client profile
class Period(Strict):
    start: date
    end: date

    @model_validator(mode="after")
    def _order(self) -> "Period":
        if self.end < self.start:
            raise ValueError(f"period ends {self.end} before it starts {self.start}")
        return self

    @property
    def days(self) -> int:
        return (self.end - self.start).days + 1


class Person(Strict):
    """A director and/or shareholder of a company."""
    id: str
    name: str
    is_director: bool = True
    shares: int = 0
    share_class: str = "ordinary"
    region: Region = "england"
    other_income: Pence = 0
    salary: Pence = 0                      # current annual salary
    employer_pension: Pence = 0            # current annual employer contribution
    works_in_business: bool = True
    connected_to: Optional[str] = None     # e.g. spouse of another person id
    dividend_waived: bool = False


class VatProfile(Strict):
    registered: bool = False
    registration_date: Optional[date] = None
    scheme: Literal["standard", "flat_rate", "cash", "annual"] = "standard"
    frs_sector: Optional[str] = None
    frs_first_year: bool = False
    stagger: Literal["1", "2", "3", "monthly"] = "1"   # stagger 1: quarters ending Mar/Jun/Sep/Dec
    exempt_supplies: bool = False
    expected_next_30_days: OptPence = None
    expected_next_12_months: OptPence = None


class Payroll(Strict):
    operates: bool = False
    other_employees_above_st: int = 0
    other_employer_nic: Pence = 0


class Contract(Strict):
    """An engagement relevant to IR35 / the off-payroll rules."""
    end_client: str
    client_size: Literal["small", "medium_large", "unknown"] = "unknown"
    sds: Literal["inside", "outside", "none"] = "none"
    via_agency: bool = False
    share_of_income_pct: int = 100


class PoolsBF(Strict):
    main: Pence = 0
    special: Pence = 0


class BuildingBF(Strict):
    id: str
    description: str
    qualifying_cost: Pence
    brought_into_use: date


class SoleTraderInfo(Strict):
    trading_start: Optional[date] = None
    other_income: Pence = 0
    prior_year_liability: OptPence = None      # IT + Class 4 for the previous tax year (drives POAs)
    poas_paid_for_year: Pence = 0              # POAs already paid towards the year being computed
    tax_deducted_at_source: Pence = 0
    turnover_by_tax_year: Dict[str, Pence] = Field(default_factory=dict)   # MTD qualifying income
    property_income_by_tax_year: Dict[str, Pence] = Field(default_factory=dict)
    mtd_software: bool = False
    trading_status: Literal["trade", "uncertain"] = "trade"
    overlap_profit: OptPence = None
    accounting_basis: Literal["accruals", "cash"] = "accruals"


class Client(Strict):
    id: str
    name: str
    entity_type: EntityType
    package: Literal["xero", "quickbooks", "freeagent"]
    region: Region = "england"
    periods: List[Period]
    synthetic: bool = True
    incorporated: Optional[date] = None
    company_number: Optional[str] = None
    confirmation_statement_date: Optional[date] = None
    first_accounts: bool = False
    associated_companies: Optional[int] = None
    associated_basis: Optional[Literal["control", "uncertain"]] = None
    aia_shared_with_related: Optional[bool] = None
    people: List[Person] = Field(default_factory=list)
    vat: VatProfile = Field(default_factory=VatProfile)
    payroll: Payroll = Field(default_factory=Payroll)
    contracts: List[Contract] = Field(default_factory=list)
    opening_reserves: Pence = 0
    losses_bf: Pence = 0
    pools_bf: PoolsBF = Field(default_factory=PoolsBF)
    buildings_bf: List[BuildingBF] = Field(default_factory=list)
    exempt_distributions: Pence = 0
    sole_trader: Optional[SoleTraderInfo] = None
    dla_account_code: Optional[str] = None
    notes: str = ""

    @model_validator(mode="after")
    def _shape(self) -> "Client":
        if not self.periods:
            raise ValueError("at least one accounting period is required")
        if self.entity_type == "sole_trader" and self.sole_trader is None:
            self.sole_trader = SoleTraderInfo()
        return self

    @property
    def period(self) -> Period:
        """The accounting period under computation (the latest one)."""
        return self.periods[-1]

    @property
    def directors(self) -> List[Person]:
        return [p for p in self.people if p.is_director]


# --------------------------------------------------------------------------- records
class Transaction(Strict):
    id: str
    date: date
    code: str
    account: str = ""
    description: str = ""
    contact: str = ""
    net: int                      # pence, natural sign for the category (income +, expense +)
    vat: int = 0                  # pence
    category: str = "uncategorised"
    side: Literal["income", "expense", "asset", "liability", "equity"] = "expense"
    facts: Dict[str, Any] = Field(default_factory=dict)
    source: str = ""              # file:row


class Asset(Strict):
    id: str
    description: str
    date_acquired: date
    cost: Pence
    asset_class: Literal["plant", "car", "integral_feature", "long_life", "building", "land", "computer", "van"]
    new_unused: Optional[bool] = None
    co2_gkm: Optional[int] = None
    private_use_pct: int = 0
    brought_into_use: Optional[date] = None
    qualifying_cost: OptPence = None
    disposal_date: Optional[date] = None
    disposal_proceeds: OptPence = None
    pool_bf: bool = False                 # already in a pool brought forward (for disposals)
    claimed_fe: bool = False              # full expensing / 50% FYA claimed when acquired (s45U)
    txn_ref: str = ""


class DLAEntry(Strict):
    date: date
    person_id: str
    description: str = ""
    amount: int                           # pence; + = advanced to the participator, - = repaid/credited
    method: Literal["bank", "dividend", "salary", "bonus", "expenses", "interest", "other"] = "bank"


class VatReturn(Strict):
    period_start: date
    period_end: date
    box1: int
    box4: int
    box6: int = 0
    box7: int = 0


class TBLine(Strict):
    code: str
    name: str = ""
    debit: int = 0
    credit: int = 0


class ClientData(BaseModel):
    """Everything ingested for one client."""
    model_config = ConfigDict(arbitrary_types_allowed=True)
    client: Client
    transactions: List[Transaction] = Field(default_factory=list)
    assets: List[Asset] = Field(default_factory=list)
    dla: List[DLAEntry] = Field(default_factory=list)
    vat_returns: List[VatReturn] = Field(default_factory=list)
    trial_balance: List[TBLine] = Field(default_factory=list)
    unmapped: List[Dict[str, Any]] = Field(default_factory=list)
    source_dir: str = ""


# --------------------------------------------------------------------------- audit objects
class ParamUse(BaseModel):
    key: str
    year: str
    value: Any
    verified: bool
    source_url: str
    authority: str


class Treatment(BaseModel):
    """How one transaction was treated, and why."""
    txn_id: str
    date: date
    description: str
    category: str
    amount: int
    vat: int
    ct: str                       # allow | disallow | capital | partial | n/a
    allowable: int                # pence allowed in the tax computation (or capital amount)
    disallowed: int
    vat_treatment: str            # recover | blocked | partial | none | output_tax | not_registered | n/a
    vat_recoverable: int
    rules: List[str]
    authority: List[str]
    params: List[ParamUse] = Field(default_factory=list)
    review_id: Optional[str] = None
    provisional: bool = False
    decision: Optional[Dict[str, Any]] = None
    note: str = ""


class ReviewItem(BaseModel):
    id: str
    client_id: str
    kind: Literal["judgment", "fact", "anti_avoidance"]
    rule_id: str
    title: str
    question: str
    factors: List[str] = Field(default_factory=list)
    authorities: List[str] = Field(default_factory=list)
    authority: List[str] = Field(default_factory=list)
    guidance: List[str] = Field(default_factory=list)
    proposed: Dict[str, Any] = Field(default_factory=dict)
    reasoning: str = ""
    amount: int = 0
    txn_ids: List[str] = Field(default_factory=list)
    status: Literal["open", "decided"] = "open"
    decision: Optional[Dict[str, Any]] = None
    impact: str = ""


class Line(BaseModel):
    """A line in a tax computation with its audit trail."""
    key: str
    label: str
    amount: int
    kind: Literal["line", "subtotal", "total", "note"] = "line"
    rules: List[str] = Field(default_factory=list)
    authority: List[str] = Field(default_factory=list)
    params: List[ParamUse] = Field(default_factory=list)
    txn_ids: List[str] = Field(default_factory=list)
    review_ids: List[str] = Field(default_factory=list)
    detail: List[str] = Field(default_factory=list)
    provisional: bool = False

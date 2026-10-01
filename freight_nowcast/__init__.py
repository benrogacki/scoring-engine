"""Freight nowcaster: real-economy momentum from published freight series.

Reads external macro data (Destatis truck toll mileage, OECD AIS port activity,
Baltic Dry, optional aisstream.io port counts) and turns it into a composite
activity index with per-geography z-scores, cycle phases and turning-point flags.
Every signal is validated against the official statistic it is meant to lead.

It is independent of ``scoring_engine``: it shares no data model with the debtor
ledger and only emits ``capstone_feed.json`` for the capstone's Tier 1 / Tier 2.
"""
__version__ = "0.1.0"

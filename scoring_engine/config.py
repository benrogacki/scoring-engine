"""Scoring configuration: weights, thresholds and policy rules.

All values can be overridden with a JSON file (see ``config/default.json``).
Only the keys you supply are replaced; everything else keeps its default.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Dict, Optional

DEFAULT_CONFIG: Dict[str, Any] = {
    "lookback_months": 12,
    "recent_window_months": 3,
    "grace_days": 5,
    "weights": {"payment": 0.45, "ageing": 0.35, "concentration": 0.20},
    "payment_history": {
        # Weighted-average days late at which the lateness component hits zero.
        "days_late_floor": 45,
        "on_time_weight": 0.4,
        # Deterioration penalty: max points deducted, reached at this many extra days late.
        "trend_max_penalty": 15,
        "trend_full_penalty_days": 30,
        # Score used when a customer has no settled invoices in the lookback ("thin file").
        "thin_file_score": 55,
        "min_invoices_for_full_confidence": 3,
    },
    "ageing": {
        # Severity weight per bucket (0 = no risk, 1 = maximum risk).
        "bucket_weights": {"current": 0.0, "1_30": 0.2, "31_60": 0.5, "61_90": 0.8, "90_plus": 1.0},
        "disputed_penalty": 10,
    },
    "concentration": {
        # Share of total AR at which the portfolio-share component hits zero.
        "max_portfolio_share": 0.15,
        # Utilisation of credit limit: full marks up to "comfortable", zero at "breach".
        "utilisation_comfortable": 0.75,
        "utilisation_breach": 1.25,
    },
    "grades": [
        {"grade": "A", "min_score": 80, "label": "Low risk"},
        {"grade": "B", "min_score": 65, "label": "Moderate risk"},
        {"grade": "C", "min_score": 50, "label": "Elevated risk"},
        {"grade": "D", "min_score": 35, "label": "High risk"},
        {"grade": "E", "min_score": 0, "label": "Severe risk"},
    ],
    # Hard policy overrides applied after the weighted score.
    "overrides": {
        "severe_arrears_share": 0.25,  # 90+ share of balance at/above this -> cap grade
        "severe_arrears_cap": "D",
        "any_90_plus_cap": "C",  # any material 90+ balance -> cap grade
        "limit_breach_utilisation": 1.2,
        "limit_breach_cap": "C",
        "materiality": 500,
    },
    "credit_limits": {
        # Limit = avg monthly sales x (terms + buffer) / 30 x grade multiplier.
        "buffer_days": 15,
        "grade_multipliers": {"A": 1.5, "B": 1.25, "C": 1.0, "D": 0.6, "E": 0.0},
        "max_increase_pct": 0.5,
        # Grades that may receive a higher limit; others are held at or below current.
        "increase_allowed_grades": ["A", "B"],
        # No increases for customers already at/above the concentration threshold.
        "block_increase_at_portfolio_share": 0.15,
        "rounding": 1000,
        "tolerance_pct": 0.10,
    },
    # Data health checks on every extract.
    "health": {
        "stale_days": 10,
        "max_missing_paid_date_share": 0.05,
        "control_total_tolerance_pct": 0.005,
    },
    # Backtest: re-score at past dates and check who went on to pay badly.
    "backtest": {
        "horizon_days": 90,
        "bad_days_past_due": 60,
        "points": 4,
        "step_days": 30,
        "min_history_days": 180,
        "min_observations": 30,
        "min_bads": 5,
        "min_grade_observations": 5,
        # Neighbouring grades may reverse by this much (sampling noise) and still count as monotonic.
        "monotonic_tolerance": 0.05,
        "auc_evidenced": 0.70,
        "auc_weak": 0.60,
    },
    "collections": {
        # Urgency multiplier applied to overdue value in each bucket.
        "bucket_urgency": {"1_30": 1.0, "31_60": 1.5, "61_90": 2.5, "90_plus": 4.0},
        "min_balance": 250,
    },
}

GRADE_ORDER = ["A", "B", "C", "D", "E"]
AGEING_BUCKETS = ["current", "1_30", "31_60", "61_90", "90_plus"]


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    result = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def load_config(path: Optional[Path] = None, overrides: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Defaults, then a JSON file, then in-memory overrides (e.g. from a job parameter)."""
    config = copy.deepcopy(DEFAULT_CONFIG)
    if path is not None:
        with open(path, encoding="utf-8") as fh:
            config = _deep_merge(config, json.load(fh))
    if overrides:
        config = _deep_merge(config, overrides)
    validate_config(config)
    return config


def validate_config(config: Dict[str, Any]) -> None:
    weights = config["weights"]
    total = sum(weights.values())
    if abs(total - 1.0) > 1e-6:
        raise ValueError(f"weights must sum to 1.0 (got {total:.3f})")
    grades = [g["grade"] for g in config["grades"]]
    if sorted(grades) != sorted(GRADE_ORDER):
        raise ValueError(f"grades must define exactly {GRADE_ORDER}")
    mins = [g["min_score"] for g in config["grades"]]
    if mins != sorted(mins, reverse=True):
        raise ValueError("grades must be listed best-first with descending min_score")

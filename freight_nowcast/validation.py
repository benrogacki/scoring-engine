"""Evidence for each signal: does the freight series actually track the statistic it claims to lead?

For every ``indicator -> target`` pair in the catalog (toll mileage -> manufacturing
production, port calls -> trade volumes) the validator reports:

1. **Lead/lag profile**: correlation of the indicator ``L`` months earlier with the
   target, for ``L = -max_lag .. +max_lag``.
2. **In-sample fit**: ``target_t = a + b * indicator_t`` with Newey-West (HAC) errors.
3. **Pseudo real-time test**: expanding-window forecasts of ``target_t`` from
   ``target_{t-1}`` plus ``indicator_t`` versus ``target_{t-1}`` alone, scored by
   RMSE ratio, a Diebold-Mariano test and the direction hit rate.
4. **Timing**: how many days earlier the indicator is published than the target.

The verdict is ``evidenced`` only when the in-sample link is significant with the
expected sign *and* the indicator improves out-of-sample nowcasts.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Mapping, Optional

from .series import Monthly, add_months, month_str, transform
from .stats import corr, diebold_mariano, norm_cdf, ols, rmse


@dataclass
class PairResult:
    indicator: str
    target: str
    transform: str
    n: int
    first: str = ""
    last: str = ""
    lead_profile: Dict[int, float] = field(default_factory=dict)
    best_lead: Optional[int] = None
    best_corr: float = float("nan")
    beta: float = float("nan")
    beta_t: float = float("nan")
    beta_p: float = float("nan")
    r2: float = float("nan")
    oos_n: int = 0
    rmse_model: float = float("nan")
    rmse_benchmark: float = float("nan")
    rmse_ratio: float = float("nan")
    dm_stat: float = float("nan")
    dm_p: float = float("nan")
    hit_rate: float = float("nan")
    timing_advantage_days: Optional[int] = None
    verdict: str = "insufficient data"
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        for k, v in d.items():
            if isinstance(v, float) and math.isnan(v):
                d[k] = None
            elif isinstance(v, float):
                d[k] = round(v, 4)
        d["lead_profile"] = {str(k): (None if math.isnan(v) else round(v, 3)) for k, v in self.lead_profile.items()}
        return d


def _lead_profile(x: Monthly, y: Monthly, max_lag: int) -> Dict[int, float]:
    out = {}
    for lag in range(-max_lag, max_lag + 1):
        pairs = [(x[add_months(m, -lag)], y[m]) for m in y if add_months(m, -lag) in x]
        out[lag] = corr([p[0] for p in pairs], [p[1] for p in pairs]) if len(pairs) >= 12 else float("nan")
    return out


def validate_pair(indicator: Monthly, target: Monthly, how: str = "mom", max_lag: int = 3,
                  min_obs: int = 36, min_train: int = 36, expected_sign: int = 1,
                  indicator_id: str = "indicator", target_id: str = "target",
                  timing_advantage_days: Optional[int] = None) -> PairResult:
    x, y = transform(indicator, how), transform(target, how)
    common = sorted(set(x) & set(y))
    res = PairResult(indicator_id, target_id, how, len(common), timing_advantage_days=timing_advantage_days)
    if len(common) < min_obs:
        res.notes.append(f"only {len(common)} overlapping months (need {min_obs})")
        return res
    res.first, res.last = month_str(common[0]), month_str(common[-1])

    res.lead_profile = _lead_profile(x, y, max_lag)
    leads = {k: v for k, v in res.lead_profile.items() if k >= 0 and not math.isnan(v)}
    if leads:
        res.best_lead = max(leads, key=lambda k: expected_sign * leads[k])
        res.best_corr = leads[res.best_lead]

    fit = ols([y[m] for m in common], [[x[m]] for m in common])
    res.beta, res.beta_t, res.beta_p, res.r2 = fit.coef[1], fit.t[1], fit.p[1], fit.r2

    # pseudo real-time: at month t we know indicator_t and target_{t-1}
    rows = [(m, y[m], y[add_months(m, -1)], x[m]) for m in common if add_months(m, -1) in y]
    e_mod, e_ben, hits = [], [], []
    for i in range(min_train, len(rows)):
        train = rows[:i]
        _, yt, ylag, xt = rows[i]
        try:
            mod = ols([r[1] for r in train], [[r[2], r[3]] for r in train], hac_lags=0)
            ben = ols([r[1] for r in train], [[r[2]] for r in train], hac_lags=0)
        except ValueError:
            continue
        f_mod, f_ben = mod.predict([ylag, xt]), ben.predict([ylag])
        e_mod.append(yt - f_mod)
        e_ben.append(yt - f_ben)
        hits.append((yt - ylag) * (f_mod - ylag) > 0)
    res.oos_n = len(e_mod)
    if res.oos_n >= 12:
        res.rmse_model, res.rmse_benchmark = rmse(e_mod), rmse(e_ben)
        res.rmse_ratio = res.rmse_model / res.rmse_benchmark if res.rmse_benchmark else float("nan")
        res.dm_stat = diebold_mariano(e_mod, e_ben)
        res.dm_p = norm_cdf(res.dm_stat) if not math.isnan(res.dm_stat) else float("nan")  # one-sided
        res.hit_rate = sum(hits) / len(hits)
    else:
        res.notes.append(f"only {res.oos_n} out-of-sample months (need 12)")

    in_sample = res.beta_p < 0.05 and expected_sign * res.beta > 0
    oos = res.rmse_ratio < 1.0 and (res.dm_p < 0.10 if not math.isnan(res.dm_p) else False)
    if in_sample and oos:
        res.verdict = "evidenced"
    elif in_sample or (res.rmse_ratio < 1.0):
        res.verdict = "partial"
        if in_sample and not oos:
            res.notes.append("significant in sample but no reliable out-of-sample gain")
        if not in_sample:
            res.notes.append("out-of-sample gain without a significant in-sample link")
    else:
        res.verdict = "not evidenced"
    if expected_sign * res.beta < 0:
        res.notes.append("coefficient has the wrong sign")
    return res


def run_validation(pairs: List[Mapping[str, Any]], monthly: Mapping[str, Monthly],
                   specs: Mapping[str, Mapping[str, Any]]) -> List[PairResult]:
    out = []
    for p in pairs:
        ind, tgt = p["indicator"], p["target"]
        if ind not in specs or tgt not in specs:
            continue  # pair uses a disabled (alternative) source
        if ind not in monthly or tgt not in monthly:
            missing = [s for s in (ind, tgt) if s not in monthly]
            r = PairResult(ind, tgt, p.get("transform", "mom"), 0)
            r.verdict = "not run"
            r.notes.append(f"missing data for {', '.join(missing)}")
            out.append(r)
            continue
        lag_i = specs.get(ind, {}).get("publication_lag_days")
        lag_t = specs.get(tgt, {}).get("publication_lag_days")
        adv = (lag_t - lag_i) if lag_i is not None and lag_t is not None else None
        out.append(validate_pair(monthly[ind], monthly[tgt], p.get("transform", "mom"), p.get("max_lag", 3),
                                 p.get("min_obs", 36), p.get("min_train", 36), p.get("expected_sign", 1),
                                 ind, tgt, adv))
    return out

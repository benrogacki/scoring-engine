"""Small, dependency-free statistics: OLS with Newey-West errors, correlations, tests."""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Optional, Sequence


def norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def two_sided_p(z: float) -> float:
    """Two-sided p-value from the normal approximation (fine for the T > 40 we need)."""
    return 2.0 * (1.0 - norm_cdf(abs(z)))


def corr(xs: Sequence[float], ys: Sequence[float]) -> float:
    n = len(xs)
    if n < 3:
        return float("nan")
    mx, my = sum(xs) / n, sum(ys) / n
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if sxx == 0 or syy == 0:
        return float("nan")
    return sxy / math.sqrt(sxx * syy)


def _solve(a: List[List[float]], b: List[float]) -> List[float]:
    """Gauss-Jordan elimination with partial pivoting (k is tiny)."""
    n = len(b)
    m = [row[:] + [b[i]] for i, row in enumerate(a)]
    for col in range(n):
        piv = max(range(col, n), key=lambda r: abs(m[r][col]))
        if abs(m[piv][col]) < 1e-12:
            raise ValueError("singular design matrix (collinear or constant regressors)")
        m[col], m[piv] = m[piv], m[col]
        p = m[col][col]
        m[col] = [x / p for x in m[col]]
        for r in range(n):
            if r != col and m[r][col] != 0:
                f = m[r][col]
                m[r] = [x - f * y for x, y in zip(m[r], m[col])]
    return [m[i][n] for i in range(n)]


def _inverse(a: List[List[float]]) -> List[List[float]]:
    n = len(a)
    cols = [_solve(a, [1.0 if i == j else 0.0 for i in range(n)]) for j in range(n)]
    return [[cols[j][i] for j in range(n)] for i in range(n)]


def newey_west_lags(n: int) -> int:
    return max(1, int(math.floor(4 * (n / 100.0) ** (2.0 / 9.0))))


@dataclass
class OLSResult:
    coef: List[float]
    se: List[float]          # Newey-West (HAC) standard errors
    t: List[float]
    p: List[float]
    r2: float
    n: int
    resid_sd: float
    hac_lags: int

    def predict(self, x_row: Sequence[float]) -> float:
        return self.coef[0] + sum(c * x for c, x in zip(self.coef[1:], x_row))


def ols(y: Sequence[float], X: Sequence[Sequence[float]], hac_lags: Optional[int] = None) -> OLSResult:
    """OLS of ``y`` on a constant plus the columns of ``X`` (rows = observations).

    Standard errors are Newey-West HAC: overlapping growth rates (yoy, 3m/3m) are
    autocorrelated by construction, and plain OLS errors would overstate the
    evidence.
    """
    n = len(y)
    Z = [[1.0] + list(row) for row in X]
    k = len(Z[0])
    if n <= k + 2:
        raise ValueError(f"need more than {k + 2} observations, have {n}")
    xtx = [[sum(Z[r][i] * Z[r][j] for r in range(n)) for j in range(k)] for i in range(k)]
    xty = [sum(Z[r][i] * y[r] for r in range(n)) for i in range(k)]
    beta = _solve(xtx, xty)
    resid = [y[r] - sum(beta[i] * Z[r][i] for i in range(k)) for r in range(n)]
    my = sum(y) / n
    sst = sum((v - my) ** 2 for v in y)
    sse = sum(e * e for e in resid)
    r2 = 1 - sse / sst if sst else float("nan")

    L = newey_west_lags(n) if hac_lags is None else hac_lags
    S = [[0.0] * k for _ in range(k)]
    for lag in range(L + 1):
        w = 1.0 if lag == 0 else 1.0 - lag / (L + 1.0)
        for t in range(lag, n):
            e2 = resid[t] * resid[t - lag]
            for i in range(k):
                zi_t, zi_l = Z[t][i], Z[t - lag][i]
                for j in range(k):
                    v = zi_t * Z[t - lag][j] * e2
                    if lag:
                        v += zi_l * Z[t][j] * e2
                    S[i][j] += w * v
    inv = _inverse(xtx)
    cov = [[sum(inv[i][a] * S[a][b] * inv[b][j] for a in range(k) for b in range(k)) for j in range(k)] for i in range(k)]
    cov = [[c * n / (n - k) for c in row] for row in cov]  # small-sample scaling
    se = [math.sqrt(max(cov[i][i], 0.0)) for i in range(k)]
    t = [b / s if s else float("nan") for b, s in zip(beta, se)]
    return OLSResult(beta, se, t, [two_sided_p(x) for x in t], r2, n,
                     math.sqrt(sse / (n - k)), L)


def diebold_mariano(e_model: Sequence[float], e_bench: Sequence[float]) -> float:
    """DM statistic on squared-error loss; negative = model beats benchmark.

    Long-run variance uses Newey-West weights; compare with N(0,1).
    """
    d = [a * a - b * b for a, b in zip(e_model, e_bench)]
    n = len(d)
    if n < 8:
        return float("nan")
    md = sum(d) / n
    L = newey_west_lags(n)
    gamma0 = sum((x - md) ** 2 for x in d) / n
    lrv = gamma0
    for lag in range(1, L + 1):
        g = sum((d[t] - md) * (d[t - lag] - md) for t in range(lag, n)) / n
        lrv += 2 * (1 - lag / (L + 1.0)) * g
    if lrv <= 0:
        return float("nan")
    return md / math.sqrt(lrv / n)


def rmse(errors: Sequence[float]) -> float:
    return math.sqrt(sum(e * e for e in errors) / len(errors)) if errors else float("nan")

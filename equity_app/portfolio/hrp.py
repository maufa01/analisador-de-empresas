"""
Hierarchical Risk Parity (López de Prado, 2016).

Three-step algorithm:
    1. Tree clustering on the correlation distance matrix.
    2. Quasi-diagonalisation of the covariance matrix using the
       cluster ordering.
    3. Recursive bisection — split the ordered cluster in two and
       allocate inversely proportional to each side's variance.

The result is a weight vector that respects the asset-correlation
structure without ever inverting the covariance matrix — much more
robust than mean-variance when N approaches T or when the cov is
ill-conditioned.

Pure SciPy + NumPy + Pandas. No external HRP libraries required.
"""
from __future__ import annotations
from typing import Optional

import numpy as np
import pandas as pd

from core.constants import PORTFOLIO_DEFAULTS


# ============================================================
# Internals
# ============================================================
def _correlation_distance(corr: np.ndarray) -> np.ndarray:
    """López de Prado's correlation distance: sqrt((1 - corr) / 2)."""
    return np.sqrt(np.clip((1.0 - corr) / 2.0, 0.0, 1.0))


def _quasi_diag(linkage: np.ndarray) -> list[int]:
    """
    Reorder leaves so correlated assets sit next to each other on the
    diagonal. ``linkage`` is the SciPy single-linkage matrix.
    """
    link = linkage.astype(int)
    sort_ix = pd.Series([link[-1, 0], link[-1, 1]])
    n_items = link[-1, 3]
    while sort_ix.max() >= n_items:
        sort_ix.index = range(0, sort_ix.shape[0] * 2, 2)
        df0 = sort_ix[sort_ix >= n_items]
        i = df0.index
        j = df0.values - n_items
        sort_ix[i] = link[j, 0]
        df1 = pd.Series(link[j, 1], index=i + 1)
        sort_ix = pd.concat([sort_ix, df1]).sort_index()
        sort_ix.index = range(sort_ix.shape[0])
    return sort_ix.tolist()


def _ivp(cov_slice: np.ndarray) -> np.ndarray:
    """Inverse-variance allocation across a cluster."""
    ivp = 1.0 / np.diag(cov_slice)
    ivp /= ivp.sum()
    return ivp


def _cluster_var(cov: np.ndarray, items: list[int]) -> float:
    """Variance of the inverse-variance allocation for a sub-cluster."""
    sub = cov[np.ix_(items, items)]
    w = _ivp(sub).reshape(-1, 1)
    return float((w.T @ sub @ w).item())


def _recursive_bisection(cov: np.ndarray, sort_ix: list[int]) -> pd.Series:
    """Top-down recursive bisection — the weight-allocation step."""
    weights = pd.Series(1.0, index=sort_ix)
    clusters: list[list[int]] = [list(sort_ix)]
    while clusters:
        new_clusters: list[list[int]] = []
        for cluster in clusters:
            if len(cluster) <= 1:
                continue
            # Bisect into two equal halves
            half = len(cluster) // 2
            left, right = cluster[:half], cluster[half:]
            v_left = _cluster_var(cov, left)
            v_right = _cluster_var(cov, right)
            alpha = 1.0 - v_left / (v_left + v_right) if (v_left + v_right) > 0 else 0.5
            for asset in left:
                weights[asset] *= alpha
            for asset in right:
                weights[asset] *= 1.0 - alpha
            new_clusters.extend([left, right])
        clusters = new_clusters
    return weights


# ============================================================
# Public API
# ============================================================
def hrp_weights(
    returns: pd.DataFrame,
    *,
    cov: Optional[pd.DataFrame] = None,
) -> pd.Series:
    """
    Compute HRP weights from a periodic returns DataFrame.

    Args:
        returns: rows = periods, columns = assets.
        cov:     optional pre-computed covariance. Defaults to the
                 *sample* covariance (HRP is robust enough to not need
                 shrinkage; pass a Ledoit-Wolf cov if you want it anyway).
    """
    try:
        from scipy.cluster.hierarchy import linkage           # type: ignore
        from scipy.spatial.distance import squareform         # type: ignore
    except ImportError as exc:
        raise ImportError(
            "HRP requires scipy. Install with `pip install scipy`."
        ) from exc

    cleaned = returns.dropna(how="any")
    if cleaned.shape[0] < 2:
        raise ValueError("Need at least 2 return observations")

    cols = list(cleaned.columns)
    if cov is None:
        cov_df = cleaned.cov()
    else:
        cov_df = cov.reindex(index=cols, columns=cols)
    corr_df = cleaned.corr()

    dist = _correlation_distance(corr_df.values)
    np.fill_diagonal(dist, 0.0)
    condensed = squareform(dist, checks=False)
    link_mat = linkage(condensed, method="single")

    sort_ix = _quasi_diag(link_mat)
    weights = _recursive_bisection(cov_df.values, sort_ix)
    weights.index = [cols[i] for i in weights.index]
    return weights.reindex(cols).fillna(0.0)

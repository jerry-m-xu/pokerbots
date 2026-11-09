"""Preflop lookups: hand percentile and equity versus top-X% ranges.

Every opponent range is modelled as "the top X% of hands" by equity against a
random hand, with X read off that seat's observed frequencies. The tables in
preflop_data.py are generated offline by tools/build_preflop.py.
"""
from bisect import bisect_left

from .preflop_data import EQ, EQM, PCT, XGRID

_LAST = len(XGRID) - 1


def pct(cls):
    """0.0 = best starting hand, 1.0 = worst (share of combos stronger)."""
    return PCT[cls]


def eq_vs_range(cls, x):
    """All-in preflop equity of hand class `cls` against the top-x share of hands."""
    row = EQ[cls]
    if x <= XGRID[0]:
        return row[0] * 0.001
    if x >= XGRID[_LAST]:
        return row[_LAST] * 0.001
    i = bisect_left(XGRID, x)
    x0 = XGRID[i - 1]
    t = (x - x0) / (XGRID[i] - x0)
    return (row[i - 1] + t * (row[i] - row[i - 1])) * 0.001


def eq_vs_random(cls, n_opp):
    """Equity share against n random opponents (1..7)."""
    n = 1 if n_opp < 1 else (7 if n_opp > 7 else n_opp)
    return EQM[cls][n - 1] * 0.001

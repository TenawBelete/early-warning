"""Learn the three global settings across cases, and test them honestly.

The signal-by-signal likelihood ratios stay as written. Only three shared
knobs are fitted, on Brier score. "Leave one case out" fits them on every
case except one and scores the held-out case, so each reported out-of-sample
score comes from settings that never saw that case.

With two cases this is a very small test. It shows the method; it does not
establish the values.
"""
from __future__ import annotations

from itertools import product

from .cases import Case, backtest
from .engine import Settings, V0

GRID = [Settings(sc, rd, hl)
        for sc, rd, hl in product((0.5, 0.75, 1.0, 1.25, 1.5, 2.0), (0.5, 0.6, 0.7, 0.8, 0.9), (0.5, 1.0, 2.0))]


def backtest_questions(case: Case) -> list[str]:
    return [q["id"] for q in case.spec["questions"] if q["kind"] == "backtest"]


def case_brier(case: Case, s: Settings) -> float:
    qs = backtest_questions(case)
    return sum(backtest(case, q, s)["brier"] for q in qs) / len(qs)


def fit(cases: list[Case]) -> tuple[Settings, float]:
    """Settings with the lowest average Brier across the given cases."""
    best, best_score = V0, float("inf")
    for s in GRID:
        score = sum(case_brier(c, s) for c in cases) / len(cases)
        if score < best_score - 1e-12:
            best, best_score = s, score
    return best, best_score


def leave_one_out(cases: list[Case]) -> list[dict]:
    out = []
    for held in cases:
        train = [c for c in cases if c is not held]
        s, train_score = fit(train)
        out.append({
            "held_out": held.key, "fitted_on": [c.key for c in train], "settings": s,
            "train_brier": train_score,
            "held_out_brier_v0": case_brier(held, V0),
            "held_out_brier_fitted": case_brier(held, s),
        })
    return out

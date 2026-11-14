"""Source credibility: how much a report counts, by outlet, and how well a claim is corroborated.

The list lives in configs/sources.json so it can be read and edited without touching code.
It is an analyst's starting point, not a measurement.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

CONFIG = Path(__file__).resolve().parents[1] / "configs" / "sources.json"


@lru_cache(maxsize=1)
def _table():
    cfg = json.loads(CONFIG.read_text())
    exact, phrases = {}, []
    for tier in ("high", "medium", "low", "satire"):
        for name in cfg[tier]:
            if name.startswith("="):
                exact[name[1:].lower()] = tier
            else:
                phrases.append((name.lower(), tier))
    phrases.sort(key=lambda x: -len(x[0]))  # "times of india" before "the times"
    return cfg["scores"], exact, [(re.compile(r"(?<![a-z0-9])" + re.escape(n) + r"(?![a-z0-9])"), t) for n, t in phrases]


def tier(outlet: str) -> str:
    """'high', 'medium', 'low', 'satire' or 'unknown' for an outlet name or web domain."""
    s = (outlet or "").strip().lower()
    _, exact, phrases = _table()
    if s in exact:
        return exact[s]
    if s.endswith(".gov") or ".gov." in s or s.endswith(".europa.eu"):
        return "high"
    for rx, t in phrases:
        if rx.search(s):
            return t
    return "unknown"


def credibility(outlet: str) -> float:
    return _table()[0][tier(outlet)]


def support(outlets: list[str]) -> tuple[float, str]:
    """Credibility of a claim given every outlet that reported it: (score 0..1, 'High' | 'Medium' | 'Low').

    The best outlet sets the level. Independent confirmation by other good outlets raises it a little;
    a claim carried by a single outlet that is not top tier is marked down.
    """
    creds = sorted({o.strip().lower(): credibility(o) for o in outlets if o}.values(), reverse=True)
    if not creds or creds[0] <= 0:
        return 0.0, "Low"
    score = creds[0]
    good = sum(c >= 0.75 for c in creds)
    if good >= 2:
        score = min(1.0, score + 0.05 * (min(good, 3) - 1))
    if len(creds) == 1 and score < 0.9:
        score *= 0.85
    return round(score, 3), "High" if score >= 0.85 else "Medium" if score >= 0.6 else "Low"

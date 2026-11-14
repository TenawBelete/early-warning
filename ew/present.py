"""How results are worded, rounded and saved."""
from __future__ import annotations

import dataclasses
import json
from datetime import date

from . import live


def show(x: float) -> str:
    """Rounded for display: the engine is not precise enough to justify decimals."""
    if x < 0.01:
        return "under 1%"
    if x > 0.99:
        return "over 99%"
    if x < 0.10 or x > 0.90:
        return f"{round(x * 100)}%"
    return f"{round(x * 20) * 5}%"


def band(x: float) -> str:
    for top, word in ((0.05, "Very unlikely"), (0.25, "Unlikely"), (0.45, "Less likely than not"), (0.55, "Roughly even"),
                      (0.75, "More likely than not"), (0.95, "Likely")):
        if x < top:
            return word
    return "Very likely"


def odds_shift(p: float, factor: float) -> float:
    o = p / (1 - p) * factor
    return o / (1 + o)


def pack(r: dict) -> str:
    """A full result as text, so it can be saved and shown again later without any network call."""
    return json.dumps(r, default=lambda o: o.isoformat() if isinstance(o, date) else dataclasses.asdict(o))


def unpack(text: str) -> dict:
    r = json.loads(text)
    mk = lambda h: live.Headline(h["title"], h["source"], h["link"], date.fromisoformat(h["published"]), h["query"])
    r["as_of"] = date.fromisoformat(r["as_of"])
    r["heads"] = [mk(h) for h in r["heads"]]
    r["sent"] = [mk(h) for h in r["sent"]] if r.get("sent") else None
    for key in ("reading", "reading2"):
        for dv in (r.get(key) or {}).get("developments", []):
            dv["date"] = date.fromisoformat(dv["date"])
    return r


def approx(x: float) -> str:
    """'about 35%', but never 'about under 1%'."""
    t = show(x)
    return t if t[0] in "uo" else "about " + t


def range_text(lo: float, hi: float) -> str:
    a, b = show(min(lo, hi)), show(max(lo, hi))
    return a if a == b else f"{a} to {b}"

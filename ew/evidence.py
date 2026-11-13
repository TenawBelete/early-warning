"""Evidence loading and the point-in-time gate.

The gate is the single most important piece of a backtest: a record may be
used only if it was publicly knowable on or before the as-of date. Records
whose publication date is unknown are never used in a blind run.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path


@dataclass(frozen=True)
class Evidence:
    id: str
    event_date: date
    public_date: date | None  # None = not known to be public before the outcome
    entity: str
    type: str
    summary: str
    source: str
    reliability: float
    note: str = ""


def _d(s: str | None) -> date | None:
    return date.fromisoformat(s) if s else None


def load_evidence(path: str | Path) -> list[Evidence]:
    rows = json.loads(Path(path).read_text())
    out = []
    for r in rows:
        out.append(
            Evidence(
                id=r["id"],
                event_date=_d(r["event_date"]),
                public_date=_d(r.get("public_date")),
                entity=r["entity"],
                type=r["type"],
                summary=r["summary"],
                source=r["source"],
                reliability=float(r["reliability"]),
                note=r.get("note", ""),
            )
        )
    ids = [e.id for e in out]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate evidence ids")
    return out


def visible_as_of(evidence: list[Evidence], as_of: date, leak: bool = False) -> list[Evidence]:
    """Return only what was publicly knowable at the end of `as_of` (UTC day).

    leak=True deliberately breaks the gate (every record becomes visible on
    its event date, even if it was reported much later or never dated). It exists only to measure how much hindsight would
    distort a result, and must never be used for a reported forecast.
    """
    out = []
    for e in evidence:
        # Blind: only the publication date counts. Leak: pretend every event
        # was known the day it happened, however much later it was reported.
        known = e.event_date if leak else e.public_date
        if known is not None and known <= as_of:
            out.append(e)
    return out

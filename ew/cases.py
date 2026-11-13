"""A case = a focal entity, an entity graph, dated evidence and questions."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from .engine import Settings, V0, posterior
from .evidence import Evidence, load_evidence, visible_as_of
from .graph import relevance_from_focus

ROOT = Path(__file__).resolve().parents[1]


@dataclass
class Case:
    key: str
    spec: dict
    catalog: dict
    evidence: list[Evidence]
    relevance: dict[str, tuple[float, int]]

    def question(self, qid: str) -> dict:
        return next(q for q in self.spec["questions"] if q["id"] == qid)


def load_case(key: str) -> Case:
    d = ROOT / "cases" / key
    spec = json.loads((d / "case.json").read_text())
    catalog = json.loads((ROOT / "configs" / spec["catalog"]).read_text())
    ev = load_evidence(d / "evidence.json")
    rel = relevance_from_focus(spec["graph"]["edges"], spec["focus_entity"], spec["graph"]["max_hops"])
    for e in ev:  # fail early on a typo rather than silently ignoring a record
        if e.type not in catalog["types"]:
            raise ValueError(f"{key}: unknown signal type {e.type!r} in record {e.id}")
        if e.entity not in rel:
            raise ValueError(f"{key}: entity {e.entity!r} in record {e.id} is not reachable from the focus")
    return Case(key, spec, catalog, ev, rel)


def list_cases() -> list[str]:
    return sorted(p.name for p in (ROOT / "cases").iterdir() if (p / "case.json").exists())


def answer(case: Case, qid: str, as_of: date, settings: Settings = V0, leak: bool = False):
    """Probabilities for one question using only what was public at the end of `as_of`."""
    vis = visible_as_of(case.evidence, as_of, leak=leak)
    if not leak:  # the gate, asserted on every single forecast
        assert all(e.public_date is not None and e.public_date <= as_of for e in vis)
    probs, detail = posterior(vis, as_of, case.catalog, case.relevance, case.question(qid)["priors"], settings)
    return probs, detail, len(vis)


def neighbours(s: Settings) -> list[Settings]:
    """Nearby plausible settings, used to show how fragile a number is."""
    out = []
    for sc in (s.lr_scale * 0.67, s.lr_scale, s.lr_scale * 1.5):
        for rd in (max(0.3, s.redundancy - 0.1), s.redundancy, min(0.95, s.redundancy + 0.1)):
            for hl in (s.half_life_mult * 0.5, s.half_life_mult, s.half_life_mult * 2):
                out.append(Settings(round(sc, 4), round(rd, 4), round(hl, 4)))
    return out


def answer_with_range(case: Case, qid: str, as_of: date, settings: Settings = V0):
    """Central forecast plus the lowest and highest value across nearby settings."""
    probs, detail, n = answer(case, qid, as_of, settings)
    lo = dict(probs)
    hi = dict(probs)
    for s in neighbours(settings):
        p, _, _ = answer(case, qid, as_of, s)
        for h, v in p.items():
            lo[h] = min(lo[h], v)
            hi[h] = max(hi[h], v)
    return probs, lo, hi, detail, n


def signal_strength(detail_for_h: list[tuple[Evidence, float]]) -> float:
    """Total evidence weight behind a number. Near zero means 'this is just the base rate'."""
    return sum(abs(c) for _, c in detail_for_h)


def backtest(case: Case, qid: str, settings: Settings = V0) -> dict:
    q = case.question(qid)
    h = q["outcome"]["hypothesis"]
    when = date.fromisoformat(q["outcome"]["date"])
    rows = []
    for s in q["as_of_dates"]:
        d = date.fromisoformat(s)
        probs, lo, hi, detail, n = answer_with_range(case, qid, d, settings)
        rows.append({
            "as_of": s, "visible": n, "p": probs[h], "low": lo[h], "high": hi[h],
            "all": probs, "strength": signal_strength(detail[h]),
            "happened": d < when <= d + timedelta(days=q["horizon_days"]),
            "for": [(e, c) for e, c in detail[h] if c > 0][:5],
            "against": [(e, c) for e, c in detail[h] if c < 0][:5],
        })
    outs = [1.0 if r["happened"] else 0.0 for r in rows]
    n = len(rows)
    return {
        "rows": rows,
        "brier": sum((r["p"] - o) ** 2 for r, o in zip(rows, outs)) / n,
        "brier_base_rate": sum((q["priors"][h] - o) ** 2 for o in outs) / n,
        "brier_50": 0.25,
    }

"""Bayesian update over any set of competing hypotheses.

Each visible record shifts each hypothesis by the likelihood ratio of its
signal type, scaled by a weight:

    weight = source reliability
           x relevance of the entity to the focus (graph spreading)
           x freshness: 0.5 ** (age / half-life of the signal family)
           x redundancy: the k-th strongest signal of the same family pointing
             the same way counts redundancy ** k

    log score(h) = log prior(h) + sum_i weight_i * lr_scale * log LR_i(h)

A signal type lists a likelihood ratio only for hypotheses it bears on; all
others get 1.0, so an irrelevant record cannot move a question.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date

from .evidence import Evidence


@dataclass(frozen=True)
class Settings:
    """Global knobs shared by every case. Learned across cases in ew/tune.py."""
    lr_scale: float = 1.0        # multiplies every log likelihood ratio
    redundancy: float = 0.7      # how fast repeated signals lose weight
    half_life_mult: float = 1.0  # stretches or shrinks every freshness half-life

    def label(self) -> str:
        return f"scale {self.lr_scale:g}, redundancy {self.redundancy:g}, half-life x{self.half_life_mult:g}"


V0 = Settings()


def posterior(
    visible: list[Evidence],
    as_of: date,
    catalog: dict,
    relevance: dict[str, tuple[float, int]],
    priors: dict[str, float],
    settings: Settings = V0,
) -> tuple[dict[str, float], dict[str, list[tuple[Evidence, float]]]]:
    """Return (probabilities, per-hypothesis list of (record, weighted log contribution))."""
    types, half = catalog["types"], catalog["half_life_days"]
    scores = {h: math.log(p) for h, p in priors.items()}
    detail: dict[str, list[tuple[Evidence, float]]] = {h: [] for h in priors}
    for h in priors:
        groups: dict[tuple[str, int], list] = {}
        for e in visible:
            t = types[e.type]
            lr = t["lr"].get(h, 1.0)
            if lr == 1.0:
                continue
            rel, _ = relevance.get(e.entity, (0.0, 99))
            ref = e.public_date or e.event_date
            age = max((as_of - ref).days, 0)
            base = e.reliability * rel * 0.5 ** (age / (half[t["family"]] * settings.half_life_mult))
            l = math.log(lr) * settings.lr_scale
            groups.setdefault((t["family"], 1 if l > 0 else -1), []).append((abs(l) * base, l * base, e))
        for members in groups.values():
            members.sort(key=lambda m: -m[0])
            for k, (_, contrib, e) in enumerate(members):
                c = contrib * settings.redundancy ** k
                scores[h] += c
                detail[h].append((e, c))
        detail[h].sort(key=lambda x: -abs(x[1]))
    m = max(scores.values())
    z = sum(math.exp(v - m) for v in scores.values())
    return {h: math.exp(v - m) / z for h, v in scores.items()}, detail

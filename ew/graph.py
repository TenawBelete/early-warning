"""Focus-centred spreading over an entity graph.

The investigation starts at one focal entity. Relevance spreads outward along
weighted links and shrinks with every hop, so connected actors are examined
but can never outweigh the focus itself.
"""
from __future__ import annotations

import heapq


def relevance_from_focus(edges: list[list], focus: str, max_hops: int = 3) -> dict[str, tuple[float, int]]:
    """Return {entity: (relevance, hops)}.

    Relevance is the strongest path from the focus, where a path's strength is
    the product of its link weights (each between 0 and 1). The focus is 1.0.
    """
    adj: dict[str, list[tuple[str, float]]] = {}
    for a, b, w in edges:
        if not 0 < w <= 1:
            raise ValueError(f"edge weight must be in (0, 1]: {a}-{b} {w}")
        adj.setdefault(a, []).append((b, w))
        adj.setdefault(b, []).append((a, w))

    best: dict[str, tuple[float, int]] = {focus: (1.0, 0)}
    heap = [(-1.0, 0, focus)]
    while heap:
        neg, hops, node = heapq.heappop(heap)
        rel = -neg
        if rel < best.get(node, (0.0, 0))[0]:
            continue
        if hops == max_hops:
            continue
        for nxt, w in adj.get(node, []):
            cand = rel * w
            if cand > best.get(nxt, (0.0, 0))[0]:
                best[nxt] = (cand, hops + 1)
                heapq.heappush(heap, (-cand, hops + 1, nxt))
    return best

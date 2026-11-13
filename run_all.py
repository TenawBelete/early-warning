"""Run every case: backtests, the cross-case tuning check, and live forecasts.

Usage:  python run_all.py

Writes results/summary.json and a dated, versioned forecast log for questions
whose answers are not yet known. Earlier logs are never overwritten.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from ew.cases import answer, answer_with_range, backtest, list_cases, load_case
from ew.engine import V0
from ew.tune import backtest_questions, case_brier, fit, leave_one_out

ROOT = Path(__file__).parent
VERSION = "0.2"


def pct(x: float) -> str:
    return f"{x:.1%}"


def main() -> dict:
    cases = [load_case(k) for k in list_cases()]
    out: dict = {"engine_version": VERSION, "default_settings": V0.label(), "cases": {}}

    for c in cases:
        entry: dict = {"name": c.spec["name"], "backtests": {}, "live": []}
        for qid in backtest_questions(c):
            b = backtest(c, qid, V0)
            entry["backtests"][qid] = {
                "question": c.question(qid)["text"],
                "brier": round(b["brier"], 4), "brier_base_rate": round(b["brier_base_rate"], 4), "brier_50": 0.25,
                "rows": [{"as_of": r["as_of"], "visible": r["visible"], "p": round(r["p"], 4), "low": round(r["low"], 4),
                          "high": round(r["high"], 4), "happened": r["happened"], "evidence_weight": round(r["strength"], 3)}
                         for r in b["rows"]],
            }
        for q in c.spec["questions"]:
            if q["kind"] != "live":
                continue
            d = date.fromisoformat(q["logged_on"])
            probs, lo, hi, detail, _ = answer_with_range(c, q["id"], d, V0)
            entry["live"].append({
                "id": q["id"], "question": q["text"], "logged_on": q["logged_on"], "resolve_by": q["resolve_by"],
                "engine_version": VERSION, "settings": V0.label(), "priors": q["priors"],
                "forecast": {h: round(p, 4) for h, p in probs.items()},
                "range": {h: [round(lo[h], 4), round(hi[h], 4)] for h in probs},
                "resolved": None,
            })
        out["cases"][c.key] = entry

    # Cross-case tuning: does fitting the three global settings actually help?
    loo = leave_one_out(cases)
    joint, joint_score = fit(cases)
    out["tuning"] = {
        "v0_average_brier": round(sum(case_brier(c, V0) for c in cases) / len(cases), 4),
        "fitted_on_all_cases": {"settings": joint.label(), "average_brier_in_sample": round(joint_score, 4),
                                "per_case": {c.key: round(case_brier(c, joint), 4) for c in cases}},
        "leave_one_case_out": [{"held_out": r["held_out"], "settings_from_other_cases": r["settings"].label(),
                                "held_out_brier_v0": round(r["held_out_brier_v0"], 4),
                                "held_out_brier_fitted": round(r["held_out_brier_fitted"], 4)} for r in loo],
        "held_out_average_v0": round(sum(r["held_out_brier_v0"] for r in loo) / len(loo), 4),
        "held_out_average_fitted": round(sum(r["held_out_brier_fitted"] for r in loo) / len(loo), 4),
    }
    out["tuning"]["verdict"] = (
        "Fitted settings beat the defaults out of sample; consider adopting them."
        if out["tuning"]["held_out_average_fitted"] < out["tuning"]["held_out_average_v0"]
        else "Fitted settings did NOT beat the defaults out of sample; defaults kept."
    )

    (ROOT / "results").mkdir(exist_ok=True)
    (ROOT / "results" / "summary.json").write_text(json.dumps(out, indent=2))
    live = [f for e in out["cases"].values() for f in e["live"]]
    if live:
        log = ROOT / "results" / f"forecast_log_{live[0]['logged_on']}_v{VERSION}.json"
        if not log.exists():  # a logged forecast is never rewritten
            log.write_text(json.dumps(live, indent=2))
    return out


if __name__ == "__main__":
    r = main()
    for key, e in r["cases"].items():
        print(f"\n== {e['name']} ==")
        for qid, b in e["backtests"].items():
            print(f"{b['question']}\n  Brier {b['brier']} (base rate only {b['brier_base_rate']}, always-50% 0.25)")
            for row in b["rows"]:
                print(f"  {row['as_of']}  {pct(row['p']):>6}  range {pct(row['low']):>6} to {pct(row['high']):>6}  "
                      f"records {row['visible']:>2}  happened {row['happened']}")
        for f in e["live"]:
            print(f"LIVE  {f['question']}  (resolves by {f['resolve_by']})")
            for h, p in f["forecast"].items():
                print(f"      {h:<16} {pct(p):>6}  range {pct(f['range'][h][0])} to {pct(f['range'][h][1])}")
    t = r["tuning"]
    print("\n== Tuning check ==")
    print("Defaults, average Brier:", t["v0_average_brier"])
    print("Fitted on all cases (in sample):", t["fitted_on_all_cases"])
    for row in t["leave_one_case_out"]:
        print("  held out", row)
    print("Held-out average: defaults", t["held_out_average_v0"], "| fitted", t["held_out_average_fitted"])
    print(t["verdict"])

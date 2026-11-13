import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ew.baseline import flag_changes, robust_z  # noqa: E402
from ew.cases import answer, answer_with_range, backtest, load_case  # noqa: E402
from ew.engine import Settings, V0, posterior  # noqa: E402
from ew.evidence import Evidence, visible_as_of  # noqa: E402
from ew.tune import GRID, fit, leave_one_out  # noqa: E402

iran = load_case("iran_2026")
Q = iran.question("next14")
PRI = Q["priors"]


def one(e_list, d, priors=PRI, s=V0):
    return posterior(e_list, d, iran.catalog, iran.relevance, priors, s)[0]


class PointInTime(unittest.TestCase):
    def test_nothing_from_the_future(self):
        for s in Q["as_of_dates"]:
            d = date.fromisoformat(s)
            for e in visible_as_of(iran.evidence, d):
                self.assertIsNotNone(e.public_date)
                self.assertLessEqual(e.public_date, d)

    def test_hidden_records_never_visible(self):
        ids = {e.id for e in visible_as_of(iran.evidence, date(2026, 2, 27))}
        for e in iran.evidence:
            if e.public_date is None:
                self.assertNotIn(e.id, ids)

    def test_no_record_dated_on_or_after_outcome(self):
        onset = date.fromisoformat(Q["outcome"]["date"])
        for e in iran.evidence:
            if e.public_date is not None:
                self.assertLess(e.public_date, onset)


class Engine(unittest.TestCase):
    def test_no_evidence_returns_prior(self):
        p = one([], date(2026, 1, 1))
        for k, v in PRI.items():
            self.assertAlmostEqual(p[k], v, places=9)

    def test_escalation_raises_and_talks_lower_strike(self):
        d = date(2026, 1, 10)
        mk = lambda t: Evidence("x", d, d, "us_president", t, "", "", 1.0)
        up, down = one([mk("embassy_departure")], d), one([mk("breakthrough_claim")], d)
        self.assertGreater(up["strike"], PRI["strike"])
        self.assertLess(down["strike"], PRI["strike"])
        self.assertGreater(down["deal"], PRI["deal"])

    def test_old_and_distant_signals_count_less(self):
        d = date(2026, 2, 1)
        fresh = Evidence("a", d, d, "us_military", "force_surge", "", "", 1.0)
        stale = Evidence("a", date(2025, 11, 1), date(2025, 11, 1), "us_military", "force_surge", "", "", 1.0)
        far = Evidence("a", d, d, "airlines", "force_surge", "", "", 1.0)
        self.assertGreater(one([fresh], d)["strike"], one([stale], d)["strike"])
        self.assertGreater(one([fresh], d)["strike"], one([far], d)["strike"])

    def test_repeats_add_less_each_time(self):
        import math
        d = date(2026, 2, 1)
        mk = lambda i: Evidence(f"r{i}", d, d, "us_military", "force_surge", "", "", 1.0)
        ps = [one([mk(i) for i in range(n)], d)["strike"] for n in (1, 2, 3, 4)]
        lo = [math.log(p / (1 - p)) for p in ps]
        steps = [b - a for a, b in zip(lo, lo[1:])]
        self.assertTrue(steps[0] > steps[1] > steps[2] > 0)

    def test_probabilities_sum_to_one(self):
        p, _, _ = answer(iran, "next14", date(2026, 2, 27))
        self.assertAlmostEqual(sum(p.values()), 1.0, places=9)

    def test_published_numbers_reproduce(self):
        # The figures reported for the first version must not drift silently.
        p, _, _ = answer(iran, "next14", date(2026, 2, 27))
        d, _, _ = answer(iran, "decap", date(2026, 2, 27))
        self.assertAlmostEqual(p["strike"], 0.7832, places=3)
        self.assertAlmostEqual(p["strike"] * d["decap"], 0.0607, places=3)
        self.assertAlmostEqual(backtest(iran, "next14")["brier"], 0.1628, places=3)

    def test_range_contains_the_central_value(self):
        p, lo, hi, _, _ = answer_with_range(iran, "next14", date(2026, 2, 21))
        for h in p:
            self.assertLessEqual(lo[h], p[h])
            self.assertGreaterEqual(hi[h], p[h])

    def test_settings_change_the_answer_in_the_expected_direction(self):
        d = date(2026, 2, 27)
        weak = answer(iran, "next14", d, Settings(0.5, 0.7, 1.0))[0]["strike"]
        strong = answer(iran, "next14", d, Settings(1.5, 0.7, 1.0))[0]["strike"]
        self.assertLess(weak, strong)


class Tuning(unittest.TestCase):
    def test_fit_is_at_least_as_good_as_defaults_in_sample(self):
        nv = load_case("nvidia_2026")
        from ew.tune import case_brier
        s, score = fit([iran, nv])
        self.assertIn(s, GRID)
        self.assertLessEqual(score, (case_brier(iran, V0) + case_brier(nv, V0)) / 2 + 1e-9)

    def test_leave_one_out_never_fits_on_the_held_out_case(self):
        nv = load_case("nvidia_2026")
        for r in leave_one_out([iran, nv]):
            self.assertNotIn(r["held_out"], r["fitted_on"])


class Graph(unittest.TestCase):
    def test_focus_is_one_and_relevance_shrinks(self):
        rel = iran.relevance
        self.assertEqual(rel["iran_leadership"], (1.0, 0))
        self.assertLess(rel["us_military"][0], rel["us_president"][0])
        self.assertLess(rel["airlines"][0], rel["third_countries"][0])
        self.assertTrue(all(0 < v[0] <= 1 for v in rel.values()))


class Baseline(unittest.TestCase):
    def test_spike_is_flagged_and_normal_is_not(self):
        normal = [10, 12, 9, 11, 10, 13, 9, 10, 11, 12] * 4
        self.assertLess(abs(robust_z(normal, 11)), 2)
        self.assertGreater(robust_z(normal, 40), 3)
        self.assertEqual([i for i, _ in flag_changes(normal + [45])], [len(normal)])


if __name__ == "__main__":
    unittest.main()

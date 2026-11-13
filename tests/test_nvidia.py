import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ew.cases import answer, load_case  # noqa: E402
from ew.engine import posterior  # noqa: E402
from ew.evidence import Evidence, visible_as_of  # noqa: E402

nv = load_case("nvidia_2026")


class NvidiaPointInTime(unittest.TestCase):
    def test_eve_of_story_sees_nothing_later(self):
        eve = date(2026, 10, 28)
        vis = visible_as_of(nv.evidence, eve)
        self.assertTrue(all(e.public_date and e.public_date <= eve for e in vis))
        ids = {e.id for e in vis}
        for hidden in ("n18", "n19", "x01"):  # happened earlier, reported later or undated
            self.assertNotIn(hidden, ids)

    def test_late_reported_items_appear_only_after_publication(self):
        self.assertNotIn("n18", {e.id for e in visible_as_of(nv.evidence, date(2026, 11, 7))})
        self.assertIn("n18", {e.id for e in visible_as_of(nv.evidence, date(2026, 11, 8))})

    def test_backtest_evidence_precedes_outcome(self):
        outcome = date.fromisoformat(nv.question("exit")["outcome"]["date"])
        for e in nv.evidence:
            if e.id.startswith("n"):
                self.assertLess(e.public_date, outcome)

    def test_priors_sum_to_one(self):
        for q in nv.spec["questions"]:
            self.assertAlmostEqual(sum(q["priors"].values()), 1.0, places=9)

    def test_engine_did_not_see_it_coming(self):
        # An honest property worth pinning: no public signal the day before.
        p, _, _ = answer(nv, "exit", date(2026, 10, 28))
        self.assertLess(p["exit"], 0.02)


class Posterior(unittest.TestCase):
    def test_irrelevant_record_cannot_move_a_question(self):
        d = date(2026, 11, 12)
        e = Evidence("z", d, d, "huang", "testimony_agreed", "", "", 1.0)
        p, _ = posterior([e], d, nv.catalog, nv.relevance, {"exit": 0.2, "stay": 0.8})
        self.assertAlmostEqual(p["exit"], 0.2, places=9)
        q, _ = posterior([e], d, nv.catalog, nv.relevance, {"testifies": 0.5, "no": 0.5})
        self.assertGreater(q["testifies"], 0.5)


if __name__ == "__main__":
    unittest.main()

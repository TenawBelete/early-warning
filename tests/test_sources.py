import sys
import unittest
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ew import ai, live  # noqa: E402
from ew.sources import credibility, support, tier  # noqa: E402
from test_ai import AS_OF, H, fake  # noqa: E402


class Tiers(unittest.TestCase):
    def test_known_outlets(self):
        for name, want in [("Reuters", "high"), ("The New York Times", "high"), ("BBC News", "high"), ("justice.gov", "high"),
                           ("Yahoo Finance", "medium"), ("Times of India", "medium"), ("TIME", "medium"),
                           ("PR Newswire", "low"), ("RT", "low"), ("New York Post", "low"),
                           ("The Onion", "satire"), ("Smalltown Gazette", "unknown")]:
            self.assertEqual(tier(name), want, name)

    def test_short_names_do_not_match_inside_other_words(self):
        self.assertEqual(tier("Smart Report Daily"), "unknown")   # contains "rt" and "ap" as letters only
        self.assertEqual(tier("The Sunday Paper"), "unknown")     # not "the sun"
        self.assertEqual(tier("Science Daily"), "unknown")        # "science" must match exactly
        self.assertEqual(tier("The Times of India"), "medium")    # not "the times"

    def test_corroboration(self):
        one_unknown = support(["Smalltown Gazette"])
        self.assertEqual(one_unknown[1], "Low")
        self.assertLess(one_unknown[0], credibility("Smalltown Gazette"))
        self.assertEqual(support(["Reuters"])[1], "High")
        self.assertGreater(support(["Reuters", "BBC", "Bloomberg"])[0], support(["Reuters"])[0])
        self.assertEqual(support(["Smalltown Gazette", "Reuters"])[1], "High")   # one good confirmation is enough
        self.assertEqual(support(["The Onion"]), (0.0, "Low"))


class InTheEngine(unittest.TestCase):
    PLAN = {"focus": "Jane Doe", "event": "e", "horizon_days": 30}

    def test_satire_is_dropped_at_collection(self):
        def get(url, timeout=15):
            from test_live import rss
            return rss([("Jane Doe resigns to become a wizard", "The Onion", AS_OF), ("Jane Doe opens plant", "Reuters", AS_OF)])
        heads, _, _ = live.collect("Jane Doe", [], AS_OF, weeks=1, get=get)
        self.assertEqual([h.source for h in heads], ["Reuters"])

    def test_poorly_sourced_claim_is_forced_to_weak(self):
        ai._model_cache.clear()
        hs = [H("Jane Doe to resign, blog claims", 1, "Some Blog"), H("Jane Doe under formal investigation", 2, "Reuters")]
        reply = {"developments": [{"summary": "resign rumour", "direction": "up", "strength": "strong", "headline_ids": [0]},
                                  {"summary": "investigation", "direction": "up", "strength": "strong", "headline_ids": [1]}]}
        reading, sent = ai.read("k", "q", self.PLAN, hs, AS_OF, http=fake(reply))
        self.assertEqual([d["strength"] for d in reading["developments"]], ["weak", "strong"])
        case = ai.build_case("q", "Jane Doe", reading, sent, 0.01)
        rel = {e.summary: e.reliability for e in case.evidence}
        self.assertLess(rel["resign rumour"], rel["investigation"])

    def test_model_is_shown_each_outlets_credibility(self):
        ai._model_cache.clear()
        seen = []
        ai.read("k", "q", self.PLAN, [H("x", 1, "Reuters"), H("y", 1, "PR Newswire")], AS_OF, http=fake({"developments": []}, seen))
        prompt = seen[-1][1]["contents"][0]["parts"][0]["text"]
        self.assertIn("Reuters [high]", prompt)
        self.assertIn("PR Newswire [low]", prompt)


class Understanding(unittest.TestCase):
    def test_restated_question_and_context(self):
        ai._model_cache.clear()
        seen = []
        p = ai.plan("k", "wat about microsft", AS_OF, context="Who will be the next CEO of Nvidia?", http=fake(
            {"kind": "who", "restated": "Who will be the next chief executive of Microsoft?", "focus": "Microsoft CEO"}, seen))
        self.assertEqual(p["restated"], "Who will be the next chief executive of Microsoft?")
        self.assertIn("next CEO of Nvidia", seen[-1][1]["contents"][0]["parts"][0]["text"])

    def test_restated_defaults_to_what_was_typed(self):
        ai._model_cache.clear()
        self.assertEqual(ai.plan("k", "will x resign", AS_OF, http=fake({"focus": "X"}))["restated"], "will x resign")


if __name__ == "__main__":
    unittest.main()

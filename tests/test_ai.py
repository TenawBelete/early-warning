import json
import sys
import unittest
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ew import ai, live  # noqa: E402
from ew.cases import answer_with_range  # noqa: E402

AS_OF = date(2026, 11, 10)
MODELS = {"models": [
    {"name": "models/gemini-3.6-flash", "supportedGenerationMethods": ["generateContent"]},
    {"name": "models/gemini-3.8-flash", "supportedGenerationMethods": ["generateContent"]},
    {"name": "models/gemini-3.9-flash-lite", "supportedGenerationMethods": ["generateContent"]},
    {"name": "models/gemini-4.0-flash-image", "supportedGenerationMethods": ["generateContent"]},
    {"name": "models/gemini-4.0-flash-preview", "supportedGenerationMethods": ["generateContent"]},
    {"name": "models/text-embedding-9", "supportedGenerationMethods": ["embedContent"]}]}


def fake(reply, seen=None):
    def http(url, key, body=None, timeout=60):
        if seen is not None:
            seen.append((url, body))
        if body is None:
            return MODELS
        return {"candidates": [{"content": {"parts": [{"text": reply if isinstance(reply, str) else json.dumps(reply)}]}}]}
    return http


def H(title, days_ago, source="Reuters"):
    return live.Headline(title, source, f"https://example.org/{days_ago}", AS_OF - timedelta(days=days_ago), "focus")


class Model(unittest.TestCase):
    def test_picks_newest_and_skips_special_variants(self):
        self.assertEqual(ai.rank_models(MODELS["models"]), ["gemini-3.8-flash", "gemini-3.9-flash-lite", "gemini-3.6-flash"])

    def test_falls_back_when_first_model_is_refused(self):
        ai._model_cache.clear()

        def http(url, key, body=None, timeout=60):
            if body is None:
                return MODELS
            if "3.8-flash" in url:
                raise ai.AIError("AI service error 429: not on free tier")
            return {"candidates": [{"content": {"parts": [{"text": "{\"ok\": 1}"}]}}]}
        self.assertEqual(ai.ask("k", "p", http=http), {"ok": 1})
        self.assertEqual(ai._model_cache["k"][0], "gemini-3.9-flash-lite")

    def test_diagnose_reports_each_model(self):
        ai._model_cache.clear()

        def http(url, key, body=None, timeout=60):
            if body is None:
                return MODELS
            if "3.8-flash" in url:
                raise ai.AIError("Could not reach the AI service: timed out")
            return {"candidates": [{"content": {"parts": [{"text": "{\"ok\": true}"}]}}]}
        rows = ai.diagnose("k", http=http)
        self.assertEqual([r["Result"] == "works" for r in rows], [False, True, True])
        self.assertEqual(ai._model_cache["k"][0], "gemini-3.9-flash-lite")

    def test_prefers_full_flash_at_same_version(self):
        ms = [{"name": "models/gemini-3.8-flash-lite", "supportedGenerationMethods": ["generateContent"]},
              {"name": "models/gemini-3.8-flash", "supportedGenerationMethods": ["generateContent"]}]
        self.assertEqual(ai.pick_model(ms), "gemini-3.8-flash")

    def test_no_model_is_an_error(self):
        with self.assertRaises(ai.AIError):
            ai.pick_model([])

    def test_unreadable_answer_is_an_error(self):
        ai._model_cache.clear()
        with self.assertRaises(ai.AIError):
            ai.ask("k", "p", http=fake("not json"))


class Plan(unittest.TestCase):
    def test_plan_is_cleaned_and_clamped(self):
        ai._model_cache.clear()
        p = ai.plan("k", "will jane doe stay ceo of acme", AS_OF, http=fake(
            {"focus": "Jane Doe", "related": ["Acme", "", "A", "B", "C"], "event": "Jane Doe stops being chief executive of Acme",
             "asks_opposite": True, "template": "nonsense", "horizon_days": 9999, "base_rate_percent": 80, "base_rate_reason": "r"}))
        self.assertEqual(p["focus"], "Jane Doe")
        self.assertEqual(len(p["related"]), 3)
        self.assertEqual((p["template"], p["horizon_days"], p["prior"]), ("custom", 365, 0.5))
        self.assertTrue(p["asks_opposite"])

    def test_plan_without_focus_fails(self):
        ai._model_cache.clear()
        with self.assertRaises(ai.AIError):
            ai.plan("k", "q", AS_OF, http=fake({"focus": ""}))


class Read(unittest.TestCase):
    PLAN = {"focus": "Jane Doe", "event": "Jane Doe stops being chief executive", "horizon_days": 30}

    def heads(self):
        return [H("Jane Doe subpoenaed in fraud inquiry", 2), H("Regulator opens case on Jane Doe", 3),
                H("Board backs Jane Doe", 5), H("Jane Doe opens plant", 40),
                live.Headline("Jane Doe resigns", "Reuters", "u", AS_OF + timedelta(days=1), "focus")]

    def test_future_headlines_are_never_sent(self):
        seen = []
        ai._model_cache.clear()
        ai.read("k", "q", self.PLAN, self.heads(), AS_OF, http=fake({"developments": []}, seen))
        prompt = seen[-1][1]["contents"][0]["parts"][0]["text"]
        self.assertNotIn("Jane Doe resigns", prompt)
        self.assertIn("Jane Doe subpoenaed", prompt)

    def test_developments_are_validated_and_scored(self):
        ai._model_cache.clear()
        reply = {"premise_ok": True, "already_happened": False, "summary": "s", "developments": [
            {"date": "2030-01-01", "summary": "Fraud inquiry opened", "direction": "up", "strength": "strong", "headline_ids": [0, 1]},
            {"date": "x", "summary": "Board support", "direction": "down", "strength": "weak", "headline_ids": [2]},
            {"summary": "invented, no headline", "direction": "up", "strength": "strong", "headline_ids": []},
            {"summary": "bad id", "direction": "up", "strength": "strong", "headline_ids": [99]},
            {"summary": "bad label", "direction": "sideways", "strength": "huge", "headline_ids": [0]}]}
        reading, sent = ai.read("k", "q", self.PLAN, self.heads(), AS_OF, http=fake(reply))
        self.assertEqual(len(reading["developments"]), 2)                       # the three invalid ones are dropped
        self.assertEqual(reading["developments"][0]["date"], AS_OF - timedelta(days=2))  # dated by headlines, not by the model
        case = ai.build_case("q", "Jane Doe", reading, sent, 0.01)
        probs, lo, hi, _, _ = answer_with_range(case, "q", AS_OF)
        self.assertGreater(probs["yes"], 0.01)
        self.assertLess(hi["yes"], 0.2)
        self.assertLessEqual(lo["yes"], probs["yes"])

    def test_many_strong_developments_stay_bounded(self):
        ai._model_cache.clear()
        hs = [H(f"Jane Doe story {i}", i % 5) for i in range(20)]
        reply = {"developments": [{"summary": f"d{i}", "direction": "up", "strength": "strong", "headline_ids": [i]} for i in range(20)]}
        reading, sent = ai.read("k", "q", self.PLAN, hs, AS_OF, http=fake(reply))
        self.assertEqual(len(reading["developments"]), ai.MAX_DEVELOPMENTS)
        p = answer_with_range(ai.build_case("q", "Jane Doe", reading, sent, 0.01), "q", AS_OF)[0]["yes"]
        self.assertLess(p, 0.35)

    def test_stale_premise_is_passed_through(self):
        ai._model_cache.clear()
        reading, _ = ai.read("k", "q", self.PLAN, self.heads(), AS_OF, http=fake(
            {"premise_ok": False, "premise_note": "She left the role in September.", "developments": []}))
        self.assertFalse(reading["premise_ok"])


class Who(unittest.TestCase):
    def test_candidates_and_developments(self):
        ai._model_cache.clear()
        hs = [H("Acme names finance chief Ann Lee interim CEO", 1), H("Acme board hires search firm", 2), H("Bo Kim seen as contender", 3)]
        reply = {"decided": False, "candidates": [{"name": "Ann Lee", "starting_percent": 25, "reason": "insider"},
                                                  {"name": "Bo Kim", "starting_percent": 15, "reason": "r"},
                                                  {"name": "Ann Lee", "starting_percent": 50}, {"name": ""}],
                 "someone_else_percent": 2, "summary": "s", "developments": [
                     {"candidate": "Ann Lee", "summary": "Named interim chief", "direction": "up", "strength": "strong", "headline_ids": [0]},
                     {"candidate": "Nobody Listed", "summary": "x", "direction": "up", "strength": "strong", "headline_ids": [1]},
                     {"candidate": "Bo Kim", "summary": "no headline", "direction": "up", "strength": "strong", "headline_ids": []}]}
        reading, sent = ai.read_who("k", "Who will be the next CEO of Acme?", hs, AS_OF, http=fake(reply))
        self.assertEqual([c["name"] for c in reading["candidates"]], ["Ann Lee", "Bo Kim", ai.OTHER])
        self.assertAlmostEqual(sum(c["prior"] for c in reading["candidates"]), 1.0)
        self.assertGreaterEqual(reading["candidates"][-1]["prior"], 0.1 / 1.5)   # "someone else" is never allowed to vanish
        self.assertEqual(len(reading["developments"]), 1)
        probs, lo, hi, _, _ = answer_with_range(ai.build_who_case("q", reading, sent), "q", AS_OF)
        self.assertAlmostEqual(sum(probs.values()), 1.0)
        self.assertGreater(probs["Ann Lee"], reading["candidates"][0]["prior"])
        self.assertLess(probs["Ann Lee"], 0.85)

    def test_no_candidates_is_an_error(self):
        ai._model_cache.clear()
        with self.assertRaises(ai.AIError):
            ai.read_who("k", "q", [H("x", 1)], AS_OF, http=fake({"candidates": []}))


class AutoPlan(unittest.TestCase):
    def test_lower_case_question(self):
        p = live.auto_plan("will tim cook step down as a ceo of apple within 30 days")
        self.assertEqual((p["focus"], p["template"], p["horizon_days"]), ("Tim Cook", "leader_exit", 30))

    def test_weeks_and_months(self):
        self.assertEqual(live.auto_plan("Will Acme sign a deal with Bolt within 2 months?")["horizon_days"], 60)
        self.assertEqual(live.auto_plan("Will Jane Doe resign in 3 weeks?")["horizon_days"], 21)


if __name__ == "__main__":
    unittest.main()

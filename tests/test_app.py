import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

try:
    from streamlit.testing.v1 import AppTest
except Exception:  # streamlit not installed: skip, the engine tests still run
    AppTest = None


@unittest.skipIf(AppTest is None, "streamlit not installed")
class App(unittest.TestCase):
    def test_every_case_and_question_renders(self):
        at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=120).run()
        self.assertFalse(at.exception)
        at.sidebar.radio[0].set_value("Worked examples (Iran, Nvidia)").run()
        self.assertFalse(at.exception)
        for case in at.sidebar.selectbox[0].options:
            at.sidebar.selectbox[0].select(case).run()
            self.assertFalse(at.exception, case)
            for q in at.sidebar.selectbox[1].options:
                at.sidebar.selectbox[1].select(q).run()
                self.assertFalse(at.exception, (case, q))

    def test_ask_anything_end_to_end(self):
        from datetime import date, timedelta
        from unittest import mock
        from ew import live
        today = date.today()
        heads = [live.Headline(f"Jane Doe opens office {i}", "Local Paper", "https://example.org/a", today - timedelta(days=15 + i), "focus") for i in range(40)]
        heads += [live.Headline(f"Jane Doe visits plant {i}", "Local Paper", "https://example.org/b", today - timedelta(days=i % 10), "focus") for i in range(10)]
        heads += [live.Headline(f"Jane Doe under investigation by regulators {i}", "Reuters", "https://example.org/c", today - timedelta(days=i % 5), "focus") for i in range(8)]
        import streamlit as st
        st.cache_data.clear()
        with mock.patch.object(live, "collect", return_value=(heads, [3, 4, 2, 3, 5, 3, 4, 3, 2, 4], ["Google News"])):
            at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=120).run()
            at.text_input[0].set_value("Will Jane Doe resign as CEO of Acme?").run()
            self.assertFalse(at.exception)
            at.button[0].click().run()
        self.assertFalse(at.exception)
        self.assertFalse(at.error)
        shown = {m.label: m.value for m in at.metric}
        self.assertEqual(shown["Headlines read"], "58")
        self.assertEqual(shown["Unusual signals"], "1")
        self.assertNotEqual(shown["Chance the event happens"], shown["Starting value"])

    def test_ask_anything_reports_fetch_failure(self):
        from unittest import mock
        import streamlit as st
        from ew import live
        st.cache_data.clear()  # the other test may have cached a successful fetch
        with mock.patch.object(live, "collect", side_effect=RuntimeError("offline")):
            at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=120).run()
            at.text_input[0].set_value("Will Jane Doe resign as CEO of Acme?").run()
            at.button[0].click().run()
        self.assertFalse(at.exception)
        self.assertTrue(at.error)

    def test_ask_anything_with_ai_reader(self):
        import os
        from datetime import date, timedelta
        from unittest import mock
        import streamlit as st
        from ew import ai, live
        st.cache_data.clear()
        today = date.today()
        heads = [live.Headline(f"Jane Doe story {i}", "Reuters", "https://example.org/a", today - timedelta(days=i), "focus") for i in range(30)]
        plan = {"focus": "Jane Doe", "related": ["Acme"], "event": "Jane Doe stops being chief executive of Acme", "asks_opposite": True,
                "template": "leader_exit", "horizon_days": 30, "prior": 0.02, "prior_reason": "Few chiefs leave in a month.", "by": "ai"}

        def reading(stale):
            return ({"premise_ok": not stale, "premise_note": "She left in September." if stale else "", "already_happened": False,
                     "summary": "Summary.", "developments": [{"date": today - timedelta(days=1), "summary": "Fraud inquiry opened",
                                                              "direction": "up", "strength": "strong", "ids": [1, 2]}]}, heads)
        for stale in (False, True):
            st.cache_data.clear()
            with mock.patch.dict(os.environ, {"GEMINI_API_KEY": "k"}), \
                 mock.patch.object(live, "collect", return_value=(heads, [3] * 10, ["Google News"])), \
                 mock.patch.object(ai, "plan", return_value=plan), mock.patch.object(ai, "read", return_value=reading(stale)):
                at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=120).run()
                at.text_input[0].set_value("will jane doe stay ceo of acme").run()
                at.button[0].click().run()
            self.assertFalse(at.exception)
            shown = {m.label: m.value for m in at.metric}
            self.assertEqual(shown["Developments that counted"], "1")
            if stale:
                self.assertEqual(shown["Chance the event happens"], "n/a")
                self.assertTrue(at.error)
            else:
                self.assertNotIn(shown["Chance the event happens"], ("n/a", "2.0%"))
                self.assertFalse(at.error)

    def test_ai_failure_falls_back_to_keywords(self):
        import os
        from unittest import mock
        import streamlit as st
        from ew import ai, live
        st.cache_data.clear()
        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": "k"}), \
             mock.patch.object(live, "collect", return_value=([], [0] * 10, ["Google News"])), \
             mock.patch.object(ai, "plan", side_effect=ai.AIError("quota")):
            at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=120).run()
            at.text_input[0].set_value("Will Jane Doe resign as CEO of Acme?").run()
            at.button[0].click().run()
        self.assertFalse(at.exception)
        self.assertTrue(any("Keyword rules were used" in w.value for w in at.warning))


if __name__ == "__main__":
    unittest.main()

import os
import unittest
from pathlib import Path

os.environ["EW_DEBUG"] = "1"  # let errors surface in tests

ROOT = Path(__file__).resolve().parents[1]

try:
    from streamlit.testing.v1 import AppTest
except Exception:  # streamlit not installed: skip, the engine tests still run
    AppTest = None


def open_app(page="Analyse"):
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=120).run()
    assert not at.exception
    return at.sidebar.radio[0].set_value(page).run()


@unittest.skipIf(AppTest is None, "streamlit not installed")
class App(unittest.TestCase):
    def test_every_case_and_question_renders(self):
        at = open_app()
        self.assertFalse(at.exception)
        at.sidebar.radio[0].set_value("Worked examples").run()
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
            at = open_app()
            at.text_input[0].set_value("Will Jane Doe resign as CEO of Acme?").run()
            self.assertFalse(at.exception)
            next(b for b in at.button if b.label == "Analyse").click().run()
        self.assertFalse(at.exception)
        self.assertFalse(at.error)
        shown = {m.label: m.value for m in at.metric}
        self.assertEqual(shown["Headlines read"], "58")
        self.assertEqual(shown["Unusual signals"], "1")
        self.assertNotEqual(shown["Answer"], shown["Starting value"])

    def test_ask_anything_reports_fetch_failure(self):
        from unittest import mock
        import streamlit as st
        from ew import live
        st.cache_data.clear()  # the other test may have cached a successful fetch
        with mock.patch.object(live, "collect", side_effect=RuntimeError("offline")):
            at = open_app()
            at.text_input[0].set_value("Will Jane Doe resign as CEO of Acme?").run()
            next(b for b in at.button if b.label == "Analyse").click().run()
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
                "template": "leader_exit", "horizon_days": 30, "deadline": str(today + timedelta(days=30)), "prior": 0.02,
                "prior_reason": "Few chiefs leave in a month.", "by": "ai", "kind": "yes_no",
                "restated": "Will Jane Doe stay chief executive of Acme for the next 30 days?"}

        def reading(stale):
            return ({"premise_ok": not stale, "premise_note": "She left in September." if stale else "", "already_happened": False,
                     "summary": "Summary.", "developments": [{"date": today - timedelta(days=1), "summary": "Fraud inquiry opened",
                                                              "direction": "up", "strength": "strong", "ids": [1, 2]}]}, heads)
        for stale in (False, True):
            st.cache_data.clear()
            with mock.patch.dict(os.environ, {"GEMINI_API_KEY": "k"}), \
                 mock.patch.object(live, "collect", return_value=(heads, [3] * 10, ["Google News"])), \
                 mock.patch.object(ai, "plan", return_value=plan), mock.patch.object(ai, "read", return_value=reading(stale)):
                at = open_app()
                at.text_input[0].set_value("will jane doe stay ceo of acme").run()
                next(b for b in at.button if b.label == "Analyse").click().run()
            self.assertFalse(at.exception)
            shown = {m.label: m.value for m in at.metric}
            self.assertEqual(shown["Developments that counted"], "1")
            self.assertTrue(any("You typed" in c.value and "will jane doe stay ceo of acme" in c.value for c in at.caption))
            if stale:
                self.assertEqual(shown["Answer"], "n/a")
                self.assertTrue(at.error)
            else:
                self.assertNotIn(shown["Answer"], ("n/a", "about 2%"))
                self.assertFalse(at.error)

    def test_unsupported_question_gets_a_suggestion(self):
        import os
        from unittest import mock
        import streamlit as st
        from ew import ai, live
        st.cache_data.clear()
        plan = {"kind": "unsupported", "by": "ai", "reason": "It asks for a price.", "suggestion": "Will Acme shares close above 100 by 31 December?"}
        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": "k"}), mock.patch.object(ai, "plan", return_value=plan), \
             mock.patch.object(live, "collect", side_effect=AssertionError("must not fetch")):
            at = open_app()
            at.text_input[0].set_value("what will the acme share price be").run()
            next(b for b in at.button if b.label == "Analyse").click().run()
        self.assertFalse(at.exception)
        self.assertTrue(any("cannot answer" in w.value for w in at.warning))
        self.assertTrue(any("Will Acme shares" in i.value for i in at.info))

    def test_far_deadline_is_damped_and_dated(self):
        import os
        from datetime import date, timedelta
        from unittest import mock
        import streamlit as st
        from ew import ai, live
        today = date.today()
        heads = [live.Headline(f"Party story {i}", "Reuters", "https://example.org/a", today - timedelta(days=i), "focus") for i in range(40)]
        devs = [{"date": today, "summary": f"Setback {i}", "direction": "down", "strength": "strong" if i < 2 else "medium", "ids": [i]} for i in range(4)]
        out = {}
        for days in (30, 725):
            st.cache_data.clear()
            plan = {"focus": "Party", "related": [], "event": "The party wins the election", "asks_opposite": False, "template": "custom",
                    "horizon_days": days, "deadline": str(today + timedelta(days=days)), "prior": 0.5, "prior_reason": "Two sides.", "by": "ai", "kind": "yes_no"}
            reading = ({"premise_ok": True, "premise_note": "", "already_happened": False, "summary": "S.", "developments": devs}, heads)
            with mock.patch.dict(os.environ, {"GEMINI_API_KEY": "k"}), \
                 mock.patch.object(live, "collect", return_value=(heads, [4] * 10, ["Google News"])), \
                 mock.patch.object(ai, "plan", return_value=plan), mock.patch.object(ai, "read", return_value=reading):
                at = open_app()
                at.text_input[0].set_value("will the party win the next election").run()
                next(b for b in at.button if b.label == "Analyse").click().run()
            self.assertFalse(at.exception)
            out[days] = float({m.label: m.value for m in at.metric}["Answer"].replace("about ", "").rstrip("%"))
            self.assertTrue(any(f"{today + timedelta(days=days):%d %B %Y}" in m.value for m in at.markdown))
        self.assertLess(out[30], out[725])          # the same bad news moves a two-year question much less
        self.assertGreater(out[725], 30)
        self.assertLess(out[725], 50)

    def test_who_question(self):
        import os
        from datetime import date, timedelta
        from unittest import mock
        import streamlit as st
        from ew import ai, live
        st.cache_data.clear()
        today = date.today()
        heads = [live.Headline(f"Acme CEO story {i}", "Reuters", "https://example.org/a", today - timedelta(days=i), "focus") for i in range(10)]
        plan = {"focus": "Acme CEO", "related": [], "event": "", "asks_opposite": False, "template": "custom", "horizon_days": 30,
                "prior": None, "prior_reason": "", "by": "ai", "kind": "who"}
        reading = ({"decided": False, "decided_note": "", "summary": "S.", "candidates": [
            {"name": "Ann Lee", "prior": 0.4, "reason": "insider"}, {"name": "Bo Kim", "prior": 0.3, "reason": "r"},
            {"name": ai.OTHER, "prior": 0.3, "reason": "x"}], "developments": [
            {"candidate": "Ann Lee", "date": today, "summary": "Named interim", "direction": "up", "strength": "strong", "ids": [0]}]}, heads)
        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": "k"}), \
             mock.patch.object(live, "collect", return_value=(heads, [3] * 10, ["Google News"])), \
             mock.patch.object(ai, "plan", return_value=plan), mock.patch.object(ai, "read_who", return_value=reading):
            at = open_app()
            at.text_input[0].set_value("who will be the next acme ceo").run()
            next(b for b in at.button if b.label == "Analyse").click().run()
        self.assertFalse(at.exception)
        self.assertFalse(at.error)
        self.assertTrue(any("Most likely: Ann Lee</div>" in m.value for m in at.markdown))

    def test_who_question_without_ai_explains(self):
        import streamlit as st
        st.cache_data.clear()
        at = open_app()
        at.text_input[0].set_value("who will be the next acme ceo").run()
        next(b for b in at.button if b.label == "Analyse").click().run()
        self.assertFalse(at.exception)
        self.assertTrue(any("need the AI reader" in e.value for e in at.error))

    def test_ai_failure_falls_back_to_keywords(self):
        import os
        from unittest import mock
        import streamlit as st
        from ew import ai, live
        st.cache_data.clear()
        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": "k"}), \
             mock.patch.object(live, "collect", return_value=([], [0] * 10, ["Google News"])), \
             mock.patch.object(ai, "plan", side_effect=ai.AIError("quota")):
            at = open_app()
            at.text_input[0].set_value("Will Jane Doe resign as CEO of Acme?").run()
            next(b for b in at.button if b.label == "Analyse").click().run()
        self.assertFalse(at.exception)
        self.assertTrue(any("Keyword rules were used" in w.value for w in at.warning))


if __name__ == "__main__":
    unittest.main()

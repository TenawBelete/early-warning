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


if __name__ == "__main__":
    unittest.main()

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
        for case in at.sidebar.selectbox[0].options:
            at.sidebar.selectbox[0].select(case).run()
            self.assertFalse(at.exception, case)
            for q in at.sidebar.selectbox[1].options:
                at.sidebar.selectbox[1].select(q).run()
                self.assertFalse(at.exception, (case, q))


if __name__ == "__main__":
    unittest.main()

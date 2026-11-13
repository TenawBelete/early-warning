import sys
import unittest
from datetime import date, timedelta
from email.utils import format_datetime
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ew import live  # noqa: E402
from ew.cases import answer_with_range  # noqa: E402

AS_OF = date(2026, 11, 10)


def rss(items):
    body = "".join(
        f"<item><title>{t} - {s}</title><link>https://example.org/{i}</link>"
        f"<pubDate>{format_datetime(datetime(d.year, d.month, d.day, 9, tzinfo=timezone.utc))}</pubDate>"
        f"<source url='https://x'>{s}</source></item>"
        for i, (t, s, d) in enumerate(items))
    return f"<rss><channel>{body}</channel></rss>".encode()


def fake_get(script):
    """script: function(url) -> list of (title, source, date)."""
    return lambda url, timeout=15: rss(script(url))


class Parsing(unittest.TestCase):
    def test_title_source_and_date(self):
        h = live.parse_google_rss(rss([("Acme chief faces probe", "Reuters", AS_OF)]), "focus")[0]
        self.assertEqual((h.title, h.source, h.published), ("Acme chief faces probe", "Reuters", AS_OF))

    def test_undated_items_are_dropped(self):
        xml = b"<rss><channel><item><title>No date</title></item></channel></rss>"
        self.assertEqual(live.parse_google_rss(xml, "focus"), [])

    def test_gdelt(self):
        h = live.parse_gdelt(b'{"articles":[{"title":"T","domain":"bbc.co.uk","url":"u","seendate":"20261109T120000Z"}]}', "focus")
        self.assertEqual(h[0].published, date(2026, 11, 9))


class Setup(unittest.TestCase):
    def test_template_detection(self):
        self.assertEqual(live.detect_template("Will Jane Doe resign as CEO of Acme?"), "leader_exit")
        self.assertEqual(live.detect_template("Will Country A strike Country B?"), "military_strike")
        self.assertEqual(live.detect_template("Will Acme sign a merger with Bolt?"), "deal")
        self.assertEqual(live.detect_template("Will Jane Doe be indicted?"), "legal_action")
        self.assertEqual(live.detect_template("Will it rain frogs?"), "custom")

    def test_focus_guess_and_base_rate(self):
        self.assertEqual(live.guess_focus("Will Jane Doe resign as CEO?"), "Jane Doe")
        self.assertAlmostEqual(live.base_rate("leader_exit", 30), 0.01)
        self.assertGreater(live.base_rate("leader_exit", 90), live.base_rate("leader_exit", 30))


class Gate(unittest.TestCase):
    def test_nothing_after_cutoff_is_used(self):
        late = AS_OF + timedelta(days=1)
        get = fake_get(lambda url: [("Jane Doe resigns", "Reuters", late), ("Jane Doe under investigation", "Reuters", AS_OF)])
        heads, counts, used = live.collect("Jane Doe", [], AS_OF, weeks=2, get=get)
        self.assertTrue(all(h.published <= AS_OF for h in heads))
        self.assertEqual([h.title for h in heads], ["Jane Doe under investigation"])
        self.assertEqual(used, ["Google News"])

    def test_fallback_to_gdelt(self):
        def get(url, timeout=15):
            if "google" in url:
                raise OSError("blocked")
            return b'{"articles":[{"title":"Jane Doe probe widens","domain":"bbc.co.uk","url":"u","seendate":"20261109T120000Z"}]}'
        heads, _, used = live.collect("Jane Doe", [], AS_OF, weeks=1, get=get)
        self.assertEqual(used, ["GDELT"])
        self.assertEqual(len(heads), 1)


class Engine(unittest.TestCase):
    def run_case(self, titles, template="leader_exit", counts=None, **kw):
        heads = [live.Headline(t, s, "https://example.org", AS_OF - timedelta(days=a), q) for t, s, a, q in titles]
        case, info = live.build_case("Will Jane Doe resign?", "Jane Doe", heads, counts or [5] * 10, AS_OF, template, 0.01, **kw)
        probs, lo, hi, detail, n = answer_with_range(case, "q", AS_OF)
        return probs["yes"], lo["yes"], hi["yes"], case, info

    def test_no_matching_news_returns_starting_value(self):
        p, *_ = self.run_case([("Jane Doe opens new office", "Reuters", 1, "focus")])
        self.assertAlmostEqual(p, 0.01)

    def test_pressure_raises_and_support_lowers(self):
        up, *_ = self.run_case([("Jane Doe under investigation by regulators", "Reuters", 1, "focus"),
                                ("Board hires firm to find successor to Jane Doe", "Bloomberg", 2, "focus")])
        down, *_ = self.run_case([("Board backs Jane Doe after record profit", "Reuters", 1, "focus")])
        self.assertGreater(up, 0.01)
        self.assertLess(down, 0.01)

    def test_repeats_of_one_story_are_bounded(self):
        one, *_ = self.run_case([("Jane Doe faces probe", "Reuters", 1, "focus")])
        many, *_ = self.run_case([(f"Jane Doe faces probe, report {i}", "Reuters", 1, "focus") for i in range(60)])
        self.assertGreater(many, one)
        self.assertLess(many, 0.10)  # sixty copies of one kind of story cannot run away

    def test_denial_is_weak_and_related_counts_less(self):
        claim, *_ = self.run_case([("Jane Doe to step down", "Reuters", 1, "focus")])
        denial, *_ = self.run_case([("Jane Doe denies she will step down", "Reuters", 1, "focus")])
        related, *_ = self.run_case([("Rival chief to step down", "Reuters", 1, "Rival Corp")])
        self.assertLess(denial, claim)
        self.assertLess(related, claim)

    def test_low_and_high_bracket_the_number(self):
        p, lo, hi, *_ = self.run_case([("Jane Doe under investigation", "Reuters", 3, "focus")])
        self.assertLessEqual(lo, p)
        self.assertLessEqual(p, hi)

    def test_attention_spike_and_saturation(self):
        *_, case, info = self.run_case([], counts=[5, 6, 4, 5, 7, 5, 6, 5, 4, 40])
        self.assertIn("attention_spike", [e.type for e in case.evidence])
        *_, case, info = self.run_case([], counts=[100] * 10)
        self.assertTrue(info["saturated"])
        self.assertEqual(case.evidence, [])

    def test_custom_clue_words(self):
        p, *_ = self.run_case([("Jane Doe volcano erupts again", "Reuters", 1, "focus")], template="custom", yes_words=["erupt"])
        q, *_ = self.run_case([("Jane Doe volcano calm", "Reuters", 1, "focus")], template="custom", yes_words=["erupt"], no_words=["calm"])
        self.assertGreater(p, 0.01)
        self.assertLess(q, 0.01)


if __name__ == "__main__":
    unittest.main()

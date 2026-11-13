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


def H(title, days_ago, source="Reuters", query="focus"):
    return live.Headline(title, source, "https://example.org", AS_OF - timedelta(days=days_ago), query)


ORDINARY = ["Big Boss unveils new product", "Big Boss lawsuit over pay continues", "Regulators investigate Big Boss firm",
            "Big Boss warns of slowdown", "Shares fall after Big Boss comments", "Big Boss accused by critics",
            "Big Boss fired back at critics", "Who is the successor to Big Boss?", "Big Boss under fire for post",
            "Big Boss visits factory"]


def ordinary(n=700, seed=0):
    import random
    rng = random.Random(seed)
    return [H(f"{rng.choice(ORDINARY)} {i}", rng.randrange(70)) for i in range(n)]


class Engine(unittest.TestCase):
    def run_case(self, heads, template="leader_exit", counts=None, prior=0.01, **kw):
        tagged, kinds = live.tag_headlines(heads, template, kw.get("yes_words"), kw.get("no_words"))
        p, lo, hi, detail, info = live.forecast("Will Big Boss resign?", "Big Boss", tagged, kinds,
                                                [5] * 10 if counts is None else counts, AS_OF, prior)
        return p, lo, hi, info

    def test_no_news_returns_starting_value(self):
        p, *_ = self.run_case([H(f"Big Boss opens office {i}", i) for i in range(40)])
        self.assertAlmostEqual(p, 0.01)

    def test_famous_name_with_ordinary_trouble_stays_at_starting_value(self):
        # the failure of the first version: steady background noise must not count as evidence
        for seed in range(25):
            p, *_ = self.run_case(ordinary(seed=seed))
            self.assertLess(p, 0.015, seed)

    def test_a_real_change_moves_the_number_but_not_to_certainty(self):
        surge = [H(f"Big Boss subpoenaed in fraud inquiry {i}", i % 6) for i in range(60)]
        p, lo, hi, info = self.run_case(ordinary() + surge)
        self.assertGreater(p, 0.015)
        self.assertLess(hi, 0.5)
        self.assertLessEqual(lo, p)
        self.assertLessEqual(p, hi)

    def test_support_lowers(self):
        calm = [H(f"Big Boss opens office {i}", 15 + i % 50) for i in range(100)] + [H(f"Big Boss tours site {i}", i % 10) for i in range(10)]
        p, *_ = self.run_case(calm + [H(f"Board backs Big Boss after record profit {i}", i % 5) for i in range(6)])
        self.assertLess(p, 0.01)

    def test_denials_and_two_stray_headlines_do_not_count(self):
        calm = [H(f"Big Boss opens office {i}", i % 60) for i in range(100)]
        p, *_ = self.run_case(calm + [H(f"Big Boss denies she will step down {i}", i) for i in range(6)])
        q, *_ = self.run_case(calm + [H("Big Boss to step down", 1), H("Big Boss stepping down, sources say", 2)])
        self.assertAlmostEqual(p, 0.01)
        self.assertAlmostEqual(q, 0.01)

    def test_related_names_count_less(self):
        calm = [H(f"Big Boss opens office {i}", i % 60) for i in range(100)]
        own = [H(f"Big Boss under investigation {i}", i % 5) for i in range(10)]
        other = [H(f"Rival chief under investigation {i}", i % 5, query="Rival") for i in range(10)]
        a, *_ = self.run_case(calm + own)
        b, *_ = self.run_case(calm + other)
        self.assertGreater(a, b)
        self.assertGreater(b, 0.01)

    def test_direct_reports_raise_the_already_happened_flag(self):
        calm = [H(f"Big Boss opens office {i}", i % 60) for i in range(100)]
        *_, info = self.run_case(calm + [H(f"Big Boss resigns as chief {i}", i % 3) for i in range(8)])
        self.assertTrue(info["maybe_happened"])

    def test_gate_inside_scoring(self):
        future = [live.Headline(f"Big Boss resigns {i}", "Reuters", "u", AS_OF + timedelta(days=1), "focus") for i in range(20)]
        p, *_ = self.run_case([H(f"Big Boss opens office {i}", i % 60) for i in range(100)] + future)
        self.assertAlmostEqual(p, 0.01)

    def test_attention_spike_and_saturation(self):
        *_, info = self.run_case([], counts=[5, 6, 4, 5, 7, 5, 6, 5, 4, 40])
        self.assertEqual(info["signals"], 1)
        *_, info = self.run_case([], counts=[100] * 10)
        self.assertTrue(info["saturated"])
        self.assertEqual(info["signals"], 0)

    def test_custom_clue_words(self):
        calm = [H(f"Big Boss volcano quiet {i}", 15 + i % 50) for i in range(60)] + [H(f"Big Boss volcano watch {i}", i % 10) for i in range(6)]
        p, *_ = self.run_case(calm + [H(f"Big Boss volcano erupts {i}", i % 4) for i in range(6)], template="custom", yes_words=["erupt"])
        self.assertGreater(p, 0.01)


if __name__ == "__main__":
    unittest.main()

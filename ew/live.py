"""Ask-anything mode: build a case on the fly from public news headlines.

The bundled cases were collected and coded by hand. This module does a much
cruder version of the same thing automatically so that any question can be
asked:

  1. fetch dated headlines about the focus (and, less deeply, related names)
  2. tag each headline with a signal type by keyword rules
  3. hand the result to the same engine as the bundled cases

Limits, stated plainly: keyword rules misread headlines, a headline is not
the article, the starting value is a rough judgment, and none of this has a
track record. Treat the output as a structured reading of the news, not as a
validated forecast.
"""
from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from email.utils import parsedate_to_datetime

from .baseline import robust_z
from .cases import Case
from .evidence import Evidence

UA = {"User-Agent": "Mozilla/5.0 (early-warning research prototype)"}
PER_QUERY_CAP = 100  # Google News returns at most about 100 items per search

# ------------------------------------------------------------------ templates
# Each signal: (type name, family, likelihood ratio for "yes", pattern).
# Order matters: the first pattern that matches a headline wins.
# Ratios are analyst-set starting values, kept modest on purpose.
TEMPLATES: dict[str, dict] = {
    "leader_exit": {
        "name": "A leader leaves or is removed",
        "detect": r"resign|step(s|ping)? down|fired|oust|replac|quit|removed|leave (office|the company)|successor|still be (ceo|president|prime minister|chair)",
        "base": (0.01, 30),
        "signals": [
            ("exit_reported", "direct", 4.0, r"\b(resigns|resigned|steps down|stepping down|to step down|stepped down|ousted|fired|sacked|removed as|leave of absence|placed on leave|goes on leave)\b"),
            ("succession_talk", "succession", 1.6, r"\b(successor|succession|interim (ceo|chief|leader|president)|search for (a )?new|replacement for)\b"),
            ("official_probe", "official", 2.0, r"\b(investigat\w*|probe|probes|subpoena\w*|indict\w*|charged|raid|raided|inquiry|whistleblower|grand jury|search warrant)\b"),
            ("scandal", "scandal", 1.8, r"\b(scandal|affair|misconduct|allegation\w*|alleged|accused|harass\w*|cover-?up|leaked|fraud)\b"),
            ("pressure", "pressure", 1.5, r"\b(calls? (for|on|to) .{0,40}(resign|quit|step down|go)|under (fire|pressure)|backlash|no.confidence|activist investor|revolt|urged to (resign|quit))\b"),
            ("trouble", "market", 1.2, r"\b((shares?|stock) (fall|falls|drop|drops|plunge|plunges|sink|sinks|tumble|tumbles|slide|slides)|downgrade\w*|short.?seller|lawsuit|sued|layoffs|recall)\b"),
            ("support", "standing", 0.75, r"\b(backs|backed by|vote of confidence|contract extended|extends contract|re-?elected|reappointed|cleared|exonerat\w*|record (profit|revenue|earnings)|beats (estimates|expectations))\b"),
        ],
    },
    "military_strike": {
        "name": "A military strike or attack",
        "detect": r"strike|attack|war\b|invade|invasion|bomb|military action|conflict",
        "base": (0.02, 14),
        "signals": [
            ("strike_reported", "direct", 4.0, r"\b(launch(es|ed)? (a |an )?(strike|strikes|attack|invasion|offensive)|air ?strikes? (on|hit|against)|strikes hit|invades|invaded|bombed|bombs)\b"),
            ("precaution", "precaution", 2.2, r"\b(evacuat\w*|leave immediately|embassy (closes|closed|staff|drawdown)|travel (warning|advisory)|airspace clos\w*|flights? (cancel\w*|suspend\w*)|shelters?)\b"),
            ("force_movement", "military", 2.0, r"\b(deploy\w*|aircraft carrier|carrier (group|strike)|warships?|troops? (mass|build|moved|sent)|build-?up|mobili[sz]\w*|bombers|reinforce\w*)\b"),
            ("talks_fail", "diplomacy", 1.6, r"\b(talks (collapse\w*|fail\w*|stall\w*|break down|broke down|end without)|walks? out|suspends? talks|no deal|rejects? (proposal|offer|terms))\b"),
            ("talks_progress", "diplomacy", 0.7, r"\b(talks (resume\w*|progress|continue)|ceasefire|truce|de-?escalat\w*|deal reached|breakthrough|peace (deal|plan|talks)|agreement)\b"),
            ("threat", "rhetoric", 1.3, r"\b(ultimatum|deadline|warns?|warning|threat\w*|vows?|retaliat\w*|red line|all options)\b"),
        ],
    },
    "deal": {
        "name": "A deal or agreement is reached",
        "detect": r"deal|agreement|ceasefire|merger|merge|acquire|acquisition|treaty|buy\b|takeover|sign",
        "base": (0.05, 30),
        "signals": [
            ("deal_reported", "direct", 4.0, r"\b(signs|signed|reach(es|ed) (a |an )?(deal|agreement|accord)|agrees? to (buy|acquire|merge|terms|a deal)|finali[sz]e[sd]?|announces? (a |an )?(deal|merger|acquisition|agreement))\b"),
            ("breakdown", "setback", 0.6, r"\b(talks (collapse\w*|fail\w*|stall\w*|break down|broke down)|walks? away|rejects?|rejected|blocked|blocks|scraps?|scrapped|abandon\w*|called off|antitrust (suit|challenge|lawsuit)|veto\w*)\b"),
            ("approval", "approval", 1.4, r"\b(regulators? (approve\w*|clear\w*)|wins? approval|green light|board approves|shareholders approve)\b"),
            ("progress", "progress", 1.7, r"\b(advanced talks|close to (a |an )?(deal|agreement)|nearing|near(s)? (a )?deal|breakthrough|optimis\w*|in talks|negotiat\w*|term sheet|bid for|offer for|progress)\b"),
        ],
    },
    "legal_action": {
        "name": "Charges, arrest, sanctions or similar",
        "detect": r"charged|charges|indict|arrest|convict|sanction|sued|prosecut|impeach|fined|jail",
        "base": (0.02, 30),
        "signals": [
            ("cleared", "outcome", 0.5, r"\b(cleared|charges dropped|drops? (charges|case|probe|investigation)|dismissed|acquitted|no charges|closes (probe|investigation)|pardon\w*|exonerat\w*)\b"),
            ("action_reported", "direct", 4.0, r"\b(charged|indicted|arrested|convicted|sanctioned|impeached|pleads|pleaded|fined|sentenced)\b"),
            ("probe", "official", 2.0, r"\b(investigat\w*|probe|probes|subpoena\w*|grand jury|raid|raided|search warrant|inquiry|referral|whistleblower)\b"),
            ("cooperation", "cooperation", 1.6, r"\b(cooperat\w*|testif\w*|plea deal|turns? witness|immunity)\b"),
            ("allegation", "scandal", 1.5, r"\b(alleg\w*|accus\w*|lawsuit|sued|complaint|leaked|fraud|bribe\w*|corruption)\b"),
        ],
    },
    "custom": {
        "name": "Something else (you give the clue words)",
        "detect": r"$^",
        "base": (0.05, 30),
        "signals": [],  # filled from the user's clue words
    },
}

HALF_LIFE = {"direct": 14, "succession": 45, "official": 30, "scandal": 30, "pressure": 14, "market": 10,
             "standing": 30, "precaution": 7, "military": 14, "diplomacy": 10, "rhetoric": 7, "setback": 21,
             "approval": 30, "progress": 21, "outcome": 45, "cooperation": 30, "response": 10, "attention": 7,
             "custom_for": 21, "custom_against": 21}

DENIAL = re.compile(r"\b(denies|denied|deny|rules? out|no plans? to|rejects? (claims?|reports?|rumou?rs?)|dismiss(es|ed) (claims?|reports?|rumou?rs?))\b", re.I)

TOP_SOURCES = ("reuters", "associated press", "ap news", "bbc", "bloomberg", "financial times", "wall street journal",
               "wsj", "new york times", "washington post", "the guardian", "economist", "cnbc", "npr", "al jazeera",
               "france 24", "dw", "politico", "axios", "nikkei", "el país", "le monde", "cbs news", "nbc news",
               "abc news", "cnn", "sec.gov", "justice.gov")

STOP = set("will would the a an of in on to by for and or be is are was were has have had do does did this that with within "
           "before after next days day weeks week months month year years from as at it its their his her than what who "
           "when happen happens going get gets still any some new".split())


# ------------------------------------------------------------------ data
@dataclass(frozen=True)
class Headline:
    title: str
    source: str
    link: str
    published: date
    query: str  # "focus" or the related name that found it


def detect_template(question: str) -> str:
    q = question.lower()
    for key, t in TEMPLATES.items():
        if key != "custom" and re.search(t["detect"], q):
            return key
    return "custom"


def base_rate(template: str, horizon_days: int) -> float:
    """Rough starting value for the horizon. A judgment, shown to the user, who can change it."""
    p, ref = TEMPLATES[template]["base"]
    return min(0.5, 1 - (1 - p) ** (horizon_days / ref))


def guess_focus(question: str) -> str:
    """Longest run of capitalised words that does not start the sentence."""
    words = question.strip().rstrip("?").split()
    best, cur = [], []
    for i, w in enumerate(words):
        core = w.strip(",.;:'\"")
        if i > 0 and core[:1].isupper():
            cur.append(core)
        else:
            if len(cur) > len(best):
                best = cur
            cur = []
    if len(cur) > len(best):
        best = cur
    return " ".join(best)


def clue_words(question: str, focus: str) -> list[str]:
    skip = STOP | set(focus.lower().split())
    out = []
    for w in re.findall(r"[a-zA-Z][a-zA-Z\-]{2,}", question.lower()):
        if w not in skip and w not in out:
            out.append(w)
    return out


# ------------------------------------------------------------------ fetching
def _get(url: str, timeout: int = 15) -> bytes:
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
        return r.read()


def google_news_url(term: str, start: date, end: date, exact: bool = True) -> str:
    """Search link for headlines published from `start` to `end` inclusive."""
    q = f'"{term}"' if exact else term
    q += f" after:{start - timedelta(days=1)} before:{end + timedelta(days=1)}"
    return "https://news.google.com/rss/search?" + urllib.parse.urlencode({"q": q, "hl": "en-US", "gl": "US", "ceid": "US:en"})


def parse_google_rss(xml_bytes: bytes, query: str) -> list[Headline]:
    out = []
    for item in ET.fromstring(xml_bytes).iter("item"):
        title = (item.findtext("title") or "").strip()
        source = (item.findtext("source") or "").strip()
        pub = item.findtext("pubDate")
        if not title or not pub:
            continue  # undated items are never used
        try:
            when = parsedate_to_datetime(pub).date()
        except (TypeError, ValueError):
            continue
        if source and title.endswith(" - " + source):
            title = title[: -len(source) - 3]
        out.append(Headline(title, source or "unknown", (item.findtext("link") or "").strip(), when, query))
    return out


def gdelt_url(term: str, start: date, end: date) -> str:
    return "https://api.gdeltproject.org/api/v2/doc/doc?" + urllib.parse.urlencode({
        "query": f'"{term}" sourcelang:english', "mode": "artlist", "format": "json", "maxrecords": 250,
        "startdatetime": f"{start:%Y%m%d}000000", "enddatetime": f"{end:%Y%m%d}235959", "sort": "datedesc"})


def parse_gdelt(json_bytes: bytes, query: str) -> list[Headline]:
    out = []
    for a in json.loads(json_bytes or b"{}").get("articles", []):
        try:
            when = datetime.strptime(a["seendate"][:8], "%Y%m%d").date()
        except (KeyError, ValueError):
            continue
        if a.get("title"):
            out.append(Headline(a["title"].strip(), a.get("domain", "unknown"), a.get("url", ""), when, query))
    return out


def fetch_window(term: str, start: date, end: date, query: str, get=_get) -> tuple[list[Headline], str]:
    """Headlines for one term and one date window. Returns (headlines, source used)."""
    try:
        return parse_google_rss(get(google_news_url(term, start, end)), query), "Google News"
    except Exception as first:
        try:
            return parse_gdelt(get(gdelt_url(term, start, end)), query), "GDELT"
        except Exception as second:
            raise RuntimeError(f"Could not reach a news source (Google News: {first}; GDELT: {second})") from second


def collect(focus: str, related: list[str], as_of: date, weeks: int = 10, get=_get):
    """Fetch the focus week by week, and each related name once over the last four weeks.

    Returns (headlines, weekly focus counts oldest first, sources used).
    Everything dated after `as_of` is dropped: that is the point-in-time gate.
    """
    seen: set[str] = set()
    heads: list[Headline] = []
    counts: list[int] = []
    used: set[str] = set()

    def keep(items):
        n = 0
        for h in items:
            key = re.sub(r"\W+", " ", h.title.lower()).strip()
            if h.published > as_of or key in seen:
                continue
            seen.add(key)
            heads.append(h)
            n += 1
        return n

    for w in range(weeks - 1, -1, -1):
        end = as_of - timedelta(days=7 * w)
        start = end - timedelta(days=6)
        items, src = fetch_window(focus, start, end, "focus", get)
        used.add(src)
        counts.append(len([h for h in items if start <= h.published <= end]))
        keep(items)
    for name in related:
        items, src = fetch_window(name, as_of - timedelta(days=27), as_of, name, get)
        used.add(src)
        keep(items)
    return heads, counts, sorted(used)


# ------------------------------------------------------------------ coding
def reliability(source: str) -> float:
    s = source.lower()
    return 0.9 if any(t in s for t in TOP_SOURCES) else 0.6


def signals_for(template: str, yes_words: list[str], no_words: list[str]):
    sig = [(n, f, lr, re.compile(p, re.I)) for n, f, lr, p in TEMPLATES[template]["signals"]]
    for words, name, fam, lr in ((no_words, "your_no_clue", "custom_against", 0.65), (yes_words, "your_yes_clue", "custom_for", 1.6)):
        words = [w.strip() for w in words if w.strip()]
        if words:
            sig.append((name, fam, lr, re.compile(r"\b(" + "|".join(re.escape(w) + r"\w*" for w in words) + r")", re.I)))
    return sig


def build_case(question: str, focus: str, heads: list[Headline], counts: list[int], as_of: date, template: str,
               prior_yes: float, yes_words: list[str] | None = None, no_words: list[str] | None = None) -> tuple[Case, dict]:
    """Turn headlines into a Case the normal engine can answer. Also returns diagnostics."""
    sig = signals_for(template, yes_words or [], no_words or [])
    types = {n: {"family": f, "lr": {"yes": lr}} for n, f, lr, _ in sig}
    types["denied_claim"] = {"family": "response", "lr": {"yes": 1.1}}
    types["attention_spike"] = {"family": "attention", "lr": {"yes": 1.3}}
    catalog = {"types": types, "half_life_days": HALF_LIFE, "watch_families": []}
    relevance = {"named_in_headline": (1.0, 0), "found_by_focus_search": (0.6, 1), "related_name": (0.5, 1)}

    names = [focus.lower()] + [w for w in focus.lower().split() if len(w) > 3][-1:]
    ev: list[Evidence] = []
    for i, h in enumerate(heads):
        kind = next((n for n, _, _, rx in sig if rx.search(h.title)), None)
        if kind is None:
            continue
        if DENIAL.search(h.title) and types[kind]["lr"]["yes"] > 1:
            kind = "denied_claim"  # a denial shows the issue is live, but is weak evidence
        low = h.title.lower()
        entity = "named_in_headline" if any(n in low for n in names) else ("found_by_focus_search" if h.query == "focus" else "related_name")
        ev.append(Evidence(f"h{i:04d}", h.published, h.published, entity, kind, h.title, h.link, reliability(h.source), h.source))

    z = None
    saturated = sum(c >= PER_QUERY_CAP - 5 for c in counts) > len(counts) / 2
    if len(counts) >= 9 and not saturated:
        z = robust_z([float(c) for c in counts[:-1]], float(counts[-1]))
        if z >= 3:
            med = sorted(counts[:-1])[len(counts[:-1]) // 2]
            ev.append(Evidence("attn", as_of, as_of, "named_in_headline", "attention_spike",
                               f"Unusual coverage: {counts[-1]} headlines this week against a typical {med}",
                               google_news_url(focus, as_of - timedelta(days=6), as_of), 0.8, "headline counts"))

    spec = {"name": question, "focus_entity": focus,
            "questions": [{"id": "q", "text": question, "kind": "live", "priors": {"yes": prior_yes, "no": 1 - prior_yes}}]}
    info = {"read": len(heads), "used": len(ev), "attention_z": z, "saturated": saturated, "weekly_counts": counts}
    return Case("live", spec, catalog, ev, relevance), info

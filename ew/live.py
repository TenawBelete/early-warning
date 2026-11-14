"""Ask-anything mode: build a case on the fly from public news headlines.

The bundled cases were collected and coded by hand. This module does a much
cruder version of the same thing automatically so that any question can be
asked:

  1. fetch dated headlines about the focus (and, less deeply, related names)
  2. tag each headline with a signal type by keyword rules
  3. compare the last two weeks with the same name's own earlier coverage:
     only a kind of story that is clearly MORE common than usual counts
  4. hand the result to the same engine as the bundled cases

Step 3 matters. A famous name always has lawsuits, critics and warnings in
its headlines. Counting each such headline as evidence (the first version of
this module did) drives every answer towards 100%.

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
from .sources import credibility, support

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
            ("exit_reported", "direct", 4.0, r"\b(resigns|resigned|steps down|stepping down|to step down|stepped down|ousted|(is|was|been|gets|got) (fired|sacked)|removed as|leave of absence|placed on leave|goes on leave)\b"),
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
            if h.published > as_of or key in seen or credibility(h.source) <= 0:
                continue  # after the cutoff, a repeat, or satire
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
    return credibility(source)


def signals_for(template: str, yes_words: list[str], no_words: list[str]):
    sig = [(n, f, lr, re.compile(p, re.I)) for n, f, lr, p in TEMPLATES[template]["signals"]]
    for words, name, fam, lr in ((no_words, "your_no_clue", "custom_against", 0.65), (yes_words, "your_yes_clue", "custom_for", 1.6)):
        words = [w.strip() for w in words if w.strip()]
        if words:
            sig.append((name, fam, lr, re.compile(r"\b(" + "|".join(re.escape(w) + r"\w*" for w in words) + r")", re.I)))
    return sig


import math

from .cases import answer, neighbours
from .engine import V0

RECENT_DAYS = 14
LABELS = {"exit_reported": "Reports that the exit is happening", "succession_talk": "Talk of a successor",
          "official_probe": "Investigations", "scandal": "Scandal or allegations", "pressure": "Pressure to go",
          "trouble": "Business or legal trouble", "support": "Shows of support", "strike_reported": "Reports of a strike",
          "precaution": "Evacuations and travel warnings", "force_movement": "Military movements",
          "talks_fail": "Talks failing", "talks_progress": "Talks progressing", "threat": "Threats and warnings",
          "deal_reported": "Reports that the deal is done", "breakdown": "Setbacks", "approval": "Approvals",
          "progress": "Progress in talks", "cleared": "Cleared or dropped", "action_reported": "Reports of legal action",
          "probe": "Investigations", "cooperation": "Witness cooperation", "allegation": "Allegations",
          "your_yes_clue": "Your YES clue words", "your_no_clue": "Your NO clue words",
          "attention_spike": "Unusual amount of coverage"}


def tag_headlines(heads: list[Headline], template: str, yes_words=None, no_words=None):
    """Return [(headline, signal type or None)]. A denial is tagged 'denied_claim' and never counted."""
    sig = signals_for(template, yes_words or [], no_words or [])
    out = []
    for h in heads:
        kind = next((n for n, _, _, rx in sig if rx.search(h.title)), None)
        if kind and DENIAL.search(h.title):
            kind = "denied_claim"
        out.append((h, kind))
    return out, {n: (f, lr) for n, f, lr, _ in sig}


def horizon_damp(horizon_days: int) -> float:
    """Today's news says less about far-off events. Full weight up to 60 days, then shrinking with the square root
    of the distance (0.41 at one year, 0.29 at two). Analyst-set, not measured."""
    return min(1.0, (60 / max(1, horizon_days)) ** 0.5)


def build_case(question: str, focus: str, tagged, kinds: dict, counts: list[int], as_of: date, prior_yes: float,
               recent_days: int = RECENT_DAYS, damp: float = 1.0) -> tuple[Case, dict]:
    """Compare recent coverage with the name's own baseline and turn the differences into a Case."""
    cut = as_of - timedelta(days=recent_days)
    types: dict = {"attention_spike": {"family": "attention", "lr": {"yes": 1.3 ** damp}}}
    ev: list[Evidence] = []
    rows: list[dict] = []
    for group, rel_name in (("focus", "focus"), ("related", "related_name")):
        mine = [(h, k) for h, k in tagged if (h.query == "focus") == (group == "focus") and h.published <= as_of]
        recent = [(h, k) for h, k in mine if h.published > cut]
        base = [(h, k) for h, k in mine if h.published <= cut]
        n_r, n_b = len(recent), len(base)
        if n_r < 5:
            continue  # too little recent coverage to say anything
        for kind, (family, lr) in kinds.items():
            ex = [h for h, k in recent if k == kind]
            k_r, k_b = len(ex), sum(k == kind for _, k in base)
            usual = (k_b + 1) / (n_b + 2)
            expected = n_r * usual
            lift = ((k_r + 1) / (n_r + 2)) / usual
            row = {"signal": kind, "group": group, "recent": k_r, "recent_total": n_r, "usual_share": k_b / n_b if n_b else None,
                   "lift": lift, "counted": False, "examples": ex[:6]}
            rows.append(row)
            # must be at least 3 headlines, 1.5x the usual share, and clearly outside ordinary week-to-week noise
            if k_r < 3 or lift < 1.5 or k_r < expected + 2 * math.sqrt(expected):
                continue
            strength = min(1.0, math.log(lift) / math.log(3))  # three times the usual share = full strength
            if n_b < 20:
                strength *= 0.5  # no real baseline to compare with
            name = f"{kind}@{group}"
            types[name] = {"family": family, "lr": {"yes": lr ** (strength * damp)}}
            usual_txt = f"usual {k_b / n_b:.0%}" if n_b >= 20 else "too little earlier coverage to know what is usual"
            ev.append(Evidence(name, as_of, as_of, rel_name, name,
                               f"{LABELS.get(kind, kind)}: {k_r} of the last {n_r} headlines ({k_r / n_r:.0%}); {usual_txt}",
                               ex[0].link, support([h.source for h in ex])[0], group))
            row["support"] = support([h.source for h in ex])[1]
            row["counted"] = True

    z = None
    saturated = bool(counts) and sum(c >= PER_QUERY_CAP - 5 for c in counts) > len(counts) / 2
    if len(counts) >= 9 and not saturated:
        z = robust_z([float(c) for c in counts[:-1]], float(counts[-1]))
        if z >= 3:
            med = sorted(counts[:-1])[len(counts[:-1]) // 2]
            ev.append(Evidence("attn", as_of, as_of, "focus", "attention_spike",
                               f"Unusual amount of coverage: {counts[-1]} headlines this week against a typical {med}",
                               google_news_url(focus, as_of - timedelta(days=6), as_of), 0.8, "focus"))

    direct = [r for r in rows if r["group"] == "focus" and kinds[r["signal"]][0] == "direct"]
    catalog = {"types": types, "half_life_days": HALF_LIFE, "watch_families": []}
    spec = {"name": question, "focus_entity": focus,
            "questions": [{"id": "q", "text": question, "kind": "live", "priors": {"yes": prior_yes, "no": 1 - prior_yes}}]}
    info = {"read": sum(h.published <= as_of for h, _ in tagged), "signals": len(ev), "attention_z": z, "saturated": saturated,
            "weekly_counts": counts, "rows": rows, "maybe_happened": any(r["counted"] and r["recent"] >= 5 for r in direct)}
    return Case("live", spec, catalog, ev, {"focus": (1.0, 0), "related_name": (0.5, 1)}), info


def forecast(question, focus, tagged, kinds, counts, as_of, prior_yes, damp: float = 1.0):
    """Central number, plus the lowest and highest across nearby engine settings and 7/14/28-day 'recent' windows."""
    case, info = build_case(question, focus, tagged, kinds, counts, as_of, prior_yes, RECENT_DAYS, damp)
    probs, detail, _ = answer(case, "q", as_of)
    lo = hi = probs["yes"]
    for days in (7, 14, 28):
        c, _ = build_case(question, focus, tagged, kinds, counts, as_of, prior_yes, days, damp)
        for st in neighbours(V0):
            v = answer(c, "q", as_of, st)[0]["yes"]
            lo, hi = min(lo, v), max(hi, v)
    return probs["yes"], lo, hi, detail["yes"], info


def asks_opposite(question: str, template: str) -> bool:
    """True when the question asks whether the status quo holds ('Will X stay...') rather than whether the event happens."""
    return template != "custom" and bool(re.search(r"\b(stays?|remains?|still be|survives?|keeps? (his|her|the|their) (job|post|role)|continues? as|hold on)\b", question, re.I))


VERBS = set("step steps resign resigns quit quits leave leaves stay stays remain remains be become get gets sign signs strike "
            "strikes attack attacks invade invades buy buys acquire acquires merge merges face faces lose loses win wins "
            "announce announces reach reaches agree agrees go goes still survive survives keep keeps continue continues "
            "have has fall falls rise rises launch launches".split())


def auto_plan(question: str) -> dict:
    """Keyword version of the set-up step, used when no AI key is configured."""
    words = re.sub(r"[?.!]", "", question).split()
    focus = guess_focus(question)
    if not focus:  # lower-case question: take the words after "will" up to the first verb
        body = words[1:] if words and words[0].lower() in {"will", "is", "does", "can", "could", "would", "are", "did"} else words
        name = []
        for w in body:
            if w.lower() in VERBS:
                break
            name.append(w)
        focus = " ".join(name[:4]).title()
    template = detect_template(question)
    m = re.search(r"(\d+)\s*(day|week|month|year)", question.lower())
    horizon = TEMPLATES[template]["base"][1]
    if m:
        horizon = int(m.group(1)) * {"day": 1, "week": 7, "month": 30, "year": 365}[m.group(2)]
    horizon = min(365, max(1, horizon))
    return {"focus": focus, "related": [], "event": TEMPLATES[template]["name"], "asks_opposite": asks_opposite(question, template),
            "template": template, "horizon_days": horizon, "deadline": "", "kind": "yes_no", "statement": "", "prior": base_rate(template, horizon),
            "prior_reason": "Rough default for this type of event.", "by": "keywords"}

"""Optional AI reader for ask-anything mode (Google Gemini, free tier).

With a key, a language model does two jobs that keyword rules do badly:

  plan(question)  -> who the question is about, what event counts as YES,
                     the time window, and a starting value with a reason
  read(headlines) -> is the question still valid, has the event already
                     happened, and which distinct developments in the news
                     make the event more or less likely

The model never outputs the probability. It labels developments; the same
engine as everywhere else turns them into a number, so every result can be
traced to dated headlines.

Limits: the model can misjudge, and on a replay of a past date it may
remember what happened next even though it is told not to use that.
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from datetime import date, timedelta

from .cases import Case
from .evidence import Evidence
from .live import HALF_LIFE, TEMPLATES, Headline, reliability

API = "https://generativelanguage.googleapis.com/v1beta"
STRENGTH = {"weak": 1.3, "medium": 1.8, "strong": 3.0}  # analyst-set, same scale as the keyword rules
MAX_DEVELOPMENTS = 8
_model_cache: dict[str, list[str]] = {}
used: dict[str, str] = {}  # last model that answered, shown in the app


class AIError(RuntimeError):
    pass


def _http(url: str, key: str, body: dict | None = None, timeout: int = 40) -> dict:
    req = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"x-goog-api-key": key, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            msg = json.loads(e.read())["error"]["message"]
        except Exception:
            msg = str(e)
        raise AIError(f"AI service error {e.code}: {msg[:300]}") from e
    except Exception as e:
        raise AIError(f"Could not reach the AI service: {e}") from e


def rank_models(models: list[dict]) -> list[str]:
    """General-purpose Flash models from the service's own list, best first, so renames do not break the app."""
    found = []
    for m in models:
        name = m.get("name", "").split("/")[-1]
        if "generateContent" not in m.get("supportedGenerationMethods", []):
            continue
        v = re.fullmatch(r"gemini-(\d+(?:\.\d+)?)-flash(-lite)?", name)
        if v:  # skips image, audio, live, preview and experimental variants
            found.append(((0 if v.group(2) else 1, float(v.group(1))), name))  # full Flash before Lite, then newest
    if not found:
        raise AIError("No suitable Gemini Flash model is available for this key.")
    full = [n for (is_full, _), n in sorted(found, reverse=True) if is_full]
    lite = [n for (is_full, _), n in sorted(found, reverse=True) if not is_full]
    # newest full Flash first, then the newest Lite (faster, a good fallback when the first is slow or refused), then the rest
    return full[:1] + lite[:1] + full[1:] + lite[1:]


def pick_model(models: list[dict]) -> str:
    return rank_models(models)[0]


def ask(key: str, prompt: str, model: str | None = None, http=_http) -> dict:
    """Send one prompt, get parsed JSON back. Tries up to three models if one is refused (for example not on the free tier)."""
    if model:
        names = [model]
    else:
        if key not in _model_cache:
            _model_cache[key] = rank_models(http(f"{API}/models?pageSize=200", key).get("models", []))[:3]
        names = _model_cache[key]
    out, last = None, None
    for name in list(names):
        try:
            out = http(f"{API}/models/{name}:generateContent", key,
                       {"contents": [{"parts": [{"text": prompt}]}],
                        "generationConfig": {"temperature": 0, "responseMimeType": "application/json"}})
            if not model and names[0] != name:
                _model_cache[key] = [name] + [n for n in names if n != name]  # remember the one that works
            used["model"] = name
            break
        except AIError as e:
            last = e
    if out is None:
        raise last
    try:
        text = out["candidates"][0]["content"]["parts"][0]["text"]
        text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
        data = json.loads(text)
    except Exception as e:
        raise AIError("The AI service returned an answer that could not be read.") from e
    if not isinstance(data, dict):
        raise AIError("The AI service returned an answer in the wrong shape.")
    return data


# ------------------------------------------------------------------ plan
PLAN_PROMPT = """You set up a forecasting question for an early-warning tool. Today is {today}.

Question: "{question}"

Return JSON with exactly these keys:
- "kind": "who" if the question asks WHO or WHICH of several people or things will be chosen, win or be next (for example "who will be the next chief executive of Acme?"); otherwise "yes_no".
- "focus": for a "yes_no" question, the single person, company or country to search news for, as a news headline would write the name (proper capitalisation). For a "who" question, the short phrase a headline about this contest would contain (for example "Acme CEO"), correctly spelled.
- "related": up to 3 other names worth a lighter look (a rival, the organisation, a counterpart). May be empty.
- "event": one short sentence stating the EVENT that would count as it happening, phrased as a change (for example "Jane Doe stops being chief executive of Acme"), never as things staying the same.
- "asks_opposite": true if the question asks whether things will stay the same (so the answer to the question is 1 minus the chance of the event), else false.
- "template": the closest of {templates}.
- "horizon_days": the time window in days stated or implied by the question; 30 if none.
- "base_rate_percent": how often an event like this happens to comparable people or organisations over a window of that length in ordinary times, as a percentage between 0.1 and 50. Be sober: big events are rare.
- "base_rate_reason": one sentence explaining that number.
"""


def plan(key: str, question: str, today: date, http=_http) -> dict:
    d = ask(key, PLAN_PROMPT.format(today=today, question=question.replace('"', "'"), templates=list(TEMPLATES)), http=http)
    focus = str(d.get("focus", "")).strip()
    if not focus:
        raise AIError("The AI could not tell who or what the question is about.")
    try:
        horizon = int(d.get("horizon_days") or 30)
        rate = float(d.get("base_rate_percent") or 0)
    except (TypeError, ValueError):
        horizon, rate = 30, 0.0
    tpl = d.get("template") if d.get("template") in TEMPLATES else "custom"
    return {"focus": focus[:80], "related": [str(x).strip()[:80] for x in (d.get("related") or []) if str(x).strip()][:3],
            "event": str(d.get("event", "")).strip()[:200] or question, "asks_opposite": bool(d.get("asks_opposite")),
            "template": tpl, "horizon_days": min(365, max(1, horizon)),
            "prior": min(0.5, max(0.001, rate / 100)) if rate > 0 else None,
            "prior_reason": str(d.get("base_rate_reason", "")).strip()[:300], "by": "ai",
            "kind": "who" if d.get("kind") == "who" else "yes_no"}


# ------------------------------------------------------------------ read
READ_PROMPT = """You read news headlines for an early-warning tool. The cutoff date is {as_of}.
Use ONLY the headlines below. Do not use anything you know about events after {as_of}.

Question: "{question}"
Focus: {focus}
The event that would count as happening: {event}
Time window: the {horizon} days after {as_of}.

Headlines (id | date | outlet | headline), newest first:
{lines}

Return JSON with exactly these keys:
- "premise_ok": false if the headlines show the question no longer makes sense as of the cutoff (for example the person no longer holds the role asked about), else true.
- "premise_note": if premise_ok is false, one sentence saying why, with the date if known. Else "".
- "already_happened": true if the headlines show the event itself has already happened by the cutoff, else false.
- "developments": at most {maxdev} DISTINCT developments from the 28 days before the cutoff that genuinely make the event more or less likely than normal for this focus. Merge headlines about the same development into one. Ignore routine coverage, opinion, speculation without facts, and stories about other people. It is fine to return an empty list. Each item:
    {{"date": "YYYY-MM-DD" (latest headline about it), "summary": your own words, at most 20 words,
      "direction": "up" or "down" (effect on the chance of the event),
      "strength": "weak", "medium" or "strong" (strong only for direct, factual, well-sourced developments),
      "headline_ids": [ids]}}
- "summary": two or three plain sentences on what the recent news says about this question. Do not give a probability.
"""


def select_headlines(heads: list[Headline], as_of: date, recent: int = 160, older: int = 40) -> list[Headline]:
    """Headlines sent to the model: everything recent (capped) plus an even sample of older ones for context."""
    ok = sorted((h for h in heads if h.published <= as_of), key=lambda h: h.published, reverse=True)
    cut = as_of - timedelta(days=28)
    new = [h for h in ok if h.published > cut][:recent]
    old = [h for h in ok if h.published <= cut]
    step = max(1, len(old) // older) if old else 1
    return new + old[::step][:older]


def read(key: str, question: str, p: dict, heads: list[Headline], as_of: date, http=_http) -> tuple[dict, list[Headline]]:
    sent = select_headlines(heads, as_of)
    assert all(h.published <= as_of for h in sent)  # the date gate
    lines = "\n".join(f"{i} | {h.published} | {h.source} | {h.title}" for i, h in enumerate(sent)) or "(none)"
    d = ask(key, READ_PROMPT.format(as_of=as_of, question=question.replace('"', "'"), focus=p["focus"], event=p["event"],
                                    horizon=p["horizon_days"], lines=lines, maxdev=MAX_DEVELOPMENTS), http=http)
    devs = []
    for x in (d.get("developments") or [])[:MAX_DEVELOPMENTS]:
        if not isinstance(x, dict) or x.get("direction") not in ("up", "down") or x.get("strength") not in STRENGTH:
            continue
        ids = [i for i in (x.get("headline_ids") or []) if isinstance(i, int) and 0 <= i < len(sent)]
        if not ids:
            continue  # a development with no headline behind it is not used
        when = max(sent[i].published for i in ids)  # dated by its own headlines, never by the model
        devs.append({"date": when, "summary": str(x.get("summary", "")).strip()[:200], "direction": x["direction"],
                     "strength": x["strength"], "ids": ids})
    return ({"premise_ok": d.get("premise_ok") is not False, "premise_note": str(d.get("premise_note", "")).strip()[:300],
             "already_happened": bool(d.get("already_happened")), "developments": devs,
             "summary": str(d.get("summary", "")).strip()[:700]}, sent)


def build_case(question: str, focus: str, reading: dict, sent: list[Headline], prior_yes: float) -> Case:
    types, ev = {}, []
    for s, lr in STRENGTH.items():
        types[f"up_{s}"] = {"family": "ai_up", "lr": {"yes": lr}}
        types[f"down_{s}"] = {"family": "ai_down", "lr": {"yes": 1 / lr}}
    for n, dv in enumerate(reading["developments"]):
        hs = [sent[i] for i in dv["ids"]]
        ev.append(Evidence(f"d{n}", dv["date"], dv["date"], "focus", f"{dv['direction']}_{dv['strength']}", dv["summary"],
                           hs[0].link, max(reliability(h.source) for h in hs), ", ".join(sorted({h.source for h in hs})[:3])))
    catalog = {"types": types, "half_life_days": {**HALF_LIFE, "ai_up": 21, "ai_down": 21}, "watch_families": []}
    spec = {"name": question, "focus_entity": focus,
            "questions": [{"id": "q", "text": question, "kind": "live", "priors": {"yes": prior_yes, "no": 1 - prior_yes}}]}
    return Case("live_ai", spec, catalog, ev, {"focus": (1.0, 0)})


def diagnose(key: str, http=_http) -> list[dict]:
    """Try a tiny request on each candidate model and time it. For the 'Test the AI connection' button."""
    import time
    try:
        names = rank_models(http(f"{API}/models?pageSize=200", key).get("models", []))[:4]
    except AIError as e:
        return [{"Model": "(listing models)", "Result": str(e), "Seconds": None}]
    rows = []
    for name in names:
        t = time.time()
        try:
            ask(key, 'Return the JSON object {"ok": true}.', model=name, http=http)
            res = "works"
        except AIError as e:
            res = str(e)
        rows.append({"Model": name, "Result": res, "Seconds": round(time.time() - t, 1)})
    working = [r["Model"] for r in rows if r["Result"] == "works"]
    if working:
        _model_cache[key] = working + [n for n in names if n not in working]  # use the ones that work first
    return rows


# ------------------------------------------------------------------ "who" questions
OTHER = "Someone else"
WHO_PROMPT = """You read news headlines for an early-warning tool. The cutoff date is {as_of}.
Use the headlines below. Do not use anything you know about events after {as_of}.

Question: "{question}"

Headlines (id | date | outlet | headline), newest first:
{lines}

Return JSON with exactly these keys:
- "decided": true if the headlines show the answer has already been settled by the cutoff (for example a permanent appointment was announced), else false.
- "decided_note": if decided, one sentence saying who or what and when. Else "".
- "candidates": up to 6 plausible answers, most likely first. Each: {{"name": full name, "starting_percent": the chance you would give before looking at the last 28 days of news, from role, experience and how such choices usually go, "reason": one short sentence}}.
- "someone_else_percent": the starting chance that the answer is none of the candidates. Outsiders are chosen often; do not make this small.
- "developments": at most {maxdev} DISTINCT developments from the 28 days before the cutoff that make one candidate more or less likely. Each:
    {{"candidate": a name exactly as written in "candidates", "summary": your own words, at most 20 words,
      "direction": "up" or "down", "strength": "weak", "medium" or "strong" (strong only for direct, factual, well-sourced developments),
      "headline_ids": [ids]}}
  Being named interim or acting holder is a development; speculation and opinion pieces are weak at most.
- "summary": two or three plain sentences on where things stand. Do not give probabilities.
"""


def read_who(key: str, question: str, heads: list[Headline], as_of: date, http=_http) -> tuple[dict, list[Headline]]:
    sent = select_headlines(heads, as_of)
    assert all(h.published <= as_of for h in sent)  # the date gate
    lines = "\n".join(f"{i} | {h.published} | {h.source} | {h.title}" for i, h in enumerate(sent)) or "(none)"
    d = ask(key, WHO_PROMPT.format(as_of=as_of, question=question.replace('"', "'"), lines=lines, maxdev=10), http=http)
    cands, seen = [], set()
    for c in (d.get("candidates") or [])[:6]:
        name = str(c.get("name", "")).strip()[:60] if isinstance(c, dict) else ""
        if not name or name.lower() in seen or name == OTHER:
            continue
        seen.add(name.lower())
        try:
            pc = float(c.get("starting_percent") or 0)
        except (TypeError, ValueError):
            pc = 0.0
        cands.append({"name": name, "weight": min(90.0, max(1.0, pc)), "reason": str(c.get("reason", "")).strip()[:200]})
    if not cands:
        raise AIError("The AI could not find any candidates in the news for this question.")
    try:
        other = float(d.get("someone_else_percent") or 0)
    except (TypeError, ValueError):
        other = 0.0
    cands.append({"name": OTHER, "weight": min(90.0, max(10.0, other)), "reason": "Nobody on this list."})
    total = sum(c["weight"] for c in cands)
    for c in cands:
        c["prior"] = c["weight"] / total
    names = {c["name"] for c in cands}
    devs = []
    for x in (d.get("developments") or [])[:10]:
        if not isinstance(x, dict) or x.get("candidate") not in names or x.get("direction") not in ("up", "down") or x.get("strength") not in STRENGTH:
            continue
        ids = [i for i in (x.get("headline_ids") or []) if isinstance(i, int) and 0 <= i < len(sent)]
        if ids:
            devs.append({"candidate": x["candidate"], "date": max(sent[i].published for i in ids),
                         "summary": str(x.get("summary", "")).strip()[:200], "direction": x["direction"], "strength": x["strength"], "ids": ids})
    return ({"decided": bool(d.get("decided")), "decided_note": str(d.get("decided_note", "")).strip()[:300],
             "candidates": cands, "developments": devs, "summary": str(d.get("summary", "")).strip()[:700]}, sent)


def build_who_case(question: str, reading: dict, sent: list[Headline]) -> Case:
    types, ev = {}, []
    for n, dv in enumerate(reading["developments"]):
        lr = STRENGTH[dv["strength"]]
        t = f"dev{n}"
        types[t] = {"family": f"{dv['direction']}:{dv['candidate']}", "lr": {dv["candidate"]: lr if dv["direction"] == "up" else 1 / lr}}
        hs = [sent[i] for i in dv["ids"]]
        ev.append(Evidence(f"d{n}", dv["date"], dv["date"], "focus", t, dv["summary"], hs[0].link,
                           max(reliability(h.source) for h in hs), dv["candidate"]))
    half = {**HALF_LIFE, **{t["family"]: 30 for t in types.values()}}
    spec = {"name": question, "focus_entity": "focus",
            "questions": [{"id": "q", "text": question, "kind": "live", "priors": {c["name"]: c["prior"] for c in reading["candidates"]}}]}
    return Case("live_who", spec, {"types": types, "half_life_days": half, "watch_families": []}, ev, {"focus": (1.0, 0)})

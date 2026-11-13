"""Early-warning platform: web app.

Run locally:   streamlit run app.py
Deploy free:   see GUIDE.md
"""
from __future__ import annotations

import json
import os
import re
from datetime import date, timedelta

import pandas as pd
import streamlit as st

from ew.cases import answer, answer_with_range, backtest, list_cases, load_case
from ew.engine import Settings, V0
from ew.evidence import visible_as_of
from ew import ai, live

st.set_page_config(page_title="Early-warning platform", layout="wide")

FITTED = Settings(1.25, 0.9, 1.0)  # fitted to the two bundled cases; failed the out-of-sample check
WEAK = 0.3                          # if evidence shifts no answer by more than this (log-odds), flag it


@st.cache_resource
def get_case(key: str):
    return load_case(key)


def pct(x: float) -> str:
    return f"{x:.1%}" if x >= 0.0095 else f"{x:.2%}"


def label_of(q: dict, h: str) -> str:
    return q.get("labels", {}).get(h, h.replace("_", " ").capitalize())


def evidence_table(pairs) -> pd.DataFrame:
    return pd.DataFrame([{"Public on": e.public_date, "What happened": e.summary,
                          "Effect": round(c, 2), "Source": e.source} for e, c in pairs])


LINK = {"Source": st.column_config.LinkColumn("Source", display_text="open")}

# ---------------------------------------------------------------- sidebar
st.sidebar.title("Early-warning platform")
st.sidebar.caption("Prototype. Probabilities from dated public evidence, never certainties.")
page = st.sidebar.radio("What do you want to do?", ["Ask anything (live news)", "Worked examples (Iran, Nvidia)"])


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_news(focus: str, related: tuple, as_of: date, weeks: int):
    return live.collect(focus, list(related), as_of, weeks)


def ai_key() -> str:
    try:
        return str(st.secrets.get("GEMINI_API_KEY", "")).strip()
    except Exception:  # no secrets file at all
        return os.environ.get("GEMINI_API_KEY", "").strip()


@st.cache_data(ttl=3600, show_spinner=False)
def ai_plan(key: str, question: str, today: date):
    return ai.plan(key, question, today)


@st.cache_data(ttl=3600, show_spinner=False)
def ai_read_who(key: str, question: str, heads: tuple, as_of: date):
    return ai.read_who(key, question, list(heads), as_of)


@st.cache_data(ttl=3600, show_spinner=False)
def ai_read(key: str, question: str, plan_json: str, heads: tuple, as_of: date):
    return ai.read(key, question, json.loads(plan_json), list(heads), as_of)


def run_question(question: str, adv: dict) -> dict | None:
    """Do everything for one question: set up, fetch, read. Returns the stored result or None on failure."""
    key, notes = ai_key(), []
    plan = None
    if key:
        try:
            with st.spinner("Working out what the question is about..."):
                plan = dict(ai_plan(key, question, date.today()))
        except ai.AIError as err:
            notes.append(f"The AI reader was not available ({err}). Keyword rules were used instead.")
    if plan is None:
        if re.match(r"\s*(who|which|whom)\b", question, re.I):
            st.error("Questions that start with 'who' or 'which' need the AI reader, which is not available right now"
                     + (f" ({notes[0]})" if notes else ". Add a free Gemini key (see GUIDE.md)")
                     + ". Or ask a yes/no question, for example 'Will Jane Doe become CEO of Acme in the next 60 days?'")
            return None
        plan = live.auto_plan(question)
    if adv["focus"]:
        plan["focus"] = adv["focus"]
    if adv["related"]:
        plan["related"] = adv["related"]
    if adv["template"] != "auto":
        plan["template"] = adv["template"]
    if adv["days"]:
        plan["horizon_days"] = adv["days"]
    if adv["prior"] is not None:
        plan["prior"], plan["prior_reason"] = adv["prior"], "Set by you."
    if not plan.get("prior"):
        plan["prior"] = live.base_rate(plan["template"], plan["horizon_days"])
        plan["prior_reason"] = "Rough default for this type of event."
    if not plan["focus"]:
        st.error("I could not tell who or what the question is about. Name the person, company or country in the question, "
                 "or type it under Advanced.")
        return None
    as_of = adv["as_of"]
    try:
        with st.spinner(f"Reading {adv['weeks']} weeks of headlines about {plan['focus']}..."):
            heads, counts, used = fetch_news(plan["focus"], tuple(plan["related"]), as_of, adv["weeks"])
    except Exception as err:
        st.error(f"Could not fetch news right now. Wait a minute and try again. Details: {err}")
        return None
    reading = sent = None
    if plan.get("kind") == "who":
        if not heads:
            st.error(f"No headlines came back for '{plan['focus']}'. Type a search phrase under Advanced (Who or what is it about).")
            return None
        try:
            with st.spinner("Reading the headlines and listing the candidates..."):
                reading, sent = ai_read_who(key, question, tuple(heads), as_of)
        except ai.AIError as err:
            st.error(f"The AI reader could not answer this 'who' question ({err}). Try again in a minute.")
            return None
    elif key and plan.get("by") == "ai" and heads:
        try:
            with st.spinner("Reading the headlines..."):
                reading, sent = ai_read(key, question, json.dumps(plan, sort_keys=True), tuple(heads), as_of)
        except ai.AIError as err:
            notes.append(f"The AI reader failed on the headlines ({err}). Keyword rules were used instead.")
    return dict(question=question, plan=plan, heads=heads, counts=counts, used=used, as_of=as_of, weeks=adv["weeks"],
                reading=reading, sent=sent, notes=notes, yes=adv["yes"], no=adv["no"])


def render_who(r: dict):
    """Result page for 'who will...' questions: several candidates instead of yes or no."""
    reading, as_of, sent = r["reading"], r["as_of"], r["sent"]
    case = ai.build_who_case(r["question"], reading, sent)
    probs, lo, hi, detail, _ = answer_with_range(case, "q", as_of)
    order = sorted(probs, key=lambda h: -probs[h])
    named = [h for h in order if h != ai.OTHER]
    top = named[0]
    st.divider()
    st.subheader(r["question"])
    st.caption(f"Searched news for: {r['plan']['focus']}. Using news published by {as_of:%d %B %Y}. "
               f"News source: {', '.join(r['used'])}. Headlines read by an AI model ({ai.used.get('model', 'Gemini')}).")
    if reading["decided"]:
        st.error("The news suggests this has already been decided. " + reading["decided_note"])
    else:
        st.markdown(f"### The most likely answer is {top}, with a probability of {pct(probs[top])}.")
        nxt = f" Next is {named[1]} at {pct(probs[named[1]])}." if len(named) > 1 else ""
        st.markdown(f"Under nearby settings {top} ranges from {pct(lo[top])} to {pct(hi[top])}.{nxt} "
                    f"The chance it is someone not on this list is {pct(probs[ai.OTHER])}.")
    if reading["summary"]:
        st.markdown(f"**What the news says.** {reading['summary']}")
    pri = {c["name"]: c for c in reading["candidates"]}
    st.dataframe(pd.DataFrame([{"Candidate": h, "Probability": pct(probs[h]), "Range": f"{pct(lo[h])} to {pct(hi[h])}",
                                "Starting value": pct(pri[h]["prior"]), "Why this starting value": pri[h]["reason"]} for h in order]),
                 hide_index=True, width="stretch")
    st.caption("Experimental. The candidates and starting values are suggested by an AI model from the headlines and general "
               "knowledge; the engine then adjusts them using the developments below. No track record.")
    t_why, t_time, t_all, t_lim = st.tabs(["Why", "Over time", "All headlines", "Limits"])
    with t_why:
        if reading["developments"]:
            st.dataframe(pd.DataFrame([{"Date": dv["date"], "Candidate": dv["candidate"], "Development": dv["summary"],
                                        "Pushes their chance": "Up" if dv["direction"] == "up" else "Down", "Strength": dv["strength"],
                                        "Source": sent[dv["ids"][0]].link} for dv in reading["developments"]]),
                         hide_index=True, column_config=LINK, width="stretch")
            for dv in reading["developments"]:
                with st.expander(f"Headlines behind: {dv['candidate']}: {dv['summary']}"):
                    for i in dv["ids"][:8]:
                        st.markdown(f"- {sent[i].published}: [{sent[i].title}]({sent[i].link}) ({sent[i].source})")
        else:
            st.caption("No development in the last four weeks favours one candidate. The numbers are the starting values.")
    with t_time:
        days_ = [as_of - timedelta(days=i) for i in range(41, -1, -2)]
        st.line_chart(pd.DataFrame([{"Date": d, **answer(case, "q", d)[0]} for d in days_]).set_index("Date"), y_label="Probability")
        st.caption("Each point uses only developments published by that day. The candidate list itself is today's.")
    with t_all:
        st.dataframe(pd.DataFrame([{"Date": h.published, "Headline": h.title, "Outlet": h.source, "Source": h.link}
                                   for h in sorted(r["heads"], key=lambda h: h.published, reverse=True)]),
                     hide_index=True, column_config=LINK, width="stretch")
    with t_lim:
        st.markdown("""
- **The candidate list comes from an AI model** reading headlines. A real candidate who is not in the news will be missing; that is what "Someone else" is for.
- **Starting values are the model's judgment**, not measured rates. The final numbers depend heavily on them.
- **Headlines only, public news only.** Boards decide in private.
- **No track record.** Use this to see who the news points to and why, then judge for yourself.
""")
    log = {"question": r["question"], "as_of": str(as_of), "probabilities": {h: round(probs[h], 4) for h in order},
           "reader": "ai", "engine": "0.6 live"}
    st.download_button("Download this forecast (keep it to score later)", json.dumps(log, indent=2),
                       file_name=f"forecast_{as_of}.json", mime="application/json")


def ask_page():
    st.title("Ask anything")
    has_ai = bool(ai_key())
    st.caption("Type a question about a person, company or country and press Analyse. The app works out the rest, "
               "reads dated public news headlines, and estimates the chance. Experimental: see the Limits tab.")
    question = st.text_input("Your question", placeholder="Will Jane Doe step down as CEO of Acme in the next 30 days?   or   Who will be the next CEO of Acme?")
    with st.expander("Advanced (optional: everything here is filled in automatically)"):
        c1, c2 = st.columns(2)
        focus_in = c1.text_input("Who or what is it about", placeholder="automatic")
        related_in = c2.text_input("Related names to check less deeply (comma-separated)", placeholder="automatic")
        c1, c2, c3 = st.columns(3)
        template = c1.selectbox("Type of event", ["auto"] + list(live.TEMPLATES),
                                format_func=lambda k: "Automatic" if k == "auto" else live.TEMPLATES[k]["name"])
        days = c2.number_input("Within how many days (0 = automatic)", 0, 365, 0)
        as_of = c3.date_input("Use only news published by the end of", value=date.today(), max_value=date.today(),
                              help="Pick a past date to replay history without showing the app what happened next.")
        own = st.checkbox("Set my own starting value")
        prior = st.slider("Starting value (%)", 0.1, 50.0, 1.0, 0.1, disabled=not own,
                          help="How often this kind of event happens in a period this long when nothing special is going on.")
        yes_w = st.text_input("Extra clue words pointing to YES (keyword mode only)")
        no_w = st.text_input("Extra clue words pointing to NO (keyword mode only)")
        weeks = st.select_slider("How far back to read", [9, 10, 13, 26], value=10, format_func=lambda w: f"{w} weeks")
        if has_ai and st.button("Test the AI connection"):
            with st.spinner("Testing..."):
                st.dataframe(pd.DataFrame(ai.diagnose(ai_key())), hide_index=True, width="stretch")
            st.cache_data.clear()
    if not has_ai:
        st.caption("Running in keyword mode. Add a free Gemini key (see GUIDE.md) and the app will read headlines with an AI model.")

    if st.button("Analyse", type="primary"):
        if not question.strip():
            st.error("Type a question first.")
        else:
            adv = dict(focus=focus_in.strip(), related=[x.strip() for x in related_in.split(",") if x.strip()][:5],
                       template=template, days=int(days), prior=prior / 100 if own else None, as_of=as_of, weeks=weeks,
                       yes=yes_w.split(","), no=no_w.split(","))
            out = run_question(question.strip(), adv)
            if out:
                st.session_state["ask"] = out
    r = st.session_state.get("ask")
    if not r:
        return

    plan, as_of, reading = r["plan"], r["as_of"], r["reading"]
    if plan.get("kind") == "who":
        render_who(r)
        return
    focus, prior0 = plan["focus"], plan["prior"]
    tagged, kinds = live.tag_headlines(r["heads"], plan["template"], r["yes"], r["no"])
    k_p, k_lo, k_hi, k_detail, info = live.forecast(r["question"], focus, tagged, kinds, r["counts"], as_of, prior0)
    if reading:
        case = ai.build_case(r["question"], focus, reading, r["sent"], prior0)
        probs, lo, hi, detail, _ = answer_with_range(case, "q", as_of)
        p_yes, lo_yes, hi_yes, n_sig = probs["yes"], lo["yes"], hi["yes"], len(reading["developments"])
    else:
        p_yes, lo_yes, hi_yes, n_sig = k_p, k_lo, k_hi, info["signals"]

    st.divider()
    st.subheader(r["question"])
    for note in r["notes"]:
        st.warning(note)
    st.caption(f"Focus: {focus}" + (f" (also checked: {', '.join(plan['related'])})" if plan["related"] else "")
               + f". Window: {plan['horizon_days']} days from {as_of:%d %B %Y}. News source: {', '.join(r['used'])}. "
               + (f"Headlines read by an AI model ({ai.used.get('model', 'Gemini')})." if reading else "Headlines read by keyword rules."))
    stale = bool(reading) and (not reading["premise_ok"] or reading["already_happened"])
    if reading and not reading["premise_ok"]:
        st.error("This question looks out of date. " + (reading["premise_note"] or "The news suggests its premise no longer holds.")
                 + " The number below is not meaningful.")
    elif (reading and reading["already_happened"]) or (not reading and info["maybe_happened"]):
        st.error("The news suggests this event has already happened. Check the headlines; the number below is not meaningful.")
    ev_txt = plan["event"].rstrip(".")
    if not stale:
        st.markdown(f"### There is a {pct(p_yes)} probability of this event in the next {plan['horizon_days']} days: {ev_txt}.")
        if n_sig == 0:
            why = "Nothing in the recent news changes the picture, so this is the starting value."
        else:
            move = "raised" if p_yes > prior0 else "lowered"
            why = f"The news {move} it from a starting value of {pct(prior0)}. Under nearby settings it ranges from {pct(lo_yes)} to {pct(hi_yes)}."
        st.markdown(why)
    if reading and reading["summary"]:
        st.markdown(f"**What the news says.** {reading['summary']}")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Chance the event happens", "n/a" if stale else pct(p_yes))
    if not stale:
        m1.caption(f"Range {pct(lo_yes)} to {pct(hi_yes)}")
    m2.metric("Starting value", pct(prior0), help=plan.get("prior_reason", ""))
    m2.caption(plan.get("prior_reason", ""))
    m3.metric("Headlines read", info["read"])
    m4.metric("Developments that counted" if reading else "Unusual signals", n_sig)
    if plan.get("asks_opposite") and not stale:
        st.info(f"Your question asks whether things stay as they are. That is the opposite of the event, "
                f"so the answer to your question is about {pct(1 - p_yes)}.")
    if info["read"] == 0:
        st.warning("No headlines came back. Check the spelling of the name, or type a shorter one under Advanced.")
    st.caption("Experimental. No track record. Not a validated forecast.")

    t_why, t_cov, t_time, t_all, t_lim = st.tabs(["Why", "Coverage", "Over time", "All headlines", "Limits"])
    with t_why:
        if reading:
            eff = {e.id: c for e, c in detail["yes"]}
            if reading["developments"]:
                st.dataframe(pd.DataFrame([{
                    "Date": dv["date"], "Development": dv["summary"],
                    "Pushes the chance": "Up" if dv["direction"] == "up" else "Down", "Strength": dv["strength"],
                    "Effect": round(eff.get(f"d{n}", 0.0), 2), "Headlines": len(dv["ids"]),
                    "Source": r["sent"][dv["ids"][0]].link} for n, dv in enumerate(reading["developments"])]),
                    hide_index=True, column_config=LINK, width="stretch")
                for n, dv in enumerate(reading["developments"]):
                    with st.expander(f"Headlines behind: {dv['summary']}"):
                        for i in dv["ids"][:8]:
                            h = r["sent"][i]
                            st.markdown(f"- {h.published}: [{h.title}]({h.link}) ({h.source})")
                st.caption("Each development was picked out by the AI model from the headlines shown. Open them and judge for yourself.")
            else:
                st.caption("The AI model found no development in the last four weeks that changes the chance.")
        rows = [x for x in info["rows"] if x["recent"] > 0]
        box = st.expander("Keyword check (the simpler method, for comparison)") if reading else st.container()
        with box:
            if reading:
                st.caption(f"Keyword rules alone give {pct(k_p)} (range {pct(k_lo)} to {pct(k_hi)}).")
            effect = {e.id: c for e, c in k_detail}
            if rows:
                st.dataframe(pd.DataFrame([{
                    "Kind of story": live.LABELS.get(x["signal"], x["signal"]),
                    "About": focus if x["group"] == "focus" else "related names",
                    "Last 14 days": f"{x['recent']} of {x['recent_total']} ({x['recent'] / x['recent_total']:.0%})",
                    "Usual share": "unknown" if x["usual_share"] is None else f"{x['usual_share']:.0%}",
                    "Counted": "Yes" if x["counted"] else "No, within normal",
                    "Effect": round(effect.get(f"{x['signal']}@{x['group']}", 0.0), 2)}
                    for x in sorted(rows, key=lambda x: (-x["counted"], -x["recent"]))]), hide_index=True, width="stretch")
                if not reading:
                    for x in rows:
                        if x["counted"]:
                            with st.expander(f"Example headlines: {live.LABELS.get(x['signal'], x['signal'])}"):
                                for h in x["examples"]:
                                    st.markdown(f"- {h.published}: [{h.title}]({h.link}) ({h.source})")
            else:
                st.caption("No recent headline matched a keyword clue for this type of event.")
    with t_cov:
        ends = [as_of - timedelta(days=7 * w) for w in range(len(r["counts"]) - 1, -1, -1)]
        st.bar_chart(pd.DataFrame({"Week ending": ends, "Headlines": r["counts"]}).set_index("Week ending"))
        if info["saturated"]:
            st.caption("This name fills the search limit of about 100 headlines almost every week, so a change in attention cannot be measured.")
        elif info["attention_z"] is None:
            st.caption("Not enough weeks to judge whether attention is unusual.")
        else:
            st.caption(f"Latest week against this name's own normal: z = {info['attention_z']:.1f} "
                       "(about 0 is normal, 3 or more is unusual).")
    with t_time:
        days_ = [as_of - timedelta(days=i) for i in range(min(42, 7 * r["weeks"] - 21) - 1, -1, -2)]
        if reading:
            ys = [answer(case, "q", d)[0]["yes"] for d in days_]
        else:
            ys = [live.forecast(r["question"], focus, tagged, kinds, [], d, prior0)[0] for d in days_]
        st.line_chart(pd.DataFrame({"Date": days_, "Chance the event happens": ys}).set_index("Date"), y_label="Probability")
        st.caption("Each point uses only what was published by that day.")
    with t_all:
        st.dataframe(pd.DataFrame([{"Date": h.published, "Headline": h.title, "Outlet": h.source,
                                    "Found by": focus if h.query == "focus" else h.query, "Source": h.link}
                                   for h in sorted(r["heads"], key=lambda h: h.published, reverse=True)]),
                     hide_index=True, column_config=LINK, width="stretch")
    with t_lim:
        st.markdown("""
- **It reads headlines, not articles**, and only public news. Private knowledge is invisible. In the Nvidia example the number stayed near the starting value until the story was reported.
- **With the AI reader:** a language model picks out the developments and suggests the starting value. It can misjudge. It never sets the final number; the engine does, from the developments listed under Why.
- **Without it:** headlines are tagged by keywords, and a kind of story counts only if it is clearly more common in the last 14 days than before.
- **The starting value is a judgment**, and the final number depends heavily on it.
- **Replays are not fully blind.** A past date hides later headlines, but today's search engine chooses which old headlines to return, and an AI model may remember what happened next.
- **At most about 100 headlines per week** are read for the focus, in English.
- **No track record.** Nothing here has been scored against outcomes. Use it to organise what the news says, then judge for yourself.
- **People.** A probability is not an accusation. Use this for public figures and organisations.
""")
    log = {"question": r["question"], "focus": focus, "event": plan["event"], "as_of": str(as_of),
           "horizon_days": plan["horizon_days"], "starting_value": prior0, "probability": None if stale else round(p_yes, 4),
           "low": round(lo_yes, 4), "high": round(hi_yes, 4), "headlines_read": info["read"],
           "reader": "ai" if reading else "keywords", "engine": "0.5 live"}
    st.download_button("Download this forecast (keep it to score later)", json.dumps(log, indent=2),
                       file_name=f"forecast_{as_of}.json", mime="application/json")


if page.startswith("Ask"):
    ask_page()
    st.stop()

keys = list_cases()
names = {k: get_case(k).spec["name"] for k in keys}
key = st.sidebar.selectbox("Case", keys, format_func=lambda k: names[k])
case = get_case(key)

questions = case.spec["questions"]
qid = st.sidebar.selectbox("Question", [q["id"] for q in questions],
                           format_func=lambda i: case.question(i)["text"])
q = case.question(qid)

dated = [e.public_date for e in case.evidence if e.public_date]
first, last = min(dated), max(dated)
if q["kind"] == "backtest":
    default = date.fromisoformat(q["as_of_dates"][-1])
elif q["kind"] == "live":
    default = date.fromisoformat(q["logged_on"])
else:
    default = last
as_of = st.sidebar.date_input("Show only what was public by the end of", value=default,
                              min_value=first - timedelta(days=1), max_value=max(last, default))

mode = st.sidebar.radio("Engine settings", ["Default", "Fitted to these two cases (not validated)"])
settings = V0 if mode == "Default" else FITTED
leak = st.sidebar.checkbox("Reveal what hindsight would add", value=False,
                           help="Breaks the date gate on purpose, to show how much later-disclosed facts would change the number.")
st.sidebar.caption(f"Settings: {settings.label()}")

# ---------------------------------------------------------------- headline
st.title(case.spec["name"])
st.subheader(q["text"])
st.caption(f"Using only records public by the end of {as_of:%d %B %Y}. Focus of the investigation: "
           f"{case.spec['focus_entity'].replace('_', ' ')}.")

probs, lo, hi, detail, n_vis = answer_with_range(case, qid, as_of, settings)
ordered = sorted(probs, key=lambda h: -probs[h])
cols = st.columns(len(ordered))
for col, h in zip(cols, ordered):
    col.metric(label_of(q, h), pct(probs[h]), help=f"Starting value {pct(q['priors'][h])}")
    col.caption(f"Range {pct(lo[h])} to {pct(hi[h])}")
st.caption("The range shows how far the number moves under nearby engine settings. It does not include "
           "uncertainty in the starting values or in which evidence was collected.")

lead = ordered[0] if q["kind"] != "backtest" else q["outcome"]["hypothesis"]
if max(abs(sum(c for _, c in detail[h])) for h in probs) < WEAK:
    st.info("Very little evidence bears on this question at this date. These numbers are essentially the starting values.")

for d in case.spec.get("derived", []):
    p = 1.0
    for dq, dh in d["product_of"]:
        p *= answer(case, dq, as_of, settings)[0][dh]
    st.metric(d["text"], pct(p), help="Product of the linked questions")

if leak:
    lp, _, ln = answer(case, qid, as_of, settings, leak=True)
    st.warning(f"With hindsight ({ln - n_vis} extra records that were not public at this date): "
               + ", ".join(f"{label_of(q, h)} {pct(lp[h])}" for h in ordered))

tab_why, tab_time, tab_record, tab_open, tab_add, tab_about = st.tabs(
    ["Why", "Over time", "Track record", "Open forecasts", "Add evidence", "How it works"])

# ---------------------------------------------------------------- why
with tab_why:
    st.markdown(f"**Evidence moving “{label_of(q, lead)}”**")
    up = [(e, c) for e, c in detail[lead] if c > 0][:8]
    down = [(e, c) for e, c in detail[lead] if c < 0][:8]
    a, b = st.columns(2)
    a.markdown("Pushing it up")
    if up:
        a.dataframe(evidence_table(up), hide_index=True, column_config=LINK, width="stretch")
    else:
        a.caption("Nothing yet.")
    b.markdown("Pushing it down")
    if down:
        b.dataframe(evidence_table(down), hide_index=True, column_config=LINK, width="stretch")
    else:
        b.caption("Nothing yet.")

    vis = visible_as_of(case.evidence, as_of)
    watch = [e for e in vis if case.catalog["types"][e.type]["family"] in case.catalog.get("watch_families", [])]
    if watch:
        st.markdown("**Watchlist: weak signals worth a human look**")
        st.caption("These barely move the probability, but they are the kind of early clue that later mattered.")
        st.dataframe(pd.DataFrame([{"Public on": e.public_date, "What happened": e.summary, "Source": e.source} for e in watch]),
                     hide_index=True, column_config=LINK, width="stretch")

    with st.expander(f"All {len(vis)} records visible at this date"):
        st.dataframe(pd.DataFrame([{"Public on": e.public_date, "Who": e.entity.replace("_", " "),
                                    "Signal": e.type.replace("_", " "), "What happened": e.summary, "Source": e.source}
                                   for e in sorted(vis, key=lambda e: e.public_date, reverse=True)]),
                     hide_index=True, column_config=LINK, width="stretch")

# ---------------------------------------------------------------- over time
with tab_time:
    days = [first + timedelta(days=i) for i in range((max(last, as_of) - first).days + 1)]
    series = pd.DataFrame([{"Date": d, **{label_of(q, h): answer(case, qid, d, settings)[0][h] for h in probs}} for d in days])
    st.line_chart(series.set_index("Date"), y_label="Probability")
    st.caption("Each point uses only what was public on that day.")

# ---------------------------------------------------------------- track record
with tab_record:
    bts = [x for x in questions if x["kind"] == "backtest"]
    if not bts:
        st.caption("This case has no scored history yet.")
    for bq in bts:
        res = backtest(case, bq["id"], settings)
        st.markdown(f"**{bq['text']}**")
        st.dataframe(pd.DataFrame([{"Cutoff": r["as_of"], "Forecast": pct(r["p"]), "Range": f"{pct(r['low'])} to {pct(r['high'])}",
                                    "Records": r["visible"], "Happened in window": "Yes" if r["happened"] else "No"}
                                   for r in res["rows"]]), hide_index=True, width="stretch")
        c1, c2, c3 = st.columns(3)
        c1.metric("Brier score (lower is better)", f"{res['brier']:.3f}")
        c2.metric("Starting value alone", f"{res['brier_base_rate']:.3f}")
        c3.metric("Always saying 50%", "0.250")
    st.caption("One case is roughly one observation. A track record needs many cases and forecasts logged before outcomes.")

# ---------------------------------------------------------------- open forecasts
with tab_open:
    lives = [x for x in questions if x["kind"] == "live"]
    if not lives:
        st.caption("No open forecasts in this case.")
    rows = []
    for lq in lives:
        d = date.fromisoformat(lq["logged_on"])
        p, l, h_, _, _ = answer_with_range(case, lq["id"], d, settings)
        for h in sorted(p, key=lambda x: -p[x]):
            if h == "no":
                continue
            rows.append({"Question": lq["text"], "Answer": label_of(lq, h), "Forecast": pct(p[h]),
                         "Starting value": pct(lq["priors"][h]), "Logged": lq["logged_on"], "Resolves by": lq["resolve_by"]})
    if rows:
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
        st.caption("Logged before the outcome is known. Score them on the resolution date; never edit a logged forecast.")

# ---------------------------------------------------------------- add evidence
with tab_add:
    st.markdown("Fill this in to create a new evidence record, then paste it into the case's `evidence.json` on GitHub.")
    with st.form("add"):
        c1, c2 = st.columns(2)
        ev_date = c1.date_input("Date the event happened", value=date.today())
        pub_date = c2.date_input("Date it became public", value=date.today())
        entity = c1.selectbox("Who is it about", sorted(case.relevance, key=lambda k: -case.relevance[k][0]),
                              format_func=lambda k: f"{k.replace('_', ' ')} (relevance {case.relevance[k][0]:.2f})")
        stype = c2.selectbox("Signal type", sorted(case.catalog["types"]), format_func=lambda k: k.replace("_", " "))
        summary = st.text_input("One-line summary, in your own words")
        source = st.text_input("Source link")
        rel = st.slider("How reliable is the source", 0.3, 1.0, 0.8, 0.1)
        ok = st.form_submit_button("Create record")
    if ok:
        if not summary or not source.startswith("http"):
            st.error("Add a summary and a source link that starts with http.")
        elif pub_date < ev_date:
            st.error("Something cannot become public before it happens.")
        else:
            rec = {"id": f"u{len(case.evidence) + 1:03d}", "event_date": str(ev_date), "public_date": str(pub_date),
                   "entity": entity, "type": stype, "summary": summary, "source": source, "reliability": rel}
            st.code(json.dumps(rec, ensure_ascii=False) + ",", language="json")
            st.caption("Copy the line above and paste it just before the last ] in the file.")

# ---------------------------------------------------------------- about
with tab_about:
    st.markdown("""
**What this does.** You pick a focus and a question. The engine starts from a base rate, then shifts it with each
dated public record. A record counts more when its source is reliable, when it is close to the focus, when it is
fresh, and when it is not a repeat of something already counted.

**The date gate.** A record is used only if it was public by the cutoff date. Records that became public later,
or whose publication date is unknown, are never used. That is what makes a replay of the past honest.

**What it is not.**
- It cannot see private knowledge. In the Nvidia case the number stayed near 0.5% until the story was reported.
- The signal strengths are an analyst's starting values, not measured from data.
- The evidence was collected by hand. A real system collects everything automatically.
- Two cases are not a track record.

**How it gets better.** Add more past cases, including ones where nothing happened. `python run_all.py` then
re-checks whether fitted settings beat the defaults on cases they have not seen.
""")

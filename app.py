"""Early-warning platform: web app.

Run locally:   streamlit run app.py
Deploy free:   see GUIDE.md
"""
from __future__ import annotations

import json
import os
import re
from datetime import date, timedelta

from pathlib import Path

import pandas as pd
import streamlit as st

from ew.cases import answer, answer_with_range, backtest, list_cases, load_case
from ew.engine import V0
from ew.evidence import visible_as_of
from ew import ai, live
from ew.sources import support, tier
from ew.present import approx, band, odds_shift, pack, range_text, show, unpack
from ew import selftest
from ew import style

st.set_page_config(page_title="Early Warning: public-evidence forecasting", layout="wide")
st.markdown(style.CSS, unsafe_allow_html=True)

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
try:
    SITE = json.loads((Path(__file__).parent / "configs" / "site.json").read_text())
except Exception:
    SITE = {}
NAME = SITE.get("product_name") or "Early Warning"
st.sidebar.markdown(style.brand(NAME, SITE.get("tagline") or "Public-evidence forecasting"), unsafe_allow_html=True)
PAGES = ["Home", "Analyse", "Worked examples", "Scorecard", "Method", "Contact"]
page = st.sidebar.radio("Go to", PAGES, key="page")


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_news(focus: str, related: tuple, as_of: date, weeks: int):
    return live.collect(focus, list(related), as_of, weeks)


def ai_key() -> str:
    try:
        return str(st.secrets.get("GEMINI_API_KEY", "")).strip()
    except Exception:  # no secrets file at all
        return os.environ.get("GEMINI_API_KEY", "").strip()


@st.cache_data(ttl=3600, show_spinner=False)
def ai_plan(question: str, today: date, context: str = ""):
    return ai.plan(ai_key(), question, today, context=context)


@st.cache_data(ttl=3600, show_spinner=False)
def ai_read_who(question: str, heads: tuple, as_of: date):
    return ai.read_who(ai_key(), question, list(heads), as_of)


@st.cache_data(ttl=3600, show_spinner=False)
def ai_read(question: str, plan_json: str, heads: tuple, as_of: date):
    return ai.read(ai_key(), question, json.loads(plan_json), list(heads), as_of)


def run_question(question: str, adv: dict) -> dict | None:
    """Do everything for one question: set up, fetch, read. Returns the stored result or None on failure."""
    key, notes = ai_key(), []
    plan = None
    if key:
        try:
            with st.spinner("Working out what the question is about..."):
                plan = dict(ai_plan(question, date.today(), adv.get("context", "")))
        except ai.AIError as err:
            notes.append(f"The AI reader was not available ({err}). Keyword rules were used instead.")
    if plan is not None and plan.get("kind") == "unsupported":
        st.warning("This tool cannot answer that question. " + plan["reason"])
        if plan["suggestion"]:
            st.info(f"Try this instead: **{plan['suggestion']}**")
        return None
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
    as_of = adv["as_of"]
    if adv["days"]:
        plan["deadline"] = (as_of + timedelta(days=adv["days"])).isoformat()
    elif not plan.get("deadline"):
        plan["deadline"] = (as_of + timedelta(days=plan["horizon_days"])).isoformat()
    plan["horizon_days"] = max(1, (date.fromisoformat(plan["deadline"]) - as_of).days)
    if adv["prior"] is not None:
        plan["prior"], plan["prior_reason"] = adv["prior"], "Set by you."
    if not plan.get("prior"):
        plan["prior"] = live.base_rate(plan["template"], min(365, plan["horizon_days"]))
        plan["prior_reason"] = "Rough default for this type of event."
    asked, question = question, plan.get("restated") or question
    if not plan["focus"]:
        st.error("I could not tell who or what the question is about. Name the person, company or country in the question, "
                 "or type it under Advanced.")
        return None
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
                reading, sent = ai_read_who(question, tuple(heads), as_of)
        except ai.AIError as err:
            st.error(f"The AI reader could not answer this 'who' question ({err}). Try again in a minute.")
            return None
    elif key and plan.get("by") == "ai" and heads:
        try:
            with st.spinner("Reading the headlines..."):
                reading, sent = ai_read(question, json.dumps(plan, sort_keys=True), tuple(heads), as_of)
        except ai.AIError as err:
            notes.append(f"The AI reader failed on the headlines ({err}). Keyword rules were used instead.")
    return dict(model=ai.used.get("model", "Gemini"), question=question, asked=asked, plan=plan, heads=heads, counts=counts, used=used, as_of=as_of, weeks=adv["weeks"],
                reading=reading, sent=sent, notes=notes, yes=adv["yes"], no=adv["no"])


def src_label(outlets: list[str]) -> str:
    n = len({o.lower() for o in outlets})
    return f"{support(outlets)[1]} ({n} outlet{'s' if n != 1 else ''})"


def render_who(r: dict):
    """Result page for 'who will...' questions: several candidates instead of yes or no."""
    reading, as_of, sent = r["reading"], r["as_of"], r["sent"]
    case = ai.build_who_case(r["question"], reading, sent)
    probs, lo, hi, detail, _ = answer_with_range(case, "q", as_of)
    assert abs(sum(probs.values()) - 1) < 1e-6  # one coherent distribution over the candidates
    base = {c["name"]: c["prior"] for c in reading["candidates"]}
    for name in base:  # widen each range for a starting value half or twice as likely
        for f in (0.5, 2.0):
            alt = dict(base)
            alt[name] = odds_shift(base[name], f)
            rest = sum(v for k, v in base.items() if k != name)
            for k in alt:
                if k != name:
                    alt[k] = base[k] * (1 - alt[name]) / rest
            reading_alt = {**reading, "candidates": [{**c, "prior": alt[c["name"]]} for c in reading["candidates"]]}
            v = answer(ai.build_who_case(r["question"], reading_alt, sent), "q", as_of)[0][name]
            lo[name], hi[name] = min(lo[name], v), max(hi[name], v)
    order = sorted(probs, key=lambda h: -probs[h])
    named = [h for h in order if h != ai.OTHER]
    top = named[0]
    st.divider()
    if r.get("asked") and r["asked"].strip().lower().rstrip("?") != r["question"].strip().lower().rstrip("?"):
        st.caption(f"You typed: “{r['asked']}”. Understood as the question above. If that is not what you meant, rephrase and run it again.")
    st.caption(f"Searched news for: {r['plan']['focus']}. Using news published by {as_of:%d %B %Y}. "
               f"News source: {', '.join(r['used'])}. Headlines read by an AI model ({r.get('model', 'Gemini')}).")
    if reading["decided"]:
        st.error("The news suggests this has already been decided. " + reading["decided_note"])
    else:
        st.markdown(style.brief_who(r["question"], [(h, approx(probs[h]), probs[h], lo[h], hi[h], h == ai.OTHER) for h in order]),
                    unsafe_allow_html=True)
        st.markdown(f"{top} ranges from {range_text(lo[top], hi[top])}. The chance it is someone not on this list is {approx(probs[ai.OTHER])}. "
                    "Ranges cover nearby engine settings and a starting value half or twice as likely.")
    if reading["summary"]:
        st.markdown(style.note("What the news says.", reading["summary"]), unsafe_allow_html=True)
    pri = {c["name"]: c for c in reading["candidates"]}
    st.dataframe(pd.DataFrame([{"Candidate": h, "Estimate": approx(probs[h]), "Range": range_text(lo[h], hi[h]),
                                "Starting value": show(pri[h]["prior"]), "Why this starting value": pri[h]["reason"]} for h in order]),
                 hide_index=True, width="stretch")
    st.caption("Experimental. The candidates and starting values are suggested by an AI model from the headlines and general "
               "knowledge; the engine then adjusts them using the developments below. No track record.")
    t_why, t_time, t_all, t_lim = st.tabs(["Why", "Over time", "All headlines", "Limits"])
    with t_why:
        if reading["developments"]:
            st.markdown(style.ledger([{"date": dv["date"], "who": dv["candidate"], "text": dv["summary"], "effect": dv["direction"],
                                       "effect_label": "Raises their chance" if dv["direction"] == "up" else "Lowers their chance",
                                       "strength": dv["strength"], "sources": src_label([sent[i].source for i in dv["ids"]]),
                                       "url": sent[dv["ids"][0]].link} for dv in reading["developments"]]), unsafe_allow_html=True)
            for dv in reading["developments"]:
                with st.expander(f"Headlines behind: {dv['candidate']}: {dv['summary']}"):
                    for i in dv["ids"][:8]:
                        st.markdown(f"- {sent[i].published}: [{sent[i].title}]({sent[i].link}) ({sent[i].source}, {tier(sent[i].source)} credibility)")
        else:
            st.caption("No development in the last four weeks favours one candidate. The numbers are the starting values.")
    with t_time:
        days_ = [as_of - timedelta(days=i) for i in range(41, -1, -2)]
        st.line_chart(pd.DataFrame([{"Date": d, **answer(case, "q", d)[0]} for d in days_]).set_index("Date"), y_label="Probability")
        st.caption("Illustrative only, not a blind backtest: the candidates and developments were picked out today, with today's knowledge. "
                   "The chart shows when each development was published.")
    with t_all:
        st.dataframe(pd.DataFrame([{"Date": h.published, "Headline": h.title, "Outlet": h.source, "Credibility": tier(h.source).capitalize(), "Source": h.link}
                                   for h in sorted(r["heads"], key=lambda h: h.published, reverse=True)]),
                     hide_index=True, column_config=LINK, width="stretch")
    with t_lim:
        st.markdown("""
- **The candidate list comes from an AI model** reading headlines. A real candidate who is not in the news will be missing; that is what "Someone else" is for.
- **Starting values are the model's judgment**, not measured rates. The final numbers depend heavily on them.
- **Source credibility.** Each outlet is rated high, medium, low or unknown from an editable list (`configs/sources.json`). Satire is dropped. A claim counts for more when a high-credibility outlet reports it and when several good outlets confirm it; a claim carried only by low or unknown outlets can never be more than a weak signal. The list is an analyst's judgment and cannot catch a false story that reputable outlets repeat.
- **Headlines only, public news only.** Boards decide in private.
- **No track record.** Use this to see who the news points to and why, then judge for yourself.
""")
    log = {"question": r["question"], "as_of": str(as_of), "probabilities": {h: round(probs[h], 4) for h in order},
           "reader": "ai", "engine": "0.6 live"}
    st.download_button("Download this forecast (keep it to score later)", json.dumps(log, indent=2),
                       file_name=f"forecast_{as_of}.json", mime="application/json")
    st.download_button("Save this full result (it can be shown again later without internet)", pack(r),
                       file_name=f"result_{as_of}.json", mime="application/json", key="save_full")


def ask_page():
    st.title("Ask a question about the future")
    has_ai = bool(ai_key())
    st.markdown('<div class="ew-lede">Name a person, company or country and something that might happen. You get an estimate, '
                'its range, and the dated public reporting behind it.</div>', unsafe_allow_html=True)
    question = st.text_input("Your question", key="q",
                             placeholder="Will Jane Doe step down as CEO of Acme in the next 30 days?   or   Who will be the next CEO of Acme?")
    with st.expander("Advanced (optional: everything here is filled in automatically)"):
        c1, c2 = st.columns(2)
        focus_in = c1.text_input("Who or what is it about", placeholder="automatic")
        related_in = c2.text_input("Related names to check less deeply (comma-separated)", placeholder="automatic")
        c1, c2, c3 = st.columns(3)
        template = c1.selectbox("Type of event", ["auto"] + list(live.TEMPLATES),
                                format_func=lambda k: "Automatic" if k == "auto" else live.TEMPLATES[k]["name"])
        days = c2.number_input("Within how many days (0 = automatic)", 0, 3650, 0)
        as_of = c3.date_input("Use only news published by the end of", value=date.today(), max_value=date.today(),
                              help="Pick a past date to replay history without showing the app what happened next.")
        own = st.checkbox("Set my own starting value")
        prior = st.slider("Starting value (%)", 0.1, 50.0, 1.0, 0.1, disabled=not own,
                          help="How often this kind of event happens in a period this long when nothing special is going on.")
        yes_w = st.text_input("Extra clue words pointing to YES (keyword mode only)")
        no_w = st.text_input("Extra clue words pointing to NO (keyword mode only)")
        weeks = st.select_slider("How far back to read", [9, 10, 13, 26], value=10, format_func=lambda w: f"{w} weeks")
        up = st.file_uploader("Show a saved result (no internet or AI needed)", type="json",
                              help="Use 'Save this full result' under any answer, then load the file here. Useful as a backup for a live demo.")
        if up is not None and st.session_state.get("loaded") != up.file_id:
            try:
                st.session_state["ask"], st.session_state["loaded"] = unpack(up.getvalue().decode()), up.file_id
            except Exception:
                st.error("That file is not a saved result from this app.")
        if has_ai and st.button("Test the AI connection"):
            with st.spinner("Testing..."):
                st.dataframe(pd.DataFrame(ai.diagnose(ai_key())), hide_index=True, width="stretch")
            st.cache_data.clear()
    if not has_ai:
        st.caption("Running in keyword mode. Add a free Gemini key (see GUIDE.md) and the app will read headlines with an AI model.")

    auto = st.session_state.pop("autorun", False)
    if st.button("Analyse", type="primary") or auto:
        if not question.strip():
            st.error("Type a question first.")
        else:
            adv = dict(focus=focus_in.strip(), related=[x.strip() for x in related_in.split(",") if x.strip()][:5],
                       template=template, days=int(days), prior=prior / 100 if own else None, as_of=as_of, weeks=weeks,
                       yes=yes_w.split(","), no=no_w.split(","),
                       context=(st.session_state.get("ask") or {}).get("question", ""))
            out = run_question(ai.sanitize(question), adv)
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
    deadline = date.fromisoformat(plan["deadline"])
    damp = live.horizon_damp(plan["horizon_days"])
    k_p, k_lo, k_hi, k_detail, info = live.forecast(r["question"], focus, tagged, kinds, r["counts"], as_of, prior0, damp)
    if reading:
        case = ai.build_case(r["question"], focus, reading, r["sent"], prior0, plan["horizon_days"])
        probs, lo, hi, detail, _ = answer_with_range(case, "q", as_of)
        p_yes, lo_yes, hi_yes, n_sig = probs["yes"], lo["yes"], hi["yes"], len(reading["developments"])
        alts = [answer(ai.build_case(r["question"], focus, reading, r["sent"], odds_shift(prior0, f), plan["horizon_days"]), "q", as_of)[0]["yes"]
                for f in (0.5, 2.0)]
    else:
        p_yes, lo_yes, hi_yes, n_sig = k_p, k_lo, k_hi, info["signals"]
        alts = [live.forecast(r["question"], focus, tagged, kinds, r["counts"], as_of, odds_shift(prior0, f), damp)[0] for f in (0.5, 2.0)]
    lo_yes, hi_yes = min([lo_yes] + alts), max([hi_yes] + alts)  # include a starting value half or twice as likely
    p_second = None
    if reading and r.get("reading2"):
        p_second = answer(ai.build_case(r["question"], focus, r["reading2"], r["sent"], prior0, plan["horizon_days"]), "q", as_of)[0]["yes"]
        lo_yes, hi_yes = min(lo_yes, p_second), max(hi_yes, p_second)

    inverse = bool(plan.get("asks_opposite"))
    q_of = (lambda x: 1 - x) if inverse else (lambda x: x)   # from the chance of the event to the answer to the question
    p_q, prior_q = q_of(p_yes), q_of(prior0)
    lo_q, hi_q = sorted((q_of(lo_yes), q_of(hi_yes)))
    ev_txt = plan["event"].rstrip(".")
    if plan.get("statement"):
        statement = plan["statement"].rstrip(".") + "."
    elif inverse:
        statement = r["question"]
    else:
        statement = f"{ev_txt} by {deadline:%d %B %Y}."

    st.divider()
    if r.get("asked") and r["asked"].strip().lower().rstrip("?") != r["question"].strip().lower().rstrip("?"):
        st.caption(f"You typed: “{r['asked']}”. Understood as: “{r['question']}” If that is not what you meant, rephrase and run it again.")
    for note in r["notes"]:
        st.warning(note)
    stale = bool(reading) and (not reading["premise_ok"] or reading["already_happened"])
    if stale:
        st.subheader(r["question"])
    if reading and not reading["premise_ok"]:
        st.error("This question looks out of date. " + (reading["premise_note"] or "The news suggests its premise no longer holds.")
                 + " No estimate is shown.")
    elif reading and reading["already_happened"]:
        st.error(f"The news suggests this has already happened: {ev_txt}. No estimate is shown. Check the headlines under Why.")
    elif not reading and info["maybe_happened"]:
        st.warning("Several recent headlines report this event directly. It may already have happened: check the headlines.")
    if as_of < date.today() and reading:
        st.warning("You chose a past date. Later headlines are hidden, but the AI model may still remember what happened next, "
                   "so this replay is not a fair test.")
    if not stale:
        how = f"Worked out as the opposite of the underlying event ({ev_txt}: {approx(p_yes)})." if inverse else f"Underlying event: {ev_txt}."
        st.markdown(style.brief(statement, band(p_q), approx(p_q), range_text(lo_q, hi_q), p_q, lo_q, hi_q, how), unsafe_allow_html=True)
        if n_sig == 0:
            why = "Nothing in the recent news changes the picture, so this is the starting value."
        elif show(p_q) == show(prior_q):
            why = f"The recent news barely moves it from the starting value of {show(prior_q)}."
        else:
            why = f"The news {'raised' if p_q > prior_q else 'lowered'} it from a starting value of {show(prior_q)}."
        why += " The range covers nearby engine settings and a starting value half or twice as likely."
        if damp < 0.99:
            why += f" The deadline is {plan['horizon_days']} days away, so today's news is counted at {damp:.0%} of its normal weight."
        if p_second is not None:
            gap = abs(p_second - p_yes)
            why += (f" A second reading of the same headlines gave {approx(q_of(p_second))}: "
                    + ("the two agree." if gap < 0.05 or gap < 0.25 * max(p_yes, p_second) else "the two differ, so treat the number with extra caution."))
        st.markdown(why)
        cautions = []
        if not reading:
            cautions.append("headlines were read by keyword rules, not by the AI model")
        if info["read"] < 30:
            cautions.append(f"only {info['read']} headlines were found")
        if plan["horizon_days"] > 180:
            cautions.append("the deadline is far away")
        if hi_q - lo_q > 0.3:
            cautions.append("the range is wide")
        if p_second is not None and abs(p_second - p_yes) >= max(0.05, 0.25 * max(p_yes, p_second)):
            cautions.append("two readings of the same headlines disagreed")
        if 0.2 <= prior0 <= 0.8 and plan.get("by") == "ai":
            cautions.append("the result leans heavily on the starting value, which is the AI model's judgment")
        level = "Low" if len(cautions) >= 2 or not reading else "Moderate"
        st.markdown(style.note(f"How much to rely on this: {level}.", "Reasons for caution: " + "; ".join(cautions) + "." if cautions
                               else "Enough headlines, a near deadline and a stable number. Still a prototype with no track record."),
                    unsafe_allow_html=True)
    if reading and reading["summary"]:
        st.markdown(style.note("What the news says.", reading["summary"]), unsafe_allow_html=True)
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Answer", "n/a" if stale else approx(p_q))
    if not stale:
        m1.caption(f"Range {range_text(lo_q, hi_q)}")
    m2.metric("Starting value", show(prior_q), help=plan.get("prior_reason", ""))
    m2.caption(plan.get("prior_reason", ""))
    m3.metric("Headlines read", info["read"])
    m4.metric("Developments that counted" if reading else "Unusual signals", n_sig)
    st.caption(f"Searched for {focus}" + (f" (also {', '.join(plan['related'])})" if plan["related"] else "")
               + f". Settles by {deadline:%d %B %Y}, {plan['horizon_days']} days from {as_of:%d %B %Y}. News source: {', '.join(r['used'])}. "
               + (f"Headlines read by an AI model ({r.get('model', 'Gemini')})." if reading else "Headlines read by keyword rules.")
               + " Experimental, with no track record.")
    if info["read"] == 0:
        st.warning("No headlines came back. Check the spelling of the name, or type a shorter one under Advanced.")

    t_why, t_cov, t_time, t_all, t_lim = st.tabs(["Why", "Coverage", "Over time", "All headlines", "Limits"])
    with t_why:
        if reading:
            if reading["developments"]:
                flip = {"up": "down", "down": "up"}
                st.markdown(style.ledger([{
                    "date": dv["date"], "text": dv["summary"],
                    "effect": flip[dv["direction"]] if inverse else dv["direction"],
                    "effect_label": "Raises the estimate" if (dv["direction"] == "up") != inverse else "Lowers the estimate",
                    "strength": dv["strength"], "sources": src_label([r["sent"][i].source for i in dv["ids"]]),
                    "url": r["sent"][dv["ids"][0]].link} for dv in reading["developments"]]), unsafe_allow_html=True)
                for n, dv in enumerate(reading["developments"]):
                    with st.expander(f"Headlines behind: {dv['summary']}"):
                        for i in dv["ids"][:8]:
                            h = r["sent"][i]
                            st.markdown(f"- {h.published}: [{h.title}]({h.link}) ({h.source}, {tier(h.source)} credibility)")
                st.caption("Each development was picked out by the AI model from the headlines shown. Open them and judge for yourself.")
                if not r.get("reading2") and ai_key() and st.button("Check stability: read the headlines a second time"):
                    try:
                        with st.spinner("Reading again..."):
                            r["reading2"] = ai.read(ai_key(), r["question"], plan, r["heads"], as_of)[0]
                        st.rerun()
                    except ai.AIError as err:
                        st.warning(f"The second reading failed ({err}).")
            else:
                st.caption("The AI model found no development in the last four weeks that changes the chance.")
        rows = [x for x in info["rows"] if x["recent"] > 0]
        box = st.expander("Keyword check (the simpler method, for comparison)") if reading else st.container()
        with box:
            if reading:
                st.caption(f"Keyword rules alone give {approx(q_of(k_p))} for the same question.")
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
                                    st.markdown(f"- {h.published}: [{h.title}]({h.link}) ({h.source}, {tier(h.source)} credibility)")
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
            ys = [live.forecast(r["question"], focus, tagged, kinds, [], d, prior0, damp)[0] for d in days_]
        st.line_chart(pd.DataFrame({"Date": days_, "Estimate": [q_of(y) for y in ys]}).set_index("Date"), y_label="Probability")
        st.caption("Illustrative only, not a blind backtest: the developments were picked out today, with today's knowledge. "
                   "The chart shows when each one was published." if reading else "Each point uses only what was published by that day.")
    with t_all:
        st.dataframe(pd.DataFrame([{"Date": h.published, "Headline": h.title, "Outlet": h.source, "Credibility": tier(h.source).capitalize(),
                                    "Found by": focus if h.query == "focus" else h.query, "Source": h.link}
                                   for h in sorted(r["heads"], key=lambda h: h.published, reverse=True)]),
                     hide_index=True, column_config=LINK, width="stretch")
    with t_lim:
        st.markdown("""
- **It reads headlines, not articles**, and only public news. Private knowledge is invisible. In the Nvidia example the number stayed near the starting value until the story was reported.
- **With the AI reader:** a language model picks out the developments and suggests the starting value. It can misjudge. It never sets the final number; the engine does, from the developments listed under Why.
- **Without it:** headlines are tagged by keywords, and a kind of story counts only if it is clearly more common in the last 14 days than before.
- **Source credibility.** Each outlet is rated high, medium, low or unknown from an editable list (`configs/sources.json`). Satire is dropped. A claim counts for more when a high-credibility outlet reports it and when several good outlets confirm it; a claim carried only by low or unknown outlets can never be more than a weak signal. The list is an analyst's judgment and cannot catch a false story that reputable outlets repeat.
- **The starting value is a judgment**, and the final number depends heavily on it.
- **Far-off deadlines.** News counts in full when the deadline is within 60 days and progressively less beyond that (41% at one year, 29% at two). That scale is a judgment, not a measurement.
- **What it will not answer:** numbers and prices, past facts, vague questions, private individuals, and a named person's death, health or private life.
- **Replays are not fully blind.** A past date hides later headlines, but today's search engine chooses which old headlines to return, and an AI model may remember what happened next.
- **At most about 100 headlines per week** are read for the focus, in English.
- **The checks are not guarantees.** "Out of date" and "already happened" are the AI model's reading of the headlines and can be wrong.
- **Untrusted text.** Questions and headlines are passed to the model as data, instruction-like questions are refused, and the model's output is validated; the model never sets the final number. This lowers the risk of manipulation; it does not remove it. The starting value is the part a manipulated model could move most.
- **Rounded on purpose.** Numbers are shown to the nearest 5% (1% at the extremes) because the method is not more precise than that.
- **No track record.** Nothing here has been scored against outcomes. Save forecasts and score them on the Scorecard page. Use this to organise what the news says, then judge for yourself.
- **People.** A probability is not an accusation. Use this for public figures and organisations.
""")
    log = {"question": r["question"], "focus": focus, "event": plan["event"], "as_of": str(as_of),
           "deadline": plan["deadline"], "horizon_days": plan["horizon_days"], "statement": statement, "starting_value": round(prior_q, 4),
           "probability": None if stale else round(p_q, 4), "low": round(lo_q, 4), "high": round(hi_q, 4), "headlines_read": info["read"],
           "reader": "ai" if reading else "keywords", "engine": "0.5 live"}
    st.download_button("Download this forecast (keep it to score later)", json.dumps(log, indent=2),
                       file_name=f"forecast_{as_of}.json", mime="application/json")
    st.download_button("Save this full result (it can be shown again later without internet)", pack(r),
                       file_name=f"result_{as_of}.json", mime="application/json", key="save_full")


def scorecard_page():
    st.title("Scorecard")
    st.caption("A forecast earns trust only by being scored. Save forecasts with 'Download this forecast' when you make them, "
               "then load the files here once the answers are known.")
    files = st.file_uploader("Forecast files", type="json", accept_multiple_files=True)
    rows = []
    for f in files or []:
        try:
            d = json.loads(f.getvalue().decode())
            if isinstance(d.get("probability"), (int, float)):
                rows.append((f.file_id, d))
        except Exception:
            st.warning(f"{f.name} is not a forecast file.")
    if not rows:
        st.info("No yes/no forecasts loaded yet. 'Who' forecasts are not scored here yet.")
        return
    scored = []
    for fid, d in rows:
        out = st.radio(f"{d['question']} (forecast {show(d['probability'])}, made {d['as_of']}, settles {d.get('deadline', '?')})",
                       ["Not settled yet", "Happened", "Did not happen"], horizontal=True, key=f"o_{fid}")
        if out != "Not settled yet":
            scored.append((d["probability"], d.get("starting_value", 0.5), 1.0 if out == "Happened" else 0.0))
    if not scored:
        return
    n = len(scored)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Forecasts scored", n)
    c2.metric("Brier score (lower is better)", f"{sum((p - o) ** 2 for p, _, o in scored) / n:.3f}")
    c3.metric("Starting values alone", f"{sum((b - o) ** 2 for _, b, o in scored) / n:.3f}")
    c4.metric("Always saying 50%", "0.250")
    buckets = {}
    for p, _, o in scored:
        buckets.setdefault(band(p), []).append((p, o))
    st.dataframe(pd.DataFrame([{"Forecast band": k, "Forecasts": len(v), "Average forecast": show(sum(p for p, _ in v) / len(v)),
                                "Share that happened": f"{sum(o for _, o in v) / len(v):.0%}"} for k, v in buckets.items()]),
                 hide_index=True, width="stretch")
    st.caption("The forecasts beat the starting values only if the first Brier score is lower than the second. "
               + ("Fewer than 30 scored forecasts: far too few to conclude anything." if n < 30 else "Calibration is good when each band's share that happened is close to its average forecast."))


def go_analyse(q: str | None = None):
    st.session_state["q"] = (q if q is not None else st.session_state.get("home_q", "")).strip()
    st.session_state["page"] = "Analyse"
    st.session_state["autorun"] = bool(st.session_state["q"])


EXAMPLES = ["Who will be the next permanent CEO of Nvidia?", "Will Nvidia name a permanent CEO within 365 days?",
            "Will the Federal Reserve change interest rates in the next 12 months?"]
LIMITS = ["It reads public headlines only. Private knowledge is invisible to it.",
          "It has no track record yet. Nothing here has been scored against outcomes.",
          "The starting value is a judgment, and the result depends heavily on it.",
          "An AI model picks out the developments and can misjudge them.",
          "It will not answer questions about prices, private individuals, or a named person's death or health."]


def home_page():
    st.title("What does the public record say will happen?")
    st.markdown(f'<div class="ew-lede">{NAME} reads dated public news about a person, company or country, weighs each source, '
                'and gives a sober estimate of what comes next, with the evidence shown and the uncertainty stated.</div>',
                unsafe_allow_html=True)
    c1, c2 = st.columns([5, 1], vertical_alignment="bottom")
    c1.text_input("Ask a question", key="home_q", placeholder="Will Jane Doe step down as CEO of Acme in the next 30 days?")
    c2.button("Analyse", type="primary", on_click=go_analyse, key="home_go", width="stretch")
    st.caption("Or start from one of these:")
    for col, q in zip(st.columns(len(EXAMPLES)), EXAMPLES):
        col.button(q, on_click=go_analyse, args=(q,), key=f"ex_{q}", width="stretch")

    st.markdown('<div class="ew-example-tag">What an answer looks like (an illustration with invented names, not a live result):</div>',
                unsafe_allow_html=True)
    st.markdown(style.brief("Acme rehires Jane Doe as chief executive by 30 October 2027.", "Very unlikely", "about 4%", "2% to 8%",
                            0.04, 0.02, 0.08, "Underlying event: Acme rehires Jane Doe as chief executive."), unsafe_allow_html=True)
    st.subheader("How it works")
    st.markdown(style.steps(), unsafe_allow_html=True)
    st.markdown(style.two_lists(
        "What it does", ["Shows every development behind a number, with dates and links.",
                         "Rates each outlet and marks unconfirmed claims down.",
                         "Uses only what was published by the date you choose.",
                         "Gives a range, and says how much to rely on each answer.",
                         "Lets you save forecasts and score them later."],
        "What it does not do", LIMITS), unsafe_allow_html=True)
    if SITE.get("video_url", "").startswith("http"):
        st.subheader("A short walkthrough")
        st.video(SITE["video_url"])


def method_page():
    st.title("How an estimate is made")
    st.markdown('<div class="ew-lede">The AI model reads and labels. It never sets the number. A small, fixed engine does that, '
                'so every estimate can be traced back to dated headlines.</div>', unsafe_allow_html=True)
    st.markdown(style.PIPELINE_SVG, unsafe_allow_html=True)
    st.subheader("Starting value, then evidence")
    st.markdown("Every estimate starts from how often that kind of event happens to comparable people or organisations over the "
                "same period. Dramatic news is common and big events are rare, so the starting value matters more than any single "
                "headline. Each development then moves the estimate up or down. Strong, well-sourced developments move it more; "
                "repeats of the same story count once; news about a far-off deadline counts for less.")
    st.subheader("Which sources count")
    st.markdown(style.tiers([("High", 0.9, "Wire services, public broadcasters, major newspapers, official sites"),
                             ("Medium", 0.75, "Established national, business and technology press"),
                             ("Unknown", 0.55, "Outlets not on the list"),
                             ("Low", 0.35, "Press-release services, tabloids, state-controlled outlets, opinion platforms"),
                             ("Satire", 0.0, "Dropped before anything is read")]), unsafe_allow_html=True)
    st.markdown("A claim confirmed by several reliable outlets counts for more. A claim carried only by low or unknown outlets can "
                "never be more than a weak signal. The list is an editable file, `configs/sources.json`.")
    st.subheader("What the range means")
    st.markdown("The range shows how far the estimate moves under nearby engine settings and under a starting value half or twice "
                "as likely. Numbers are rounded to the nearest 5% (1% at the extremes) because the method is not more precise than that.")
    st.subheader("Limits")
    st.markdown("\n".join(f"- {x}" for x in LIMITS + [
        "Replays of past dates are illustrative: today's search engine chooses which old headlines return, and an AI model may remember outcomes.",
        "Checks such as 'out of date' are the AI model's reading of the headlines, not guarantees.",
        "Questions and headlines are treated as untrusted data and instruction-like text is refused. This lowers the risk of manipulation; it does not remove it."]))
    st.subheader("System check")
    st.markdown("Runs a fixed set of difficult questions through the live AI model and checks that each is understood correctly. "
                "It uses about ten AI calls from the free daily allowance.")
    if not ai_key():
        st.caption("Needs the AI reader (a Gemini key in the app's Secrets).")
    elif st.button("Run the system check"):
        with st.spinner("Checking how the AI model understands 13 difficult questions..."):
            rows = selftest.run(ai_key(), date.today())
        passed = sum(x["Result"] == "Pass" for x in rows)
        (st.success if passed == len(rows) else st.warning)(f"{passed} of {len(rows)} checks passed.")
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")


def contact_page():
    st.title("Contact")
    who = " ".join(x for x in (SITE.get("contact_name", ""), SITE.get("organisation", "")) if x)
    st.markdown(f'<div class="ew-lede">{NAME} is an early prototype. Questions, corrections and proposals for evaluation are welcome.</div>',
                unsafe_allow_html=True)
    if who:
        st.markdown(f"**{who}**")
    if "@" in SITE.get("contact_email", ""):
        st.markdown(f"Email: [{SITE['contact_email']}](mailto:{SITE['contact_email']})")
    if SITE.get("contact_url", "").startswith("http"):
        st.markdown(f"{SITE.get('contact_url_label') or 'Website'}: [{SITE['contact_url']}]({SITE['contact_url']})")
    st.caption("The source code and the evidence files for the worked examples are public in the project repository.")


ROUTES = {"Home": home_page, "Analyse": ask_page, "Scorecard": scorecard_page, "Method": method_page, "Contact": contact_page}
if page in ROUTES:
    try:
        ROUTES[page]()
    except Exception as err:  # never show a raw traceback to an audience
        if os.environ.get("EW_DEBUG"):
            raise
        st.error("Something went wrong while preparing this page. Please try again, or load a saved result under Advanced on the Analyse page.")
        with st.expander("Technical details"):
            st.code(repr(err))
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

settings = V0  # settings fitted to the two bundled cases failed the out-of-sample check and are not offered
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

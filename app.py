"""Early-warning platform: web app.

Run locally:   streamlit run app.py
Deploy free:   see GUIDE.md
"""
from __future__ import annotations

import json
from datetime import date, timedelta

import pandas as pd
import streamlit as st

from ew.cases import answer, answer_with_range, backtest, list_cases, load_case
from ew.engine import Settings, V0
from ew.evidence import visible_as_of
from ew import live

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


def ask_page():
    st.title("Ask anything")
    st.caption("Type a question about a person, company or country. The app reads dated public news headlines "
               "and runs them through the same engine as the worked examples. Experimental: read the Limits tab.")
    question = st.text_input("Your question", placeholder="Will Jane Doe step down as CEO of Acme in the next 30 days?")
    c1, c2 = st.columns(2)
    focus_in = c1.text_input("Who or what is it about (the focus)", placeholder="Jane Doe",
                             help="The search uses this exact name. Leave empty to let the app guess from the question.")
    related_in = c2.text_input("Related names to check less deeply (optional, comma-separated)", placeholder="Acme, John Roe",
                               help="Headlines about these count half as much, so the focus never drifts.")
    keys_t = list(live.TEMPLATES)
    guess_t = live.detect_template(question) if question else "custom"
    c1, c2, c3 = st.columns(3)
    template = c1.selectbox("Type of event", keys_t, index=keys_t.index(guess_t),
                            format_func=lambda k: live.TEMPLATES[k]["name"], key=f"tpl_{guess_t}")
    horizon = c2.number_input("Within how many days", 1, 365, live.TEMPLATES[template]["base"][1])
    as_of = c3.date_input("Use only news published by the end of", value=date.today(), max_value=date.today(),
                          help="Pick a past date to replay history without showing the app what happened next.")
    start = live.base_rate(template, int(horizon))
    prior = st.slider("Starting value before reading any news (%)", 0.1, 50.0, round(start * 100, 1), 0.1,
                      key=f"prior_{template}_{horizon}",
                      help="How often this kind of event happens in a period this long when nothing special is going on. "
                           "The default is a rough judgment. Change it if you know better.") / 100
    focus = focus_in.strip() or live.guess_focus(question)
    yes_default = ", ".join(live.clue_words(question, focus)[:6]) if template == "custom" else ""
    with st.expander("Clue words (needed for 'Something else', optional otherwise)", expanded=template == "custom"):
        yes_w = st.text_input("Words in a headline that point towards YES", value=yes_default, key=f"yes_{template}_{question}")
        no_w = st.text_input("Words in a headline that point towards NO")
    weeks = st.select_slider("How far back to read", [9, 10, 13, 26], value=10, format_func=lambda w: f"{w} weeks")

    if st.button("Analyse", type="primary"):
        if not question.strip() or not focus:
            st.error("Type a question and say who or what it is about.")
        elif template == "custom" and not (yes_w.strip() or no_w.strip()):
            st.error("For this type of question, give at least one clue word.")
        else:
            related = tuple(x.strip() for x in related_in.split(",") if x.strip())[:5]
            try:
                with st.spinner(f"Reading {weeks} weeks of headlines about {focus}..."):
                    heads, counts, used = fetch_news(focus, related, as_of, weeks)
            except Exception as err:
                st.error(f"Could not fetch news right now. Wait a minute and try again. Details: {err}")
                return
            st.session_state["ask"] = dict(question=question.strip(), focus=focus, heads=heads, counts=counts, used=used,
                                           as_of=as_of, template=template, prior=prior, horizon=int(horizon),
                                           yes=yes_w.split(","), no=no_w.split(","), weeks=weeks)
    r = st.session_state.get("ask")
    if not r:
        return

    tagged, kinds = live.tag_headlines(r["heads"], r["template"], r["yes"], r["no"])
    p_yes, lo_yes, hi_yes, detail_yes, info = live.forecast(r["question"], r["focus"], tagged, kinds, r["counts"],
                                                            r["as_of"], r["prior"])
    probs, lo, hi = {"yes": p_yes}, {"yes": lo_yes}, {"yes": hi_yes}
    st.divider()
    st.subheader(r["question"])
    st.caption(f"Focus: {r['focus']}. Window: {r['horizon']} days from {r['as_of']:%d %B %Y}. "
               f"News source: {', '.join(r['used'])}.")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Probability of yes", pct(p_yes))
    m1.caption(f"Range {pct(lo_yes)} to {pct(hi_yes)}")
    m2.metric("Starting value", pct(r["prior"]))
    m3.metric("Headlines read", info["read"])
    m4.metric("Unusual signals", info["signals"])
    if info["read"] == 0:
        st.warning("No headlines came back. Check the spelling of the focus, or try a shorter name.")
    elif info["signals"] == 0:
        st.info("Nothing in the last two weeks stands out from this name's usual coverage. "
                "The number is the starting value.")
    if info["maybe_happened"]:
        st.warning("Several recent headlines report this event directly. It may already have happened: check the headlines.")
    st.caption("A kind of story counts only when it is clearly more common in the last two weeks than in this name's "
               "own earlier coverage. This is a keyword reading of headlines with no track record, not a validated forecast.")

    t_why, t_cov, t_time, t_all, t_lim = st.tabs(["Why", "Coverage", "Over time", "All headlines", "Limits"])
    with t_why:
        effect = {e.id: c for e, c in detail_yes}
        rows = [x for x in info["rows"] if x["recent"] > 0]
        if rows:
            st.dataframe(pd.DataFrame([{
                "Kind of story": live.LABELS.get(x["signal"], x["signal"]),
                "About": r["focus"] if x["group"] == "focus" else "related names",
                "Last 14 days": f"{x['recent']} of {x['recent_total']} ({x['recent'] / x['recent_total']:.0%})",
                "Usual share": "unknown" if x["usual_share"] is None else f"{x['usual_share']:.0%}",
                "Counted": "Yes" if x["counted"] else "No, within normal",
                "Effect": round(effect.get(f"{x['signal']}@{x['group']}", 0.0), 2)}
                for x in sorted(rows, key=lambda x: (-x["counted"], -x["recent"]))]), hide_index=True, width="stretch")
            st.caption("Effect above 0 pushes the probability up, below 0 pushes it down.")
            for x in rows:
                if x["counted"]:
                    with st.expander(f"Example headlines: {live.LABELS.get(x['signal'], x['signal'])}"):
                        for h in x["examples"]:
                            st.markdown(f"- {h.published}: [{h.title}]({h.link}) ({h.source})")
            st.caption("Read the examples. If the headlines were misread, ignore that signal.")
        else:
            st.caption("No headline in the last two weeks matched any clue for this type of event.")
    with t_cov:
        ends = [r["as_of"] - timedelta(days=7 * w) for w in range(len(r["counts"]) - 1, -1, -1)]
        st.bar_chart(pd.DataFrame({"Week ending": ends, "Headlines": r["counts"]}).set_index("Week ending"))
        if info["saturated"]:
            st.caption("This name fills the search limit of about 100 headlines almost every week, so a change in attention cannot be measured.")
        elif info["attention_z"] is None:
            st.caption("Not enough weeks to judge whether attention is unusual.")
        else:
            st.caption(f"Latest week against this name's own normal: z = {info['attention_z']:.1f} "
                       "(about 0 is normal, 3 or more is unusual and counts as a weak signal).")
    with t_time:
        days = [r["as_of"] - timedelta(days=i) for i in range(min(42, 7 * r["weeks"] - 21) - 1, -1, -2)]
        st.line_chart(pd.DataFrame({"Date": days, "Probability of yes": [live.forecast(r["question"], r["focus"], tagged, kinds, [], d, r["prior"])[0] for d in days]}).set_index("Date"),
                      y_label="Probability")
        st.caption("Each point uses only headlines published by that day.")
    with t_all:
        st.dataframe(pd.DataFrame([{"Date": h.published, "Headline": h.title, "Outlet": h.source,
                                    "Found by": r["focus"] if h.query == "focus" else h.query, "Source": h.link}
                                   for h in sorted(r["heads"], key=lambda h: h.published, reverse=True)]),
                     hide_index=True, column_config=LINK, width="stretch")
    with t_lim:
        st.markdown("""
- **Compared with its own past.** A kind of story counts only if it is clearly more common in the last 14 days than in the earlier weeks for the same name. A name that is always in trouble will not trigger it; a slow build-up over months will be missed.
- **Keywords, not understanding.** A headline is tagged by the words in it. Sarcasm, questions and stories about someone else with the same name are misread.
- **Headlines only.** The article text is not read.
- **The starting value is a judgment.** The final number depends heavily on it.
- **Public news only.** Private knowledge is invisible. In the Nvidia example the number stayed near the starting value until the story was reported.
- **Replays are not fully blind.** Choosing a past date hides later headlines, but today's search engine decides which old headlines to return.
- **At most about 100 headlines per week** are read for the focus, and only English-language search is used.
- **No track record.** Nothing here has been scored against outcomes. Use it to organise what the news says, then judge for yourself.
- **People.** A probability is not an accusation. Use this for public figures and organisations.
""")
    log = {"question": r["question"], "focus": r["focus"], "as_of": str(r["as_of"]), "horizon_days": r["horizon"],
           "event_type": r["template"], "starting_value": r["prior"], "probability": round(probs["yes"], 4),
           "low": round(lo["yes"], 4), "high": round(hi["yes"], 4), "headlines_read": info["read"],
           "unusual_signals": info["signals"], "engine": "0.4 live"}
    st.download_button("Download this forecast (keep it to score later)", json.dumps(log, indent=2),
                       file_name=f"forecast_{r['as_of']}.json", mime="application/json")


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

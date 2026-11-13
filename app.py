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

"""Look and feel: one stylesheet and the HTML for the site's panels.

Design: a briefing document, not a dashboard. The estimate is written as a
sentence in a serif face and placed on a seven-word scale (very unlikely to
very likely), the way analysts word estimates, with an amber marker on ink
blue. Everything else stays quiet.

Every piece of dynamic text is escaped before it is placed in HTML, because
it can come from a user, a headline or an AI model.
"""
from __future__ import annotations

from html import escape

INK, AMBER, SLATE, LINE, PAPER = "#14213D", "#E8A317", "#5A6474", "#D6DBE1", "#F4F6F5"
WORDS = [(0.05, "Very unlikely"), (0.25, "Unlikely"), (0.45, "Less likely than not"), (0.55, "Roughly even"),
         (0.75, "More likely than not"), (0.95, "Likely"), (1.0, "Very likely")]

CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Serif:wght@400;500;600&display=swap');
html, body, [class*="css"], .stMarkdown, button, input, textarea {{ font-family: 'IBM Plex Sans', 'Source Sans Pro', sans-serif; }}
.block-container {{ padding-top: 3.4rem; max-width: 1120px; }}
h1, h2, h3 {{ color: {INK}; letter-spacing: -0.015em; }}
h1, [data-testid="stHeading"] h1 {{ font-family: 'IBM Plex Sans', 'Source Sans Pro', sans-serif !important; font-weight: 700; font-size: 2.5rem; line-height: 1.15; }}
[data-testid="stSidebar"], [data-testid="stSidebar"] [data-testid="stSidebarContent"] {{ background: {INK}; }}
[data-testid="stSidebar"] [data-testid="stSidebarContent"] {{ padding-top: 1.2rem; }}
[data-testid="stSidebar"] * {{ color: #E6EAF2; }}
.ew-brand-name {{ font-family: 'IBM Plex Serif', Georgia, serif; font-size: 1.5rem; font-weight: 500; color: #FFFFFF !important; line-height: 1.15; }}
.ew-brand-name span {{ display: inline-block; width: 10px; height: 10px; border-radius: 50%; background: {AMBER}; margin-right: 0.55rem; }}
.ew-brand-tag {{ font-size: 0.86rem; color: #A7B1C5 !important; margin: 0.35rem 0 1.3rem 0; line-height: 1.4; }}
.stButton > button[kind="primary"], .stFormSubmitButton > button {{ background: {INK}; color: #FFFFFF; border: 0; border-radius: 6px; padding: 0.6rem 1.5rem; font-weight: 600; }}
.stButton > button[kind="primary"]:hover, .stFormSubmitButton > button:hover {{ background: #223463; color: #FFFFFF; }}
.stButton > button:focus-visible, input:focus-visible {{ outline: 3px solid {AMBER}; outline-offset: 2px; }}
[data-testid="stTextInput"] input {{ border-radius: 6px; padding: 0.75rem 0.9rem; font-size: 1.05rem; background: #FFFFFF; }}
[data-testid="stMetric"] {{ background: #FFFFFF; border: 1px solid {LINE}; border-radius: 6px; padding: 0.85rem 1rem; }}
[data-testid="stMetricLabel"] p {{ color: {SLATE}; font-size: 0.85rem; }}
[data-testid="stMetricValue"] {{ color: {INK}; font-size: 1.55rem; font-weight: 600; }}
[data-testid="stExpander"] {{ background: #FFFFFF; border: 1px solid {LINE}; border-radius: 6px; }}
.stTabs [data-baseweb="tab-list"] {{ gap: 1.5rem; border-bottom: 1px solid {LINE}; }}
.stTabs [data-baseweb="tab"] {{ font-weight: 600; color: {SLATE}; }}
.stTabs [aria-selected="true"] {{ color: {INK}; }}
.ew-lede {{ font-size: 1.15rem; line-height: 1.55; color: #2A3550; max-width: 62ch; margin: 0.2rem 0 1.4rem 0; }}
.ew-asked {{ color: {SLATE}; font-size: 0.92rem; margin: 0.1rem 0 0.2rem 0; }}

.ew-brief {{ background: {INK}; border-radius: 8px; padding: 1.9rem 2rem 1.5rem 2rem; margin: 0.8rem 0 1.1rem 0; }}
.ew-brief .ew-statement {{ font-family: 'IBM Plex Serif', Georgia, serif; font-size: 1.55rem; line-height: 1.35; color: #FFFFFF; max-width: 46ch; }}
.ew-brief .ew-verdict {{ display: flex; align-items: baseline; gap: 0.9rem; flex-wrap: wrap; margin-top: 1.2rem; }}
.ew-brief .ew-word {{ font-size: 2rem; font-weight: 700; color: {AMBER}; letter-spacing: -0.01em; line-height: 1.1; }}
.ew-brief .ew-num {{ font-size: 1.25rem; font-weight: 500; color: #FFFFFF; }}
.ew-brief .ew-range {{ font-size: 0.95rem; color: #A7B1C5; }}
.ew-brief .ew-frame {{ font-size: 0.85rem; color: #A7B1C5; margin-top: 1.1rem; line-height: 1.5; max-width: 80ch; }}
.ew-scale {{ position: relative; margin: 1.5rem 0 0 0; }}
.ew-segs {{ display: flex; gap: 3px; height: 12px; }}
.ew-segs div {{ background: #2B3A5E; border-radius: 2px; }}
.ew-segs div.on {{ background: #4A5C8A; }}
.ew-span {{ position: absolute; top: 3px; height: 6px; background: {AMBER}; opacity: 0.55; border-radius: 3px; }}
.ew-mark {{ position: absolute; top: -5px; width: 4px; height: 22px; margin-left: -2px; background: {AMBER}; border-radius: 2px; }}
.ew-ticks {{ display: flex; justify-content: space-between; font-size: 0.75rem; color: #8E9AB3; margin-top: 0.45rem; }}

.ew-cand {{ display: grid; grid-template-columns: minmax(130px, 230px) 1fr 5.2rem; gap: 1rem; align-items: center; margin-top: 0.95rem; }}
.ew-cand .ew-name {{ font-weight: 600; color: #FFFFFF; }}
.ew-cand .ew-val {{ text-align: right; color: #FFFFFF; font-weight: 600; }}
.ew-cand.ew-other .ew-name, .ew-cand.ew-other .ew-val {{ color: #A7B1C5; font-weight: 400; }}
.ew-bar {{ position: relative; height: 8px; background: #2B3A5E; border-radius: 4px; }}
.ew-bar .ew-span {{ top: 1px; }}
.ew-bar .ew-mark {{ top: -6px; height: 20px; }}

.ew-note {{ background: #FFFFFF; border: 1px solid {LINE}; border-left: 4px solid {INK}; border-radius: 6px; padding: 0.85rem 1.1rem; margin: 0.4rem 0 0.9rem 0; color: #1C2740; line-height: 1.5; }}
.ew-note b {{ color: {INK}; }}
.ew-ledger {{ background: #FFFFFF; border: 1px solid {LINE}; border-radius: 6px; margin: 0.3rem 0 0.8rem 0; }}
.ew-item {{ display: grid; grid-template-columns: 6.5rem 1fr 12.5rem; gap: 1.2rem; padding: 0.95rem 1.1rem; border-top: 1px solid {LINE}; align-items: start; }}
.ew-item:first-child {{ border-top: 0; }}
.ew-item .ew-date {{ color: {SLATE}; font-size: 0.9rem; }}
.ew-item .ew-what {{ color: #1C2740; line-height: 1.45; }}
.ew-item .ew-what a {{ color: {INK}; font-size: 0.88rem; text-decoration: underline; }}
.ew-item .ew-who {{ font-weight: 600; color: {INK}; }}
.ew-item .ew-meta {{ font-size: 0.88rem; color: {SLATE}; line-height: 1.5; }}
.ew-eff {{ font-weight: 600; color: {INK}; }}
.ew-eff.up::before {{ content: "\\25B2"; color: #1E7A4F; margin-right: 0.35rem; font-size: 0.75rem; }}
.ew-eff.down::before {{ content: "\\25BC"; color: #B4432F; margin-right: 0.35rem; font-size: 0.75rem; }}

.ew-steps {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 0; margin: 0.6rem 0 1.6rem 0; border-top: 2px solid {INK}; }}
.ew-step {{ padding: 1rem 1.2rem 0.4rem 0; }}
.ew-step .n {{ font-family: 'IBM Plex Serif', Georgia, serif; font-size: 1.6rem; color: {AMBER}; line-height: 1; }}
.ew-step .t {{ font-weight: 600; color: {INK}; margin: 0.45rem 0 0.25rem 0; }}
.ew-step .d {{ color: #3A4560; font-size: 0.95rem; line-height: 1.5; }}
.ew-two {{ display: grid; grid-template-columns: 1fr 1fr; gap: 2.2rem; margin: 0.4rem 0 1.4rem 0; }}
.ew-two h4 {{ color: {INK}; margin: 0 0 0.5rem 0; font-size: 1.05rem; }}
.ew-two ul {{ margin: 0; padding-left: 1.1rem; color: #2A3550; line-height: 1.6; }}
.ew-tiers {{ display: grid; grid-template-columns: 9rem 1fr; gap: 0.5rem 1rem; align-items: center; max-width: 640px; margin: 0.5rem 0 1.2rem 0; }}
.ew-tiers .lab {{ color: {INK}; font-weight: 600; }}
.ew-tiers .bar {{ height: 14px; background: {INK}; border-radius: 2px; }}
.ew-tiers .eg {{ grid-column: 2; color: {SLATE}; font-size: 0.88rem; margin-top: -0.35rem; }}
.ew-example-tag {{ color: {SLATE}; font-size: 0.88rem; margin: 1.4rem 0 -0.3rem 0; }}
@media (max-width: 760px) {{
  .ew-steps, .ew-two {{ grid-template-columns: 1fr; }}
  .ew-item {{ grid-template-columns: 1fr; gap: 0.3rem; }}
  .ew-cand {{ grid-template-columns: 1fr 4.5rem; }} .ew-cand .ew-bar {{ grid-column: 1 / -1; order: 3; }}
  h1 {{ font-size: 1.9rem; }} .ew-brief {{ padding: 1.3rem 1.2rem; }}
}}
</style>
"""


def brand(name: str, tagline: str) -> str:
    return (f'<div class="ew-brand-name"><span></span>{escape(name)}</div>'
            f'<div class="ew-brand-tag">{escape(tagline)}. A prototype: estimates from dated public reporting, never certainties.</div>')


def safe_url(u: str) -> str:
    u = (u or "").strip()
    return escape(u, quote=True) if u.startswith(("https://", "http://")) else "#"


def _pc(x: float) -> float:
    return max(0.0, min(100.0, x * 100))


def scale(p: float, lo: float, hi: float) -> str:
    """The seven-word scale with the range and a marker."""
    segs, prev = "", 0.0
    for top, _ in WORDS:
        on = " class=\"on\"" if prev <= p < top or (top == 1.0 and p >= prev) else ""
        segs += f'<div{on} style="flex:{(top - prev) * 100:.0f}"></div>'
        prev = top
    return (f'<div class="ew-scale"><div class="ew-segs">{segs}</div>'
            f'<div class="ew-span" style="left:{_pc(lo):.1f}%;width:{max(_pc(hi) - _pc(lo), 0.6):.1f}%"></div>'
            f'<div class="ew-mark" style="left:{_pc(p):.1f}%"></div></div>'
            '<div class="ew-ticks"><span>Very unlikely</span><span>Roughly even</span><span>Very likely</span></div>')


def brief(statement: str, word: str, value: str, rng: str, p: float, lo: float, hi: float, how: str = "") -> str:
    """The answer panel for a yes/no question: the statement, the verdict in words, the number and its range."""
    return ('<div class="ew-brief">'
            f'<div class="ew-statement">{escape(statement)}</div>'
            f'<div class="ew-verdict"><div class="ew-word">{escape(word)}</div><div class="ew-num">{escape(value)}</div>'
            f'<div class="ew-range">range {escape(rng)}</div></div>'
            + scale(p, lo, hi) +
            f'<div class="ew-frame">{escape(how + " " if how else "")}A model estimate from public news reporting, not a statement of fact.</div></div>')


def brief_who(question: str, rows: list[tuple[str, str, float, float, float, bool]]) -> str:
    """rows: (name, shown value, p, lo, hi, is_other), most likely first."""
    top = rows[0]
    body = "".join(
        f'<div class="ew-cand{" ew-other" if other else ""}"><div class="ew-name">{escape(name)}</div>'
        f'<div class="ew-bar"><div class="ew-span" style="left:{_pc(lo):.1f}%;width:{max(_pc(hi) - _pc(lo), 0.6):.1f}%"></div>'
        f'<div class="ew-mark" style="left:{_pc(p):.1f}%"></div></div>'
        f'<div class="ew-val">{escape(val)}</div></div>' for name, val, p, lo, hi, other in rows)
    return ('<div class="ew-brief">'
            f'<div class="ew-statement">{escape(question)}</div>'
            f'<div class="ew-verdict"><div class="ew-word">Most likely: {escape(top[0])}</div><div class="ew-num">{escape(top[1])}</div></div>'
            + body +
            '<div class="ew-frame">Bars show each range. A model estimate from public news reporting, not a statement of fact.</div></div>')


def note(label: str, text: str) -> str:
    return f'<div class="ew-note"><b>{escape(label)}</b> {escape(text)}</div>'


def ledger(items: list[dict]) -> str:
    """Evidence rows. Each item: date, text, effect ('up'|'down'), effect_label, strength, sources, url, optional who."""
    rows = ""
    for it in items:
        who = f'<span class="ew-who">{escape(it["who"])}: </span>' if it.get("who") else ""
        rows += ('<div class="ew-item">'
                 f'<div class="ew-date">{escape(str(it["date"]))}</div>'
                 f'<div class="ew-what">{who}{escape(it["text"])}<br><a href="{safe_url(it["url"])}" target="_blank" rel="noopener noreferrer">Open a source headline</a></div>'
                 f'<div class="ew-meta"><div class="ew-eff {"up" if it["effect"] == "up" else "down"}">{escape(it["effect_label"])}</div>'
                 f'{escape(it["strength"].capitalize())} signal<br>Sources: {escape(it["sources"])}</div></div>')
    return f'<div class="ew-ledger">{rows}</div>'


STEPS = [("You ask", "A question about a person, company or country, in your own words. The platform restates it so you can see how it was understood."),
         ("It reads", "Ten weeks of dated public headlines. Nothing published after your cutoff date is used, and satire is dropped."),
         ("It weighs", "Each outlet is rated for credibility. Claims from several reliable outlets count for more; unconfirmed ones barely count."),
         ("It estimates", "A starting value for how often such events happen, adjusted by each development, with a range and the reasons.")]


def steps() -> str:
    return '<div class="ew-steps">' + "".join(
        f'<div class="ew-step"><div class="n">{i}</div><div class="t">{escape(t)}</div><div class="d">{escape(d)}</div></div>'
        for i, (t, d) in enumerate(STEPS, 1)) + "</div>"


def two_lists(left_title: str, left: list[str], right_title: str, right: list[str]) -> str:
    li = lambda xs: "".join(f"<li>{escape(x)}</li>" for x in xs)
    return (f'<div class="ew-two"><div><h4>{escape(left_title)}</h4><ul>{li(left)}</ul></div>'
            f'<div><h4>{escape(right_title)}</h4><ul>{li(right)}</ul></div></div>')


def tiers(rows: list[tuple[str, float, str]]) -> str:
    return '<div class="ew-tiers">' + "".join(
        f'<div class="lab">{escape(lab)}</div><div class="bar" style="width:{max(score, 0.02) * 100:.0f}%"></div><div class="eg">{escape(eg)}</div>'
        for lab, score, eg in rows) + "</div>"


PIPELINE_SVG = f"""
<svg viewBox="0 0 1040 150" role="img" aria-label="How a question becomes an estimate" style="width:100%;max-width:1040px;margin:0.4rem 0 1rem 0">
  <defs><marker id="a" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0 0L10 5L0 10z" fill="{INK}"/></marker></defs>
  <g font-family="IBM Plex Sans, sans-serif" font-size="15" fill="{INK}">
    <g><rect x="2" y="40" width="150" height="70" rx="6" fill="#fff" stroke="{INK}" stroke-width="1.5"/><text x="77" y="72" text-anchor="middle" font-weight="600">Your question</text><text x="77" y="93" text-anchor="middle" font-size="12.5" fill="{SLATE}">restated and checked</text></g>
    <g><rect x="198" y="40" width="160" height="70" rx="6" fill="#fff" stroke="{INK}" stroke-width="1.5"/><text x="278" y="72" text-anchor="middle" font-weight="600">Dated headlines</text><text x="278" y="93" text-anchor="middle" font-size="12.5" fill="{SLATE}">only up to your cutoff</text></g>
    <g><rect x="404" y="40" width="160" height="70" rx="6" fill="#fff" stroke="{INK}" stroke-width="1.5"/><text x="484" y="72" text-anchor="middle" font-weight="600">Source weighting</text><text x="484" y="93" text-anchor="middle" font-size="12.5" fill="{SLATE}">credibility, confirmation</text></g>
    <g><rect x="610" y="40" width="170" height="70" rx="6" fill="#fff" stroke="{INK}" stroke-width="1.5"/><text x="695" y="72" text-anchor="middle" font-weight="600">Developments</text><text x="695" y="93" text-anchor="middle" font-size="12.5" fill="{SLATE}">picked out by an AI reader</text></g>
    <g><rect x="826" y="30" width="210" height="90" rx="6" fill="{INK}"/><text x="931" y="64" text-anchor="middle" font-weight="600" fill="#fff">Engine sets the number</text><text x="931" y="86" text-anchor="middle" font-size="12.5" fill="#C9D1E3">starting value, evidence,</text><text x="931" y="103" text-anchor="middle" font-size="12.5" fill="#C9D1E3">range</text></g>
    <g stroke="{INK}" stroke-width="1.5" marker-end="url(#a)"><line x1="154" y1="75" x2="194" y2="75"/><line x1="360" y1="75" x2="400" y2="75"/><line x1="566" y1="75" x2="606" y2="75"/><line x1="782" y1="75" x2="822" y2="75"/></g>
  </g>
</svg>
"""

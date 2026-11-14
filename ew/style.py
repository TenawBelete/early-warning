"""Look and feel: one stylesheet and the HTML for the site's panels.

Design: a briefing document, not a dashboard. The estimate is written as a
sentence in a serif face and placed on a seven-word scale (very unlikely to
very likely), the way analysts word estimates, with an amber marker on ink
blue. Everything else stays quiet.

Every piece of dynamic text is escaped before it is placed in HTML, because
it can come from a user, a headline or an AI model.
"""
from __future__ import annotations

import random
from html import escape

BG, SURFACE, LINE, TEXT, MUTED, AMBER, ICE = "#0A0E16", "#121826", "#252E40", "#E9EDF5", "#9AA6BC", "#F2A900", "#7CC4FF"
INK, SLATE = TEXT, MUTED  # names kept for the diagram below
WORDS = [(0.05, "Very unlikely"), (0.25, "Unlikely"), (0.45, "Less likely than not"), (0.55, "Roughly even"),
         (0.75, "More likely than not"), (0.95, "Likely"), (1.0, "Very likely")]

CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&display=swap');
html, body, [class*="css"], .stMarkdown, button, input, textarea {{ font-family: 'IBM Plex Sans', 'Source Sans Pro', sans-serif; }}
.stApp {{ background: {BG}; }}
header[data-testid="stHeader"] {{ background: transparent; }}
.block-container {{ padding-top: 1.1rem; max-width: 1240px; }}
h1, h2, h3, h4, [data-testid="stHeading"] * {{ color: #FFFFFF !important; letter-spacing: -0.02em; }}
h1, [data-testid="stHeading"] h1 {{ font-weight: 700; font-size: 2.6rem; line-height: 1.1; }}
h2, [data-testid="stHeading"] h2 {{ font-size: 1.7rem; font-weight: 600; margin-top: 1.2rem; }}
p, li {{ color: {TEXT}; }}
a {{ color: {ICE}; }}

/* top navigation */
.st-key-topnav {{ border-bottom: 1px solid {LINE}; padding: 0.2rem 0 0.55rem 0; margin-bottom: 1.6rem; }}
.ew-brand-name {{ font-size: 1.25rem; font-weight: 700; color: #FFFFFF; letter-spacing: -0.01em; white-space: nowrap; padding-top: 0.35rem; }}
.ew-brand-name span {{ display: inline-block; width: 11px; height: 11px; background: {AMBER}; margin-right: 0.6rem; transform: rotate(45deg); }}
.ew-brand-name small {{ font-weight: 400; color: {MUTED}; font-size: 0.86rem; margin-left: 0.7rem; }}
.st-key-topnav [role="radiogroup"] {{ justify-content: flex-end; gap: 0.2rem; flex-wrap: nowrap; }}
.st-key-topnav [data-testid="stRadioOption"] > div > div:first-child {{ display: none; }}
.st-key-topnav [data-testid="stRadioOption"] {{ padding: 0.45rem 0.8rem; border-bottom: 2px solid transparent; cursor: pointer; margin: 0; white-space: nowrap; }}
.st-key-topnav [data-testid="stRadioOption"] p {{ color: {MUTED}; font-weight: 600; font-size: 0.97rem; }}
.st-key-topnav [data-testid="stRadioOption"]:hover p {{ color: #FFFFFF; }}
.st-key-topnav [data-testid="stRadioOption"][data-selected="true"] {{ border-bottom-color: {AMBER}; }}
.st-key-topnav [data-testid="stRadioOption"][data-selected="true"] p {{ color: #FFFFFF; }}
.st-key-topnav [data-testid="stRadioOption"]:focus-within {{ outline: 2px solid {AMBER}; outline-offset: 2px; }}
@media (max-width: 860px) {{ .st-key-topnav [role="radiogroup"] {{ flex-wrap: wrap; justify-content: flex-start; }} }}

/* controls */
.stButton > button[kind="primary"], .stFormSubmitButton > button {{ background: {AMBER}; color: #0A0E16; border: 0; border-radius: 4px; padding: 0.65rem 1.6rem; font-weight: 700; }}
.stButton > button[kind="primary"] p {{ color: #0A0E16 !important; font-weight: 700; }}
.stButton > button[kind="primary"]:hover {{ background: #FFC233; color: #0A0E16; }}
.stButton > button[kind="secondary"] {{ background: transparent; border: 1px solid {LINE}; color: {TEXT}; border-radius: 4px; }}
.stButton > button[kind="secondary"]:hover {{ border-color: {AMBER}; color: #FFFFFF; }}
.stButton > button:focus-visible, input:focus-visible {{ outline: 2px solid {AMBER}; outline-offset: 2px; }}
[data-testid="stTextInput"] input {{ border-radius: 4px; padding: 0.8rem 0.95rem; font-size: 1.05rem; background: {SURFACE}; color: #FFFFFF; border: 1px solid {LINE}; }}
[data-testid="stTextInput"] input::placeholder {{ color: #6F7C95; }}
[data-testid="stMetric"] {{ background: {SURFACE}; border: 1px solid {LINE}; border-radius: 6px; padding: 0.9rem 1.05rem; }}
[data-testid="stMetricLabel"] p {{ color: {MUTED}; font-size: 0.86rem; }}
[data-testid="stMetricValue"] {{ color: #FFFFFF; font-size: 1.6rem; font-weight: 600; }}
[data-testid="stExpander"] {{ background: {SURFACE}; border: 1px solid {LINE}; border-radius: 6px; }}
.stTabs [data-baseweb="tab-list"] {{ gap: 1.6rem; border-bottom: 1px solid {LINE}; }}
.stTabs [data-baseweb="tab"] {{ font-weight: 600; color: {MUTED}; }}
.stTabs [aria-selected="true"] {{ color: #FFFFFF; }}
.ew-lede {{ font-size: 1.15rem; line-height: 1.55; color: #C5CEDF; max-width: 62ch; margin: 0.2rem 0 1.4rem 0; }}

/* hero */
.ew-hero {{ position: relative; overflow: hidden; border: 1px solid {LINE}; border-radius: 10px; background: linear-gradient(120deg, #0E1422 0%, #131B2E 55%, #0E1422 100%); padding: 3.6rem 3rem 3.2rem 3rem; margin-bottom: 1.4rem; min-height: 330px; }}
.ew-hero svg {{ position: absolute; right: 0; top: 0; height: 100%; width: 58%; opacity: 0.95; }}
.ew-hero .in {{ position: relative; max-width: 600px; }}
.ew-hero h1 {{ font-size: 3.1rem; line-height: 1.05; margin: 0 0 1rem 0; color: #FFFFFF; font-weight: 700; padding: 0; }}
.ew-hero p {{ font-size: 1.18rem; line-height: 1.55; color: #C5CEDF; margin: 0; }}
.ew-cards {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 1.1rem; margin: 0.6rem 0 1.8rem 0; }}
.ew-card {{ background: {SURFACE}; border: 1px solid {LINE}; border-radius: 8px; padding: 1.5rem 1.5rem 1.3rem 1.5rem; }}
.ew-card svg {{ width: 34px; height: 34px; margin-bottom: 0.9rem; }}
.ew-card .t {{ font-size: 1.15rem; font-weight: 600; color: #FFFFFF; margin-bottom: 0.4rem; }}
.ew-card .d {{ color: #B9C3D6; line-height: 1.55; font-size: 0.98rem; }}
.ew-foot {{ border-top: 1px solid {LINE}; margin-top: 3rem; padding: 1.4rem 0 0.6rem 0; color: {MUTED}; font-size: 0.9rem; line-height: 1.6; }}
.ew-foot b {{ color: {TEXT}; }}

/* answer panel */
.ew-brief {{ background: {SURFACE}; border: 1px solid {LINE}; border-top: 3px solid {AMBER}; border-radius: 8px; padding: 1.9rem 2rem 1.5rem 2rem; margin: 0.8rem 0 1.1rem 0; }}
.ew-brief .ew-statement {{ font-size: 1.6rem; font-weight: 500; line-height: 1.3; color: #FFFFFF; max-width: 46ch; letter-spacing: -0.01em; }}
.ew-brief .ew-verdict {{ display: flex; align-items: baseline; gap: 0.9rem; flex-wrap: wrap; margin-top: 1.2rem; }}
.ew-brief .ew-word {{ font-size: 2.1rem; font-weight: 700; color: {AMBER}; letter-spacing: -0.02em; line-height: 1.1; }}
.ew-brief .ew-num {{ font-size: 1.25rem; font-weight: 500; color: #FFFFFF; }}
.ew-brief .ew-range {{ font-size: 0.95rem; color: {MUTED}; }}
.ew-brief .ew-frame {{ font-size: 0.86rem; color: {MUTED}; margin-top: 1.1rem; line-height: 1.5; max-width: 80ch; }}
.ew-scale {{ position: relative; margin: 1.5rem 0 0 0; }}
.ew-segs {{ display: flex; gap: 3px; height: 12px; }}
.ew-segs div {{ background: #26314A; border-radius: 2px; }}
.ew-segs div.on {{ background: #3E4E73; }}
.ew-span {{ position: absolute; top: 3px; height: 6px; background: {AMBER}; opacity: 0.55; border-radius: 3px; }}
.ew-mark {{ position: absolute; top: -5px; width: 4px; height: 22px; margin-left: -2px; background: {AMBER}; border-radius: 2px; }}
.ew-ticks {{ display: flex; justify-content: space-between; font-size: 0.76rem; color: {MUTED}; margin-top: 0.45rem; }}
.ew-cand {{ display: grid; grid-template-columns: minmax(130px, 230px) 1fr 5.2rem; gap: 1rem; align-items: center; margin-top: 0.95rem; }}
.ew-cand .ew-name {{ font-weight: 600; color: #FFFFFF; }}
.ew-cand .ew-val {{ text-align: right; color: #FFFFFF; font-weight: 600; }}
.ew-cand.ew-other .ew-name, .ew-cand.ew-other .ew-val {{ color: {MUTED}; font-weight: 400; }}
.ew-bar {{ position: relative; height: 8px; background: #26314A; border-radius: 4px; }}
.ew-bar .ew-span {{ top: 1px; }}
.ew-bar .ew-mark {{ top: -6px; height: 20px; }}

.ew-note {{ background: {SURFACE}; border: 1px solid {LINE}; border-left: 3px solid {ICE}; border-radius: 6px; padding: 0.85rem 1.1rem; margin: 0.4rem 0 0.9rem 0; color: {TEXT}; line-height: 1.5; }}
.ew-note b {{ color: #FFFFFF; }}
.ew-ledger {{ background: {SURFACE}; border: 1px solid {LINE}; border-radius: 6px; margin: 0.3rem 0 0.8rem 0; }}
.ew-item {{ display: grid; grid-template-columns: 6.5rem 1fr 12.5rem; gap: 1.2rem; padding: 0.95rem 1.1rem; border-top: 1px solid {LINE}; align-items: start; }}
.ew-item:first-child {{ border-top: 0; }}
.ew-item .ew-date {{ color: {MUTED}; font-size: 0.9rem; }}
.ew-item .ew-what {{ color: {TEXT}; line-height: 1.45; }}
.ew-item .ew-what a {{ color: {ICE}; font-size: 0.88rem; }}
.ew-item .ew-who {{ font-weight: 600; color: #FFFFFF; }}
.ew-item .ew-meta {{ font-size: 0.88rem; color: {MUTED}; line-height: 1.5; }}
.ew-eff {{ font-weight: 600; color: #FFFFFF; }}
.ew-eff.up::before {{ content: "\\25B2"; color: #4CC38A; margin-right: 0.35rem; font-size: 0.75rem; }}
.ew-eff.down::before {{ content: "\\25BC"; color: #F0725C; margin-right: 0.35rem; font-size: 0.75rem; }}

.ew-steps {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 0; margin: 0.6rem 0 1.6rem 0; border-top: 2px solid {AMBER}; }}
.ew-step {{ padding: 1.1rem 1.4rem 0.4rem 0; }}
.ew-step .n {{ font-size: 1.5rem; font-weight: 700; color: {AMBER}; line-height: 1; }}
.ew-step .t {{ font-weight: 600; color: #FFFFFF; margin: 0.5rem 0 0.25rem 0; font-size: 1.05rem; }}
.ew-step .d {{ color: #B9C3D6; font-size: 0.96rem; line-height: 1.55; }}
.ew-two {{ display: grid; grid-template-columns: 1fr 1fr; gap: 1.1rem; margin: 0.4rem 0 1.4rem 0; }}
.ew-two > div {{ background: {SURFACE}; border: 1px solid {LINE}; border-radius: 8px; padding: 1.3rem 1.5rem; }}
.ew-two h4 {{ color: #FFFFFF; margin: 0 0 0.6rem 0; font-size: 1.1rem; padding: 0; }}
.ew-two ul {{ margin: 0; padding-left: 1.1rem; line-height: 1.65; }}
.ew-two li {{ color: #C5CEDF; }}
.ew-tiers {{ display: grid; grid-template-columns: 9rem 1fr; gap: 0.5rem 1rem; align-items: center; max-width: 640px; margin: 0.5rem 0 1.2rem 0; }}
.ew-tiers .lab {{ color: #FFFFFF; font-weight: 600; }}
.ew-tiers .bar {{ height: 14px; background: {AMBER}; border-radius: 2px; }}
.ew-tiers .eg {{ grid-column: 2; color: {MUTED}; font-size: 0.88rem; margin-top: -0.35rem; }}
.ew-example-tag {{ color: {MUTED}; font-size: 0.9rem; margin: 0.4rem 0 -0.3rem 0; }}
@media (max-width: 860px) {{
  .ew-steps, .ew-two, .ew-cards {{ grid-template-columns: 1fr; }}
  .ew-item {{ grid-template-columns: 1fr; gap: 0.3rem; }}
  .ew-cand {{ grid-template-columns: 1fr 4.5rem; }} .ew-cand .ew-bar {{ grid-column: 1 / -1; order: 3; }}
  .ew-hero {{ padding: 2rem 1.3rem; }} .ew-hero h1 {{ font-size: 2.1rem; }} .ew-hero svg {{ opacity: 0.25; width: 100%; }}
  .ew-brief {{ padding: 1.3rem 1.2rem; }} .ew-brand-name small {{ display: none; }}
}}
</style>
"""


def _hero_art() -> str:
    """Original artwork drawn in code: scattered dated reports settle onto a seven-step scale."""
    rng = random.Random(7)
    dots, lines = "", ""
    for _ in range(150):
        x, y = rng.uniform(40, 580), rng.uniform(20, 235)
        hot = rng.random() < 0.12
        dots += f'<circle cx="{x:.0f}" cy="{y:.0f}" r="{2.6 if hot else 1.5}" fill="{AMBER if hot else "#3B4864"}"/>'
        if hot:
            lines += f'<path d="M{x:.0f} {y:.0f} C{x:.0f} {y + 60:.0f}, 430 250, 430 292" stroke="{AMBER}" stroke-opacity="0.28" fill="none"/>'
    segs, x0 = "", 60
    for w in (26, 104, 104, 52, 104, 104, 26):
        segs += f'<rect x="{x0}" y="296" width="{w - 4}" height="10" rx="2" fill="#2A3550"/>'
        x0 += w
    return (f'<svg viewBox="0 0 620 340" preserveAspectRatio="xMaxYMid slice" aria-hidden="true">{lines}{dots}{segs}'
            f'<rect x="360" y="298" width="150" height="6" rx="3" fill="{AMBER}" fill-opacity="0.5"/>'
            f'<rect x="428" y="284" width="4" height="34" rx="2" fill="{AMBER}"/></svg>')


ICONS = {
    "ask": f'<svg viewBox="0 0 34 34" fill="none" stroke="{AMBER}" stroke-width="2"><rect x="3" y="6" width="28" height="18" rx="3"/><path d="M10 30l5-6"/><path d="M10 13h14M10 18h8"/></svg>',
    "evidence": f'<svg viewBox="0 0 34 34" fill="none" stroke="{AMBER}" stroke-width="2"><path d="M5 8h24M5 17h24M5 26h14"/><circle cx="27" cy="26" r="3"/></svg>',
    "score": f'<svg viewBox="0 0 34 34" fill="none" stroke="{AMBER}" stroke-width="2"><path d="M4 29h26"/><path d="M8 29V17M17 29V7M26 29V13"/></svg>',
}


def hero(title: str, text: str) -> str:
    return f'<div class="ew-hero">{_hero_art()}<div class="in"><h1>{escape(title)}</h1><p>{escape(text)}</p></div></div>'


def cards(items: list[tuple[str, str, str]]) -> str:
    return '<div class="ew-cards">' + "".join(
        f'<div class="ew-card">{ICONS[icon]}<div class="t">{escape(t)}</div><div class="d">{escape(d)}</div></div>' for icon, t, d in items) + "</div>"


def footer(name: str, lines: list[str]) -> str:
    return (f'<div class="ew-foot"><b>{escape(name)}</b><br>' + "<br>".join(escape(x) for x in lines if x)
            + "<br>A prototype. Estimates from dated public reporting, never certainties. No track record yet.</div>")


def brand(name: str, tagline: str) -> str:
    return f'<div class="ew-brand-name"><span></span>{escape(name)}<small>{escape(tagline)}</small></div>'


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
  <defs><marker id="a" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0 0L10 5L0 10z" fill="{MUTED}"/></marker></defs>
  <g font-family="IBM Plex Sans, sans-serif" font-size="15" fill="{INK}">
    <g><rect x="2" y="40" width="150" height="70" rx="6" fill="{SURFACE}" stroke="{LINE}" stroke-width="1.5"/><text x="77" y="72" text-anchor="middle" font-weight="600">Your question</text><text x="77" y="93" text-anchor="middle" font-size="12.5" fill="{SLATE}">restated and checked</text></g>
    <g><rect x="198" y="40" width="160" height="70" rx="6" fill="{SURFACE}" stroke="{LINE}" stroke-width="1.5"/><text x="278" y="72" text-anchor="middle" font-weight="600">Dated headlines</text><text x="278" y="93" text-anchor="middle" font-size="12.5" fill="{SLATE}">only up to your cutoff</text></g>
    <g><rect x="404" y="40" width="160" height="70" rx="6" fill="{SURFACE}" stroke="{LINE}" stroke-width="1.5"/><text x="484" y="72" text-anchor="middle" font-weight="600">Source weighting</text><text x="484" y="93" text-anchor="middle" font-size="12.5" fill="{SLATE}">credibility, confirmation</text></g>
    <g><rect x="610" y="40" width="170" height="70" rx="6" fill="{SURFACE}" stroke="{LINE}" stroke-width="1.5"/><text x="695" y="72" text-anchor="middle" font-weight="600">Developments</text><text x="695" y="93" text-anchor="middle" font-size="12.5" fill="{SLATE}">picked out by an AI reader</text></g>
    <g><rect x="826" y="30" width="210" height="90" rx="6" fill="{AMBER}"/><text x="931" y="64" text-anchor="middle" font-weight="700" fill="#0A0E16">Engine sets the number</text><text x="931" y="86" text-anchor="middle" font-size="12.5" fill="#3A2A00">starting value, evidence,</text><text x="931" y="103" text-anchor="middle" font-size="12.5" fill="#3A2A00">range</text></g>
    <g stroke="{MUTED}" stroke-width="1.5" marker-end="url(#a)"><line x1="154" y1="75" x2="194" y2="75"/><line x1="360" y1="75" x2="400" y2="75"/><line x1="566" y1="75" x2="606" y2="75"/><line x1="782" y1="75" x2="822" y2="75"/></g>
  </g>
</svg>
"""

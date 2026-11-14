"""Look and feel: one stylesheet and the HTML for the result panels.

Every piece of dynamic text is escaped before it is placed in HTML, because
it can come from a user, a headline or an AI model.
"""
from __future__ import annotations

from html import escape

INK, TEAL, MUTED, LINE = "#0F1B2D", "#0E7C86", "#5B6778", "#DDE2EA"

CSS = f"""
<style>
.block-container {{ padding-top: 3.6rem; max-width: 1180px; }}
h1 {{ color: {INK}; font-weight: 700; letter-spacing: -0.02em; }}
h2, h3 {{ color: {INK}; letter-spacing: -0.01em; }}
[data-testid="stSidebar"] {{ border-right: 0; background: {INK}; }}
[data-testid="stSidebar"] [data-testid="stSidebarContent"] {{ background: {INK}; padding-top: 1.2rem; }}
[data-testid="stSidebar"] * {{ color: #E8EDF4; }}
.ew-brand {{ font-size: 0.78rem; letter-spacing: 0.18em; text-transform: uppercase; color: #3CC4CF !important; font-weight: 700; }}
.ew-brand-name {{ font-size: 1.45rem; font-weight: 700; color: #FFFFFF !important; margin: 0.15rem 0 0.35rem 0; line-height: 1.15; }}
.ew-brand-tag {{ font-size: 0.85rem; color: #A9B6C8 !important; margin-bottom: 1.1rem; }}
.stButton > button[kind="primary"] {{ background: {TEAL}; border: 0; border-radius: 8px; padding: 0.55rem 1.6rem; font-weight: 600; }}
.stButton > button[kind="primary"]:hover {{ background: #0A636B; }}
[data-testid="stTextInput"] input {{ border-radius: 8px; padding: 0.7rem 0.9rem; font-size: 1.02rem; }}
[data-testid="stMetric"] {{ background: #FFFFFF; border: 1px solid {LINE}; border-radius: 10px; padding: 0.9rem 1rem; }}
[data-testid="stMetricLabel"] p {{ color: {MUTED}; font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.06em; }}
[data-testid="stMetricValue"] {{ color: {INK}; font-size: 1.7rem; font-weight: 700; }}
[data-testid="stExpander"] {{ background: #FFFFFF; border: 1px solid {LINE}; border-radius: 10px; }}
.stTabs [data-baseweb="tab-list"] {{ gap: 1.4rem; border-bottom: 1px solid {LINE}; }}
.stTabs [data-baseweb="tab"] {{ font-weight: 600; color: {MUTED}; }}
.stTabs [aria-selected="true"] {{ color: {TEAL}; }}
.ew-eyebrow {{ font-size: 0.76rem; letter-spacing: 0.14em; text-transform: uppercase; color: {TEAL}; font-weight: 700; margin-bottom: 0.2rem; }}
.ew-hero {{ background: {INK}; border-radius: 14px; padding: 1.6rem 1.8rem 1.4rem 1.8rem; margin: 0.6rem 0 1.1rem 0; color: #FFFFFF; }}
.ew-hero .ew-q {{ font-size: 0.8rem; letter-spacing: 0.12em; text-transform: uppercase; color: #3CC4CF; font-weight: 700; }}
.ew-hero .ew-row {{ display: flex; align-items: baseline; gap: 1.1rem; flex-wrap: wrap; margin-top: 0.35rem; }}
.ew-hero .ew-band {{ font-size: 2.3rem; font-weight: 700; letter-spacing: -0.02em; line-height: 1.1; color: #FFFFFF; }}
.ew-hero .ew-num {{ font-size: 1.5rem; font-weight: 600; color: #3CC4CF; }}
.ew-hero .ew-range {{ font-size: 0.95rem; color: #A9B6C8; }}
.ew-hero .ew-event {{ font-size: 1.02rem; color: #E8EDF4; margin-top: 0.7rem; line-height: 1.45; }}
.ew-hero .ew-frame {{ font-size: 0.82rem; color: #A9B6C8; margin-top: 0.85rem; }}
.ew-track {{ position: relative; height: 10px; background: #26374F; border-radius: 6px; margin: 1.1rem 0 0.3rem 0; }}
.ew-span {{ position: absolute; top: 0; height: 10px; background: #2E8F98; border-radius: 6px; opacity: 0.75; }}
.ew-dot {{ position: absolute; top: -4px; width: 18px; height: 18px; margin-left: -9px; background: #FFFFFF; border: 3px solid #3CC4CF; border-radius: 50%; }}
.ew-scale {{ display: flex; justify-content: space-between; font-size: 0.72rem; color: #8090A6; }}
.ew-cand {{ display: grid; grid-template-columns: minmax(120px, 220px) 1fr 70px; gap: 0.9rem; align-items: center; margin-top: 0.75rem; }}
.ew-cand .ew-name {{ font-weight: 600; color: #FFFFFF; font-size: 0.98rem; }}
.ew-cand .ew-val {{ text-align: right; color: #3CC4CF; font-weight: 700; }}
.ew-cand .ew-track {{ margin: 0; }}
.ew-cand.ew-other .ew-name, .ew-cand.ew-other .ew-val {{ color: #A9B6C8; font-weight: 500; }}
.ew-note {{ background: #FFFFFF; border: 1px solid {LINE}; border-left: 4px solid {TEAL}; border-radius: 8px; padding: 0.8rem 1rem; margin: 0.4rem 0 1rem 0; color: #18212F; }}
.ew-note b {{ color: {INK}; }}
</style>
"""

BRAND = ('<div class="ew-brand">Early Warning</div><div class="ew-brand-name">Public-evidence forecasting</div>'
         '<div class="ew-brand-tag">Prototype. Estimates from dated public reporting, never certainties.</div>')


def _pc(x: float) -> float:
    return max(0.0, min(100.0, x * 100))


def _track(p: float, lo: float, hi: float) -> str:
    return (f'<div class="ew-track"><div class="ew-span" style="left:{_pc(lo):.1f}%;width:{max(_pc(hi) - _pc(lo), 1.0):.1f}%"></div>'
            f'<div class="ew-dot" style="left:{_pc(p):.1f}%"></div></div>')


def hero_yes_no(band: str, num: str, rng: str, p: float, lo: float, hi: float, event: str, deadline: str) -> str:
    return ('<div class="ew-hero"><div class="ew-q">Estimate</div>'
            f'<div class="ew-row"><div class="ew-band">{escape(band)}</div><div class="ew-num">about {escape(num)}</div>'
            f'<div class="ew-range">Range {escape(rng)}</div></div>'
            + _track(p, lo, hi) +
            '<div class="ew-scale"><span>0%</span><span>25%</span><span>50%</span><span>75%</span><span>100%</span></div>'
            f'<div class="ew-event">That this happens by {escape(deadline)}: {escape(event)}.</div>'
            '<div class="ew-frame">A model estimate from public news reporting, not a statement of fact.</div></div>')


def hero_who(rows: list[tuple[str, str, float, float, float, bool]]) -> str:
    """rows: (name, shown value, p, lo, hi, is_other), most likely first."""
    top = rows[0]
    body = "".join(
        f'<div class="ew-cand{" ew-other" if other else ""}"><div class="ew-name">{escape(name)}</div>{_track(p, lo, hi)}'
        f'<div class="ew-val">{escape(val)}</div></div>' for name, val, p, lo, hi, other in rows)
    return ('<div class="ew-hero"><div class="ew-q">Estimate</div>'
            f'<div class="ew-row"><div class="ew-band">Most likely: {escape(top[0])}</div><div class="ew-num">about {escape(top[1])}</div></div>'
            + body +
            '<div class="ew-frame">A model estimate from public news reporting, not a statement of fact. Bars show the range.</div></div>')


def note(label: str, text: str) -> str:
    return f'<div class="ew-note"><b>{escape(label)}</b> {escape(text)}</div>'

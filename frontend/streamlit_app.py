from __future__ import annotations

import html
import itertools
import json
import math
import os
import random
import secrets
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

import altair as alt
import pandas as pd
import requests
import streamlit as st
import streamlit.components.v1 as components
from dotenv import load_dotenv

FRONTEND_DIR = str(Path(__file__).resolve().parent)
PROJECT_ROOT = str(Path(FRONTEND_DIR).parent)
for import_path in (PROJECT_ROOT, FRONTEND_DIR):
    if import_path not in sys.path:
        sys.path.insert(0, import_path)

from event_simulation import render_simulation

try:
    import pydeck as pdk
except ImportError:  # pragma: no cover - fallback when pydeck is absent
    pdk = None

load_dotenv()
API_URL = os.getenv("API_URL", "https://netcoopai.onrender.com").rstrip("/")
CAMPUS_MAP_URL = os.getenv(
    "CAMPUS_MAP_URL",
    "https://netcoopai-campus-map.onrender.com",
).rstrip("/")
PAGES = (
    "Overview",
    "Live Network Map",
    "Event Simulation",
    "Device Inventory",
    "Agent Control Center",
    "Incident Investigation",
    "Knowledge Base",
    "Analytics",
    "Settings",
)

# Cosmetic switches -----------------------------------------------------------
# The mockup shows small trend sparklines on KPI cards, agents, incidents and the
# sidebar health card. The API does not expose per-item history, so these are
# decorative curves (deterministic per item). Set to False to hide them.
SHOW_SPARKLINES = True
USER_INITIALS = "JD"
LOCAL_TZ = datetime.now().astimezone().tzinfo

PAGE_HEADERS: dict[str, tuple[str, str, str]] = {
    "Overview": ("👋", "Welcome to NetCoop AI", "Real-time network monitoring, intelligent diagnosis and proactive recommendations"),
    "Live Network Map": ("🔗", "Live Network Map", "Campus geospatial view of the IIT Bhubaneswar device inventory and current health"),
    "Event Simulation": ("🎪", "Event Impact Simulation", "Explore event-related congestion, spill-over and mitigation scenarios without changing live network state."),
    "Device Inventory": ("📍", "Device Inventory", "Upload a CSV or GeoJSON inventory from the sidebar, then review locations and current status."),
    "Agent Control Center": ("🤖", "Agent Control Center", "Live status and most recent execution latency for every LangGraph workflow agent."),
    "Incident Investigation": ("🚨", "Incident Investigation", "Inspect the evidence, review ranked probable causes, and answer agent follow-up questions."),
    "Knowledge Base": ("🧠", "Knowledge Base", "Search static diagnostic facts and correlation rules. Context-specific fact entries are heuristic references, not independent probabilities."),
    "Analytics": ("📊", "Network Analytics", "Telemetry trends, current device status and historical baselines"),
    "Settings": ("⚙️", "Settings & System Status", "Unit contract, backend configuration status, and service health."),
}

# ---------------------------------------------------------------------------
# Icons (Feather-style strokes) – used inline and as CSS masks for the sidebar nav
# ---------------------------------------------------------------------------
ICONS: dict[str, str] = {
    "home": '<path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><path d="M9 22V12h6v10"/>',
    "pin": '<path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/>',
    "database": '<ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"/><path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"/>',
    "cpu": '<rect x="4" y="4" width="16" height="16" rx="2"/><rect x="9" y="9" width="6" height="6"/><path d="M9 1v3M15 1v3M9 20v3M15 20v3M20 9h3M20 14h3M1 9h3M1 14h3"/>',
    "alert": '<path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><path d="M12 9v4"/><path d="M12 17h.01"/>',
    "book": '<path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/>',
    "book-open": '<path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/><path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/>',
    "chart": '<path d="M18 20V10M12 20V4M6 20v-6"/>',
    "sliders": '<path d="M4 21v-7M4 10V3M12 21v-9M12 8V3M20 21v-5M20 12V3M1 14h6M9 8h6M17 16h6"/>',
    "server": '<rect x="2" y="2" width="20" height="8" rx="2"/><rect x="2" y="14" width="20" height="8" rx="2"/><path d="M6 6h.01M6 18h.01"/>',
    "check": '<path d="M20 6L9 17l-5-5"/>',
    "exclaim": '<path d="M12 6v8"/><path d="M12 18h.01"/>',
    "bolt": '<path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/>',
    "bell": '<path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/>',
    "wifi": '<path d="M5 12.55a11 11 0 0 1 14.08 0"/><path d="M1.42 9a16 16 0 0 1 21.16 0"/><path d="M8.53 16.11a6 6 0 0 1 6.95 0"/><path d="M12 20h.01"/>',
    "shield": '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>',
    "activity": '<path d="M22 12h-4l-3 9L9 3l-3 9H2"/>',
    "bulb": '<path d="M9 18h6"/><path d="M10 22h4"/><path d="M12 2a7 7 0 0 0-4 12.7c.6.5 1 1.3 1 2.3h6c0-1 .4-1.8 1-2.3A7 7 0 0 0 12 2z"/>',
    "gauge": '<path d="M12 14l4-4"/><path d="M3.34 19a10 10 0 1 1 17.32 0"/>',
    "search": '<circle cx="11" cy="11" r="8"/><path d="M21 21l-4.35-4.35"/>',
}
NAV_ICONS = ["home", "pin", "database", "cpu", "alert", "book", "chart", "sliders"]
_UID = itertools.count(1)


def icon(name: str, size: int = 18, color: str = "currentColor", stroke: float = 2) -> str:
    return (
        f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="{color}" '
        f'stroke-width="{stroke}" stroke-linecap="round" stroke-linejoin="round">{ICONS[name]}</svg>'
    )


def nav_icon_css() -> str:
    rules = []
    for index, name in enumerate(NAV_ICONS, 1):
        inner = ICONS[name].replace('"', "'")
        svg = (
            "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='black' "
            f"stroke-width='2' stroke-linecap='round' stroke-linejoin='round'>{inner}</svg>"
        )
        uri = quote(svg, safe="")
        rules.append(
            f'[data-testid="stSidebar"] [data-testid="stRadio"] label:nth-of-type({index}) p::before'
            f'{{-webkit-mask-image:url("data:image/svg+xml,{uri}");mask-image:url("data:image/svg+xml,{uri}");}}'
        )
    return "".join(rules)


def H(markup: str) -> str:
    """Collapse multi-line HTML so Markdown never mistakes indentation for a code block."""
    return "".join(line.strip() for line in markup.strip().splitlines())


def md(markup: str) -> None:
    st.markdown(H(markup), unsafe_allow_html=True)


def spark(seed: str, color: str, *, width: int = 120, height: int = 36, fill: bool = True, trend: float = 0.0) -> str:
    """Decorative smooth sparkline, deterministic per seed."""
    if not SHOW_SPARKLINES:
        return ""
    points = 18
    rng = random.Random(seed)
    value, ys = 0.5, []
    for _ in range(points):
        value = min(0.95, max(0.05, value + rng.uniform(-0.2, 0.2) + trend / points))
        ys.append(value)
    low, high = min(ys), max(ys)
    span = (high - low) or 1.0
    pad = 3
    coords = [
        (pad + i * (width - 2 * pad) / (points - 1), pad + (1 - (y - low) / span) * (height - 2 * pad - 4))
        for i, y in enumerate(ys)
    ]
    path = f"M{coords[0][0]:.1f},{coords[0][1]:.1f}"
    for (x0, y0), (x1, y1) in zip(coords, coords[1:]):
        path += f" Q{x0:.1f},{y0:.1f} {(x0 + x1) / 2:.1f},{(y0 + y1) / 2:.1f}"
    path += f" L{coords[-1][0]:.1f},{coords[-1][1]:.1f}"
    gid = f"sg{next(_UID)}"
    area = f'<path d="{path} L{width - pad},{height} L{pad},{height} Z" fill="url(#{gid})"/>' if fill else ""
    return (
        f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" fill="none">'
        f'<defs><linearGradient id="{gid}" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0" stop-color="{color}" stop-opacity=".28"/><stop offset="1" stop-color="{color}" stop-opacity="0"/>'
        f'</linearGradient></defs>{area}'
        f'<path d="{path}" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>'
    )


def logo_svg(size: int = 64) -> str:
    center, radius = 32, 22
    nodes = [
        (center + radius * math.cos(math.radians(angle)), center + radius * math.sin(math.radians(angle)))
        for angle in range(-90, 270, 60)
    ]
    lines = "".join(f'<line x1="{center}" y1="{center}" x2="{x:.1f}" y2="{y:.1f}"/>' for x, y in nodes)
    dots = "".join(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="5.5" stroke="none"/>' for x, y in nodes)
    return (
        f'<svg width="{size}" height="{size}" viewBox="0 0 64 64" fill="#6253b7" stroke="#6253b7" '
        f'stroke-width="2.5" stroke-linecap="round">{lines}<circle cx="32" cy="32" r="9" stroke="none"/>{dots}</svg>'
    )


st.set_page_config(page_title="NetCoop AI · Network Intelligence", page_icon="🌐", layout="wide")

CSS = """
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
:root{--ink:#17213d;--muted:#64708b;--purple:#6253b7;--line:#e6e9f2;--green:#20b981;--yellow:#f3b61f;--red:#ef5c62;--blue:#4f83ff;}
.stApp{background:linear-gradient(135deg,#fff8f0 0%,#f5f3ff 50%,#eefaf6 100%);color:var(--ink);font-family:'Inter','Segoe UI',system-ui,sans-serif;}
.stApp p,.stApp label,.stApp button,.stApp input,.stApp textarea{font-family:inherit;}
[data-testid="stHeader"]{background:transparent;}
[data-testid="stAppViewContainer"]{background:transparent;}
.block-container{padding:1.1rem 1.6rem 2.5rem !important;max-width:1560px;}
footer{visibility:hidden;}
h1,h2,h3,h4{color:var(--ink);letter-spacing:-.02em;}
/* ---------- sidebar ---------- */
[data-testid="stSidebar"]{background:linear-gradient(180deg,#fffaf4 0%,#f6f3ff 100%);border-right:1px solid #ece8f2;}
.brand{text-align:center;padding:4px 0 14px;}
.brand-name{font-size:1.65rem;font-weight:800;color:#1c2748;letter-spacing:-.03em;margin-top:4px;line-height:1.1;}
.brand-tag{color:var(--muted);font-size:.86rem;line-height:1.25;margin-top:4px;}
[data-testid="stSidebar"] [data-testid="stRadio"] div[role="radiogroup"]{gap:4px;}
[data-testid="stSidebar"] [data-testid="stRadio"] label{width:100%;padding:10px 14px;margin:0;border-radius:12px;color:#34405c;cursor:pointer;transition:background .15s;}
[data-testid="stSidebar"] [data-testid="stRadio"] label:hover{background:rgba(98,83,183,.09);}
[data-testid="stSidebar"] [data-testid="stRadio"] label > div:first-child{display:none;}
[data-testid="stSidebar"] [data-testid="stRadio"] label p{margin:0;font-size:.93rem;font-weight:600;color:inherit !important;}
[data-testid="stSidebar"] [data-testid="stRadio"] label:has(input:checked){background:linear-gradient(135deg,#6a5bc4,#5a4aa8);color:#fff;box-shadow:0 8px 18px rgba(98,83,183,.28);}
[data-testid="stSidebar"] [data-testid="stRadio"] label p::before{content:"";display:inline-block;width:19px;height:19px;margin-right:13px;vertical-align:-4px;background-color:currentColor;-webkit-mask-size:contain;mask-size:contain;-webkit-mask-repeat:no-repeat;mask-repeat:no-repeat;-webkit-mask-position:center;mask-position:center;}
.side-city{border-radius:22px;overflow:hidden;border:1px solid #e8e6f3;margin-top:14px;box-shadow:0 6px 18px rgba(60,65,112,.07);}
.side-city svg{display:block;}
.side-health{margin-top:12px;padding:16px 18px 10px;border-radius:20px;border:1px solid #e8e6f3;background:linear-gradient(160deg,#fff,#f5f1ff);box-shadow:0 6px 18px rgba(60,65,112,.07);}
.sh-title{font-weight:700;color:#1c2748;font-size:1rem;}
.sh-sub{color:var(--muted);font-size:.84rem;margin-bottom:8px;}
.sh-row{display:flex;align-items:center;gap:10px;}
.sh-check{width:30px;height:30px;border-radius:50%;display:grid;place-items:center;background:var(--green);color:#fff;}
.sh-val{font-size:1.65rem;font-weight:800;letter-spacing:-.03em;color:var(--ink);}
.sh-spark{margin-top:4px;line-height:0;}
/* ---------- cards ---------- */
[data-testid="stVerticalBlockBorderWrapper"]{border:1px solid var(--line) !important;border-radius:20px !important;background:linear-gradient(150deg,rgba(255,255,255,.95),rgba(248,246,255,.92)) !important;box-shadow:0 8px 28px rgba(60,65,112,.06);}
[data-testid="stMetric"]{background:linear-gradient(145deg,#fff8f1,#f3f1ff);border:1px solid var(--line);border-radius:18px;padding:14px 17px;box-shadow:0 5px 20px rgba(50,62,100,.045);}
[data-testid="stMetricLabel"]{color:var(--muted);font-weight:650;}
[data-testid="stMetricValue"]{color:var(--ink);}
[data-testid="stExpander"] details{border:1px solid var(--line);border-radius:14px;background:rgba(255,255,255,.7);}
[data-testid="stDeckGlJsonChart"]{border-radius:16px;overflow:hidden;}
[data-baseweb="input"],[data-baseweb="select"] > div{border-radius:12px !important;}
.panel-title{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:10px;}
.pt-title{display:flex;align-items:center;gap:10px;font-size:1.04rem;font-weight:700;color:var(--ink);letter-spacing:-.01em;}
.pt-icon{width:28px;height:28px;border-radius:9px;display:grid;place-items:center;font-size:.95rem;line-height:1;}
.legend{display:flex;flex-wrap:wrap;gap:6px 14px;font-size:.78rem;color:var(--muted);}
.legend i{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:6px;}
.small-muted{color:var(--muted);font-size:.83rem;}
/* ---------- top bar ---------- */
.topbar{display:flex;align-items:center;justify-content:space-between;gap:18px;padding:18px 26px;margin:0 0 16px;border-radius:26px;border:1px solid rgba(255,255,255,.75);background:radial-gradient(ellipse at 85% 10%,rgba(190,236,214,.65) 0,transparent 42%),radial-gradient(ellipse at 20% 0%,rgba(222,213,255,.7) 0,transparent 46%),linear-gradient(105deg,#fff3e4 0%,#f5f1ff 52%,#ffeee8 100%);box-shadow:0 10px 30px rgba(60,65,112,.06);}
.tb-left{display:flex;align-items:center;gap:14px;min-width:0;}
.tb-emoji{font-size:2.5rem;line-height:1;}
.tb-title{font-size:1.85rem;font-weight:800;letter-spacing:-.03em;color:var(--ink);line-height:1.15;}
.tb-sub{color:#46526f;font-size:.93rem;margin-top:4px;max-width:760px;}
.tb-right{display:flex;align-items:center;gap:14px;flex-shrink:0;}
.tb-live{display:inline-flex;align-items:center;gap:8px;font-size:.88rem;color:#2d3856;font-weight:500;white-space:nowrap;}
.tb-live i{width:8px;height:8px;border-radius:50%;background:var(--green);box-shadow:0 0 0 4px rgba(32,185,129,.18);}
.tb-conn{display:inline-flex;align-items:center;gap:8px;padding:11px 20px;border-radius:999px;background:rgba(226,247,236,.92);border:1px solid #c9efda;color:#18784c;font-weight:700;font-size:.9rem;white-space:nowrap;}
.tb-conn.warn{background:#fff4d6;border-color:#f6dd94;color:#9a6b00;}
.tb-bell,.tb-avatar{width:46px;height:46px;border-radius:50%;display:grid;place-items:center;}
.tb-bell{background:rgba(255,255,255,.75);border:1px solid #efe3e6;color:#2d3856;}
.tb-avatar{background:#e8e4fb;color:#4b3f9e;font-weight:800;border:2px solid #cfc7f3;letter-spacing:.02em;}
@media (max-width:1000px){.topbar{flex-direction:column;align-items:flex-start;}.tb-right{flex-wrap:wrap;}}
/* ---------- KPI cards ---------- */
.kpi-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:16px;margin-bottom:18px;}
.kpi{position:relative;overflow:hidden;display:flex;align-items:center;gap:14px;padding:18px;min-height:112px;border-radius:20px;border:1px solid;box-shadow:0 6px 20px rgba(50,62,100,.05);}
.kpi-icon{width:54px;height:54px;border-radius:50%;display:grid;place-items:center;flex-shrink:0;position:relative;z-index:1;}
.kpi-body{position:relative;z-index:1;}
.kpi-label{font-weight:600;font-size:.95rem;color:#27334f;}
.kpi-value{font-size:2rem;font-weight:800;line-height:1.1;color:var(--ink);letter-spacing:-.03em;}
.kpi-note{font-size:.82rem;font-weight:700;margin-top:6px;}
.kpi-spark{position:absolute;right:0;bottom:0;line-height:0;pointer-events:none;}
/* ---------- agents ---------- */
.agent-row{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:10px 2px;border-bottom:1px solid #edf0f5;}
.agent-row:last-child{border-bottom:0;}
.agent-icon{width:42px;height:42px;border-radius:50%;display:grid;place-items:center;flex-shrink:0;}
.agent-info{flex:1;min-width:0;}
.agent-name{color:#27334f;font-size:.9rem;font-weight:650;line-height:1.2;}
.agent-meta{color:var(--muted);font-size:.76rem;margin-top:3px;}
.agent-spark{line-height:0;flex-shrink:0;}
.overview-agent-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:10px;margin-top:8px;}
.overview-agent-card{display:flex;align-items:center;gap:10px;min-width:0;padding:12px;border:1px solid #e9edf5;border-radius:14px;background:rgba(255,255,255,.72);}
.overview-agent-details{min-width:0;flex:1;}
.overview-agent-name{color:#27334f;font-size:.82rem;font-weight:700;line-height:1.2;}
.overview-agent-meta{color:var(--muted);font-size:.72rem;margin-top:4px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
.status-dot{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:6px;background:#9aa3b5;}
.status-healthy{background:var(--green);} .status-ready{background:#55a5ff;}
.status-degraded,.status-stale,.status-unavailable{background:var(--red);}
.status-warning{background:var(--yellow);} .status-critical{background:var(--red);}
/* ---------- incidents ---------- */
.incident-card{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:12px 14px;margin:8px 0 6px;border-radius:14px;border:1px solid var(--line);background:linear-gradient(100deg,#f7f5ff 0%,#fff 75%);}
.incident-card.sev-critical{background:linear-gradient(100deg,#fff1ef 0%,#fff 75%);}
.incident-card.sev-warning{background:linear-gradient(100deg,#fff8e4 0%,#fff 75%);}
.incident-card.sev-resolved{background:linear-gradient(100deg,#eefaf2 0%,#fff 75%);}
.incident-main{min-width:0;flex:1;}
.incident-head{display:flex;align-items:center;flex-wrap:wrap;gap:8px;font-size:.74rem;color:var(--muted);}
.badge{display:inline-block;padding:2px 10px;border-radius:8px;font-size:.72rem;font-weight:700;}
.badge-critical{background:#ffe0dc;color:#c0392b;} .badge-warning{background:#ffefc2;color:#a56a00;}
.badge-resolved{background:#d9f5e4;color:#1b7a4a;} .badge-unknown{background:#e8ebf2;color:#5b6784;}
.incident-title{font-weight:700;color:#26324e;font-size:.93rem;margin-top:5px;line-height:1.3;}
.incident-meta{color:var(--muted);font-size:.78rem;margin-top:3px;}
.incident-spark{line-height:0;flex-shrink:0;}
/* ---------- donut / hot zones / KB ---------- */
.donut{width:132px;height:132px;border-radius:50%;display:grid;place-items:center;background:conic-gradient(#31c39a var(--healthy),#ffc83d 0 var(--warning),#f06469 0 var(--critical),#e3e7ef 0);margin:6px auto;position:relative;}
.donut:before{content:"";position:absolute;width:88px;height:88px;border-radius:50%;background:#fff;}
.donut span{position:relative;font-size:1.3rem;font-weight:800;color:var(--ink);}
.dl-row{display:flex;align-items:center;justify-content:space-between;padding:7px 0;font-size:.9rem;color:#27334f;}
.dl-row b{font-weight:700;}
.dl-row i{display:inline-block;width:11px;height:11px;border-radius:50%;margin-right:10px;}
.pl{display:flex;justify-content:center;gap:22px;font-size:.78rem;color:var(--muted);margin:0 0 4px;}
.pl i{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:6px;}
.heat-scale{display:flex;align-items:center;gap:10px;font-size:.78rem;color:var(--muted);margin-top:10px;}
.heat-scale i{flex:1;height:8px;border-radius:99px;background:linear-gradient(90deg,#fff3a8,#ffb23d,#ef4444);}
.kb-row{display:flex;align-items:flex-start;gap:10px;padding:8px 2px;border-bottom:1px solid #eff1f6;font-size:.86rem;color:#27334f;}
.kb-row:last-child{border-bottom:0;}
.kb-dot{width:9px;height:9px;border-radius:50%;margin-top:6px;flex-shrink:0;}
.kb-name{flex:1;min-width:0;font-weight:600;}
.kb-act{font-weight:400;color:var(--muted);font-size:.74rem;margin-top:2px;display:-webkit-box;-webkit-line-clamp:1;-webkit-box-orient:vertical;overflow:hidden;}
.kb-val{font-weight:700;}
.help-card{text-align:center;padding:16px 12px 12px;border-radius:16px 16px 4px 4px;background:linear-gradient(160deg,#f3eeff,#e9e2ff);color:#27334f;}
.help-card .hc-title{font-weight:800;font-size:1rem;margin-top:4px;}
.help-card .hc-text{font-size:.78rem;color:#56627f;margin-top:6px;line-height:1.35;}
.qa-row{display:flex;flex-wrap:wrap;gap:10px;}
.qa-chip{padding:8px 14px;border-radius:999px;background:#f3f1ff;border:1px solid #e3def8;font-size:.82rem;color:#46526f;}
.qa-chip b{color:var(--ink);margin-left:4px;}
/* ---------- text-style link buttons ---------- */
[class*="st-key-viewall"]{text-align:right;}
[class*="st-key-viewall"] button{background:transparent !important;border:0 !important;box-shadow:none !important;color:#5b4fc0 !important;font-weight:650;font-size:.8rem;padding:4px 0 !important;min-height:0 !important;}
[class*="st-key-viewall"] button:hover{text-decoration:underline;}
[class*="st-key-browse"] button{background:linear-gradient(135deg,#6a5bc4,#5a4aa8) !important;color:#fff !important;border:0 !important;border-radius:4px 4px 14px 14px !important;font-weight:650;box-shadow:0 8px 16px rgba(98,83,183,.25);}
"""
st.markdown("<style>" + CSS + nav_icon_css() + "</style>", unsafe_allow_html=True)

DARK_THEME_CSS = """
:root{color-scheme:dark;--ink:#e6eaf5;--muted:#a3aec5;--line:#30394d;}
.stApp,[data-testid="stAppViewContainer"]{background:#0d1220 !important;color:#e6eaf5 !important;}
.stApp h1,.stApp h2,.stApp h3,.stApp h4,.stApp p,.stApp label,.stApp [data-testid="stMarkdownContainer"]{color:#e6eaf5;}
.stApp [data-testid="stCaptionContainer"],.stApp [data-testid="stCaptionContainer"] p{color:#a3aec5 !important;}
[data-testid="stSidebar"]{background:linear-gradient(180deg,#121a2a,#17162b) !important;border-color:#30394d !important;}
[data-testid="stSidebar"] .brand-name,[data-testid="stSidebar"] .sh-title,[data-testid="stSidebar"] .sh-val{color:#e6eaf5 !important;}
[data-testid="stSidebar"] .brand-tag,[data-testid="stSidebar"] .sh-sub{color:#a3aec5 !important;}
[data-testid="stSidebar"] [data-testid="stRadio"] label{color:#d5dced;}
[data-testid="stVerticalBlockBorderWrapper"]{background:linear-gradient(150deg,#171f30,#171a2a) !important;border-color:#30394d !important;}
[data-testid="stMetric"]{background:linear-gradient(145deg,#1d2638,#211e35) !important;border-color:#30394d !important;}
[data-testid="stMetricLabel"],[data-testid="stMetricValue"]{color:#e6eaf5 !important;}
[data-testid="stExpander"] details,[data-testid="stPopover"]{background:#171f30 !important;border-color:#30394d !important;}
[data-testid="stTextInput"] input,[data-testid="stNumberInput"] input,[data-testid="stTextArea"] textarea,
[data-baseweb="select"] > div,[data-baseweb="input"]{background:#111827 !important;color:#e6eaf5 !important;border-color:#3a465e !important;}
[data-baseweb="popover"],[role="listbox"]{background:#171f30 !important;color:#e6eaf5 !important;}
[role="option"]{color:#e6eaf5 !important;}
[data-testid="stDataFrame"],[data-testid="stTable"]{filter:brightness(.86) saturate(.9);}
[data-testid="stAlert"]{background:#1b2435 !important;color:#e6eaf5 !important;}
[data-testid="stTabs"] button{color:#c6cfe0 !important;}
[data-testid="stDialog"] [role="dialog"]{background:#171f30 !important;color:#e6eaf5 !important;}
.topbar{background:radial-gradient(ellipse at 85% 10%,rgba(36,94,77,.45) 0,transparent 42%),radial-gradient(ellipse at 20% 0%,rgba(70,58,125,.5) 0,transparent 46%),linear-gradient(105deg,#1b2434,#211e35 52%,#302128) !important;border-color:#394258 !important;}
.tb-title,.pt-title,.dl-row,.kb-row,.incident-title{color:#e6eaf5 !important;}
.tb-sub,.legend,.small-muted,.incident-head,.incident-meta{color:#a3aec5 !important;}
.side-health{background:linear-gradient(160deg,#1b2535,#211e35) !important;border-color:#30394d !important;}
.incident-card{background:linear-gradient(100deg,#1a2031,#171f30 75%) !important;border-color:#30394d !important;}
.incident-card.sev-critical{background:linear-gradient(100deg,#382222,#171f30 75%) !important;}
.incident-card.sev-warning{background:linear-gradient(100deg,#382f1b,#171f30 75%) !important;}
.incident-card.sev-resolved{background:linear-gradient(100deg,#1b332a,#171f30 75%) !important;}
.qa-chip{background:#25243d;border-color:#403b64;color:#c6cfe0;}
.help-card{background:linear-gradient(160deg,#292443,#24213b);color:#e6eaf5;}
.help-card .hc-text{color:#b4bdd0;}
"""


def apply_theme() -> None:
    if st.session_state.get("dark_theme", False):
        st.markdown(f"<style>{DARK_THEME_CSS}</style>", unsafe_allow_html=True)


def api_get(path: str, **params: Any) -> Any:
    response = requests.get(f"{API_URL}{path}", params=params or None, timeout=60)
    response.raise_for_status()
    return response.json()


def api_post(path: str, **kwargs: Any) -> Any:
    response = requests.post(f"{API_URL}{path}", timeout=20, **kwargs)
    response.raise_for_status()
    return response.json()


def format_age(value: str | None) -> str:
    if not value:
        return "Not run yet"
    try:
        timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        seconds = max(0, int((datetime.now(timezone.utc) - timestamp.astimezone(timezone.utc)).total_seconds()))
        if seconds < 60:
            return f"{seconds}s ago"
        if seconds < 3600:
            return f"{seconds // 60} min ago"
        if seconds < 86400:
            return f"{seconds // 3600} hr ago"
        return f"{seconds // 86400}d ago"
    except ValueError:
        return value


def status_class(value: str) -> str:
    return str(value).strip().lower().replace(" ", "-")


def go_to(page: str) -> None:
    """Button callback: switch the sidebar navigation to another page."""
    st.session_state["nav_page"] = page


# Weighted score shown in the sidebar: healthy = 100 %, warning = 50 %, critical = 0 %.
HEALTH_WEIGHTS = {"healthy": 1.0, "warning": 0.5, "critical": 0.0}


def health_score(devices: list[dict[str, Any]]) -> float | None:
    scores = [HEALTH_WEIGHTS[d["status"]] for d in devices if d.get("status") in HEALTH_WEIGHTS]
    return 100 * sum(scores) / len(scores) if scores else None


def card_header(icon_html: str, tint: str, title: str, right: str = "") -> str:
    return H(
        f'<div class="panel-title"><div class="pt-title"><span class="pt-icon" style="background:{tint}22;color:{tint}">'
        f'{icon_html}</span>{html.escape(title)}</div>{right}</div>'
    )


def status_legend(include_unknown: bool = True) -> str:
    items = [("#20b981", "Healthy"), ("#f3b61f", "Warning"), ("#ef5c62", "Critical")]
    if include_unknown:
        items.append(("#98a2b8", "Unknown"))
    return '<div class="legend">' + "".join(f'<span><i style="background:{c}"></i>{n}</span>' for c, n in items) + "</div>"


def show_topbar(page: str, health: dict[str, Any]) -> None:
    emoji, title, subtitle = PAGE_HEADERS[page]
    now = datetime.now().astimezone().strftime("%H:%M:%S")
    backend = str(health.get("status", "unavailable"))
    ok = backend.lower() in {"healthy", "ok", "ready", "up"}
    label = "Connected" if ok else backend.title()
    md(
        f"""
        <div class="topbar">
          <div class="tb-left"><div class="tb-emoji">{emoji}</div>
            <div><div class="tb-title">{html.escape(title)}</div><div class="tb-sub">{html.escape(subtitle)}</div></div></div>
          <div class="tb-right">
            <span class="tb-live"><i></i>Live • {now}</span>
            <span class="tb-conn{'' if ok else ' warn'}">{icon('wifi', 18)}{html.escape(label)}</span>
            <span class="tb-bell">{icon('bell', 20)}</span>
            <span class="tb-avatar">{html.escape(USER_INITIALS)}</span>
          </div>
        </div>
        """
    )


def device_neighbors(device: dict[str, Any]) -> list[str]:
    raw = device.get("neighbors_json") or device.get("neighbors") or []
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            raw = [item.strip() for item in raw.replace(",", ";").split(";") if item.strip()]
    return [str(item) for item in raw] if isinstance(raw, list) else []


def render_campus_scene(
    points: list[dict[str, Any]],
    *,
    height: int = 440,
) -> None:
    """Render a campus-style 3D background with device markers overlaid by status color."""
    buildings = [
        {"name": "Main Gate", "x": 110, "y": 430, "w": 170, "h": 36, "fill": "#efdfb8"},
        {"name": "Academic Admin", "x": 260, "y": 280, "w": 170, "h": 72, "fill": "#f4e8d3"},
        {"name": "Auditorium", "x": 175, "y": 155, "w": 150, "h": 70, "fill": "#e9e0d0"},
        {"name": "Library", "x": 70, "y": 195, "w": 150, "h": 82, "fill": "#dfe8f6"},
        {"name": "Academic Complex", "x": 470, "y": 195, "w": 220, "h": 100, "fill": "#d9e7f8"},
        {"name": "Sports Complex", "x": 500, "y": 330, "w": 200, "h": 90, "fill": "#cfe4d8"},
        {"name": "Core NOC", "x": 440, "y": 430, "w": 120, "h": 62, "fill": "#b8d8e6"},
        {"name": "Hostel Block 1", "x": 40, "y": 500, "w": 120, "h": 54, "fill": "#d8d7e5"},
        {"name": "Hostel Block 2", "x": 185, "y": 500, "w": 120, "h": 54, "fill": "#d8d7e5"},
        {"name": "Hostel Block 3", "x": 330, "y": 500, "w": 120, "h": 54, "fill": "#d8d7e5"},
        {"name": "Lecture Hall", "x": 20, "y": 80, "w": 150, "h": 62, "fill": "#e9d4bb"},
    ]
    building_svg = "".join(
        f'''
        <g>
          <polygon points="{b['x']},{b['y']} {b['x']+b['w']},{b['y']} {b['x']+b['w']+18},{b['y']+10} {b['x']+18},{b['y']+10}" fill="rgba(20, 32, 58, 0.18)"/>
          <polygon points="{b['x']+b['w']},{b['y']} {b['x']+b['w']+18},{b['y']+10} {b['x']+b['w']+18},{b['y']+b['h']+10} {b['x']+b['w']},{b['y']+b['h']}" fill="rgba(18, 27, 46, 0.18)"/>
          <rect x="{b['x']}" y="{b['y']}" width="{b['w']}" height="{b['h']}" rx="8" fill="{b['fill']}" stroke="rgba(21,30,52,0.38)" stroke-width="1.2"/>
          <text x="{b['x'] + b['w'] / 2}" y="{b['y'] + b['h'] / 2 + 2}" text-anchor="middle" font-size="11" font-family="Segoe UI, sans-serif" fill="#1b2740" opacity="0.8">{b['name']}</text>
        </g>
        '''
        for b in buildings
    )

    status_colors = {
        "healthy": "#22c55e",
        "warning": "#fbbf24",
        "critical": "#ef4444",
        "unknown": "#94a3b8",
    }
    marker_svg = "".join(
        f'''
        <g transform="translate({p['x']} {p['y']})">
          <path d="M0,-12 L9,8 L0,0 L-9,8 Z" fill="{status_colors.get(p['status'], '#94a3b8')}" stroke="rgba(255,255,255,0.8)" stroke-width="1.4"/>
          <circle cx="0" cy="0" r="2.8" fill="white" opacity="0.9"/>
          <title>{p['name']} · {p['status']}</title>
        </g>
        '''
        for p in points
    )

    html = f"""
    <div style="width:100%; height:{height}px; border-radius:18px; overflow:hidden; border:1px solid rgba(148,163,184,0.35); background:linear-gradient(180deg,#edf5ff 0%,#dfeaf8 48%,#ccdef4 100%); box-shadow: inset 0 1px 0 rgba(255,255,255,0.8);">
      <svg viewBox="0 0 860 620" width="100%" height="100%" xmlns="http://www.w3.org/2000/svg">
        <defs>
          <linearGradient id="campusGround" x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stop-color="#eaf5ec"/>
            <stop offset="100%" stop-color="#cfe8d1"/>
          </linearGradient>
        </defs>
        <rect width="860" height="620" fill="url(#campusGround)"/>
        <path d="M0,480 C170,470 240,440 350,440 C520,440 620,520 860,500 L860,620 L0,620 Z" fill="rgba(90,124,86,0.23)"/>
        <path d="M60,120 C190,80 300,70 420,110 C560,150 700,160 820,80 L820,0 L0,0 L0,120 Z" fill="rgba(255,255,255,0.35)"/>
        <g opacity="0.96">{building_svg}</g>
        <g>{marker_svg}</g>
      </svg>
    </div>
    """
    components.html(html, height=height, scrolling=False)


def render_3d_campus_if_available(
    devices: list[dict[str, Any]],
    *,
    height: int = 360,
    highlight_ids: set[str] | None = None,
    map_key: str = "default",
    show_device_list: bool = True,
) -> bool:
    inventory_id = st.session_state.setdefault(
        f"campus_3d_inventory_id_{map_key}", secrets.token_urlsafe(16)
    )
    highlighted = highlight_ids or set()
    payload = [
        {
            **device,
            "highlighted": str(device.get("device_id") or "") in highlighted,
        }
        for device in devices
    ]
    try:
        response = requests.put(
            f"{CAMPUS_MAP_URL}/api/inventory/{quote(inventory_id, safe='')}",
            json=payload,
            timeout=90,
        )
        response.raise_for_status()
    except requests.RequestException as error:
        st.warning(
            f"Could not connect to the 3D campus map at {CAMPUS_MAP_URL}: {error}. "
            "Confirm that the campus-map Render service is deployed and CAMPUS_MAP_URL is correct."
        )
        return False
    components.iframe(
        f"{CAMPUS_MAP_URL}/?inventory_id={quote(inventory_id, safe='')}"
        f"&show_device_list={'1' if show_device_list else '0'}",
        height=height,
        scrolling=False,
    )
    return True


def render_topology(
    devices: list[dict[str, Any]],
    *,
    height: int = 360,
    highlight_ids: set[str] | None = None,
    map_key: str = "default",
    show_device_list: bool = True,
) -> None:
    """Render the campus map; prefer the supplied 3D campus app when available."""
    if render_3d_campus_if_available(
        devices,
        height=height,
        highlight_ids=highlight_ids,
        map_key=map_key,
        show_device_list=show_device_list,
    ):
        return

    if not devices:
        st.info("Upload a connected-device inventory to render the campus map.")
        return

    points: list[dict[str, Any]] = []
    highlights = highlight_ids or set()
    for device in devices:
        latitude = device.get("latitude")
        longitude = device.get("longitude")
        if latitude is None or longitude is None:
            continue
        status = str(device.get("status", "unknown")).lower()
        points.append({
            "device_id": str(device.get("device_id") or "unknown"),
            "name": device.get("name") or device.get("device_id") or "Unknown device",
            "device_type": str(device.get("device_type") or "network device"),
            "status": status,
            "latitude": float(latitude),
            "longitude": float(longitude),
            "risk_probability": float(device.get("risk_probability", 0.0) or 0.0),
            "highlight": str(device.get("device_id") or "") in highlights,
            "x": 0.0,
            "y": 0.0,
        })

    if not points:
        st.info("No latitude/longitude data is present in the current device inventory.")
        return

    lat_min, lat_max = min(item["latitude"] for item in points), max(item["latitude"] for item in points)
    lon_min, lon_max = min(item["longitude"] for item in points), max(item["longitude"] for item in points)
    for item in points:
        item["x"] = 90 + ((item["longitude"] - lon_min) / (lon_max - lon_min + 1e-6)) * 680
        item["y"] = 540 - ((item["latitude"] - lat_min) / (lat_max - lat_min + 1e-6)) * 430
    render_campus_scene(points, height=height)

    md(status_legend())
    if show_device_list:
        df = pd.DataFrame(points)
        st.dataframe(
            df[["device_id", "name", "device_type", "status", "latitude", "longitude", "risk_probability"]].sort_values("device_id").reset_index(drop=True),
            hide_index=True,
            use_container_width=True,
        )


def incident_rows(
    incidents: list[dict[str, Any]],
    limit: int = 5,
    devices: list[dict[str, Any]] | None = None,
) -> None:
    if not incidents:
        st.info("No processed incidents yet. Send telemetry to begin.")
        return
    tones = {"critical": ("critical", "#ef5c62"), "warning": ("warning", "#f3b61f")}
    for incident in incidents[:limit]:
        severity = str(incident.get("severity", "unknown")).lower()
        if severity in tones:
            tone, color = tones[severity]
        elif severity in {"resolved", "info", "ok", "healthy"}:
            tone, color = "resolved", "#20b981"
        else:
            tone, color = "unknown", "#94a0b8"
        causes = incident.get("probable_causes", [])
        top = max(causes, key=lambda cause: cause.get("probability", 0), default=None)
        top_line = (
            f"{top.get('cause', 'Unknown cause')} · {top.get('probability', 0):.0%}" if top else "No ranked cause yet"
        )
        incident_id = str(incident.get("incident_id", ""))
        md(
            f"""
            <div class="incident-card sev-{tone}">
              <div class="incident-main">
                <div class="incident-head"><span class="badge badge-{tone}">{html.escape(severity.title())}</span>
                  <span>#{html.escape(incident_id[:12])} • {html.escape(format_age(incident.get('timestamp')))}</span></div>
                <div class="incident-title">{html.escape(str(incident.get('summary', '')))}</div>
                <div class="incident-meta">{html.escape(top_line)}</div>
              </div>
              <div class="incident-spark">{spark(incident_id or severity, color, width=96, height=40)}</div>
            </div>
            """
        )
        with st.expander(f"Investigate {incident.get('incident_id', '')[:8]}"):
            show_incident(incident, devices or [])


def show_incident(incident: dict[str, Any], devices: list[dict[str, Any]]) -> None:
    st.write(incident.get("summary", ""))
    scoring_method = incident.get("scoring_method", "static_fallback").replace("_", " ").title()
    st.caption(
        f"Status: {incident.get('conclusion', 'unknown').replace('_', ' ').title()} · "
        f"{scoring_method} · {incident.get('confidence_threshold', 0.9):.0%} confidence threshold"
    )
    if incident.get("scoring_weights"):
        st.caption(
            "Weights: "
            + " · ".join(
                f"{name.replace('_', ' ')} {value:.0%}"
                for name, value in incident["scoring_weights"].items()
            )
        )
    causes = incident.get("probable_causes", [])
    if causes:
        st.subheader("Ranked recommendations")
        for index, cause in enumerate(causes, 1):
            st.markdown(
                f"**{index}. {cause['cause']} — {cause['probability']:.0%}**  \n"
                f"{cause['recommended_action']}"
            )
            st.caption("Evidence: " + "; ".join(cause.get("evidence", [])))
            if cause.get("score_breakdown"):
                st.caption(
                    "AI factor ratings: "
                    + " · ".join(
                        f"{name.replace('_', ' ')} {value:.0%}"
                        for name, value in cause["score_breakdown"].items()
                    )
                )
            if cause.get("sources"):
                st.caption(
                    "External references: "
                    + " · ".join(
                        f"[{source['title']}]({source['url']})"
                        for source in cause["sources"]
                    )
                )
    research = incident.get("web_research", {})
    if research.get("status") == "searched" and research.get("sources"):
        with st.expander("Tavily web research (unverified references)"):
            for source in research["sources"]:
                st.markdown(f"- [{source['title']}]({source['url']}) — {source['snippet']}")
    elif research.get("message"):
        st.caption(f"Web research: {research['message']}")
    questions = incident.get("human_questions", [])
    if questions:
        st.warning("Operator follow-up is pending.")
        for question in questions:
            st.markdown(f"- {question}")
        incident_id = str(incident["incident_id"])
        seen_dialogs = st.session_state.setdefault("hitl_dialog_seen", set())
        requested_dialog = st.session_state.get("hitl_dialog_requested") == incident_id
        if incident_id in seen_dialogs and not requested_dialog:
            if st.button("Answer follow-up questions", key=f"open-hitl-{incident_id}"):
                st.session_state["hitl_dialog_requested"] = incident_id
    nearby = incident.get("nearby_connections", [])
    if nearby:
        st.subheader("Topology-nearby watch list")
        st.dataframe(
            pd.DataFrame([
                {
                    "Device": item["device_id"],
                    "Type": item["device_type"],
                    "Severity": item["severity"],
                    "Risk estimate": item["probability"],
                    "Hops": item["connection_hops"],
                    "Evidence": "; ".join(item["evidence"]),
                }
                for item in nearby
            ]),
            hide_index=True,
            use_container_width=True,
        )
    simulation = incident.get("event_simulation")
    if simulation:
        st.subheader("Event simulation (what-if estimate)")
        summary = simulation["summary"]
        metrics = st.columns(4)
        metrics[0].metric("Critical devices", summary["critical"])
        metrics[1].metric("Warning devices", summary["warning"])
        metrics[2].metric("Peak network load", f"{summary['peak_network_load_pct']:.1f}%")
        metrics[3].metric("First overload", f"T+{summary['first_critical_minute']} min" if summary["first_critical_minute"] is not None else "None")
        predicted = [
            item for item in simulation["devices"]
            if item["severity"] in {"critical", "warning"}
        ]
        if predicted:
            st.dataframe(
                pd.DataFrame([
                    {
                        "Device": item["device_id"],
                        "Area": item["area"],
                        "Role": item["role"],
                        "Severity": item["severity"],
                        "Peak utilization": item["peak_utilization"],
                        "Risk estimate": item["risk_probability"],
                        "Topology hops": item["connection_hops"],
                        "Recommendation": item["recommended_action"],
                    }
                    for item in predicted
                ]),
                hide_index=True,
                use_container_width=True,
            )
        st.caption(simulation["model_note"])

    st.json({
        "telemetry": incident.get("telemetry", {}),
        "units": incident.get("units", {}),
        "infrastructure_findings": incident.get("infrastructure_findings", []),
        "nearby_connections": incident.get("nearby_connections", []),
        "event_context": incident.get("event_context"),
        "historical_context": incident.get("historical_context", []),
        "limitations": incident.get("limitations", ""),
    })
    if simulation:
        with st.expander("Full event simulation data"):
            st.json(simulation)
    st.link_button("Download incident report", f"{API_URL}/incidents/{incident['incident_id']}/report")


@st.dialog("Additional information needed", width="large", on_dismiss="rerun")
def render_human_review_dialog(
    incident: dict[str, Any],
    devices: list[dict[str, Any]],
) -> None:
    incident_id = str(incident["incident_id"])
    st.write("The diagnostic agents need a few details to verify likely causes.")
    for question in incident.get("human_questions", []):
        st.markdown(f"- {question}")

    with st.form(f"information-{incident_id}"):
        event_context: dict[str, Any] | None = None
        if incident.get("event_context") is None:
            event_answer = st.radio(
                "Is a crowd-gathering event happening?",
                ["No", "Yes"],
                horizontal=True,
                key=f"event-happening-{incident_id}",
            )
            event_context = {"event_happening": event_answer == "Yes"}
            if event_answer == "Yes":
                st.caption(
                    "Enter the event coordinates and select the network device serving that area. "
                    "Coordinates are recorded for context; impact is propagated through topology links."
                )
                label_to_id = {
                    f"{device['device_id']} · {device.get('name') or device['device_id']}": device["device_id"]
                    for device in devices
                }
                if not label_to_id:
                    st.error("Load or upload the device topology before simulating an event.")
                    label_to_id = {incident["device_id"]: incident["device_id"]}
                event_type = st.selectbox(
                    "Event type",
                    ["festival", "sports", "livestream", "exam", "outage"],
                    key=f"event-type-{incident_id}",
                )
                anchor_label = st.selectbox(
                    "Serving / anchor device",
                    list(label_to_id),
                    key=f"event-anchor-{incident_id}",
                )
                latitude_col, longitude_col = st.columns(2)
                latitude = latitude_col.number_input(
                    "Event latitude",
                    min_value=-90.0,
                    max_value=90.0,
                    value=0.0,
                    format="%.6f",
                    key=f"event-lat-{incident_id}",
                )
                longitude = longitude_col.number_input(
                    "Event longitude",
                    min_value=-180.0,
                    max_value=180.0,
                    value=0.0,
                    format="%.6f",
                    key=f"event-lon-{incident_id}",
                )
                attendance = st.number_input(
                    "Expected attendance",
                    min_value=1,
                    max_value=500_000,
                    value=5000,
                    step=100,
                    key=f"event-attendance-{incident_id}",
                )
                radius_hops = st.slider(
                    "Topology impact radius (hops)",
                    1,
                    3,
                    2,
                    key=f"event-hops-{incident_id}",
                )
                event_context.update({
                    "event_type": event_type,
                    "anchor_device_id": label_to_id[anchor_label],
                    "latitude": latitude,
                    "longitude": longitude,
                    "attendance": attendance,
                    "radius_hops": radius_hops,
                })

        answer_options = ["Not sure", "No", "Yes"]
        firewall_alert = st.selectbox(
            "Firewall or UTM alert?", answer_options, key=f"utm-{incident_id}"
        )
        firewall_change = st.selectbox(
            "Recent firewall policy change?", answer_options, key=f"fw-{incident_id}"
        )
        interface_errors = st.selectbox(
            "Are interface/CRC errors increasing?", answer_options, key=f"crc-{incident_id}"
        )
        route_change = st.selectbox(
            "Recent routing/QoS change?", answer_options, key=f"route-{incident_id}"
        )
        include_drops = st.checkbox(
            "Include an exact firewall drop count", key=f"include-drops-{incident_id}"
        )
        drops = st.number_input(
            "Firewall drops (events)", min_value=0, step=1, key=f"drops-{incident_id}"
        )
        submit, later = st.columns(2)
        submitted = submit.form_submit_button(
            "Submit client information", type="primary", use_container_width=True
        )
        later.form_submit_button("Answer later", use_container_width=True)

    if submitted:
        map_answer = {"Yes": True, "No": False, "Not sure": "unknown"}
        answers: dict[str, Any] = {
            "utm_alerts": map_answer[firewall_alert],
            "recent_firewall_change": map_answer[firewall_change],
            "interface_errors_present": map_answer[interface_errors],
            "recent_route_change": map_answer[route_change],
        }
        if include_drops:
            answers["firewall_drops"] = drops
        try:
            api_post(
                f"/incidents/{incident_id}/information",
                json={"answers": answers, "event_context": event_context},
            )
            st.session_state["hitl_dialog_seen"].discard(incident_id)
            st.success("Operator information submitted; report and event estimate were updated.")
            st.rerun()
        except requests.RequestException as error:
            st.error(f"Could not submit client information: {error}")
    elif later:
        st.rerun()


AGENT_STYLES = (
    ("perform", "gauge", "#3b82f6"),
    ("infra", "cpu", "#22a06b"),
    ("connect", "wifi", "#3b82f6"),
    ("utm", "shield", "#3b82f6"),
    ("secur", "shield", "#3b82f6"),
    ("recommend", "bulb", "#f0a914"),
    ("correl", "bulb", "#f0a914"),
    ("monitor", "activity", "#14b8a6"),
)


def agent_style(name: str) -> tuple[str, str]:
    lowered = name.lower()
    for key, glyph, color in AGENT_STYLES:
        if key in lowered:
            return glyph, color
    return "cpu", "#6253b7"


def show_agent_panel(health: dict[str, Any], compact: bool = False) -> None:
    for name, details in health.get("agents", {}).items():
        display_name = "Recommendation & Correlation Agent" if name == "Correlation Agent" else name
        latency = details.get("latency_ms")
        if isinstance(latency, (int, float)):
            response = f"{latency:g} ms"
        elif name == "Common Monitoring Agent":
            response = "Service monitor"
        else:
            response = "Waiting for first run"
        status = details.get("status", "unavailable")
        label = f"{status.title()} · {response}"
        if not compact:
            label += f" · {format_age(details.get('last_execution') or details.get('last_check'))}"
        glyph, color = agent_style(name)
        line_color = "#ef5c62" if status_class(status) in {"degraded", "stale", "unavailable", "critical"} else color
        md(
            f"""
            <div class="agent-row">
              <span class="agent-icon" style="background:{color}1f;color:{color}">{icon(glyph, 22, color, 2)}</span>
              <div class="agent-info"><div class="agent-name">{html.escape(display_name)}</div>
                <div class="agent-meta"><span class="status-dot status-{status_class(status)}"></span>{html.escape(label)}</div></div>
              <div class="agent-spark">{spark(name, line_color, width=76, height=30, fill=False)}</div>
            </div>
            """
        )


def city_card() -> str:
    return H(
        """
        <div class="side-city"><svg viewBox="0 0 200 118" width="100%" xmlns="http://www.w3.org/2000/svg">
        <defs><linearGradient id="citysky" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#e3ecfb"/><stop offset="1" stop-color="#f4eefb"/></linearGradient></defs>
        <rect width="200" height="118" fill="url(#citysky)"/>
        <rect x="12" y="52" width="22" height="50" rx="2" fill="#c9d8f3"/>
        <rect x="38" y="36" width="20" height="66" rx="2" fill="#a9c1ee"/>
        <rect x="62" y="58" width="24" height="44" rx="2" fill="#bfcff0"/>
        <rect x="116" y="48" width="22" height="54" rx="2" fill="#b7c9ee"/>
        <rect x="142" y="30" width="22" height="72" rx="2" fill="#9db8ea"/>
        <rect x="168" y="56" width="20" height="46" rx="2" fill="#c5d4f1"/>
        <path d="M100 12 L106 40 L112 102 H88 L94 40 Z" fill="#445577"/>
        <path d="M96 40h8M94 60h12M91 80h18" stroke="#e8eefc" stroke-width="1.6"/>
        <circle cx="100" cy="11" r="3" fill="#ef5c62"/>
        <rect y="100" width="200" height="18" fill="#bfe3c9"/>
        <circle cx="26" cy="102" r="9" fill="#78c493"/><circle cx="74" cy="104" r="8" fill="#5fb383"/>
        <circle cx="130" cy="103" r="9" fill="#78c493"/><circle cx="176" cy="104" r="8" fill="#5fb383"/>
        </svg></div>
        """
    )


def render_sidebar() -> tuple[str, str | None]:
    overview: dict[str, Any] = {}
    try:
        overview = api_get("/overview")
    except requests.RequestException:
        pass
    with st.sidebar:
        md(f'<div class="brand">{logo_svg(64)}<div class="brand-name">NetCoop AI</div><div class="brand-tag">Smart Network<br>Intelligence</div></div>')
        st.toggle("Dark theme", key="dark_theme", help="Switch the dashboard to a dark color scheme.")
        page = st.radio("Navigation", PAGES, key="nav_page", label_visibility="collapsed")

        inventory = None
        with st.expander("Device inventory"):
            st.caption("Demo site: IIT Bhubaneswar")
            if st.button("Load 15 synthetic IIT Bhubaneswar devices", help="Replaces the current device inventory with illustrative campus-area locations."):
                try:
                    result = api_post("/devices/demo/iit-bhubaneswar")
                    st.success(f"Loaded {result['uploaded']} synthetic devices.")
                    st.rerun()
                except requests.RequestException as error:
                    st.error(f"Could not load demo devices: {error}")
            inventory = st.file_uploader("Upload connected-device CSV or JSON", type=["csv", "json"], key="inventory-upload")
            if inventory and st.button("Ingest device map", type="primary"):
                try:
                    result = api_post("/devices/upload", files={"file": (inventory.name, inventory.getvalue())})
                    st.success(f"Ingested {result['uploaded']} devices.")
                    st.rerun()
                except requests.RequestException as error:
                    st.error(f"Inventory upload failed: {error}")
            st.caption("CSV: device_id, name, device_type, vendor, connected_to. Separate multiple device IDs with semicolons.")

        with st.expander("Client telemetry"):
            telemetry_file = st.file_uploader("Upload telemetry JSON", type=["json"], key="telemetry-upload")
            if telemetry_file and st.button("Queue uploaded telemetry"):
                try:
                    if telemetry_file.size > 1_000_000:
                        raise ValueError("Telemetry JSON must be 1 MB or smaller.")
                    payload = json.loads(telemetry_file.getvalue())
                    if not isinstance(payload, dict):
                        raise ValueError("Upload one JSON object with device_id, metrics, and units.")
                    queued = api_post("/telemetry", json=payload)
                    st.success(f"Queued event {queued['event_id'][:8]}.")
                except (ValueError, requests.RequestException) as error:
                    st.error(f"Telemetry upload failed: {error}")

        with st.expander("Synthetic telemetry"):
            device_ids = [device["device_id"] for device in overview.get("devices", [])]
            selected_device = st.selectbox("Device", device_ids or ["SW_CAMPUS_1"])
            bandwidth_unit = st.selectbox("Bandwidth unit", ["Mbps", "Gbps", "Kbps", "bps"])
            scenario = st.selectbox("Scenario", ["normal", "latency_spike", "hardware_failure"])
            if st.button("Send sample telemetry"):
                bandwidth_mbps = {"normal": 2500, "latency_spike": 8500, "hardware_failure": 100000}[scenario]
                divisor = {"Mbps": 1, "Gbps": 1000, "Kbps": 0.001, "bps": 0.000001}[bandwidth_unit]
                metrics: dict[str, Any] = {
                    "cpu_utilization_pct": round(random.uniform(10, 35), 2),
                    "link_utilization_pct": round(random.uniform(20, 50), 2),
                    "packet_loss_pct": 0.0,
                    "latency_ms": round(random.uniform(5, 20), 2),
                    "jitter_ms": round(random.uniform(1, 5), 2),
                    "queue_drops": 0,
                }
                if scenario == "latency_spike":
                    metrics.update({
                        "cpu_utilization_pct": round(random.uniform(40, 70), 2),
                        "link_utilization_pct": round(random.uniform(60, 85), 2),
                        "packet_loss_pct": round(random.uniform(0.1, 1.5), 2),
                        "latency_ms": round(random.uniform(150, 400), 2),
                        "jitter_ms": round(random.uniform(30, 80), 2),
                        "queue_drops": random.randint(0, 50),
                    })
                elif scenario == "hardware_failure":
                    metrics.update({
                        "cpu_utilization_pct": 99.9,
                        "link_utilization_pct": 100.0,
                        "packet_loss_pct": round(random.uniform(15, 30), 2),
                        "latency_ms": round(random.uniform(500, 1000), 2),
                        "queue_drops": random.randint(5000, 15000),
                        "interface_errors": random.randint(100, 500),
                    })
                metrics["bandwidth"] = bandwidth_mbps / divisor
                try:
                    response = api_post("/telemetry", json={
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "device_id": selected_device,
                        "metrics": metrics,
                        "units": {"bandwidth": bandwidth_unit},
                    })
                    st.success(f"Queued event {response['event_id'][:8]}.")
                except requests.RequestException as error:
                    st.error(f"Telemetry submission failed: {error}")

        md(city_card())
        score = health_score(overview.get("devices", []))
        value = f"{score:.1f}%" if score is not None else "—"
        md(
            f"""
            <div class="side-health" title="Weighted average of device status: healthy 100%, warning 50%, critical 0%">
              <div class="sh-title">Network Health</div><div class="sh-sub">Overall</div>
              <div class="sh-row"><span class="sh-check">{icon('check', 18, '#fff', 3)}</span><span class="sh-val">{value}</span></div>
              <div class="sh-spark">{spark('network-health', '#20b981', width=190, height=48, trend=0.6)}</div>
            </div>
            """
        )
    return page, inventory.name if inventory else None


KPI_THEMES = {
    "blue": dict(bg="linear-gradient(135deg,#f3f8ff 0%,#e1eeff 100%)", border="#d3e4fb", accent="#3b82f6", tint="#dbe9fd", note="#2f6fdc", solid=False),
    "green": dict(bg="linear-gradient(135deg,#f2fbf4 0%,#e0f5e7 100%)", border="#cdeed8", accent="#22b36b", tint="#d4f1de", note="#1b8a52", solid=True),
    "yellow": dict(bg="linear-gradient(135deg,#fffbea 0%,#fff0c4 100%)", border="#f7e3a2", accent="#f5b50f", tint="#fff0c4", note="#b27a00", solid=True),
    "red": dict(bg="linear-gradient(135deg,#fff3f2 0%,#ffe0de 100%)", border="#f9cdca", accent="#ef4f55", tint="#ffdcdc", note="#d23c42", solid=False),
    "purple": dict(bg="linear-gradient(135deg,#f6f2ff 0%,#e9e1ff 100%)", border="#dcd2fa", accent="#7c5ce0", tint="#e4dbff", note="#6a4bd0", solid=False),
}


def kpi_card(theme: str, glyph: str, label: str, value: Any, note: str) -> str:
    t = KPI_THEMES[theme]
    if t["solid"]:
        badge = (
            f'<span class="kpi-icon" style="background:{t["accent"]};box-shadow:0 6px 14px {t["accent"]}55">'
            f'{icon(glyph, 28, "#fff", 3)}</span>'
        )
    else:
        badge = f'<span class="kpi-icon" style="background:{t["tint"]}">{icon(glyph, 26, t["accent"], 2.2)}</span>'
    return (
        f'<div class="kpi" style="background:{t["bg"]};border-color:{t["border"]}">{badge}'
        f'<div class="kpi-body"><div class="kpi-label">{label}</div><div class="kpi-value">{value}</div>'
        f'<div class="kpi-note" style="color:{t["note"]}">{note}</div></div>'
        f'<div class="kpi-spark">{spark("kpi-" + label, t["accent"], width=140, height=56)}</div></div>'
    )


RANGE_HOURS = {"Last 1 Hour": 1, "Last 6 Hours": 6, "Last 24 Hours": 24, "All recent": None}


def performance_chart(frame: pd.DataFrame) -> alt.Chart:
    long = frame.melt("Time", var_name="Series", value_name="Value").dropna(subset=["Value"])
    base = alt.Chart(long).encode(
        x=alt.X("Time:T", axis=alt.Axis(title=None, format="%H:%M", grid=False, domain=False, ticks=False, labelColor="#64708b")),
        y=alt.Y("Value:Q", scale=alt.Scale(zero=True), axis=alt.Axis(title=None, tickCount=5, domain=False, ticks=False, gridColor="#e9edf5", labelColor="#64708b")),
    )
    latency = base.transform_filter(alt.datum.Series == "Latency (ms)").mark_area(
        line={"color": "#4f83ff", "strokeWidth": 2},
        color=alt.Gradient(
            gradient="linear",
            stops=[alt.GradientStop(color="rgba(79,131,255,0.04)", offset=0), alt.GradientStop(color="rgba(79,131,255,0.45)", offset=1)],
            x1=1, x2=1, y1=1, y2=0,
        ),
        interpolate="monotone",
    )
    loss = base.transform_filter(alt.datum.Series == "Packet loss (%)").mark_line(color="#8b5cf6", strokeWidth=2, interpolate="monotone")
    return (latency + loss).properties(height=220).configure_view(strokeWidth=0).configure(background="transparent")


def render_overview(data: dict[str, Any], health: dict[str, Any]) -> None:
    devices = data.get("devices", [])
    incidents = data.get("incidents", [])
    counts = {status: sum(item.get("status") == status for item in devices) for status in ("healthy", "warning", "critical", "unknown")}
    device_ids = {item["device_id"] for item in devices}
    active = sum(
        incident.get("severity") in {"warning", "critical"}
        and any(issue.get("device_id") in device_ids for issue in incident.get("issue_devices", []))
        for incident in incidents
    )
    total = len(devices)

    def share(count: int) -> str:
        return f"{100 * count / total:.1f}%" if total else "0.0%"

    md(
        '<div class="kpi-grid">'
        + kpi_card("blue", "server", "Total Devices", total, "Registered")
        + kpi_card("green", "check", "Healthy", counts["healthy"], share(counts["healthy"]))
        + kpi_card("yellow", "exclaim", "Warning", counts["warning"], share(counts["warning"]))
        + kpi_card("red", "alert", "Critical", counts["critical"], share(counts["critical"]))
        + kpi_card("purple", "bolt", "Active Incidents", active, "Needs attention" if active else "All clear")
        + "</div>"
    )

    left, right = st.columns([2, 1])
    with left, st.container(border=True):
        md(card_header(icon("pin", 16, "currentColor", 2.2), "#ef5c62", "Campus Device Map", status_legend()))
        render_topology(devices, height=520, map_key="overview-main", show_device_list=False)

    with right:
        with st.container(border=True):
            head, selector = st.columns([1.5, 1])
            with head:
                md(card_header(icon("chart", 16, "currentColor", 2.2), "#4f83ff", "Network Performance"))
            with selector:
                window = st.selectbox("Time range", list(RANGE_HOURS), index=3, key="perf-range", label_visibility="collapsed")
            performance = []
            for incident in reversed(incidents):
                telemetry = incident.get("telemetry", {})
                if "latency_ms" in telemetry or "packet_loss_pct" in telemetry:
                    performance.append({
                        "Time": incident.get("timestamp"),
                        "Latency (ms)": telemetry.get("latency_ms"),
                        "Packet loss (%)": telemetry.get("packet_loss_pct"),
                    })
            frame = pd.DataFrame()
            if performance:
                frame = pd.DataFrame(performance)
                frame["Time"] = pd.to_datetime(frame["Time"], errors="coerce", utc=True)
                for column in ("Latency (ms)", "Packet loss (%)"):
                    frame[column] = pd.to_numeric(frame[column], errors="coerce")
                frame = frame.dropna(subset=["Time"])
                hours = RANGE_HOURS[window]
                if hours:
                    frame = frame[frame["Time"] >= pd.Timestamp.now(tz="UTC") - pd.Timedelta(hours=hours)]
            if frame.empty:
                st.info("Performance charts appear after telemetry has been processed." if not performance else "No telemetry in this time range.")
            else:
                frame["Time"] = frame["Time"].dt.tz_convert(LOCAL_TZ).dt.tz_localize(None)
                md('<div class="pl"><span><i style="background:#4f83ff"></i>Latency (ms)</span><span><i style="background:#8b5cf6"></i>Packet Loss (%)</span></div>')
                st.altair_chart(performance_chart(frame), use_container_width=True, theme=None)

        with st.container(border=True):
            md(card_header(icon("activity", 16, "currentColor", 2.2), "#4f83ff", "Device Health Distribution"))
            donut_col, legend_col = st.columns([1, 1])
            n = max(1, total)
            healthy_share = 100 * counts["healthy"] / n
            warning_end = healthy_share + 100 * counts["warning"] / n
            critical_end = warning_end + 100 * counts["critical"] / n
            healthy_pct = round(100 * counts["healthy"] / total) if devices else 0
            with donut_col:
                md(f'<div class="donut" style="--healthy:{healthy_share}%;--warning:{warning_end}%;--critical:{critical_end}%"><span>{healthy_pct}%</span></div>')
            with legend_col:
                rows = [("#31c39a", "Healthy", counts["healthy"]), ("#ffc83d", "Warning", counts["warning"]), ("#f06469", "Critical", counts["critical"])]
                if counts["unknown"]:
                    rows.append(("#98a2b8", "Unknown", counts["unknown"]))
                md("".join(f'<div class="dl-row"><span><i style="background:{c}"></i>{n_}</span><b>{v}</b></div>' for c, n_, v in rows))

    with st.container(border=True):
        head, link = st.columns([2, 1])
        with head:
            md(card_header(icon("activity", 16, "currentColor", 2.2), "#22a06b", "Agent Control Center"))
        with link:
            st.button("View All →", key="viewall_agents", on_click=go_to, args=("Agent Control Center",))
        agent_cards = []
        for name, details in health.get("agents", {}).items():
            display_name = "Recommendation & Correlation Agent" if name == "Correlation Agent" else name
            latency = details.get("latency_ms")
            response = f"{latency:g} ms" if isinstance(latency, (int, float)) else (
                "Service monitor" if name == "Common Monitoring Agent" else "Waiting for first run"
            )
            status = details.get("status", "unavailable")
            glyph, color = agent_style(name)
            agent_cards.append(
                f'<div class="overview-agent-card">'
                f'<span class="agent-icon" style="background:{color}1f;color:{color}">{icon(glyph, 19, color, 2)}</span>'
                f'<div class="overview-agent-details"><div class="overview-agent-name">{html.escape(display_name)}</div>'
                f'<div class="overview-agent-meta"><span class="status-dot status-{status_class(status)}"></span>'
                f'{html.escape(status.title())} · {html.escape(response)}</div></div></div>'
            )
        md(f'<div class="overview-agent-grid">{"".join(agent_cards)}</div>')

    left, middle, right = st.columns([1.1, 1, 1.3])
    with left, st.container(border=True):
        head, link = st.columns([2, 1])
        with head:
            md(card_header(icon("alert", 16, "currentColor", 2.2), "#ef5c62", "Recent Incidents"))
        with link:
            st.button("View All →", key="viewall_incidents", on_click=go_to, args=("Incident Investigation",))
        incident_rows(incidents, 3, devices)

    with middle, st.container(border=True):
        head, link = st.columns([2, 1])
        with head:
            md(card_header("🔥", "#f97316", "Top Hot Zones"))
        with link:
            st.button("View All →", key="viewall_hotzones", on_click=go_to, args=("Live Network Map",))
        risks = sorted(devices, key=lambda item: item.get("risk_probability", 0), reverse=True)
        hot = [item for item in risks if item.get("risk_probability", 0) >= 0.45]
        if hot:
            render_topology(
                devices,
                height=360,
                highlight_ids={item["device_id"] for item in hot},
                map_key="overview-hot-zones",
            )
        else:
            render_topology(devices, height=360, map_key="overview-hot-zones")

    with right, st.container(border=True):
        md(card_header(icon("book-open", 16, "currentColor", 2.2), "#4f83ff", "Knowledge Base Explorer"))
        query = st.text_input("Search rules", placeholder="Search rules...", key="overview-rule-search", label_visibility="collapsed")
        list_col, help_col = st.columns([1.35, 1])
        with list_col:
            try:
                results = api_get("/knowledge/rules", q=query, limit=8)
                st.caption(f"{results['total']:,} matching facts and rules")
                palette = ["#6366f1", "#ef5c62", "#f3b61f", "#20b981", "#3b82f6"]
                rows = []
                for index, rule in enumerate(results["rules"][:5]):
                    action = html.escape(str(rule["recommended_action"]))
                    rows.append(
                        f'<div class="kb-row"><span class="kb-dot" style="background:{palette[index % len(palette)]}"></span>'
                        f'<div class="kb-name">{html.escape(str(rule["cause"]))}<div class="kb-act" title="{action}">{action}</div></div>'
                        f'<span class="kb-val">{rule["confidence"]:.0%}</span></div>'
                    )
                md("".join(rows))
            except requests.RequestException as error:
                st.error(f"Knowledge base unavailable: {error}")
        with help_col:
            md('<div class="help-card"><div style="font-size:1.6rem">💡</div><div class="hc-title">Need help?</div><div class="hc-text">Explore our knowledge base for detailed diagnostic rules and recommendations.</div></div>')
            st.button("Browse KB →", key="browse_kb", on_click=go_to, args=("Knowledge Base",), use_container_width=True)

    with st.container(border=True):
        info, report = st.columns([4, 1])
        with info:
            md(
                f'<div class="qa-row"><span class="qa-chip">Queue depth<b>{data.get("queued", 0)}</b></span>'
                f'<span class="qa-chip">Static contexts<b>{health.get("static_rules", 0):,}</b></span>'
                f'<span class="qa-chip">Backend<b>{html.escape(str(health.get("status", "unavailable")))}</b></span>'
                f'<span class="qa-chip">Worker<b>{html.escape(str(health.get("worker", "unavailable")))}</b></span></div>'
            )
        with report:
            if incidents:
                st.link_button("Open latest report", f"{API_URL}/incidents/{incidents[0]['incident_id']}/report", use_container_width=True)


def render_inventory(data: dict[str, Any]) -> None:
    devices = data.get("devices", [])
    if not devices:
        st.info("No devices are registered yet.")
        return
    frame = pd.DataFrame(devices)
    frame["connected_to"] = frame.apply(
        lambda device: ";".join(device_neighbors(device.to_dict())),
        axis=1,
    )
    columns = [
        name
        for name in (
            "device_id", "name", "device_type", "vendor", "status",
            "risk_probability", "connected_to", "last_seen",
        )
        if name in frame
    ]
    with st.container(border=True):
        st.dataframe(frame[columns], hide_index=True, use_container_width=True)
        st.download_button("Download inventory CSV", frame[columns].to_csv(index=False), "device-inventory.csv", "text/csv")
    with st.container(border=True):
        render_topology(devices, height=540, map_key="device-inventory")


def render_incidents(data: dict[str, Any]) -> None:
    incidents = data.get("incidents", [])
    if not incidents:
        st.info("No incidents are available yet.")
        return
    options = {f"{item['severity'].upper()} · {item['incident_id'][:12]} · {item['summary'][:65]}": item for item in incidents}
    selected = st.selectbox("Choose an incident", list(options))
    incident = options[selected]
    with st.container(border=True):
        show_incident(incident, data.get("devices", []))


def render_pending_human_review(data: dict[str, Any]) -> None:
    pending = [
        incident
        for incident in data.get("incidents", [])
        if incident.get("human_questions")
    ]
    if not pending:
        return

    seen_dialogs = st.session_state.setdefault("hitl_dialog_seen", set())
    requested_id = st.session_state.get("hitl_dialog_requested")
    incident = next(
        (item for item in pending if str(item["incident_id"]) == requested_id),
        None,
    )
    if incident is None:
        incident = next(
            (item for item in pending if str(item["incident_id"]) not in seen_dialogs),
            None,
        )

    if incident is not None:
        incident_id = str(incident["incident_id"])
        seen_dialogs.add(incident_id)
        st.session_state.pop("hitl_dialog_requested", None)
        render_human_review_dialog(incident, data.get("devices", []))
        return

    st.info(f"{len(pending)} incident(s) are waiting for additional information.")
    if st.button("Open pending HITL questions", key="open-pending-hitl"):
        st.session_state["hitl_dialog_requested"] = str(pending[0]["incident_id"])


def render_knowledge_base() -> None:
    query = st.text_input("Search causes, metrics, device roles, vendor contexts, or actions", placeholder="e.g. latency, router, interface errors")
    try:
        response = api_get("/knowledge/rules", q=query, limit=100)
    except requests.RequestException as error:
        st.error(f"Could not query the knowledge base: {error}")
        return
    st.metric("Matching rule contexts", f"{response['total']:,}")
    if response["rules"]:
        with st.container(border=True):
            st.dataframe(pd.DataFrame(response["rules"]), hide_index=True, use_container_width=True)
    else:
        st.info("No matching rules found.")


def render_analytics(data: dict[str, Any]) -> None:
    incidents = data.get("incidents", [])
    devices = data.get("devices", [])
    if not incidents:
        st.info("Analytics will populate as telemetry is received.")
        return
    points = []
    for incident in reversed(incidents):
        values = incident.get("telemetry", {})
        points.append({
            "Timestamp": incident.get("timestamp"),
            "Latency (ms)": values.get("latency_ms"),
            "Packet loss (%)": values.get("packet_loss_pct"),
            "CPU (%)": values.get("cpu_utilization_pct"),
        })
    series = pd.DataFrame(points).dropna(subset=["Timestamp"]).set_index("Timestamp")
    metric, severity = st.columns(2)
    with metric, st.container(border=True):
        st.subheader("Telemetry trends")
        st.line_chart(series, height=360)
    with severity, st.container(border=True):
        st.subheader("Current device status")
        counts = pd.Series([item.get("status", "unknown") for item in devices]).value_counts()
        st.bar_chart(counts, height=360, color="#6253b7")
    st.subheader("Historical baselines")
    contexts = [
        {"Incident": item["incident_id"][:8], **context}
        for item in incidents
        for context in item.get("historical_context", [])
    ]
    if contexts:
        st.dataframe(pd.DataFrame(contexts), hide_index=True, use_container_width=True)
    else:
        st.caption("Two-hour comparison baselines appear when a device has multiple processed samples.")


def render_settings(health: dict[str, Any]) -> None:
    with st.container(border=True):
        st.json({
            "backend": API_URL,
            "overall": health.get("status"),
            "redis_queue": health.get("queue"),
            "worker": health.get("worker"),
            "database": health.get("database"),
            "static_rule_contexts": health.get("static_rules"),
        })
    try:
        schema = api_get("/telemetry/schema")
        st.subheader("Canonical telemetry units")
        rows = [
            {
                "Metric": metric,
                "Canonical unit": details["canonical_unit"],
                "Accepted input units": ", ".join(details["accepted_input_units"]),
                "Normal range": f"{details['normal_range']['minimum']}–{details['normal_range']['maximum']} {details['normal_range']['unit']}",
            }
            for metric, details in schema["metrics"].items()
        ]
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
    except requests.RequestException as error:
        st.error(f"Could not load telemetry configuration: {error}")


def main() -> None:
    page, _ = render_sidebar()
    apply_theme()
    try:
        health = api_get("/health")
        data = api_get("/overview")
    except requests.RequestException as error:
        st.error(f"Could not reach the FastAPI backend at {API_URL}: {error}")
        st.info("Start the API and Redis Streams worker, then refresh this page.")
        st.stop()
    show_topbar(page, health)
    if page == "Overview":
        render_overview(data, health)
    elif page == "Live Network Map":
        devices = data.get("devices", [])
        with st.container(border=True):
            render_topology(devices, height=650, map_key="live-network")
    elif page == "Event Simulation":
        render_simulation(data.get("devices", []))
    elif page == "Device Inventory":
        render_inventory(data)
    elif page == "Agent Control Center":
        st.metric("Overall monitoring status", health.get("common_monitoring_agent", health.get("status", "unknown")))
        left, right = st.columns([1.4, 1])
        with left, st.container(border=True):
            show_agent_panel(health)
        with right, st.container(border=True):
            st.subheader("Runtime services")
            for label, key in (("API", "status"), ("Redis Streams", "queue"), ("Python worker", "worker"), ("Database", "database")):
                value = health.get(key, "unknown")
                md(f'<div class="agent-row"><b>{label}</b><span><span class="status-dot status-{status_class(value)}"></span>{html.escape(str(value).title())}</span></div>')
            st.metric("Static rule contexts", f"{health.get('static_rules', 0):,}")
    elif page == "Incident Investigation":
        render_incidents(data)
    elif page == "Knowledge Base":
        render_knowledge_base()
    elif page == "Analytics":
        render_analytics(data)
    elif page == "Settings":
        render_settings(health)
    render_pending_human_review(data)


main()
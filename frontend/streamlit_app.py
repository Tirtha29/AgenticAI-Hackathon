from __future__ import annotations

import json
import html
import os
import random
from datetime import datetime, timezone
from typing import Any

import pandas as pd
import pydeck as pdk
import requests
import streamlit as st
from dotenv import load_dotenv

load_dotenv()
API_URL = os.getenv("API_URL", "http://localhost:8000").rstrip("/")
PAGES = (
    "Overview",
    "Live Network Map",
    "Device Inventory",
    "Agent Control Center",
    "Incident Investigation",
    "Knowledge Base",
    "Analytics",
    "Settings",
)

st.set_page_config(page_title="NetCoop AI · Network Intelligence", page_icon="🌐", layout="wide")
st.markdown(
    """
    <style>
    :root {
        --ink: #17213d;
        --muted: #64708b;
        --purple: #6253b7;
        --line: #e6e9f2;
        --green: #20b981;
        --yellow: #f3b61f;
        --red: #ef5c62;
    }
    .stApp { background: linear-gradient(135deg, #fff9f2 0%, #f3f5ff 48%, #effaf7 100%); color: var(--ink); }
    [data-testid="stHeader"] { background: transparent; }
    [data-testid="stAppViewContainer"] { background: transparent; }
    [data-testid="stSidebar"] { background: linear-gradient(180deg, #fffaf4 0%, #f8f6ff 100%); border-right: 1px solid #ece8f2; }
    [data-testid="stSidebar"] [data-testid="stRadio"] label { color: #34405c; font-weight: 600; }
    h1, h2, h3, h4 { color: var(--ink); letter-spacing: -0.025em; }
    [data-testid="stMetric"] {
        background: linear-gradient(145deg, #fff8f1, #f3f1ff); border: 1px solid var(--line); border-radius: 18px;
        padding: 14px 17px; box-shadow: 0 5px 20px rgba(50,62,100,.045);
    }
    [data-testid="stMetricLabel"] { color: var(--muted); font-weight: 650; }
    [data-testid="stMetricValue"] { color: var(--ink); }
    [data-testid="stVerticalBlockBorderWrapper"] {
        border-color: var(--line) !important; border-radius: 18px;
        background: linear-gradient(145deg, rgba(255,255,255,.94), rgba(247,245,255,.92));
    }
    .hero {
        display:flex; align-items:center; justify-content:space-between; gap:20px; padding:22px 26px;
        margin: 4px 0 20px; border:1px solid #e8e8f4; border-radius:24px;
        background: radial-gradient(ellipse at 82% 15%, #d9f3e8 0, transparent 36%),
                    radial-gradient(ellipse at 18% 0%, #e8e2ff 0, transparent 44%),
                    linear-gradient(105deg,#fff5e9 0%,#f4f1ff 52%,#fff0ec 100%);
        box-shadow: 0 10px 32px rgba(60,65,112,.07);
    }
    .hero h1 { margin:0; font-size:1.75rem; }
    .hero p { margin:.35rem 0 0; color:var(--muted); }
    .live-pill { background:#e5f8ee; border:1px solid #c9efda; color:#18784c; border-radius:999px; padding:8px 14px; white-space:nowrap; font-size:.86rem; font-weight:700; }
    .panel-title { display:flex; align-items:center; justify-content:space-between; margin-bottom:8px; }
    .panel-title h3 { margin:0; font-size:1.04rem; }
    .agent-row { display:flex; align-items:center; justify-content:space-between; gap:10px; padding:10px 2px; border-bottom:1px solid #edf0f5; }
    .agent-row:last-child { border-bottom:0; }
    .agent-name { color:#27334f; font-size:.9rem; font-weight:650; }
    .agent-meta { color:var(--muted); font-size:.76rem; margin-top:3px; }
    .status-dot { display:inline-block; width:9px; height:9px; border-radius:50%; margin-right:6px; background:#9aa3b5; }
    .status-healthy { background:var(--green); } .status-ready { background:#55a5ff; }
    .status-degraded, .status-stale, .status-unavailable { background:var(--red); }
    .status-warning { background:var(--yellow); } .status-critical { background:var(--red); }
    .incident-card { padding:12px 14px; margin:8px 0; background:linear-gradient(110deg,#fff7f3,#f7f5ff); border:1px solid var(--line); border-radius:14px; }
    .incident-title { font-weight:700; color:#26324e; }
    .incident-meta { color:var(--muted); font-size:.78rem; margin-top:3px; }
    .donut {
        width:138px;height:138px;border-radius:50%;display:grid;place-items:center;
        background:conic-gradient(#31c39a var(--healthy), #ffc83d 0 var(--warning), #f06469 0 var(--critical), #e3e7ef 0);
        margin:auto; position:relative;
    }
    .donut:before { content:""; position:absolute; width:96px;height:96px;border-radius:50%;background:white; }
    .donut span { position:relative;font-size:1.1rem;font-weight:800;color:var(--ink); }
    .small-muted { color:var(--muted); font-size:.83rem; }
    </style>
    """,
    unsafe_allow_html=True,
)


def api_get(path: str, **params: Any) -> Any:
    response = requests.get(f"{API_URL}{path}", params=params or None, timeout=8)
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
        return f"{seconds // 60}m ago"
    except ValueError:
        return value


def status_class(value: str) -> str:
    return value.strip().lower().replace(" ", "-")


def show_hero() -> None:
    now = datetime.now().astimezone().strftime("%H:%M:%S")
    st.markdown(
        f"""
        <div class="hero">
          <div><h1>👋 Welcome to NetCoop AI</h1>
          <p>Real-time network monitoring, intelligent diagnosis and proactive recommendations</p></div>
          <div class="live-pill">● Live · {now}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def make_map(devices: list[dict[str, Any]], *, heat: bool = False, height: int = 360) -> None:
    mapped = [
        device for device in devices
        if device.get("location_known") and device.get("latitude") is not None and device.get("longitude") is not None
    ]
    if not mapped:
        st.info("Upload a device inventory with coordinates to render the network map.")
        return
    frame = pd.DataFrame(mapped)
    colors = {
        "healthy": [39, 190, 127, 235],
        "warning": [255, 192, 44, 245],
        "critical": [239, 76, 80, 250],
        "unknown": [132, 143, 166, 210],
    }
    frame["color"] = frame["status"].map(colors).apply(
        lambda value: value if isinstance(value, list) else colors["unknown"]
    )
    layers: list[Any] = []
    if heat:
        frame["risk_weight"] = frame.get("risk_probability", pd.Series([0.0] * len(frame))).fillna(0.0)
    if heat and frame["risk_weight"].max() > 0:
        layers.append(pdk.Layer(
            "HeatmapLayer",
            data=frame,
            get_position="[longitude, latitude]",
            get_weight="risk_weight",
            radiusPixels=55,
            intensity=1.2,
            threshold=0.05,
            opacity=0.65,
        ))
    layers.append(pdk.Layer(
        "ScatterplotLayer",
        data=frame,
        get_position="[longitude, latitude]",
        get_fill_color="color",
        get_line_color=[255, 255, 255, 235],
        get_radius=95 if not heat else 70,
        radius_min_pixels=7,
        radius_max_pixels=18,
        line_width_min_pixels=2,
        pickable=True,
        auto_highlight=True,
    ))
    view = pdk.ViewState(
        latitude=float(frame["latitude"].mean()),
        longitude=float(frame["longitude"].mean()),
        zoom=12 if len(frame) < 30 else 10,
        pitch=0,
    )
    st.pydeck_chart(
        pdk.Deck(
            layers=layers,
            initial_view_state=view,
            tooltip={"text": "{name} · {device_id}\nType: {device_type}\nStatus: {status}\nRisk: {risk_probability}"},
            map_style="https://basemaps.cartocdn.com/gl/positron-gl-style/style.json",
        ),
        height=height,
        use_container_width=True,
    )


def incident_rows(incidents: list[dict[str, Any]], limit: int = 5) -> None:
    if not incidents:
        st.info("No processed incidents yet. Send telemetry to begin.")
        return
    for incident in incidents[:limit]:
        severity = str(incident.get("severity", "unknown")).upper()
        top_probability = max(
            (cause.get("probability", 0) for cause in incident.get("probable_causes", [])),
            default=0,
        )
        st.markdown(
            f"""
            <div class="incident-card">
              <div class="incident-title">{html.escape(severity)} · {html.escape(str(incident.get('incident_id', ''))[:12])} · {top_probability:.0%}</div>
              <div class="incident-meta">{html.escape(str(incident.get('summary', '')))}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        with st.expander(f"Investigate {incident.get('incident_id', '')[:8]}"):
            show_incident(incident)


def show_incident(incident: dict[str, Any]) -> None:
    st.write(incident.get("summary", ""))
    st.caption(f"Status: {incident.get('conclusion', 'unknown').replace('_', ' ').title()} · 90% confidence threshold")
    causes = incident.get("probable_causes", [])
    if causes:
        st.subheader("Ranked recommendations")
        for index, cause in enumerate(causes, 1):
            st.markdown(
                f"**{index}. {cause['cause']} — {cause['probability']:.0%}**  \n"
                f"{cause['recommended_action']}"
            )
            st.caption("Evidence: " + "; ".join(cause.get("evidence", [])))
    questions = incident.get("human_questions", [])
    if questions:
        st.warning("Additional client information is needed before confirming a cause.")
        for question in questions:
            st.markdown(f"- {question}")
        with st.form(f"information-{incident['incident_id']}"):
            firewall_alert = st.selectbox("Firewall or UTM alert?", ["Not sure", "No", "Yes"], key=f"utm-{incident['incident_id']}")
            firewall_change = st.selectbox("Recent firewall policy change?", ["Not sure", "No", "Yes"], key=f"fw-{incident['incident_id']}")
            interface_errors = st.selectbox("Are interface/CRC errors increasing?", ["Not sure", "No", "Yes"], key=f"crc-{incident['incident_id']}")
            route_change = st.selectbox("Recent routing/QoS change?", ["Not sure", "No", "Yes"], key=f"route-{incident['incident_id']}")
            include_drops = st.checkbox("Include an exact firewall drop count", key=f"include-drops-{incident['incident_id']}")
            drops = st.number_input("Firewall drops (events)", min_value=0, step=1, key=f"drops-{incident['incident_id']}")
            if st.form_submit_button("Submit client information"):
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
                    api_post(f"/incidents/{incident['incident_id']}/information", json={"answers": answers})
                    st.success("Client information submitted; diagnosis has been updated.")
                    st.rerun()
                except requests.RequestException as error:
                    st.error(f"Could not submit client information: {error}")
    st.json({
        "telemetry": incident.get("telemetry", {}),
        "units": incident.get("units", {}),
        "infrastructure_findings": incident.get("infrastructure_findings", []),
        "nearby_devices": incident.get("blast_radius", []),
        "historical_context": incident.get("historical_context", []),
        "limitations": incident.get("limitations", ""),
    })
    st.link_button("Download incident report", f"{API_URL}/incidents/{incident['incident_id']}/report")


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
        st.markdown(
            f"""
            <div class="agent-row">
              <div><div class="agent-name">{html.escape(display_name)}</div>
              <div class="agent-meta"><span class="status-dot status-{status_class(status)}"></span>{html.escape(label)}</div></div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def render_sidebar() -> tuple[str, str | None]:
    st.sidebar.markdown("## 🌐 NetCoop AI")
    st.sidebar.caption("Smart Network Intelligence")
    page = st.sidebar.radio("Navigation", PAGES, label_visibility="collapsed")
    st.sidebar.divider()
    st.sidebar.subheader("Device inventory")
    st.sidebar.caption("Demo site: IIT Bhubaneswar")
    if st.sidebar.button("Load 15 synthetic IIT Bhubaneswar devices", help="Replaces the current device inventory with illustrative campus-area locations."):
        try:
            result = api_post("/devices/demo/iit-bhubaneswar")
            st.sidebar.success(f"Loaded {result['uploaded']} synthetic devices.")
            st.rerun()
        except requests.RequestException as error:
            st.sidebar.error(f"Could not load demo devices: {error}")
    inventory = st.sidebar.file_uploader("Upload CSV or GeoJSON", type=["csv", "json", "geojson"], key="inventory-upload")
    if inventory and st.sidebar.button("Ingest device map", type="primary"):
        try:
            result = api_post("/devices/upload", files={"file": (inventory.name, inventory.getvalue())})
            st.sidebar.success(f"Ingested {result['uploaded']} devices.")
            st.rerun()
        except requests.RequestException as error:
            st.sidebar.error(f"Inventory upload failed: {error}")
    st.sidebar.caption("CSV: device_id, latitude, longitude; optional name, device_type, vendor, neighbors.")
    st.sidebar.subheader("Client telemetry")
    telemetry_file = st.sidebar.file_uploader("Upload telemetry JSON", type=["json"], key="telemetry-upload")
    if telemetry_file and st.sidebar.button("Queue uploaded telemetry"):
        try:
            if telemetry_file.size > 1_000_000:
                raise ValueError("Telemetry JSON must be 1 MB or smaller.")
            payload = json.loads(telemetry_file.getvalue())
            if not isinstance(payload, dict):
                raise ValueError("Upload one JSON object with device_id, metrics, and units.")
            queued = api_post("/telemetry", json=payload)
            st.sidebar.success(f"Queued event {queued['event_id'][:8]}.")
        except (ValueError, requests.RequestException) as error:
            st.sidebar.error(f"Telemetry upload failed: {error}")
    st.sidebar.subheader("Synthetic telemetry")
    try:
        device_ids = [device["device_id"] for device in api_get("/overview").get("devices", [])]
    except requests.RequestException:
        device_ids = []
    selected_device = st.sidebar.selectbox("Device", device_ids or ["SW_CAMPUS_1"])
    bandwidth_unit = st.sidebar.selectbox("Bandwidth unit", ["Mbps", "Gbps", "Kbps", "bps"])
    scenario = st.sidebar.selectbox("Scenario", ["normal", "latency_spike", "hardware_failure"])
    if st.sidebar.button("Send sample telemetry"):
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
            st.sidebar.success(f"Queued event {response['event_id'][:8]}.")
        except requests.RequestException as error:
            st.sidebar.error(f"Telemetry submission failed: {error}")
    return page, inventory.name if inventory else None


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
    show_hero()
    columns = st.columns(5)
    for column, label, value, color in zip(
        columns,
        ("Total Devices", "Healthy", "Warning", "Critical", "Active Incidents"),
        (len(devices), counts["healthy"], counts["warning"], counts["critical"], active),
        ("🔷", "🟢", "🟡", "🔴", "🟣"),
    ):
        column.metric(f"{color} {label}", value)

    left, right = st.columns([1.62, 1])
    with left, st.container(border=True):
        st.markdown('<div class="panel-title"><h3>📍 IIT Bhubaneswar Network Map</h3><span class="small-muted">🟢 Healthy　🟡 Warning　🔴 Critical　⚪ Unknown</span></div>', unsafe_allow_html=True)
        make_map(devices, height=355)
        st.caption("Synthetic device coordinates are illustrative campus-area positions, not surveyed device placements.")
    with right, st.container(border=True):
        st.markdown('<div class="panel-title"><h3>📈 Network Performance</h3><span class="small-muted">Recent telemetry</span></div>', unsafe_allow_html=True)
        performance = []
        for incident in reversed(incidents):
            telemetry = incident.get("telemetry", {})
            if "latency_ms" in telemetry or "packet_loss_pct" in telemetry:
                performance.append({
                    "Time": incident.get("timestamp"),
                    "Latency (ms)": telemetry.get("latency_ms"),
                    "Packet loss (%)": telemetry.get("packet_loss_pct"),
                })
        if performance:
            chart = pd.DataFrame(performance).dropna(subset=["Time"]).set_index("Time")
            st.line_chart(chart, height=220, color=["#4f83ff", "#8b5cf6"])
        else:
            st.info("Performance charts appear after telemetry has been processed.")
        st.markdown('<div class="panel-title"><h3>🛡️ Agent Control Center</h3><span class="small-muted">Live health</span></div>', unsafe_allow_html=True)
        show_agent_panel(health, compact=True)

    left, right = st.columns([1, 1])
    with left, st.container(border=True):
        st.markdown('<div class="panel-title"><h3>🩺 Device Health Distribution</h3></div>', unsafe_allow_html=True)
        healthy_pct = round(100 * counts["healthy"] / len(devices)) if devices else 0
        st.markdown(
            f'<div class="donut" style="--healthy:{healthy_pct}%;--warning:{healthy_pct + (100*counts["warning"]/max(1,len(devices)))}%;--critical:{healthy_pct + (100*(counts["warning"]+counts["critical"])/max(1,len(devices)))}%"><span>{healthy_pct}%</span></div>',
            unsafe_allow_html=True,
        )
        st.caption(f"🟢 Healthy {counts['healthy']}　 🟡 Warning {counts['warning']}　 🔴 Critical {counts['critical']}　 ⚪ Unknown {counts['unknown']}")
    with right, st.container(border=True):
        st.markdown('<div class="panel-title"><h3>🔥 Top Hot Zones</h3></div>', unsafe_allow_html=True)
        make_map(devices, heat=True, height=225)
        risks = sorted(devices, key=lambda item: item.get("risk_probability", 0), reverse=True)
        hot = [item for item in risks if item.get("risk_probability", 0) >= 0.45]
        if hot:
            st.caption(" · ".join(f"{item['device_id']} · {item['risk_probability']:.0%}" for item in hot[:4]))
        else:
            st.caption("Awaiting telemetry before marking hot zones. The sample device locations are illustrative.")

    left, middle, right = st.columns([1, 1, 1])
    with left, st.container(border=True):
        st.markdown('<div class="panel-title"><h3>🚨 Recent Incidents</h3></div>', unsafe_allow_html=True)
        incident_rows(incidents, 3)
    with middle, st.container(border=True):
        st.markdown('<div class="panel-title"><h3>🧠 Knowledge Base Explorer</h3></div>', unsafe_allow_html=True)
        query = st.text_input("Search rules", placeholder="latency, packet loss, router…", key="overview-rule-search")
        try:
            results = api_get("/knowledge/rules", q=query, limit=8)
            st.caption(f"{results['total']:,} matching facts and rules")
            for rule in results["rules"][:5]:
                st.markdown(f"**{rule['cause']}** · {rule['confidence']:.0%}")
                st.caption(rule["recommended_action"])
        except requests.RequestException as error:
            st.error(f"Knowledge base unavailable: {error}")
    with right, st.container(border=True):
        st.markdown('<div class="panel-title"><h3>⚡ Quick Actions</h3></div>', unsafe_allow_html=True)
        st.write(f"Queue depth: **{data.get('queued', 0)}** · Static contexts: **{health.get('static_rules', 0):,}**")
        st.write(f"Backend: **{health.get('status', 'unavailable')}** · Worker: **{health.get('worker', 'unavailable')}**")
        if incidents:
            st.link_button("Open latest report", f"{API_URL}/incidents/{incidents[0]['incident_id']}/report", use_container_width=True)


def render_inventory(data: dict[str, Any]) -> None:
    st.title("📍 Device Inventory")
    st.caption("Upload a CSV or GeoJSON inventory from the sidebar, then review locations and current status.")
    devices = data.get("devices", [])
    if not devices:
        st.info("No devices are registered yet.")
        return
    frame = pd.DataFrame(devices)
    columns = [name for name in ("device_id", "name", "device_type", "vendor", "status", "risk_probability", "latitude", "longitude", "last_seen") if name in frame]
    st.dataframe(frame[columns], hide_index=True, use_container_width=True)
    make_map(devices, height=540)
    st.download_button("Download inventory CSV", frame[columns].to_csv(index=False), "device-inventory.csv", "text/csv")


def render_incidents(data: dict[str, Any]) -> None:
    st.title("🚨 Incident Investigation")
    st.caption("Inspect the evidence, review ranked probable causes, and answer agent follow-up questions.")
    incidents = data.get("incidents", [])
    if not incidents:
        st.info("No incidents are available yet.")
        return
    options = {f"{item['severity'].upper()} · {item['incident_id'][:12]} · {item['summary'][:65]}": item for item in incidents}
    selected = st.selectbox("Choose an incident", list(options))
    incident = options[selected]
    show_incident(incident)


def render_knowledge_base() -> None:
    st.title("🧠 Knowledge Base")
    st.caption("Search static diagnostic facts and correlation rules. Context-specific fact entries are heuristic references, not independent probabilities.")
    query = st.text_input("Search causes, metrics, device roles, vendor contexts, or actions", placeholder="e.g. latency, router, interface errors")
    try:
        response = api_get("/knowledge/rules", q=query, limit=100)
    except requests.RequestException as error:
        st.error(f"Could not query the knowledge base: {error}")
        return
    st.metric("Matching rule contexts", f"{response['total']:,}")
    if response["rules"]:
        st.dataframe(pd.DataFrame(response["rules"]), hide_index=True, use_container_width=True)
    else:
        st.info("No matching rules found.")


def render_analytics(data: dict[str, Any]) -> None:
    st.title("📊 Network Analytics")
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
    st.title("⚙️ Settings & System Status")
    st.caption("Unit contract, backend configuration status, and service health.")
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
    try:
        health = api_get("/health")
        data = api_get("/overview")
    except requests.RequestException as error:
        st.error(f"Could not reach the FastAPI backend at {API_URL}: {error}")
        st.info("Start the API and Redis Streams worker, then refresh this page.")
        st.stop()
    if page == "Overview":
        render_overview(data, health)
    elif page == "Live Network Map":
        st.title("🗺️ IIT Bhubaneswar · Live Network Map")
        devices = data.get("devices", [])
        make_map(devices, height=650)
        st.caption("Demo coordinates are illustrative campus-area positions, not surveyed device placements. Nearby-device risk is a distance heuristic, not confirmation that a neighboring device has failed.")
        st.dataframe(pd.DataFrame(devices), hide_index=True, use_container_width=True)
    elif page == "Device Inventory":
        render_inventory(data)
    elif page == "Agent Control Center":
        st.title("🤖 Agent Control Center")
        st.caption("Live status and most recent execution latency for every LangGraph workflow agent.")
        st.metric("Overall monitoring status", health.get("common_monitoring_agent", health.get("status", "unknown")))
        left, right = st.columns([1.4, 1])
        with left, st.container(border=True):
            show_agent_panel(health)
        with right, st.container(border=True):
            st.subheader("Runtime services")
            for label, key in (("API", "status"), ("Redis Streams", "queue"), ("Python worker", "worker"), ("Database", "database")):
                value = health.get(key, "unknown")
                st.markdown(f'<div class="agent-row"><b>{label}</b><span><span class="status-dot status-{status_class(value)}"></span>{value.title()}</span></div>', unsafe_allow_html=True)
            st.metric("Static rule contexts", f"{health.get('static_rules', 0):,}")
    elif page == "Incident Investigation":
        render_incidents(data)
    elif page == "Knowledge Base":
        render_knowledge_base()
    elif page == "Analytics":
        render_analytics(data)
    elif page == "Settings":
        render_settings(health)


main()

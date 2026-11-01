from __future__ import annotations

import json
import os
from typing import Any

import pandas as pd
import requests
import streamlit as st
import streamlit.components.v1 as components
from dotenv import load_dotenv

load_dotenv()
API_URL = os.getenv("API_URL", "https://netcoopai.onrender.com").rstrip("/")
EVENT_TYPES = ("festival", "sports", "livestream", "exam", "outage")


def _load_presets() -> dict[str, dict[str, Any]]:
    response = requests.get(f"{API_URL}/simulation/presets", timeout=8)
    response.raise_for_status()
    return response.json()["presets"]


def _shape_for_device_type(device_type: str) -> str:
    key = (device_type or "").strip().lower()
    if "router" in key:
        return "circle"
    if "switch" in key:
        return "square"
    if "firewall" in key:
        return "diamond"
    if "gateway" in key:
        return "hexagon"
    if "access point" in key or "ap" in key or "wifi" in key:
        return "triangle"
    return "square"


def _extract_device_neighbors(device: dict[str, Any]) -> list[str]:
    neighbors = device.get("neighbors") or device.get("neighbors_json") or []
    if isinstance(neighbors, str):
        try:
            neighbors = json.loads(neighbors)
        except json.JSONDecodeError:
            neighbors = [item.strip() for item in neighbors.split(";") if item.strip()]
    return [str(item) for item in neighbors] if isinstance(neighbors, list) else []


def _shape_svg(device_type: str, x: float, y: float) -> str:
    shape = _shape_for_device_type(device_type)
    if shape == "circle":
        return f'<circle class="body" cx="{x:.1f}" cy="{y:.1f}" r="18" />'
    if shape == "square":
        return f'<rect class="body" x="{x - 18:.1f}" y="{y - 18:.1f}" width="36" height="36" rx="7" />'
    if shape == "triangle":
        return f'<polygon class="body" points="{x:.1f},{y - 20:.1f} {x - 18:.1f},{y + 18:.1f} {x + 18:.1f},{y + 18:.1f}" />'
    if shape == "diamond":
        return f'<polygon class="body" points="{x:.1f},{y - 22:.1f} {x + 22:.1f},{y:.1f} {x:.1f},{y + 22:.1f} {x - 22:.1f},{y:.1f}" />'
    if shape == "hexagon":
        return f'<polygon class="body" points="{x:.1f},{y - 22:.1f} {x + 20:.1f},{y - 12:.1f} {x + 20:.1f},{y + 12:.1f} {x:.1f},{y + 22:.1f} {x - 20:.1f},{y + 12:.1f} {x - 20:.1f},{y - 12:.1f}" />'
    return f'<rect class="body" x="{x - 18:.1f}" y="{y - 18:.1f}" width="36" height="36" rx="7" />'


def _render_animation(result: dict[str, Any], devices: list[dict[str, Any]]) -> None:
    by_id = {str(device["device_id"]): device for device in devices}

    positions: dict[str, tuple[float, float]] = {}
    latitudes = [float(device.get("latitude", 0.0)) for device in devices if device.get("latitude") is not None]
    longitudes = [float(device.get("longitude", 0.0)) for device in devices if device.get("longitude") is not None]
    if latitudes and longitudes:
        min_lat, max_lat = min(latitudes), max(latitudes)
        min_lon, max_lon = min(longitudes), max(longitudes)

        def scale_x(lon: float) -> float:
            if max_lon == min_lon:
                return 120.0
            return 110.0 + ((lon - min_lon) / (max_lon - min_lon)) * 680.0

        def scale_y(lat: float) -> float:
            if max_lat == min_lat:
                return 120.0
            return 110.0 + ((max_lat - lat) / (max_lat - min_lat)) * 420.0

    else:
        def scale_x(index: int) -> float:
            return 120.0 + (index % 5) * 140.0

        def scale_y(index: int) -> float:
            return 110.0 + (index // 5) * 110.0

    for index, device in enumerate(devices):
        device_id = str(device["device_id"])
        latitude = device.get("latitude")
        longitude = device.get("longitude")
        if latitude is not None and longitude is not None:
            positions[device_id] = (scale_x(float(longitude)), scale_y(float(latitude)))
        else:
            positions[device_id] = (scale_x(index), scale_y(index))

    edges: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for device in devices:
        device_id = str(device["device_id"])
        for neighbor in _extract_device_neighbors(device):
            pair = tuple(sorted((device_id, str(neighbor))))
            if pair[0] == pair[1] or pair in seen:
                continue
            seen.add(pair)
            if pair[0] in positions and pair[1] in positions:
                x1, y1 = positions[pair[0]]
                x2, y2 = positions[pair[1]]
                edges.append({"from": pair[0], "to": pair[1], "x1": x1, "y1": y1, "x2": x2, "y2": y2})

    for a, b in result.get("links", []):
        a, b = str(a), str(b)
        pair = tuple(sorted((a, b)))
        if a in positions and b in positions and pair not in seen:
            x1, y1 = positions[a]
            x2, y2 = positions[b]
            edges.append({"from": a, "to": b, "x1": x1, "y1": y1, "x2": x2, "y2": y2})
            seen.add(pair)

    frames_util = result.get("frames", {}).get("utilization", {})
    frames_severity = result.get("frames", {}).get("severity", {})
    frame_minutes = result.get("frames", {}).get("minutes", [])
    max_frames = max(1, len(frame_minutes))

    nodes = []
    for device_id, device in sorted(by_id.items()):
        pos = positions.get(device_id, (120.0, 120.0))
        nodes.append({
            "device_id": device_id,
            "device_type": str(device.get("device_type") or "network device").lower(),
            "name": device.get("name") or device_id,
            "x": pos[0],
            "y": pos[1],
            "util": frames_util.get(device_id, [0.0] * max_frames),
            "severity": frames_severity.get(device_id, [0] * max_frames),
        })

    edge_svg = "\n".join(
        f'<line class="edge" id="edge-{index}" x1="{edge["x1"]:.1f}" y1="{edge["y1"]:.1f}" x2="{edge["x2"]:.1f}" y2="{edge["y2"]:.1f}" />'
        for index, edge in enumerate(edges)
    )
    node_svg = "\n".join(
        f'''
        <g class="node severity-0" id="node-{device['device_id']}">
          <circle class="ring" cx="{device['x']:.1f}" cy="{device['y']:.1f}" r="28" />
          <circle class="pulse" cx="{device['x']:.1f}" cy="{device['y']:.1f}" r="18" fill="rgba(255,255,255,0.0)" />
          {_shape_svg(device['device_type'], device['x'], device['y'])}
          <rect class="tag" x="{device['x'] - 38:.1f}" y="{device['y'] + 24:.1f}" width="76" height="16" rx="6" />
          <text x="{device['x']:.1f}" y="{device['y'] + 34:.1f}">{str(device['device_id'])[:9]}</text>
        </g>
        '''
        for device in nodes
    )

    html = f"""
    <style>
      html, body {{ margin: 0; width: 100%; }}
      .netcoop-sim {{ width: min(100%, 900px); aspect-ratio: 900 / 620; margin: 0 auto; background: linear-gradient(180deg, rgba(18,27,54,.92), rgba(12,17,28,.96)); border-radius: 14px; overflow: hidden; border: 1px solid rgba(145,160,200,0.35); }}
      .netcoop-sim svg {{ display: block; width: 100%; height: 100%; }}
      .netcoop-sim .edge {{ stroke: rgba(134, 152, 196, 0.7); stroke-width: 2.2; fill: none; stroke-dasharray: 10 10; animation: flow 1.4s linear infinite; }}
      .netcoop-sim .edge.active {{ stroke: rgba(255, 209, 94, 0.9); stroke-width: 3.2; }}
      .netcoop-sim .node .ring {{ fill: none; stroke: rgba(255,255,255,0.0); stroke-width: 3; opacity: 0; }}
      .netcoop-sim .node.severity-0 .ring {{ stroke: rgba(52, 211, 153, 0.9); }}
      .netcoop-sim .node.severity-1 .ring {{ stroke: rgba(251, 191, 36, 0.9); }}
      .netcoop-sim .node.severity-2 .ring {{ stroke: rgba(248, 113, 113, 0.9); }}
      .netcoop-sim .node .body {{ stroke-width: 2.5; stroke: rgba(255,255,255,0.8); fill: rgba(239,244,255,0.95); }}
      .netcoop-sim .node.severity-0 .body {{ fill: rgba(216, 247, 228, 0.96); stroke: #2eb67d; }}
      .netcoop-sim .node.severity-1 .body {{ fill: rgba(255, 240, 179, 0.97); stroke: #d79a00; }}
      .netcoop-sim .node.severity-2 .body {{ fill: rgba(255, 214, 214, 0.98); stroke: #d74a4a; }}
      .netcoop-sim .node text {{ font-size: 10px; fill: rgba(239,245,255,0.92); font-family: Arial, sans-serif; text-anchor: middle; pointer-events: none; }}
      .netcoop-sim .node .tag {{ fill: rgba(15, 23, 42, 0.88); stroke: rgba(147, 163, 184, 0.7); }}
      .netcoop-sim .node .pulse {{ opacity: 0; }}
      .netcoop-sim .node.severity-1 .pulse, .netcoop-sim .node.severity-2 .pulse {{ opacity: 1; animation: pulse 1.2s ease-in-out infinite; }}
      @keyframes flow {{ from {{ stroke-dashoffset: 80; }} to {{ stroke-dashoffset: 0; }} }}
      @keyframes pulse {{ 0% {{ opacity: 0.16; transform: scale(0.92); }} 40% {{ opacity: 0.88; }} 100% {{ opacity: 0.12; transform: scale(1.22); }} }}
    </style>
    <div class="netcoop-sim">
      <svg viewBox="0 0 900 620" preserveAspectRatio="xMidYMid meet" xmlns="http://www.w3.org/2000/svg">
        {edge_svg}
        {node_svg}
      </svg>
    </div>
    <script>
      const nodeData = {json.dumps(nodes)};
      const edgeData = {json.dumps(edges)};
      const frameCount = {max_frames};
      const clamp = (value, min, max) => Math.min(Math.max(value, min), max);
      const severityOf = (deviceId, frameIndex) => {{
        const device = nodeData.find((d) => d.device_id === deviceId);
        if (!device || !device.severity || !device.severity.length) return 0;
        return Number(device.severity[clamp(frameIndex, 0, device.severity.length - 1)]) || 0;
      }};
      const utilOf = (deviceId, frameIndex) => {{
        const device = nodeData.find((d) => d.device_id === deviceId);
        if (!device || !device.util || !device.util.length) return 0;
        return Number(device.util[clamp(frameIndex, 0, device.util.length - 1)]) || 0;
      }};
      const updateFrame = (index) => {{
        nodeData.forEach((device) => {{
          const node = document.getElementById('node-' + device.device_id);
          if (!node) return;
          const severity = severityOf(device.device_id, index);
          node.classList.remove('severity-0', 'severity-1', 'severity-2');
          node.classList.add('severity-' + severity);
          const ring = node.querySelector('.ring');
          const util = utilOf(device.device_id, index);
          ring.setAttribute('r', String(22 + util * 12));
          ring.setAttribute('stroke-width', String(2 + Math.min(5, util * 2.8)));
          ring.setAttribute('opacity', severity === 0 ? '0.2' : String(0.52 + severity * 0.18));
          const body = node.querySelector('.body');
          if (body) {{
            body.setAttribute('stroke-width', String(2 + util * 1.4));
          }}
        }});
        edgeData.forEach((edge, idx) => {{
          const line = document.getElementById('edge-' + idx);
          if (!line) return;
          const a = utilOf(edge.from, index);
          const b = utilOf(edge.to, index);
          const score = Math.min(1, (a + b) / 3.2);
          line.classList.toggle('active', score > 0.55);
          line.setAttribute('stroke-width', String(2 + score * 4));
          line.setAttribute('stroke-opacity', String(0.38 + score));
          line.style.animationDuration = String(Math.max(0.6, 2.2 - score) + 's');
        }});
      }};
      let currentFrame = 0;
      updateFrame(currentFrame);
      setInterval(() => {{
        currentFrame = (currentFrame + 1) % frameCount;
        updateFrame(currentFrame);
      }}, 200);
      const animation = document.querySelector('.netcoop-sim');
      const resizeFrame = () => {{
        const height = `${{Math.ceil(animation.getBoundingClientRect().height + 8)}}px`;
        if (window.frameElement && window.frameElement.style.height !== height) {{
          window.frameElement.style.height = height;
        }}
      }};
      new ResizeObserver(resizeFrame).observe(animation);
      window.addEventListener('resize', resizeFrame);
      setInterval(resizeFrame, 500);
      resizeFrame();
    </script>
    """

    components.html(html, height=650, scrolling=False)


def render_simulation(devices: list[dict[str, Any]]) -> None:
    st.markdown(
        """
        <style>
          [data-testid="stAppViewContainer"] {
            container-type: inline-size;
          }
          @container (max-width: 900px) {
            body:has(#event-simulation-responsive) [data-testid="stForm"] [data-testid="stHorizontalBlock"],
            body:has(#event-simulation-responsive) [data-testid="stHorizontalBlock"]:has([data-testid="stMetric"]) {
              flex-wrap: wrap !important;
              gap: .75rem !important;
            }
            body:has(#event-simulation-responsive) [data-testid="stForm"] [data-testid="stHorizontalBlock"] > [data-testid="stColumn"],
            body:has(#event-simulation-responsive) [data-testid="stHorizontalBlock"]:has([data-testid="stMetric"]) > [data-testid="stColumn"] {
              flex: 1 1 calc(50% - .75rem) !important;
              min-width: 0 !important;
              width: auto !important;
            }
            body:has(#event-simulation-responsive) [data-testid="stMetricLabel"] {
              font-size: .78rem;
            }
            body:has(#event-simulation-responsive) [data-testid="stMetricValue"] {
              font-size: clamp(1.05rem, 4vw, 1.55rem);
              overflow-wrap: anywhere;
            }
          }
          @container (max-width: 600px) {
            body:has(#event-simulation-responsive) [data-testid="stForm"] [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {
              flex-basis: 100% !important;
            }
            body:has(#event-simulation-responsive) [data-testid="stTabs"] [role="tablist"] {
              max-width: 100%;
              overflow-x: auto;
              flex-wrap: nowrap;
            }
            body:has(#event-simulation-responsive) [data-testid="stTabs"] [role="tab"] {
              flex-shrink: 0;
              white-space: nowrap;
            }
          }
        </style>
        <div id="event-simulation-responsive" aria-hidden="true"></div>
        """,
        unsafe_allow_html=True,
    )
    st.subheader("What-if event simulation")
    st.caption("Model crowd demand and overload propagation through the declared device connections.")
    st.warning(
        "This is a planning estimate, not a calibrated forecast. Device capacities and traffic assumptions "
        "are illustrative; simulated results never modify live device health or telemetry."
    )
    try:
        presets = _load_presets()
    except requests.RequestException as error:
        st.error(f"Could not load simulation presets from the backend: {error}")
        return

    if not devices:
        st.info("Upload or load a connected-device inventory before simulating an event.")
        return

    with st.form("event-simulation-form"):
        event_type = st.selectbox(
            "Event type",
            EVENT_TYPES,
            format_func=lambda key: presets[key]["label"],
        )
        preset = presets[event_type]
        device_labels = {
            f"{device['device_id']} · {device.get('name') or device['device_id']}": device["device_id"]
            for device in devices
        }
        anchor_device_id = st.selectbox(
            "Serving / anchor device",
            list(device_labels),
            help="This identifies where the event enters the network topology.",
        )
        anchor_device_id = device_labels[anchor_device_id]

        left, right = st.columns(2)
        latitude = left.number_input("Event latitude", min_value=-90.0, max_value=90.0, value=20.1520, format="%.6f")
        longitude = right.number_input("Event longitude", min_value=-180.0, max_value=180.0, value=85.6748, format="%.6f")

        event_name = st.text_input("Event name (optional)", max_chars=80)
        c1, c2, c3 = st.columns(3)
        attendance = c1.slider("Attendance", 1, 500_000, int(preset["attendance"]), step=100)
        radius_hops = c2.slider("Topology impact radius (hops)", 1, 3, int(preset["radius_hops"]))
        duration_min = c3.slider("Duration (minutes)", 15, 720, int(preset["duration_min"]), step=15)

        c4, c5, c6 = st.columns(3)
        capacity_boost_pct = c4.slider("Extra capacity (%)", 0.0, 300.0, 0.0, step=5.0)
        traffic_shaping_pct = c5.slider("Traffic shaping (%)", 0.0, 80.0, 0.0, step=5.0)
        use_live_health = c6.checkbox("Include current device health", value=True)
        submitted = st.form_submit_button("Run event simulation", type="primary", use_container_width=True)

    if submitted:
        scenario = {
            "event_name": event_name or None,
            "event_type": event_type,
            "anchor_device_id": anchor_device_id,
            "latitude": latitude,
            "longitude": longitude,
            "attendance": attendance,
            "radius_hops": radius_hops,
            "duration_min": duration_min,
            "capacity_boost_pct": capacity_boost_pct,
            "traffic_shaping_pct": traffic_shaping_pct,
            "use_live_health": use_live_health,
        }
        try:
            response = requests.post(f"{API_URL}/simulation/run", json=scenario, timeout=60)
            response.raise_for_status()
            st.session_state["event_simulation_result"] = response.json()
        except requests.RequestException as error:
            st.error(f"Event simulation failed: {error}")
            return

    result = st.session_state.get("event_simulation_result")
    if not result:
        st.caption("Choose an event and location, then run the simulation to see predicted impact.")
        return

    summary = result["summary"]
    kpis = st.columns(5)
    kpis[0].metric("Critical", summary["critical"])
    kpis[1].metric("Warning", summary["warning"])
    kpis[2].metric("Knock-on devices", summary["knock_on_devices"])
    kpis[3].metric("Peak network load", f"{summary['peak_network_load_pct']:.1f}%")
    first_critical = summary["first_critical_minute"]
    kpis[4].metric("First overload", f"T+{first_critical} min" if first_critical is not None else "None")

    st.subheader("Animated traffic propagation")
    _render_animation(result, devices)

    impact, actions, timeline = st.tabs(["Device impact", "Recommendations", "Timeline & model"])
    with impact:
        rows = [
            {
                "Severity": row["severity"].title(),
                "Area": row["area"],
                "Device": row["device_id"],
                "Role": row["role"].replace("_", " ").title(),
                "Connection hops": row["connection_hops"],
                "Peak utilization": row["peak_utilization"],
                "Risk estimate": row["risk_probability"],
                "Overload at (min)": row["time_to_overload_min"],
                "Latency (ms)": row["peak_latency_ms"],
                "Packet loss (%)": row["peak_packet_loss_pct"],
            }
            for row in result["devices"]
        ]
        st.dataframe(
            pd.DataFrame(rows),
            hide_index=True,
            use_container_width=True,
            column_config={
                "Peak utilization": st.column_config.ProgressColumn("Peak utilization", format="%.0f%%", min_value=0, max_value=2),
                "Risk estimate": st.column_config.ProgressColumn("Risk estimate", format="%.2f", min_value=0, max_value=1),
            },
        )
        st.caption("Risk estimates are model scores for ranking, not empirically calibrated probabilities.")

    with actions:
        for item in result["recommendations"]:
            deadline = f" · act before T+{item['act_before_min']} min" if item["act_before_min"] is not None else ""
            st.markdown(
                f"**{item['priority'].title()}: {item['title']}{deadline}**  \n"
                f"{item['action']}  \n"
                f"Areas: {', '.join(item['areas']) or 'Network-wide'}"
            )
        effect = result.get("mitigation_effect")
        if effect:
            st.subheader("Mitigation what-if")
            before, after = st.columns(2)
            before.metric("Critical devices before mitigation", effect["critical_before"])
            after.metric("Critical devices after mitigation", effect["critical_after"])
            st.caption(
                f"Peak network load: {effect['peak_load_before_pct']:.1f}% → "
                f"{effect['peak_load_after_pct']:.1f}%."
            )

    with timeline:
        timeline_data = pd.DataFrame(result["timeline"]).set_index("minute")
        st.line_chart(timeline_data[["critical", "warning"]], use_container_width=True)
        st.line_chart(timeline_data[["network_load_pct"]], use_container_width=True)
        st.info(result["model_note"])
        st.download_button(
            "Download simulation result (JSON)",
            json.dumps(result, indent=2),
            file_name="event-simulation.json",
            mime="application/json",
        )

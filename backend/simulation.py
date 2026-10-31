"""Event-impact simulation for NetCoop AI.

Answers the question: "if an event happens *here*, which devices overload, and
which *other* areas will start to see connection problems?"

The model is deliberately high level and deterministic (no randomness) so that
results are reproducible and unit-testable:

1. DIRECT demand   - an operator-selected anchor device represents the event's
                     serving network point; demand falls off by connection hops.
2. SPILLOVER       - an overloaded access device sheds part of its clients onto
                     its nearest neighbours that still have headroom (users
                     roaming to the next AP / switch), which moves the problem
                     to *other areas*.
3. UPSTREAM        - all served traffic is aggregated up the topology tree
                     (access -> switch -> router -> perimeter).  A saturated
                     uplink is a shared bottleneck.
4. COLLATERAL      - devices that carry little traffic themselves but sit behind
                     a saturated uplink still suffer latency / loss.
5. OUTAGE          - (event_type="outage") devices within the configured hop
                     radius (and devices below them) go offline together.

Results are model-based what-if estimates, not calibrated forecasts.
"""
from __future__ import annotations

import json
import math
import re
from collections import defaultdict
from typing import Any

# --------------------------------------------------------------------------- #
# Presets
# --------------------------------------------------------------------------- #
EVENT_PRESETS: dict[str, dict[str, Any]] = {
    "festival": {
        "label": "Cultural fest / concert",
        "description": "Dense crowd, heavy photo/video uploads, short exit surge when it ends.",
        "kind": "surge", "mbps_user": 1.4, "penetration": 0.75, "concurrency": 0.35,
        "ramp_up": 0.25, "plateau_end": 0.80, "exit_spike": 1.35, "spread": 0.6,
        "attendance": 6000, "radius_hops": 2, "duration_min": 240,
    },
    "sports": {
        "label": "Sports match / tournament",
        "description": "Large stand crowd, social media and replays, strong halftime / exit spikes.",
        "kind": "surge", "mbps_user": 1.0, "penetration": 0.80, "concurrency": 0.40,
        "ramp_up": 0.20, "plateau_end": 0.85, "exit_spike": 1.5, "spread": 0.8,
        "attendance": 9000, "radius_hops": 2, "duration_min": 180,
    },
    "livestream": {
        "label": "Convocation / live-streamed ceremony",
        "description": "Sustained high-bitrate streaming by many attendees and remote viewers.",
        "kind": "surge", "mbps_user": 2.8, "penetration": 0.70, "concurrency": 0.50,
        "ramp_up": 0.15, "plateau_end": 0.90, "exit_spike": 1.1, "spread": 0.3,
        "attendance": 3500, "radius_hops": 1, "duration_min": 150,
    },
    "exam": {
        "label": "Online exam / portal rush",
        "description": "Everyone online at once, latency-sensitive, almost no ramp-up.",
        "kind": "surge", "mbps_user": 0.6, "penetration": 0.95, "concurrency": 0.90,
        "ramp_up": 0.05, "plateau_end": 0.95, "exit_spike": 1.0, "spread": 0.15,
        "attendance": 5000, "radius_hops": 2, "duration_min": 120,
    },
    "outage": {
        "label": "Power / fibre outage",
        "description": "Devices inside the radius (and everything below them) go offline; users shift to working devices.",
        "kind": "outage", "mbps_user": 0.9, "penetration": 0.85, "concurrency": 0.40,
        "ramp_up": 0.04, "plateau_end": 0.85, "exit_spike": 1.0, "spread": 0.0,
        "attendance": 2500, "radius_hops": 1, "duration_min": 120,
    },
}

# --------------------------------------------------------------------------- #
# Device model
# --------------------------------------------------------------------------- #
CAPACITY_MBPS = {"access point": 300.0, "switch": 1000.0, "router": 4000.0,
                 "firewall": 3000.0, "gateway": 2500.0, "network device": 1000.0}
BASE_LATENCY_MS = {"access point": 6.0, "switch": 3.0, "router": 2.0,
                   "firewall": 3.0, "gateway": 4.0, "network device": 4.0}
BASE_UTIL = {"access point": 0.20, "switch": 0.18, "network device": 0.20}
TIER = {"gateway": 0, "firewall": 1, "router": 2, "switch": 3, "network device": 3, "access point": 4}
ACCESS_TYPES = {"access point", "switch", "network device"}
PERIMETER_TYPES = {"firewall", "gateway"}

SPILL_RADIUS_HOPS = 3        # maximum topology distance for client spill-over
SPILL_TARGETS = 3            # nearest working devices that share the overflow
SPILL_THRESHOLD = 0.90       # device starts shedding clients above this utilisation
SPILL_FRACTION = 0.60        # share of overflow that roams (rest gives up / is dropped)
SPILL_FRACTION_DOWN = 0.85   # share of an offline device's users that roam
INTERNET_FRACTION = 0.60     # share of campus traffic that crosses firewall / gateway
UPSTREAM_OVERHEAD = 0.08     # management / background load of non-access gear
WARNING_AT = 0.75
CRITICAL_AT = 1.00
MAX_DEVICES = 1500
MAX_FRAMES = 61
SEVERITY_CODE = {"healthy": 0, "warning": 1, "critical": 2}

def _norm_type(value: Any) -> str:
    text = str(value or "").lower().replace("_", " ").replace("-", " ").strip()
    if "access point" in text or text in {"ap", "wifi", "wi fi", "wifi ap", "wireless"}:
        return "access point"
    for key in ("gateway", "firewall", "router", "switch"):
        if key in text:
            return key
    return "network device"


_TYPE_WORDS = re.compile(
    r"\b(wi[- ]?fi\s+access\s+point|access\s+point|switch|router|firewall|gateway)\b", re.I
)


def area_label(name: str, device_id: str) -> str:
    """'Synthetic · Hostel North Wi-Fi Access Point' -> 'Hostel North'."""
    text = str(name or "")
    if "·" in text:
        text = text.split("·", 1)[1]
    cleaned = re.sub(r"\s+", " ", _TYPE_WORDS.sub("", text)).strip(" -·")
    return cleaned or text.strip() or device_id


def _smooth(x: float) -> float:
    x = max(0.0, min(1.0, x))
    return x * x * (3 - 2 * x)


def _neighbors_of(device: dict[str, Any]) -> list[str]:
    raw = device.get("neighbors")
    if raw is None:
        raw = device.get("neighbors_json") or "[]"
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            raw = [item.strip() for item in raw.split(";") if item.strip()]
    return [str(item) for item in raw] if isinstance(raw, list) else []


# --------------------------------------------------------------------------- #
# Scenario resolution
# --------------------------------------------------------------------------- #
def resolve_scenario(raw: dict[str, Any], devices: list[dict[str, Any]]) -> dict[str, Any]:
    event_type = raw.get("event_type") or "festival"
    if event_type not in EVENT_PRESETS:
        raise ValueError(f"Unknown event_type '{event_type}'. Choose one of: {', '.join(EVENT_PRESETS)}")
    preset = EVENT_PRESETS[event_type]
    anchor_device_id = str(raw.get("anchor_device_id") or "")
    device_ids = {str(device["device_id"]) for device in devices}
    if anchor_device_id not in device_ids:
        raise ValueError(f"Unknown anchor_device_id '{anchor_device_id}'.")
    latitude, longitude = raw.get("latitude"), raw.get("longitude")
    if (latitude is None) != (longitude is None):
        raise ValueError("Event latitude and longitude must be provided together.")

    def pick(key: str) -> Any:
        value = raw.get(key)
        return preset[key] if value is None else value

    return {
        "event_name": raw.get("event_name") or preset["label"],
        "event_type": event_type,
        "event_label": preset["label"],
        "kind": preset["kind"],
        "anchor_device_id": anchor_device_id,
        "latitude": float(latitude) if latitude is not None else None,
        "longitude": float(longitude) if longitude is not None else None,
        "attendance": int(pick("attendance")),
        "radius_hops": int(raw.get("radius_hops") or preset["radius_hops"]),
        "duration_min": int(pick("duration_min")),
        "capacity_boost_pct": float(raw.get("capacity_boost_pct") or 0),
        "traffic_shaping_pct": float(raw.get("traffic_shaping_pct") or 0),
        "use_live_health": bool(raw.get("use_live_health", True)),
        **{key: preset[key] for key in (
            "mbps_user", "penetration", "concurrency", "ramp_up", "plateau_end", "exit_spike", "spread")},
    }


def _profile(tau: float, sc: dict[str, Any]) -> tuple[float, float, float]:
    """Return (presence 0..1+, concurrency multiplier, dispersal 0..1) at tau = minute / duration."""
    ramp, end = sc["ramp_up"], sc["plateau_end"]
    if tau < 0:
        return 0.0, 1.0, 0.0
    if tau < ramp:
        presence = 0.10 + 0.90 * _smooth(tau / ramp)
    elif tau <= end:
        presence = 1.0 + 0.05 * math.sin(tau * 18.0)
    elif tau <= end + 0.35:
        presence = 1.0 - 0.85 * _smooth((tau - end) / 0.35)
    else:
        presence = 0.10
    spike = 1.0
    if end < tau <= end + 0.14:
        spike = 1.0 + (sc["exit_spike"] - 1.0) * math.sin(math.pi * (tau - end) / 0.14)
    dispersal = _smooth((tau - end) / 0.30) if tau > end else 0.0
    return presence, spike, dispersal


# --------------------------------------------------------------------------- #
# Topology
# --------------------------------------------------------------------------- #
class _Network:
    def __init__(self, devices: list[dict[str, Any]], sc: dict[str, Any]) -> None:
        self.sc = sc
        self.nodes: dict[str, dict[str, Any]] = {}
        for device in devices:
            kind = _norm_type(device.get("device_type"))
            did = str(device["device_id"])
            node = {
                "id": did,
                "name": str(device.get("name") or did),
                "area": area_label(device.get("name") or did, did),
                "type": kind,
                "tier": TIER[kind], "cap": CAPACITY_MBPS[kind],
                "status": str(device.get("status") or "unknown"),
                "neighbors": _neighbors_of(device),
            }
            self.nodes[did] = node
        if len(self.nodes) > MAX_DEVICES:
            raise ValueError(f"Simulation supports up to {MAX_DEVICES} devices (got {len(self.nodes)}).")

        self.access = [n for n in self.nodes.values() if n["type"] in ACCESS_TYPES]
        if not self.access:
            self.access = list(self.nodes.values())
        self.access_ids = sorted(n["id"] for n in self.access)
        access_set = set(self.access_ids)

        for node in self.nodes.values():
            node["access"] = node["id"] in access_set
            base = BASE_UTIL.get(node["type"], UPSTREAM_OVERHEAD)
            if node["access"] and sc["use_live_health"]:
                base += {"warning": 0.25, "critical": 0.45}.get(node["status"], 0.0)
            node["base_load"] = min(base, 0.9) * node["cap"]

        self._build_graph()
        if sc["anchor_device_id"] not in self.nodes:
            raise ValueError(f"Unknown anchor_device_id '{sc['anchor_device_id']}'.")
        self.event_hops = self._distances(sc["anchor_device_id"])
        self._build_spill_neighbors()
        self.down: set[str] = set()
        if sc["kind"] == "outage":
            self.down = {
                device_id
                for device_id, hops in self.event_hops.items()
                if hops <= sc["radius_hops"]
            }
            for node_id in self.order_asc:  # a device behind a dead parent is isolated too
                parent = self.parent.get(node_id)
                if parent in self.down:
                    self.down.add(node_id)

        boost = 1 + sc["capacity_boost_pct"] / 100.0
        self.cap_eff = {}
        for node in self.nodes.values():
            if node["id"] in self.down:
                self.cap_eff[node["id"]] = 0.0
            elif node["access"] and self.event_hops.get(node["id"], 999) <= sc["radius_hops"]:
                self.cap_eff[node["id"]] = node["cap"] * boost
            else:
                self.cap_eff[node["id"]] = node["cap"]

    # -- graph ------------------------------------------------------------- #
    def _build_graph(self) -> None:
        adj: dict[str, set[str]] = {i: set() for i in self.nodes}
        for node in self.nodes.values():
            for other in node["neighbors"]:
                if other in adj and other != node["id"]:
                    adj[node["id"]].add(other)
                    adj[other].add(node["id"])
        components = self._components(adj)
        self.inferred_links: list[tuple[str, str]] = []
        self.adj = adj

        roots = []
        for component in components:
            lowest = min(self.nodes[device_id]["tier"] for device_id in component)
            roots.extend(
                device_id
                for device_id in component
                if self.nodes[device_id]["tier"] == lowest
            )
        roots.sort()
        depth = {r: 0 for r in roots}
        frontier = list(roots)
        while frontier:
            nxt = []
            for cur in frontier:
                for other in sorted(adj[cur]):
                    if other not in depth:
                        depth[other] = depth[cur] + 1
                        nxt.append(other)
            frontier = nxt
        self.depth = depth
        self.parent: dict[str, str | None] = {}
        for node_id in self.nodes:
            if node_id in roots:
                self.parent[node_id] = None
                continue
            candidates = [o for o in adj[node_id] if depth[o] == depth[node_id] - 1]
            candidates.sort(key=lambda o: (self.nodes[o]["tier"], o))
            self.parent[node_id] = candidates[0] if candidates else None
        self.order_asc = sorted(self.nodes, key=lambda i: (depth[i], i))
        self.order_desc = list(reversed(self.order_asc))
        self.children: dict[str, list[str]] = defaultdict(list)
        for child, parent in self.parent.items():
            if parent:
                self.children[parent].append(child)

    @staticmethod
    def _components(adj: dict[str, set[str]]) -> list[list[str]]:
        seen: set[str] = set()
        groups = []
        for start in sorted(adj):
            if start in seen:
                continue
            stack, group = [start], []
            seen.add(start)
            while stack:
                cur = stack.pop()
                group.append(cur)
                for other in adj[cur]:
                    if other not in seen:
                        seen.add(other)
                        stack.append(other)
            groups.append(group)
        return groups

    def _build_spill_neighbors(self) -> None:
        self.spill_nbrs: dict[str, list[tuple[str, int]]] = {}
        for a in self.access:
            distances = self._distances(a["id"])
            near = [
                (hops, device_id)
                for device_id, hops in distances.items()
                if device_id != a["id"]
                and self.nodes[device_id]["access"]
                and hops <= SPILL_RADIUS_HOPS
            ]
            near.sort()
            self.spill_nbrs[a["id"]] = [
                (device_id, hops) for hops, device_id in near[:8]
            ]

    def _distances(self, start: str) -> dict[str, int]:
        if start not in self.adj:
            return {}
        distances = {start: 0}
        frontier = [start]
        while frontier:
            current = frontier.pop(0)
            for neighbor in sorted(self.adj[current]):
                if neighbor not in distances:
                    distances[neighbor] = distances[current] + 1
                    frontier.append(neighbor)
        return distances

    def descendants(self, node_id: str) -> int:
        stack, count = list(self.children.get(node_id, [])), 0
        while stack:
            cur = stack.pop()
            count += 1
            stack.extend(self.children.get(cur, []))
        return count

    # -- one time step ----------------------------------------------------- #
    def step(self, minute: int) -> dict[str, Any]:
        sc = self.sc
        presence, spike, dispersal = _profile(minute / sc["duration_min"], sc)
        scope_hops = min(
            3,
            sc["radius_hops"] + (1 if dispersal > 0 and sc["spread"] > 0 else 0),
        )
        weights = {
            n["id"]: math.exp(
                -((self.event_hops.get(n["id"], 999) / max(scope_hops, 1)) ** 2)
            )
            for n in self.access
            if self.event_hops.get(n["id"], 999) <= scope_hops
        }
        denom = max(sum(weights.values()), 1.0)
        per_user = sc["mbps_user"] * (1 - sc["traffic_shaping_pct"] / 100.0)
        total_event = sc["attendance"] * presence * sc["penetration"] * sc["concurrency"] * spike * per_user

        event = {
            device_id: total_event * weights.get(device_id, 0.0) / denom
            for device_id in self.access_ids
        }
        local = {i: self.nodes[i]["base_load"] + event[i] for i in self.access_ids}
        current = dict(local)
        received: dict[str, float] = defaultdict(float)
        dropped: dict[str, float] = defaultdict(float)
        flows: dict[tuple[str, str], float] = defaultdict(float)
        shed_down: set[str] = set()

        if sc["kind"] == "outage":
            for node_id in sorted(self.down):
                if node_id not in self.access_ids:
                    continue
                excess = max(current[node_id], 0.0)
                if excess <= 1e-6:
                    continue
                targets = [(i, d) for i, d in self.spill_nbrs.get(node_id, []) if i not in self.down][:SPILL_TARGETS]
                if not targets:
                    dropped[node_id] += excess
                    current[node_id] = 0.0
                    continue
                shares = [
                    (i, (1.0 / (d + 0.05)) * max(0.05, 1.0 - current[i] / max(self.cap_eff[i], 1e-9)))
                    for i, d in targets
                ]
                total_share = sum(s for _, s in shares)
                moved = min(excess, SPILL_FRACTION_DOWN * excess)
                for target, share in shares:
                    amount = moved * share / total_share if total_share else 0.0
                    current[target] += amount
                    received[target] += amount
                    flows[(node_id, target)] += amount
                dropped[node_id] += excess - moved
                current[node_id] = 0.0

        for _ in range(4):
            changed = False
            for node_id in self.access_ids:
                cap = self.cap_eff[node_id]
                if node_id in self.down:
                    if node_id in shed_down:
                        continue
                    shed_down.add(node_id)
                    surplus, fraction = current[node_id], SPILL_FRACTION_DOWN
                else:
                    surplus, fraction = current[node_id] - SPILL_THRESHOLD * cap, SPILL_FRACTION
                    if surplus <= 1e-6:
                        continue
                targets = [(i, d) for i, d in self.spill_nbrs.get(node_id, []) if i not in self.down][:SPILL_TARGETS]
                if not targets:
                    if node_id in self.down:
                        dropped[node_id] += surplus
                        current[node_id] = 0.0
                    continue
                shares = [
                    (i, (1.0 / (d + 0.05)) * max(0.05, 1.0 - current[i] / max(self.cap_eff[i], 1e-9)))
                    for i, d in targets
                ]
                total_share = sum(s for _, s in shares)
                moved = fraction * surplus
                for target, share in shares:
                    amount = moved * share / total_share if total_share else 0.0
                    current[target] += amount
                    received[target] += amount
                    flows[(node_id, target)] += amount
                dropped[node_id] += surplus - moved
                current[node_id] -= surplus
                changed = True
            if not changed:
                break

        served = {i: min(current[i], self.cap_eff[i]) for i in self.access_ids}
        offered = {i: local[i] + received[i] for i in self.access_ids}

        agg = {i: (served.get(i, 0.0) if self.nodes[i]["access"] else UPSTREAM_OVERHEAD * self.nodes[i]["cap"])
               for i in self.nodes}
        total_served = sum(served.values())
        for node_id in self.order_desc:
            node = self.nodes[node_id]
            if node["type"] in PERIMETER_TYPES:
                agg[node_id] = UPSTREAM_OVERHEAD * node["cap"] + INTERNET_FRACTION * total_served
            parent = self.parent.get(node_id)
            if parent and node["type"] not in PERIMETER_TYPES:  # perimeter boxes are parallel, not in the data path
                agg[parent] += agg[node_id]

        rho_own: dict[str, float] = {}
        for node_id, node in self.nodes.items():
            cap = self.cap_eff[node_id]
            if node_id in self.down or cap <= 0:
                rho_own[node_id] = 2.0
            elif node["access"]:  # own clients, or own clients + devices hanging below it
                rho_own[node_id] = max(offered[node_id], agg[node_id]) / cap
            else:
                rho_own[node_id] = agg[node_id] / cap

        path_pressure: dict[str, float] = {}
        anc_max: dict[str, float] = {}
        for node_id in self.order_asc:
            parent = self.parent.get(node_id)
            if parent is None:
                anc_max[node_id] = 0.0
            else:
                anc_max[node_id] = max(anc_max[parent], min(rho_own[parent], 1.4) if parent not in self.down else 0.0)
            path_pressure[node_id] = 0.85 * anc_max[node_id]

        rho_eff = {i: (2.0 if i in self.down else min(2.0, max(rho_own[i], path_pressure[i]))) for i in self.nodes}
        return {
            "minute": minute, "presence": presence, "event": event, "local": local, "received": dict(received),
            "offered": offered, "served": served, "agg": agg, "rho_own": rho_own, "path": path_pressure,
            "rho_eff": rho_eff, "flows": dict(flows), "dropped": sum(dropped.values()),
            "load_pct": 100.0 * sum(offered.values()) / max(sum(self.cap_eff[i] for i in self.access_ids), 1e-9),
        }


# --------------------------------------------------------------------------- #
# Metrics helpers
# --------------------------------------------------------------------------- #
def _severity(rho: float) -> str:
    return "critical" if rho >= CRITICAL_AT else ("warning" if rho >= WARNING_AT else "healthy")


def _risk(rho: float) -> float:
    return round(1.0 / (1.0 + math.exp(-7.0 * (rho - 0.8))), 3)


def _latency_ms(base: float, rho: float) -> float:
    if rho < 0.95:
        value = base / (1.0 - rho)
    else:
        value = base * 20.0 * (1.0 + (rho - 0.95) * 10.0)
    return round(min(value, 1500.0), 1)


def _loss_pct(rho: float) -> float:
    return round(min(35.0, max(0.0, rho - 0.85) * 45.0), 2)


def _frame_minutes(duration: int) -> list[int]:
    total = int(duration * 1.45)
    step = max(5, math.ceil(total / (MAX_FRAMES - 1) / 5) * 5)
    return list(range(0, total + 1, step))


def _simulate(devices: list[dict[str, Any]], sc: dict[str, Any]) -> tuple[_Network, list[dict[str, Any]]]:
    net = _Network(devices, sc)
    return net, [net.step(m) for m in _frame_minutes(sc["duration_min"])]


def _summary(net: _Network, steps: list[dict[str, Any]]) -> dict[str, Any]:
    peak_rho = {i: max(s["rho_eff"][i] for s in steps) for i in net.nodes}
    counts = {"critical": 0, "warning": 0, "healthy": 0}
    for rho in peak_rho.values():
        counts[_severity(rho)] += 1
    worst_step = max(steps, key=lambda s: (sum(1 for r in s["rho_eff"].values() if r >= CRITICAL_AT), s["load_pct"]))
    return {**counts, "devices": len(net.nodes), "peak_minute": worst_step["minute"],
            "peak_network_load_pct": round(max(s["load_pct"] for s in steps), 1)}


# --------------------------------------------------------------------------- #
# Public entry point
# --------------------------------------------------------------------------- #
def run_simulation(devices: list[dict[str, Any]], raw_scenario: dict[str, Any]) -> dict[str, Any]:
    if not devices:
        raise ValueError("No devices are available to simulate.")
    sc = resolve_scenario(raw_scenario, devices)
    net, steps = _simulate(devices, sc)

    records: dict[str, dict[str, Any]] = {}
    for node_id, node in net.nodes.items():
        series = [s["rho_eff"][node_id] for s in steps]
        peak_index = max(range(len(series)), key=lambda k: series[k])
        peak = steps[peak_index]
        rho = series[peak_index]
        own, path = peak["rho_own"][node_id], peak["path"][node_id]
        offered = peak["offered"].get(node_id, 0.0)
        event_mbps = peak["event"].get(node_id, 0.0)
        received = peak["received"].get(node_id, 0.0)
        sources = sorted(
            ((flow, s_id) for (s_id, t_id), flow in peak["flows"].items() if t_id == node_id), reverse=True
        )[:2]
        parent = net.parent.get(node_id)

        if node_id in net.down:
            role = "offline"
        elif not node["access"] or node["type"] in PERIMETER_TYPES:
            role = "upstream" if own >= 0.5 and own >= path else ("collateral" if path >= WARNING_AT else "unaffected")
        elif offered > 0 and event_mbps / offered >= 0.5 and rho >= 0.6:
            role = "direct"
        elif sc["kind"] == "outage" and node["access"] and node_id not in net.down and path >= 0.10:
            role = "spillover"
        elif received > 0 and node["access"] and rho >= 0.55:
            role = "spillover"
        elif offered > 0 and received / offered >= 0.3 and rho >= 0.6:
            role = "spillover"
        elif path >= WARNING_AT and path >= 0.9 * own:
            role = "collateral"
        elif rho >= 0.6:
            role = "direct"
        else:
            role = "unaffected"

        first = lambda threshold: next((s["minute"] for s, r in zip(steps, series) if r >= threshold), None)  # noqa: E731
        reasons: list[str] = []
        hops_from_anchor = net.event_hops.get(node_id, 999)
        if hops_from_anchor is None:
            hops_from_anchor = 999
        if role == "offline":
            reasons.append(
                f"Within {sc['radius_hops']} topology hop(s) of the event anchor "
                "or downstream of an unavailable device."
            )
        if role == "direct":
            reasons.append(
                f"Crowd demand ~{event_mbps:.0f} Mbps at {hops_from_anchor} connection hop(s) "
                f"from the event anchor ({own:.0%} of {net.cap_eff[node_id]:.0f} Mbps capacity)."
            )
        if received > 1 and role in {"spillover", "direct", "upstream"}:
            names = ", ".join(net.nodes[s_id]["area"] for _, s_id in sources)
            reasons.append(f"Receives ~{received:.0f} Mbps of clients displaced from {names}.")
        if role == "upstream":
            reasons.append(f"Aggregates ~{peak['agg'][node_id]:.0f} Mbps from {net.descendants(node_id)} downstream device(s) "
                           f"({own:.0%} of capacity).")
        if role == "collateral" and parent:
            reasons.append(f"Own load is only {min(own, 9.99):.0%}, but its uplink via {net.nodes[parent]['area']} is saturated "
                           f"(path pressure {path:.0%}).")
        if not reasons:
            reasons.append("No material impact predicted.")

        actions = {
            "offline": "Dispatch field team / restore power or fibre; confirm users roamed to neighbouring devices.",
            "direct": "Pre-deploy temporary APs / uplinks near this spot, enable band-steering and client rate limits before the event starts.",
            "spillover": "Pre-balance clients: raise neighbour capacity, lower sticky-client thresholds and watch this device as an early-warning signal.",
            "upstream": "Add uplink capacity or QoS-shape the event VLAN/SSID; verify ECMP / LAG headroom on this device.",
            "collateral": "Protect critical traffic with QoS priority; relieve the saturated uplink upstream rather than this device.",
            "unaffected": "No action needed.",
        }
        records[node_id] = {
            "device_id": node_id, "name": node["name"], "area": node["area"], "device_type": node["type"],
            "connection_hops": hops_from_anchor,
            "role": role, "severity": _severity(rho), "peak_utilization": round(rho, 3),
            "peak_minute": peak["minute"], "risk_probability": _risk(rho),
            "time_to_warning_min": first(WARNING_AT), "time_to_overload_min": first(CRITICAL_AT),
            "baseline_utilization": round(node["base_load"] / node["cap"], 3),
            "capacity_mbps": round(net.cap_eff[node_id], 1),
            "peak_latency_ms": _latency_ms(BASE_LATENCY_MS[node["type"]], rho),
            "peak_packet_loss_pct": 100.0 if node_id in net.down else _loss_pct(rho),
            "spill_received_mbps": round(received, 1), "event_demand_mbps": round(event_mbps, 1),
            "reasons": reasons, "recommended_action": actions[role],
        }

    ranked = sorted(records.values(), key=lambda r: (-SEVERITY_CODE[r["severity"]], -r["peak_utilization"]))
    summary = _summary(net, steps)
    summary.update({
        "epicentre_area": net.nodes[sc["anchor_device_id"]]["area"],
        "first_critical_minute": min((r["time_to_overload_min"] for r in records.values()
                                      if r["time_to_overload_min"] is not None), default=None),
        "knock_on_devices": sum(1 for r in records.values()
                                if r["role"] in {"spillover", "collateral", "upstream"} and r["severity"] != "healthy"),
        "dropped_mbps_peak": round(max(s["dropped"] for s in steps), 1),
        "roles": {role: sum(1 for r in records.values() if r["role"] == role)
                  for role in ("direct", "spillover", "upstream", "collateral", "offline", "unaffected")},
    })

    # spill flows (top 12 by peak volume) with per-frame series for animation
    peak_flow: dict[tuple[str, str], float] = defaultdict(float)
    for s in steps:
        for key, value in s["flows"].items():
            peak_flow[key] = max(peak_flow[key], value)
    top_flows = sorted(peak_flow.items(), key=lambda kv: -kv[1])[:12]
    spill_flows = [
        {"from": a, "to": b, "peak_mbps": round(v, 1), "series": [round(s["flows"].get((a, b), 0.0), 1) for s in steps]}
        for (a, b), v in top_flows if v >= 1
    ]

    rings = []
    for hops in range(0, 4):
        group = [r for r in records.values() if r["connection_hops"] == hops]
        if group:
            rings.append({
                "label": "Event anchor" if hops == 0 else f"{hops} hop(s)",
                "devices": len(group),
                "critical": sum(r["severity"] == "critical" for r in group),
                "warning": sum(r["severity"] == "warning" for r in group),
                "avg_risk": round(sum(r["risk_probability"] for r in group) / len(group), 3),
            })

    timeline = []
    for s in steps:
        values = list(s["rho_eff"].values())
        timeline.append({
            "minute": s["minute"], "presence": round(s["presence"], 3), "network_load_pct": round(s["load_pct"], 1),
            "critical": sum(v >= CRITICAL_AT for v in values),
            "warning": sum(WARNING_AT <= v < CRITICAL_AT for v in values),
            "healthy": sum(v < WARNING_AT for v in values),
        })

    frames = {
        "minutes": [s["minute"] for s in steps],
        "utilization": {i: [round(s["rho_eff"][i], 2) for s in steps] for i in net.nodes},
        "severity": {i: [SEVERITY_CODE[_severity(s["rho_eff"][i])] for s in steps] for i in net.nodes},
    }

    result = {
        "scenario": sc,
        "summary": summary,
        "devices": ranked,
        "timeline": timeline,
        "frames": frames,
        "spill_flows": spill_flows,
        "rings": rings,
        "links": sorted({(a, b) if a < b else (b, a) for a, nbrs in net.adj.items() for b in nbrs}),
        "inferred_links": [list(pair) for pair in net.inferred_links],
        "recommendations": _recommendations(records, summary),
        "model_note": ("Deterministic what-if model (topology-hop crowd demand, neighbour spillover, shared-uplink saturation). "
                       "Capacities and per-user rates are planning assumptions, not measurements; treat results as a ranking of "
                       "likely trouble spots rather than calibrated forecasts. Event coordinates are recorded as context only; "
                       "the operator-selected anchor device determines topology impact."),
    }
    if sc["capacity_boost_pct"] > 0 or sc["traffic_shaping_pct"] > 0:
        plain = {**sc, "capacity_boost_pct": 0.0, "traffic_shaping_pct": 0.0}
        before_net, before_steps = _simulate(devices, plain)
        before = _summary(before_net, before_steps)
        result["mitigation_effect"] = {
            "critical_before": before["critical"], "critical_after": summary["critical"],
            "warning_before": before["warning"], "warning_after": summary["warning"],
            "peak_load_before_pct": before["peak_network_load_pct"], "peak_load_after_pct": summary["peak_network_load_pct"],
        }
    return result


def _recommendations(records: dict[str, dict[str, Any]], summary: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []

    def group(role: str) -> list[dict[str, Any]]:
        return sorted((r for r in records.values() if r["role"] == role and r["severity"] != "healthy"),
                      key=lambda r: -r["peak_utilization"])

    def lead(items: list[dict[str, Any]]) -> int | None:
        times = [r["time_to_overload_min"] if r["time_to_overload_min"] is not None else r["time_to_warning_min"] for r in items]
        times = [t for t in times if t is not None]
        return min(times) if times else None

    direct, spill, upstream, collateral, offline = (group(r) for r in ("direct", "spillover", "upstream", "collateral", "offline"))
    if offline:
        out.append({"priority": "critical", "title": "Restore offline devices", "areas": [r["area"] for r in offline[:5]],
                    "action": "Dispatch field team and verify power / fibre. Users have been redistributed to neighbouring devices.",
                    "act_before_min": 0})
    if direct:
        extra = max(1, math.ceil(sum(r["event_demand_mbps"] for r in direct) / (0.7 * 300)) - len(direct))
        out.append({"priority": "critical" if any(r["severity"] == "critical" for r in direct) else "warning",
                    "title": "Reinforce the epicentre", "areas": [r["area"] for r in direct[:5]],
                    "action": f"Pre-deploy ~{extra} temporary access point(s)/uplink(s) around the venue and enable client rate limits.",
                    "act_before_min": lead(direct)})
    if spill:
        out.append({"priority": "warning", "title": "Watch the knock-on areas", "areas": [r["area"] for r in spill[:5]],
                    "action": "These areas absorb roaming clients from overloaded neighbours - raise capacity or lower sticky-client thresholds.",
                    "act_before_min": lead(spill)})
    if upstream:
        out.append({"priority": "critical" if any(r["severity"] == "critical" for r in upstream) else "warning",
                    "title": "Relieve shared uplinks", "areas": [r["area"] for r in upstream[:5]],
                    "action": "Aggregated event traffic is stressing these devices - add LAG/ECMP capacity or shape the event SSID/VLAN.",
                    "act_before_min": lead(upstream)})
    if collateral:
        out.append({"priority": "warning", "title": "Protect bystander areas", "areas": [r["area"] for r in collateral[:5]],
                    "action": "These areas are not near the event but share a saturated uplink - prioritise critical services with QoS.",
                    "act_before_min": lead(collateral)})
    if not out:
        out.append({"priority": "info", "title": "No action needed", "areas": [],
                    "action": "The network is predicted to absorb this event without service degradation.", "act_before_min": None})
    return out

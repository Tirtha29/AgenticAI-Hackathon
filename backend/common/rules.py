from typing import Any

BASE_RULES = [
    {
        "id": "HW-01",
        "cause": "Device hardware failure or CPU saturation",
        "required": {"cpu_utilization_pct": 95},
        "alternatives": (("packet_loss_pct", 10), ("interface_errors", 100)),
        "probability": 0.96,
        "action": "Check control-plane load and hardware alarms; validate interface health, then use a tested failover plan.",
    },
    {
        "id": "PHY-01",
        "cause": "Physical link, optic, or cabling fault",
        "required": {"interface_errors": 100, "packet_loss_pct": 10},
        "probability": 0.97,
        "action": "Inspect optics, cabling, CRC counters, and both ends of the link before replacing hardware.",
    },
    {
        "id": "NET-01",
        "cause": "Link congestion or QoS queue saturation",
        "required": {"link_utilization_pct": 80, "latency_ms": 100, "packet_loss_pct": 1},
        "probability": 0.93,
        "action": "Review top talkers and QoS queues; validate an alternate route or capacity change.",
    },
    {
        "id": "ROUTE-01",
        "cause": "Unstable route or degraded network path",
        "required": {"latency_ms": 100, "jitter_ms": 20, "packet_loss_pct": 0.1},
        "probability": 0.91,
        "action": "Compare hop-by-hop latency, routing changes, and path stability; confirm before rerouting.",
    },
    {
        "id": "HW-02",
        "cause": "CPU and memory resource exhaustion",
        "required": {"cpu_utilization_pct": 90, "memory_utilization_pct": 95},
        "probability": 0.94,
        "action": "Inspect process and memory-pool utilization, identify leaks or runaway tasks, and validate failover capacity.",
    },
    {
        "id": "NET-02",
        "cause": "Queue saturation during high link utilization",
        "required": {"link_utilization_pct": 90, "queue_drops": 100},
        "probability": 0.94,
        "action": "Inspect queue occupancy and QoS class counters; identify burst sources before making a capacity or policy change.",
    },
    {
        "id": "PHY-02",
        "cause": "Degraded physical interface causing packet loss",
        "required": {"interface_errors": 50, "packet_loss_pct": 1},
        "probability": 0.95,
        "action": "Compare both link ends, inspect CRC and optic diagnostics, and validate cabling before replacing components.",
    },
    {
        "id": "QOS-01",
        "cause": "Queueing or QoS instability",
        "required": {"jitter_ms": 50, "queue_drops": 100},
        "probability": 0.92,
        "action": "Compare jitter and drops by QoS class; verify shaping and scheduling against the approved policy.",
    },
    {
        "id": "THERMAL-01",
        "cause": "Thermal stress contributing to device degradation",
        "required": {"temperature_c": 80, "cpu_utilization_pct": 80},
        "probability": 0.91,
        "action": "Check fan and airflow alarms, rack temperature, and device load; follow the vendor-approved thermal recovery procedure.",
    },
    {
        "id": "PATH-02",
        "cause": "Congestion-related path delay and packet loss",
        "required": {"latency_ms": 250, "packet_loss_pct": 1},
        "probability": 0.92,
        "action": "Compare hop-level delay, loss, and queue counters to isolate the congested segment before rerouting.",
    },
    {
        "id": "HW-03",
        "cause": "Hardware or interface fault under CPU saturation",
        "required": {"cpu_utilization_pct": 95, "interface_errors": 50},
        "probability": 0.93,
        "action": "Correlate control-plane load with interface and hardware alarms; use only a tested failover plan.",
    },
]

CAUSE_RULES = [
    ("High CPU utilization", "cpu_utilization_pct", 80, "Inspect process load, control-plane activity, and recent configuration changes."),
    ("CPU saturation", "cpu_utilization_pct", 95, "Check runaway processes or a device hardware fault; consider controlled failover."),
    ("High memory utilization", "memory_utilization_pct", 85, "Inspect memory pools, leaks, and session growth."),
    ("Link congestion", "link_utilization_pct", 80, "Review top talkers and QoS; consider rerouting or increasing link capacity."),
    ("Elevated packet loss", "packet_loss_pct", 1, "Check physical errors, congestion, duplex, and the adjacent hop."),
    ("High latency", "latency_ms", 100, "Compare hop-by-hop latency and queue depth; inspect congestion and routing changes."),
    ("High jitter", "jitter_ms", 20, "Inspect queueing, QoS policy, and path stability."),
    ("Queue congestion or buffer pressure", "queue_drops", 50, "Review queue occupancy, QoS classes, and burst traffic."),
    ("Interface or physical-layer errors", "interface_errors", 10, "Check optics, cabling, CRC counters, and interface negotiation at both ends."),
    ("Device overheating", "temperature_c", 70, "Check airflow, fan status, and rack temperature."),
    ("Unusual firewall denial volume", "firewall_drops", 100, "Review firewall policy changes and correlate denied traffic with approved change records."),
    ("Sustained high CPU pressure", "cpu_utilization_pct", 90, "Check process-level CPU, control-plane queues, and recent changes; confirm capacity before failover."),
    ("Critical memory pressure", "memory_utilization_pct", 95, "Inspect memory pools, process growth, and allocation failures; preserve diagnostics before restart."),
    ("Severe link saturation", "link_utilization_pct", 90, "Compare utilization by interface and direction, identify top talkers, and validate QoS/capacity options."),
    ("Persistent packet loss", "packet_loss_pct", 0.5, "Compare loss across adjacent hops and inspect interface errors, congestion, and optical diagnostics."),
    ("Severe end-to-end delay", "latency_ms", 250, "Use hop-by-hop measurements to distinguish queueing, routing, and remote endpoint delay."),
    ("Severe delay variation", "jitter_ms", 50, "Inspect queueing and QoS class behavior; compare path and application measurements."),
    ("Severe packet queue drops", "queue_drops", 500, "Review queue depth, tail-drop counters, burst traffic, and QoS class configuration."),
    ("High interface error rate", "interface_errors", 50, "Compare error counters at both ends and inspect optics, cabling, CRC, and interface negotiation."),
    ("Critical device temperature", "temperature_c", 80, "Check fan alarms, airflow, rack conditions, and vendor thermal alerts; avoid unplanned power cycles."),
    ("Extreme firewall deny volume", "firewall_drops", 500, "Correlate deny spikes with approved policy changes and security alerts before modifying firewall rules."),
    ("Near-capacity measured throughput", "bandwidth_mbps", 95000, "Compare throughput with interface capacity and utilization counters; verify whether this is expected peak traffic."),
]
DEVICE_ROLES = ("switch", "router", "access point", "firewall", "gateway", "network device")
VENDOR_CONTEXTS = tuple(f"profile-{index:02d}" for index in range(1, 21))


def build_fact_catalog() -> list[dict[str, Any]]:
    return [
        {
            "fact_id": f"NET-{index:02d}-{role.replace(' ', '-')}-{vendor}",
            "cause": cause,
            "metric": metric,
            "threshold": threshold,
            "action": action,
            "device_role": role,
            "vendor_context": vendor,
        }
        for index, (cause, metric, threshold, action) in enumerate(CAUSE_RULES, 1)
        for role in DEVICE_ROLES
        for vendor in VENDOR_CONTEXTS
    ]


FACT_CATALOG = build_fact_catalog()

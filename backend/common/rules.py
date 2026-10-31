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

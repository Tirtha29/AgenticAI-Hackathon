from backend.common.classes.performance import NormalRange

METRIC_UNITS = {
    "cpu_utilization_pct": "%",
    "memory_utilization_pct": "%",
    "link_utilization_pct": "%",
    "packet_loss_pct": "%",
    "latency_ms": "ms",
    "jitter_ms": "ms",
    "queue_drops": "packets",
    "interface_errors": "errors",
    "temperature_c": "°C",
    "firewall_drops": "events",
    "bandwidth_mbps": "Mbps",
}

ACCEPTED_UNITS = {
    "cpu_utilization_pct": {"%": 1.0, "fraction": 100.0},
    "memory_utilization_pct": {"%": 1.0, "fraction": 100.0},
    "link_utilization_pct": {"%": 1.0, "fraction": 100.0},
    "packet_loss_pct": {"%": 1.0},
    "latency_ms": {"ms": 1.0, "s": 1000.0, "us": 0.001},
    "jitter_ms": {"ms": 1.0, "s": 1000.0, "us": 0.001},
    "queue_drops": {"packets": 1.0, "count": 1.0},
    "interface_errors": {"errors": 1.0, "count": 1.0},
    "temperature_c": {"°C": 1.0, "C": 1.0},
    "firewall_drops": {"events": 1.0, "count": 1.0},
    "bandwidth_mbps": {"Mbps": 1.0, "Gbps": 1000.0, "Kbps": 0.001, "bps": 0.000001},
}

METRIC_ALIASES = {
    "cpu_utilization": "cpu_utilization_pct",
    "memory_utilization": "memory_utilization_pct",
    "link_utilization": "link_utilization_pct",
    "latency_s": "latency_ms",
    "jitter_s": "jitter_ms",
    "temperature": "temperature_c",
    "bandwidth": "bandwidth_mbps",
    "throughput": "bandwidth_mbps",
    "link_speed": "bandwidth_mbps",
}

NORMAL_RANGES: dict[str, NormalRange] = {
    "cpu_utilization_pct": NormalRange(minimum=0, maximum=80, unit="%"),
    "memory_utilization_pct": NormalRange(minimum=0, maximum=85, unit="%"),
    "link_utilization_pct": NormalRange(minimum=0, maximum=80, unit="%"),
    "packet_loss_pct": NormalRange(minimum=0, maximum=0.1, unit="%"),
    "latency_ms": NormalRange(minimum=0, maximum=100, unit="ms"),
    "jitter_ms": NormalRange(minimum=0, maximum=20, unit="ms"),
    "queue_drops": NormalRange(minimum=0, maximum=50, unit="packets"),
    "interface_errors": NormalRange(minimum=0, maximum=10, unit="errors"),
    "temperature_c": NormalRange(minimum=0, maximum=70, unit="°C"),
    "firewall_drops": NormalRange(minimum=0, maximum=100, unit="events"),
    "bandwidth_mbps": NormalRange(minimum=100, maximum=100000, unit="Mbps"),
}

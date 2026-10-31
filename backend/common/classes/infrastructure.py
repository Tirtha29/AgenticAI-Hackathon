from backend.common.classes.base import StrictModel
from backend.common.classes.performance import MetricFinding


class InfrastructureAgentOutput(StrictModel):
    findings: list[MetricFinding]
    maintenance_actions: list[str]

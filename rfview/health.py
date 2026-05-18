from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

Severity = Literal["error", "warning", "info"]


@dataclass(slots=True)
class Issue:
    severity: Severity
    rule_id: str
    message: str
    suggestion: str | None = None
    path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        item: dict[str, Any] = {
            "severity": self.severity,
            "rule_id": self.rule_id,
            "message": self.message,
        }
        if self.suggestion:
            item["suggestion"] = self.suggestion
        if self.path:
            item["path"] = self.path
        return item


@dataclass(slots=True)
class HealthReport:
    asset_id: str
    format: Literal["sigmf", "hdf5-radioml", "unknown"]
    summary: dict[str, Any] = field(default_factory=dict)
    issues: list[Issue] = field(default_factory=list)
    stats: dict[str, Any] = field(default_factory=dict)
    cache: dict[str, Any] = field(default_factory=dict)

    @property
    def gate(self) -> Literal["pass", "warn", "fail"]:
        if any(issue.severity == "error" for issue in self.issues):
            return "fail"
        if any(issue.severity == "warning" for issue in self.issues):
            return "warn"
        return "pass"

    def add(self, severity: Severity, rule_id: str, message: str, suggestion: str | None = None, path: str | None = None) -> None:
        self.issues.append(Issue(severity, rule_id, message, suggestion, path))

    def to_dict(self) -> dict[str, Any]:
        return {
            "asset_id": self.asset_id,
            "format": self.format,
            "gate": self.gate,
            "summary": self.summary,
            "stats": self.stats,
            "issues": [issue.to_dict() for issue in self.issues],
            "cache": self.cache,
        }

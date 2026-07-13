"""Decision model for command guard rules."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class DecisionKind(str, Enum):
    DENY = "deny"
    ASK = "ask"
    WARNING = "warning"
    NONE = "none"


PRIORITY = {
    DecisionKind.NONE: 0,
    DecisionKind.WARNING: 1,
    DecisionKind.ASK: 2,
    DecisionKind.DENY: 3,
}


@dataclass(frozen=True)
class Decision:
    kind: DecisionKind
    reason: str = ""
    rule_id: str = ""

    @classmethod
    def none(cls) -> "Decision":
        return cls(DecisionKind.NONE)

    @classmethod
    def warning(cls, rule_id: str, reason: str) -> "Decision":
        return cls(DecisionKind.WARNING, reason, rule_id)

    @classmethod
    def ask(cls, rule_id: str, reason: str) -> "Decision":
        return cls(DecisionKind.ASK, reason, rule_id)

    @classmethod
    def deny(cls, rule_id: str, reason: str) -> "Decision":
        return cls(DecisionKind.DENY, reason, rule_id)

    @property
    def is_actionable(self) -> bool:
        return self.kind != DecisionKind.NONE

    def formatted_reason(self) -> str:
        if not self.rule_id:
            return self.reason
        return f"[{self.rule_id}] {self.reason}"


def combine(decisions: list[Decision]) -> Decision:
    if not decisions:
        return Decision.none()
    return max(decisions, key=lambda decision: PRIORITY[decision.kind])

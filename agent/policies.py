"""Policy layer: map a Verdict to a PolicyAction.

The agent emits verdicts (what is true). This module decides what to do
about them (downstream action, escalation, notification). Rules are loaded
from config/policies.yaml at module import; per-fund-defect overrides take
precedence over defaults.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .schemas import PolicyAction, Verdict, SeverityT, ActionT


_DEFAULT_CONFIG = Path(__file__).resolve().parents[1] / "config" / "policies.yaml"


@dataclass(frozen=True)
class _Rule:
    rule_id: str
    fund_id: str | None
    defect_type: str | None
    severity_in: tuple[str, ...]
    min_confidence: float
    action: str
    escalate_to: str | None
    notification_channel: str | None


def _load_rules(path: Path) -> tuple[list[_Rule], list[_Rule]]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))

    def _parse(items: list[dict[str, Any]], with_fund: bool) -> list[_Rule]:
        out: list[_Rule] = []
        for r in items or []:
            when = r.get("when", {})
            out.append(_Rule(
                rule_id=str(r["rule_id"]),
                fund_id=r.get("fund_id") if with_fund else None,
                defect_type=r.get("defect_type") if with_fund else None,
                severity_in=tuple(when.get("severity_in", [])),
                min_confidence=float(when.get("min_confidence", 0.0)),
                action=str(r["action"]),
                escalate_to=r.get("escalate_to"),
                notification_channel=r.get("notification_channel"),
            ))
        return out

    overrides = _parse(raw.get("fund_overrides", []), with_fund=True)
    defaults = _parse(raw.get("defaults", []), with_fund=False)
    return overrides, defaults


_OVERRIDES: list[_Rule] = []
_DEFAULTS: list[_Rule] = []


def reload_policies(path: Path | str = _DEFAULT_CONFIG) -> None:
    """Reload rules from disk. Called on import; tests can call to refresh."""
    global _OVERRIDES, _DEFAULTS
    _OVERRIDES, _DEFAULTS = _load_rules(Path(path))


reload_policies()


def _matches(rule: _Rule, verdict: Verdict, fund_id: str) -> bool:
    if rule.fund_id is not None and rule.fund_id != fund_id:
        return False
    if rule.defect_type is not None and rule.defect_type != verdict.defect_type:
        return False
    if rule.severity_in and verdict.severity not in rule.severity_in:
        return False
    if verdict.confidence < rule.min_confidence:
        return False
    return True


def apply_policy(verdict: Verdict, fund_id: str) -> PolicyAction:
    """Resolve a verdict against the policy rules.

    Order:
      1. fund + defect specific overrides
      2. fund-only overrides
      3. defect-only overrides
      4. defaults

    The first matching rule within the highest-priority bucket wins.
    """
    fund_defect = [r for r in _OVERRIDES
                   if r.fund_id == fund_id and r.defect_type is not None]
    fund_only = [r for r in _OVERRIDES
                 if r.fund_id == fund_id and r.defect_type is None]
    defect_only = [r for r in _OVERRIDES
                   if r.fund_id is None and r.defect_type == verdict.defect_type]
    for bucket in (fund_defect, fund_only, defect_only, _DEFAULTS):
        for rule in bucket:
            if _matches(rule, verdict, fund_id):
                return PolicyAction(
                    verdict_defect_type=verdict.defect_type,
                    severity=verdict.severity,
                    confidence=verdict.confidence,
                    action=rule.action,  # type: ignore[arg-type]
                    escalate_to=rule.escalate_to,
                    notification_channel=rule.notification_channel,
                    rule_matched=rule.rule_id,
                )

    # Should not happen if defaults cover all severities, but be safe.
    return PolicyAction(
        verdict_defect_type=verdict.defect_type,
        severity=verdict.severity,
        confidence=verdict.confidence,
        action="LOG_ONLY",
        escalate_to=None,
        notification_channel=None,
        rule_matched="no_rule_matched_fallback",
    )

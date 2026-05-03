"""Structured schemas for the agent layer.

These types are the contract between the agent and downstream consumers
(policy layer, audit log, UI). They are versioned with the rest of the
codebase; changes here are breaking changes for replay.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import date, datetime
from typing import Any, Literal


SeverityT = Literal["LOW", "MEDIUM", "HIGH", "CRITICAL", "NONE"]
ActionT = Literal[
    "AUTO_SIGN_OFF", "LOG_ONLY", "REVIEW_QUEUE",
    "URGENT_REVIEW", "BLOCK_NAV",
]


# Closed set of defect categories the agent is asked to evaluate.
DEFECT_TYPES = (
    "single_stock_shock",
    "fx_cutoff_mismatch",
    "missed_corp_action",
    "stale_price",
    "stale_hwm_perf_fee",
    "trade_wrong_side",
    "missed_coupon_accrual",
    "subscription_pre_cutoff",
    "wrong_wht",
    "class_fee_misallocation",
    "no_defect",
    "agent_did_not_converge",
)


@dataclass
class EvidenceItem:
    """A single piece of evidence cited by the agent in its verdict."""
    description: str
    source_table: str | None = None       # e.g. 'dividend_receipts', or 'tool:get_holdings'
    source_key: dict[str, Any] = field(default_factory=dict)
    source_fields: list[str] = field(default_factory=list)
    observed_value: Any = None
    expected_value: Any = None


@dataclass
class ToolCall:
    """One tool invocation made by the agent during the run."""
    iteration: int
    tool_name: str
    arguments: dict[str, Any]
    result_summary: dict[str, Any]   # row count / shape / scalar value
    latency_ms: float
    error: str | None = None
    tool_use_id: str | None = None


@dataclass
class Verdict:
    """One conclusion produced by the agent. A single agent run can produce
    multiple verdicts (one per defect category evaluated)."""
    defect_type: str
    severity: SeverityT
    confidence: float                     # [0.0, 1.0]
    evidence: list[EvidenceItem] = field(default_factory=list)
    recommended_action: ActionT = "LOG_ONLY"
    reasoning: str = ""
    bps_impact: float | None = None

    def __post_init__(self) -> None:
        if self.defect_type not in DEFECT_TYPES:
            raise ValueError(
                f"unknown defect_type {self.defect_type!r}; "
                f"must be one of {DEFECT_TYPES}"
            )
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(
                f"confidence must be in [0,1], got {self.confidence}"
            )


@dataclass
class PolicyAction:
    """The downstream action triggered by a verdict, after policy resolution."""
    verdict_defect_type: str
    severity: SeverityT
    confidence: float
    action: ActionT
    escalate_to: str | None
    notification_channel: str | None
    rule_matched: str             # human-readable rule id


@dataclass
class TokenUsage:
    """Token accounting for one agent run."""
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0

    @property
    def total(self) -> int:
        return (
            self.input_tokens + self.output_tokens
            + self.cache_creation_input_tokens + self.cache_read_input_tokens
        )

    def add(self, other: "TokenUsage") -> None:
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens
        self.cache_creation_input_tokens += other.cache_creation_input_tokens
        self.cache_read_input_tokens += other.cache_read_input_tokens


@dataclass
class AgentRun:
    """Immutable record of one agent investigation."""
    run_id: str
    fund_id: str
    as_of_date: date
    share_class: str | None
    model_version: str
    prompt_version: str           # hash of system_prompt + defect_checklist
    verdicts: list[Verdict] = field(default_factory=list)
    policy_actions: list[PolicyAction] = field(default_factory=list)
    tool_call_log: list[ToolCall] = field(default_factory=list)
    message_history: list[dict[str, Any]] = field(default_factory=list)
    token_usage: TokenUsage = field(default_factory=TokenUsage)
    total_latency_ms: float = 0.0
    iterations: int = 0
    converged: bool = True
    halted_reason: str | None = None  # 'max_iterations' | 'token_budget' | 'error' | None
    started_at: datetime = field(default_factory=lambda: datetime.utcnow())
    finished_at: datetime | None = None


def _json_default(o: Any) -> Any:
    if isinstance(o, (date, datetime)):
        return o.isoformat()
    if hasattr(o, "__dataclass_fields__"):
        return asdict(o)
    return str(o)


def to_json_dict(obj: Any) -> Any:
    """Recursively coerce a dataclass tree into a JSON-friendly dict."""
    import json
    return json.loads(json.dumps(obj, default=_json_default))

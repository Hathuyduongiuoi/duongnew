"""Core data structures for the Hung Phat Market Evaluation AI Agent."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


CANONICAL_TABLES = (
    "market_reports",
    "competitors",
    "customer_feedback",
    "solution_catalog",
    "deployment_capability",
    "evaluation_criteria",
)

TABLE_LABELS_VI = {
    "market_reports": "Tài liệu thị trường",
    "competitors": "Hồ sơ đối thủ",
    "customer_feedback": "Phản hồi khách hàng",
    "solution_catalog": "Danh mục giải pháp",
    "deployment_capability": "Khả năng triển khai",
    "evaluation_criteria": "Bộ tiêu chí lựa chọn",
}


@dataclass
class SourceCitation:
    """Traceable reference back to an exact row and source document."""

    citation_id: str
    table_name: str
    location: str
    source_file: str
    sheet_name: str
    row_number: int
    source_name: str
    report_period: str
    metric: str
    raw_value: Any
    normalized_value: Any = None
    note: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class AuditEvent:
    """Single immutable audit event recording data, rules, or tool execution."""

    seq: int
    timestamp: str
    stage: str
    actor: str  # "AGENT" | "SKILL" | "TOOL" | "RULE" | "HUMAN"
    action: str
    detail: str
    tool_name: Optional[str] = None
    tool_args: Optional[Dict[str, Any]] = None
    tool_result_summary: Optional[Dict[str, Any]] = None
    citations: List[str] = field(default_factory=list)
    status: str = "OK"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ConflictOrGapItem:
    """Represents either missing required information or a contradiction across records."""

    issue_id: str
    issue_type: str  # "MISSING_DATA" | "CONFLICT" | "PERIOD_MISMATCH" | "CAPABILITY_MISMATCH"
    severity: str  # "HIGH" | "MEDIUM" | "LOW"
    location: str
    table_name: str
    field_name: str
    description: str
    candidates: List[Dict[str, Any]] = field(default_factory=list)
    suggested_action: str = ""
    resolved: bool = False
    resolution_note: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CriterionScore:
    """Score breakdown for a single criterion on a single location."""

    criterion_id: str
    criterion_name: str
    category_key: str
    weight_pct: float
    raw_score: Optional[float]  # 0..10 scale or None if missing
    weighted_score: Optional[float]
    min_threshold: Optional[float]
    is_hard_gate: bool
    gate_status: str  # "PASS" | "BOUNDARY_PASS" | "FAIL" | "UNKNOWN"
    document_facts: List[str] = field(default_factory=list)
    agent_inferences: List[str] = field(default_factory=list)
    citation_ids: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class LocationEvaluation:
    """Complete evaluation summary for one candidate location."""

    location: str
    rank: Optional[int]
    total_weighted_score: Optional[float]
    overall_status: str  # "SELECTED" | "ALTERNATIVE" | "DISQUALIFIED" | "INSUFFICIENT_DATA" | "BOUNDARY_REVIEW"
    hard_gate_passed: bool
    boundary_flags: List[str] = field(default_factory=list)
    missing_data_flags: List[str] = field(default_factory=list)
    conflict_flags: List[str] = field(default_factory=list)
    criterion_scores: List[CriterionScore] = field(default_factory=list)
    document_facts_summary: List[str] = field(default_factory=list)
    agent_inferences_summary: List[str] = field(default_factory=list)
    exclusion_or_selection_reason: str = ""
    citation_ids: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["criterion_scores"] = [c.to_dict() for c in self.criterion_scores]
        return data


"""Audit logging and source-citation registry for full traceability."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .models import AuditEvent, SourceCitation


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


class AuditLogger:
    """Tracks every agent decision, tool invocation, rule check, and source citation."""

    def __init__(self, run_id: str, log_dir: Optional[Path] = None) -> None:
        self.run_id = run_id
        self.created_at = _now_iso()
        self.log_dir = log_dir
        self.events: List[AuditEvent] = []
        self.citations: Dict[str, SourceCitation] = {}
        self.rules_trace: List[Dict[str, Any]] = []
        self._citation_counter = 0

    def add_citation(
        self,
        table_name: str,
        location: str,
        source_file: str,
        sheet_name: str,
        row_number: int,
        source_name: str,
        report_period: str,
        metric: str,
        raw_value: Any,
        normalized_value: Any = None,
        note: str = "",
    ) -> str:
        self._citation_counter += 1
        cid = f"CIT-{self._citation_counter:03d}"
        self.citations[cid] = SourceCitation(
            citation_id=cid,
            table_name=table_name,
            location=location,
            source_file=source_file,
            sheet_name=sheet_name,
            row_number=row_number,
            source_name=source_name or "Không ghi rõ nguồn",
            report_period=report_period or "Không ghi rõ kỳ",
            metric=metric,
            raw_value=raw_value,
            normalized_value=normalized_value,
            note=note,
        )
        return cid

    def log(
        self,
        stage: str,
        actor: str,
        action: str,
        detail: str,
        tool_name: Optional[str] = None,
        tool_args: Optional[Dict[str, Any]] = None,
        tool_result_summary: Optional[Dict[str, Any]] = None,
        citations: Optional[List[str]] = None,
        status: str = "OK",
    ) -> AuditEvent:
        event = AuditEvent(
            seq=len(self.events) + 1,
            timestamp=_now_iso(),
            stage=stage,
            actor=actor,
            action=action,
            detail=detail,
            tool_name=tool_name,
            tool_args=tool_args,
            tool_result_summary=tool_result_summary,
            citations=citations or [],
            status=status,
        )
        self.events.append(event)
        return event

    def log_rule(
        self,
        rule_id: str,
        rule_name: str,
        location: str,
        inputs: Dict[str, Any],
        threshold: Any,
        outcome: str,
        explanation: str,
        citations: Optional[List[str]] = None,
    ) -> None:
        entry = {
            "rule_id": rule_id,
            "rule_name": rule_name,
            "location": location,
            "inputs": inputs,
            "threshold": threshold,
            "outcome": outcome,
            "explanation": explanation,
            "citations": citations or [],
            "timestamp": _now_iso(),
        }
        self.rules_trace.append(entry)
        self.log(
            stage="STAGE_4_EVALUATION",
            actor="RULE",
            action=f"RULE_{rule_id}",
            detail=f"[{location}] {rule_name}: {outcome} — {explanation}",
            tool_result_summary={"inputs": inputs, "threshold": threshold, "outcome": outcome},
            citations=citations or [],
            status="WARN" if outcome in ("FAIL", "BOUNDARY_PASS", "UNKNOWN") else "OK",
        )

    def to_dict(self, extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "run_id": self.run_id,
            "created_at": self.created_at,
            "updated_at": _now_iso(),
            "summary": {
                "total_events": len(self.events),
                "total_citations": len(self.citations),
                "total_rules_checked": len(self.rules_trace),
                "tool_calls": sum(1 for e in self.events if e.tool_name),
                "human_actions": sum(1 for e in self.events if e.actor == "HUMAN"),
            },
            "events": [e.to_dict() for e in self.events],
            "rules_trace": self.rules_trace,
            "citations": {cid: c.to_dict() for cid, c in self.citations.items()},
        }
        if extra:
            payload["execution_snapshot"] = extra
        return payload

    def persist(self, extra: Optional[Dict[str, Any]] = None) -> Optional[Path]:
        if not self.log_dir:
            return None
        self.log_dir.mkdir(parents=True, exist_ok=True)
        out_path = self.log_dir / f"{self.run_id}.json"
        out_path.write_text(json.dumps(self.to_dict(extra), ensure_ascii=False, indent=2), encoding="utf-8")
        return out_path


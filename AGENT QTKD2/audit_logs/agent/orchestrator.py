"""Hybrid AI Agent Orchestrator: Real Tool-Calling Loop (Gemini / OpenAI / Local ReAct Engine)."""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .audit import AuditLogger
from .llm_client import (
    LLMClientError,
    call_gemini_with_tools,
    call_openai_with_tools,
    extract_gemini_parts,
    generate_domain_narrative_with_llm,
)
from .models import TABLE_LABELS_VI
from .parsers import classify_sheets_to_canonical
from .skills.skill_company_stats import run_company_statistics_pipeline
from .skills.skill_conflict_gap import run_conflict_and_gap_analysis
from .skills.skill_evaluate_rank import run_evaluation_and_ranking
from .skills.skill_ingest_normalize import run_ingest_and_normalize
from .skills.skill_proposal_survey import run_proposal_and_survey_plan


AGENT_SYSTEM_PROMPT = """Bạn là Hà Thuỳ Dương — Chuyên viên Data Analyst & Business Intelligence (Senior Data Analyst & BI).
Nhiệm vụ của bạn là gọi các công cụ theo đúng thứ tự:
1. Gọi `tool_read_uploaded_sources` để đọc dữ liệu từ Excel (.xlsx/.csv), Word (.docx), Google Sheets hoặc Lark Base.
2. Gọi `tool_normalize_and_deduplicate` để làm sạch dữ liệu, khử trùng lặp và thống kê chỉ số.
   - Nếu `analysis_mode = "company_statistics"`, hãy tổng hợp rõ các chỉ số thống kê nổi bật bằng tiếng Việt và kết thúc.
3. Với dữ liệu đánh giá địa bàn (`analysis_mode = "market_expansion"`):
   - Gọi `tool_detect_gaps_and_conflicts`; nếu `hitl_required = true`, DỪNG NGAY để con người xác nhận.
   - Khi `enough_data = true`, gọi `tool_evaluate_criteria_and_rules` và `tool_generate_proposal_and_survey_plan`.

NGUYÊN TẮC BẮT BUỘC:
- Chỉ dùng số liệu thực từ kết quả tool, tuyệt đối không tự bịa số liệu ngoài tài liệu.
- Trình bày bằng tiếng Việt rõ ràng, súc tích, có số liệu kiểm chứng."""


TOOL_SCHEMAS: List[Dict[str, Any]] = [
    {
        "name": "tool_read_uploaded_sources",
        "description": "Đọc các bảng/sheet đầu vào (CSV/XLSX/Google Sheets), phân loại vào 6 bảng chuẩn và kiểm tra ánh xạ cột.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "confirm": {"type": "BOOLEAN", "description": "Xác nhận đọc dữ liệu nguồn đã nạp."}
            },
            "required": ["confirm"],
        },
    },
    {
        "name": "tool_normalize_and_deduplicate",
        "description": "Kỹ năng 1: Chuẩn hóa kỳ thống kê, khử trùng lặp số liệu từ cùng nguồn gốc, liên kết dữ liệu theo 4 địa bàn và gắn mã trích dẫn CIT-xxx.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "confirm": {"type": "BOOLEAN", "description": "Xác nhận chạy bước tiền xử lý & chuẩn hóa."}
            },
            "required": ["confirm"],
        },
    },
    {
        "name": "tool_detect_gaps_and_conflicts",
        "description": "Kỹ năng 2: Đối chiếu chéo 4 địa bàn để phát hiện thông tin thiếu, mâu thuẫn nguồn, lệch kỳ thống kê và kiểm tra cổng Kiểm soát con người (HITL).",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "conflict_variance_pct": {
                    "type": "NUMBER",
                    "description": "Ngưỡng % chênh lệch để coi là mâu thuẫn số liệu giữa 2 nguồn (mặc định 20).",
                }
            },
        },
    },
    {
        "name": "tool_evaluate_criteria_and_rules",
        "description": "Kỹ năng 3: Chấm điểm 4 địa bàn theo Bộ tiêu chí, kiểm tra ngưỡng bắt buộc (Product Fit & Năng lực triển khai) và ranh giới quy tắc, xuất bảng so sánh có trích dẫn nguồn.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "tie_margin": {
                    "type": "NUMBER",
                    "description": "Khoảng chênh lệch điểm giữa hạng #2 và #3 để kích hoạt cảnh báo ranh giới (mặc định 0.20).",
                }
            },
        },
    },
    {
        "name": "tool_generate_proposal_and_survey_plan",
        "description": "Kỹ năng 4: Tạo Báo cáo đề xuất cho Trưởng phòng PTKD và Kế hoạch khảo sát tiếp theo (nhóm khách, thông tin xác minh, người phụ trách).",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "executive_note": {
                    "type": "STRING",
                    "description": "Ghi chú chiến lược bổ sung dựa hoàn toàn trên kết quả tool (nếu có).",
                }
            },
        },
    },
]


def _to_openai_tools(schemas: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    converted = []
    for s in schemas:
        params = json.loads(json.dumps(s["parameters"]).replace('"OBJECT"', '"object"').replace('"BOOLEAN"', '"boolean"').replace('"NUMBER"', '"number"').replace('"STRING"', '"string"'))
        converted.append(
            {
                "type": "function",
                "function": {
                    "name": s["name"],
                    "description": s["description"],
                    "parameters": params,
                },
            }
        )
    return converted


class AgentToolExecutor:
    """Stateful tool runtime shared by both LLM Tool-Calling and Local ReAct Engine."""

    def __init__(
        self,
        raw_sheets: Dict[str, List[Dict[str, Any]]],
        audit: AuditLogger,
        config: Optional[Dict[str, Any]] = None,
        table_overrides: Optional[Dict[str, str]] = None,
        column_overrides: Optional[Dict[str, Dict[str, str]]] = None,
        human_resolutions: Optional[Dict[str, Any]] = None,
        source_metadata: Optional[List[Dict[str, Any]]] = None,
        document_texts: Optional[Dict[str, List[str]]] = None,
    ) -> None:
        self.raw_sheets = raw_sheets
        self.audit = audit
        self.config = config or {}
        self.table_overrides = table_overrides or {}
        self.column_overrides = column_overrides or {}
        self.human_resolutions = human_resolutions or {}
        self.source_metadata = source_metadata or []
        self.document_texts = document_texts or {}

        self.analysis_mode: str = "market_expansion"
        self.schema_mapping: Optional[Dict[str, Any]] = None
        self.normalized_payload: Optional[Dict[str, Any]] = None
        self.company_stats_result: Optional[Dict[str, Any]] = None
        self.conflict_gap_result: Optional[Dict[str, Any]] = None
        self.evaluation_result: Optional[Dict[str, Any]] = None
        self.proposal_result: Optional[Dict[str, Any]] = None
        self.receive_ok: Optional[bool] = None
        self.receive_error: Optional[str] = None
        self.clean_ok: Optional[bool] = None
        self.clean_error: Optional[str] = None

    def execute_tool(self, tool_name: str, args: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        args = args or {}
        if tool_name == "tool_read_uploaded_sources":
            self.schema_mapping = classify_sheets_to_canonical(
                self.raw_sheets,
                table_overrides=self.table_overrides,
                column_overrides=self.column_overrides,
            )
            total_raw_rows = sum(len(rows) for rows in self.raw_sheets.values())
            has_doc_text = any(bool(lines) for lines in self.document_texts.values())
            core_tables = ("market_reports", "competitors", "customer_feedback", "deployment_capability")
            core_row_count = sum(len(self.schema_mapping["canonical_data"].get(t, [])) for t in core_tables)

            if (not self.raw_sheets or total_raw_rows == 0) and not has_doc_text:
                self.receive_ok = False
                self.receive_error = (
                    "Không nhận diện được bảng/dòng dữ liệu hay nội dung văn bản nào từ Excel, Word, Google Sheet hoặc Lark Base đã gửi. "
                    "Vui lòng kiểm tra lại file và gửi lại."
                )
                self.audit.log(
                    stage="STAGE_1_INPUT",
                    actor="TOOL",
                    action="RECEIVE_DATA_FAILED",
                    detail=self.receive_error,
                    tool_name=tool_name,
                    tool_args=args,
                    tool_result_summary={"receive_ok": False, "sheets_loaded": len(self.raw_sheets), "total_raw_rows": total_raw_rows, "core_row_count": core_row_count},
                    status="ERROR",
                )
                return {
                    "receive_ok": False,
                    "error": self.receive_error,
                    "sheets_loaded": len(self.raw_sheets),
                    "total_raw_rows": total_raw_rows,
                }

            self.receive_ok = True
            self.receive_error = None
            analysis_goal = str(self.config.get("analysis_goal") or "auto").strip().lower()
            if core_row_count == 0 or analysis_goal in ("financial", "priority_customers", "project_kpi", "classification"):
                # Multi-domain Project / KPI-MG Tree / Financial / Priority Customer / Classification mode
                self.analysis_mode = "company_statistics"
                summary = {
                    "receive_ok": True,
                    "analysis_mode": "company_statistics",
                    "sheets_loaded": len(self.raw_sheets),
                    "total_raw_rows": total_raw_rows,
                    "sheet_names": list(self.raw_sheets.keys()),
                    "word_docs": [k for k, v in self.document_texts.items() if v],
                }
                self.audit.log(
                    stage="STAGE_1_INPUT",
                    actor="TOOL",
                    action="CALL_TOOL_READ_SOURCES",
                    detail=f"Nhận dữ liệu công ty/thống kê thành công: đọc {len(self.raw_sheets)} bảng ({total_raw_rows} dòng) và {len(summary['word_docs'])} văn bản Word.",
                    tool_name=tool_name,
                    tool_args=args,
                    tool_result_summary=summary,
                )
                return summary

            self.analysis_mode = "market_expansion"
            summary = {
                "receive_ok": True,
                "analysis_mode": "market_expansion",
                "sheets_loaded": len(self.raw_sheets),
                "sheet_assignments": self.schema_mapping["sheet_assignments"],
                "canonical_row_counts": {
                    TABLE_LABELS_VI[k]: len(v) for k, v in self.schema_mapping["canonical_data"].items()
                },
            }
            self.audit.log(
                stage="STAGE_1_INPUT",
                actor="TOOL",
                action="CALL_TOOL_READ_SOURCES",
                detail=f"Nhận dữ liệu thành công: đọc {len(self.raw_sheets)} sheet/file ({total_raw_rows} dòng) và ánh xạ vào cấu trúc 6 bảng chuẩn.",
                tool_name=tool_name,
                tool_args=args,
                tool_result_summary={"receive_ok": True, "sheets_loaded": len(self.raw_sheets), "counts": summary["canonical_row_counts"]},
            )
            return summary

        if tool_name == "tool_normalize_and_deduplicate":
            if self.schema_mapping is None:
                read_res = self.execute_tool("tool_read_uploaded_sources", {"confirm": True})
                if not read_res.get("receive_ok"):
                    return {"receive_ok": False, "clean_ok": False, "error": self.receive_error}
            if self.receive_ok is False:
                return {"receive_ok": False, "clean_ok": False, "error": self.receive_error}

            if self.analysis_mode == "company_statistics":
                stats_res = run_company_statistics_pipeline(
                    self.raw_sheets,
                    self.audit,
                    source_metadata=self.source_metadata,
                    document_texts=self.document_texts,
                    analysis_goal=str(self.config.get("analysis_goal") or "auto"),
                    user_prompt=str(self.config.get("user_prompt") or ""),
                    cleaning_rules=self.config.get("cleaning_rules") or {},
                    business_context=self.config.get("business_context") or {},
                )
                if not stats_res.get("clean_ok"):
                    self.clean_ok = False
                    self.clean_error = stats_res.get("error") or "Làm sạch dữ liệu thống kê thất bại."
                    return {"clean_ok": False, "error": self.clean_error}
                self.clean_ok = True
                self.clean_error = None
                self.company_stats_result = stats_res
                self.proposal_result = {
                    "headline": f"{stats_res.get('domain_label', 'Thống kê Công ty')} — Báo cáo Tổng hợp",
                    "decision_status": "COMPANY_STATISTICS",
                    "selected_locations": [],
                    "survey_plan": [],
                    "markdown_report": stats_res["markdown_report"],
                }
                return {
                    "clean_ok": True,
                    "analysis_mode": "company_statistics",
                    "domain_label": stats_res.get("domain_label"),
                    "total_tables": stats_res["total_tables"],
                    "total_rows_clean": stats_res["total_rows_clean"],
                    "financial_summary": stats_res.get("financial_summary"),
                    "project_summary": stats_res.get("project_summary"),
                    "kpi_tree": stats_res.get("kpi_tree"),
                    "priority_entities": (stats_res.get("priority_entities") or [])[:8],
                    "numeric_highlights": stats_res["numeric_highlights"][:8],
                }

            self.normalized_payload = run_ingest_and_normalize(
                self.schema_mapping["canonical_data"],
                self.audit,
            )
            locs = self.normalized_payload.get("locations") or []
            norm_tables = self.normalized_payload.get("tables") or {}
            market_rows = norm_tables.get("market_reports") or []
            valid_market_nums = [
                r for r in market_rows
                if r.get("metric_value") is not None or r.get("score_10") is not None
            ]

            if len(locs) == 0:
                self.clean_ok = False
                self.clean_error = (
                    "Làm sạch dữ liệu thất bại: Không trích xuất được tên địa bàn hợp lệ nào sau chuẩn hóa. "
                    "Vui lòng kiểm tra cột Địa bàn (Location/Tỉnh thành) và gửi lại."
                )
            elif len(market_rows) > 0 and len(valid_market_nums) == 0 and not norm_tables.get("customer_feedback") and not norm_tables.get("deployment_capability"):
                self.clean_ok = False
                self.clean_error = (
                    "Làm sạch dữ liệu thất bại: Toàn bộ chỉ số quy mô/định lượng bị lỗi hoặc trống không thể quy đổi. "
                    "Vui lòng kiểm tra lại dữ liệu số và gửi lại."
                )
            else:
                self.clean_ok = True
                self.clean_error = None

            if not self.clean_ok:
                self.audit.log(
                    stage="STAGE_2_INGESTION",
                    actor="TOOL",
                    action="CLEANING_FAILED",
                    detail=self.clean_error or "Không thể làm sạch dữ liệu.",
                    tool_name=tool_name,
                    tool_args=args,
                    tool_result_summary={"clean_ok": False, "locations": locs},
                    status="ERROR",
                )
                return {
                    "clean_ok": False,
                    "error": self.clean_error,
                    "locations": locs,
                    "summary": self.normalized_payload["summary"],
                }

            return {
                "clean_ok": True,
                "locations": self.normalized_payload["locations"],
                "summary": self.normalized_payload["summary"],
                "dedup_log": self.normalized_payload["dedup_log"],
                "period_normalization_log": self.normalized_payload["period_normalization_log"],
            }

        if tool_name == "tool_detect_gaps_and_conflicts":
            if self.normalized_payload is None and self.company_stats_result is None:
                norm_res = self.execute_tool("tool_normalize_and_deduplicate", {"confirm": True})
                if norm_res.get("receive_ok") is False or norm_res.get("clean_ok") is False:
                    return norm_res
            if self.receive_ok is False or self.clean_ok is False:
                return {"blocked_by_data_gate": True, "error": self.receive_error or self.clean_error}
            if self.analysis_mode == "company_statistics":
                return {
                    "analysis_mode": "company_statistics",
                    "enough_data": True,
                    "hitl_required": False,
                    "message": "Đã thống kê trực tiếp toàn bộ bảng dữ liệu công ty (không cần HITL địa bàn).",
                }
            merged_cfg = dict(self.config)
            if "conflict_variance_pct" in args and args["conflict_variance_pct"] is not None:
                merged_cfg["conflict_variance_pct"] = args["conflict_variance_pct"]
            self.conflict_gap_result = run_conflict_and_gap_analysis(
                self.normalized_payload,
                self.audit,
                config=merged_cfg,
                human_resolutions=self.human_resolutions,
            )
            return self.conflict_gap_result

        if tool_name == "tool_evaluate_criteria_and_rules":
            if self.analysis_mode == "company_statistics":
                return {
                    "analysis_mode": "company_statistics",
                    "message": "Đã tổng hợp số liệu thống kê công ty ở bước làm sạch.",
                }
            if self.conflict_gap_result is None:
                self.execute_tool("tool_detect_gaps_and_conflicts", {})
            if not self.conflict_gap_result.get("enough_data"):
                return {
                    "blocked_by_hitl_stage3": True,
                    "message": "Chưa đủ dữ liệu hợp lệ tại Bước 2. Phải chờ con người xử lý hoặc xác nhận trước khi đánh giá Bước 3.",
                }
            merged_cfg = dict(self.config)
            if "tie_margin" in args and args["tie_margin"] is not None:
                merged_cfg["tie_margin"] = args["tie_margin"]
            self.evaluation_result = run_evaluation_and_ranking(
                self.normalized_payload,
                self.conflict_gap_result,
                self.audit,
                config=merged_cfg,
            )
            return {
                "decision_status": self.evaluation_result["decision_status"],
                "selected_locations": self.evaluation_result["selected_locations"],
                "near_tie_alert": self.evaluation_result["near_tie_alert"],
                "conditions_to_supplement": self.evaluation_result["conditions_to_supplement"],
                "evaluations_compact": [
                    {
                        "location": ev["location"],
                        "rank": ev["rank"],
                        "status": ev["overall_status"],
                        "total_score": ev["total_weighted_score"],
                        "hard_gate_passed": ev["hard_gate_passed"],
                        "boundary_flags": ev["boundary_flags"],
                        "reason": ev["exclusion_or_selection_reason"],
                    }
                    for ev in self.evaluation_result["evaluations"]
                ],
            }

        if tool_name == "tool_generate_proposal_and_survey_plan":
            if self.analysis_mode == "company_statistics":
                note = str(args.get("executive_note") or "").strip()
                if note and self.proposal_result:
                    self.proposal_result["markdown_report"] += f"\n\n## Nhận định bổ sung của AI\n{note}"
                    self.proposal_result["llm_narrative"] = note
                return {
                    "analysis_mode": "company_statistics",
                    "headline": (self.proposal_result or {}).get("headline", "Báo cáo thống kê công ty"),
                }
            if self.evaluation_result is None:
                eval_res = self.execute_tool("tool_evaluate_criteria_and_rules", {})
                if eval_res.get("blocked_by_hitl_stage3"):
                    return eval_res
            note = str(args.get("executive_note") or "").strip()
            self.proposal_result = run_proposal_and_survey_plan(
                self.normalized_payload,
                self.conflict_gap_result,
                self.evaluation_result,
                self.audit,
                llm_narrative=note,
            )
            return {
                "headline": self.proposal_result["headline"],
                "decision_status": self.proposal_result["decision_status"],
                "selected_locations": self.proposal_result["selected_locations"],
                "survey_plan_count": len(self.proposal_result["survey_plan"]),
            }

        return {"error": f"Unknown tool '{tool_name}'"}


class MarketEvaluationOrchestrator:
    """Runs and persists multi-skill market evaluation sessions with HITL support."""

    def __init__(self, log_dir: Path) -> None:
        self.log_dir = log_dir
        self.sessions: Dict[str, Dict[str, Any]] = {}

    def start_run(
        self,
        raw_sheets: Dict[str, List[Dict[str, Any]]],
        source_metadata: Optional[List[Dict[str, Any]]] = None,
        config: Optional[Dict[str, Any]] = None,
        table_overrides: Optional[Dict[str, str]] = None,
        column_overrides: Optional[Dict[str, Dict[str, str]]] = None,
        human_resolutions: Optional[Dict[str, Any]] = None,
        run_id: Optional[str] = None,
        document_texts: Optional[Dict[str, List[str]]] = None,
    ) -> Dict[str, Any]:
        config = config or {}
        run_id = run_id or f"HP-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6].upper()}"
        audit = AuditLogger(run_id=run_id, log_dir=self.log_dir)

        audit.log(
            stage="STAGE_1_INPUT",
            actor="AGENT",
            action="SESSION_STARTED",
            detail=f"Khởi tạo phiên đánh giá {run_id} với {len(raw_sheets)} sheet dữ liệu.",
            tool_result_summary={"sources": source_metadata or list(raw_sheets.keys())},
        )

        executor = AgentToolExecutor(
            raw_sheets=raw_sheets,
            audit=audit,
            config=config,
            table_overrides=table_overrides,
            column_overrides=column_overrides,
            human_resolutions=human_resolutions,
            source_metadata=source_metadata,
            document_texts=document_texts,
        )

        requested_mode = str(config.get("agent_mode") or "local").lower()
        api_key = str(config.get("api_key") or "").strip()
        if not api_key and requested_mode == "gemini":
            api_key = os.environ.get("GEMINI_API_KEY", "").strip()
        elif not api_key and requested_mode == "openai":
            api_key = os.environ.get("OPENAI_API_KEY", "").strip()
        model = str(config.get("model") or "").strip()
        allow_fallback = bool(config.get("allow_local_fallback", True))

        engine_used = "local_react_agent"
        llm_error: Optional[str] = None
        llm_final_text = ""

        if requested_mode in ("gemini", "openai") and api_key:
            try:
                # Fast-path: read & clean deterministically first (<0.2s), then run 1 fast LLM synthesis for company_statistics
                read_fast = executor.execute_tool("tool_read_uploaded_sources", {"confirm": True})
                if read_fast.get("receive_ok") and executor.analysis_mode == "company_statistics":
                    prefix = "vertex_express" if (requested_mode == "gemini" and api_key.startswith("AQ.")) else requested_mode
                    engine_used = f"{prefix}:{model or ('gemini-2.5-flash' if requested_mode == 'gemini' else 'gpt-4o-mini')}"
                    norm_fast = executor.execute_tool("tool_normalize_and_deduplicate", {"confirm": True})
                    if norm_fast.get("clean_ok") and executor.company_stats_result:
                        llm_final_text = generate_domain_narrative_with_llm(
                            agent_mode=requested_mode,
                            api_key=api_key,
                            model=model or ("gemini-2.5-flash" if requested_mode == "gemini" else "gpt-4o-mini"),
                            stats_snapshot=executor.company_stats_result,
                            user_prompt=str(config.get("user_prompt") or ""),
                            base_url=str(config.get("openai_base_url") or "https://api.openai.com/v1"),
                            timeout_sec=15,
                            lang=str(config.get("language") or "vi"),
                        )
                elif read_fast.get("receive_ok"):
                    if requested_mode == "gemini":
                        prefix = "vertex_express" if api_key.startswith("AQ.") else "gemini"
                        engine_used = f"{prefix}:{model or 'gemini-2.5-flash'}"
                        llm_final_text = self._run_gemini_loop(executor, audit, api_key, model or "gemini-2.5-flash")
                    else:
                        engine_used = f"openai:{model or 'gpt-4o-mini'}"
                        llm_final_text = self._run_openai_loop(
                            executor,
                            audit,
                            api_key,
                            model or "gpt-4o-mini",
                            str(config.get("openai_base_url") or "https://api.openai.com/v1"),
                        )
            except LLMClientError as exc:
                llm_error = str(exc)
                audit.log(
                    stage="AGENT_ORCHESTRATION",
                    actor="AGENT",
                    action="LLM_API_ERROR",
                    detail=f"Lỗi gọi {requested_mode} API: {llm_error}",
                    status="WARN",
                )
                if not allow_fallback:
                    raise
                engine_used = "local_react_fallback"
                self._run_local_react_loop(executor, audit)
        else:
            self._run_local_react_loop(executor, audit)

        # Ensure pipeline completes cleanly only if BOTH data gates passed and enough_data=True
        if executor.receive_ok is not False and executor.clean_ok is not False:
            if executor.analysis_mode == "company_statistics":
                if executor.company_stats_result is None:
                    executor.execute_tool("tool_normalize_and_deduplicate", {"confirm": True})
                if not llm_final_text and requested_mode in ("gemini", "openai") and api_key and executor.company_stats_result:
                    try:
                        llm_final_text = generate_domain_narrative_with_llm(
                            agent_mode=requested_mode,
                            api_key=api_key,
                            model=model or ("gemini-2.5-flash" if requested_mode == "gemini" else "gpt-4o-mini"),
                            stats_snapshot=executor.company_stats_result,
                            user_prompt=str(config.get("user_prompt") or ""),
                            base_url=str(config.get("openai_base_url") or "https://api.openai.com/v1"),
                            lang=str(config.get("language") or "vi"),
                        )
                    except Exception:
                        llm_final_text = ""
                if llm_final_text and executor.proposal_result and not executor.proposal_result.get("llm_narrative"):
                    executor.proposal_result["markdown_report"] += f"\n\n## Nhận định AI theo yêu cầu\n{llm_final_text}"
                    executor.proposal_result["llm_narrative"] = llm_final_text
                    if executor.company_stats_result is not None:
                        executor.company_stats_result["llm_narrative"] = llm_final_text
            elif executor.conflict_gap_result and executor.conflict_gap_result.get("enough_data"):
                if executor.evaluation_result is None:
                    executor.execute_tool("tool_evaluate_criteria_and_rules", {})
                if executor.proposal_result is None:
                    executor.execute_tool("tool_generate_proposal_and_survey_plan", {"executive_note": llm_final_text})
                elif llm_final_text and not executor.proposal_result.get("llm_narrative"):
                    executor.proposal_result = run_proposal_and_survey_plan(
                        executor.normalized_payload,
                        executor.conflict_gap_result,
                        executor.evaluation_result,
                        audit,
                        llm_narrative=llm_final_text,
                    )

        # Determine overall workflow state (including Gate 1 Receive & Gate 2 Clean failures)
        if executor.receive_ok is False:
            workflow_status = "FAILED_RECEIVE_DATA"
            current_stage = "STAGE_1_INPUT"
        elif executor.clean_ok is False:
            workflow_status = "FAILED_CLEAN_DATA"
            current_stage = "STAGE_2_INGESTION"
        elif executor.conflict_gap_result and executor.conflict_gap_result.get("hitl_required"):
            workflow_status = "AWAITING_HUMAN_STAGE3"
            current_stage = "STAGE_3_CONFLICT_GAP"
        elif executor.evaluation_result and executor.evaluation_result.get("hitl_boundary_review_recommended"):
            workflow_status = "COMPLETED_WITH_HITL_REVIEW"
            current_stage = "STAGE_5_REPORTING"
        else:
            workflow_status = "COMPLETED"
            current_stage = "STAGE_5_REPORTING"

        cleaned_sheets_store: Dict[str, List[Dict[str, Any]]] = {}
        if executor.company_stats_result and "_cleaned_sheets" in executor.company_stats_result:
            cleaned_sheets_store = executor.company_stats_result.pop("_cleaned_sheets") or {}

        response_payload = self._build_response_payload(
            run_id=run_id,
            engine_used=engine_used,
            llm_error=None if allow_fallback else llm_error,
            workflow_status=workflow_status,
            current_stage=current_stage,
            source_metadata=source_metadata or [],
            config=config,
            executor=executor,
            audit=audit,
        )

        # Store session for HITL resume / boundary confirmation / Excel & Word exports
        self.sessions[run_id] = {
            "raw_sheets": raw_sheets,
            "cleaned_sheets": cleaned_sheets_store,
            "source_metadata": source_metadata or [],
            "config": config,
            "table_overrides": table_overrides or {},
            "column_overrides": column_overrides or {},
            "human_resolutions": human_resolutions or {},
            "last_response": response_payload,
        }

        audit_path = audit.persist(extra={"workflow_status": workflow_status, "engine_used": engine_used})
        response_payload["audit_file"] = str(audit_path) if audit_path else None
        return response_payload

    def resume_with_human_input(
        self,
        run_id: str,
        human_resolutions: Dict[str, Any],
        extra_sheets: Optional[Dict[str, List[Dict[str, Any]]]] = None,
    ) -> Dict[str, Any]:
        """Handle Stage 3 Human-in-the-Loop resolution (loop back to Step 2 or proceed with flag)."""
        if run_id not in self.sessions:
            raise KeyError(f"Không tìm thấy phiên làm việc '{run_id}'.")
        sess = self.sessions[run_id]
        merged_sheets = dict(sess["raw_sheets"])
        if extra_sheets:
            for k, rows in extra_sheets.items():
                if k in merged_sheets:
                    merged_sheets[k] = merged_sheets[k] + rows
                else:
                    merged_sheets[k] = rows

        merged_res = dict(sess.get("human_resolutions") or {})
        merged_res.update(human_resolutions or {})

        return self.start_run(
            raw_sheets=merged_sheets,
            source_metadata=sess["source_metadata"],
            config=sess["config"],
            table_overrides=sess["table_overrides"],
            column_overrides=sess["column_overrides"],
            human_resolutions=merged_res,
            run_id=f"{run_id}-R{len(merged_res) + 1}",
        )

    def record_boundary_decision(
        self,
        run_id: str,
        decision: str,
        chosen_locations: Optional[List[str]] = None,
        note: str = "",
    ) -> Dict[str, Any]:
        """Handle HITL Checkpoint #2: Manager approves or overrides boundary/near-tie recommendation."""
        if run_id not in self.sessions:
            raise KeyError(f"Không tìm thấy phiên làm việc '{run_id}'.")
        sess = self.sessions[run_id]
        resp = sess["last_response"]
        audit_data = resp["audit"]

        # Append human sign-off event
        seq = len(audit_data["events"]) + 1
        event = {
            "seq": seq,
            "timestamp": datetime.now().astimezone().isoformat(timespec="seconds"),
            "stage": "STAGE_4_HITL_BOUNDARY",
            "actor": "HUMAN",
            "action": "MANAGER_BOUNDARY_DECISION",
            "detail": f"Trưởng phòng PTKD xác nhận: {decision}. Địa bàn chốt: {chosen_locations or resp['evaluation'].get('selected_locations')}. Ghi chú: {note}",
            "tool_name": None,
            "tool_args": None,
            "tool_result_summary": {"decision": decision, "chosen_locations": chosen_locations},
            "citations": [],
            "status": "OK",
        }
        audit_data["events"].append(event)
        audit_data["summary"]["total_events"] = len(audit_data["events"])
        audit_data["summary"]["human_actions"] += 1

        resp["human_boundary_signoff"] = {
            "decision": decision,
            "chosen_locations": chosen_locations or resp["evaluation"].get("selected_locations"),
            "note": note,
            "timestamp": event["timestamp"],
        }
        resp["workflow_status"] = "COMPLETED_APPROVED"

        if resp.get("audit_file"):
            Path(resp["audit_file"]).write_text(
                json.dumps(audit_data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        return resp

    def _run_local_react_loop(self, executor: AgentToolExecutor, audit: AuditLogger) -> None:
        """Deterministic multi-step ReAct Tool-Calling Engine (zero API key required)."""
        audit.log(
            stage="STAGE_1_INPUT",
            actor="AGENT",
            action="AGENT_THOUGHT",
            detail="Suy luận Agent: Cần đọc và kiểm tra cấu trúc các bảng dữ liệu đầu vào trước khi tiền xử lý.",
        )
        read_res = executor.execute_tool("tool_read_uploaded_sources", {"confirm": True})
        if read_res.get("receive_ok") is False:
            audit.log(
                stage="STAGE_1_INPUT",
                actor="AGENT",
                action="GATE_1_STOP_RESUBMIT",
                detail="Nhận được OK? = Không -> Dừng quy trình và yêu cầu người dùng gửi lại file/Google Sheet hợp lệ.",
                status="ERROR",
            )
            return

        audit.log(
            stage="STAGE_2_INGESTION",
            actor="AGENT",
            action="AGENT_THOUGHT",
            detail="Suy luận Agent: Gọi Kỹ năng 1 (tool_normalize_and_deduplicate) để làm sạch dữ liệu, chuẩn hóa kỳ và khử trùng nguồn.",
        )
        norm_res = executor.execute_tool("tool_normalize_and_deduplicate", {"confirm": True})
        if norm_res.get("clean_ok") is False:
            audit.log(
                stage="STAGE_2_INGESTION",
                actor="AGENT",
                action="GATE_2_STOP_RESUBMIT",
                detail="Làm sạch thành công? = Không -> Báo lỗi không thể làm sạch và yêu cầu người dùng gửi lại dữ liệu.",
                status="ERROR",
            )
            return

        if executor.analysis_mode == "company_statistics":
            audit.log(
                stage="STAGE_5_REPORTING",
                actor="AGENT",
                action="COMPANY_STATS_COMPLETED",
                detail="Hoàn tất tổng hợp & thống kê toàn bộ dữ liệu công ty (Excel / Word / Lark Base).",
            )
            return

        audit.log(
            stage="STAGE_3_CONFLICT_GAP",
            actor="AGENT",
            action="AGENT_THOUGHT",
            detail="Suy luận Agent: Gọi Kỹ năng 2 (tool_detect_gaps_and_conflicts) để đối chiếu 4 địa bàn và kiểm tra cổng Đủ dữ liệu.",
        )
        gap_res = executor.execute_tool("tool_detect_gaps_and_conflicts", {})

        if gap_res.get("hitl_required"):
            audit.log(
                stage="STAGE_3_CONFLICT_GAP",
                actor="AGENT",
                action="PAUSE_FOR_HITL",
                detail="Suy luận Agent: Cổng kiểm tra trả về KHÔNG ĐỦ DỮ LIỆU / CÓ MÂU THUẪN. Tạm dừng quy trình và chuyển Con người kiểm soát.",
                status="WARN",
            )
            return

        audit.log(
            stage="STAGE_4_EVALUATION",
            actor="AGENT",
            action="AGENT_THOUGHT",
            detail="Suy luận Agent: Dữ liệu hợp lệ -> Chuyển sang Bước 3, gọi Kỹ năng 3 (tool_evaluate_criteria_and_rules) để chấm điểm và xếp hạng.",
        )
        executor.execute_tool("tool_evaluate_criteria_and_rules", {})

        audit.log(
            stage="STAGE_5_REPORTING",
            actor="AGENT",
            action="AGENT_THOUGHT",
            detail="Suy luận Agent: Đã có kết quả đánh giá -> Gọi Kỹ năng 4 (tool_generate_proposal_and_survey_plan) để lập Báo cáo Đề xuất & Kế hoạch khảo sát.",
        )
        executor.execute_tool("tool_generate_proposal_and_survey_plan", {})

    def _run_gemini_loop(
        self,
        executor: AgentToolExecutor,
        audit: AuditLogger,
        api_key: str,
        model: str,
    ) -> str:
        """Real Gemini Function-Calling loop executing Skill Tools."""
        contents: List[Dict[str, Any]] = [
            {
                "role": "user",
                "parts": [
                    {
                        "text": (
                            f"Hãy thực hiện quy trình đánh giá 4 địa bàn mở rộng cho Công ty Hưng Phát trên {len(executor.raw_sheets)} sheet đã tải lên. "
                            "Gọi lần lượt các tool từ đọc dữ liệu -> chuẩn hóa -> đối chiếu mâu thuẫn -> chấm điểm -> lập báo cáo. "
                            "Nếu tool_detect_gaps_and_conflicts báo hitl_required=true thì dừng lại và giải thích các điểm cần con người xử lý."
                        )
                    }
                ],
            }
        ]

        final_texts: List[str] = []
        for _turn in range(10):
            resp_json = call_gemini_with_tools(
                api_key=api_key,
                model=model,
                system_prompt=AGENT_SYSTEM_PROMPT,
                contents=contents,
                function_declarations=TOOL_SCHEMAS,
            )
            texts, calls, raw_content = extract_gemini_parts(resp_json)
            if texts:
                final_texts.extend(texts)
                audit.log(
                    stage="AGENT_ORCHESTRATION",
                    actor="AGENT",
                    action="LLM_THOUGHT",
                    detail=" ".join(texts)[:500],
                )
            if raw_content:
                contents.append(raw_content)

            if not calls:
                break

            fn_responses: List[Dict[str, Any]] = []
            stop_for_hitl = False
            for call in calls:
                fn_name = call.get("name", "")
                fn_args = call.get("args") or {}
                tool_out = executor.execute_tool(fn_name, fn_args)
                if fn_name == "tool_detect_gaps_and_conflicts" and tool_out.get("hitl_required"):
                    stop_for_hitl = True
                if tool_out.get("receive_ok") is False or tool_out.get("clean_ok") is False:
                    stop_for_hitl = True
                fn_responses.append(
                    {
                        "functionResponse": {
                            "name": fn_name,
                            "response": {"result": tool_out},
                        }
                    }
                )
            contents.append({"role": "user", "parts": fn_responses})
            if stop_for_hitl:
                # Let LLM summarize the HITL stop cleanly or break
                resp_hitl = call_gemini_with_tools(
                    api_key=api_key,
                    model=model,
                    system_prompt=AGENT_SYSTEM_PROMPT,
                    contents=contents,
                    function_declarations=TOOL_SCHEMAS,
                )
                h_texts, _, _ = extract_gemini_parts(resp_hitl)
                final_texts.extend(h_texts)
                break

        return "\n".join(final_texts).strip()

    def _run_openai_loop(
        self,
        executor: AgentToolExecutor,
        audit: AuditLogger,
        api_key: str,
        model: str,
        base_url: str,
    ) -> str:
        """Real OpenAI Tool-Calling loop executing Skill Tools."""
        oa_tools = _to_openai_tools(TOOL_SCHEMAS)
        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": AGENT_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"Thực hiện đánh giá thị trường mở rộng 4 địa bàn trên {len(executor.raw_sheets)} bảng dữ liệu đã nạp. "
                    "Hãy gọi tuần tự các công cụ và dừng tại Bước 2 nếu hitl_required=true."
                ),
            },
        ]

        final_texts: List[str] = []
        for _turn in range(10):
            resp = call_openai_with_tools(
                api_key=api_key,
                model=model,
                messages=messages,
                tools=oa_tools,
                base_url=base_url,
            )
            choice = (resp.get("choices") or [{}])[0]
            msg = choice.get("message") or {}
            messages.append(msg)
            if msg.get("content"):
                final_texts.append(msg["content"])
                audit.log(
                    stage="AGENT_ORCHESTRATION",
                    actor="AGENT",
                    action="LLM_THOUGHT",
                    detail=msg["content"][:500],
                )
            tool_calls = msg.get("tool_calls") or []
            if not tool_calls:
                break

            stop_for_hitl = False
            for tc in tool_calls:
                fn = tc.get("function") or {}
                fn_name = fn.get("name", "")
                try:
                    fn_args = json.loads(fn.get("arguments") or "{}")
                except json.JSONDecodeError:
                    fn_args = {}
                tool_out = executor.execute_tool(fn_name, fn_args)
                if fn_name == "tool_detect_gaps_and_conflicts" and tool_out.get("hitl_required"):
                    stop_for_hitl = True
                if tool_out.get("receive_ok") is False or tool_out.get("clean_ok") is False:
                    stop_for_hitl = True
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.get("id", ""),
                        "content": json.dumps(tool_out, ensure_ascii=False),
                    }
                )
            if stop_for_hitl:
                resp2 = call_openai_with_tools(
                    api_key=api_key,
                    model=model,
                    messages=messages,
                    tools=oa_tools,
                    base_url=base_url,
                )
                msg2 = ((resp2.get("choices") or [{}])[0]).get("message") or {}
                if msg2.get("content"):
                    final_texts.append(msg2["content"])
                break

        return "\n".join(final_texts).strip()

    def _build_response_payload(
        self,
        run_id: str,
        engine_used: str,
        llm_error: Optional[str],
        workflow_status: str,
        current_stage: str,
        source_metadata: List[Dict[str, Any]],
        config: Dict[str, Any],
        executor: AgentToolExecutor,
        audit: AuditLogger,
    ) -> Dict[str, Any]:
        gate_failed = None
        gate_error_message = None
        if executor.receive_ok is False:
            gate_failed = "RECEIVE_DATA"
            gate_error_message = executor.receive_error
        elif executor.clean_ok is False:
            gate_failed = "CLEAN_DATA"
            gate_error_message = executor.clean_error

        dedup_log = []
        if executor.normalized_payload:
            dedup_log = executor.normalized_payload.get("dedup_log") or []
        elif executor.company_stats_result:
            dedup_log = executor.company_stats_result.get("dedup_log") or []

        return {
            "run_id": run_id,
            "engine_used": engine_used,
            "llm_error": llm_error,
            "analysis_mode": executor.analysis_mode,
            "workflow_status": workflow_status,
            "current_stage": current_stage,
            "gate_status": {
                "receive_ok": executor.receive_ok,
                "clean_ok": executor.clean_ok,
                "gate_failed": gate_failed,
                "gate_error_message": gate_error_message,
                "requires_resubmit": bool(gate_failed),
            },
            "source_metadata": source_metadata,
            "config": {k: v for k, v in config.items() if k != "api_key"},
            "schema_mapping": executor.schema_mapping,
            "ingestion": {
                "locations": executor.normalized_payload["locations"] if executor.normalized_payload else [],
                "summary": executor.normalized_payload["summary"] if executor.normalized_payload else {},
                "dedup_log": dedup_log,
                "period_normalization_log": (
                    executor.normalized_payload["period_normalization_log"] if executor.normalized_payload else []
                ),
            },
            "company_stats": executor.company_stats_result,
            "conflict_gap": executor.conflict_gap_result,
            "evaluation": executor.evaluation_result,
            "proposal": executor.proposal_result,
            "audit": audit.to_dict(),
        }


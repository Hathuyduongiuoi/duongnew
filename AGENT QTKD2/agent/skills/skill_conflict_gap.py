"""Skill 2: Cross-Referencing, Missing Data & Conflict Detection, and Stage 3 HITL Gate."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..audit import AuditLogger
from ..models import ConflictOrGapItem


def _apply_human_resolutions(
    normalized_payload: Dict[str, Any],
    human_resolutions: Dict[str, Any],
    audit: AuditLogger,
) -> Dict[str, Any]:
    """Apply user-verified conflict choices or supplemental fields before re-checking Stage 3."""
    if not human_resolutions:
        return normalized_payload

    tables = normalized_payload["tables"]

    # 1. Conflict source choices: {issue_id: {"selected_record_id": "MT-02", "note": "..."}}
    conflict_choices = human_resolutions.get("conflict_choices", {})
    if conflict_choices:
        dropped_ids = set()
        for issue_id, choice in conflict_choices.items():
            selected_rec = choice.get("selected_record_id")
            drop_recs = choice.get("rejected_record_ids", [])
            note = choice.get("note", "Con người xác nhận nguồn tin cậy hơn")
            for r_id in drop_recs:
                if r_id and r_id != selected_rec:
                    dropped_ids.add(r_id)
            audit.log(
                stage="STAGE_3_CONFLICT_GAP",
                actor="HUMAN",
                action="RESOLVE_CONFLICT",
                detail=f"Con người xử lý mâu thuẫn {issue_id}: giữ bản ghi '{selected_rec}', loại {drop_recs}. Ghi chú: {note}",
                status="OK",
            )
        if dropped_ids:
            tables["market_reports"] = [
                r for r in tables["market_reports"] if r.get("record_id") not in dropped_ids
            ]
            tables["customer_feedback"] = [
                r for r in tables["customer_feedback"] if r.get("record_id") not in dropped_ids
            ]

    # 2. Supplemental verified records entered by human at HITL gate
    supplements = human_resolutions.get("supplemental_data", [])
    for idx, sup in enumerate(supplements, start=1):
        loc = sup.get("location", "").strip()
        table = sup.get("table_name", "")
        if not loc or table not in tables:
            continue
        cit_id = audit.add_citation(
            table_name=table,
            location=loc,
            source_file="HUMAN_SUPPLEMENT_UI",
            sheet_name="HITL_Input",
            row_number=idx,
            source_name=sup.get("source_name") or "Bổ sung trực tiếp bởi Con người (HITL)",
            report_period=sup.get("report_period") or "Bổ sung hiện hành",
            metric="human_verified_supplement",
            raw_value=sup,
        )
        if table == "customer_feedback":
            tables["customer_feedback"].append(
                {
                    "record_id": f"KH-HITL-{idx}",
                    "location": loc,
                    "customer_segment": sup.get("customer_segment") or "Chuỗi bán lẻ (bổ sung HITL)",
                    "customer_name": sup.get("customer_name") or "Khách hàng bổ sung",
                    "store_warehouse_count": sup.get("store_warehouse_count"),
                    "required_features": sup.get("required_features") or [],
                    "required_features_raw": ", ".join(sup.get("required_features") or []),
                    "interest_level_raw": str(sup.get("interest_score", "")),
                    "interest_score": sup.get("interest_score"),
                    "onsite_support_raw": str(sup.get("onsite_support_required_score", "")),
                    "onsite_support_required_score": sup.get("onsite_support_required_score"),
                    "budget_vnd_m": None,
                    "pain_points": sup.get("pain_points") or "",
                    "source_name": sup.get("source_name") or "Bổ sung HITL",
                    "survey_date": sup.get("report_period") or "Hiện hành",
                    "citation_id": cit_id,
                }
            )
        elif table == "deployment_capability":
            tables["deployment_capability"].append(
                {
                    "record_id": f"TK-HITL-{idx}",
                    "location": loc,
                    "max_onsite_capacity": sup.get("max_onsite_capacity"),
                    "estimated_onsite_demand": sup.get("estimated_onsite_demand"),
                    "available_engineers": sup.get("available_engineers"),
                    "travel_time_hours": sup.get("travel_time_hours"),
                    "sla_hours": sup.get("sla_hours"),
                    "capability_score": sup.get("capability_score"),
                    "constraints": sup.get("constraints") or "",
                    "source_name": sup.get("source_name") or "Bổ sung HITL",
                    "updated_date": "Hiện hành",
                    "citation_id": cit_id,
                }
            )
        audit.log(
            stage="STAGE_3_CONFLICT_GAP",
            actor="HUMAN",
            action="SUPPLEMENT_DATA",
            detail=f"Con người bổ sung dữ liệu xác minh cho {loc} ({table})",
            citations=[cit_id],
        )

    return normalized_payload


def run_conflict_and_gap_analysis(
    normalized_payload: Dict[str, Any],
    audit: AuditLogger,
    config: Optional[Dict[str, Any]] = None,
    human_resolutions: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Execute Stage 3 (Skill 2): detect missing fields, source conflicts, period mismatches & HITL gate."""
    config = config or {}
    conflict_variance_pct = float(config.get("conflict_variance_pct", 20.0))
    onsite_conflict_gap = float(config.get("onsite_conflict_gap", 4.0))
    human_resolutions = human_resolutions or {}

    audit.log(
        stage="STAGE_3_CONFLICT_GAP",
        actor="SKILL",
        action="START_SKILL_2_CONFLICT_GAP",
        detail="Bắt đầu Kỹ năng 2: Đối chiếu dữ kiện giữa 4 địa bàn, phát hiện thông tin thiếu và mâu thuẫn.",
        tool_name="tool_detect_gaps_and_conflicts",
    )

    if human_resolutions:
        normalized_payload = _apply_human_resolutions(normalized_payload, human_resolutions, audit)

    locations: List[str] = normalized_payload["locations"]
    tables = normalized_payload["tables"]
    issues: List[ConflictOrGapItem] = []
    issue_counter = 0

    def next_issue_id() -> str:
        nonlocal issue_counter
        issue_counter += 1
        return f"GAP-{issue_counter:02d}"

    # Global checks
    if not tables.get("solution_catalog"):
        issues.append(
            ConflictOrGapItem(
                issue_id=next_issue_id(),
                issue_type="MISSING_DATA",
                severity="HIGH",
                location="TOÀN CÔNG TY",
                table_name="solution_catalog",
                field_name="supported_features",
                description="Thiếu bảng Danh mục giải pháp (solution_catalog) nên không thể đối chiếu Product-Market Fit.",
                suggested_action="Tải lên sheet/file Danh mục giải pháp của Hưng Phát.",
            )
        )

    if len(locations) < 4:
        issues.append(
            ConflictOrGapItem(
                issue_id=next_issue_id(),
                issue_type="MISSING_DATA",
                severity="MEDIUM" if len(locations) >= 2 else "HIGH",
                location="TOÀN HỒ SƠ",
                table_name="market_reports",
                field_name="location",
                description=f"Chỉ phát hiện {len(locations)} địa bàn ({', '.join(locations)}), thấp hơn 4 địa bàn theo bối cảnh dự án.",
                suggested_action="Kiểm tra lại dữ liệu đầu vào xem có bị thiếu địa bàn nào không.",
            )
        )

    # Check statistical periods across all market_reports
    all_periods = sorted(
        {
            r.get("normalized_period", "")
            for r in tables.get("market_reports", [])
            if r.get("normalized_period") and r.get("normalized_period") != "KHÔNG RÕ KỲ"
        }
    )
    if len(all_periods) > 1:
        years = {p.split("-")[0] for p in all_periods if p[:4].isdigit()}
        sev = "HIGH" if len(years) > 1 else "MEDIUM"
        issues.append(
            ConflictOrGapItem(
                issue_id=next_issue_id(),
                issue_type="PERIOD_MISMATCH",
                severity=sev,
                location="LIÊN ĐỊA BÀN",
                table_name="market_reports",
                field_name="report_period",
                description=(
                    f"Các tài liệu thị trường sử dụng nhiều kỳ thống kê khác nhau: {', '.join(all_periods)}. "
                    "Cần lưu ý khi so sánh trực tiếp quy mô giữa các địa bàn."
                ),
                candidates=[{"period": p} for p in all_periods],
                suggested_action="Xác nhận kỳ chuẩn đối chiếu hoặc gắn ghi chú chênh lệch kỳ trong báo cáo.",
            )
        )

    # Per-location cross-referencing
    location_data_status: Dict[str, Dict[str, Any]] = {}
    for loc in locations:
        m_rows = [r for r in tables.get("market_reports", []) if r.get("location") == loc]
        c_rows = [r for r in tables.get("competitors", []) if r.get("location") == loc]
        f_rows = [r for r in tables.get("customer_feedback", []) if r.get("location") == loc]
        d_rows = [r for r in tables.get("deployment_capability", []) if r.get("location") == loc]

        loc_missing: List[str] = []
        loc_conflicts: List[str] = []

        # 1. Missing Market Report or missing market size / source / period
        valid_m_rows = [r for r in m_rows if r.get("market_size_vnd_bn") is not None]
        if not valid_m_rows:
            desc = f"Địa bàn {loc} thiếu số liệu quy mô thị trường trong Tài liệu thị trường."
            issues.append(
                ConflictOrGapItem(
                    issue_id=next_issue_id(),
                    issue_type="MISSING_DATA",
                    severity="HIGH",
                    location=loc,
                    table_name="market_reports",
                    field_name="market_size_vnd_bn",
                    description=desc,
                    suggested_action=f"Bổ sung báo cáo thị trường có nguồn & kỳ thống kê cho {loc}.",
                )
            )
            loc_missing.append(desc)
        else:
            for r in valid_m_rows:
                if not r.get("source_name") or r.get("normalized_period") == "KHÔNG RÕ KỲ":
                    desc = f"Bản ghi {r['record_id']} tại {loc} thiếu nguồn dữ liệu hoặc kỳ thống kê rõ ràng."
                    issues.append(
                        ConflictOrGapItem(
                            issue_id=next_issue_id(),
                            issue_type="MISSING_DATA",
                            severity="MEDIUM",
                            location=loc,
                            table_name="market_reports",
                            field_name="source_name / report_period",
                            description=desc,
                            candidates=[{"record_id": r["record_id"], "citation_id": r["citation_id"]}],
                            suggested_action="Xác minh nguồn trích dẫn và thời điểm công bố.",
                        )
                    )
                    loc_missing.append(desc)

        # 2. Missing Customer Feedback
        if not f_rows:
            desc = f"Địa bàn {loc} chưa có dữ liệu Phản hồi khách hàng (không thể xác minh nhu cầu & khớp giải pháp)."
            issues.append(
                ConflictOrGapItem(
                    issue_id=next_issue_id(),
                    issue_type="MISSING_DATA",
                    severity="HIGH",
                    location=loc,
                    table_name="customer_feedback",
                    field_name="required_features / onsite_support_required",
                    description=desc,
                    suggested_action=f"Cần bổ sung khảo sát phản hồi khách hàng sơ bộ cho {loc} trước khi xếp hạng chính thức.",
                )
            )
            loc_missing.append(desc)
        else:
            has_features = any(r.get("required_features") for r in f_rows)
            if not has_features:
                desc = f"Phản hồi khách hàng tại {loc} thiếu thông tin nhu cầu tính năng cụ thể."
                issues.append(
                    ConflictOrGapItem(
                        issue_id=next_issue_id(),
                        issue_type="MISSING_DATA",
                        severity="HIGH",
                        location=loc,
                        table_name="customer_feedback",
                        field_name="required_features",
                        description=desc,
                        suggested_action=f"Bổ sung danh sách tính năng kho khách hàng tại {loc} cần.",
                    )
                )
                loc_missing.append(desc)

        # 3. Missing Deployment Capability
        valid_d_rows = [
            r
            for r in d_rows
            if r.get("max_onsite_capacity") is not None or r.get("capability_score") is not None
        ]
        if not valid_d_rows:
            desc = f"Địa bàn {loc} thiếu dữ liệu Khả năng triển khai (năng lực hỗ trợ tại chỗ / nhân sự)."
            issues.append(
                ConflictOrGapItem(
                    issue_id=next_issue_id(),
                    issue_type="MISSING_DATA",
                    severity="HIGH",
                    location=loc,
                    table_name="deployment_capability",
                    field_name="max_onsite_capacity / capability_score",
                    description=desc,
                    suggested_action=f"Yêu cầu Đội Triển khai cung cấp đánh giá năng lực hỗ trợ tại chỗ cho {loc}.",
                )
            )
            loc_missing.append(desc)

        # 4. Missing Competitor Profile (Medium severity)
        if not c_rows:
            desc = f"Địa bàn {loc} chưa có hồ sơ đối thủ cạnh tranh."
            issues.append(
                ConflictOrGapItem(
                    issue_id=next_issue_id(),
                    issue_type="MISSING_DATA",
                    severity="MEDIUM",
                    location=loc,
                    table_name="competitors",
                    field_name="competitor_name / competition_level",
                    description=desc,
                    suggested_action=f"Thu thập thêm hồ sơ đối thủ tại {loc} để giảm rủi ro khi khảo sát.",
                )
            )
            loc_missing.append(desc)

        # 5. Contradiction in Market Size across independent sources for same location
        if len(valid_m_rows) >= 2:
            vals = [r["market_size_vnd_bn"] for r in valid_m_rows]
            min_v, max_v = min(vals), max(vals)
            if max_v > 0:
                diff_pct = ((max_v - min_v) / max_v) * 100.0
                if diff_pct >= conflict_variance_pct:
                    cands = [
                        {
                            "record_id": r["record_id"],
                            "value": r["market_size_vnd_bn"],
                            "unit": "tỷ VNĐ",
                            "period": r["normalized_period"],
                            "source_name": r["source_name"],
                            "citation_id": r["citation_id"],
                        }
                        for r in valid_m_rows
                    ]
                    desc = (
                        f"Mâu thuẫn số liệu quy mô thị trường tại {loc}: chênh lệch {diff_pct:.1f}% "
                        f"giữa các nguồn ({min_v} tỷ vs {max_v} tỷ)."
                    )
                    issues.append(
                        ConflictOrGapItem(
                            issue_id=next_issue_id(),
                            issue_type="CONFLICT",
                            severity="HIGH",
                            location=loc,
                            table_name="market_reports",
                            field_name="market_size_vnd_bn",
                            description=desc,
                            candidates=cands,
                            suggested_action=f"Con người chọn nguồn đáng tin cậy hơn cho {loc} hoặc xác minh lại kỳ thống kê.",
                        )
                    )
                    loc_conflicts.append(desc)

        # 6. Contradiction in Customer Feedback onsite requirement for same location
        onsite_vals = [
            (r, r["onsite_support_required_score"])
            for r in f_rows
            if r.get("onsite_support_required_score") is not None
        ]
        if len(onsite_vals) >= 2:
            scores = [v for _, v in onsite_vals]
            if max(scores) - min(scores) >= onsite_conflict_gap:
                cands = [
                    {
                        "record_id": r["record_id"],
                        "value": score,
                        "unit": "/10",
                        "customer_segment": r["customer_segment"],
                        "source_name": r["source_name"],
                        "citation_id": r["citation_id"],
                    }
                    for r, score in onsite_vals
                ]
                desc = (
                    f"Mâu thuẫn yêu cầu hỗ trợ tại chỗ trong phản hồi khách hàng tại {loc}: "
                    f"dao động từ {min(scores)}/10 đến {max(scores)}/10."
                )
                issues.append(
                    ConflictOrGapItem(
                        issue_id=next_issue_id(),
                        issue_type="CONFLICT",
                        severity="HIGH",
                        location=loc,
                        table_name="customer_feedback",
                        field_name="onsite_support_required",
                        description=desc,
                        candidates=cands,
                        suggested_action=f"Xác minh lại phân khúc khách hàng thực tế tại {loc} hoặc chọn bản ghi đại diện.",
                    )
                )
                loc_conflicts.append(desc)

        # 7. Capability vs Onsite demand mismatch warning (for audit & Stage 4 transparency)
        if valid_d_rows and onsite_vals:
            max_cap = max(
                (r.get("max_onsite_capacity") for r in valid_d_rows if r.get("max_onsite_capacity") is not None),
                default=None,
            )
            avg_req = sum(v for _, v in onsite_vals) / len(onsite_vals)
            if max_cap is not None and avg_req > max_cap:
                desc = (
                    f"Cảnh báo năng lực tại {loc}: nhu cầu hỗ trợ tại chỗ ({avg_req:.2f}/10) "
                    f"vượt năng lực đáp ứng tối đa hiện tại ({max_cap:.2f}/10)."
                )
                issues.append(
                    ConflictOrGapItem(
                        issue_id=next_issue_id(),
                        issue_type="CAPABILITY_MISMATCH",
                        severity="LOW",
                        location=loc,
                        table_name="deployment_capability",
                        field_name="max_onsite_capacity",
                        description=desc,
                        suggested_action="Đánh giá loại hoặc hạ điểm Khả năng triển khai theo bộ tiêu chí ở Bước 3.",
                    )
                )

        has_high_blocker = any(
            it.location == loc and it.severity == "HIGH" and it.issue_type in ("MISSING_DATA", "CONFLICT")
            for it in issues
        )
        location_data_status[loc] = {
            "sufficient": not has_high_blocker,
            "missing_notes": loc_missing,
            "conflict_notes": loc_conflicts,
            "counts": {
                "market_reports": len(m_rows),
                "competitors": len(c_rows),
                "customer_feedback": len(f_rows),
                "deployment_capability": len(d_rows),
            },
        }

    # Evaluate Stage 3 Decision Diamond: CÓ ĐỦ DỮ LIỆU KHÔNG? (ENOUGH DATA?)
    high_blockers = [
        it for it in issues if it.severity == "HIGH" and it.issue_type in ("MISSING_DATA", "CONFLICT")
    ]
    sufficient_locs = [loc for loc, st in location_data_status.items() if st["sufficient"]]
    acknowledge_incomplete = bool(human_resolutions.get("acknowledge_incomplete", False))

    # Decision rule:
    # We need zero unresolved HIGH conflicts, and ideally sufficient data for candidate locations (>=2 viable or acknowledged by human).
    unresolved_high_conflicts = [it for it in high_blockers if it.issue_type == "CONFLICT"]
    unresolved_high_missing = [it for it in high_blockers if it.issue_type == "MISSING_DATA"]

    if (unresolved_high_conflicts or len(sufficient_locs) < 2 or unresolved_high_missing) and not acknowledge_incomplete:
        enough_data = False
        hitl_required = True
        gate_reason = (
            f"Phát hiện {len(unresolved_high_missing)} lỗ hổng dữ liệu nghiêm trọng và "
            f"{len(unresolved_high_conflicts)} mâu thuẫn chưa giải quyết "
            f"(hiện chỉ có {len(sufficient_locs)}/{len(locations)} địa bàn đủ dữ liệu sạch). "
            "Theo quy trình To-Be, chuyển nhánh KHÔNG -> Yêu cầu bổ sung / Kiểm soát con người."
        )
    else:
        enough_data = True
        hitl_required = False
        gate_reason = (
            "Đã có đủ dữ liệu hợp lệ để tiếp tục Bước 3."
            if not acknowledge_incomplete
            else "Con người đã xác nhận chạy đánh giá với phần dữ liệu hiện có (giữ nguyên trạng thái thiếu thông tin, không tự suy diễn bù)."
        )

    audit.log(
        stage="STAGE_3_CONFLICT_GAP",
        actor="TOOL",
        action="DECISION_ENOUGH_DATA",
        detail=gate_reason,
        tool_name="tool_check_hitl_gate",
        tool_result_summary={
            "enough_data": enough_data,
            "hitl_required": hitl_required,
            "sufficient_locations": sufficient_locs,
            "high_conflicts": len(unresolved_high_conflicts),
            "high_missing": len(unresolved_high_missing),
            "total_issues": len(issues),
        },
        status="WARN" if hitl_required else "OK",
    )

    return {
        "enough_data": enough_data,
        "hitl_required": hitl_required,
        "gate_reason": gate_reason,
        "sufficient_locations": sufficient_locs,
        "location_data_status": location_data_status,
        "issues": [it.to_dict() for it in issues],
        "period_coverage": all_periods,
    }


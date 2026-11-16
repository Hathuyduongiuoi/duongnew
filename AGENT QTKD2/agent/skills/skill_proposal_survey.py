"""Skill 4: Business Proposal Report & Next Survey Plan Generator (Strict Fact vs Inference Separation)."""

from __future__ import annotations

from typing import Any, Dict, List

from ..audit import AuditLogger


def run_proposal_and_survey_plan(
    normalized_payload: Dict[str, Any],
    conflict_gap_result: Dict[str, Any],
    evaluation_result: Dict[str, Any],
    audit: AuditLogger,
    llm_narrative: str = "",
) -> Dict[str, Any]:
    """Execute Stage 5 (Skill 4): build Manager Proposal Report and Next Survey Plan."""
    audit.log(
        stage="STAGE_5_REPORTING",
        actor="SKILL",
        action="START_SKILL_4_PROPOSAL_SURVEY",
        detail="Bắt đầu Kỹ năng 4: Tổng hợp Báo cáo Đề xuất cho Trưởng phòng PTKD và Kế hoạch khảo sát tiếp theo.",
        tool_name="tool_generate_proposal_and_survey_plan",
    )

    tables = normalized_payload["tables"]
    evaluations = evaluation_result["evaluations"]
    selected_locs = evaluation_result["selected_locations"]
    decision_status = evaluation_result["decision_status"]
    conditions = evaluation_result["conditions_to_supplement"]
    near_tie_alert = evaluation_result.get("near_tie_alert")
    issues = conflict_gap_result.get("issues", [])

    # Build Next Survey Plan strictly from dataset facts & detected gaps/boundaries
    survey_plan: List[Dict[str, Any]] = []
    target_locs = list(selected_locs)

    # If near-tie at #2/#3, also add optional comparative verification item for the #3 alternative
    if near_tie_alert:
        alts = [ev["location"] for ev in evaluations if ev["overall_status"] == "ALTERNATIVE"]
        if alts:
            target_locs.append(alts[0])

    for ev in evaluations:
        loc = ev["location"]
        if loc not in target_locs:
            continue

        is_conditional_alt = ev["overall_status"] == "ALTERNATIVE"
        f_rows = [r for r in tables.get("customer_feedback", []) if r.get("location") == loc]
        d_rows = [r for r in tables.get("deployment_capability", []) if r.get("location") == loc]
        c_rows = [r for r in tables.get("competitors", []) if r.get("location") == loc]

        segments = list(
            dict.fromkeys(r["customer_segment"] for r in f_rows if r.get("customer_segment"))
        ) or ["Chuỗi bán lẻ mục tiêu tại địa bàn (cần xác định danh sách mẫu từ dữ liệu)"]

        sample_customers = [
            f"{r['customer_name']} ({int(r['store_warehouse_count'])} điểm/kho, {r['citation_id']})"
            if r.get("customer_name") and r.get("store_warehouse_count") is not None
            else (f"{r['customer_name']} ({r['citation_id']})" if r.get("customer_name") else "")
            for r in f_rows
        ]
        sample_customers = [s for s in sample_customers if s]

        verify_items: List[str] = []
        # 1. Verify pain points & budgets from actual feedback rows
        for fr in f_rows:
            if fr.get("required_features_raw"):
                verify_items.append(
                    f"Xác minh thực tế nhu cầu tính năng ({fr['required_features_raw']}) và khả năng chi trả "
                    f"(ngân sách ghi nhận: {fr['budget_vnd_m'] or 'chưa rõ'} triệu) [{fr['citation_id']}]."
                )
        # 2. Verify deployment capability & SLA constraints
        for dr in d_rows:
            if dr.get("constraints") or dr.get("sla_hours") is not None:
                verify_items.append(
                    f"Thẩm định cam kết SLA ({dr.get('sla_hours') or '?'}h), thời gian di chuyển ({dr.get('travel_time_hours') or '?'}h) "
                    f"và phương án khắc phục hạn chế: '{dr.get('constraints') or 'Không ghi nhận'}' [{dr['citation_id']}]."
                )
        # 3. Verify any boundary flags
        for bf in ev.get("boundary_flags", []):
            verify_items.append(f"[KIỂM TRA RANH GIỚI] {bf}")
        # 4. Verify any medium/low gaps for this location
        for it in issues:
            if it["location"] in (loc, "LIÊN ĐỊA BÀN") and it["severity"] in ("MEDIUM", "HIGH"):
                verify_items.append(f"[XÁC MINH DỮ LIỆU] {it['description']}")
        # 5. Competitor verification
        if c_rows:
            comp_names = ", ".join(cr["competitor_name"] for cr in c_rows if cr.get("competitor_name"))
            verify_items.append(f"Đối chiếu điểm yếu thực tế của đối thủ ({comp_names}) khi chào giải pháp Hưng Phát.")

        owner = (
            "Trưởng nhóm Phát triển Kinh doanh (BD Lead) & Kỹ sư Giải pháp (Pre-sales)"
            if not ev.get("boundary_flags")
            else "Trưởng nhóm BD + Kỹ sư Giải pháp + Đại diện Đội Triển khai (bắt buộc thẩm định SLA)"
        )
        if is_conditional_alt:
            owner += " [Khảo sát dự phòng đối chiếu hạng #2 vs #3]"

        survey_plan.append(
            {
                "location": loc,
                "priority_tag": (
                    f"Ưu tiên #{ev['rank']} (Đề xuất chính)"
                    if not is_conditional_alt
                    else f"Dự phòng đối chiếu (Hạng #{ev['rank']} - sát điểm #2)"
                ),
                "target_customer_segments": segments,
                "sample_accounts": sample_customers,
                "information_to_verify": verify_items[:6],
                "owner": owner,
                "expected_timeline": "Tuần 1-2 sau phê duyệt" if not is_conditional_alt else "Song song Tuần 1 (nếu Trưởng phòng duyệt đối chiếu)",
                "go_no_go_criteria": "Chốt >= 3 chuỗi đạt Fit >= 6.0 và ký xác nhận biên bản SLA hỗ trợ tại chỗ không vượt năng lực đội triển khai.",
            }
        )

    # Add supplemental data collection plan if decision is INSUFFICIENT_EVIDENCE
    if decision_status == "INSUFFICIENT_EVIDENCE":
        for it in issues:
            if it["severity"] == "HIGH" and it["location"] not in ("TOÀN CÔNG TY",):
                survey_plan.append(
                    {
                        "location": it["location"],
                        "priority_tag": "BỔ SUNG HỒ SƠ BẮT BUỘC (Chưa đủ căn cứ xếp hạng)",
                        "target_customer_segments": ["Chưa đủ dữ liệu — cần thu thập mẫu ban đầu theo cấu trúc chuẩn"],
                        "sample_accounts": [],
                        "information_to_verify": [it["description"], it["suggested_action"]],
                        "owner": "Nhân viên Nghiên cứu Thị trường & Quản lý Dữ liệu",
                        "expected_timeline": "Trước khi chạy lại đánh giá Vòng 2",
                        "go_no_go_criteria": "Đầy đủ số liệu nguồn, kỳ thống kê đồng nhất và xử lý hết mâu thuẫn.",
                    }
                )

    # Headline summary
    if decision_status == "SELECTED_2_LOCATIONS":
        headline = f"Đề xuất chọn 2 địa bàn khảo sát tiếp theo cho Đợt mở rộng 1: {selected_locs[0]} và {selected_locs[1]}."
    elif decision_status == "SELECTED_WITH_BOUNDARY_REVIEW":
        headline = (
            f"Đề xuất sơ bộ 2 địa bàn: {selected_locs[0]} và {selected_locs[1]} "
            "(CẦN TRƯỞNG PHÒNG DUYỆT CÁC ĐIỂM RANH GIỚI TRƯỚC KHI CHỐT)."
        )
    else:
        sel_txt = ", ".join(selected_locs) if selected_locs else "Chưa có địa bàn đủ căn cứ"
        headline = (
            f"CHƯA ĐỦ CĂN CỨ LỰA CHỌN ĐỦ 2 ĐỊA BÀN (mới xác nhận được: {sel_txt}). "
            "Cần bổ sung dữ liệu hoặc xử lý mâu thuẫn trước khi trình Ban Giám đốc."
        )

    # Render clean Markdown Proposal Report with strict Document Facts vs Agent Inference separation
    md_lines: List[str] = [
        "# BÁO CÁO ĐỀ XUẤT MỞ RỘNG THỊ TRƯỜNG — CÔNG TY HƯNG PHÁT",
        "",
        "**Kính gửi:** Trưởng phòng Phát triển Kinh doanh",
        f"**Mã phiên truy vết (Audit Run ID):** `{audit.run_id}`",
        f"**Trạng thái kết luận:** `{decision_status}`",
        "",
        "## 1. Tóm tắt điều hành (Executive Summary)",
        f"- **Kết luận chính:** {headline}",
        f"- **Chuẩn hóa dữ liệu:** Đã nạp {normalized_payload['summary']['raw_market_rows']} bản ghi thị trường, "
        f"khử **{normalized_payload['summary']['dedup_dropped_count']}** bản ghi trùng nguồn gốc, "
        f"chuẩn hóa **{normalized_payload['summary']['period_normalizations']}** kỳ thống kê.",
    ]
    if near_tie_alert:
        md_lines.append(f"- **Cảnh báo ranh giới xếp hạng:** {near_tie_alert}")
    if conditions:
        md_lines.append("")
        md_lines.append("### Điều kiện cần bổ sung (Do chưa đủ căn cứ lựa chọn)")
        for c in conditions:
            md_lines.append(f"- {c}")

    md_lines.extend(
        [
            "",
            "## 2. Bảng so sánh 4 địa bàn (Có trích dẫn nguồn)",
            "",
            "| Hạng | Địa bàn | Trạng thái | Điểm tổng | Quy mô TT | Product Fit | Năng lực TK | Cạnh tranh |",
            "|---:|---|---|---:|---:|---:|---:|---:|",
        ]
    )

    for ev in evaluations:
        by_cat = {cs["category_key"]: cs for cs in ev["criterion_scores"]}
        def fmt_cs(cat_k: str) -> str:
            cs = by_cat.get(cat_k)
            if not cs or cs["raw_score"] is None:
                return "Thiếu/Chờ XM"
            tag = ""
            if cs["gate_status"] == "FAIL":
                tag = " (KHÔNG ĐẠT)"
            elif cs["gate_status"] == "BOUNDARY_PASS":
                tag = " (RANH GIỚI)"
            return f"{cs['raw_score']}/10{tag}"

        rank_str = f"#{ev['rank']}" if ev["rank"] else "-"
        tot_str = f"**{ev['total_weighted_score']}**" if ev["total_weighted_score"] is not None else "N/A"
        md_lines.append(
            f"| {rank_str} | {ev['location']} | {ev['overall_status']} | {tot_str} | "
            f"{fmt_cs('market_size')} | {fmt_cs('product_fit')} | {fmt_cs('deployment_capability')} | {fmt_cs('competition')} |"
        )

    md_lines.extend(["", "## 3. Phân tích chi tiết từng địa bàn (Tách bạch Dữ liệu gốc vs Suy luận Agent)"])
    for ev in evaluations:
        md_lines.extend(
            [
                "",
                f"### {ev['location']} — [{ev['overall_status']}]" + (f" (Tổng điểm: {ev['total_weighted_score']}/10)" if ev["total_weighted_score"] is not None else ""),
                f"**Lý do lựa chọn / chưa ưu tiên:** {ev['exclusion_or_selection_reason']}",
                "",
                "**[Số liệu trong tài liệu — Document Facts]:**",
            ]
        )
        if ev["document_facts_summary"]:
            for f in ev["document_facts_summary"]:
                md_lines.append(f"- {f}")
        else:
            md_lines.append("- *(Không có số liệu đầy đủ trong gói dữ liệu)*")

        md_lines.append("")
        md_lines.append("**[Suy luận & Đánh giá của Agent — Agent Inference]:**")
        for inf in ev["agent_inferences_summary"]:
            md_lines.append(f"- {inf}")

    md_lines.extend(["", "## 4. Kế hoạch khảo sát tiếp theo"])
    if survey_plan:
        for sp in survey_plan:
            md_lines.extend(
                [
                    "",
                    f"### {sp['location']} ({sp['priority_tag']})",
                    f"- **Nhóm khách cần tiếp cận:** {'; '.join(sp['target_customer_segments'])}",
                    f"- **Người phụ trách:** {sp['owner']} | **Thời hạn:** {sp['expected_timeline']}",
                    "- **Thông tin cần xác minh:**",
                ]
            )
            for v in sp["information_to_verify"]:
                md_lines.append(f"  - {v}")
            md_lines.append(f"- **Tiêu chí Go/No-Go trình Ban Giám đốc:** {sp['go_no_go_criteria']}")
    else:
        md_lines.append("- Chưa thể lập kế hoạch khảo sát chi tiết do chưa có địa bàn đạt điều kiện tối thiểu.")

    if llm_narrative:
        md_lines.extend(
            [
                "",
                "## 5. Tổng hợp điều hành bổ sung từ LLM Agent `[Suy luận Agent — Căn cứ trên kết quả công cụ]`",
                llm_narrative.strip(),
            ]
        )

    markdown_report = "\n".join(md_lines)

    report_obj = {
        "headline": headline,
        "decision_status": decision_status,
        "selected_locations": selected_locs,
        "conditions_to_supplement": conditions,
        "near_tie_alert": near_tie_alert,
        "survey_plan": survey_plan,
        "llm_narrative": llm_narrative,
        "markdown_report": markdown_report,
    }

    audit.log(
        stage="STAGE_5_REPORTING",
        actor="TOOL",
        action="COMPLETE_PROPOSAL_SURVEY",
        detail=f"Đã tạo Báo cáo Đề xuất và Kế hoạch khảo sát gồm {len(survey_plan)} hạng mục.",
        tool_name="tool_generate_proposal_and_survey_plan",
        tool_result_summary={
            "decision_status": decision_status,
            "selected_locations": selected_locs,
            "survey_plan_count": len(survey_plan),
        },
    )

    return report_obj


"""Skill 3: Multi-Criteria Evaluation, Hard-Gate Rules, Boundary Analysis & Citation-Linked Ranking."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from ..audit import AuditLogger
from ..models import CriterionScore, LocationEvaluation
from ..parsers import norm_key, parse_number, strip_accents


DEFAULT_CRITERIA: List[Dict[str, Any]] = [
    {
        "criterion_id": "TC-01",
        "criterion_name": "Quy mô & Tiềm năng thị trường",
        "category_key": "market_size",
        "weight_pct": 25.0,
        "min_threshold": None,
        "is_hard_gate": False,
        "boundary_margin": 0.25,
        "rule_description": "Chuẩn hóa theo quy mô thị trường đã khử trùng nguồn: 10 * (Quy mô địa bàn / Quy mô lớn nhất).",
    },
    {
        "criterion_id": "TC-02",
        "criterion_name": "Mức độ khớp nhu cầu sản phẩm (Product-Market Fit)",
        "category_key": "product_fit",
        "weight_pct": 30.0,
        "min_threshold": 6.0,
        "is_hard_gate": True,
        "boundary_margin": 0.25,
        "rule_description": "Đối chiếu tính năng khách hàng cần với Danh mục giải pháp Hưng Phát. Ngưỡng tối thiểu >= 6.0.",
    },
    {
        "criterion_id": "TC-03",
        "criterion_name": "Khả năng triển khai & Hỗ trợ tại chỗ",
        "category_key": "deployment_capability",
        "weight_pct": 30.0,
        "min_threshold": 6.0,
        "is_hard_gate": True,
        "boundary_margin": 0.25,
        "rule_description": "Nhu cầu hỗ trợ tại chỗ không được vượt năng lực tối đa; điểm năng lực triển khai >= 6.0.",
    },
    {
        "criterion_id": "TC-04",
        "criterion_name": "Mức độ thuận lợi cạnh tranh",
        "category_key": "competition",
        "weight_pct": 15.0,
        "min_threshold": None,
        "is_hard_gate": False,
        "boundary_margin": 0.25,
        "rule_description": "Điểm thuận lợi = 10 - Điểm áp lực cạnh tranh trung bình tại địa bàn.",
    },
]


def _feature_tokens(text: str) -> set:
    cleaned = strip_accents(text).lower()
    stopwords = {"va", "cho", "cua", "tai", "he", "thong", "quan", "ly", "cac", "nhieu", "voi"}
    tokens = {t for t in re.split(r"[^a-z0-9]+", cleaned) if len(t) >= 2 and t not in stopwords}
    return tokens


def _match_feature_to_catalog(
    req_feature: str,
    catalog: List[Dict[str, Any]],
) -> Tuple[Optional[Dict[str, Any]], float, str]:
    """Match a requested feature against Solution Catalog entries."""
    req_norm = norm_key(req_feature)
    req_toks = _feature_tokens(req_feature)
    best_sol: Optional[Dict[str, Any]] = None
    best_overlap = 0.0

    for sol in catalog:
        candidates = sol.get("supported_features", []) + [sol.get("solution_name", "")]
        for cand in candidates:
            cand_norm = norm_key(cand)
            if not cand_norm:
                continue
            if req_norm == cand_norm or req_norm in cand_norm or cand_norm in req_norm:
                overlap = 1.0
            else:
                cand_toks = _feature_tokens(cand)
                if not req_toks or not cand_toks:
                    overlap = 0.0
                else:
                    inter = len(req_toks & cand_toks)
                    overlap = inter / max(1, min(len(req_toks), len(cand_toks)))
            if overlap > best_overlap:
                best_overlap = overlap
                best_sol = sol

    if best_sol is None or best_overlap < 0.45:
        return None, 2.0, f"'{req_feature}' chưa có giải pháp khớp rõ trong Danh mục (2.0/10)"

    # Determine readiness score from solution catalog entry
    r_raw = str(best_sol.get("readiness_status") or "").strip()
    r_num = parse_number(r_raw)
    if r_num is not None:
        score = r_num / 10.0 if r_num > 10.0 else r_num
    else:
        rk = norm_key(r_raw)
        if "chua_ho_tro" in rk or "unsupported" in rk:
            score = 1.5
        elif "tuy_chinh_sau" in rk or "major" in rk or "phuc_tap" in rk:
            score = 2.9
        elif "tuy_chinh_nhe" in rk or "minor" in rk:
            score = 6.0
        elif "tuy_chinh" in rk:
            score = 4.5
        elif "san_sang" in rk or "ready" in rk:
            score = 9.0
        else:
            score = best_sol.get("readiness_score") or 6.0

    score = round(max(0.0, min(10.0, float(score))), 2)
    return (
        best_sol,
        score,
        f"'{req_feature}' -> khớp '{best_sol['solution_name']}' ({best_sol['readiness_status']}, {score}/10, {best_sol['citation_id']})",
    )


def _resolve_criteria(
    uploaded_criteria: List[Dict[str, Any]],
    config: Dict[str, Any],
) -> List[Dict[str, Any]]:
    criteria = [dict(c) for c in (uploaded_criteria if uploaded_criteria else DEFAULT_CRITERIA)]

    # Allow UI config overrides for weights / thresholds
    custom_weights = config.get("weights", {})
    min_fit = config.get("min_fit_threshold")
    min_cap = config.get("min_capability_threshold")

    for c in criteria:
        cat = c["category_key"]
        if cat in custom_weights and custom_weights[cat] is not None:
            c["weight_pct"] = float(custom_weights[cat])
        if cat == "product_fit" and min_fit is not None:
            c["min_threshold"] = float(min_fit)
        if cat == "deployment_capability" and min_cap is not None:
            c["min_threshold"] = float(min_cap)

    total_w = sum(float(c.get("weight_pct") or 0.0) for c in criteria)
    if total_w > 0 and abs(total_w - 100.0) > 0.01:
        for c in criteria:
            c["weight_pct"] = round((float(c["weight_pct"]) / total_w) * 100.0, 2)

    return criteria


def run_evaluation_and_ranking(
    normalized_payload: Dict[str, Any],
    conflict_gap_result: Dict[str, Any],
    audit: AuditLogger,
    config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Execute Stage 4 (Skill 3): score locations, enforce hard gates & boundaries, rank top 2."""
    config = config or {}
    tie_margin = float(config.get("tie_margin", 0.20))

    audit.log(
        stage="STAGE_4_EVALUATION",
        actor="SKILL",
        action="START_SKILL_3_EVALUATE_RANK",
        detail="Bắt đầu Kỹ năng 3: Chấm điểm theo bộ tiêu chí, kiểm tra ngưỡng bắt buộc/ranh giới và xếp hạng.",
        tool_name="tool_evaluate_criteria_and_rules",
    )

    tables = normalized_payload["tables"]
    locations: List[str] = normalized_payload["locations"]
    criteria = _resolve_criteria(tables.get("evaluation_criteria", []), config)
    loc_data_status = conflict_gap_result.get("location_data_status", {})
    all_issues = conflict_gap_result.get("issues", [])

    # Compute max market size across non-conflicting deduplicated records
    loc_market_values: Dict[str, Optional[float]] = {}
    loc_market_rows: Dict[str, List[Dict[str, Any]]] = {}
    for loc in locations:
        m_rows = [
            r
            for r in tables.get("market_reports", [])
            if r.get("location") == loc and r.get("market_size_vnd_bn") is not None
        ]
        loc_market_rows[loc] = m_rows
        if m_rows:
            # Prefer latest period or average across consistent rows
            loc_market_values[loc] = round(sum(r["market_size_vnd_bn"] for r in m_rows) / len(m_rows), 2)
        else:
            loc_market_values[loc] = None

    valid_sizes = [v for v in loc_market_values.values() if v is not None and v > 0]
    max_market_size = max(valid_sizes) if valid_sizes else None

    evaluations: List[LocationEvaluation] = []
    catalog = tables.get("solution_catalog", [])

    for loc in locations:
        st = loc_data_status.get(loc, {"sufficient": True, "missing_notes": [], "conflict_notes": []})
        is_sufficient = bool(st.get("sufficient", True))
        loc_high_conflicts = [
            it for it in all_issues if it["location"] == loc and it["severity"] == "HIGH" and it["issue_type"] == "CONFLICT"
        ]
        loc_high_missing = [
            it for it in all_issues if it["location"] == loc and it["severity"] == "HIGH" and it["issue_type"] == "MISSING_DATA"
        ]

        m_rows = loc_market_rows.get(loc, [])
        c_rows = [r for r in tables.get("competitors", []) if r.get("location") == loc]
        f_rows = [r for r in tables.get("customer_feedback", []) if r.get("location") == loc]
        d_rows = [r for r in tables.get("deployment_capability", []) if r.get("location") == loc]

        crit_scores: List[CriterionScore] = []
        loc_citations: List[str] = []
        loc_facts: List[str] = []
        loc_inferences: List[str] = []
        boundary_flags: List[str] = []
        hard_gate_passed = True

        for crit in criteria:
            cat = crit["category_key"]
            weight = float(crit["weight_pct"])
            min_thr = crit.get("min_threshold")
            is_hard = bool(crit.get("is_hard_gate", False))
            margin = float(crit.get("boundary_margin") or 0.25)

            raw_score: Optional[float] = None
            facts: List[str] = []
            infs: List[str] = []
            cits: List[str] = []
            gate_status = "PASS"

            if cat == "market_size":
                val = loc_market_values.get(loc)
                if loc_high_conflicts and any(it["table_name"] == "market_reports" for it in loc_high_conflicts):
                    raw_score = None
                    gate_status = "UNKNOWN"
                    for r in m_rows:
                        cits.append(r["citation_id"])
                        facts.append(
                            f"Quy mô {r['market_size_vnd_bn']} tỷ ({r['normalized_period']}, nguồn: {r['source_name']}, {r['citation_id']})"
                        )
                    infs.append("Không chấm điểm quy mô do còn mâu thuẫn số liệu chưa được con người xác minh.")
                elif val is not None and max_market_size:
                    raw_score = round(10.0 * (val / max_market_size), 2)
                    for r in m_rows:
                        cits.append(r["citation_id"])
                        chain_str = f", {r['retail_chain_count']} chuỗi bán lẻ" if r.get("retail_chain_count") is not None else ""
                        growth_str = f", tăng trưởng {r['growth_rate_pct']}%" if r.get("growth_rate_pct") is not None else ""
                        facts.append(
                            f"Quy mô {r['market_size_vnd_bn']} tỷ{chain_str}{growth_str} "
                            f"(kỳ {r['normalized_period']}, nguồn: {r['source_name']}, {r['citation_id']})"
                        )
                    infs.append(
                        f"Điểm quy mô chuẩn hóa = 10 × ({val} / {max_market_size}) = {raw_score}/10."
                    )
                else:
                    gate_status = "UNKNOWN"
                    infs.append("Thiếu số liệu quy mô thị trường trong gói dữ liệu.")

            elif cat == "product_fit":
                if not f_rows or not catalog:
                    raw_score = None
                    gate_status = "UNKNOWN"
                    infs.append("Thiếu phản hồi khách hàng hoặc danh mục giải pháp để đánh giá Product-Market Fit.")
                else:
                    feature_matches: List[float] = []
                    for fr in f_rows:
                        cits.append(fr["citation_id"])
                        feats = fr.get("required_features") or []
                        facts.append(
                            f"Nhóm '{fr['customer_segment']}' yêu cầu: {fr['required_features_raw']} "
                            f"(quan tâm: {fr['interest_level_raw'] or fr['interest_score']}, {fr['citation_id']})"
                        )
                        for feat in feats:
                            sol, f_score, match_note = _match_feature_to_catalog(feat, catalog)
                            feature_matches.append(f_score)
                            if sol:
                                cits.append(sol["citation_id"])
                            infs.append(match_note)
                    if feature_matches:
                        raw_score = round(sum(feature_matches) / len(feature_matches), 2)
                        infs.append(f"Điểm Product-Market Fit bình quân theo tính năng = {raw_score}/10.")
                    else:
                        gate_status = "UNKNOWN"
                        infs.append("Không có danh sách tính năng nhu cầu cụ thể để đối chiếu.")

            elif cat == "deployment_capability":
                if not d_rows:
                    raw_score = None
                    gate_status = "UNKNOWN"
                    infs.append("Thiếu hồ sơ Khả năng triển khai cho địa bàn này.")
                elif loc_high_conflicts and any(it["table_name"] == "customer_feedback" for it in loc_high_conflicts):
                    raw_score = None
                    gate_status = "UNKNOWN"
                    for dr in d_rows:
                        cits.append(dr["citation_id"])
                        facts.append(
                            f"Năng lực hỗ trợ tại chỗ tối đa: {dr['max_onsite_capacity']}/10, "
                            f"nhân sự: {dr['available_engineers']} ({dr['citation_id']})"
                        )
                    infs.append("Chưa chấm điểm Khả năng triển khai vì phản hồi khách hàng mâu thuẫn về mức độ hỗ trợ tại chỗ.")
                else:
                    dr = d_rows[0]
                    cits.append(dr["citation_id"])
                    max_cap = dr.get("max_onsite_capacity")
                    explicit_cap_score = dr.get("capability_score")
                    onsite_reqs = [
                        fr["onsite_support_required_score"]
                        for fr in f_rows
                        if fr.get("onsite_support_required_score") is not None
                    ]
                    avg_req = round(sum(onsite_reqs) / len(onsite_reqs), 2) if onsite_reqs else dr.get("estimated_onsite_demand")

                    for fr in f_rows:
                        if fr.get("onsite_support_required_score") is not None:
                            cits.append(fr["citation_id"])
                            facts.append(
                                f"Yêu cầu hỗ trợ tại chỗ từ khách hàng: {fr['onsite_support_required_score']}/10 "
                                f"({fr['onsite_support_raw']}, {fr['citation_id']})"
                            )
                    facts.append(
                        f"Năng lực hỗ trợ tại chỗ tối đa của Hưng Phát: {max_cap}/10; "
                        f"nhân sự khả dụng: {dr.get('available_engineers')}; "
                        f"di chuyển: {dr.get('travel_time_hours')}h ({dr['citation_id']})"
                    )
                    if dr.get("constraints"):
                        facts.append(f"Hạn chế ghi nhận: {dr['constraints']} ({dr['citation_id']})")

                    if max_cap is not None and avg_req is not None and avg_req > max_cap:
                        overload = round(avg_req - max_cap, 2)
                        raw_score = round(max(1.0, 5.5 - overload), 2)
                        gate_status = "FAIL"
                        hard_gate_passed = False
                        infs.append(
                            f"VI PHẠM NGƯỠNG TRIỂN KHAI: Nhu cầu tại chỗ ({avg_req}/10) vượt năng lực tối đa ({max_cap}/10) "
                            f"là {overload} điểm -> Điểm năng lực bị hạ xuống {raw_score}/10."
                        )
                        audit.log_rule(
                            rule_id="RULE_ONSITE_CAPACITY",
                            rule_name="Kiểm tra quá tải hỗ trợ tại chỗ",
                            location=loc,
                            inputs={"avg_onsite_demand": avg_req, "max_onsite_capacity": max_cap},
                            threshold=f"demand <= {max_cap}",
                            outcome="FAIL",
                            explanation=f"Nhu cầu {avg_req}/10 > khả năng tối đa {max_cap}/10.",
                            citations=cits,
                        )
                    elif explicit_cap_score is not None:
                        raw_score = round(float(explicit_cap_score), 2)
                        infs.append(f"Sử dụng điểm năng lực triển khai từ hồ sơ nội bộ: {raw_score}/10.")
                    elif max_cap is not None and avg_req is not None:
                        headroom = round(max_cap - avg_req, 2)
                        raw_score = round(min(10.0, 6.0 + headroom * 0.8), 2)
                        infs.append(
                            f"Năng lực tại chỗ ({max_cap}) đáp ứng nhu cầu ({avg_req}), dư biên {headroom} -> "
                            f"Điểm triển khai = min(10, 6.0 + {headroom}×0.8) = {raw_score}/10."
                        )
                    elif max_cap is not None:
                        raw_score = round(float(max_cap), 2)
                        infs.append(f"Chưa có điểm yêu cầu tại chỗ từ khách hàng; tạm dùng năng lực tối đa {raw_score}/10.")
                    else:
                        gate_status = "UNKNOWN"
                        infs.append("Thiếu chỉ số năng lực hỗ trợ tại chỗ.")

            elif cat == "competition":
                pressures = [
                    r["competition_pressure_score"]
                    for r in c_rows
                    if r.get("competition_pressure_score") is not None
                ]
                if pressures:
                    avg_p = round(sum(pressures) / len(pressures), 2)
                    raw_score = round(max(1.0, 10.0 - avg_p), 2)
                    for cr in c_rows:
                        cits.append(cr["citation_id"])
                        facts.append(
                            f"Đối thủ '{cr['competitor_name']}' (thị phần ~{cr['market_share_pct']}%, "
                            f"áp lực {cr['competition_level_raw']}, điểm yếu: {cr['weaknesses']}, {cr['citation_id']})"
                        )
                    infs.append(f"Điểm thuận lợi cạnh tranh = 10 - áp lực TB ({avg_p}) = {raw_score}/10.")
                else:
                    gate_status = "UNKNOWN"
                    infs.append("Chưa có hồ sơ đối thủ để chấm điểm cạnh tranh.")

            # Check Hard Gate Threshold & Boundary
            if raw_score is not None and min_thr is not None and gate_status != "FAIL":
                if raw_score < min_thr:
                    gate_status = "FAIL"
                    if is_hard:
                        hard_gate_passed = False
                    audit.log_rule(
                        rule_id=f"GATE_{crit['criterion_id']}",
                        rule_name=f"Ngưỡng tối thiểu {crit['criterion_name']}",
                        location=loc,
                        inputs={"score": raw_score},
                        threshold=f">= {min_thr}",
                        outcome="FAIL",
                        explanation=f"{raw_score} < {min_thr} (thiếu {round(min_thr - raw_score, 2)} điểm).",
                        citations=cits,
                    )
                elif raw_score <= min_thr + margin:
                    gate_status = "BOUNDARY_PASS"
                    b_msg = (
                        f"Tiêu chí '{crit['criterion_name']}' đạt sát ranh giới ({raw_score}/10 so với ngưỡng >= {min_thr})."
                    )
                    boundary_flags.append(b_msg)
                    audit.log_rule(
                        rule_id=f"GATE_{crit['criterion_id']}",
                        rule_name=f"Ranh giới ngưỡng {crit['criterion_name']}",
                        location=loc,
                        inputs={"score": raw_score},
                        threshold=f">= {min_thr} (biên +{margin})",
                        outcome="BOUNDARY_PASS",
                        explanation=b_msg,
                        citations=cits,
                    )
                else:
                    gate_status = "PASS"
                    if is_hard:
                        audit.log_rule(
                            rule_id=f"GATE_{crit['criterion_id']}",
                            rule_name=f"Ngưỡng tối thiểu {crit['criterion_name']}",
                            location=loc,
                            inputs={"score": raw_score},
                            threshold=f">= {min_thr}",
                            outcome="PASS",
                            explanation=f"{raw_score} >= {min_thr}.",
                            citations=cits,
                        )

            weighted = round(raw_score * (weight / 100.0), 3) if raw_score is not None else None
            dedup_cits = list(dict.fromkeys(cits))
            loc_citations.extend(dedup_cits)
            loc_facts.extend(facts)
            loc_inferences.extend(infs)

            crit_scores.append(
                CriterionScore(
                    criterion_id=crit["criterion_id"],
                    criterion_name=crit["criterion_name"],
                    category_key=cat,
                    weight_pct=weight,
                    raw_score=raw_score,
                    weighted_score=weighted,
                    min_threshold=min_thr,
                    is_hard_gate=is_hard,
                    gate_status=gate_status,
                    document_facts=facts,
                    agent_inferences=infs,
                    citation_ids=dedup_cits,
                )
            )

        # Total weighted score only valid if essential data is present (no HIGH missing/conflict)
        if not is_sufficient or any(cs.raw_score is None and cs.is_hard_gate for cs in crit_scores):
            total_score = None
            overall_status = "INSUFFICIENT_DATA"
            hard_gate_passed = False
        else:
            known_weights = sum(cs.weight_pct for cs in crit_scores if cs.weighted_score is not None)
            known_weighted = sum(cs.weighted_score for cs in crit_scores if cs.weighted_score is not None)
            # If only non-critical competition is missing, rescale known weights and flag clearly
            if known_weights > 0:
                total_score = round((known_weighted / (known_weights / 100.0)), 2) if known_weights < 99.9 else round(known_weighted, 2)
                if known_weights < 99.9:
                    loc_inferences.append(
                        f"Lưu ý: Thiếu dữ liệu tiêu chí phụ ({round(100 - known_weights, 1)}% trọng số), điểm tổng được chuẩn hóa trên phần tiêu chí có dữ liệu."
                    )
            else:
                total_score = None
            overall_status = "ALTERNATIVE" if hard_gate_passed else "DISQUALIFIED"

        evaluations.append(
            LocationEvaluation(
                location=loc,
                rank=None,
                total_weighted_score=total_score,
                overall_status=overall_status,
                hard_gate_passed=hard_gate_passed,
                boundary_flags=boundary_flags,
                missing_data_flags=[it["description"] for it in loc_high_missing],
                conflict_flags=[it["description"] for it in loc_high_conflicts],
                criterion_scores=crit_scores,
                document_facts_summary=loc_facts,
                agent_inferences_summary=loc_inferences,
                citation_ids=list(dict.fromkeys(loc_citations)),
            )
        )

    # Rank eligible locations
    eligible = [ev for ev in evaluations if ev.hard_gate_passed and ev.total_weighted_score is not None]
    eligible.sort(key=lambda x: x.total_weighted_score or 0.0, reverse=True)

    # Check near-tie boundary between Rank #2 and Rank #3
    near_tie_alert: Optional[str] = None
    if len(eligible) >= 3:
        s2 = eligible[1].total_weighted_score or 0.0
        s3 = eligible[2].total_weighted_score or 0.0
        diff = round(s2 - s3, 3)
        if diff <= tie_margin:
            near_tie_alert = (
                f"SÁT RANH GIỚI XẾP HẠNG (#2 vs #3): '{eligible[1].location}' ({s2}) chỉ hơn "
                f"'{eligible[2].location}' ({s3}) đúng {diff} điểm (<= biên dung sai {tie_margin}). "
                "Cần Trưởng phòng kiểm tra ưu tiên chiến lược trước khi chốt khảo sát."
            )
            eligible[1].boundary_flags.append(near_tie_alert)
            eligible[2].boundary_flags.append(near_tie_alert)
            audit.log_rule(
                rule_id="RULE_NEAR_TIE_2_3",
                rule_name="Kiểm tra sát điểm giữa hạng #2 và #3",
                location=f"{eligible[1].location} vs {eligible[2].location}",
                inputs={"rank2_score": s2, "rank3_score": s3, "gap": diff},
                threshold=f"> {tie_margin}",
                outcome="BOUNDARY_PASS",
                explanation=near_tie_alert,
            )

    # Assign ranks and finalize statuses
    selected_locations: List[str] = []
    for idx, ev in enumerate(eligible, start=1):
        ev.rank = idx
        if idx <= 2:
            ev.overall_status = "SELECTED"
            selected_locations.append(ev.location)
            ev.exclusion_or_selection_reason = (
                f"Đề xuất khảo sát tiếp (#{idx}): Đạt tất cả ngưỡng bắt buộc (Product Fit & Năng lực triển khai >= ngưỡng) "
                f"với tổng điểm {ev.total_weighted_score}/10."
            )
            if ev.boundary_flags:
                ev.exclusion_or_selection_reason += " Lưu ý ranh giới: " + " ".join(ev.boundary_flags)
        else:
            ev.overall_status = "ALTERNATIVE"
            top2_ref = eligible[1].total_weighted_score
            ev.exclusion_or_selection_reason = (
                f"Chưa ưu tiên đợt 1 (Hạng #{idx}, {ev.total_weighted_score}/10): Đạt ngưỡng cơ bản nhưng xếp sau 2 địa bàn dẫn đầu "
                f"(kém hạng #2 '{eligible[1].location}' {round((top2_ref or 0) - (ev.total_weighted_score or 0), 2)} điểm)."
            )

    # Explain non-eligible locations
    for ev in evaluations:
        if ev.overall_status == "DISQUALIFIED":
            failed_crits = [
                f"{cs.criterion_name} ({cs.raw_score}/10 < {cs.min_threshold})"
                for cs in ev.criterion_scores
                if cs.gate_status == "FAIL"
            ]
            ev.exclusion_or_selection_reason = (
                "Chưa ưu tiên / Loại khỏi đợt 1 do không đạt quy tắc bắt buộc: " + "; ".join(failed_crits) + "."
            )
        elif ev.overall_status == "INSUFFICIENT_DATA":
            reasons = ev.missing_data_flags + ev.conflict_flags
            ev.exclusion_or_selection_reason = (
                "Chưa đủ căn cứ xếp hạng do thiếu dữ liệu hoặc còn mâu thuẫn chưa xử lý: "
                + "; ".join(reasons)
            )

    # Determine overall decision status & conditions needed if < 2 selected
    conditions_to_supplement: List[str] = []
    if len(selected_locations) < 2:
        decision_status = "INSUFFICIENT_EVIDENCE"
        for it in all_issues:
            if it["severity"] == "HIGH":
                conditions_to_supplement.append(f"[{it['location']}] {it['suggested_action']} ({it['description']})")
        if not conditions_to_supplement:
            conditions_to_supplement.append(
                "Chỉ có dưới 2 địa bàn đạt ngưỡng Product Fit & Năng lực triển khai. Cần Ban Giám đốc cân nhắc thu hẹp phạm vi xuống 1 địa bàn hoặc nâng cấp năng lực triển khai / điều chỉnh giải pháp."
            )
    elif near_tie_alert or any(ev.boundary_flags for ev in eligible[:2]):
        decision_status = "SELECTED_WITH_BOUNDARY_REVIEW"
    else:
        decision_status = "SELECTED_2_LOCATIONS"

    # Sort final list nicely: Selected #1, #2, Alternatives, Disqualified, Insufficient
    status_order = {"SELECTED": 0, "ALTERNATIVE": 1, "DISQUALIFIED": 2, "INSUFFICIENT_DATA": 3}
    evaluations.sort(key=lambda e: (status_order.get(e.overall_status, 9), e.rank or 99, -(e.total_weighted_score or -1)))

    eval_summary = {
        "decision_status": decision_status,
        "selected_locations": selected_locations,
        "eligible_count": len(eligible),
        "near_tie_alert": near_tie_alert,
        "conditions_to_supplement": conditions_to_supplement,
    }

    audit.log(
        stage="STAGE_4_EVALUATION",
        actor="TOOL",
        action="COMPLETE_EVALUATION_RANKING",
        detail=(
            f"Hoàn tất đánh giá {len(evaluations)} địa bàn. Trạng thái quyết định: {decision_status}. "
            f"Đề xuất: {', '.join(selected_locations) if selected_locations else 'Chưa đủ căn cứ chọn đủ 2 địa bàn'}."
        ),
        tool_name="tool_evaluate_criteria_and_rules",
        tool_result_summary=eval_summary,
        status="WARN" if decision_status != "SELECTED_2_LOCATIONS" else "OK",
    )

    return {
        "criteria_used": criteria,
        "evaluations": [ev.to_dict() for ev in evaluations],
        "decision_status": decision_status,
        "selected_locations": selected_locations,
        "near_tie_alert": near_tie_alert,
        "conditions_to_supplement": conditions_to_supplement,
        "hitl_boundary_review_recommended": decision_status in ("SELECTED_WITH_BOUNDARY_REVIEW", "INSUFFICIENT_EVIDENCE"),
    }


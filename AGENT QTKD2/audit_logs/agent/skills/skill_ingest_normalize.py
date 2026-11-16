"""Skill 1: Data Ingestion, Period Normalization, Source Deduplication & Entity Linking."""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Dict, List, Optional, Tuple

from ..audit import AuditLogger
from ..models import CANONICAL_TABLES, TABLE_LABELS_VI
from ..parsers import norm_key, parse_bool_flag, parse_number, strip_accents


def normalize_location_name(raw_loc: str) -> str:
    """Standardize location strings like 'TP. Đà Nẵng' / 'tỉnh Bình Dương' -> canonical label."""
    text = unicodedata.normalize("NFC", re.sub(r"\s+", " ", str(raw_loc or "").strip()))
    if not text:
        return ""
    low = strip_accents(text).lower()
    for prefix in ("thanh pho ", "tp. ", "tp ", "tinh "):
        if low.startswith(prefix):
            return text[len(prefix):].strip()
    if low.startswith("tp."):
        return text[3:].strip()
    return text


def parse_period_info(raw_period: str, raw_period_type: str = "") -> Dict[str, Any]:
    """Parse statistical period strings (Q4/2025, 2025-Q4, 2025, H2-2025, YYYY-MM-DD)."""
    text = str(raw_period or "").strip()
    ptype = norm_key(raw_period_type)
    if not text:
        return {
            "raw": "",
            "normalized": "KHÔNG RÕ KỲ",
            "year": None,
            "period_kind": "unknown",
            "quarter": None,
            "requires_annualization": False,
        }

    up = strip_accents(text).upper().strip()
    # Quarter patterns: 2025-Q4, Q4/2025, QUY 4 2025
    m_q1 = re.match(r"^(20\d{2})\s*[-/ ]?\s*Q([1-4])$", up)
    m_q2 = re.match(r"^(?:Q|QUY)\s*([1-4])\s*[-/ ]?\s*(20\d{2})$", up)
    if m_q1:
        yr, q = int(m_q1.group(1)), int(m_q1.group(2))
        return {
            "raw": text,
            "normalized": f"{yr}-Q{q}",
            "year": yr,
            "period_kind": "quarter",
            "quarter": q,
            "requires_annualization": "quarter_flow" in ptype or ptype in {"quy_flow", "flow_quy"},
        }
    if m_q2:
        q, yr = int(m_q2.group(1)), int(m_q2.group(2))
        return {
            "raw": text,
            "normalized": f"{yr}-Q{q}",
            "year": yr,
            "period_kind": "quarter",
            "quarter": q,
            "requires_annualization": "quarter_flow" in ptype or ptype in {"quy_flow", "flow_quy"},
        }

    # Half-year patterns: 2025-H2, H1/2025, 6T/2025
    m_h1 = re.match(r"^(20\d{2})\s*[-/ ]?\s*H([12])$", up)
    m_h2 = re.match(r"^H([12])\s*[-/ ]?\s*(20\d{2})$", up)
    if m_h1 or m_h2:
        yr = int((m_h1 or m_h2).group(1 if m_h1 else 2))
        h = int((m_h1 or m_h2).group(2 if m_h1 else 1))
        return {
            "raw": text,
            "normalized": f"{yr}-H{h}",
            "year": yr,
            "period_kind": "half_year",
            "quarter": None,
            "requires_annualization": "half_flow" in ptype,
        }

    # Month / Date patterns: 2025-11-15 or 11/2025
    m_date = re.match(r"^(20\d{2})[-/](\d{1,2})(?:[-/](\d{1,2}))?$", up)
    if m_date:
        yr, mo = int(m_date.group(1)), int(m_date.group(2))
        q = (mo - 1) // 3 + 1 if 1 <= mo <= 12 else None
        return {
            "raw": text,
            "normalized": f"{yr}-Q{q}" if q else f"{yr}",
            "year": yr,
            "period_kind": "date_snapshot",
            "quarter": q,
            "requires_annualization": False,
        }

    # Year only: 2025 or NAM 2025
    m_yr = re.search(r"\b(20\d{2})\b", up)
    if m_yr:
        yr = int(m_yr.group(1))
        return {
            "raw": text,
            "normalized": f"{yr}-YEAR",
            "year": yr,
            "period_kind": "year",
            "quarter": None,
            "requires_annualization": False,
        }

    return {
        "raw": text,
        "normalized": text,
        "year": None,
        "period_kind": "other",
        "quarter": None,
        "requires_annualization": False,
    }


def _extract_location_registry(canonical_data: Dict[str, List[Dict[str, Any]]]) -> List[str]:
    """Collect unique canonical location names preserving order of appearance."""
    seen: Dict[str, str] = {}
    for table in ("market_reports", "competitors", "customer_feedback", "deployment_capability"):
        for row in canonical_data.get(table, []):
            loc = normalize_location_name(row.get("location", ""))
            if loc:
                key = norm_key(loc)
                if key not in seen:
                    seen[key] = loc
    return list(seen.values())


def run_ingest_and_normalize(
    canonical_data: Dict[str, List[Dict[str, Any]]],
    audit: AuditLogger,
) -> Dict[str, Any]:
    """Execute Stage 2 (Skill 1): normalize periods, deduplicate repeated source data, link locations."""
    audit.log(
        stage="STAGE_2_INGESTION",
        actor="SKILL",
        action="START_SKILL_1_INGEST_NORMALIZE",
        detail="Bắt đầu Kỹ năng 1: Tiền xử lý, chuẩn hóa kỳ thống kê, khử trùng lặp nguồn và ánh xạ địa bàn.",
        tool_name="tool_normalize_and_deduplicate",
    )

    locations = _extract_location_registry(canonical_data)
    loc_key_to_display = {norm_key(l): l for l in locations}

    normalized_tables: Dict[str, List[Dict[str, Any]]] = {t: [] for t in CANONICAL_TABLES}
    dedup_log: List[Dict[str, Any]] = []
    period_normalization_log: List[Dict[str, Any]] = []

    # 1. Market Reports: period normalization + source deduplication
    seen_origin_keys: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
    seen_value_keys: Dict[Tuple[str, str, str, float], Dict[str, Any]] = {}

    for idx, row in enumerate(canonical_data.get("market_reports", []), start=1):
        raw_loc = row.get("location", "")
        loc = loc_key_to_display.get(norm_key(normalize_location_name(raw_loc)), normalize_location_name(raw_loc))
        period_info = parse_period_info(
            row.get("report_period") or row.get("published_date", ""),
            row.get("period_type", ""),
        )
        market_size = parse_number(row.get("market_size_vnd_bn"))
        chain_count = parse_number(row.get("retail_chain_count"))
        growth_pct = parse_number(row.get("growth_rate_pct"))

        norm_market_size = market_size
        norm_note = ""
        if market_size is not None and period_info["requires_annualization"]:
            norm_market_size = round(market_size * 4.0, 2)
            norm_note = f"Quy đổi từ số liệu quý ({market_size}) x 4 = {norm_market_size} tỷ/năm"

        source_name = str(row.get("source_name") or "").strip()
        origin_id = norm_key(str(row.get("origin_source_id") or ""))
        rec_id = str(row.get("record_id") or f"MT-{idx:02d}")

        cit_id = audit.add_citation(
            table_name="market_reports",
            location=loc or "KHÔNG RÕ",
            source_file=row.get("_source_file", ""),
            sheet_name=row.get("_sheet_name", ""),
            row_number=int(row.get("_row_number", idx + 1)),
            source_name=source_name,
            report_period=period_info["normalized"],
            metric="market_size_vnd_bn / retail_chain_count",
            raw_value={
                "market_size_vnd_bn": row.get("market_size_vnd_bn"),
                "retail_chain_count": row.get("retail_chain_count"),
                "growth_rate_pct": row.get("growth_rate_pct"),
            },
            normalized_value={
                "market_size_vnd_bn": norm_market_size,
                "period": period_info["normalized"],
            },
            note=norm_note,
        )

        # Deduplication check:
        # Case A: Same location + same explicit origin_source_id + same normalized period
        # Case B: Same location + same period + same rounded market_size + same chain_count (when notes/source show mirror)
        is_duplicate = False
        dup_reason = ""
        kept_ref = None

        loc_k = norm_key(loc)
        src_k = norm_key(source_name)
        notes_k = norm_key(str(row.get("notes") or ""))
        if origin_id and (loc_k, origin_id, period_info["normalized"]) in seen_origin_keys:
            is_duplicate = True
            kept_ref = seen_origin_keys[(loc_k, origin_id, period_info["normalized"])]
            dup_reason = (
                f"Trùng mã nguồn gốc '{row.get('origin_source_id')}' tại {loc} "
                f"(kỳ {period_info['normalized']}) với bản ghi {kept_ref['record_id']} ({kept_ref['citation_id']})"
            )
        elif (
            market_size is not None
            and (loc_k, period_info["normalized"], src_k, round(norm_market_size or 0, 2)) in seen_value_keys
        ):
            is_duplicate = True
            kept_ref = seen_value_keys[(loc_k, period_info["normalized"], src_k, round(norm_market_size or 0, 2))]
            dup_reason = (
                f"Trùng nguồn '{source_name}' và số liệu {norm_market_size} tỷ tại {loc} "
                f"với bản ghi {kept_ref['record_id']} ({kept_ref['citation_id']})"
            )
        elif market_size is not None:
            # Case C: Same location + period + exact market size + matching chain count & secondary citation cues
            for existing in normalized_tables["market_reports"]:
                if (
                    norm_key(existing["location"]) == loc_k
                    and existing["normalized_period"] == period_info["normalized"]
                    and existing.get("market_size_vnd_bn") is not None
                    and round(existing["market_size_vnd_bn"], 2) == round(norm_market_size or 0, 2)
                    and (chain_count is None or existing.get("retail_chain_count") == int(chain_count))
                ):
                    ex_src_k = norm_key(existing.get("source_name") or "")
                    has_mirror_cue = any(
                        cue in (src_k + "_" + notes_k)
                        for cue in ("trich_lai", "trich_dan", "ban_sao", "lap_nguon", "tong_hop_lai")
                    )
                    src_overlap = bool(src_k and ex_src_k and (src_k in ex_src_k or ex_src_k in src_k))
                    if has_mirror_cue or src_overlap:
                        is_duplicate = True
                        kept_ref = existing
                        dup_reason = (
                            f"Phát hiện trích lại cùng số liệu ({norm_market_size} tỷ, kỳ {period_info['normalized']}) "
                            f"từ '{existing['source_name']}' qua '{source_name}' ({existing['citation_id']})"
                        )
                        break

        item = {
            "record_id": rec_id,
            "location": loc,
            "market_size_vnd_bn": norm_market_size,
            "raw_market_size_vnd_bn": market_size,
            "retail_chain_count": int(chain_count) if chain_count is not None else None,
            "growth_rate_pct": growth_pct,
            "raw_period": period_info["raw"],
            "normalized_period": period_info["normalized"],
            "period_kind": period_info["period_kind"],
            "period_year": period_info["year"],
            "published_date": str(row.get("published_date") or "").strip(),
            "source_name": source_name,
            "origin_source_id": str(row.get("origin_source_id") or "").strip(),
            "notes": str(row.get("notes") or "").strip(),
            "normalization_note": norm_note,
            "citation_id": cit_id,
            "is_duplicate": is_duplicate,
        }

        if period_info["raw"] != period_info["normalized"] or norm_note:
            period_normalization_log.append(
                {
                    "record_id": rec_id,
                    "location": loc,
                    "raw_period": period_info["raw"],
                    "normalized_period": period_info["normalized"],
                    "period_kind": period_info["period_kind"],
                    "normalization_note": norm_note or "Chuẩn hóa định dạng kỳ thống kê",
                    "citation_id": cit_id,
                }
            )

        if is_duplicate:
            dedup_log.append(
                {
                    "dropped_record_id": rec_id,
                    "kept_record_id": kept_ref["record_id"] if kept_ref else "",
                    "location": loc,
                    "source_name": source_name,
                    "origin_source_id": item["origin_source_id"],
                    "reason": dup_reason,
                    "dropped_citation_id": cit_id,
                    "kept_citation_id": kept_ref["citation_id"] if kept_ref else "",
                }
            )
            audit.log(
                stage="STAGE_2_INGESTION",
                actor="TOOL",
                action="DEDUP_DROPPED",
                detail=f"Loại bỏ bản ghi lặp {rec_id}: {dup_reason}",
                tool_name="tool_normalize_and_deduplicate",
                citations=[cit_id] + ([kept_ref["citation_id"]] if kept_ref else []),
                status="WARN",
            )
        else:
            if origin_id:
                seen_origin_keys[(loc_k, origin_id, period_info["normalized"])] = item
            if norm_market_size is not None:
                seen_value_keys[(loc_k, period_info["normalized"], norm_key(source_name), round(norm_market_size, 2))] = item
            normalized_tables["market_reports"].append(item)

    # 2. Competitors
    for idx, row in enumerate(canonical_data.get("competitors", []), start=1):
        loc = loc_key_to_display.get(
            norm_key(normalize_location_name(row.get("location", ""))),
            normalize_location_name(row.get("location", "")),
        )
        p_info = parse_period_info(row.get("report_period", ""))
        comp_score = parse_number(row.get("competition_level"))
        if comp_score is None:
            # Map text competition level (Cao -> high pressure = 8.5, Thấp -> 3.0)
            from ..parsers import level_to_score

            comp_score = level_to_score(row.get("competition_level"), invert=False)
        cit_id = audit.add_citation(
            table_name="competitors",
            location=loc or "KHÔNG RÕ",
            source_file=row.get("_source_file", ""),
            sheet_name=row.get("_sheet_name", ""),
            row_number=int(row.get("_row_number", idx + 1)),
            source_name=str(row.get("source_name") or "").strip(),
            report_period=p_info["normalized"],
            metric="competitor_profile",
            raw_value={
                "competitor_name": row.get("competitor_name"),
                "competition_level": row.get("competition_level"),
                "market_share_pct": row.get("market_share_pct"),
            },
            normalized_value={"competition_pressure_score": comp_score},
        )
        normalized_tables["competitors"].append(
            {
                "record_id": str(row.get("record_id") or f"DT-{idx:02d}"),
                "location": loc,
                "competitor_name": str(row.get("competitor_name") or "").strip(),
                "market_share_pct": parse_number(row.get("market_share_pct")),
                "target_segment": str(row.get("target_segment") or "").strip(),
                "strengths": str(row.get("strengths") or "").strip(),
                "weaknesses": str(row.get("weaknesses") or "").strip(),
                "competition_level_raw": str(row.get("competition_level") or "").strip(),
                "competition_pressure_score": comp_score,
                "source_name": str(row.get("source_name") or "").strip(),
                "normalized_period": p_info["normalized"],
                "citation_id": cit_id,
            }
        )

    # 3. Customer Feedback
    from ..parsers import level_to_score

    for idx, row in enumerate(canonical_data.get("customer_feedback", []), start=1):
        loc = loc_key_to_display.get(
            norm_key(normalize_location_name(row.get("location", ""))),
            normalize_location_name(row.get("location", "")),
        )
        p_info = parse_period_info(row.get("survey_date", ""))
        features_raw = str(row.get("required_features") or "").strip()
        features = [f.strip() for f in re.split(r"[;|,]+", features_raw) if f.strip()]
        interest_score = level_to_score(row.get("interest_level"), invert=False)
        onsite_req = level_to_score(row.get("onsite_support_required"), invert=False)
        cit_id = audit.add_citation(
            table_name="customer_feedback",
            location=loc or "KHÔNG RÕ",
            source_file=row.get("_source_file", ""),
            sheet_name=row.get("_sheet_name", ""),
            row_number=int(row.get("_row_number", idx + 1)),
            source_name=str(row.get("source_name") or "").strip(),
            report_period=p_info["normalized"],
            metric="customer_feedback",
            raw_value={
                "customer_segment": row.get("customer_segment"),
                "required_features": features_raw,
                "interest_level": row.get("interest_level"),
                "onsite_support_required": row.get("onsite_support_required"),
            },
            normalized_value={
                "interest_score": interest_score,
                "onsite_support_required_score": onsite_req,
            },
        )
        normalized_tables["customer_feedback"].append(
            {
                "record_id": str(row.get("record_id") or f"KH-{idx:02d}"),
                "location": loc,
                "customer_segment": str(row.get("customer_segment") or "").strip(),
                "customer_name": str(row.get("customer_name") or "").strip(),
                "store_warehouse_count": parse_number(row.get("store_warehouse_count")),
                "required_features": features,
                "required_features_raw": features_raw,
                "interest_level_raw": str(row.get("interest_level") or "").strip(),
                "interest_score": interest_score,
                "onsite_support_raw": str(row.get("onsite_support_required") or "").strip(),
                "onsite_support_required_score": onsite_req,
                "budget_vnd_m": parse_number(row.get("budget_vnd_m")),
                "pain_points": str(row.get("pain_points") or "").strip(),
                "source_name": str(row.get("source_name") or "").strip(),
                "survey_date": p_info["normalized"],
                "citation_id": cit_id,
            }
        )

    # 4. Solution Catalog
    for idx, row in enumerate(canonical_data.get("solution_catalog", []), start=1):
        feats_raw = str(row.get("supported_features") or "").strip()
        feats = [f.strip() for f in re.split(r"[;|,]+", feats_raw) if f.strip()]
        readiness_score = level_to_score(row.get("readiness_status"), invert=False)
        cit_id = audit.add_citation(
            table_name="solution_catalog",
            location="TOÀN CÔNG TY",
            source_file=row.get("_source_file", ""),
            sheet_name=row.get("_sheet_name", ""),
            row_number=int(row.get("_row_number", idx + 1)),
            source_name="Danh mục giải pháp Hưng Phát",
            report_period="Hiện hành",
            metric="solution_catalog",
            raw_value={
                "solution_name": row.get("solution_name"),
                "supported_features": feats_raw,
                "readiness_status": row.get("readiness_status"),
            },
            normalized_value={"readiness_score": readiness_score},
        )
        normalized_tables["solution_catalog"].append(
            {
                "solution_id": str(row.get("solution_id") or f"GP-{idx:02d}"),
                "solution_name": str(row.get("solution_name") or "").strip(),
                "supported_features": feats,
                "supported_features_raw": feats_raw,
                "target_segments": str(row.get("target_segments") or "").strip(),
                "readiness_status": str(row.get("readiness_status") or "").strip(),
                "readiness_score": readiness_score,
                "standard_onsite_level": str(row.get("standard_onsite_level") or "").strip(),
                "notes": str(row.get("notes") or "").strip(),
                "citation_id": cit_id,
            }
        )

    # 5. Deployment Capability
    for idx, row in enumerate(canonical_data.get("deployment_capability", []), start=1):
        loc = loc_key_to_display.get(
            norm_key(normalize_location_name(row.get("location", ""))),
            normalize_location_name(row.get("location", "")),
        )
        p_info = parse_period_info(row.get("updated_date", ""))
        max_cap = level_to_score(row.get("max_onsite_capacity"), invert=False)
        est_demand = level_to_score(row.get("estimated_onsite_demand"), invert=False)
        cap_score = parse_number(row.get("capability_score"))
        cit_id = audit.add_citation(
            table_name="deployment_capability",
            location=loc or "KHÔNG RÕ",
            source_file=row.get("_source_file", ""),
            sheet_name=row.get("_sheet_name", ""),
            row_number=int(row.get("_row_number", idx + 1)),
            source_name=str(row.get("source_name") or "Đội Triển khai Hưng Phát").strip(),
            report_period=p_info["normalized"],
            metric="deployment_capability",
            raw_value={
                "max_onsite_capacity": row.get("max_onsite_capacity"),
                "estimated_onsite_demand": row.get("estimated_onsite_demand"),
                "available_engineers": row.get("available_engineers"),
                "capability_score": row.get("capability_score"),
            },
            normalized_value={"max_onsite_capacity": max_cap, "capability_score": cap_score},
        )
        normalized_tables["deployment_capability"].append(
            {
                "record_id": str(row.get("record_id") or f"TK-{idx:02d}"),
                "location": loc,
                "max_onsite_capacity": max_cap,
                "estimated_onsite_demand": est_demand,
                "available_engineers": parse_number(row.get("available_engineers")),
                "travel_time_hours": parse_number(row.get("travel_time_hours")),
                "sla_hours": parse_number(row.get("sla_hours")),
                "capability_score": cap_score,
                "constraints": str(row.get("constraints") or "").strip(),
                "source_name": str(row.get("source_name") or "Đội Triển khai Hưng Phát").strip(),
                "updated_date": p_info["normalized"],
                "citation_id": cit_id,
            }
        )

    # 6. Evaluation Criteria (use uploaded criteria or standard defaults if missing)
    for idx, row in enumerate(canonical_data.get("evaluation_criteria", []), start=1):
        cat_raw = norm_key(str(row.get("category_key") or row.get("criterion_name") or ""))
        cat_key = _infer_criterion_category(cat_raw)
        is_hard = parse_bool_flag(row.get("is_hard_gate"))
        cit_id = audit.add_citation(
            table_name="evaluation_criteria",
            location="BỘ TIÊU CHÍ",
            source_file=row.get("_source_file", ""),
            sheet_name=row.get("_sheet_name", ""),
            row_number=int(row.get("_row_number", idx + 1)),
            source_name="Bộ tiêu chí đánh giá địa bàn",
            report_period="Hiện hành",
            metric=str(row.get("criterion_name") or cat_key),
            raw_value={
                "weight_pct": row.get("weight_pct"),
                "min_threshold": row.get("min_threshold"),
                "is_hard_gate": row.get("is_hard_gate"),
            },
        )
        normalized_tables["evaluation_criteria"].append(
            {
                "criterion_id": str(row.get("criterion_id") or f"TC-{idx:02d}"),
                "criterion_name": str(row.get("criterion_name") or cat_key).strip(),
                "category_key": cat_key,
                "weight_pct": parse_number(row.get("weight_pct")) or 25.0,
                "min_threshold": parse_number(row.get("min_threshold")),
                "is_hard_gate": bool(is_hard) if is_hard is not None else False,
                "boundary_margin": parse_number(row.get("boundary_margin")) or 0.25,
                "rule_description": str(row.get("rule_description") or "").strip(),
                "citation_id": cit_id,
            }
        )

    summary = {
        "locations_detected": locations,
        "table_counts": {TABLE_LABELS_VI[k]: len(v) for k, v in normalized_tables.items()},
        "raw_market_rows": len(canonical_data.get("market_reports", [])),
        "dedup_kept_market_rows": len(normalized_tables["market_reports"]),
        "dedup_dropped_count": len(dedup_log),
        "period_normalizations": len(period_normalization_log),
    }

    audit.log(
        stage="STAGE_2_INGESTION",
        actor="TOOL",
        action="COMPLETE_INGEST_NORMALIZE",
        detail=(
            f"Hoàn tất chuẩn hóa {len(locations)} địa bàn ({', '.join(locations) or 'chưa có'}). "
            f"Khử {len(dedup_log)} bản ghi trùng nguồn, chuẩn hóa {len(period_normalization_log)} kỳ thống kê."
        ),
        tool_name="tool_normalize_and_deduplicate",
        tool_result_summary=summary,
    )

    return {
        "locations": locations,
        "tables": normalized_tables,
        "dedup_log": dedup_log,
        "period_normalization_log": period_normalization_log,
        "summary": summary,
    }


def _infer_criterion_category(cat_raw: str) -> str:
    if any(k in cat_raw for k in ("market", "quy_mo", "tiem_nang", "size")):
        return "market_size"
    if any(k in cat_raw for k in ("fit", "khop", "nhu_cau", "giai_phap", "product")):
        return "product_fit"
    if any(k in cat_raw for k in ("capab", "trien_khai", "ho_tro", "onsite", "nang_luc")):
        return "deployment_capability"
    if any(k in cat_raw for k in ("comp", "doi_thu", "canh_tranh")):
        return "competition"
    return cat_raw or "other"

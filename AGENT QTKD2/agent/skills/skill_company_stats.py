"""Statistical pipeline: Receive -> Clean -> Describe -> Classify/Prioritize -> Report (any company data)."""

from __future__ import annotations

import json
import re
import statistics
from collections import Counter, defaultdict
from typing import Any, Dict, List, Optional, Tuple

from ..audit import AuditLogger
from ..parsers import norm_key, parse_number
from .bi_analyst_stages import build_7stage_bi_pipeline_and_report

_DATE_RE = re.compile(r"^\d{4}[-/]\d{1,2}[-/]\d{1,2}$|^\d{1,2}[-/]\d{1,2}[-/]\d{2,4}$")
_CODE_RE = re.compile(r"^[A-Za-z]{1,6}[-_]\d+$")
_PHONE_RE = re.compile(r"^0\d{8,11}$")
_NON_METRIC_COL_HINTS = ("id", "ma_", "code", "sdt", "phone", "ngay", "date", "thoi_gian", "stt", "row")
_NON_GROUP_COL_HINTS = _NON_METRIC_COL_HINTS + ("ghi_chu", "note", "mo_ta", "description", "nhan_xet", "email", "dia_chi", "address")

_UNIT_RE = re.compile(r"(tỷ|tỉ|ty|triệu|trieu|nghìn|nghin|ngàn|ngan)\s*(?:vnd|vnđ|đ|đồng|dong)?\s*$", re.I)
_UNIT_RANK = {"ty": 1_000_000, "trieu": 1_000, "nghin": 1}
_UNIT_LABEL = {"ty": "tỷ", "trieu": "triệu", "nghin": "nghìn"}

KV_HEADERS = {"Chi_Tieu", "Gia_Tri", "Gia_Tri_So"}

DOMAIN_HINTS: Dict[str, Tuple[str, Tuple[str, ...]]] = {
    "financial": (
        "Thống kê Tài chính & Biên lợi nhuận",
        (
            "doanh_thu", "chi_phi", "loi_nhuan", "revenue", "cost", "expense", "profit",
            "budget", "ngan_sach", "gia_von", "thu_chi", "tai_chinh", "margin", "ebitda",
            "cong_no", "roi", "dong_tien", "cash",
        ),
    ),
    "priority_customers": (
        "Khách hàng Ưu tiên & Phân nhóm VIP",
        (
            "khach_hang", "customer", "client", "vip", "tier", "rfm", "doanh_so", "don_hang",
            "order", "ltv", "churn", "uu_tien", "phan_khuc", "segment", "doi_tac", "tan_suat",
        ),
    ),
    "project_kpi": (
        "Phân tích Dự án & Cây KPI / MG",
        (
            "du_an", "project", "kpi", "okr", "mg", "muc_tieu", "target", "ke_hoach", "tien_do",
            "progress", "milestone", "deadline", "nhiem_vu", "task", "rui_ro", "risk", "hieu_suat",
            "hoan_thanh", "sla",
        ),
    ),
    "classification": (
        "Trình phân loại & Gom nhóm Đa chiều",
        (
            "phan_loai", "nhom", "category", "group", "class", "phong_ban", "khu_vuc",
            "danh_muc", "nguon", "kenh",
        ),
    ),
}

_REVENUE_KEYS = ("doanh_thu", "doanh_so", "revenue", "sales", "thu_nhap", "income", "tong_thu")
_COST_KEYS = ("chi_phi", "cost", "expense", "gia_von", "tong_chi", "thuc_chi", "spent")
_PROFIT_KEYS = ("loi_nhuan", "profit", "ebitda", "lai_rong", "net_income")
_PROGRESS_KEYS = ("tien_do", "progress", "hoan_thanh", "completion", "kpi", "ty_le_dat", "dat_duoc")
_STATUS_KEYS = ("trang_thai", "status", "tinh_trang", "xep_loai", "ket_qua", "muc_do", "tier")
_ENTITY_KEYS = (
    "khach_hang", "customer", "client", "ten_du_an", "du_an", "project", "ten", "name",
    "san_pham", "product", "phong_ban", "department", "khu_vuc", "region", "doi_tac", "hang_muc",
)


# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------

def _kw_in_norm(kw: str, norm_text: str) -> bool:
    """Match keyword in normalized text. Short keywords (<=3 chars) must match a whole token."""
    if not kw or not norm_text:
        return False
    if len(kw) <= 3:
        return kw in norm_text.split("_") or kw in norm_text.split()
    if kw in norm_text:
        return True
    kw_flat = kw.replace("_", "")
    return len(kw_flat) >= 4 and kw_flat in norm_text.replace("_", "")


def _cell_unit(txt: str) -> Optional[str]:
    m = _UNIT_RE.search((txt or "").strip().lower())
    if not m:
        return None
    word = m.group(1)
    if word in ("tỷ", "tỉ", "ty"):
        return "ty"
    if word in ("triệu", "trieu"):
        return "trieu"
    return "nghin"


def _extract_stat_number(col_name: str, raw_val: Any) -> Optional[float]:
    """Extract numeric metric only when cell is genuinely statistical (skip dates, IDs, phones)."""
    if raw_val is None or isinstance(raw_val, bool):
        return None
    if isinstance(raw_val, (int, float)):
        return float(raw_val)
    txt = str(raw_val).strip()
    if not txt:
        return None
    if _DATE_RE.match(txt) or _CODE_RE.match(txt) or _PHONE_RE.match(txt):
        return None
    nk = norm_key(col_name)
    if any(nk == h or nk.startswith(h) for h in _NON_METRIC_COL_HINTS):
        return None
    if re.search(r"[a-zA-Z]", txt) and not re.search(
        r"(ty|tỷ|tỉ|trieu|triệu|nghin|nghìn|ngan|ngàn|vnd|vnđ|usd|đồng|dong|%|gio|giờ|ngay|ngày|thang|tháng|nam|năm|cai|cái|don|đơn|sp|kh|nv|m2|kg)$",
        txt.lower(),
    ):
        if not re.match(r"^\s*[-+]?\d+(?:[.,]\d+)?\s*/\s*10\s*$", txt):
            return None
    return parse_number(txt)


def _unified_numeric_column(rows: List[Dict[str, Any]], col: str) -> Tuple[List[Optional[float]], Optional[str]]:
    """Numeric values aligned to rows. Mixed units (tỷ / triệu / nghìn) are converted to the smallest unit."""
    raw: List[Tuple[Optional[float], Optional[str]]] = []
    units = set()
    for r in rows:
        v = str(r.get(col, "")).strip()
        n = _extract_stat_number(col, v) if v else None
        u = _cell_unit(v) if n is not None else None
        raw.append((n, u))
        if u:
            units.add(u)
    if len(units) >= 2:
        base = min(units, key=lambda u: _UNIT_RANK[u])
        out = [
            (n * (_UNIT_RANK[u] / _UNIT_RANK[base]) if (n is not None and u) else n)
            for n, u in raw
        ]
        return out, f"quy đổi về {_UNIT_LABEL[base]}"
    return [n for n, _ in raw], None


def _is_groupable(col: str, vals: List[str], n_rows: int) -> bool:
    if not vals:
        return False
    nk = norm_key(col)
    if any(nk == h or nk.startswith(h) for h in _NON_GROUP_COL_HINTS):
        return False
    date_like = sum(1 for v in vals if _DATE_RE.match(v) or _CODE_RE.match(v))
    if date_like >= 0.6 * len(vals):
        return False
    if sum(len(v) for v in vals) / len(vals) > 40:
        return False
    if n_rows >= 3 and len(set(vals)) == len(vals):
        return False  # identifier-like column
    return True


def _describe(nums: List[float]) -> Dict[str, Any]:
    med = statistics.median(nums)
    std = statistics.pstdev(nums) if len(nums) > 1 else 0.0
    outliers: List[float] = []
    if len(nums) >= 4:
        q = statistics.quantiles(nums, n=4, method="inclusive")
        q1, q3 = q[0], q[2]
        iqr = q3 - q1
        if iqr > 0:
            lo, hi = q1 - 1.5 * iqr, q3 + 1.5 * iqr
            outliers = [x for x in nums if x < lo or x > hi]
    return {
        "count": len(nums),
        "sum": round(sum(nums), 2),
        "avg": round(sum(nums) / len(nums), 2),
        "median": round(med, 2),
        "std": round(std, 2),
        "min": round(min(nums), 2),
        "max": round(max(nums), 2),
        "outlier_count": len(outliers),
        "outliers": [round(x, 2) for x in sorted(outliers, key=abs, reverse=True)[:3]],
    }


# ---------------------------------------------------------------------------
# Domain detection, prompt filter
# ---------------------------------------------------------------------------

def _detect_analysis_domain(
    analysis_goal: str,
    user_prompt: str,
    table_summaries: List[Dict[str, Any]],
    document_texts: Dict[str, List[str]],
) -> Tuple[str, str]:
    goal = (analysis_goal or "auto").strip().lower()
    if goal in DOMAIN_HINTS:
        return goal, DOMAIN_HINTS[goal][0]

    prompt_norm = norm_key(user_prompt)
    header_corpus = " ".join(norm_key(h) for t in table_summaries for h in t.get("headers", []))
    table_corpus = " ".join(norm_key(t.get("sheet_name", "")) for t in table_summaries)
    doc_corpus = " ".join(norm_key(p) for lines in document_texts.values() for p in lines[:20])
    kv_corpus = " ".join(
        norm_key(m["label"]) for t in table_summaries for m in (t.get("kv_metrics") or [])
    )
    combined = f"{header_corpus} {table_corpus} {doc_corpus} {kv_corpus}"

    scores: Dict[str, int] = {}
    for dom, (_, keywords) in DOMAIN_HINTS.items():
        s = sum(3 for kw in keywords if _kw_in_norm(kw, prompt_norm))
        s += sum(1 for kw in keywords if _kw_in_norm(kw, combined))
        scores[dom] = s

    best = max(scores, key=lambda k: scores[k]) if scores else "general_statistics"
    if scores.get(best, 0) == 0:
        if any(t.get("numeric_stats") or t.get("kv_metrics") for t in table_summaries):
            return "general_statistics", "Phân tích & Thống kê Dữ liệu Tổng hợp"
        return "classification", "Phân loại & Tổng hợp Tài liệu"
    return best, DOMAIN_HINTS[best][0]


def _pick_best_column(headers: List[str], candidates: Tuple[str, ...], preferred_pool: Optional[set] = None) -> Optional[str]:
    for h in headers:
        if preferred_pool is not None and h not in preferred_pool:
            continue
        nh = norm_key(h)
        if any(_kw_in_norm(kw, nh) for kw in candidates):
            return h
    return None


def _apply_user_prompt_filter(
    cleaned_sheets: Dict[str, List[Dict[str, Any]]],
    user_prompt: str,
) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """Apply the customer's own request: numeric threshold (> 100) and/or focus keywords."""
    prompt = (user_prompt or "").strip()
    if not prompt:
        return [], None

    prompt_norm = norm_key(prompt)
    m_thr = re.search(r"(>=|<=|>|<|trên|tren|dưới|duoi)\s*([-+]?\d+(?:[.,]\d+)?)", prompt.lower())
    op: Optional[str] = None
    thr_val: Optional[float] = None
    if m_thr:
        raw_op = m_thr.group(1)
        op = ">=" if raw_op == ">=" else "<=" if raw_op == "<=" else ">" if raw_op in (">", "trên", "tren") else "<"
        thr_val = float(m_thr.group(2).replace(",", "."))

    stop = {
        "phan", "loai", "nhom", "thong", "ke", "du", "an", "cay", "kpi", "mg", "tai", "chinh",
        "khach", "hang", "uu", "tien", "theo", "cac", "cua", "cho", "toi", "va", "voi", "tren",
        "duoi", "loc", "lay", "xem", "bang", "bao", "cao",
    }
    search_tokens = [t for t in prompt_norm.split("_") if len(t) >= 3 and t not in stop and not t.isdigit()]

    matches: List[Dict[str, Any]] = []
    for s_name, rows in cleaned_sheets.items():
        if not rows:
            continue
        headers = [k for k in rows[0].keys() if not str(k).startswith("_")]
        target_col: Optional[str] = None
        target_vals: List[Optional[float]] = []
        if thr_val is not None:
            for h in headers:
                if _kw_in_norm(norm_key(h), prompt_norm):
                    vals, _ = _unified_numeric_column(rows, h)
                    if any(v is not None for v in vals):
                        target_col, target_vals = h, vals
                        break
            if target_col is None:
                for h in headers:
                    vals, _ = _unified_numeric_column(rows, h)
                    if sum(v is not None for v in vals) >= max(1, len(rows) // 2):
                        target_col, target_vals = h, vals
                        break

        for idx, r in enumerate(rows):
            reasons: List[str] = []
            if thr_val is not None and target_col is not None:
                n = target_vals[idx]
                if n is not None:
                    ok = (n > thr_val) if op == ">" else (n >= thr_val) if op == ">=" else (n < thr_val) if op == "<" else (n <= thr_val)
                    if ok:
                        reasons.append(f"{target_col} {op} {thr_val:g} (thực tế: {n:g})")
            if search_tokens:
                row_txt = norm_key(" ".join(str(r.get(h, "")) for h in headers))
                hits = [t for t in search_tokens if t in row_txt.split("_") or t in row_txt]
                if hits:
                    reasons.append(f"khớp từ khóa: {', '.join(hits[:3])}")
            if reasons:
                label = next((str(r.get(h, "")).strip() for h in headers if str(r.get(h, "")).strip()), f"{s_name}#{r.get('_row_number', '')}")
                matches.append(
                    {
                        "table": s_name,
                        "row_label": label,
                        "reason": "; ".join(reasons),
                        "row_preview": {h: r.get(h, "") for h in headers[:6]},
                    }
                )

    note = f'Áp dụng yêu cầu của bạn: "{prompt}" — {len(matches)} bản ghi khớp.'
    return matches[:30], note


# ---------------------------------------------------------------------------
# Financial / project summaries, classifiers, KPI tree
# ---------------------------------------------------------------------------

def _compute_financial_and_project_summaries(
    cleaned_sheets: Dict[str, List[Dict[str, Any]]],
    table_summaries: List[Dict[str, Any]],
) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    total_rev = total_cost = total_profit = 0.0
    rev_col = cost_col = profit_col = None

    progress_vals: List[float] = []
    progress_col = None
    total_projects = completed = at_risk = on_track = 0

    kv_rev = 0.0
    kv_cost = 0.0
    kv_profit = 0.0
    has_kv_rev = has_kv_cost = has_kv_profit = False

    for t in table_summaries:
        s_name = t["sheet_name"]
        rows = cleaned_sheets.get(s_name) or []

        if t.get("is_kv"):
            # Key:Value metrics extracted from Word / PDF / text (used when structured tables don't have financial columns)
            for m in t.get("kv_metrics") or []:
                nk = norm_key(m["label"])
                num = m.get("number")
                if num is None:
                    continue
                if any(_kw_in_norm(k, nk) for k in _PROFIT_KEYS):
                    kv_profit += num
                    has_kv_profit = True
                elif any(_kw_in_norm(k, nk) for k in _COST_KEYS):
                    kv_cost += num
                    has_kv_cost = True
                elif any(_kw_in_norm(k, nk) for k in _REVENUE_KEYS):
                    kv_rev += num
                    has_kv_rev = True
            continue

        headers = t.get("headers", [])
        num_set = {ns["column"] for ns in t.get("numeric_stats", [])}
        r_col = _pick_best_column(headers, _REVENUE_KEYS, num_set)
        c_col = _pick_best_column(headers, _COST_KEYS, num_set)
        p_col = _pick_best_column(headers, _PROFIT_KEYS, num_set)
        prg_col = _pick_best_column(headers, _PROGRESS_KEYS, num_set)
        st_col = _pick_best_column(headers, _STATUS_KEYS)

        if r_col:
            rev_col = rev_col or r_col
            total_rev += sum(v for v in _unified_numeric_column(rows, r_col)[0] if v is not None)
        if c_col:
            cost_col = cost_col or c_col
            total_cost += sum(v for v in _unified_numeric_column(rows, c_col)[0] if v is not None)
        if p_col:
            profit_col = profit_col or p_col
            total_profit += sum(v for v in _unified_numeric_column(rows, p_col)[0] if v is not None)

        project_like = any(_kw_in_norm(k, norm_key(h)) for h in headers for k in ("du_an", "project", "task", "nhiem_vu"))
        if prg_col or (st_col and project_like):
            total_projects += len(rows)
            prg_vals = _unified_numeric_column(rows, prg_col)[0] if prg_col else [None] * len(rows)
            if prg_col:
                progress_col = progress_col or prg_col
            for idx, r in enumerate(rows):
                st_norm = norm_key(str(r.get(st_col, ""))) if st_col else ""
                pv = prg_vals[idx]
                if pv is not None:
                    progress_vals.append(pv)
                is_done = any(k in st_norm for k in ("hoan_thanh", "done", "completed", "xong")) or (pv is not None and pv >= 100.0)
                is_risk = any(k in st_norm for k in ("cham", "tre", "delay", "rui_ro", "risk", "vuot", "loi", "blocked")) or (pv is not None and pv < 50.0)
                if is_done:
                    completed += 1
                elif is_risk:
                    at_risk += 1
                else:
                    on_track += 1

    if not rev_col and not cost_col and not profit_col:
        if has_kv_rev:
            total_rev = kv_rev
            rev_col = "Chỉ tiêu văn bản"
        if has_kv_cost:
            total_cost = kv_cost
            cost_col = "Chỉ tiêu văn bản"
        if has_kv_profit:
            total_profit = kv_profit
            profit_col = "Chỉ tiêu văn bản"

    fin_summary = None
    if rev_col or cost_col or profit_col:
        net = round(total_profit if profit_col else (total_rev - total_cost), 2)
        margin = round(net * 100.0 / total_rev, 1) if total_rev > 0 and (cost_col or profit_col) else None
        fin_summary = {
            "total_revenue": round(total_rev, 2) if rev_col else None,
            "total_cost": round(total_cost, 2) if cost_col else None,
            "net_profit": net if (profit_col or (rev_col and cost_col)) else None,
            "margin_pct": margin,
            "revenue_col": rev_col,
            "cost_col": cost_col,
            "profit_col": profit_col,
        }

    proj_summary = None
    if total_projects > 0:
        proj_summary = {
            "total_projects": total_projects,
            "avg_progress_pct": round(sum(progress_vals) / len(progress_vals), 1) if progress_vals else None,
            "progress_col": progress_col,
            "completed_count": completed,
            "on_track_count": on_track,
            "at_risk_count": at_risk,
        }
    return fin_summary, proj_summary


def _build_classifiers_and_priorities(
    cleaned_sheets: Dict[str, List[Dict[str, Any]]],
    table_summaries: List[Dict[str, Any]],
    user_prompt: str,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """ABC priority ranking (per table, never mixing different metrics) + multi-dimension group classifiers."""
    classifiers: List[Dict[str, Any]] = []
    priority_entities: List[Dict[str, Any]] = []
    prompt_norm = norm_key(user_prompt)

    for t in table_summaries:
        if t.get("is_kv"):
            continue
        s_name = t["sheet_name"]
        rows = cleaned_sheets.get(s_name) or []
        headers = t.get("headers", [])
        num_stats = t.get("numeric_stats", [])
        if not rows or not headers:
            continue
        num_set = {ns["column"] for ns in num_stats}

        entity_col = _pick_best_column(headers, _ENTITY_KEYS)
        if not entity_col:
            entity_col = next((h for h in headers if h not in num_set), headers[0])

        metric_col: Optional[str] = None
        if num_stats:
            for ns in num_stats:
                if _kw_in_norm(norm_key(ns["column"]), prompt_norm):
                    metric_col = ns["column"]
                    break
            if not metric_col:
                metric_col = _pick_best_column(headers, _REVENUE_KEYS + _PROFIT_KEYS + _PROGRESS_KEYS, num_set)
            if not metric_col:
                metric_col = max(num_stats, key=lambda x: abs(x["sum"]))["column"]

        group_cols = [c["column"] for c in t.get("category_stats", []) if c["column"] != entity_col and c.get("groupable", True)]
        status_col = _pick_best_column(headers, _STATUS_KEYS)
        metric_vals: List[Optional[float]] = []
        metric_note: Optional[str] = None
        if metric_col:
            metric_vals, metric_note = _unified_numeric_column(rows, metric_col)

        # --- ABC priority ranking inside this table
        if metric_col and entity_col and entity_col != metric_col:
            totals: Dict[str, float] = defaultdict(float)
            groups: Dict[str, str] = {}
            statuses: Dict[str, str] = {}
            for idx, r in enumerate(rows):
                ename = str(r.get(entity_col, "")).strip()
                mval = metric_vals[idx]
                if not ename or mval is None:
                    continue
                totals[ename] += mval
                if group_cols and ename not in groups:
                    groups[ename] = str(r.get(group_cols[0], "")).strip()
                if status_col and ename not in statuses:
                    statuses[ename] = str(r.get(status_col, "")).strip()

            ranked = sorted(totals.items(), key=lambda kv: kv[1], reverse=True)
            pos_sum = sum(max(v, 0.0) for _, v in ranked) or 1.0
            cum = 0.0
            tier_counts: Counter = Counter()
            tier_sums: Dict[str, float] = defaultdict(float)
            for idx, (ename, val) in enumerate(ranked, start=1):
                cum += max(val, 0.0)
                cum_pct = cum * 100.0 / pos_sum
                tier = "Nhóm A · Ưu tiên #1" if (idx == 1 or cum_pct <= 75.0) else "Nhóm B · Tiềm năng" if cum_pct <= 92.0 else "Nhóm C · Theo dõi"
                tier_counts[tier] += 1
                tier_sums[tier] += val
                if idx <= 10:
                    priority_entities.append(
                        {
                            "rank": idx,
                            "table": s_name,
                            "name": ename,
                            "tier": tier,
                            "value": round(val, 2),
                            "metric_value": round(val, 2),
                            "metric_col": metric_col,
                            "metric_label": metric_col + (f" ({metric_note})" if metric_note else ""),
                            "share_pct": round(max(val, 0.0) * 100.0 / pos_sum, 1),
                            "group_label": groups.get(ename, ""),
                            "status_badge": statuses.get(ename, ""),
                        }
                    )
            if ranked:
                classifiers.append(
                    {
                        "sheet_name": s_name,
                        "title": f"Phân hạng Ưu tiên ABC ({s_name})",
                        "group_name": f"Phân hạng Ưu tiên ABC ({s_name})",
                        "dimension": f"{entity_col} theo {metric_col}",
                        "total_items": len(ranked),
                        "metric_name": metric_col,
                        "metric_column": metric_col,
                        "groups": [
                            {
                                "label": name,
                                "count": tier_counts[name],
                                "share_pct": round(tier_counts[name] * 100.0 / len(ranked), 1),
                                "metric_sum": round(tier_sums[name], 2),
                                "metric_avg": round(tier_sums[name] / tier_counts[name], 2),
                                "priority_tag": "VIP / Cao" if "Nhóm A" in name else "Trung bình" if "Nhóm B" in name else "Cơ bản",
                            }
                            for name in ("Nhóm A · Ưu tiên #1", "Nhóm B · Tiềm năng", "Nhóm C · Theo dõi")
                            if tier_counts[name] > 0
                        ],
                    }
                )

        # --- Group-by classifiers (multi-dimensional: up to 4 dimensions per table)
        ordered = sorted(group_cols[:6], key=lambda c: (0 if _kw_in_norm(norm_key(c), prompt_norm) else 1, c))
        for g_col in ordered[:4]:
            counts: Dict[str, int] = defaultdict(int)
            sums: Dict[str, float] = defaultdict(float)
            for idx, r in enumerate(rows):
                gval = str(r.get(g_col, "")).strip() or "(Trống)"
                counts[gval] += 1
                if metric_col and metric_vals and metric_vals[idx] is not None:
                    sums[gval] += metric_vals[idx]  # type: ignore[operator]
            total_cnt = sum(counts.values()) or 1
            sorted_g = sorted(counts.items(), key=lambda kv: (sums.get(kv[0], 0.0), kv[1]), reverse=True)[:8]
            classifiers.append(
                {
                    "sheet_name": s_name,
                    "title": f"Phân nhóm theo {g_col} ({s_name})",
                    "group_name": f"Phân nhóm theo {g_col} ({s_name})",
                    "dimension": g_col,
                    "total_items": total_cnt,
                    "metric_name": metric_col or "Số bản ghi",
                    "metric_column": metric_col or "Số bản ghi",
                    "groups": [
                        {
                            "label": lbl,
                            "count": cnt,
                            "share_pct": round(cnt * 100.0 / total_cnt, 1),
                            "metric_sum": round(sums[lbl], 2) if metric_col else cnt,
                            "metric_avg": round(sums[lbl] / cnt, 2) if metric_col else 1.0,
                            "priority_tag": "Trọng tâm" if i == 0 else "Nhóm phụ",
                        }
                        for i, (lbl, cnt) in enumerate(sorted_g)
                    ],
                }
            )

    return classifiers[:12], priority_entities[:24]


def _build_kpi_mg_tree(
    domain: str,
    domain_label: str,
    user_prompt: str,
    fin_summary: Optional[Dict[str, Any]],
    proj_summary: Optional[Dict[str, Any]],
    classifiers: List[Dict[str, Any]],
    priority_entities: List[Dict[str, Any]],
    all_numeric_highlights: List[Dict[str, Any]],
    total_rows_clean: int,
    quality: Dict[str, Any],
) -> Dict[str, Any]:
    branches: List[Dict[str, Any]] = []

    if fin_summary:
        kids = []
        if fin_summary.get("total_revenue") is not None:
            kids.append({"label": f"Tổng Thu ({fin_summary['revenue_col']})", "value": fin_summary["total_revenue"], "status": "GOOD"})
        if fin_summary.get("total_cost") is not None:
            kids.append({"label": f"Tổng Chi ({fin_summary['cost_col']})", "value": fin_summary["total_cost"], "status": "WATCH"})
        if fin_summary.get("net_profit") is not None:
            kids.append({"label": "Lợi nhuận ròng", "value": fin_summary["net_profit"], "status": "GOOD" if fin_summary["net_profit"] >= 0 else "RISK"})
        if fin_summary.get("margin_pct") is not None:
            kids.append({"label": "Biên lợi nhuận (%)", "value": f"{fin_summary['margin_pct']}%", "status": "GOOD" if fin_summary["margin_pct"] >= 15 else "WATCH"})
        branches.append(
            {
                "name": "KPI Tài chính & Hiệu quả",
                "owner": "Tài chính / Kế toán",
                "summary": f"Thu: {fin_summary.get('total_revenue', '--')} · Biên: {fin_summary.get('margin_pct', '--')}%",
                "status": "RISK" if (fin_summary.get("net_profit") or 0) < 0 else "GOOD",
                "children": kids,
            }
        )

    if proj_summary:
        kids = [
            {"label": "Tổng dự án / hạng mục", "value": proj_summary["total_projects"], "status": "GOOD"},
            {"label": "Hoàn thành / Đúng hạn", "value": proj_summary["completed_count"] + proj_summary["on_track_count"], "status": "GOOD"},
            {"label": "Cần chú ý / Rủi ro", "value": proj_summary["at_risk_count"], "status": "RISK" if proj_summary["at_risk_count"] > 0 else "GOOD"},
        ]
        if proj_summary.get("avg_progress_pct") is not None:
            kids.insert(1, {"label": f"Tiến độ TB ({proj_summary['progress_col']})", "value": f"{proj_summary['avg_progress_pct']}%", "status": "GOOD" if proj_summary["avg_progress_pct"] >= 70 else "WATCH"})
        branches.append(
            {
                "name": "KPI Tiến độ & Rủi ro Dự án",
                "owner": "PMO / Quản lý Dự án",
                "summary": f"{proj_summary['total_projects']} hạng mục · {proj_summary['at_risk_count']} rủi ro",
                "status": "RISK" if proj_summary["at_risk_count"] > 0 else "GOOD",
                "children": kids,
            }
        )

    if priority_entities:
        top_a = [e for e in priority_entities if "Nhóm A" in e["tier"]]
        branches.append(
            {
                "name": "KPI Trọng tâm & Đối tượng Ưu tiên (Nhóm A)",
                "owner": "Kinh doanh / CSKH",
                "summary": f"{len(top_a)} mục Nhóm A · Dẫn đầu: {priority_entities[0]['name']}",
                "status": "GOOD",
                "children": [
                    {
                        "label": f"#{e['rank']} {e['name']} ({e['tier']})",
                        "value": f"{e['value']} ({e['share_pct']}%)",
                        "status": "GOOD" if "Nhóm A" in e["tier"] else "WATCH",
                    }
                    for e in priority_entities[:4]
                ],
            }
        )

    if all_numeric_highlights or classifiers:
        kids = [
            {"label": f"{ns['column']} ({ns['table']})", "value": f"Σ {ns['sum']} · TB {ns['avg']}", "status": "GOOD"}
            for ns in all_numeric_highlights[:4]
        ]
        for cl in classifiers[:2]:
            if cl["groups"]:
                g = cl["groups"][0]
                kids.append({"label": f"{cl['dimension']}: {g['label']}", "value": f"{g['count']} ({g['share_pct']}%)", "status": "GOOD"})
        if kids:
            branches.append(
                {
                    "name": "KPI Cơ cấu & Phân nhóm Chính",
                    "owner": "Vận hành / Phân tích",
                    "summary": f"{total_rows_clean} dòng sạch · {len(classifiers)} trình phân loại",
                    "status": "GOOD",
                    "children": kids[:5],
                }
            )

    comp = quality.get("completeness_pct", 100.0)
    branches.append(
        {
            "name": "KPI Chất lượng Dữ liệu",
            "owner": "Quản trị dữ liệu",
            "summary": f"Đầy đủ {comp}% · loại {quality.get('dedup', 0)} trùng · {quality.get('outliers', 0)} ngoại lai",
            "status": "GOOD" if comp >= 90 and quality.get("outliers", 0) == 0 else "WATCH",
            "children": [
                {"label": "Độ đầy đủ dữ liệu", "value": f"{comp}%", "status": "GOOD" if comp >= 90 else "WATCH"},
                {"label": "Dòng trùng đã loại", "value": quality.get("dedup", 0), "status": "GOOD"},
                {"label": "Dòng trống đã loại", "value": quality.get("empty_rows", 0), "status": "GOOD"},
                {"label": "Giá trị ngoại lai phát hiện", "value": quality.get("outliers", 0), "status": "WATCH" if quality.get("outliers", 0) else "GOOD"},
            ],
        }
    )

    root = {
        "financial": "MG Tài chính: Tối đa Lợi nhuận & Kiểm soát Chi phí",
        "priority_customers": "MG Khách hàng: Giữ chân Nhóm A & Mở rộng Tiềm năng",
        "project_kpi": "MG Dự án: Đảm bảo Tiến độ & Mục tiêu KPI",
        "classification": "MG Phân loại: Chuẩn hóa Nhóm & Trọng tâm Dữ liệu",
        "general_statistics": "MG Tổng hợp: Giám sát Chỉ số Hoạt động Công ty",
    }
    return {
        "title": f"Cây KPI / Mục tiêu Quản trị (MG) — {domain_label}",
        "goal_name": root.get(domain, "MG Tổng hợp Dữ liệu"),
        "user_focus": user_prompt or "Tự động trích xuất từ dữ liệu thực tế",
        "branches": branches,
    }


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def run_company_statistics_pipeline(
    raw_sheets: Dict[str, List[Dict[str, Any]]],
    audit: AuditLogger,
    source_metadata: Optional[List[Dict[str, Any]]] = None,
    document_texts: Optional[Dict[str, List[str]]] = None,
    analysis_goal: str = "auto",
    user_prompt: str = "",
    cleaning_rules: Optional[Dict[str, Any]] = None,
    business_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    source_metadata = source_metadata or []
    document_texts = document_texts or {}
    rules = cleaning_rules or {}
    trim_ws = rules.get("trim_whitespace", True) is not False
    drop_empty = rules.get("drop_empty_rows", True) is not False
    drop_dups = rules.get("drop_duplicates", True) is not False
    drop_missing = bool(rules.get("drop_missing_rows", False))
    biz_ctx = business_context or {}

    dedup_log: List[Dict[str, Any]] = []
    cleaned_sheets: Dict[str, List[Dict[str, Any]]] = {}
    table_summaries: List[Dict[str, Any]] = []

    total_rows_raw = total_rows_clean = total_missing_cells = total_cells = 0
    empty_rows_removed = normalized_cells = unit_conversions = missing_rows_removed = trimmed_cells = 0
    all_numeric: List[Dict[str, Any]] = []
    all_categories: List[Dict[str, Any]] = []

    for s_name, rows in raw_sheets.items():
        if not rows:
            continue
        raw_cnt = len(rows)
        total_rows_raw += raw_cnt
        headers = [str(k) for k in rows[0].keys() if not str(k).startswith("_")]
        if not headers:
            continue

        seen = set()
        kept: List[Dict[str, Any]] = []
        sheet_dropped = 0
        sheet_missing_cells = 0
        for idx, r in enumerate(rows, start=1):
            clean_vals: Dict[str, str] = {}
            non_empty = 0
            for h in headers:
                v = r.get(h, "")
                raw_s = str(v) if v is not None else ""
                s_v = raw_s.strip() if trim_ws else raw_s
                if trim_ws and raw_s and s_v != raw_s:
                    trimmed_cells += 1
                if s_v.lower() in {"nan", "none", "null"}:
                    s_v = ""
                if s_v != "":
                    non_empty += 1
                clean_vals[h] = s_v
            if drop_empty and non_empty == 0:
                empty_rows_removed += 1
                sheet_dropped += 1
                continue
            if drop_missing and non_empty < len(headers):
                missing_rows_removed += 1
                sheet_dropped += 1
                continue
            if drop_dups:
                fp = json.dumps(clean_vals, sort_keys=True, ensure_ascii=False)
                if fp in seen:
                    dedup_log.append(
                        {
                            "dropped_record_id": f"{s_name}#{r.get('_row_number', idx)}",
                            "reason": f"Bản ghi trùng hoàn toàn trong bảng '{s_name}' (dòng {r.get('_row_number', idx)}) đã được loại tự động.",
                        }
                    )
                    sheet_dropped += 1
                    continue
                seen.add(fp)
            total_cells += len(headers)
            row_missing = len(headers) - non_empty
            total_missing_cells += row_missing
            sheet_missing_cells += row_missing
            kept.append(
                {
                    "_row_number": r.get("_row_number", idx),
                    "_source_file": r.get("_source_file", s_name),
                    "_sheet_name": s_name,
                    **clean_vals,
                }
            )
        if not kept:
            continue

        cleaned_sheets[s_name] = kept
        total_rows_clean += len(kept)
        source_file = kept[0].get("_source_file") or s_name

        # Key:Value metrics from Word / PDF / text are a metric list, not a data table.
        if set(headers) == KV_HEADERS:
            kv_metrics = [
                {
                    "label": kr["Chi_Tieu"],
                    "value": kr["Gia_Tri"],
                    "number": parse_number(kr["Gia_Tri"]),
                }
                for kr in kept
            ]
            table_summaries.append(
                {
                    "sheet_name": s_name,
                    "source_file": source_file,
                    "row_count": len(kept),
                    "column_count": 2,
                    "headers": ["Chi_Tieu", "Gia_Tri"],
                    "is_kv": True,
                    "kv_metrics": kv_metrics,
                    "numeric_stats": [],
                    "category_stats": [],
                    "preview_rows": [{"Chi_Tieu": m["label"], "Gia_Tri": m["value"]} for m in kv_metrics[:8]],
                }
            )
            continue

        numeric_cols: List[Dict[str, Any]] = []
        categorical_cols: List[Dict[str, Any]] = []
        for h in headers:
            vals, unit_note = _unified_numeric_column(kept, h)
            nums = [v for v in vals if v is not None]
            cats = [kr[h] for kr, v in zip(kept, vals) if v is None and kr.get(h, "") != ""]
            blanks = sum(1 for kr in kept if kr.get(h, "") == "")

            if nums and len(nums) >= max(1, len(kept) // 3):
                for kr, v in zip(kept, vals):
                    cell = kr.get(h, "")
                    if v is not None and cell and not re.fullmatch(r"[-+]?\d+(\.\d+)?", cell):
                        normalized_cells += 1
                if unit_note:
                    unit_conversions += 1
                stat = {"table": s_name, "column": h, "missing_count": blanks, "unit_note": unit_note}
                stat.update(_describe(nums))
                numeric_cols.append(stat)
                all_numeric.append(stat)
            elif cats:
                counter = Counter(cats)
                cat = {
                    "table": s_name,
                    "column": h,
                    "unique_count": len(counter),
                    "non_empty": len(cats),
                    "groupable": _is_groupable(h, cats, len(kept)),
                    "top_values": [
                        {"value": k, "count": cnt, "pct": round(cnt * 100.0 / len(kept), 1)}
                        for k, cnt in counter.most_common(6)
                    ],
                }
                categorical_cols.append(cat)
                all_categories.append(cat)

        table_summaries.append(
            {
                "sheet_name": s_name,
                "source_file": source_file,
                "raw_row_count": raw_cnt,
                "row_count": len(kept),
                "dropped_row_count": sheet_dropped,
                "missing_cells_count": sheet_missing_cells,
                "column_count": len(headers),
                "headers": headers,
                "numeric_stats": numeric_cols,
                "category_stats": categorical_cols,
                "preview_rows": [{h: kr.get(h, "") for h in headers} for kr in kept[:25]],
            }
        )

    has_doc_text = any(bool(lines) for lines in document_texts.values())
    if total_rows_clean == 0 and not has_doc_text:
        err = (
            "Làm sạch dữ liệu thất bại: Không còn dòng dữ liệu hợp lệ hoặc nội dung thống kê nào sau khi lọc dữ liệu trống. "
            "Vui lòng kiểm tra file dữ liệu và gửi lại."
        )
        audit.log(stage="STAGE_2_INGESTION", actor="TOOL", action="COMPANY_STATS_CLEAN_FAILED", detail=err, status="ERROR")
        return {"clean_ok": False, "error": err, "dedup_log": dedup_log}

    domain, domain_label = _detect_analysis_domain(analysis_goal, user_prompt, table_summaries, document_texts)
    fin, proj = _compute_financial_and_project_summaries(cleaned_sheets, table_summaries)
    classifiers, priority_entities = _build_classifiers_and_priorities(cleaned_sheets, table_summaries, user_prompt)
    prompt_matches, prompt_note = _apply_user_prompt_filter(cleaned_sheets, user_prompt)

    completeness = round(100.0 * (1.0 - total_missing_cells / total_cells), 1) if total_cells > 0 else 100.0
    outlier_total = sum(n.get("outlier_count", 0) for n in all_numeric)
    quality = {
        "completeness_pct": completeness,
        "dedup": len(dedup_log),
        "empty_rows": empty_rows_removed,
        "outliers": outlier_total,
    }
    kpi_tree = _build_kpi_mg_tree(
        domain, domain_label, user_prompt, fin, proj, classifiers, priority_entities, all_numeric, total_rows_clean, quality
    )

    unit_conversions_log: List[Dict[str, str]] = []
    quality_issues: List[Dict[str, Any]] = []
    for ns in all_numeric:
        if ns.get("unit_note"):
            unit_conversions_log.append(
                {
                    "sheet": ns["table"],
                    "column": ns["column"],
                    "note": ns["unit_note"],
                }
            )
        if ns.get("missing_count", 0) > 0:
            quality_issues.append(
                {
                    "type": "MISSING",
                    "sheet": ns["table"],
                    "column": ns["column"],
                    "detail": f"Thiếu {ns['missing_count']} giá trị (giữ nguyên, không tự tạo số liệu giả).",
                }
            )
        if ns.get("outlier_count", 0) > 0:
            outs = ", ".join(str(x) for x in (ns.get("outliers") or [])[:3])
            quality_issues.append(
                {
                    "type": "OUTLIER",
                    "sheet": ns["table"],
                    "column": ns["column"],
                    "detail": f"{ns['outlier_count']} giá trị bất thường ({outs}) so với trung vị {ns['median']}. Nên kiểm tra lại số liệu gốc.",
                }
            )

    bi_pipeline, process_steps, md_report = build_7stage_bi_pipeline_and_report(
        raw_sheets=raw_sheets,
        cleaned_sheets=cleaned_sheets,
        table_summaries=table_summaries,
        source_metadata=source_metadata,
        document_texts=document_texts,
        domain=domain,
        domain_label=domain_label,
        user_prompt=user_prompt,
        prompt_matches=prompt_matches,
        prompt_note=prompt_note,
        fin_summary=fin,
        proj_summary=proj,
        classifiers=classifiers,
        priority_entities=priority_entities,
        kpi_tree=kpi_tree,
        all_numeric=all_numeric,
        all_categories=all_categories,
        total_rows_raw=total_rows_raw,
        total_rows_clean=total_rows_clean,
        empty_rows_removed=empty_rows_removed,
        total_missing_cells=total_missing_cells,
        normalized_cells=normalized_cells,
        unit_conversions=unit_conversions,
        completeness_pct=completeness,
        dedup_log=dedup_log,
        quality_issues=quality_issues,
    )

    audit.log(
        stage="STAGE_2_INGESTION",
        actor="TOOL",
        action="COMPANY_STATS_CLEAN_OK",
        detail=f"Chuyên viên Hà Thuỳ Dương phân tích '{domain_label}': {len(table_summaries)} bảng ({total_rows_clean} dòng sạch), {len(classifiers)} trình phân loại, {len(bi_pipeline['stage4_charts'])} biểu đồ, {len(bi_pipeline['stage5_insights'])} Insight.",
        tool_result_summary={"domain": domain, "tables": len(table_summaries), "rows": total_rows_clean, "classifiers": len(classifiers)},
    )

    doc_cards = [
        {"source_file": name, "paragraph_count": len(paras), "paragraphs": paras[:30]}
        for name, paras in document_texts.items()
        if paras
    ]

    return {
        "clean_ok": True,
        "analyst_name": "Hà Thuỳ Dương",
        "analyst_role": "Chuyên viên Data Analyst & Business Intelligence",
        "domain_detected": domain,
        "domain_label": domain_label,
        "analysis_goal": analysis_goal,
        "user_prompt": user_prompt,
        "prompt_note": prompt_note,
        "prompt_matches": prompt_matches,
        "process_steps": process_steps,
        "quality": quality,
        "quality_issues": quality_issues,
        "unit_conversions": unit_conversions_log,
        "empty_rows_dropped": empty_rows_removed,
        "missing_rows_dropped": missing_rows_removed,
        "total_rows_dropped": total_rows_raw - total_rows_clean,
        "trimmed_cells_count": trimmed_cells,
        "cleaning_rules": {
            "trim_whitespace": trim_ws,
            "drop_empty_rows": drop_empty,
            "drop_duplicates": drop_dups,
            "drop_missing_rows": drop_missing,
        },
        "business_context": biz_ctx,
        "empty_cells_count": total_missing_cells,
        "numeric_cells_standardized": normalized_cells,
        "financial_summary": fin,
        "project_summary": proj,
        "kpi_tree": kpi_tree,
        "classifiers": classifiers,
        "priority_entities": priority_entities,
        "bi_pipeline": bi_pipeline,
        "total_tables": len(table_summaries),
        "total_sheets": len(table_summaries),
        "total_rows_raw": total_rows_raw,
        "total_rows_clean": total_rows_clean,
        "dedup_dropped_count": len(dedup_log),
        "completeness_pct": completeness,
        "dedup_log": dedup_log,
        "table_summaries": table_summaries,
        "numeric_highlights": all_numeric,
        "category_highlights": all_categories,
        "document_texts": doc_cards,
        "markdown_report": md_report,
        "_cleaned_sheets": cleaned_sheets,
    }

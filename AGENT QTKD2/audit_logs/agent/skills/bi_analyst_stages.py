"""7-Stage Senior Data Analyst & Business Intelligence Engine (Chuyên viên: Hà Thuỳ Dương).

Implements all 7 mandatory stages:
- Stage 1: Tiếp nhận và Kiểm tra dữ liệu (Sheet inventory, Data Dictionary, Initial Quality Assessment)
- Stage 2: Làm sạch và Tiền xử lý dữ liệu (Missing, Duplicates, Formats, IQR Outliers, Category Normalization, Invalid Values)
- Stage 3: Phân tích dữ liệu (Tổng quan, Theo thời gian, Theo nhóm, Hiệu suất, So sánh, Bất thường)
- Stage 4: Trực quan hóa dữ liệu (Column, Line, Pie, Bar, Pareto 80/20, Histogram, Combo)
- Stage 5: Phân tích Insight (DATA -> INFORMATION -> INSIGHT -> DECISION + 5 câu hỏi chuẩn)
- Stage 6: Đề xuất giải pháp (Vấn đề, Giải pháp, Bộ phận, KPI, Thứ tự ưu tiên, Rủi ro & Điều kiện)
- Stage 7: Báo cáo chuyên nghiệp 10 mục & Bàn giao 4 sản phẩm đầu ra
"""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from typing import Any, Dict, List, Optional, Tuple

from ..parsers import norm_key

ANALYST_NAME = "Hà Thuỳ Dương"
ANALYST_ROLE = "Chuyên viên Data Analyst & Business Intelligence"

_TIME_COL_HINTS = (
    "ngay", "date", "thoi_gian", "time", "thang", "month", "quy", "quarter",
    "nam", "year", "ky", "period", "created", "order_date", "invoice_date",
)

_ROLE_MAP: List[Tuple[str, str, Tuple[str, ...]]] = [
    ("Doanh thu / Giá trị", "Chỉ số tài chính cốt lõi phản ánh quy mô nguồn thu hoặc giá trị giao dịch", ("doanh_thu", "doanh_so", "revenue", "sales", "thanh_tien", "amount", "total", "tong_tien", "gia_tri", "price", "don_gia")),
    ("Chi phí / Giá vốn", "Chỉ số chi phí đầu vào, ngân sách hoặc giá vốn vận hành", ("chi_phi", "cost", "expense", "gia_von", "ngan_sach", "budget", "spent")),
    ("Lợi nhuận / Hiệu quả", "Chỉ số lãi ròng hoặc thặng dư tài chính sau khi trừ chi phí", ("loi_nhuan", "profit", "margin", "ebitda", "lai_rong", "net_income")),
    ("Số lượng / Quy mô", "Chỉ số đếm sản lượng, đơn hàng, nhân sự hoặc tần suất hoạt động", ("so_luong", "quantity", "qty", "count", "so_don", "orders", "nhan_su", "units", "volume")),
    ("Tiến độ / KPI (%)", "Chỉ số đo lường tỷ lệ hoàn thành mục tiêu hoặc mức độ đạt KPI", ("tien_do", "progress", "kpi", "hoan_thanh", "completion", "ty_le", "rate", "score", "diem")),
    ("Thời gian / Kỳ báo cáo", "Trường thời gian phục vụ phân tích xu hướng theo Ngày/Tháng/Quý/Năm", _TIME_COL_HINTS),
    ("Khách hàng / Đối tác", "Định danh hoặc phân nhóm khách hàng, đối tác kinh doanh", ("khach_hang", "customer", "client", "doi_tac", "partner", "buyer")),
    ("Sản phẩm / Dịch vụ", "Tên mặt hàng, dòng sản phẩm, gói giải pháp hoặc danh mục hàng hóa", ("san_pham", "product", "item", "hang_hoa", "dich_vu", "service", "sku", "category", "danh_muc")),
    ("Khu vực / Địa bàn", "Phân vùng địa lý, tỉnh thành, chi nhánh hoặc thị trường", ("khu_vuc", "region", "dia_ban", "location", "city", "tinh", "chi_nhanh", "branch", "area", "zone")),
    ("Nhân viên / Phòng ban", "Đơn vị phụ trách, phòng ban hoặc nhân sự thực hiện", ("nhan_vien", "staff", "sales_rep", "employee", "phong_ban", "department", "team", "owner", "pic")),
    ("Kênh bán / Nguồn", "Kênh phân phối, phương thức thanh toán hoặc nguồn tiếp cận", ("kenh", "channel", "source", "nguon", "payment", "phuong_thuc", "platform")),
    ("Trạng thái / Phân hạng", "Tình trạng xử lý, mức độ ưu tiên hoặc phân hạng đối tượng", ("trang_thai", "status", "tier", "hang", "muc_do", "segment", "phan_khuc", "nhom", "group")),
    ("Mã định danh (ID)", "Khóa định danh duy nhất cho bản ghi, giao dịch hoặc đối tượng", ("id", "ma_", "code", "stt", "order_id", "customer_id", "product_id")),
]


def _fmt_num(val: Any) -> str:
    if val is None or val == "":
        return "—"
    try:
        n = float(val)
    except Exception:
        return str(val)
    if abs(n - round(n)) < 1e-6:
        return f"{int(round(n)):,}".replace(",", ".")
    return f"{n:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _detect_column_role_and_meaning(col: str, is_numeric: bool, is_time: bool, unique_cnt: int, row_cnt: int) -> Tuple[str, str]:
    nk = norm_key(col)
    for role, meaning, kws in _ROLE_MAP:
        for kw in kws:
            if kw in nk.split("_") or (len(kw) >= 4 and kw in nk):
                return role, meaning
    if is_time:
        return "Thời gian / Kỳ báo cáo", "Trường thời gian dùng để theo dõi biến động qua các kỳ"
    if is_numeric:
        return "Chỉ số định lượng", f"Biến số định lượng dùng để tính tổng, trung bình, phân phối ({col})"
    if row_cnt >= 5 and unique_cnt == row_cnt:
        return "Mã định danh / Tên riêng", f"Trường định danh từng bản ghi hoặc đối tượng ({col})"
    if unique_cnt <= max(25, row_cnt // 2):
        return "Chiều phân nhóm (Dimension)", f"Trường phân loại dùng để gom nhóm và so sánh ({col})"
    return "Thông tin mô tả", f"Trường văn bản bổ sung thông tin chi tiết ({col})"


def _parse_period_token(raw_val: str) -> Optional[Tuple[str, str]]:
    """Parse common date/period strings into (normalized_period, granularity_label)."""
    s = (raw_val or "").strip()
    if not s:
        return None
    # ISO YYYY-MM-DD or YYYY/MM/DD
    m = re.match(r"^((?:19|20)\d{2})[-/](\d{1,2})(?:[-/](\d{1,2}))?", s)
    if m:
        y, mo = int(m.group(1)), int(m.group(2))
        if 1 <= mo <= 12:
            return f"{y:04d}-{mo:02d}", "Tháng (YYYY-MM)"
    # DD/MM/YYYY or DD-MM-YYYY
    m = re.match(r"^(\d{1,2})[-/](\d{1,2})[-/]((?:19|20)\d{2})", s)
    if m:
        d1, d2, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        mo = d2 if 1 <= d2 <= 12 else (d1 if 1 <= d1 <= 12 else 0)
        if mo:
            return f"{y:04d}-{mo:02d}", "Tháng (YYYY-MM)"
    # Quarter: Q1 2025, Quý 2/2025, 2025-Q3
    m = re.search(r"(?:q|quý|quy)\s*([1-4])\s*[-/, ]*\s*((?:19|20)\d{2})", s, re.I)
    if m:
        return f"{int(m.group(2))}-Q{int(m.group(1))}", "Quý (YYYY-Q)"
    m = re.search(r"((?:19|20)\d{2})\s*[-/ ]*\s*(?:q|quý|quy)\s*([1-4])", s, re.I)
    if m:
        return f"{int(m.group(1))}-Q{int(m.group(2))}", "Quý (YYYY-Q)"
    # Month/Year: Tháng 3/2025, T03-2025, 03/2025
    m = re.search(r"(?:tháng|thang|t)?\s*(\d{1,2})\s*[-/]\s*((?:19|20)\d{2})", s, re.I)
    if m and 1 <= int(m.group(1)) <= 12:
        return f"{int(m.group(2)):04d}-{int(m.group(1)):02d}", "Tháng (YYYY-MM)"
    # Standalone Year
    m = re.fullmatch(r"((?:19|20)\d{2})", s)
    if m:
        return m.group(1), "Năm (YYYY)"
    return None


def _build_time_series_analysis(
    cleaned_sheets: Dict[str, List[Dict[str, Any]]],
    table_summaries: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Stage 3.2: Detect time columns and compute period-by-period trend & growth."""
    for t in table_summaries:
        if t.get("is_kv"):
            continue
        s_name = t["sheet_name"]
        rows = cleaned_sheets.get(s_name) or []
        headers = t.get("headers") or []
        num_stats = t.get("numeric_stats") or []
        if len(rows) < 2 or not num_stats:
            continue

        # Pick primary numeric metric (Revenue > Profit > max sum)
        metric_col = num_stats[0]["column"]
        for ns in num_stats:
            nk = norm_key(ns["column"])
            if any(k in nk for k in ("doanh_thu", "doanh_so", "revenue", "sales", "thanh_tien", "amount", "total")):
                metric_col = ns["column"]
                break

        # Find best time column
        best_col = None
        best_gran = ""
        parsed_col_vals: List[Optional[str]] = []

        for h in headers:
            nh = norm_key(h)
            time_hint = any(k in nh.split("_") or (len(k) >= 4 and k in nh) for k in _TIME_COL_HINTS)
            sample_rows = rows[: min(len(rows), 300)]
            parsed_sample = [_parse_period_token(str(r.get(h, ""))) for r in sample_rows]
            valid_hits = [p for p in parsed_sample if p is not None]
            if valid_hits and (len(valid_hits) >= max(2, len(sample_rows) // 3) or time_hint):
                best_col = h
                best_gran = valid_hits[0][1]
                parsed_col_vals = [
                    (p[0] if p else None)
                    for p in (_parse_period_token(str(r.get(h, ""))) for r in rows)
                ]
                break

        if not best_col:
            continue

        # Aggregate metric by period
        by_period_sum: Dict[str, float] = defaultdict(float)
        by_period_cnt: Counter = Counter()
        for r, p_key in zip(rows, parsed_col_vals):
            if not p_key:
                continue
            raw_v = str(r.get(metric_col, "")).strip()
            try:
                val = float(re.sub(r"[^\d.-]", "", raw_v.replace(",", ""))) if raw_v else 0.0
            except Exception:
                val = 0.0
            by_period_sum[p_key] += val
            by_period_cnt[p_key] += 1

        if len(by_period_sum) < 2:
            continue

        sorted_periods = sorted(by_period_sum.keys())
        peak_val = max((abs(v) for v in by_period_sum.values()), default=1.0) or 1.0
        periods_out: List[Dict[str, Any]] = []
        prev_sum: Optional[float] = None
        for pk in sorted_periods:
            cur_sum = round(by_period_sum[pk], 2)
            mom = round((cur_sum - prev_sum) * 100.0 / abs(prev_sum), 1) if (prev_sum is not None and abs(prev_sum) > 1e-9) else None
            periods_out.append(
                {
                    "period": pk,
                    "count": by_period_cnt[pk],
                    "sum": cur_sum,
                    "mom_growth_pct": mom,
                    "pct_of_peak": round(abs(cur_sum) * 100.0 / peak_val, 1),
                }
            )
            prev_sum = cur_sum

        first_sum = periods_out[0]["sum"]
        last_sum = periods_out[-1]["sum"]
        overall_growth = round((last_sum - first_sum) * 100.0 / abs(first_sum), 1) if abs(first_sum) > 1e-9 else 0.0
        peak_pt = max(periods_out, key=lambda x: x["sum"])
        low_pt = min(periods_out, key=lambda x: x["sum"])

        # Compute period-over-period group drivers (last period vs previous period)
        period_drivers: Dict[str, Any] = {"available": False, "groups": []}
        if len(sorted_periods) >= 2:
            p_prev, p_last = sorted_periods[-2], sorted_periods[-1]
            cat_cols = [c for c in (t.get("category_stats") or []) if c.get("groupable", True)]
            if cat_cols:
                grp_col = cat_cols[0]["column"]
                prev_map: Dict[str, float] = defaultdict(float)
                last_map: Dict[str, float] = defaultdict(float)
                for r, p_key in zip(rows, parsed_col_vals):
                    if p_key not in (p_prev, p_last):
                        continue
                    g_val = str(r.get(grp_col, "")).strip() or "(Trống)"
                    raw_v = str(r.get(metric_col, "")).strip()
                    try:
                        val = float(re.sub(r"[^\d.-]", "", raw_v.replace(",", ""))) if raw_v else 0.0
                    except Exception:
                        val = 0.0
                    if p_key == p_prev:
                        prev_map[g_val] += val
                    else:
                        last_map[g_val] += val
                all_grps = set(prev_map.keys()) | set(last_map.keys())
                drv_list = []
                for g in all_grps:
                    delta = round(last_map[g] - prev_map[g], 2)
                    drv_list.append({"label": g, "prev": round(prev_map[g], 2), "curr": round(last_map[g], 2), "delta": delta})
                drv_list.sort(key=lambda x: abs(x["delta"]), reverse=True)
                period_drivers = {
                    "available": True,
                    "group_col": grp_col,
                    "prev_period": p_prev,
                    "curr_period": p_last,
                    "prev_total": round(by_period_sum[p_prev], 2),
                    "curr_total": round(by_period_sum[p_last], 2),
                    "total_delta": round(by_period_sum[p_last] - by_period_sum[p_prev], 2),
                    "groups": drv_list[:6],
                }

        return {
            "available": True,
            "sheet_name": s_name,
            "time_col": best_col,
            "granularity": best_gran,
            "metric_col": metric_col,
            "period_count": len(periods_out),
            "first_period": periods_out[0]["period"],
            "last_period": periods_out[-1]["period"],
            "overall_growth_pct": overall_growth,
            "peak_period": peak_pt,
            "low_period": low_pt,
            "periods": periods_out[:36],
            "period_drivers": period_drivers,
            "summary_note": (
                f"Chuỗi thời gian gồm {len(periods_out)} kỳ ({periods_out[0]['period']} → {periods_out[-1]['period']}) "
                f"theo '{best_col}': đỉnh cao nhất tại kỳ {peak_pt['period']} ({_fmt_num(peak_pt['sum'])}), "
                f"thấp nhất tại {low_pt['period']} ({_fmt_num(low_pt['sum'])}), "
                f"tăng trưởng kỳ cuối so với kỳ đầu: {overall_growth:+.1f}%."
            ),
        }

    return {
        "available": False,
        "summary_note": "Dữ liệu hiện có không chứa cột thời gian (Ngày/Tháng/Quý/Năm) đủ điều kiện để phân tích chuỗi thời gian; hệ thống tập trung phân tích chuyên sâu theo nhóm, hiệu suất và đối tượng.",
        "periods": [],
    }


def _build_stage4_charts(
    table_summaries: List[Dict[str, Any]],
    classifiers: List[Dict[str, Any]],
    priority_entities: List[Dict[str, Any]],
    time_analysis: Dict[str, Any],
    fin_summary: Optional[Dict[str, Any]],
    cleaned_sheets: Dict[str, List[Dict[str, Any]]],
) -> List[Dict[str, Any]]:
    """Stage 4: Auto-select appropriate chart types with clear titles, axes, units, and business meaning."""
    charts: List[Dict[str, Any]] = []

    # 1. Column Chart (Biểu đồ Cột): Compare metric across top groups
    if classifiers:
        c0 = classifiers[0]
        groups = c0.get("groups") or []
        if groups:
            metric_lbl = c0.get("metric_column") or "Số lượng bản ghi"
            max_v = max((abs(float(g.get("metric_sum", g.get("count", 0)))) for g in groups), default=1.0) or 1.0
            pts = [
                {
                    "label": g["label"],
                    "value": round(float(g.get("metric_sum", g.get("count", 0))), 2),
                    "count": g.get("count", 0),
                    "pct": g.get("share_pct", 0),
                    "height_pct": round(abs(float(g.get("metric_sum", g.get("count", 0)))) * 100.0 / max_v, 1),
                }
                for g in groups[:8]
            ]
            top_g = pts[0]
            charts.append(
                {
                    "chart_id": "chart_column_group",
                    "chart_type": "column",
                    "chart_type_label": "Biểu đồ Cột (Column Chart)",
                    "title": f"So sánh {metric_lbl} theo {c0['dimension']} ({c0['sheet_name']})",
                    "x_axis_label": f"Nhóm {c0['dimension']}",
                    "y_axis_label": f"{metric_lbl}",
                    "legend": f"Cột biểu thị tổng {metric_lbl} của từng nhóm {c0['dimension']}",
                    "data_points": pts,
                    "commentary": (
                        f"Nhóm dẫn đầu là '{top_g['label']}' đạt {_fmt_num(top_g['value'])} "
                        f"({top_g['pct']}% tổng tỷ trọng, {top_g['count']} bản ghi)."
                    ),
                    "business_meaning": (
                        f"Giúp nhận diện ngay phân khúc '{top_g['label']}' đang tạo ra đóng góp lớn nhất "
                        f"để ưu tiên phân bổ nguồn lực kinh doanh và ngân sách."
                    ),
                }
            )

    # 2. Line Chart (Biểu đồ Đường): Time-series trend (if available)
    if time_analysis.get("available") and time_analysis.get("periods"):
        periods = time_analysis["periods"]
        pts = [
            {
                "label": p["period"],
                "value": p["sum"],
                "secondary_value": p.get("mom_growth_pct"),
                "pct": p.get("pct_of_peak", 50.0),
            }
            for p in periods[:18]
        ]
        charts.append(
            {
                "chart_id": "chart_line_time",
                "chart_type": "line",
                "chart_type_label": "Biểu đồ Đường (Line Chart)",
                "title": f"Xu hướng {time_analysis['metric_col']} theo {time_analysis['granularity']}",
                "x_axis_label": f"Kỳ thời gian ({time_analysis['time_col']})",
                "y_axis_label": f"Tổng {time_analysis['metric_col']}",
                "legend": f"Đường xu hướng {time_analysis['metric_col']} qua {time_analysis['period_count']} kỳ",
                "data_points": pts,
                "commentary": time_analysis.get("summary_note", ""),
                "business_meaning": (
                    "Theo dõi tính chu kỳ, mùa vụ và tốc độ tăng trưởng qua từng giai đoạn để chủ động kế hoạch tồn kho, nhân sự và dòng tiền."
                ),
            }
        )

    # 3. Pie / Donut Chart (Biểu đồ Tròn): Proportion structure
    if classifiers:
        c_pie = classifiers[1] if len(classifiers) > 1 else classifiers[0]
        groups = c_pie.get("groups") or []
        if groups:
            pts = [
                {
                    "label": g["label"],
                    "value": round(float(g.get("metric_sum", g.get("count", 0))), 2),
                    "pct": g.get("share_pct", 0),
                }
                for g in groups[:6]
            ]
            top2_pct = round(sum(p["pct"] for p in pts[:2]), 1)
            charts.append(
                {
                    "chart_id": "chart_pie_share",
                    "chart_type": "pie",
                    "chart_type_label": "Biểu đồ Tròn (Pie / Donut Chart)",
                    "title": f"Cơ cấu Tỷ trọng (%) theo {c_pie['dimension']}",
                    "x_axis_label": f"Phân nhóm {c_pie['dimension']}",
                    "y_axis_label": "Tỷ trọng đóng góp (%)",
                    "legend": "Mỗi phần thể hiện % đóng góp trên tổng thể 100%",
                    "data_points": pts,
                    "commentary": f"2 nhóm đứng đầu chiếm tới {top2_pct}% tổng quy mô toàn bảng '{c_pie['sheet_name']}'.",
                    "business_meaning": "Đánh giá mức độ tập trung hay phân tán của cơ cấu danh mục để kiểm soát rủi ro phụ thuộc.",
                }
            )

    # 4. Pareto Chart (Biểu đồ Pareto 80/20) & Horizontal Bar Chart (Biểu đồ Thanh ngang)
    if priority_entities:
        cum = 0.0
        pts_pareto = []
        max_v = max((abs(float(e.get("metric_value", 0))) for e in priority_entities), default=1.0) or 1.0
        for e in priority_entities[:8]:
            cum = round(min(100.0, cum + float(e.get("share_pct", 0))), 1)
            pts_pareto.append(
                {
                    "label": str(e["name"]),
                    "value": round(float(e.get("metric_value", 0)), 2),
                    "pct": float(e.get("share_pct", 0)),
                    "cumulative_pct": cum,
                    "height_pct": round(abs(float(e.get("metric_value", 0))) * 100.0 / max_v, 1),
                    "tier": e.get("tier", ""),
                }
            )
        m_col = priority_entities[0].get("metric_col", "Giá trị")
        tbl = priority_entities[0].get("table", "")
        group_a_cnt = sum(1 for e in priority_entities if "Nhóm A" in str(e.get("tier", "")))
        charts.append(
            {
                "chart_id": "chart_pareto_abc",
                "chart_type": "pareto",
                "chart_type_label": "Biểu đồ Pareto (Cột + Đường tích lũy 80/20)",
                "title": f"Phân tích Pareto 80/20 & Xếp hạng Ưu tiên theo {m_col} ({tbl})",
                "x_axis_label": "Đối tượng / Khách hàng / Hạng mục",
                "y_axis_label": f"{m_col} & Tỷ trọng tích lũy (%)",
                "legend": "Cột: Giá trị từng đối tượng · Đường: Tỷ lệ đóng góp tích lũy (%)",
                "data_points": pts_pareto,
                "commentary": (
                    f"Dẫn đầu là '{pts_pareto[0]['label']}' chiếm {pts_pareto[0]['pct']}%. "
                    f"Nhóm A ({group_a_cnt} đối tượng đầu) quyết định phần lớn kết quả toàn bảng."
                ),
                "business_meaning": (
                    "Xác định nhóm 20% khách hàng/sản phẩm trọng yếu tạo ra ~80% giá trị để tập trung giữ chân và chăm sóc đặc biệt."
                ),
            }
        )
        charts.append(
            {
                "chart_id": "chart_bar_ranking",
                "chart_type": "bar",
                "chart_type_label": "Biểu đồ Thanh ngang (Horizontal Bar Chart)",
                "title": f"Xếp hạng Top Đối tượng theo {m_col} ({tbl})",
                "x_axis_label": f"Giá trị {m_col}",
                "y_axis_label": "Tên đối tượng xếp hạng",
                "legend": f"Thanh ngang xếp từ cao xuống thấp theo {m_col}",
                "data_points": pts_pareto[:6],
                "commentary": f"Khoảng cách giữa #{1} ({pts_pareto[0]['label']}) và phần còn lại thể hiện rõ thứ bậc ưu tiên.",
                "business_meaning": "Hỗ trợ nhà quản lý tra cứu nhanh bảng xếp hạng hiệu suất từng đối tượng/đơn vị.",
            }
        )

    # 5. Histogram (Biểu đồ Phân phối dữ liệu) for primary numeric column
    for t in table_summaries:
        if t.get("is_kv") or not t.get("numeric_stats"):
            continue
        ns0 = t["numeric_stats"][0]
        col = ns0["column"]
        rows = cleaned_sheets.get(t["sheet_name"]) or []
        vals: List[float] = []
        for r in rows:
            raw_v = str(r.get(col, "")).strip()
            try:
                vals.append(float(re.sub(r"[^\d.-]", "", raw_v.replace(",", ""))))
            except Exception:
                pass
        if len(vals) >= 4 and max(vals) > min(vals):
            lo, hi = min(vals), max(vals)
            bin_count = min(6, max(3, int(math.sqrt(len(vals)))))
            step = (hi - lo) / bin_count
            bins = [0] * bin_count
            for v in vals:
                b_idx = min(bin_count - 1, int((v - lo) / step))
                bins[b_idx] += 1
            max_b = max(bins) or 1
            hist_pts = []
            for i in range(bin_count):
                b_start = lo + i * step
                b_end = lo + (i + 1) * step
                hist_pts.append(
                    {
                        "label": f"{_fmt_num(round(b_start, 1))}–{_fmt_num(round(b_end, 1))}",
                        "value": bins[i],
                        "pct": round(bins[i] * 100.0 / len(vals), 1),
                        "height_pct": round(bins[i] * 100.0 / max_b, 1),
                    }
                )
            charts.append(
                {
                    "chart_id": "chart_histogram_dist",
                    "chart_type": "histogram",
                    "chart_type_label": "Biểu đồ Phân phối Tần suất (Histogram)",
                    "title": f"Phân phối tần suất của chỉ số '{col}' ({t['sheet_name']})",
                    "x_axis_label": f"Khoảng giá trị {col}",
                    "y_axis_label": "Số lượng bản ghi (Tần suất)",
                    "legend": f"Phân bố {len(vals)} bản ghi qua {bin_count} khoảng giá trị",
                    "data_points": hist_pts,
                    "commentary": (
                        f"Trung bình đạt {_fmt_num(ns0['avg'])}, trung vị {_fmt_num(ns0['median'])}, "
                        f"độ lệch chuẩn σ = {_fmt_num(ns0['std'])}, phát hiện {ns0.get('outlier_count', 0)} ngoại lai."
                    ),
                    "business_meaning": (
                        "Cho biết dữ liệu tập trung quanh mức trung vị hay bị lệch về một phía do các giao dịch đột biến (Outliers)."
                    ),
                }
            )
            break

    # 6. Combo Chart (Biểu đồ Kết hợp): Compare 2 metrics or Value vs Volume
    if classifiers and classifiers[0].get("groups"):
        c0 = classifiers[0]
        groups = c0["groups"][:6]
        max_sum = max((abs(float(g.get("metric_sum", 0))) for g in groups), default=1.0) or 1.0
        max_avg = max((abs(float(g.get("metric_avg", 0))) for g in groups), default=1.0) or 1.0
        pts_combo = [
            {
                "label": g["label"],
                "value": round(float(g.get("metric_sum", 0)), 2),
                "secondary_value": round(float(g.get("metric_avg", 0)), 2),
                "count": g.get("count", 0),
                "pct": g.get("share_pct", 0),
                "height_pct": round(abs(float(g.get("metric_sum", 0))) * 100.0 / max_sum, 1),
                "line_pct": round(abs(float(g.get("metric_avg", 0))) * 100.0 / max_avg, 1),
            }
            for g in groups
        ]
        m_lbl = c0.get("metric_column") or "Giá trị"
        charts.append(
            {
                "chart_id": "chart_combo_sum_avg",
                "chart_type": "combo",
                "chart_type_label": "Biểu đồ Kết hợp (Combo Chart: Tổng quy mô & Trung bình/Bản ghi)",
                "title": f"So sánh Tổng {m_lbl} và Trung bình mỗi bản ghi theo {c0['dimension']}",
                "x_axis_label": f"Nhóm {c0['dimension']}",
                "y_axis_label": f"Cột: Tổng {m_lbl} · Đường: Trung bình/Bản ghi",
                "legend": f"Cột hồng: Tổng {m_lbl} · Đường cam: Trung bình {m_lbl}/bản ghi",
                "data_points": pts_combo,
                "commentary": (
                    f"Đối chiếu giữa tổng quy mô và hiệu suất trung bình trên mỗi giao dịch/bản ghi giữa các nhóm {c0['dimension']}."
                ),
                "business_meaning": (
                    "Phân biệt nhóm có doanh số lớn nhờ số lượng nhiều (Volume-driven) với nhóm có giá trị trung bình đơn cao (Value-driven)."
                ),
            }
        )

    return charts


def _build_stage5_insights_and_stage6_solutions(
    domain_label: str,
    total_rows_raw: int,
    total_rows_clean: int,
    completeness_pct: float,
    dedup_count: int,
    outlier_total: int,
    fin_summary: Optional[Dict[str, Any]],
    proj_summary: Optional[Dict[str, Any]],
    classifiers: List[Dict[str, Any]],
    priority_entities: List[Dict[str, Any]],
    time_analysis: Dict[str, Any],
    all_numeric: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[str]]:
    """Build Stage 5 (DATA -> INFORMATION -> INSIGHT -> DECISION) and Stage 6 (Actionable Solutions)."""
    insights: List[Dict[str, Any]] = []
    solutions: List[Dict[str, Any]] = []
    core_problems: List[str] = []

    # Insight 1: Group / Pareto concentration
    if classifiers and classifiers[0].get("groups"):
        c0 = classifiers[0]
        g_top = c0["groups"][0]
        g_last = c0["groups"][-1]
        m_col = c0.get("metric_column") or "số lượng bản ghi"
        insights.append(
            {
                "id": "INS-01",
                "title": f"Sự tập trung tỷ trọng theo nhóm '{c0['dimension']}' ({c0['sheet_name']})",
                "category": "Phân tích Nhóm & Cơ cấu Pareto",
                "diid_chain": {
                    "data": f"{total_rows_clean} bản ghi sạch tại bảng '{c0['sheet_name']}' được phân theo trường '{c0['dimension']}'.",
                    "information": f"Nhóm '{g_top['label']}' dẫn đầu với {_fmt_num(g_top.get('metric_sum', g_top['count']))} ({g_top['share_pct']}% tổng {m_col}), trong khi nhóm thấp nhất '{g_last['label']}' chỉ chiếm {g_last['share_pct']}%.",
                    "insight": f"Cơ cấu kết quả đang nghiêng mạnh về '{g_top['label']}' (chênh lệch gấp {round(max(g_top['share_pct'], 0.1) / max(g_last['share_pct'], 0.1), 1)} lần so với nhóm cuối).",
                    "decision": f"Bảo vệ nguồn thu/hiệu suất tại nhóm chủ lực '{g_top['label']}', đồng thời rà soát nguyên nhân hiệu suất thấp ở nhóm '{g_last['label']}'.",
                },
                "finding": f"Nhóm '{g_top['label']}' chiếm tới {g_top['share_pct']}% tổng {m_col} ({g_top['count']} bản ghi) trong chiều phân tích '{c0['dimension']}'.",
                "evidence": f"Tổng {m_col} của '{g_top['label']}' = {_fmt_num(g_top.get('metric_sum', g_top['count']))} (TB: {_fmt_num(g_top.get('metric_avg', 0))}), so với '{g_last['label']}' = {_fmt_num(g_last.get('metric_sum', g_last['count']))} ({g_last['share_pct']}%).",
                "causes_proven": f"Số lượng bản ghi/giao dịch của '{g_top['label']}' đạt {g_top['count']} dòng và mức đóng góp trung bình mỗi dòng đạt {_fmt_num(g_top.get('metric_avg', 0))}.",
                "causes_hypothesis": f"Có thể do nhu cầu thị trường hoặc chính sách bán hàng/phân bổ nguồn lực đang ưu tiên mạnh cho '{g_top['label']}' (cần kiểm chứng thêm dữ liệu ngân sách Marketing & KPI nhân sự).",
                "business_impact": f"Nếu nhóm '{g_top['label']}' sụt giảm 10–20%, kết quả toàn doanh nghiệp sẽ bị ảnh hưởng trực tiếp tương ứng {round(g_top['share_pct'] * 0.15, 1)}% tổng quy mô.",
                "recommended_action": f"Thiết lập cơ chế chăm sóc ưu tiên (SLA riêng) cho nhóm '{g_top['label']}' và tái cấu trúc danh mục/kênh bán ở các nhóm dưới 10% tỷ trọng.",
            }
        )
        if g_top["share_pct"] >= 45.0:
            core_problems.append(
                f"Rủi ro tập trung cao: Nhóm '{g_top['label']}' ({c0['dimension']}) chiếm {g_top['share_pct']}% tổng quy mô, dễ gây biến động lớn nếu thị trường/khách hàng nhóm này thay đổi."
            )
        solutions.append(
            {
                "priority_order": "Ưu tiên 1 (Triển khai ngay)",
                "problem": f"Chênh lệch hiệu suất lớn giữa nhóm dẫn đầu '{g_top['label']}' ({g_top['share_pct']}%) và nhóm cuối '{g_last['label']}' ({g_last['share_pct']}%) tại '{c0['dimension']}'.",
                "solution": f"Chuẩn hóa quy trình thành công của '{g_top['label']}' để nhân rộng sang nhóm hạng B, đồng thời áp dụng chính sách giữ chân/tối ưu chi phí riêng cho nhóm dẫn đầu.",
                "department": "Phòng Kinh doanh & Phòng Phát triển Thị trường",
                "kpi": f"Duy trì tốc độ tăng trưởng nhóm '{g_top['label']}' ≥ 10% và nâng tỷ trọng các nhóm hạng B thêm +5–8% trong kỳ tới.",
                "risks_and_conditions": "Điều kiện: Phải đồng bộ dữ liệu CRM/Bán hàng hàng tuần; Rủi ro: Dàn trải nguồn lực nếu mở rộng sang nhóm C khi chưa kiểm chứng nhu cầu.",
            }
        )

    # Insight 2: Financial & Profit Margin OR Top Priority Entities (ABC)
    if fin_summary and (fin_summary.get("total_revenue") is not None or fin_summary.get("net_profit") is not None):
        rev = fin_summary.get("total_revenue") or 0.0
        cost = fin_summary.get("total_cost") or 0.0
        net = fin_summary.get("net_profit") if fin_summary.get("net_profit") is not None else (rev - cost)
        margin = fin_summary.get("margin_pct")
        margin_str = f"{margin}%" if margin is not None else "chưa có cột chi phí tách riêng"
        insights.append(
            {
                "id": "INS-02",
                "title": "Hiệu quả Tài chính, Cấu trúc Doanh thu – Chi phí & Biên lợi nhuận",
                "category": "Phân tích Tài chính & Hiệu suất",
                "diid_chain": {
                    "data": f"Dữ liệu tài chính ghi nhận Tổng Thu = {_fmt_num(rev)}, Tổng Chi = {_fmt_num(cost)}.",
                    "information": f"Lợi nhuận ròng đạt {_fmt_num(net)} với tỷ suất biên lợi nhuận ròng đạt {margin_str}.",
                    "insight": (
                        "Biên lợi nhuận đang ở mức khả quan, tạo dư địa tái đầu tư."
                        if (margin is not None and margin >= 15)
                        else "Biên lợi nhuận cần được giám sát chặt theo từng đơn vị/nhóm để tránh chi phí ăn mòn doanh thu."
                    ),
                    "decision": "Kiểm soát định mức chi phí theo từng trung tâm doanh thu và ưu tiên các dòng sản phẩm/khách hàng có biên lãi cao.",
                },
                "finding": f"Tổng doanh thu đạt {_fmt_num(rev)}, tổng chi phí {_fmt_num(cost)}, lợi nhuận ròng {_fmt_num(net)} (Biên lợi nhuận: {margin_str}).",
                "evidence": f"Cột doanh thu '{fin_summary.get('revenue_col') or 'Thu'}' = {_fmt_num(rev)}; Cột chi phí '{fin_summary.get('cost_col') or 'Chi'}' = {_fmt_num(cost)}.",
                "causes_proven": "Được tổng hợp trực tiếp từ các bản ghi giao dịch hợp lệ sau khi đã loại bỏ dòng trùng và chuẩn hóa đơn vị tiền tệ.",
                "causes_hypothesis": "Sự chênh lệch biên lợi nhuận giữa các nhóm có thể bắt nguồn từ chính sách chiết khấu hoặc chi phí vận hành/giao nhận khác nhau (cần đối chiếu bảng kê chi phí chi tiết).",
                "business_impact": "Quyết định trực tiếp đến dòng tiền ròng (Net Cashflow) và khả năng hoàn thành mục tiêu lợi nhuận năm của doanh nghiệp.",
                "recommended_action": "Áp dụng ngưỡng cảnh báo chi phí vượt định mức và rà soát các giao dịch/đối tượng có tỷ lệ chi phí/doanh thu cao bất thường.",
            }
        )
        if margin is not None and margin < 15.0:
            core_problems.append(f"Biên lợi nhuận ròng đạt {margin}% (Lợi nhuận: {_fmt_num(net)} / Doanh thu: {_fmt_num(rev)}), cần tối ưu chi phí ({_fmt_num(cost)}).")
        solutions.append(
            {
                "priority_order": "Ưu tiên 1 (Trọng tâm Tài chính)",
                "problem": f"Cần tối ưu hiệu quả chuyển đổi từ Doanh thu ({_fmt_num(rev)}) sang Lợi nhuận ròng ({_fmt_num(net)}, biên LN: {margin_str}).",
                "solution": "Thiết lập báo cáo P&L (Lãi/Lỗ) chi tiết theo từng nhóm khách hàng/sản phẩm và cắt giảm các khoản mục chi phí không tạo ra giá trị gia tăng.",
                "department": "Phòng Tài chính – Kế toán & Ban Giám đốc",
                "kpi": "Cải thiện biên lợi nhuận ròng thêm +2% đến +5% và kiểm soát tỷ lệ chi phí trên doanh thu trong ngưỡng mục tiêu.",
                "risks_and_conditions": "Điều kiện: Hạch toán đầy đủ chi phí trực tiếp vào từng đơn hàng/dự án; Rủi ro: Cắt giảm nhầm chi phí hỗ trợ khách hàng VIP.",
            }
        )
    elif priority_entities:
        top1 = priority_entities[0]
        group_a = [e for e in priority_entities if "Nhóm A" in str(e.get("tier", ""))]
        insights.append(
            {
                "id": "INS-02",
                "title": f"Phân hạng Ưu tiên ABC theo chỉ số '{top1.get('metric_col', '')}'",
                "category": "Phân tích Đối tượng Ưu tiên (ABC)",
                "diid_chain": {
                    "data": f"Xếp hạng {len(priority_entities)} đối tượng dẫn đầu trong bảng '{top1.get('table', '')}'.",
                    "information": f"Đối tượng #1 '{top1['name']}' đạt {_fmt_num(top1.get('metric_value', 0))} ({top1['share_pct']}% tổng toàn bảng).",
                    "insight": f"Nhóm A gồm {len(group_a)} đối tượng đầu đóng vai trò trụ cột quyết định thành tích của đơn vị.",
                    "decision": "Tập trung chính sách giữ chân và gia tăng giá trị vòng đời (LTV) cho các đối tượng thuộc Nhóm A.",
                },
                "finding": f"Đối tượng đứng đầu '{top1['name']}' đóng góp {top1['share_pct']}% ({_fmt_num(top1.get('metric_value', 0))}) trên chỉ số '{top1.get('metric_col', '')}'.",
                "evidence": f"Top {len(group_a)} đối tượng Nhóm A chiếm tỷ trọng áp đảo so với nhóm C.",
                "causes_proven": f"Dữ liệu thực tế ghi nhận giá trị tích lũy của '{top1['name']}' vượt trội so với trung bình toàn bảng.",
                "causes_hypothesis": "Các đối tượng Nhóm A có thể có tần suất mua lặp lại cao hơn hoặc quy mô hợp đồng lớn hơn (cần kiểm chứng lịch sử hợp đồng).",
                "business_impact": "Mất 1 khách hàng/đối tượng Nhóm A sẽ không thể bù đắp bằng nhiều đối tượng Nhóm C.",
                "recommended_action": "Phân công chuyên viên phụ trách riêng (Key Account Manager) cho danh sách Nhóm A.",
            }
        )

    # Insight 3: Time-series trend OR Statistical Dispersion & Outliers
    if time_analysis.get("available"):
        pk = time_analysis["peak_period"]
        lw = time_analysis["low_period"]
        gr = time_analysis.get("overall_growth_pct", 0.0)
        insights.append(
            {
                "id": "INS-03",
                "title": f"Biến động theo Thời gian ({time_analysis['granularity']}) & Tốc độ Tăng trưởng",
                "category": "Phân tích Chuỗi thời gian (Time-Series)",
                "diid_chain": {
                    "data": f"{time_analysis['period_count']} kỳ dữ liệu từ {time_analysis['first_period']} đến {time_analysis['last_period']}.",
                    "information": f"Kỳ đạt đỉnh: {pk['period']} ({_fmt_num(pk['sum'])}); Kỳ thấp nhất: {lw['period']} ({_fmt_num(lw['sum'])}); Tăng trưởng chung: {gr:+.1f}%.",
                    "insight": f"Có sự chênh lệch đáng kể giữa kỳ cao điểm ({pk['period']}) và kỳ thấp điểm ({lw['period']}).",
                    "decision": "Chủ động điều tiết kế hoạch bán hàng, nhân sự và tồn kho theo chu kỳ cao điểm – thấp điểm.",
                },
                "finding": f"Chỉ số '{time_analysis['metric_col']}' biến động từ {_fmt_num(lw['sum'])} ({lw['period']}) đến {_fmt_num(pk['sum'])} ({pk['period']}), tăng trưởng tổng thể {gr:+.1f}%.",
                "evidence": time_analysis.get("summary_note", ""),
                "causes_proven": f"Số lượng giao dịch tại kỳ {pk['period']} đạt {pk['count']} dòng, so với {lw['count']} dòng tại kỳ {lw['period']}.",
                "causes_hypothesis": "Biến động có thể chịu ảnh hưởng bởi tính mùa vụ ngành hàng hoặc các chiến dịch khuyến mãi theo đợt (cần đối chiếu lịch Marketing).",
                "business_impact": "Nếu không dự báo trước kỳ cao điểm/thấp điểm sẽ dẫn đến quá tải vận hành hoặc đọng vốn lưu động.",
                "recommended_action": f"Lập kế hoạch dự trữ nguồn lực trước kỳ cao điểm tương tự {pk['period']} và tung chương trình kích cầu vào kỳ thấp điểm như {lw['period']}.",
            }
        )
        solutions.append(
            {
                "priority_order": "Ưu tiên 2 (Kế hoạch Chu kỳ / Thời gian)",
                "problem": f"Biến động giữa kỳ cao điểm {pk['period']} ({_fmt_num(pk['sum'])}) và kỳ thấp điểm {lw['period']} ({_fmt_num(lw['sum'])}).",
                "solution": "Xây dựng lịch kế hoạch kinh doanh & tồn kho theo kỳ (Rolling Forecast), đẩy mạnh khuyến mãi kích cầu vào các kỳ trũng.",
                "department": "Phòng Kế hoạch – Vận hành & Phòng Marketing",
                "kpi": f"Giảm biên độ sụt giảm ở các kỳ thấp điểm tối thiểu 15% và giữ đà tăng trưởng dương qua các kỳ.",
                "risks_and_conditions": "Điều kiện: Cập nhật dữ liệu theo tuần/tháng đều đặn; Rủi ro: Tồn kho tăng nếu dự báo sai nhu cầu mùa vụ.",
            }
        )

    # Insight 4: Data Quality, Missing Values & Outliers (Mandatory BI Governance Insight)
    outlier_cols = [n for n in all_numeric if n.get("outlier_count", 0) > 0]
    outlier_desc = (
        ", ".join(f"{n['column']} ({n['outlier_count']} ngoại lai, ví dụ: {', '.join(_fmt_num(x) for x in (n.get('outliers') or [])[:2])})" for n in outlier_cols[:3])
        if outlier_cols
        else "Không phát hiện giá trị ngoại lai vượt ngưỡng 1.5×IQR"
    )
    insights.append(
        {
            "id": f"INS-0{len(insights) + 1}",
            "title": "Chất lượng Dữ liệu, Độ phân tán Thống kê & Kiểm soát Ngoại lai (Outliers)",
            "category": "Quản trị Dữ liệu & Bất thường (Data Governance)",
            "diid_chain": {
                "data": f"Kiểm tra {total_rows_raw} dòng dữ liệu gốc trên toàn bộ các Sheet tải lên.",
                "information": f"Độ đầy đủ đạt {completeness_pct}%, đã lọc {dedup_count} bản ghi trùng lặp và phát hiện {outlier_total} giá trị ngoại lai (IQR).",
                "insight": (
                    f"Các giá trị ngoại lai tại ({outlier_desc}) làm lệch trung bình cộng (Mean) so với trung vị (Median)."
                    if outlier_total > 0
                    else "Cấu trúc dữ liệu có tính nhất quán tốt, trung bình và trung vị bám sát nhau."
                ),
                "decision": "Sử dụng đồng thời Trung bình (Mean) và Trung vị (Median) khi giao chỉ tiêu KPI; chuẩn hóa quy trình nhập liệu tại nguồn.",
            },
            "finding": f"Độ đầy đủ dữ liệu đạt {completeness_pct}% ({total_rows_clean}/{total_rows_raw} dòng sạch); phát hiện {dedup_count} dòng trùng và {outlier_total} giá trị ngoại lai.",
            "evidence": f"Chi tiết ngoại lai theo phương pháp IQR: {outlier_desc}.",
            "causes_proven": (
                f"Có {dedup_count} dòng bị nhập lặp hoàn toàn và {outlier_total} điểm dữ liệu nằm ngoài khoảng [Q1 - 1.5×IQR, Q3 + 1.5×IQR]."
            ),
            "causes_hypothesis": "Các giá trị ngoại lai có thể là đơn hàng B2B/dự án đặc biệt lớn hoặc lỗi gõ thừa chữ số khi nhập liệu thủ công (cần kiểm tra chứng từ gốc).",
            "business_impact": "Nếu dùng trung bình cộng đơn thuần khi có ngoại lai sẽ dẫn đến giao KPI quá cao hoặc đánh giá sai mức nền thực tế.",
            "recommended_action": "Rà soát danh sách các bản ghi ngoại lai đã được hệ thống đánh dấu và áp dụng ràng buộc kiểm tra dữ liệu (Data Validation) trên file Excel/hệ thống nhập liệu.",
        }
    )
    if completeness_pct < 98.0 or dedup_count > 0 or outlier_total > 0:
        core_problems.append(
            f"Vấn đề chất lượng & bất thường dữ liệu: Độ đầy đủ {completeness_pct}%, có {dedup_count} dòng trùng lặp và {outlier_total} giá trị ngoại lai ({outlier_desc}) cần đối chiếu chứng từ gốc."
        )
    solutions.append(
        {
            "priority_order": "Ưu tiên 3 (Chuẩn hóa Quản trị Dữ liệu & BI)",
            "problem": f"Tồn tại {dedup_count} dòng trùng lặp, độ đầy đủ {completeness_pct}% và {outlier_total} điểm dữ liệu ngoại lai cần kiểm chứng.",
            "solution": "Áp dụng bộ quy tắc Data Validation (bắt buộc nhập các trường khóa, chuẩn hóa danh mục Dropdown, cảnh báo tự động khi giá trị vượt ngưỡng IQR).",
            "department": "Bộ phận Phân tích Dữ liệu (BI / Data Analyst) & Quản trị Hệ thống",
            "kpi": "Đạt độ đầy đủ dữ liệu ≥ 99.5%, tỷ lệ bản ghi trùng lặp = 0% trong các kỳ báo cáo tiếp theo.",
            "risks_and_conditions": "Điều kiện: Các phòng ban dùng chung mẫu biểu (Template) dữ liệu chuẩn đã làm sạch; Rủi ro: Nhân sự nhập liệu tự do ngoài danh mục.",
        }
    )

    if not core_problems:
        core_problems.append(
            "Cần duy trì tốc độ tăng trưởng đồng đều giữa các phân nhóm và tiếp tục theo dõi định kỳ các chỉ số KPI/MG để tối ưu hóa hiệu suất."
        )

    return insights, solutions, core_problems


def build_7stage_bi_pipeline_and_report(
    raw_sheets: Dict[str, List[Dict[str, Any]]],
    cleaned_sheets: Dict[str, List[Dict[str, Any]]],
    table_summaries: List[Dict[str, Any]],
    source_metadata: List[Dict[str, Any]],
    document_texts: Dict[str, List[str]],
    domain: str,
    domain_label: str,
    user_prompt: str,
    prompt_matches: List[Dict[str, Any]],
    prompt_note: Optional[str],
    fin_summary: Optional[Dict[str, Any]],
    proj_summary: Optional[Dict[str, Any]],
    classifiers: List[Dict[str, Any]],
    priority_entities: List[Dict[str, Any]],
    kpi_tree: Dict[str, Any],
    all_numeric: List[Dict[str, Any]],
    all_categories: List[Dict[str, Any]],
    total_rows_raw: int,
    total_rows_clean: int,
    empty_rows_removed: int,
    total_missing_cells: int,
    normalized_cells: int,
    unit_conversions: int,
    completeness_pct: float,
    dedup_log: List[Dict[str, Any]],
    quality_issues: List[Dict[str, Any]],
) -> Tuple[Dict[str, Any], List[Dict[str, Any]], str]:
    """Execute all 7 BI stages and return (bi_pipeline_dict, process_steps_7, markdown_report_10_sections)."""

    # -----------------------------------------------------------------------
    # GIAI ĐOẠN 1: TIẾP NHẬN VÀ KIỂM TRA DỮ LIỆU
    # -----------------------------------------------------------------------
    sheets_inventory: List[Dict[str, Any]] = []
    field_dictionary: List[Dict[str, Any]] = []
    important_fields: List[str] = []
    total_columns = 0
    date_standardized_count = 0
    category_normalized_count = 0

    for t in table_summaries:
        s_name = t["sheet_name"]
        rows = cleaned_sheets.get(s_name) or []
        headers = t.get("headers") or []
        total_columns += len(headers)
        num_map = {ns["column"]: ns for ns in (t.get("numeric_stats") or [])}
        cat_map = {cs["column"]: cs for cs in (t.get("category_stats") or [])}

        key_cols_in_sheet: List[str] = []
        for h in headers:
            is_num = h in num_map
            sample_vals = [str(r.get(h, "")).strip() for r in rows[:30] if str(r.get(h, "")).strip()]
            parsed_dates = [p for p in (_parse_period_token(v) for v in sample_vals[:15]) if p is not None]
            is_time = len(parsed_dates) >= max(1, len(sample_vals[:15]) // 2) if sample_vals else False
            if is_time:
                date_standardized_count += sum(1 for r in rows if _parse_period_token(str(r.get(h, ""))) is not None)

            blanks = sum(1 for r in rows if str(r.get(h, "")).strip() == "")
            non_empty = len(rows) - blanks
            uniq_vals = {str(r.get(h, "")).strip() for r in rows if str(r.get(h, "")).strip()}
            uniq_lower = {v.lower() for v in uniq_vals}
            if len(uniq_vals) > len(uniq_lower):
                category_normalized_count += len(uniq_vals) - len(uniq_lower)

            role, meaning = _detect_column_role_and_meaning(h, is_num, is_time, len(uniq_vals), len(rows))
            if any(k in role for k in ("Doanh thu", "Chi phí", "Lợi nhuận", "Thời gian", "Khách hàng", "Sản phẩm", "Khu vực", "Tiến độ")):
                key_cols_in_sheet.append(f"{h} ({role})")
                if f"{s_name}.{h}" not in important_fields:
                    important_fields.append(f"{h} [{role}]")

            dtype = (
                "Thời gian (Date/Period)"
                if is_time
                else "Số định lượng (Numeric)"
                if is_num
                else "Phân nhóm (Categorical)"
                if h in cat_map and cat_map[h].get("groupable")
                else "Văn bản / Định danh (Text/ID)"
            )
            field_dictionary.append(
                {
                    "sheet_name": s_name,
                    "column": h,
                    "data_type": dtype,
                    "semantic_role": role,
                    "non_empty_count": non_empty,
                    "missing_count": blanks,
                    "missing_pct": round(blanks * 100.0 / max(len(rows), 1), 1),
                    "unique_count": len(uniq_vals),
                    "sample_values": list(uniq_vals)[:3],
                    "meaning": meaning,
                }
            )

        s_meaning = (
            f"Bảng dữ liệu '{s_name}' gồm {len(rows)} bản ghi × {len(headers)} trường, "
            f"phản ánh {domain_label.lower()} với {len(num_map)} chỉ số định lượng và {len(cat_map)} trường phân loại."
        )
        sheets_inventory.append(
            {
                "sheet_name": s_name,
                "source_file": t.get("source_file", s_name),
                "row_count": len(rows),
                "column_count": len(headers),
                "numeric_col_count": len(num_map),
                "category_col_count": len(cat_map),
                "key_fields": key_cols_in_sheet[:6] or headers[:5],
                "meaning": s_meaning,
            }
        )

    initial_quality_note = (
        f"Dữ liệu đầu vào gồm {len(table_summaries)} Sheet ({total_rows_raw} dòng gốc, {total_columns} cột). "
        f"Độ đầy đủ đạt {completeness_pct}% ({total_missing_cells} ô trống); "
        f"phát hiện {len(dedup_log)} dòng trùng lặp và {empty_rows_removed} dòng trống hoàn toàn."
    )

    stage1_intake = {
        "analyst_name": ANALYST_NAME,
        "analyst_role": ANALYST_ROLE,
        "total_sheets": len(table_summaries),
        "total_rows_raw": total_rows_raw,
        "total_rows_clean": total_rows_clean,
        "total_columns": total_columns,
        "domain_label": domain_label,
        "important_fields": important_fields[:10],
        "sheets_inventory": sheets_inventory,
        "field_dictionary": field_dictionary,
        "initial_quality_assessment": initial_quality_note,
    }

    # -----------------------------------------------------------------------
    # GIAI ĐOẠN 2: LÀM SẠCH VÀ TIỀN XỬ LÝ DỮ LIỆU
    # -----------------------------------------------------------------------
    outlier_total = sum(n.get("outlier_count", 0) for n in all_numeric)
    cols_with_missing = [fd for fd in field_dictionary if fd["missing_count"] > 0]
    outlier_details = [
        {
            "sheet": n["table"],
            "column": n["column"],
            "outlier_count": n["outlier_count"],
            "outliers": n.get("outliers", []),
            "median": n["median"],
        }
        for n in all_numeric
        if n.get("outlier_count", 0) > 0
    ]

    stage2_cleaning = {
        "total_rows_raw": total_rows_raw,
        "total_rows_clean": total_rows_clean,
        "empty_rows_dropped": empty_rows_removed,
        "dedup_dropped_count": len(dedup_log),
        "empty_cells_count": total_missing_cells,
        "numeric_standardized_count": normalized_cells,
        "unit_conversions_count": unit_conversions,
        "date_standardized_count": date_standardized_count,
        "category_normalized_count": category_normalized_count,
        "outlier_total_count": outlier_total,
        "columns_with_missing": cols_with_missing,
        "outlier_details": outlier_details,
        "principles_applied": [
            "Không tự ý xóa bản ghi hợp lệ khi chưa có căn cứ (chỉ loại dòng trống 100% và dòng trùng lặp 100%).",
            "Không tự suy diễn hoặc tự tạo số liệu giả thay thế cho các ô bị khuyết (Missing Values).",
            "Các giá trị ngoại lai (Outliers theo IQR) được giữ nguyên trên bản dữ liệu sạch và gắn nhãn cảnh báo để đối chiếu chứng từ gốc.",
            "Tạo bản dữ liệu sạch riêng biệt (hỗ trợ xuất file Excel .xlsx sạch), giữ nguyên file dữ liệu gốc.",
        ],
    }

    # -----------------------------------------------------------------------
    # GIAI ĐOẠN 3: PHÂN TÍCH DỮ LIỆU
    # -----------------------------------------------------------------------
    time_analysis = _build_time_series_analysis(cleaned_sheets, table_summaries)

    # Comparative analysis (3.5)
    comparisons: List[Dict[str, str]] = []
    for cl in classifiers[:3]:
        grps = cl.get("groups") or []
        if len(grps) >= 2:
            g1, g2, glast = grps[0], grps[1], grps[-1]
            m_lbl = cl.get("metric_column") or "Số bản ghi"
            comparisons.append(
                {
                    "dimension": f"{cl['dimension']} ({cl['sheet_name']})",
                    "top_vs_second": f"#{1} '{g1['label']}' ({_fmt_num(g1.get('metric_sum', g1['count']))} · {g1['share_pct']}%) vượt #{2} '{g2['label']}' ({_fmt_num(g2.get('metric_sum', g2['count']))} · {g2['share_pct']}%).",
                    "top_vs_bottom": f"Gấp {round(max(g1['share_pct'], 0.1) / max(glast['share_pct'], 0.1), 1)} lần nhóm thấp nhất '{glast['label']}' ({glast['share_pct']}%).",
                    "metric_label": m_lbl,
                }
            )

    # Anomaly analysis (3.6)
    anomalies: List[str] = []
    for od in outlier_details:
        anomalies.append(
            f"[{od['sheet']} · {od['column']}] Phát hiện {od['outlier_count']} giá trị ngoại lai (tiêu biểu: {', '.join(_fmt_num(x) for x in od['outliers'])}) so với trung vị {_fmt_num(od['median'])}."
        )
    if time_analysis.get("available"):
        pk = time_analysis["peak_period"]
        lw = time_analysis["low_period"]
        anomalies.append(
            f"[Biến động Thời gian] Kỳ đỉnh {pk['period']} ({_fmt_num(pk['sum'])}) chênh lệch {_fmt_num(pk['sum'] - lw['sum'])} so với kỳ thấp nhất {lw['period']} ({_fmt_num(lw['sum'])})."
        )
    if not anomalies:
        anomalies.append("Không phát hiện biến động dị biệt hay ngoại lai vượt ngưỡng kiểm soát 1.5×IQR trên các chỉ số chính.")

    stage3_analysis = {
        "general_analysis": {
            "total_records": total_rows_clean,
            "financial_summary": fin_summary,
            "project_summary": proj_summary,
            "numeric_stats": all_numeric,
        },
        "time_analysis": time_analysis,
        "group_analysis": classifiers,
        "performance_analysis": {
            "kpi_tree": kpi_tree,
            "priority_entities": priority_entities,
        },
        "comparative_analysis": comparisons,
        "anomaly_analysis": anomalies,
    }

    # -----------------------------------------------------------------------
    # GIAI ĐOẠN 4: TRỰC QUAN HÓA DỮ LIỆU
    # -----------------------------------------------------------------------
    stage4_charts = _build_stage4_charts(
        table_summaries=table_summaries,
        classifiers=classifiers,
        priority_entities=priority_entities,
        time_analysis=time_analysis,
        fin_summary=fin_summary,
        cleaned_sheets=cleaned_sheets,
    )

    # -----------------------------------------------------------------------
    # GIAI ĐOẠN 5: PHÂN TÍCH INSIGHT & GIAI ĐOẠN 6: ĐỀ XUẤT GIẢI PHÁP
    # -----------------------------------------------------------------------
    stage5_insights, stage6_solutions, core_problems = _build_stage5_insights_and_stage6_solutions(
        domain_label=domain_label,
        total_rows_raw=total_rows_raw,
        total_rows_clean=total_rows_clean,
        completeness_pct=completeness_pct,
        dedup_count=len(dedup_log),
        outlier_total=outlier_total,
        fin_summary=fin_summary,
        proj_summary=proj_summary,
        classifiers=classifiers,
        priority_entities=priority_entities,
        time_analysis=time_analysis,
        all_numeric=all_numeric,
    )

    # -----------------------------------------------------------------------
    # 7-STEP PROCESS SUMMARY FOR UI & AUDIT
    # -----------------------------------------------------------------------
    n_sources = len({m.get("source") for m in source_metadata if m.get("source")}) or len(raw_sheets)
    process_steps = [
        {
            "key": "STAGE_1_INTAKE",
            "title": "Giai đoạn 1 · Tiếp nhận & Kiểm tra dữ liệu",
            "status": "OK",
            "detail": f"Đọc {n_sources} nguồn → {len(table_summaries)} Sheet, {total_rows_raw} dòng, {total_columns} cột · Lập từ điển {len(field_dictionary)} trường dữ liệu.",
        },
        {
            "key": "STAGE_2_CLEAN",
            "title": "Giai đoạn 2 · Làm sạch & Tiền xử lý",
            "status": "OK",
            "detail": f"Giữ {total_rows_clean}/{total_rows_raw} dòng sạch · Loại {len(dedup_log)} dòng trùng, {empty_rows_removed} dòng trống · Chuẩn hóa {normalized_cells} ô số, {date_standardized_count} ô ngày · Ghi nhận {total_missing_cells} ô thiếu & {outlier_total} ngoại lai (không tự ý xóa).",
        },
        {
            "key": "STAGE_3_ANALYZE",
            "title": "Giai đoạn 3 · Phân tích đa chiều",
            "status": "OK",
            "detail": f"Thống kê {len(all_numeric)} chỉ số định lượng · {len(classifiers)} chiều phân nhóm · "
            + (f"Xu hướng {time_analysis['period_count']} kỳ thời gian · " if time_analysis.get("available") else "")
            + f"Xếp hạng {len(priority_entities)} đối tượng ABC.",
        },
        {
            "key": "STAGE_4_VISUALIZE",
            "title": "Giai đoạn 4 · Trực quan hóa dữ liệu",
            "status": "OK",
            "detail": f"Tự động thiết lập {len(stage4_charts)} biểu đồ chuyên nghiệp ({', '.join(c['chart_type_label'].split('(')[0].strip() for c in stage4_charts[:4])}) kèm trục đo và ý nghĩa kinh doanh.",
        },
        {
            "key": "STAGE_5_INSIGHT",
            "title": "Giai đoạn 5 · Phân tích Insight (DATA → DECISION)",
            "status": "OK",
            "detail": f"Trích xuất {len(stage5_insights)} Insight cốt lõi theo mô hình DATA → INFORMATION → INSIGHT → DECISION (tách bạch nguyên nhân có bằng chứng & giả thuyết).",
        },
        {
            "key": "STAGE_6_SOLUTION",
            "title": "Giai đoạn 6 · Đề xuất giải pháp thực thi",
            "status": "OK",
            "detail": f"Đề xuất {len(stage6_solutions)} giải pháp gắn với bộ phận chịu trách nhiệm, KPI đo lường, thứ tự ưu tiên và điều kiện thực hiện.",
        },
        {
            "key": "STAGE_7_DELIVER",
            "title": "Giai đoạn 7 · Lập báo cáo & Bàn giao 4 sản phẩm",
            "status": "OK",
            "detail": "Hoàn tất 4 sản phẩm bàn giao: (1) Excel dữ liệu sạch, (2) Excel tổng hợp & biểu đồ, (3) Dashboard trực quan, (4) Báo cáo phân tích chuyên nghiệp 10 mục.",
        },
    ]

    # -----------------------------------------------------------------------
    # GIAI ĐOẠN 7: TẠO BÁO CÁO CHUYÊN NGHIỆP 10 MỤC (MARKDOWN / WORD / HTML)
    # -----------------------------------------------------------------------
    executive_conclusion = (
        f"Trên cơ sở phân tích {total_rows_clean} bản ghi sạch từ {len(table_summaries)} Sheet dữ liệu ({completeness_pct}% độ đầy đủ), "
        f"chuyên viên phân tích {ANALYST_NAME} khuyến nghị Ban Quản lý ưu tiên tập trung nguồn lực vào nhóm dẫn đầu "
        + (f"'{classifiers[0]['groups'][0]['label']}' ({classifiers[0]['groups'][0]['share_pct']}% tỷ trọng) " if (classifiers and classifiers[0].get("groups")) else "")
        + (f"đồng thời kiểm soát chặt biên lợi nhuận ({fin_summary['margin_pct']}%) " if (fin_summary and fin_summary.get("margin_pct") is not None) else "")
        + f"và triển khai ngay {len(stage6_solutions)} giải pháp theo lộ trình ưu tiên đã đề xuất để tối ưu hóa hiệu suất kinh doanh."
    )

    md: List[str] = [
        f"# BÁO CÁO PHÂN TÍCH & THỐNG KÊ DỮ LIỆU CÔNG TY — {domain_label.upper()}",
        f"- **Chuyên viên thực hiện**: **{ANALYST_NAME}** (*{ANALYST_ROLE}*)",
        f"- **Lĩnh vực & Trọng tâm phân tích**: {domain_label}" + (f" · *Yêu cầu riêng: {user_prompt}*" if user_prompt else ""),
        f"- **Quy mô dữ liệu**: {len(table_summaries)} Sheet · {total_rows_clean}/{total_rows_raw} bản ghi sạch · {total_columns} trường dữ liệu · Độ đầy đủ **{completeness_pct}%**",
        "",
        "## 1. Tổng quan và mục tiêu phân tích",
        f"- **Mục tiêu phân tích**: Chủ động thực hiện trọn vẹn 7 giai đoạn phân tích dữ liệu doanh nghiệp (từ tiếp nhận, kiểm tra cấu trúc, làm sạch tiền xử lý, thống kê đa chiều, trực quan hóa biểu đồ đến trích xuất Insight theo mô hình `DATA → INFORMATION → INSIGHT → DECISION` và đề xuất giải pháp thực thi).",
        f"- **Phạm vi dữ liệu**: {len(table_summaries)} bảng dữ liệu ({', '.join(t['sheet_name'] for t in table_summaries)})"
        + (f" và {len(document_texts)} tài liệu văn bản đi kèm." if document_texts else "."),
        "",
        "## 2. Mô tả dữ liệu (Danh sách Sheet & Từ điển trường dữ liệu)",
    ]
    for sh in sheets_inventory:
        md.append(
            f"- **Sheet `{sh['sheet_name']}`** *(Nguồn: {sh['source_file']})*: {sh['row_count']} dòng × {sh['column_count']} cột — {sh['meaning']} Trường quan trọng: {', '.join(sh['key_fields'][:5])}."
        )
    md.append("")
    md.append("| Sheet | Trường dữ liệu (Cột) | Kiểu dữ liệu | Vai trò ngữ nghĩa | Đầy đủ / Thiếu | Ý nghĩa & Mẫu dữ liệu |")
    md.append("|---|---|---|---|---|---|")
    for fd in field_dictionary[:25]:
        samples = ", ".join(str(x) for x in (fd.get("sample_values") or [])[:3])
        md.append(
            f"| {fd['sheet_name']} | **{fd['column']}** | {fd['data_type']} | {fd['semantic_role']} | "
            f"Đủ {fd['non_empty_count']} · Thiếu {fd['missing_count']} ({fd['missing_pct']}%) | {fd['meaning']} *(Mẫu: {samples})* |"
        )
    md.append("")

    md.extend(
        [
            "## 3. Đánh giá chất lượng dữ liệu",
            f"- **Độ đầy đủ tổng thể (Completeness)**: **{completeness_pct}%** (Tổng số ô thiếu giá trị: {total_missing_cells} ô trên {len(cols_with_missing)} cột).",
            f"- **Tính duy nhất (Uniqueness)**: Phát hiện **{len(dedup_log)}** bản ghi trùng lặp hoàn toàn và **{empty_rows_removed}** dòng trống.",
            f"- **Tính nhất quán & Định dạng (Consistency)**: Chuẩn hóa **{normalized_cells}** ô định dạng số, **{date_standardized_count}** ô thời gian và **{category_normalized_count}** nhãn phân loại.",
            f"- **Giá trị bất thường (Outliers)**: Phát hiện **{outlier_total}** điểm dữ liệu vượt ngưỡng IQR ($Q_1 - 1.5\\text{{IQR}}, Q_3 + 1.5\\text{{IQR}}$).",
            "",
            "## 4. Quy trình làm sạch dữ liệu (Giai đoạn 2)",
            "- **Nguyên tắc**: Không tự ý xóa dữ liệu khi chưa có căn cứ; không tự suy diễn hoặc tạo dữ liệu giả thay thế; giữ nguyên dữ liệu gốc và xuất bản dữ liệu sạch riêng.",
        ]
    )
    for st in process_steps[:2]:
        md.append(f"- **{st['title']}**: {st['detail']}")
    md.append("")

    md.append("## 5. Kết quả phân tích (Giai đoạn 3)")
    if fin_summary:
        md.append("### 5.1. Phân tích Tổng quan Tài chính")
        if fin_summary.get("total_revenue") is not None:
            md.append(f"- **Tổng Doanh thu ({fin_summary['revenue_col']})**: **{_fmt_num(fin_summary['total_revenue'])}**")
        if fin_summary.get("total_cost") is not None:
            md.append(f"- **Tổng Chi phí ({fin_summary['cost_col']})**: **{_fmt_num(fin_summary['total_cost'])}**")
        if fin_summary.get("net_profit") is not None:
            md.append(
                f"- **Lợi nhuận ròng**: **{_fmt_num(fin_summary['net_profit'])}**"
                + (f" (Biên lợi nhuận: **{fin_summary['margin_pct']}%**)" if fin_summary.get("margin_pct") is not None else "")
            )
        md.append("")

    if proj_summary:
        md.append("### 5.2. Phân tích Dự án & Tiến độ")
        md.append(
            f"- **Tổng số dự án/hạng mục**: {proj_summary['total_projects']} · Hoàn thành: {proj_summary['completed_count']} · Đang ổn: {proj_summary['on_track_count']} · Rủi ro/Chậm: {proj_summary['at_risk_count']}"
            + (f" · Tiến độ TB: {proj_summary['avg_progress_pct']}%" if proj_summary.get("avg_progress_pct") is not None else "")
        )
        md.append("")

    if all_numeric:
        md.append("### 5.3. Thống kê mô tả các chỉ số định lượng")
        md.append("| Bảng nguồn | Chỉ tiêu / Cột | Số dòng | Thiếu | Tổng (Sum) | Trung bình | Trung vị | Độ lệch chuẩn | Nhỏ nhất | Lớn nhất | Ngoại lai |")
        md.append("|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
        for ns in all_numeric[:20]:
            note = f" *({ns['unit_note']})*" if ns.get("unit_note") else ""
            md.append(
                f"| {ns['table']} | {ns['column']}{note} | {ns['count']} | {ns['missing_count']} | {ns['sum']} | {ns['avg']} | "
                f"{ns['median']} | {ns['std']} | {ns['min']} | {ns['max']} | {ns['outlier_count']} |"
            )
        md.append("")

    md.append("### 5.4. Phân tích theo Thời gian (Time-Series)")
    md.append(f"- {time_analysis.get('summary_note', '')}")
    if time_analysis.get("available") and time_analysis.get("periods"):
        for pt in time_analysis["periods"][:12]:
            mom_txt = f" (Tăng trưởng kỳ liền kề: {pt['mom_growth_pct']:+.1f}%)" if pt.get("mom_growth_pct") is not None else ""
            md.append(f"  - Kỳ **{pt['period']}**: {pt['count']} bản ghi · Tổng `{time_analysis['metric_col']}` = **{_fmt_num(pt['sum'])}**{mom_txt}")
    md.append("")

    if classifiers:
        md.append("### 5.5. Phân tích theo Nhóm & So sánh")
        for cl in classifiers[:6]:
            tops = ", ".join(f"{g['label']} ({g['count']} dòng · {_fmt_num(g.get('metric_sum', g['count']))} · {g['share_pct']}%)" for g in cl["groups"][:5])
            md.append(f"- **{cl['group_name']}** [`{cl['dimension']}`]: {tops}")
        for cmp_item in comparisons:
            md.append(f"- **So sánh `{cmp_item['dimension']}`**: {cmp_item['top_vs_second']} {cmp_item['top_vs_bottom']}")
        md.append("")

    if priority_entities:
        md.append("### 5.6. Phân tích Hiệu suất & Xếp hạng Ưu tiên ABC (Pareto)")
        md.append("| Hạng | Bảng | Tên đối tượng | Phân hạng | Giá trị | Tỷ trọng % | Nhóm / Trạng thái |")
        md.append("|---:|---|---|---|---:|---:|---|")
        for pe in priority_entities[:12]:
            grp = pe["group_label"] or pe["status_badge"] or "-"
            md.append(f"| #{pe['rank']} | {pe['table']} | {pe['name']} | {pe['tier']} | {pe['value']} | {pe['share_pct']}% | {grp} |")
        md.append("")

    if kpi_tree.get("branches"):
        md.append(f"### 5.7. Cây KPI / Mục tiêu Quản trị (MG): {kpi_tree['goal_name']}")
        for br in kpi_tree["branches"]:
            md.append(f"- **{br['name']}** *({br['owner']})* — {br['summary']}")
            for ch in br.get("children", []):
                md.append(f"  - {ch['label']}: **{ch['value']}**")
        md.append("")

    if prompt_matches:
        md.append(f'### 5.8. Kết quả lọc theo yêu cầu riêng: "{user_prompt}"')
        for pm in prompt_matches[:10]:
            md.append(f"- **{pm['row_label']}** *({pm['table']})*: {pm['reason']}")
        md.append("")

    md.append("## 6. Các biểu đồ trực quan (Giai đoạn 4)")
    for ch in stage4_charts:
        md.append(f"- **{ch['chart_type_label']} — {ch['title']}**")
        md.append(f"  - *Trục hoành (X)*: {ch['x_axis_label']} · *Trục tung (Y)*: {ch['y_axis_label']}")
        md.append(f"  - *Nhận xét*: {ch['commentary']}")
        md.append(f"  - *Ý nghĩa kinh doanh*: {ch['business_meaning']}")
    md.append("")

    md.append("## 7. Những Insight quan trọng (Giai đoạn 5: DATA → INFORMATION → INSIGHT → DECISION)")
    for ins in stage5_insights:
        md.append(f"### {ins['id']}: {ins['title']} *({ins['category']})*")
        diid = ins["diid_chain"]
        md.append(f"- **Mô hình chuyển hóa**: **DATA** ({diid['data']}) → **INFORMATION** ({diid['information']}) → **INSIGHT** ({diid['insight']}) → **DECISION** ({diid['decision']})")
        md.append(f"- **1. Phát hiện điều gì?** {ins['finding']}")
        md.append(f"- **2. Số liệu nào chứng minh?** {ins['evidence']}")
        md.append(f"- **3a. Nguyên nhân đã được dữ liệu chứng minh**: {ins['causes_proven']}")
        md.append(f"- **3b. Giả thuyết cần kiểm chứng thêm**: {ins['causes_hypothesis']}")
        md.append(f"- **4. Tác động đến doanh nghiệp**: {ins['business_impact']}")
        md.append(f"- **5. Doanh nghiệp nên làm gì?** {ins['recommended_action']}")
        md.append("")

    md.append("## 8. Vấn đề doanh nghiệp đang gặp phải")
    for prob in core_problems:
        md.append(f"- {prob}")
    md.append("")

    md.append("## 9. Giải pháp và đề xuất thực thi (Giai đoạn 6)")
    md.append("| Thứ tự ưu tiên | Vấn đề cần giải quyết | Giải pháp cụ thể | Bộ phận chịu trách nhiệm | KPI đo lường hiệu quả | Rủi ro & Điều kiện thực hiện |")
    md.append("|---|---|---|---|---|---|")
    for sol in stage6_solutions:
        md.append(
            f"| **{sol['priority_order']}** | {sol['problem']} | {sol['solution']} | **{sol['department']}** | {sol['kpi']} | {sol['risks_and_conditions']} |"
        )
    md.append("")

    md.extend(
        [
            "## 10. Kết luận dành cho nhà quản lý",
            f"- {executive_conclusion}",
            f"- **Bàn giao 4 sản phẩm đầu ra**: (1) File Excel dữ liệu đã làm sạch (`.xlsx`), (2) File Excel bảng tổng hợp & biểu đồ phân tích (`.xlsx`), (3) Dashboard tổng quan trực quan, (4) Báo cáo phân tích chuyên nghiệp Word/PDF/HTML do chuyên viên **{ANALYST_NAME}** thực hiện.",
        ]
    )

    stage7_report = {
        "analyst_name": ANALYST_NAME,
        "analyst_role": ANALYST_ROLE,
        "core_problems": core_problems,
        "executive_conclusion": executive_conclusion,
        "deliverables": [
            {"id": "cleaned_xlsx", "name": "1. File Excel dữ liệu đã làm sạch (.xlsx)", "format": "XLSX"},
            {"id": "analysis_xlsx", "name": "2. File Excel bảng tổng hợp & biểu đồ phân tích (.xlsx)", "format": "XLSX"},
            {"id": "dashboard_html", "name": "3. Dashboard tổng quan & Báo cáo HTML tương tác", "format": "HTML/WEB"},
            {"id": "report_docx_pdf", "name": "4. Báo cáo phân tích chuyên nghiệp Word (.docx) / PDF", "format": "DOCX/PDF"},
        ],
    }

    bi_pipeline = {
        "analyst_name": ANALYST_NAME,
        "analyst_role": ANALYST_ROLE,
        "stage1_intake": stage1_intake,
        "stage2_cleaning": stage2_cleaning,
        "stage3_analysis": stage3_analysis,
        "stage4_charts": stage4_charts,
        "stage5_insights": stage5_insights,
        "stage6_solutions": stage6_solutions,
        "stage7_report": stage7_report,
    }

    return bi_pipeline, process_steps, "\n".join(md)


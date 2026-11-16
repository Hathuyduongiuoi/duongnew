"""Pure-Python OpenXML (.xlsx and .docx) exporters for Senior Data Analyst & BI Deliverables.

Generates:
1. Cleaned Data Excel workbook (.xlsx)
2. Summary Tables & Analytical Charts Excel workbook (.xlsx)
3. Professional 10-Section BI Analytical Report Word document (.docx)
"""

from __future__ import annotations

import io
import re
import zipfile
from typing import Any, Dict, List
from xml.sax.saxutils import escape


def _clean_xml_text(val: Any) -> str:
    if val is None:
        return ""
    s = str(val)
    # Strip illegal XML 1.0 control chars
    s = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", s)
    return escape(s)


def _col_letter(col_idx_1based: int) -> str:
    result = ""
    n = col_idx_1based
    while n > 0:
        n, rem = divmod(n - 1, 26)
        result = chr(65 + rem) + result
    return result or "A"


def _sanitize_sheet_title(name: str, used: set[str]) -> str:
    cleaned = re.sub(r"[\[\]\:\*\?\/\\]", "_", str(name or "Sheet")).strip() or "Sheet"
    base = cleaned[:28]
    candidate = base
    idx = 2
    while candidate.lower() in used:
        suffix = f"_{idx}"
        candidate = f"{base[:31 - len(suffix)]}{suffix}"
        idx += 1
    used.add(candidate.lower())
    return candidate


def _build_xlsx_bytes(sheets_spec: List[Dict[str, Any]]) -> bytes:
    """Build a styled multi-sheet OpenXML .xlsx workbook from sheets_spec.

    Each item in sheets_spec has:
      - name: str
      - headers: List[str]
      - rows: List[List[Any]]
    """
    if not sheets_spec:
        sheets_spec = [{"name": "DuLieu", "headers": ["Ghi_Chu"], "rows": [["Không có dữ liệu"]]}]

    used_names: set[str] = set()
    normalized_sheets: List[Dict[str, Any]] = []
    for sp in sheets_spec:
        s_title = _sanitize_sheet_title(sp.get("name", "Sheet"), used_names)
        normalized_sheets.append(
            {
                "title": s_title,
                "headers": [str(h) for h in (sp.get("headers") or [])],
                "rows": sp.get("rows") or [],
            }
        )

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        # [Content_Types].xml
        sheet_overrides = "\n".join(
            f'  <Override PartName="/xl/worksheets/sheet{i}.xml" '
            f'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            for i in range(1, len(normalized_sheets) + 1)
        )
        content_types = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
{sheet_overrides}
</Types>"""
        zf.writestr("[Content_Types].xml", content_types.encode("utf-8"))

        # _rels/.rels
        root_rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>"""
        zf.writestr("_rels/.rels", root_rels.encode("utf-8"))

        # xl/workbook.xml
        sheet_tags = "\n".join(
            f'    <sheet name="{_clean_xml_text(sh["title"])}" sheetId="{i}" r:id="rId{i}"/>'
            for i, sh in enumerate(normalized_sheets, start=1)
        )
        workbook_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets>
{sheet_tags}
  </sheets>
</workbook>"""
        zf.writestr("xl/workbook.xml", workbook_xml.encode("utf-8"))

        # xl/_rels/workbook.xml.rels
        wb_rels_items = [
            f'  <Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i}.xml"/>'
            for i in range(1, len(normalized_sheets) + 1)
        ]
        wb_rels_items.append(
            f'  <Relationship Id="rId{len(normalized_sheets) + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
        )
        wb_rels = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">\n'
            + "\n".join(wb_rels_items)
            + "\n</Relationships>"
        )
        zf.writestr("xl/_rels/workbook.xml.rels", wb_rels.encode("utf-8"))

        # xl/styles.xml (style 0 = normal, style 1 = bold pink/rose header, style 2 = numeric)
        styles_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <fonts count="2">
    <font><sz val="11"/><color rgb="FF1E293B"/><name val="Calibri"/></font>
    <font><b/><sz val="11"/><color rgb="FFFFFFFF"/><name val="Calibri"/></font>
  </fonts>
  <fills count="3">
    <fill><patternFill patternType="none"/></fill>
    <fill><patternFill patternType="gray125"/></fill>
    <fill><patternFill patternType="solid"><fgColor rgb="FFDB2777"/><bgColor indexed="64"/></patternFill></fill>
  </fills>
  <borders count="2">
    <border><left/><right/><top/><bottom/><diagonal/></border>
    <border>
      <left style="thin"><color rgb="FFE2E8F0"/></left>
      <right style="thin"><color rgb="FFE2E8F0"/></right>
      <top style="thin"><color rgb="FFE2E8F0"/></top>
      <bottom style="thin"><color rgb="FFE2E8F0"/></bottom>
      <diagonal/>
    </border>
  </borders>
  <cellStyleXfs count="1">
    <xf numFmtId="0" fontId="0" fillId="0" borderId="0"/>
  </cellStyleXfs>
  <cellXfs count="3">
    <xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0" applyBorder="1"/>
    <xf numFmtId="0" fontId="1" fillId="2" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1"/>
    <xf numFmtId="4" fontId="0" fillId="0" borderId="1" xfId="0" applyNumberFormat="1" applyBorder="1"/>
  </cellXfs>
</styleSheet>"""
        zf.writestr("xl/styles.xml", styles_xml.encode("utf-8"))

        # Write each worksheet
        for s_idx, sh in enumerate(normalized_sheets, start=1):
            headers = sh["headers"]
            rows = sh["rows"]
            row_xml_parts: List[str] = []

            if headers:
                h_cells: List[str] = []
                for c_idx, h_text in enumerate(headers, start=1):
                    ref = f"{_col_letter(c_idx)}1"
                    h_cells.append(
                        f'<c r="{ref}" s="1" t="inlineStr"><is><t>{_clean_xml_text(h_text)}</t></is></c>'
                    )
                row_xml_parts.append(f'<row r="1" ht="22" customHeight="1">{"".join(h_cells)}</row>')

            max_rows = min(len(rows), 25000)
            for r_offset in range(max_rows):
                r_num = r_offset + (2 if headers else 1)
                row_vals = rows[r_offset]
                c_parts: List[str] = []
                for c_idx, val in enumerate(row_vals, start=1):
                    ref = f"{_col_letter(c_idx)}{r_num}"
                    if isinstance(val, (int, float)) and not isinstance(val, bool):
                        c_parts.append(f'<c r="{ref}" s="2"><v>{val}</v></c>')
                    else:
                        txt = "" if val is None else str(val)
                        # Check if string is a clean number
                        if re.fullmatch(r"-?\d+(\.\d+)?", txt.strip()):
                            c_parts.append(f'<c r="{ref}" s="2"><v>{txt.strip()}</v></c>')
                        else:
                            c_parts.append(
                                f'<c r="{ref}" s="0" t="inlineStr"><is><t>{_clean_xml_text(txt)}</t></is></c>'
                            )
                row_xml_parts.append(f'<row r="{r_num}">{"".join(c_parts)}</row>')

            col_count = max(len(headers), max((len(r) for r in rows[:50]), default=1), 1)
            cols_xml = f'<cols><col min="1" max="{col_count}" width="22" customWidth="1"/></cols>'
            ws_xml = (
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
                '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">\n'
                f"  {cols_xml}\n"
                "  <sheetData>\n"
                + "\n".join(row_xml_parts)
                + "\n  </sheetData>\n</worksheet>"
            )
            zf.writestr(f"xl/worksheets/sheet{s_idx}.xml", ws_xml.encode("utf-8"))

    return buf.getvalue()


def export_cleaned_excel_bytes(session_resp: Dict[str, Any], cleaned_sheets: Dict[str, List[Dict[str, Any]]]) -> bytes:
    """Product 1: File Excel dữ liệu đã làm sạch (.xlsx)."""
    sheets_spec: List[Dict[str, Any]] = []
    cs = session_resp.get("company_stats") or {}

    if cleaned_sheets:
        for s_name, rows in cleaned_sheets.items():
            if not rows:
                continue
            headers = [k for k in rows[0].keys() if not str(k).startswith("_")]
            matrix: List[List[Any]] = []
            for r in rows:
                matrix.append([r.get(h, "") for h in headers])
            sheets_spec.append({"name": s_name, "headers": headers, "rows": matrix})
    else:
        # Fallback to normalized canonical tables if market_expansion mode
        ing = session_resp.get("ingestion") or {}
        norm_data = ing.get("normalized_data") or {}
        for s_name, rows in norm_data.items():
            if not isinstance(rows, list) or not rows:
                continue
            headers = [k for k in rows[0].keys() if not str(k).startswith("_")]
            matrix = [[r.get(h, "") for h in headers] for r in rows]
            sheets_spec.append({"name": s_name, "headers": headers, "rows": matrix})

    # Add Cleaning Audit Log sheet
    stage2 = (cs.get("bi_pipeline") or {}).get("stage2_cleaning") or {}
    log_rows: List[List[Any]] = [
        ["Chuyên viên thực hiện", "Hà Thuỳ Dương (Senior Data Analyst & BI)"],
        ["Mã phiên phân tích", session_resp.get("run_id", "")],
        ["Tổng số dòng gốc", cs.get("total_rows_raw", 0)],
        ["Tổng số dòng sạch còn lại", cs.get("total_rows_clean", 0)],
        ["Số bản ghi trùng đã loại bỏ", cs.get("dedup_dropped_count", 0)],
        ["Số dòng trống hoàn toàn đã loại", cs.get("empty_rows_dropped", 0)],
        ["Số ô thiếu giá trị (Missing Values)", cs.get("empty_cells_count", 0)],
        ["Số ô số liệu đã chuẩn hóa", cs.get("numeric_cells_standardized", 0)],
        ["Số ô ngày tháng đã chuẩn hóa", stage2.get("date_standardized_count", 0)],
        ["Số nhãn phân loại đã đồng nhất", stage2.get("category_normalized_count", 0)],
        ["Số giá trị ngoại lai (IQR Outliers)", stage2.get("outlier_total_count", 0)],
        ["Độ đầy đủ dữ liệu (%)", f"{cs.get('completeness_pct', 100.0)}%"],
    ]
    for issue in (cs.get("quality_issues") or [])[:50]:
        log_rows.append(
            [
                f"[{issue.get('type', 'CHECK')}] {issue.get('sheet', '')} · {issue.get('column', '')}",
                issue.get("detail", ""),
            ]
        )
    sheets_spec.append(
        {
            "name": "NhatKy_LamSach",
            "headers": ["Hạng mục Kiểm tra & Tiền xử lý", "Kết quả / Ghi nhận"],
            "rows": log_rows,
        }
    )
    return _build_xlsx_bytes(sheets_spec)


def export_analysis_excel_bytes(session_resp: Dict[str, Any]) -> bytes:
    """Product 2: File Excel có các bảng tổng hợp và biểu đồ phân tích (.xlsx)."""
    cs = session_resp.get("company_stats") or {}
    bi = cs.get("bi_pipeline") or {}
    stage1 = bi.get("stage1_intake") or {}
    stage3 = bi.get("stage3_analysis") or {}
    stage4 = bi.get("stage4_charts") or []
    stage5 = bi.get("stage5_insights") or []
    stage6 = bi.get("stage6_solutions") or []

    sheets_spec: List[Dict[str, Any]] = []

    # Sheet 1: Tổng quan & Từ điển dữ liệu (Giai đoạn 1)
    s1_rows: List[List[Any]] = [
        ["CHUYÊN VIÊN PHÂN TÍCH", "Hà Thuỳ Dương — Senior Data Analyst & BI", "", "", "", ""],
        ["Lĩnh vực & Trọng tâm", cs.get("domain_label", ""), "Tổng số Sheet", cs.get("total_sheets", 0), "Độ đầy đủ", f"{cs.get('completeness_pct', 100.0)}%"],
        ["Tổng số dòng gốc", cs.get("total_rows_raw", 0), "Tổng dòng sạch", cs.get("total_rows_clean", 0), "Trùng đã loại", cs.get("dedup_dropped_count", 0)],
        ["", "", "", "", "", ""],
        ["SHEET", "TÊN TRƯỜNG (CỘT)", "KIỂU DỮ LIỆU", "VAI TRÒ NGỮ NGHĨA", "ĐẦY ĐỦ / THIẾU", "Ý NGHĨA & MẪU DỮ LIỆU"],
    ]
    for fd in stage1.get("field_dictionary") or []:
        s1_rows.append(
            [
                fd.get("sheet_name", ""),
                fd.get("column", ""),
                fd.get("data_type", ""),
                fd.get("semantic_role", ""),
                f"Đủ {fd.get('non_empty_count', 0)} · Thiếu {fd.get('missing_count', 0)} ({fd.get('missing_pct', 0)}%)",
                f"{fd.get('meaning', '')} | Mẫu: {', '.join(str(x) for x in (fd.get('sample_values') or [])[:3])}",
            ]
        )
    sheets_spec.append(
        {
            "name": "1_TongQuan_TuDien",
            "headers": ["Sheet / Chỉ tiêu", "Trường dữ liệu", "Kiểu dữ liệu", "Vai trò", "Mức độ đầy đủ", "Mô tả & Giá trị mẫu"],
            "rows": s1_rows,
        }
    )

    # Sheet 2: Thống kê Mô tả Số học (Giai đoạn 3.1)
    s2_rows: List[List[Any]] = []
    for t in cs.get("table_summaries") or []:
        for ns in t.get("numeric_stats") or []:
            s2_rows.append(
                [
                    t.get("sheet_name", ""),
                    ns.get("column", ""),
                    ns.get("count", 0),
                    ns.get("missing_count", 0),
                    ns.get("sum", 0),
                    ns.get("avg", 0),
                    ns.get("median", 0),
                    ns.get("std", 0),
                    ns.get("min", 0),
                    ns.get("max", 0),
                    ns.get("outlier_count", 0),
                    ns.get("unit_note") or "Chuẩn",
                ]
            )
    sheets_spec.append(
        {
            "name": "2_ThongKe_MoTa",
            "headers": ["Sheet", "Chỉ số định lượng", "Số dòng (N)", "Thiếu", "Tổng (Sum)", "Trung bình (Mean)", "Trung vị (Median)", "Độ lệch chuẩn (Std)", "Min", "Max", "Ngoại lai (IQR)", "Ghi chú đơn vị"],
            "rows": s2_rows or [["Không có cột định lượng", "", 0, 0, 0, 0, 0, 0, 0, 0, 0, ""]],
        }
    )

    # Sheet 3: Phân tích theo Nhóm & Xếp hạng Pareto ABC (Giai đoạn 3.3 & 3.4)
    s3_rows: List[List[Any]] = []
    for clf in cs.get("classifiers") or []:
        for g in clf.get("groups") or []:
            bar = "█" * max(1, int(round(float(g.get("share_pct", 0)) / 5.0)))
            s3_rows.append(
                [
                    clf.get("sheet_name", ""),
                    clf.get("title", ""),
                    g.get("label", ""),
                    g.get("count", 0),
                    g.get("metric_sum", g.get("count", 0)),
                    g.get("metric_avg", 0),
                    f"{g.get('share_pct', 0)}%",
                    bar,
                ]
            )
    for pe in cs.get("priority_entities") or []:
        s3_rows.append(
            [
                pe.get("table", ""),
                f"Xếp hạng ABC ({pe.get('metric_col', '')})",
                f"#{pe.get('rank', '')} {pe.get('name', '')}",
                1,
                pe.get("metric_value", 0),
                pe.get("metric_value", 0),
                f"{pe.get('share_pct', 0)}%",
                pe.get("tier", ""),
            ]
        )
    sheets_spec.append(
        {
            "name": "3_PhanTich_Nhom_ABC",
            "headers": ["Sheet", "Chiều phân tích", "Nhóm / Đối tượng", "Số bản ghi", "Tổng giá trị", "Trung bình", "Tỷ trọng (%)", "Biểu đồ Thanh / Hạng ABC"],
            "rows": s3_rows or [["", "Chưa có nhóm phân loại", "", 0, 0, 0, "0%", ""]],
        }
    )

    # Sheet 4: Phân tích theo Thời gian & Biểu đồ trực quan (Giai đoạn 3.2 & Giai đoạn 4)
    s4_rows: List[List[Any]] = []
    time_series = stage3.get("time_analysis") or {}
    if time_series.get("available"):
        s4_rows.append(
            [
                "XU HƯỚNG THỜI GIAN",
                f"Cột: {time_series.get('time_col', '')} ({time_series.get('granularity', '')})",
                f"Chỉ số: {time_series.get('metric_col', '')}",
                f"Tăng trưởng: {time_series.get('overall_growth_pct', 0)}%",
                time_series.get("summary_note", ""),
            ]
        )
        for pt in time_series.get("periods") or []:
            bar = "▓" * max(1, int(round(float(pt.get("pct_of_peak", 10)) / 5.0)))
            s4_rows.append(
                [
                    pt.get("period", ""),
                    pt.get("count", 0),
                    pt.get("sum", 0),
                    f"{pt.get('mom_growth_pct', 0)}%" if pt.get("mom_growth_pct") is not None else "—",
                    bar,
                ]
            )
    s4_rows.append(["", "", "", "", ""])
    s4_rows.append(["DANH MỤC BIỂU ĐỒ (GIAI ĐOẠN 4)", "LOẠI BIỂU ĐỒ", "TRỤC ĐO & ĐƠN VỊ", "NHẬN XÉT DỮ LIỆU", "Ý NGHĨA KINH DOANH"])
    for ch in stage4:
        s4_rows.append(
            [
                ch.get("title", ""),
                ch.get("chart_type_label", ""),
                f"X: {ch.get('x_axis_label', '')} | Y: {ch.get('y_axis_label', '')}",
                ch.get("commentary", ""),
                ch.get("business_meaning", ""),
            ]
        )
        for dp in (ch.get("data_points") or [])[:15]:
            bar = "█" * max(1, int(round(float(dp.get("pct", 10)) / 5.0)))
            s4_rows.append(
                [
                    f"   ↳ {dp.get('label', '')}",
                    dp.get("value", 0),
                    dp.get("secondary_value", ""),
                    f"{dp.get('pct', 0)}%",
                    bar,
                ]
            )
    sheets_spec.append(
        {
            "name": "4_ThoiGian_BieuDo",
            "headers": ["Kỳ / Tiêu đề Biểu đồ", "Số lượng / Loại biểu đồ", "Giá trị / Trục đo", "Tăng trưởng / Nhận xét", "Trực quan / Ý nghĩa kinh doanh"],
            "rows": s4_rows,
        }
    )

    # Sheet 5: Phân tích Insight (Giai đoạn 5) & Giải pháp (Giai đoạn 6)
    s5_rows: List[List[Any]] = [
        ["GIAI ĐOẠN 5: INSIGHT (DATA → INFORMATION → INSIGHT → DECISION)", "", "", "", "", ""],
        ["MÃ & CHỦ ĐỀ INSIGHT", "1. PHÁT HIỆN ĐIỀU GÌ?", "2. SỐ LIỆU CHỨNG MINH", "3. NGUYÊN NHÂN (CHỨNG MINH vs GIẢ THUYẾT)", "4. TÁC ĐỘNG DOANH NGHIỆP", "5. HÀNH ĐỘNG ĐỀ XUẤT (DECISION)"],
    ]
    for ins in stage5:
        s5_rows.append(
            [
                f"{ins.get('id', '')} · {ins.get('title', '')}",
                ins.get("finding", ""),
                ins.get("evidence", ""),
                f"[Chứng minh]: {ins.get('causes_proven', '')} | [Giả thuyết kiểm chứng]: {ins.get('causes_hypothesis', '')}",
                ins.get("business_impact", ""),
                ins.get("recommended_action", ""),
            ]
        )
    s5_rows.append(["", "", "", "", "", ""])
    s5_rows.append(["GIAI ĐOẠN 6: ĐỀ XUẤT GIẢI PHÁP THỰC THI", "", "", "", "", ""])
    s5_rows.append(["THỨ TỰ ƯU TIÊN", "VẤN ĐỀ CẦN GIẢI QUYẾT", "GIẢI PHÁP CỤ THỂ", "BỘ PHẬN CHỊU TRÁCH NHIỆM", "KPI ĐO LƯỜNG HIỆU QUẢ", "RỦI RO & ĐIỀU KIỆN THỰC HIỆN"])
    for sol in stage6:
        s5_rows.append(
            [
                sol.get("priority_order", ""),
                sol.get("problem", ""),
                sol.get("solution", ""),
                sol.get("department", ""),
                sol.get("kpi", ""),
                sol.get("risks_and_conditions", ""),
            ]
        )
    sheets_spec.append(
        {
            "name": "5_Insight_GiaiPhap",
            "headers": ["Hạng mục / Ưu tiên", "Phát hiện / Vấn đề", "Số liệu / Giải pháp", "Nguyên nhân / Bộ phận", "Tác động / KPI", "Quyết định / Rủi ro & Điều kiện"],
            "rows": s5_rows,
        }
    )

    return _build_xlsx_bytes(sheets_spec)


def export_report_docx_bytes(session_resp: Dict[str, Any]) -> bytes:
    """Product 4: Báo cáo phân tích chuyên nghiệp định dạng Word (.docx)."""
    md_text = ((session_resp.get("proposal") or {}).get("markdown_report") or "").strip()
    if not md_text:
        md_text = "# BÁO CÁO PHÂN TÍCH DỮ LIỆU & BUSINESS INTELLIGENCE — HÀ THUỲ DƯƠNG\nChưa có nội dung báo cáo."

    paragraphs_xml: List[str] = []

    def add_p(text: str, style: str = "Normal", bold: bool = False, color: str = "1E293B", sz_half_pt: int = 22) -> None:
        clean = _clean_xml_text(text)
        b_tag = "<w:b/>" if bold else ""
        paragraphs_xml.append(
            f"""<w:p>
  <w:pPr><w:pStyle w:val="{style}"/><w:spacing w:before="80" w:after="80"/></w:pPr>
  <w:r>
    <w:rPr>{b_tag}<w:color w:val="{color}"/><w:sz w:val="{sz_half_pt}"/></w:rPr>
    <w:t xml:space="preserve">{clean}</w:t>
  </w:r>
</w:p>"""
        )

    for raw_line in md_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        # Strip markdown bold markers for clean Word rendering
        plain = re.sub(r"\*\*(.+?)\*\*", r"\1", line)
        plain = re.sub(r"\*(.+?)\*", r"\1", plain)
        if plain.startswith("# "):
            add_p(plain[2:].strip(), style="Heading1", bold=True, color="BE185D", sz_half_pt=32)
        elif plain.startswith("## "):
            add_p(plain[3:].strip(), style="Heading2", bold=True, color="9D174D", sz_half_pt=26)
        elif plain.startswith("### "):
            add_p(plain[4:].strip(), style="Heading3", bold=True, color="334155", sz_half_pt=24)
        elif plain.startswith("- ") or plain.startswith("* "):
            add_p("• " + plain[2:].strip(), style="Normal", bold=False, color="1E293B", sz_half_pt=21)
        else:
            add_p(plain, style="Normal", bold=False, color="1E293B", sz_half_pt=21)

    document_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">\n'
        "  <w:body>\n"
        + "\n".join(paragraphs_xml)
        + """
    <w:sectPr>
      <w:pgSz w:w="11906" w:h="16838"/>
      <w:pgMar w:top="1134" w:right="1134" w:bottom="1134" w:left="1134"/>
    </w:sectPr>
  </w:body>
</w:document>"""
    )

    styles_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:style w:type="paragraph" w:default="1" w:styleId="Normal">
    <w:name w:val="Normal"/>
    <w:rPr><w:rFonts w:ascii="Calibri" w:hAnsi="Calibri"/><w:sz w:val="22"/></w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Heading1">
    <w:name w:val="heading 1"/>
    <w:rPr><w:b/><w:color w:val="BE185D"/><w:sz w:val="32"/></w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Heading2">
    <w:name w:val="heading 2"/>
    <w:rPr><w:b/><w:color w:val="9D174D"/><w:sz w:val="26"/></w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Heading3">
    <w:name w:val="heading 3"/>
    <w:rPr><w:b/><w:color w:val="334155"/><w:sz w:val="24"/></w:rPr>
  </w:style>
</w:styles>"""

    content_types = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
  <Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
</Types>"""

    root_rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>"""

    doc_rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>"""

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types.encode("utf-8"))
        zf.writestr("_rels/.rels", root_rels.encode("utf-8"))
        zf.writestr("word/document.xml", document_xml.encode("utf-8"))
        zf.writestr("word/styles.xml", styles_xml.encode("utf-8"))
        zf.writestr("word/_rels/document.xml.rels", doc_rels.encode("utf-8"))
    return buf.getvalue()


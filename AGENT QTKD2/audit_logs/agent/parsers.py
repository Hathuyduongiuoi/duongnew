"""Zero-dependency universal parsers for Excel, Word, PDF, OpenDocument, HTML, XML, Markdown, JSON, ZIP, Google Sheets, and Lark Base."""

from __future__ import annotations

import csv
import io
import json
import os
import re
import shutil
import subprocess
import tempfile
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
import zlib
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from xml.sax.saxutils import escape

from .models import CANONICAL_TABLES
from .netutil import secure_urlopen

def strip_accents(text: str) -> str:
    """Normalize Vietnamese text by removing diacritics and mapping đ/Đ -> d/D."""
    if not text:
        return ""
    text = text.replace("đ", "d").replace("Đ", "D")
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in nfkd if not unicodedata.combining(ch))


def norm_key(text: str) -> str:
    """Convert any header or sheet name into lowercase underscore identifier."""
    cleaned = strip_accents(str(text).strip().lower())
    cleaned = re.sub(r"[^a-z0-9]+", "_", cleaned)
    return cleaned.strip("_")


def parse_number(value: Any) -> Optional[float]:
    """Parse flexible Vietnamese/English numeric formats (e.g. '340,5 tỷ', '8.2/10', '25%')."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text or text.lower() in {"na", "n/a", "null", "none", "-", "chua co", "chưa có", "thieu", "thiếu"}:
        return None

    # Handle fraction like '8.5/10' -> 8.5
    frac_match = re.match(r"^\s*([-+]?\d+(?:[.,]\d+)?)\s*/\s*10\s*$", text)
    if frac_match:
        return float(frac_match.group(1).replace(",", "."))

    # Accounting negative "(300.000)" and unicode minus
    is_paren_negative = bool(re.match(r"^\s*\(\s*[^()]*\d[^()]*\)\s*(?:%|[A-Za-zÀ-ỹ]+)?\s*$", text))
    text = text.replace("\u2212", "-").replace("\u2013", "-")

    # Extract first numeric token
    m = re.search(r"[-+]?\d[\d.,]*", text)
    if not m:
        return None
    num_str = m.group(0).rstrip(".,")
    # Disambiguate thousand vs decimal separators
    if "," in num_str and "." in num_str:
        if num_str.rfind(",") > num_str.rfind("."):
            num_str = num_str.replace(".", "").replace(",", ".")
        else:
            num_str = num_str.replace(",", "")
    elif "." in num_str and num_str.count(".") > 1:
        # Vietnamese thousand grouping: 1.250.000
        num_str = num_str.replace(".", "")
    elif re.fullmatch(r"[-+]?[1-9]\d{0,2}\.\d{3}", num_str):
        # Single dot + exactly 3 digits, e.g. 300.000 / 1.250 -> Vietnamese thousands (not 3-decimal numbers)
        num_str = num_str.replace(".", "")
    elif "," in num_str:
        parts = num_str.split(",")
        if len(parts) == 2 and len(parts[1]) != 3:
            num_str = num_str.replace(",", ".")
        elif len(parts) > 2:
            num_str = num_str.replace(",", "")
        else:
            # Ambiguous e.g. 1,200 vs 8,5 -> if <=2 digits before & 3 after treat as decimal? wait 3 digits e.g. 1,500
            num_str = num_str.replace(",", "") if len(parts[1]) == 3 and int(parts[0]) >= 1 else num_str.replace(",", ".")
    try:
        parsed_val = float(num_str)
    except ValueError:
        return None
    if is_paren_negative and parsed_val > 0:
        parsed_val = -parsed_val
    return parsed_val


def parse_bool_flag(value: Any) -> Optional[bool]:
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    k = norm_key(str(value))
    if k in {"true", "1", "yes", "co", "bat_buoc", "hard", "y"}:
        return True
    if k in {"false", "0", "no", "khong", "soft", "n"}:
        return False
    return None


def level_to_score(value: Any, invert: bool = False) -> Optional[float]:
    """Convert qualitative text levels (Cao/Trung bình/Thấp) or numbers to 0-10 score."""
    num = parse_number(value)
    if num is not None:
        score = max(0.0, min(10.0, num))
        return round(10.0 - score, 2) if invert else round(score, 2)
    k = norm_key(str(value or ""))
    mapping = {
        "rat_cao": 9.5,
        "very_high": 9.5,
        "cao": 8.5,
        "high": 8.5,
        "kha": 7.2,
        "trung_binh_cao": 6.8,
        "trung_binh": 5.5,
        "medium": 5.5,
        "moderate": 5.5,
        "thap": 3.0,
        "low": 3.0,
        "rat_thap": 1.5,
        "very_low": 1.5,
        "san_sang": 9.0,
        "ready": 9.0,
        "can_tuy_chinh_nhe": 6.5,
        "can_tuy_chinh": 5.5,
        "chua_ho_tro": 1.5,
        "unsupported": 1.5,
    }
    if k in mapping:
        val = mapping[k]
        return round(10.0 - val, 2) if invert else round(val, 2)
    return None


def decode_text_bytes(raw: bytes) -> str:
    for enc in ("utf-8-sig", "utf-8", "utf-16", "cp1258", "cp1252", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def parse_csv_bytes(raw: bytes, filename: str = "uploaded.csv") -> Dict[str, List[Dict[str, Any]]]:
    """Parse CSV bytes into {sheet_name: [rows]} preserving 1-based row numbers."""
    text = decode_text_bytes(raw)
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        return {}

    sample = "\n".join(lines[:10])
    delimiter = ","
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        delimiter = dialect.delimiter
    except csv.Error:
        if sample.count(";") > sample.count(","):
            delimiter = ";"
        elif sample.count("\t") > sample.count(","):
            delimiter = "\t"

    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    all_rows = list(reader)
    if not all_rows:
        return {}

    # Find first non-empty header row
    header_idx = 0
    while header_idx < len(all_rows) and not any(str(c).strip() for c in all_rows[header_idx]):
        header_idx += 1
    if header_idx >= len(all_rows):
        return {}

    headers = [str(c).strip() or f"col_{i+1}" for i, c in enumerate(all_rows[header_idx])]
    records: List[Dict[str, Any]] = []
    for idx in range(header_idx + 1, len(all_rows)):
        row_vals = all_rows[idx]
        if not any(str(v).strip() for v in row_vals):
            continue
        rec: Dict[str, Any] = {
            "_row_number": idx + 1,
            "_source_file": filename,
            "_sheet_name": Path(filename).stem,
        }
        for col_i, h in enumerate(headers):
            val = row_vals[col_i].strip() if col_i < len(row_vals) else ""
            rec[h] = val
        records.append(rec)

    sheet_key = Path(filename).stem
    return {sheet_key: records}


def _col_letters_to_index(ref: str) -> int:
    m = re.match(r"^([A-Za-z]+)", ref or "")
    if not m:
        return 0
    letters = m.group(1).upper()
    idx = 0
    for ch in letters:
        idx = idx * 26 + (ord(ch) - ord("A") + 1)
    return idx - 1


def _index_to_col_letters(idx: int) -> str:
    res = ""
    n = idx + 1
    while n > 0:
        n, rem = divmod(n - 1, 26)
        res = chr(65 + rem) + res
    return res


def _excel_serial_to_date_str(serial: float) -> str:
    # Excel epoch starts 1899-12-30 (accounts for 1900 leap-year bug)
    dt = datetime(1899, 12, 30) + timedelta(days=serial)
    return dt.strftime("%Y-%m-%d")


def _parse_date_style_ids(styles_xml: Optional[bytes]) -> set:
    if not styles_xml:
        return set()
    date_xf_ids = set()
    try:
        root = ET.fromstring(styles_xml)
    except ET.ParseError:
        return set()

    custom_date_numfmts = set()
    for nf in root.findall(".//{*}numFmts/{*}numFmt"):
        nf_id = nf.attrib.get("numFmtId")
        code = (nf.attrib.get("formatCode") or "").lower()
        if nf_id and any(tok in code for tok in ("yy", "mm", "dd")) and "h" not in code.replace("hh", ""):
            custom_date_numfmts.add(nf_id)

    standard_date_ids = {str(i) for i in range(14, 23)} | {"27", "28", "29", "30", "31", "36", "45", "46", "47", "50", "51", "52", "53", "54", "55", "56", "57", "58"}
    cell_xfs = root.find(".//{*}cellXfs")
    if cell_xfs is not None:
        for idx, xf in enumerate(cell_xfs.findall("{*}xf")):
            nf_id = xf.attrib.get("numFmtId", "")
            if nf_id in standard_date_ids or nf_id in custom_date_numfmts:
                date_xf_ids.add(str(idx))
    return date_xf_ids


def parse_xlsx_bytes(raw: bytes, filename: str = "uploaded.xlsx") -> Dict[str, List[Dict[str, Any]]]:
    """Pure-Python XLSX workbook reader supporting sharedStrings, inlineStr, and dates."""
    if not raw:
        return {}
    try:
        zf = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile as exc:
        raise ValueError(f"File '{filename}' không phải định dạng .xlsx hợp lệ: {exc}") from exc

    names = set(zf.namelist())
    if "xl/workbook.xml" not in names:
        raise ValueError(f"File '{filename}' thiếu xl/workbook.xml")

    # 1. Shared strings
    shared_strings: List[str] = []
    if "xl/sharedStrings.xml" in names:
        ss_root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
        for si in ss_root.findall("{*}si"):
            texts = [t.text or "" for t in si.iter() if t.tag.endswith("}t") or t.tag == "t"]
            shared_strings.append("".join(texts))

    # 2. Styles (to detect Excel numeric dates)
    date_xf_ids = _parse_date_style_ids(zf.read("xl/styles.xml") if "xl/styles.xml" in names else None)

    # 3. Relationships
    rels: Dict[str, str] = {}
    if "xl/_rels/workbook.xml.rels" in names:
        rels_root = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
        for rel in rels_root:
            rid = rel.attrib.get("Id", "")
            target = rel.attrib.get("Target", "")
            if target.startswith("/"):
                target = target.lstrip("/")
            elif not target.startswith("xl/"):
                target = f"xl/{target.lstrip('./')}"
            rels[rid] = target

    # 4. Workbook sheets
    wb_root = ET.fromstring(zf.read("xl/workbook.xml"))
    sheets_meta: List[Tuple[str, str]] = []
    for sh in wb_root.findall(".//{*}sheet"):
        name = sh.attrib.get("name", "Sheet")
        rid = ""
        for k, v in sh.attrib.items():
            if k.endswith("}id") or k == "r:id":
                rid = v
                break
        target = rels.get(rid, "")
        if target and target in names:
            sheets_meta.append((name, target))

    result: Dict[str, List[Dict[str, Any]]] = {}
    for sheet_name, target in sheets_meta:
        sh_root = ET.fromstring(zf.read(target))
        rows_dict: Dict[int, Dict[int, str]] = {}
        max_col = 0
        for row_el in sh_root.findall(".//{*}sheetData/{*}row"):
            r_attr = row_el.attrib.get("r")
            row_idx = int(r_attr) if r_attr and r_attr.isdigit() else (max(rows_dict.keys(), default=0) + 1)
            row_cells: Dict[int, str] = {}
            fallback_col = 0
            for c_el in row_el.findall("{*}c"):
                ref = c_el.attrib.get("r", "")
                col_idx = _col_letters_to_index(ref) if ref else fallback_col
                fallback_col = col_idx + 1
                max_col = max(max_col, col_idx)
                cell_type = c_el.attrib.get("t", "n")
                style_id = c_el.attrib.get("s", "")

                val_str = ""
                if cell_type == "inlineStr":
                    is_el = c_el.find("{*}is")
                    if is_el is not None:
                        val_str = "".join(t.text or "" for t in is_el.iter() if t.tag.endswith("}t") or t.tag == "t")
                else:
                    v_el = c_el.find("{*}v")
                    raw_v = v_el.text if (v_el is not None and v_el.text is not None) else ""
                    if cell_type == "s" and raw_v != "":
                        s_idx = int(float(raw_v))
                        val_str = shared_strings[s_idx] if 0 <= s_idx < len(shared_strings) else raw_v
                    elif cell_type == "b":
                        val_str = "TRUE" if raw_v in ("1", "true", "TRUE") else "FALSE"
                    elif cell_type in ("n", "") and raw_v != "" and style_id in date_xf_ids:
                        try:
                            serial = float(raw_v)
                            if 20000 <= serial <= 80000:
                                val_str = _excel_serial_to_date_str(serial)
                            else:
                                val_str = raw_v
                        except ValueError:
                            val_str = raw_v
                    else:
                        val_str = raw_v

                if val_str.strip() != "":
                    row_cells[col_idx] = val_str.strip()
            if row_cells:
                rows_dict[row_idx] = row_cells

        if not rows_dict:
            result[sheet_name] = []
            continue

        sorted_row_nums = sorted(rows_dict.keys())
        header_row_num = sorted_row_nums[0]
        header_cells = rows_dict[header_row_num]
        used_cols = sorted(set(header_cells.keys()) | {c for r in rows_dict.values() for c in r.keys()})
        headers: Dict[int, str] = {}
        for c_idx in used_cols:
            headers[c_idx] = header_cells.get(c_idx, "").strip() or f"col_{c_idx + 1}"

        records: List[Dict[str, Any]] = []
        for r_num in sorted_row_nums[1:]:
            r_cells = rows_dict[r_num]
            if not any(v.strip() for v in r_cells.values()):
                continue
            rec: Dict[str, Any] = {
                "_row_number": r_num,
                "_source_file": filename,
                "_sheet_name": sheet_name,
            }
            for c_idx in used_cols:
                rec[headers[c_idx]] = r_cells.get(c_idx, "")
            records.append(rec)

        result[sheet_name] = records

    return result


def write_xlsx_file(path: Path, sheets: Dict[str, List[List[Any]]]) -> None:
    """Write a multi-sheet .xlsx file using pure Python stdlib (zero dependencies)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    shared_strings: List[str] = []
    ss_index: Dict[str, int] = {}

    def get_ss(text: str) -> int:
        if text not in ss_index:
            ss_index[text] = len(shared_strings)
            shared_strings.append(text)
        return ss_index[text]

    sheet_xmls: List[Tuple[str, str]] = []
    for sheet_name, rows in sheets.items():
        row_xml_parts: List[str] = []
        for r_idx, row in enumerate(rows, start=1):
            cell_xmls: List[str] = []
            for c_idx, val in enumerate(row):
                ref = f"{_index_to_col_letters(c_idx)}{r_idx}"
                style_attr = ' s="1"' if r_idx == 1 else ""
                if val is None or val == "":
                    continue
                if isinstance(val, bool):
                    b_val = "1" if val else "0"
                    cell_xmls.append(f'<c r="{ref}" t="b"{style_attr}><v>{b_val}</v></c>')
                elif isinstance(val, (int, float)):
                    cell_xmls.append(f'<c r="{ref}"{style_attr}><v>{val}</v></c>')
                else:
                    idx = get_ss(str(val))
                    cell_xmls.append(f'<c r="{ref}" t="s"{style_attr}><v>{idx}</v></c>')
            if cell_xmls:
                row_xml_parts.append(f'<row r="{r_idx}">{"".join(cell_xmls)}</row>')
        ws_xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            f'<sheetData>{"".join(row_xml_parts)}</sheetData>'
            "</worksheet>"
        )
        sheet_xmls.append((sheet_name[:31], ws_xml))

    # Build sharedStrings.xml
    si_items = "".join(f'<si><t xml:space="preserve">{escape(s)}</t></si>' for s in shared_strings)
    ss_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" count="{len(shared_strings)}" uniqueCount="{len(shared_strings)}">'
        f"{si_items}</sst>"
    )

    # Minimal styles.xml (style 0 normal, style 1 bold header)
    styles_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<fonts count="2">'
        '<font><sz val="11"/><name val="Calibri"/></font>'
        '<font><b/><sz val="11"/><name val="Calibri"/></font>'
        '</fonts>'
        '<fills count="2"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill></fills>'
        '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
        '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
        '<cellXfs count="2">'
        '<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
        '<xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/>'
        '</cellXfs>'
        '</styleSheet>'
    )

    content_types_overrides = [
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>',
        '<Override PartName="/xl/sharedStrings.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/>',
        '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>',
    ]
    wb_sheets_xml = []
    wb_rels_xml = [
        '<Relationship Id="rIdSS" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/sharedStrings" Target="sharedStrings.xml"/>',
        '<Relationship Id="rIdStyles" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>',
    ]

    for i, (s_name, _) in enumerate(sheet_xmls, start=1):
        content_types_overrides.append(
            f'<Override PartName="/xl/worksheets/sheet{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        )
        wb_sheets_xml.append(f'<sheet name="{escape(s_name)}" sheetId="{i}" r:id="rId{i}"/>')
        wb_rels_xml.append(
            f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i}.xml"/>'
        )

    content_types_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        f'{"".join(content_types_overrides)}</Types>'
    )
    root_rels_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
        '</Relationships>'
    )
    wb_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f'<sheets>{"".join(wb_sheets_xml)}</sheets></workbook>'
    )
    wb_rels_doc = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        f'{"".join(wb_rels_xml)}</Relationships>'
    )

    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types_xml)
        zf.writestr("_rels/.rels", root_rels_xml)
        zf.writestr("xl/workbook.xml", wb_xml)
        zf.writestr("xl/_rels/workbook.xml.rels", wb_rels_doc)
        zf.writestr("xl/sharedStrings.xml", ss_xml)
        zf.writestr("xl/styles.xml", styles_xml)
        for i, (_, ws_xml) in enumerate(sheet_xmls, start=1):
            zf.writestr(f"xl/worksheets/sheet{i}.xml", ws_xml)


def parse_google_sheet_url(url: str) -> Tuple[str, Optional[str]]:
    """Extract (spreadsheet_id, gid) from a Google Sheets URL."""
    url = (url or "").strip()
    m = re.search(r"https?://docs\.google\.com/spreadsheets/d/([a-zA-Z0-9_-]+)", url)
    if not m:
        raise ValueError(
            "Link Google Sheets không hợp lệ. Vui lòng dùng dạng "
            "https://docs.google.com/spreadsheets/d/<ID>/edit"
        )
    sheet_id = m.group(1)
    gid_match = re.search(r"[?#&]gid=(\d+)", url)
    gid = gid_match.group(1) if gid_match else None
    return sheet_id, gid


def fetch_google_sheet_url(
    url: str,
    fetch_all_tabs: bool = True,
    timeout_sec: int = 20,
) -> Dict[str, List[Dict[str, Any]]]:
    """Download public Google Sheets (all tabs as XLSX or single tab via CSV)."""
    sheet_id, gid = parse_google_sheet_url(url)
    headers = {"User-Agent": "HungPhat-AI-Agent/1.0"}

    if fetch_all_tabs or not gid:
        export_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=xlsx"
        req = urllib.request.Request(export_url, headers=headers)
        try:
            with secure_urlopen(req, timeout=timeout_sec) as resp:
                data = resp.read()
                ctype = (resp.headers.get("Content-Type") or "").lower()
                if "text/html" in ctype or data[:15].lstrip().startswith(b"<"):
                    raise ValueError(
                        "Google Sheet đang ở chế độ riêng tư hoặc yêu cầu đăng nhập. "
                        "Hãy bật 'Bất kỳ ai có đường liên kết -> Người xem' rồi thử lại."
                    )
                return parse_xlsx_bytes(data, filename=f"gsheet_{sheet_id[:8]}.xlsx")
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403):
                raise ValueError(
                    f"Không có quyền truy cập Google Sheet (HTTP {exc.code}). "
                    "Vui lòng mở quyền 'Bất kỳ ai có đường liên kết -> Người xem'."
                ) from exc
            raise ValueError(f"Lỗi tải Google Sheet (HTTP {exc.code}): {exc.reason}") from exc
        except urllib.error.URLError as exc:
            raise ValueError(f"Không thể kết nối tới Google Sheets: {exc.reason}") from exc
    else:
        csv_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}"
        req = urllib.request.Request(csv_url, headers=headers)
        try:
            with secure_urlopen(req, timeout=timeout_sec) as resp:
                data = resp.read()
                ctype = (resp.headers.get("Content-Type") or "").lower()
                if "text/html" in ctype or data[:15].lstrip().startswith(b"<"):
                    raise ValueError(
                        "Google Sheet đang khóa quyền truy cập. "
                        "Hãy bật 'Bất kỳ ai có đường liên kết -> Người xem'."
                    )
                return parse_csv_bytes(data, filename=f"gsheet_{sheet_id[:8]}_gid{gid}.csv")
        except urllib.error.HTTPError as exc:
            raise ValueError(f"Lỗi tải tab Google Sheet (HTTP {exc.code}): {exc.reason}") from exc
        except urllib.error.URLError as exc:
            raise ValueError(f"Không thể kết nối tới Google Sheets: {exc.reason}") from exc


def parse_docx_bytes(raw: bytes, filename: str = "document.docx") -> Tuple[Dict[str, List[Dict[str, Any]]], List[str]]:
    """Extract tables and key-value / statistical paragraphs from a Word (.docx) file using stdlib."""
    if not raw:
        return {}, []
    try:
        zf = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile as exc:
        raise ValueError(
            f"File '{filename}' không phải định dạng Word .docx hợp lệ (nếu dùng .doc cũ, hãy lưu lại thành .docx)."
        ) from exc

    names = set(zf.namelist())
    if "word/document.xml" not in names:
        raise ValueError(f"File Word '{filename}' bị thiếu nội dung word/document.xml.")

    root = ET.fromstring(zf.read("word/document.xml"))
    body = root.find(".//{*}body")
    if body is None:
        return {}, []

    def _p_text(p_el: ET.Element) -> str:
        parts: List[str] = []
        for node in p_el.iter():
            tag = node.tag.split("}")[-1]
            if tag == "t" and node.text:
                parts.append(node.text)
            elif tag == "tab":
                parts.append("\t")
            elif tag in ("br", "cr"):
                parts.append(" ")
        return "".join(parts).strip()

    stem = Path(filename).stem
    sheets: Dict[str, List[Dict[str, Any]]] = {}
    paragraphs: List[str] = []
    table_idx = 0

    for child in list(body):
        tag = child.tag.split("}")[-1]
        if tag == "p":
            txt = _p_text(child)
            if txt:
                paragraphs.append(txt)
        elif tag == "tbl":
            table_idx += 1
            raw_rows: List[List[str]] = []
            for tr in child.findall("./{*}tr"):
                cells_txt: List[str] = []
                for tc in tr.findall("./{*}tc"):
                    cell_paras = [_p_text(p) for p in tc.findall(".//{*}p")]
                    cells_txt.append(" | ".join(t for t in cell_paras if t))
                if any(c.strip() for c in cells_txt):
                    raw_rows.append(cells_txt)

            if len(raw_rows) >= 2:
                max_cols = max(len(r) for r in raw_rows)
                hdr_row = raw_rows[0]
                headers = [
                    (hdr_row[i].strip() if i < len(hdr_row) and hdr_row[i].strip() else f"Cot_{i+1}")
                    for i in range(max_cols)
                ]
                s_name = f"{stem}_Bang_{table_idx}"
                records: List[Dict[str, Any]] = []
                for r_idx, row_vals in enumerate(raw_rows[1:], start=2):
                    rec: Dict[str, Any] = {
                        "_row_number": r_idx,
                        "_source_file": filename,
                        "_sheet_name": s_name,
                    }
                    for c_idx, h in enumerate(headers):
                        rec[h] = row_vals[c_idx].strip() if c_idx < len(row_vals) else ""
                    records.append(rec)
                if records:
                    sheets[s_name] = records

    # Also extract structured statistical / key-value lines from Word paragraphs
    kv_records: List[Dict[str, Any]] = []
    for p_idx, p_txt in enumerate(paragraphs, start=1):
        clean_ln = re.sub(r"^[\-\*\u2022\d\.\)\s]+", "", p_txt).strip()
        if ":" in clean_ln and len(clean_ln) <= 240:
            key_part, val_part = clean_ln.split(":", 1)
            key_part = key_part.strip()
            val_part = val_part.strip()
            if key_part and val_part:
                num_val = parse_number(val_part)
                kv_records.append(
                    {
                        "_row_number": p_idx,
                        "_source_file": filename,
                        "_sheet_name": f"{stem}_ThongKe_Word",
                        "Chi_Tieu": key_part,
                        "Gia_Tri": val_part,
                        "Gia_Tri_So": num_val if num_val is not None else "",
                    }
                )
    if kv_records and not sheets:
        sheets[f"{stem}_ThongKe_Word"] = kv_records
    elif kv_records and len(kv_records) >= 2:
        sheets[f"{stem}_ChiTieu_Word"] = kv_records

    return sheets, paragraphs


def _flatten_lark_value(val: Any) -> str:
    """Convert rich Lark Base Bitable cell values into clean flat string/number text."""
    if val is None:
        return ""
    if isinstance(val, bool):
        return "TRUE" if val else "FALSE"
    if isinstance(val, (int, float)):
        # Detect epoch milliseconds (2000..2100) often used for Lark Date fields
        if isinstance(val, int) and 946684800000 <= val <= 4102444800000:
            dt = datetime.fromtimestamp(val / 1000.0, tz=timezone.utc)
            return dt.strftime("%Y-%m-%d")
        return str(val)
    if isinstance(val, str):
        return val.strip()
    if isinstance(val, dict):
        if "text" in val:
            return str(val.get("text") or "").strip()
        if "name" in val:
            return str(val.get("name") or "").strip()
        if "link" in val:
            return str(val.get("link") or "").strip()
        return json.dumps(val, ensure_ascii=False)
    if isinstance(val, list):
        parts = [_flatten_lark_value(item) for item in val]
        return ", ".join(p for p in parts if p)
    return str(val).strip()


def parse_json_records_bytes(raw: bytes, filename: str = "data.json") -> Dict[str, List[Dict[str, Any]]]:
    """Parse JSON exports (including Lark Base API JSON or generic table JSON)."""
    text = decode_text_bytes(raw)
    try:
        obj = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"File JSON '{filename}' không đúng định dạng JSON: {exc}") from exc

    stem = Path(filename).stem
    raw_items: Optional[List[Any]] = None
    if isinstance(obj, list):
        raw_items = obj
    elif isinstance(obj, dict):
        if isinstance(obj.get("data"), dict) and isinstance(obj["data"].get("items"), list):
            raw_items = obj["data"]["items"]
        elif isinstance(obj.get("items"), list):
            raw_items = obj["items"]
        elif isinstance(obj.get("records"), list):
            raw_items = obj["records"]
        elif all(isinstance(v, list) for v in obj.values()) and obj:
            multi: Dict[str, List[Dict[str, Any]]] = {}
            for k, v_list in obj.items():
                rows = []
                for idx, item in enumerate(v_list, start=1):
                    if isinstance(item, dict):
                        f = item.get("fields") if isinstance(item.get("fields"), dict) else item
                        rec = {"_row_number": idx, "_source_file": filename, "_sheet_name": str(k)}
                        for fk, fv in f.items():
                            rec[str(fk)] = _flatten_lark_value(fv)
                        rows.append(rec)
                if rows:
                    multi[str(k)] = rows
            if multi:
                return multi

    if not raw_items:
        return {}

    records: List[Dict[str, Any]] = []
    for idx, item in enumerate(raw_items, start=1):
        if not isinstance(item, dict):
            continue
        fields = item.get("fields") if isinstance(item.get("fields"), dict) else item
        rec: Dict[str, Any] = {
            "_row_number": idx,
            "_source_file": filename,
            "_sheet_name": stem,
        }
        for fk, fv in fields.items():
            rec[str(fk)] = _flatten_lark_value(fv)
        records.append(rec)
    return {stem: records} if records else {}


def parse_lark_base_url(url: str) -> Tuple[str, str, Optional[str]]:
    """Extract (api_origin, app_token, table_id) from a LarkSuite or Feishu Base URL."""
    clean = (url or "").strip()
    m_domain = re.match(r"^https?://([^/]+)/", clean)
    if not m_domain:
        raise ValueError(
            "Link Lark Base không hợp lệ. Vui lòng dùng dạng "
            "https://xxx.larksuite.com/base/<app_token>?table=<table_id>"
        )
    host = m_domain.group(1).lower()
    if "feishu.cn" in host:
        api_origin = "https://open.feishu.cn/open-apis"
    elif "larksuite.com" in host or "lark" in host:
        api_origin = "https://open.larksuite.com/open-apis"
    else:
        raise ValueError(
            "Link không phải Lark Base (.larksuite.com hoặc .feishu.cn). "
            "Nếu dùng link bảng tính khác, hãy thử Google Sheets hoặc xuất file Excel/CSV."
        )

    m_base = re.search(r"/(?:base|bitable)/([A-Za-z0-9_-]+)", clean)
    if not m_base:
        raise ValueError(
            "Không tìm thấy App Token (/base/<ID>) trong link Lark Base. "
            "Hãy mở trực tiếp Bảng (Base) trên Lark và copy URL trình duyệt."
        )
    app_token = m_base.group(1)
    parsed_qs = urllib.parse.parse_qs(urllib.parse.urlparse(clean).query)
    table_id = (parsed_qs.get("table") or [None])[0]
    return api_origin, app_token, table_id


def _lark_api_request(
    url: str,
    token: Optional[str] = None,
    post_body: Optional[Dict[str, Any]] = None,
    timeout_sec: int = 20,
) -> Dict[str, Any]:
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "User-Agent": "HungPhat-AI-Agent/1.0",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(post_body).encode("utf-8") if post_body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method="POST" if data is not None else "GET")
    try:
        with secure_urlopen(req, timeout=timeout_sec) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        err_txt = exc.read().decode("utf-8", errors="replace")[:260]
        raise ValueError(f"Lark API trả lỗi HTTP {exc.code}: {err_txt}") from exc
    except urllib.error.URLError as exc:
        raise ValueError(f"Không kết nối được máy chủ Lark Base: {exc.reason}") from exc


def convert_lark_records_to_rows(
    table_name: str,
    items: List[Dict[str, Any]],
    source_label: str = "lark_base",
) -> List[Dict[str, Any]]:
    """Flatten Lark Bitable API record items into tabular row dicts."""
    all_keys: List[str] = []
    seen = set()
    for it in items:
        fields = it.get("fields") or {}
        for k in fields.keys():
            if k not in seen:
                seen.add(k)
                all_keys.append(k)

    rows: List[Dict[str, Any]] = []
    for idx, it in enumerate(items, start=1):
        fields = it.get("fields") or {}
        rec: Dict[str, Any] = {
            "_row_number": idx,
            "_source_file": source_label,
            "_sheet_name": table_name,
        }
        for k in all_keys:
            rec[k] = _flatten_lark_value(fields.get(k))
        if any(str(rec[k]).strip() for k in all_keys):
            rows.append(rec)
    return rows


def fetch_lark_base_url(
    url: str,
    lark_app_id: str = "",
    lark_app_secret: str = "",
    lark_token: str = "",
    fetch_all_tabs: bool = True,
    timeout_sec: int = 20,
) -> Dict[str, List[Dict[str, Any]]]:
    """Read tables & records directly from Lark Base (LarkSuite / Feishu Bitable API)."""
    api_origin, app_token, selected_table_id = parse_lark_base_url(url)

    token = (lark_token or "").strip()
    if not token and lark_app_id.strip() and lark_app_secret.strip():
        auth_res = _lark_api_request(
            f"{api_origin}/auth/v3/tenant_access_token/internal",
            post_body={"app_id": lark_app_id.strip(), "app_secret": lark_app_secret.strip()},
            timeout_sec=timeout_sec,
        )
        if auth_res.get("code") != 0 or not auth_res.get("tenant_access_token"):
            raise ValueError(f"Xác thực Lark App thất bại: {auth_res.get('msg') or auth_res}")
        token = str(auth_res["tenant_access_token"])

    if not token:
        raise ValueError(
            "Để đọc trực tiếp link Lark Base, vui lòng nhập Access Token hoặc App ID + App Secret trong phần Lark Base "
            "(hoặc trên Lark Base chọn 'Xuất ra Excel / CSV' rồi tải file lên ngay!)."
        )

    tables_res = _lark_api_request(
        f"{api_origin}/bitable/v1/apps/{app_token}/tables?page_size=100",
        token=token,
        timeout_sec=timeout_sec,
    )
    if tables_res.get("code") != 0:
        raise ValueError(f"Không đọc được danh sách bảng Lark Base: {tables_res.get('msg') or tables_res}")

    tables = (tables_res.get("data") or {}).get("items") or []
    if not fetch_all_tabs and selected_table_id:
        tables = [t for t in tables if t.get("table_id") == selected_table_id] or tables[:1]

    result: Dict[str, List[Dict[str, Any]]] = {}
    for tbl in tables:
        tid = tbl.get("table_id")
        tname = tbl.get("name") or f"LarkTable_{tid}"
        if not tid:
            continue
        collected_items: List[Dict[str, Any]] = []
        page_token = ""
        while True:
            qs = f"page_size=500" + (f"&page_token={urllib.parse.quote(page_token)}" if page_token else "")
            rec_res = _lark_api_request(
                f"{api_origin}/bitable/v1/apps/{app_token}/tables/{tid}/records?{qs}",
                token=token,
                timeout_sec=timeout_sec,
            )
            if rec_res.get("code") != 0:
                raise ValueError(f"Lỗi đọc bản ghi bảng '{tname}' trên Lark Base: {rec_res.get('msg')}")
            data_obj = rec_res.get("data") or {}
            collected_items.extend(data_obj.get("items") or [])
            if not data_obj.get("has_more") or not data_obj.get("page_token"):
                break
            page_token = str(data_obj["page_token"])

        result[tname] = convert_lark_records_to_rows(tname, collected_items, source_label=f"LarkBase:{tname}")

    return result


# --- Universal Document, PDF, OpenDocument, HTML, XML, Markdown, Legacy Office & Archive Parsers ---


def _rows_matrix_to_records(
    raw_rows: List[List[str]],
    filename: str,
    sheet_name: str,
) -> List[Dict[str, Any]]:
    """Convert a 2D list of cells (first non-empty row = header) into normalized record dicts."""
    cleaned_rows = [r for r in raw_rows if any(str(c).strip() for c in r)]
    if len(cleaned_rows) < 2:
        return []
    max_cols = max(len(r) for r in cleaned_rows)
    hdr_row = cleaned_rows[0]
    seen_hdrs: Dict[str, int] = {}
    headers: List[str] = []
    for i in range(max_cols):
        base = (hdr_row[i].strip() if i < len(hdr_row) else "") or f"Cot_{i + 1}"
        if base in seen_hdrs:
            seen_hdrs[base] += 1
            headers.append(f"{base}_{seen_hdrs[base]}")
        else:
            seen_hdrs[base] = 1
            headers.append(base)

    records: List[Dict[str, Any]] = []
    for r_idx, row_vals in enumerate(cleaned_rows[1:], start=2):
        if not any(str(v).strip() for v in row_vals):
            continue
        rec: Dict[str, Any] = {
            "_row_number": r_idx,
            "_source_file": filename,
            "_sheet_name": sheet_name,
        }
        for c_idx, h in enumerate(headers):
            rec[h] = str(row_vals[c_idx]).strip() if c_idx < len(row_vals) else ""
        records.append(rec)
    return records


def _extract_kv_records(
    paragraphs: List[str],
    filename: str,
    sheet_label: str,
) -> List[Dict[str, Any]]:
    """Extract structured Key: Value metric lines from paragraph lists."""
    kv_records: List[Dict[str, Any]] = []
    for p_idx, p_txt in enumerate(paragraphs, start=1):
        clean_ln = re.sub(r"^[\-\*\u2022\d\.\)\s]+", "", p_txt).strip()
        if ":" in clean_ln and len(clean_ln) <= 240:
            key_part, val_part = clean_ln.split(":", 1)
            key_part = key_part.strip()
            val_part = val_part.strip()
            if key_part and val_part and not key_part.lower().startswith("http"):
                num_val = parse_number(val_part)
                kv_records.append(
                    {
                        "_row_number": p_idx,
                        "_source_file": filename,
                        "_sheet_name": sheet_label,
                        "Chi_Tieu": key_part,
                        "Gia_Tri": val_part,
                        "Gia_Tri_So": num_val if num_val is not None else "",
                    }
                )
    return kv_records


class _SimpleHTMLTableParser(HTMLParser):
    """Stdlib HTML parser extracting all <table> grids plus readable non-table blocks."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: List[List[List[str]]] = []
        self.paragraphs: List[str] = []
        self._in_skip = 0
        self._table_depth = 0
        self._in_tr = False
        self._in_cell = False
        self._cur_table: List[List[str]] = []
        self._cur_row: List[str] = []
        self._cur_cell: List[str] = []
        self._cur_block: List[str] = []

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        t = tag.lower()
        if t in ("script", "style", "noscript"):
            self._in_skip += 1
            return
        if self._in_skip:
            return
        if t == "table":
            if self._table_depth == 0:
                self._flush_block()
                self._cur_table = []
            self._table_depth += 1
        elif t == "tr" and self._table_depth > 0:
            self._in_tr = True
            self._cur_row = []
        elif t in ("td", "th") and self._table_depth > 0 and self._in_tr:
            self._in_cell = True
            self._cur_cell = []
        elif t in ("p", "h1", "h2", "h3", "h4", "li", "div", "section", "br") and self._table_depth == 0:
            self._flush_block()

    def handle_endtag(self, tag: str) -> None:
        t = tag.lower()
        if t in ("script", "style", "noscript") and self._in_skip > 0:
            self._in_skip -= 1
            return
        if self._in_skip:
            return
        if t in ("td", "th") and self._in_cell:
            self._cur_row.append(re.sub(r"\s+", " ", "".join(self._cur_cell)).strip())
            self._cur_cell = []
            self._in_cell = False
        elif t == "tr" and self._in_tr:
            if any(c for c in self._cur_row):
                self._cur_table.append(self._cur_row)
            self._cur_row = []
            self._in_tr = False
        elif t == "table" and self._table_depth > 0:
            self._table_depth -= 1
            if self._table_depth == 0 and self._cur_table:
                self.tables.append(self._cur_table)
                self._cur_table = []
        elif t in ("p", "h1", "h2", "h3", "h4", "li") and self._table_depth == 0:
            self._flush_block()

    def handle_data(self, data: str) -> None:
        if self._in_skip:
            return
        if self._in_cell:
            self._cur_cell.append(data)
        elif self._table_depth == 0:
            self._cur_block.append(data)

    def _flush_block(self) -> None:
        txt = re.sub(r"\s+", " ", "".join(self._cur_block)).strip()
        self._cur_block = []
        if txt:
            self.paragraphs.append(txt)


def parse_html_tables_bytes(
    raw: bytes,
    filename: str = "document.html",
) -> Tuple[Dict[str, List[Dict[str, Any]]], List[str]]:
    """Extract all HTML <table> elements into tabular sheets and capture text paragraphs."""
    html_text = decode_text_bytes(raw)
    parser = _SimpleHTMLTableParser()
    parser.feed(html_text)
    parser.close()
    parser._flush_block()

    stem = Path(filename).stem
    sheets: Dict[str, List[Dict[str, Any]]] = {}
    for idx, tbl in enumerate(parser.tables, start=1):
        s_name = stem if (idx == 1 and len(parser.tables) == 1) else f"{stem}_Bang_{idx}"
        recs = _rows_matrix_to_records(tbl, filename, s_name)
        if recs:
            sheets[s_name] = recs

    kv = _extract_kv_records(parser.paragraphs, filename, f"{stem}_ChiTieu")
    if kv and (not sheets or len(kv) >= 2):
        sheets[f"{stem}_ChiTieu"] = kv
    return sheets, parser.paragraphs


def parse_ods_bytes(raw: bytes, filename: str = "workbook.ods") -> Dict[str, List[Dict[str, Any]]]:
    """Pure-Python OpenDocument Spreadsheet (.ods) reader parsing content.xml."""
    try:
        zf = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile as exc:
        raise ValueError(f"File '{filename}' không phải định dạng .ods hợp lệ: {exc}") from exc
    if "content.xml" not in zf.namelist():
        return {}

    root = ET.fromstring(zf.read("content.xml"))
    result: Dict[str, List[Dict[str, Any]]] = {}
    for t_idx, tbl in enumerate(root.findall(".//{*}table"), start=1):
        t_name = None
        for k, v in tbl.attrib.items():
            if k.endswith("}name") or k == "name":
                t_name = v
                break
        sheet_name = t_name or f"Sheet{t_idx}"

        matrix: List[List[str]] = []
        for tr in tbl.findall("{*}table-row"):
            row_repeat = 1
            for k, v in tr.attrib.items():
                if k.endswith("}number-rows-repeated") and v.isdigit():
                    row_repeat = min(int(v), 50)
                    break
            row_vals: List[str] = []
            for tc in tr.findall("{*}table-cell"):
                col_repeat = 1
                raw_val = ""
                for k, v in tc.attrib.items():
                    if k.endswith("}number-columns-repeated") and v.isdigit():
                        col_repeat = min(int(v), 50)
                    elif k.endswith("}value") and raw_val == "":
                        raw_val = v
                p_texts = ["".join(p.itertext()).strip() for p in tc.findall("{*}p")]
                cell_txt = " | ".join(p for p in p_texts if p) or raw_val
                row_vals.extend([cell_txt] * col_repeat)
            while row_vals and not row_vals[-1].strip():
                row_vals.pop()
            if any(c.strip() for c in row_vals):
                for _ in range(row_repeat):
                    matrix.append(list(row_vals))

        recs = _rows_matrix_to_records(matrix, filename, sheet_name)
        if recs:
            result[sheet_name] = recs
    return result


def parse_odt_bytes(raw: bytes, filename: str = "document.odt") -> Tuple[Dict[str, List[Dict[str, Any]]], List[str]]:
    """Pure-Python OpenDocument Text (.odt) reader extracting tables and paragraphs."""
    try:
        zf = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile as exc:
        raise ValueError(f"File '{filename}' không phải định dạng .odt hợp lệ: {exc}") from exc
    if "content.xml" not in zf.namelist():
        return {}, []

    root = ET.fromstring(zf.read("content.xml"))
    body = root.find(".//{*}body/{*}text") or root
    stem = Path(filename).stem
    paragraphs: List[str] = []
    sheets: Dict[str, List[Dict[str, Any]]] = {}
    t_idx = 0

    for child in list(body):
        tag = child.tag.split("}")[-1]
        if tag in ("p", "h"):
            txt = re.sub(r"\s+", " ", "".join(child.itertext())).strip()
            if txt:
                paragraphs.append(txt)
        elif tag == "table":
            t_idx += 1
            matrix: List[List[str]] = []
            for tr in child.findall("{*}table-row"):
                row_vals = [
                    re.sub(r"\s+", " ", "".join(tc.itertext())).strip()
                    for tc in tr.findall("{*}table-cell")
                ]
                if any(row_vals):
                    matrix.append(row_vals)
            s_name = f"{stem}_Bang_{t_idx}"
            recs = _rows_matrix_to_records(matrix, filename, s_name)
            if recs:
                sheets[s_name] = recs

    kv = _extract_kv_records(paragraphs, filename, f"{stem}_ThongKe_ODT")
    if kv and (not sheets or len(kv) >= 2):
        sheets[f"{stem}_ThongKe_ODT"] = kv
    return sheets, paragraphs


def parse_xml_records_bytes(
    raw: bytes,
    filename: str = "data.xml",
) -> Tuple[Dict[str, List[Dict[str, Any]]], List[str]]:
    """Parse Excel 2003 SpreadsheetML XML or generic structured XML into tables & notes."""
    xml_text = decode_text_bytes(raw)
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise ValueError(f"File XML '{filename}' không đúng cấu trúc XML: {exc}") from exc

    stem = Path(filename).stem
    sheets: Dict[str, List[Dict[str, Any]]] = {}

    # 1. Excel 2003 SpreadsheetML (<Workbook>/<Worksheet>/<Table>/<Row>/<Cell><Data>)
    worksheets = root.findall(".//{*}Worksheet")
    if worksheets:
        for idx, ws in enumerate(worksheets, start=1):
            ws_name = None
            for k, v in ws.attrib.items():
                if k.endswith("}Name") or k == "Name":
                    ws_name = v
                    break
            s_name = ws_name or f"Sheet{idx}"
            matrix: List[List[str]] = []
            for row_el in ws.findall(".//{*}Row"):
                row_cells: List[str] = []
                for c_el in row_el.findall("{*}Cell"):
                    idx_attr = None
                    for k, v in c_el.attrib.items():
                        if k.endswith("}Index") or k == "Index":
                            idx_attr = int(v) if v.isdigit() else None
                            break
                    if idx_attr and idx_attr - 1 > len(row_cells):
                        row_cells.extend([""] * (idx_attr - 1 - len(row_cells)))
                    d_el = c_el.find("{*}Data")
                    txt = "".join(d_el.itertext()).strip() if d_el is not None else "".join(c_el.itertext()).strip()
                    row_cells.append(txt)
                if any(c.strip() for c in row_cells):
                    matrix.append(row_cells)
            recs = _rows_matrix_to_records(matrix, filename, s_name)
            if recs:
                sheets[s_name] = recs
        if sheets:
            return sheets, []

    # 2. Generic repeated child element collection in XML
    children = [el for el in list(root) if isinstance(el.tag, str)]
    if not children:
        children = []
    # Unwrap single wrapper like <records><record>...</record></records>
    while len(children) == 1 and list(children[0]):
        children = list(children[0])

    if len(children) >= 2:
        records: List[Dict[str, Any]] = []
        all_cols: List[str] = []
        seen_cols = set()
        raw_items: List[Dict[str, str]] = []
        for el in children:
            item_map: Dict[str, str] = {}
            for ak, av in el.attrib.items():
                ck = ak.split("}")[-1]
                item_map[ck] = av.strip()
            sub_els = list(el)
            if sub_els:
                for sub in sub_els:
                    ck = sub.tag.split("}")[-1]
                    val = re.sub(r"\s+", " ", "".join(sub.itertext())).strip()
                    item_map[ck] = val
            else:
                val = re.sub(r"\s+", " ", "".join(el.itertext())).strip()
                if val:
                    item_map[el.tag.split("}")[-1]] = val
            if item_map:
                for ck in item_map:
                    if ck not in seen_cols:
                        seen_cols.add(ck)
                        all_cols.append(ck)
                raw_items.append(item_map)

        for idx, it in enumerate(raw_items, start=1):
            rec: Dict[str, Any] = {"_row_number": idx, "_source_file": filename, "_sheet_name": stem}
            for ck in all_cols:
                rec[ck] = it.get(ck, "")
            records.append(rec)
        if records:
            sheets[stem] = records
            return sheets, []

    # Fallback flat text lines
    paras = [ln.strip() for ln in root.itertext() if ln and ln.strip()]
    return {}, paras


def parse_markdown_or_text_bytes(
    raw: bytes,
    filename: str = "notes.txt",
) -> Tuple[Dict[str, List[Dict[str, Any]]], List[str]]:
    """Extract Markdown pipe tables, CSV/TSV blocks, Key:Value lines, and paragraphs."""
    text = decode_text_bytes(raw)
    lines = text.splitlines()
    stem = Path(filename).stem
    sheets: Dict[str, List[Dict[str, Any]]] = {}
    paragraphs: List[str] = []

    # Extract Markdown tables | col1 | col2 |
    cur_md_rows: List[List[str]] = []
    md_idx = 0

    def _flush_md() -> None:
        nonlocal cur_md_rows, md_idx
        if len(cur_md_rows) >= 2:
            md_idx += 1
            s_name = stem if md_idx == 1 else f"{stem}_Bang_{md_idx}"
            recs = _rows_matrix_to_records(cur_md_rows, filename, s_name)
            if recs:
                sheets[s_name] = recs
        cur_md_rows = []

    non_table_lines: List[str] = []
    for raw_ln in lines:
        s = raw_ln.strip()
        if s.startswith("|") and s.endswith("|") and s.count("|") >= 2:
            # Skip markdown separator row |---|---|
            inner = s.strip("|").strip()
            if inner and re.fullmatch(r"[\|\-:\s]+", inner):
                continue
            cells = [c.strip() for c in s.strip("|").split("|")]
            cur_md_rows.append(cells)
        else:
            _flush_md()
            if s:
                non_table_lines.append(s)
    _flush_md()

    # If no Markdown table found, check if non-table content is delimited CSV/TSV
    if not sheets and len(non_table_lines) >= 2:
        first_delims = max(non_table_lines[0].count(","), non_table_lines[0].count(";"), non_table_lines[0].count("\t"))
        if first_delims >= 2:
            csv_try = parse_csv_bytes(text.encode("utf-8"), filename=filename)
            if any(len(v) >= 1 for v in csv_try.values()):
                return csv_try, []

    for ln in non_table_lines:
        clean_ln = re.sub(r"^#{1,6}\s+", "", ln).strip()
        if clean_ln:
            paragraphs.append(clean_ln)

    kv = _extract_kv_records(paragraphs, filename, f"{stem}_ChiTieu")
    if kv and (not sheets or len(kv) >= 2):
        sheets[f"{stem}_ChiTieu"] = kv

    return sheets, paragraphs


def _decode_pdf_literal(raw_bytes: bytes) -> str:
    """Decode PDF literal parentheses string or UTF-16BE / PDFDocEncoding tokens."""
    if raw_bytes.startswith(b"\xfe\xff"):
        return raw_bytes[2:].decode("utf-16-be", errors="ignore")
    for enc in ("utf-8", "cp1252", "latin-1"):
        try:
            return raw_bytes.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw_bytes.decode("latin-1", errors="ignore")


def _parse_pdf_content_stream(stream_bytes: bytes) -> List[str]:
    """Extract text lines (Tj, TJ, ', \") from a decompressed PDF content stream."""
    chunks: List[str] = []
    token_re = re.compile(rb"\(((?:\\.|[^\\()])*)\)|<([0-9A-Fa-f\s]+)>")
    for bt_match in re.finditer(rb"BT\b(.*?)\bET", stream_bytes, flags=re.DOTALL):
        block = bt_match.group(1)
        for op_m in re.finditer(
            rb"(\[(?:[^\[\]]|\((?:\\.|[^\\()])*\))*\]|\((?:\\.|[^\\()])*\)|<[0-9A-Fa-f\s]+>)\s*(TJ|Tj|'|\"|Td|TD|T\*)",
            block,
        ):
            op = op_m.group(2)
            if op in (b"Td", b"TD", b"T*"):
                continue
            expr = op_m.group(1)
            op_parts: List[str] = []
            for tm in token_re.finditer(expr):
                if tm.group(1) is not None:
                    unesc = re.sub(
                        rb"\\([\\()nrtbf]|([0-7]{1,3}))",
                        lambda m: (
                            {
                                b"n": b"\n",
                                b"r": b"\r",
                                b"t": b"\t",
                                b"b": b"\b",
                                b"f": b"\f",
                            }.get(m.group(1), bytes([int(m.group(2), 8)]) if m.group(2) else m.group(1))
                        ),
                        tm.group(1),
                    )
                    txt = _decode_pdf_literal(unesc)
                    if txt:
                        op_parts.append(txt)
                elif tm.group(2) is not None:
                    hex_clean = re.sub(rb"\s+", b"", tm.group(2))
                    if len(hex_clean) % 2 == 1:
                        hex_clean += b"0"
                    try:
                        bval = bytes.fromhex(hex_clean.decode("ascii"))
                        txt = _decode_pdf_literal(bval)
                        if txt and sum(ch.isprintable() or ch.isspace() for ch in txt) >= len(txt) * 0.7:
                            op_parts.append(txt)
                    except ValueError:
                        pass
            joined = re.sub(r"\s+", " ", "".join(op_parts)).strip()
            if joined:
                chunks.append(joined)
    return chunks


def parse_pdf_bytes(
    raw: bytes,
    filename: str = "document.pdf",
) -> Tuple[Dict[str, List[Dict[str, Any]]], List[str]]:
    """Pure-Python PDF text/table extractor decompressing FlateDecode streams cleanly."""
    if not raw.lstrip().startswith(b"%PDF"):
        raise ValueError(f"File '{filename}' không phải định dạng PDF hợp lệ.")

    extracted_lines: List[str] = []
    # Extract compressed or uncompressed PDF streams
    for m in re.finditer(rb"stream\r?\n(.*?)\r?\n?endstream", raw, flags=re.DOTALL):
        stream_data = m.group(1)
        candidates = [stream_data]
        for wbits in (zlib.MAX_WBITS, -zlib.MAX_WBITS):
            try:
                candidates.insert(0, zlib.decompress(stream_data, wbits))
                break
            except zlib.error:
                continue
        for buf in candidates:
            if b"BT" in buf and (b"Tj" in buf or b"TJ" in buf):
                extracted_lines.extend(_parse_pdf_content_stream(buf))
                break

    # Deduplicate adjacent identical fragments & normalize lines
    paragraphs: List[str] = []
    for ln in extracted_lines:
        for sub in ln.splitlines():
            clean = sub.strip()
            if clean and len(clean) >= 2:
                paragraphs.append(clean)

    # Attempt multi-space column table extraction from aligned PDF rows
    stem = Path(filename).stem
    sheets: Dict[str, List[Dict[str, Any]]] = {}
    aligned_rows: List[List[str]] = []
    for p in paragraphs:
        cols = [c.strip() for c in re.split(r"\s{2,}|\t|\|", p) if c.strip()]
        if len(cols) >= 3:
            aligned_rows.append(cols)
    if len(aligned_rows) >= 2:
        recs = _rows_matrix_to_records(aligned_rows, filename, f"{stem}_PDF_Bang")
        if recs:
            sheets[f"{stem}_PDF_Bang"] = recs

    kv = _extract_kv_records(paragraphs, filename, f"{stem}_PDF_ChiTieu")
    if kv and (not sheets or len(kv) >= 2):
        sheets[f"{stem}_PDF_ChiTieu"] = kv

    return sheets, paragraphs


def parse_legacy_office_via_textutil(
    raw: bytes,
    filename: str,
) -> Tuple[Dict[str, List[Dict[str, Any]]], List[str]]:
    """Safely convert .doc / .rtf / .webarchive using macOS built-in textutil if available."""
    ext = Path(filename).suffix.lower() or ".txt"
    textutil_bin = shutil.which("textutil")
    if textutil_bin:
        with tempfile.TemporaryDirectory(prefix="hp_textutil_") as tmpdir:
            src_path = Path(tmpdir) / f"input{ext}"
            src_path.write_bytes(raw)
            proc = subprocess.run(
                [textutil_bin, "-convert", "html", "-stdout", str(src_path)],
                capture_output=True,
                timeout=15,
                check=False,
            )
            if proc.returncode == 0 and proc.stdout:
                sheets, paras = parse_html_tables_bytes(proc.stdout, filename=filename)
                if sheets or paras:
                    return sheets, paras

            proc_txt = subprocess.run(
                [textutil_bin, "-convert", "txt", "-stdout", str(src_path)],
                capture_output=True,
                timeout=15,
                check=False,
            )
            if proc_txt.returncode == 0 and proc_txt.stdout:
                return parse_markdown_or_text_bytes(proc_txt.stdout, filename=filename)

    # Pure-Python RTF plain-text fallback
    if ext == ".rtf":
        rtf_txt = raw.decode("latin-1", errors="ignore")
        stripped = re.sub(r"\\[a-z]+\d*\s?|[{}]", " ", rtf_txt)
        stripped = re.sub(r"\s+", "\n", stripped).strip()
        return parse_markdown_or_text_bytes(stripped.encode("utf-8"), filename=filename)

    return {}, []


def parse_xls_bytes(
    raw: bytes,
    filename: str = "legacy.xls",
) -> Tuple[Dict[str, List[Dict[str, Any]]], List[str]]:
    """Smart .xls dispatcher supporting disguised XLSX, HTML-table XLS, SpreadsheetML XML, and binary BIFF strings."""
    head = raw.lstrip()[:256].lower()
    if raw.startswith(b"PK\x03\x04"):
        return parse_xlsx_bytes(raw, filename=filename), []
    if b"<html" in head or b"<table" in head or b"<!doctype html" in head:
        return parse_html_tables_bytes(raw, filename=filename)
    if head.startswith(b"<?xml") or b"<workbook" in head:
        return parse_xml_records_bytes(raw, filename=filename)

    # Binary .xls fallback: try textutil or readable UTF-16/UTF-8 tokens
    sheets, paras = parse_legacy_office_via_textutil(raw, filename=filename)
    if sheets or paras:
        return sheets, paras

    # Extract readable TSV/lines if any tab-delimited blocks exist
    text_guess = decode_text_bytes(raw)
    if "\t" in text_guess:
        return parse_csv_bytes(raw, filename=filename), []
    raise ValueError(
        f"File '{filename}' ở định dạng .xls nhị phân cũ (BIFF8). "
        "Vui lòng mở bằng Excel/Google Sheets và Lưu dưới dạng .xlsx hoặc .csv để đọc đầy đủ 100% các cột."
    )


def parse_zip_archive_bytes(
    raw: bytes,
    filename: str = "bundle.zip",
    dispatch_fn: Any = None,
) -> Tuple[Dict[str, List[Dict[str, Any]]], Dict[str, List[str]]]:
    """Extract and parse all supported files packed inside a .zip archive."""
    try:
        zf = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile as exc:
        raise ValueError(f"File nén '{filename}' không hợp lệ: {exc}") from exc

    all_sheets: Dict[str, List[Dict[str, Any]]] = {}
    all_docs: Dict[str, List[str]] = {}
    for info in zf.infolist():
        if info.is_dir():
            continue
        inner_name = Path(info.filename).name
        if not inner_name or inner_name.startswith(".") or "__MACOSX" in info.filename:
            continue
        inner_bytes = zf.read(info.filename)
        if not inner_bytes:
            continue
        if dispatch_fn is not None:
            s_map, d_map = dispatch_fn(inner_bytes, inner_name)
            for k, v in s_map.items():
                target = k if k not in all_sheets else f"{Path(inner_name).stem}_{k}"
                all_sheets[target] = v
            all_docs.update(d_map)
    return all_sheets, all_docs


# --- Smart Schema Mapping ---

SHEET_KEYWORDS: Dict[str, List[str]] = {
    "market_reports": ["thi_truong", "thitruong", "market", "bao_cao_thi_truong", "tai_lieu_thi_truong"],
    "competitors": ["doi_thu", "doithu", "competitor", "ho_so_doi_thu", "canh_tranh"],
    "customer_feedback": ["phan_hoi", "phanhoi", "khach_hang", "customer", "feedback", "khao_sat"],
    "solution_catalog": ["giai_phap", "giaiphap", "solution", "danh_muc", "catalog", "san_pham"],
    "deployment_capability": ["trien_khai", "trienkhai", "capability", "kha_nang", "nang_luc", "capacity"],
    "evaluation_criteria": ["tieu_chi", "tieuchi", "criteria", "bo_tieu_chi", "rubric", "quy_tac"],
}

COLUMN_ALIASES: Dict[str, Dict[str, List[str]]] = {
    "market_reports": {
        "record_id": ["record_id", "id", "ma_ban_ghi", "ma", "ma_bao_cao"],
        "location": ["dia_ban", "location", "tinh_thanh", "khu_vuc", "thi_truong", "region", "city"],
        "market_size_vnd_bn": ["quy_mo_thi_truong_ty", "quy_mo_thi_truong", "quy_mo", "market_size", "market_size_vnd_bn", "doanh_thu_tiem_nang"],
        "retail_chain_count": ["so_chuoi_ban_le", "so_chuoi", "retail_chain_count", "so_khach_hang_tiem_nang", "so_luong_chuoi"],
        "growth_rate_pct": ["toc_do_tang_truong_pct", "toc_do_tang_truong", "tang_truong", "growth_rate", "growth_rate_pct"],
        "report_period": ["ky_thong_ke", "report_period", "thoi_diem", "ky", "period", "quy", "nam"],
        "period_type": ["loai_ky", "period_type", "don_vi_ky"],
        "published_date": ["ngay_cong_bo", "published_date", "ngay_bao_cao", "date"],
        "source_name": ["nguon_du_lieu", "nguon", "source_name", "source", "tai_lieu_nguon"],
        "origin_source_id": ["ma_nguon_goc", "origin_source_id", "nguon_goc", "primary_source", "ma_nguon"],
        "notes": ["ghi_chu", "notes", "note", "mo_ta"],
    },
    "competitors": {
        "record_id": ["record_id", "id", "ma_doi_thu", "ma"],
        "location": ["dia_ban", "location", "tinh_thanh", "khu_vuc", "region"],
        "competitor_name": ["ten_doi_thu", "competitor_name", "doi_thu", "ten_cong_ty"],
        "market_share_pct": ["thi_phan_uoc_tinh_pct", "thi_phan", "market_share_pct", "market_share"],
        "target_segment": ["phan_khuc_muc_tieu", "phan_khuc", "target_segment"],
        "strengths": ["diem_manh", "strengths", "loi_the"],
        "weaknesses": ["diem_yeu", "weaknesses", "han_che"],
        "competition_level": ["muc_do_canh_tranh", "competition_level", "ap_luc_canh_tranh", "diem_canh_tranh"],
        "source_name": ["nguon_du_lieu", "nguon", "source_name", "source"],
        "report_period": ["ky_thong_ke", "report_period", "thoi_diem", "ngay_cap_nhat"],
    },
    "customer_feedback": {
        "record_id": ["record_id", "id", "ma_phan_hoi", "ma"],
        "location": ["dia_ban", "location", "tinh_thanh", "khu_vuc", "region"],
        "customer_segment": ["nhom_khach_hang", "customer_segment", "phan_khuc", "loai_khach_hang"],
        "customer_name": ["ten_khach_hang", "customer_name", "ten_chuoi", "khach_hang"],
        "store_warehouse_count": ["so_cua_hang_kho", "so_cua_hang", "so_kho", "store_warehouse_count"],
        "required_features": ["nhu_cau_tinh_nang", "required_features", "tinh_nang_can_thiet", "nhu_cau", "yeu_cau_giai_phap"],
        "interest_level": ["muc_do_quan_tam", "interest_level", "quan_tam"],
        "onsite_support_required": ["yeu_cau_ho_tro_tai_cho", "ho_tro_tai_cho", "onsite_support_required", "yeu_cau_onsite"],
        "budget_vnd_m": ["ngan_sach_du_kien_trieu", "ngan_sach", "budget_vnd_m", "budget"],
        "pain_points": ["van_de_hien_tai", "pain_points", "kho_khan"],
        "source_name": ["nguon_du_lieu", "nguon", "source_name", "source"],
        "survey_date": ["ngay_khao_sat", "survey_date", "ky_thong_ke", "thoi_diem"],
    },
    "solution_catalog": {
        "solution_id": ["solution_id", "ma_giai_phap", "id", "ma"],
        "solution_name": ["ten_giai_phap", "solution_name", "giai_phap", "module"],
        "supported_features": ["tinh_nang_ho_tro", "supported_features", "tinh_nang", "features"],
        "target_segments": ["phan_khuc_phu_hop", "target_segments", "doi_tuong_phu_hop"],
        "readiness_status": ["muc_do_san_sang", "readiness_status", "trang_thai_san_pham", "kha_nang_dap_ung"],
        "standard_onsite_level": ["yeu_cau_trien_khai_tai_cho", "standard_onsite_level", "muc_ho_tro_chuan"],
        "notes": ["ghi_chu", "notes", "mo_ta"],
    },
    "deployment_capability": {
        "record_id": ["record_id", "id", "ma"],
        "location": ["dia_ban", "location", "tinh_thanh", "khu_vuc", "region"],
        "max_onsite_capacity": ["nang_luc_ho_tro_tai_cho_toi_da", "nang_luc_tai_cho_toi_da", "max_onsite_capacity", "kha_nang_onsite"],
        "estimated_onsite_demand": ["yeu_cau_tai_cho_thuc_te", "estimated_onsite_demand", "nhu_cau_onsite"],
        "available_engineers": ["so_nhan_su_trien_khai_kha_dung", "so_nhan_su", "available_engineers", "nhan_su"],
        "travel_time_hours": ["thoi_gian_di_chuyen_gio", "thoi_gian_di_chuyen", "travel_time_hours"],
        "sla_hours": ["sla_cam_ket_gio", "sla_hours", "sla"],
        "capability_score": ["diem_nang_luc_trien_khai", "capability_score", "diem_trien_khai"],
        "constraints": ["han_che_hien_tai", "constraints", "rao_can", "ghi_chu"],
        "source_name": ["nguon_du_lieu", "nguon", "source_name", "bo_phan_cung_cap"],
        "updated_date": ["ngay_cap_nhat", "updated_date", "ky_thong_ke"],
    },
    "evaluation_criteria": {
        "criterion_id": ["criterion_id", "ma_tieu_chi", "id", "ma"],
        "criterion_name": ["ten_tieu_chi", "criterion_name", "tieu_chi"],
        "category_key": ["ma_nhom", "category_key", "nhom_tieu_chi"],
        "weight_pct": ["trong_so_pct", "trong_so", "weight_pct", "weight"],
        "min_threshold": ["nguong_toi_thieu", "min_threshold", "nguong_dat", "min_score"],
        "is_hard_gate": ["quy_tac_bat_buoc", "is_hard_gate", "bat_buoc", "hard_gate"],
        "boundary_margin": ["bien_ranh_gioi", "boundary_margin", "dung_sai_bien"],
        "rule_description": ["mo_ta_quy_tac", "rule_description", "mo_ta", "cach_tinh"],
    },
}


def detect_table_for_sheet(sheet_name: str, rows: List[Dict[str, Any]]) -> Tuple[Optional[str], float]:
    """Guess which canonical table a sheet belongs to based on sheet name and headers."""
    s_key = norm_key(sheet_name)
    best_table: Optional[str] = None
    best_score = 0.0

    sample_headers = []
    if rows:
        sample_headers = [norm_key(k) for k in rows[0].keys() if not str(k).startswith("_")]

    for table in CANONICAL_TABLES:
        score = 0.0
        for kw in SHEET_KEYWORDS[table]:
            if kw == s_key:
                score += 10.0
            elif kw in s_key:
                score += 6.0

        aliases = COLUMN_ALIASES[table]
        matched_fields = 0
        for field_aliases in aliases.values():
            norm_aliases = {norm_key(a) for a in field_aliases}
            if any(h in norm_aliases for h in sample_headers):
                matched_fields += 1
        score += matched_fields * 1.5

        if score > best_score:
            best_score = score
            best_table = table

    if best_score < 2.0:
        return None, 0.0
    return best_table, best_score


def map_row_columns(
    table_name: str,
    rows: List[Dict[str, Any]],
    column_overrides: Optional[Dict[str, str]] = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, str]]:
    """Map raw column names in rows to canonical field names while preserving raw data."""
    if not rows:
        return [], {}
    aliases = COLUMN_ALIASES.get(table_name, {})
    raw_headers = [k for k in rows[0].keys() if not str(k).startswith("_")]

    col_map: Dict[str, str] = {}
    used_raw = set()
    overrides = column_overrides or {}

    # Apply explicit user overrides first: {canonical_field: raw_header}
    for canon_field, raw_col in overrides.items():
        if raw_col in raw_headers:
            col_map[canon_field] = raw_col
            used_raw.add(raw_col)

    # Auto-match remaining canonical fields
    for canon_field, field_aliases in aliases.items():
        if canon_field in col_map:
            continue
        norm_aliases = [norm_key(a) for a in field_aliases]
        matched = None
        # Exact match first
        for h in raw_headers:
            if h in used_raw:
                continue
            if norm_key(h) in norm_aliases:
                matched = h
                break
        # Substring fallback
        if not matched:
            for h in raw_headers:
                if h in used_raw:
                    continue
                nh = norm_key(h)
                if any(a in nh or nh in a for a in norm_aliases if len(a) >= 4):
                    matched = h
                    break
        if matched:
            col_map[canon_field] = matched
            used_raw.add(matched)

    normalized_rows: List[Dict[str, Any]] = []
    for r in rows:
        item: Dict[str, Any] = {
            "_row_number": r.get("_row_number", 0),
            "_source_file": r.get("_source_file", ""),
            "_sheet_name": r.get("_sheet_name", ""),
            "_raw": {k: v for k, v in r.items() if not str(k).startswith("_")},
        }
        for canon_field, raw_col in col_map.items():
            item[canon_field] = r.get(raw_col, "")
        normalized_rows.append(item)

    return normalized_rows, col_map


def classify_sheets_to_canonical(
    raw_sheets: Dict[str, List[Dict[str, Any]]],
    table_overrides: Optional[Dict[str, str]] = None,
    column_overrides: Optional[Dict[str, Dict[str, str]]] = None,
) -> Dict[str, Any]:
    """Classify all uploaded sheets into the 6 canonical tables and return schema mapping metadata."""
    table_overrides = table_overrides or {}
    column_overrides = column_overrides or {}

    canonical_data: Dict[str, List[Dict[str, Any]]] = {t: [] for t in CANONICAL_TABLES}
    sheet_assignments: List[Dict[str, Any]] = []
    detected_column_maps: Dict[str, Dict[str, str]] = {}

    for sheet_name, rows in raw_sheets.items():
        override_table = table_overrides.get(sheet_name)
        if override_table in CANONICAL_TABLES:
            target_table = override_table
            confidence = 100.0
        else:
            target_table, confidence = detect_table_for_sheet(sheet_name, rows)

        if target_table:
            mapped_rows, col_map = map_row_columns(
                target_table,
                rows,
                column_overrides=column_overrides.get(target_table),
            )
            canonical_data[target_table].extend(mapped_rows)
            detected_column_maps[target_table] = col_map
        sheet_assignments.append(
            {
                "sheet_name": sheet_name,
                "row_count": len(rows),
                "assigned_table": target_table,
                "confidence": round(confidence, 2),
                "headers": [k for k in rows[0].keys() if not str(k).startswith("_")] if rows else [],
            }
        )

    return {
        "canonical_data": canonical_data,
        "sheet_assignments": sheet_assignments,
        "column_maps": detected_column_maps,
    }


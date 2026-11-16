"""Web server & REST API for Hung Phat Market Expansion AI Agent (AI301 - Project 04)."""

from __future__ import annotations

import argparse
import email.parser
import gzip
import html as html_lib
import json
import mimetypes
import os
import re
import threading
import traceback
import uuid
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import unquote, urlparse

from agent.auth_analytics import (
    SESSION_COOKIE_NAME,
    SESSION_TTL_SEC,
    authenticate_user,
    create_session_token,
    get_admin_dashboard_stats,
    get_site_settings,
    get_user_personal_stats,
    log_analytics_event,
    parse_cookie_header,
    register_user,
    request_password_reset_otp,
    reset_password_with_otp,
    toggle_user_lock,
    update_site_settings,
    verify_session_token,
)
from agent.exporters import (
    export_analysis_excel_bytes,
    export_cleaned_excel_bytes,
    export_report_docx_bytes,
)
from agent.llm_client import chat_with_assistant, extract_table_and_text_with_gemini_vision
from agent.models import CANONICAL_TABLES, TABLE_LABELS_VI
from agent.orchestrator import MarketEvaluationOrchestrator
from agent.parsers import (
    COLUMN_ALIASES,
    classify_sheets_to_canonical,
    fetch_google_sheet_url,
    fetch_lark_base_url,
    parse_csv_bytes,
    parse_docx_bytes,
    parse_html_tables_bytes,
    parse_json_records_bytes,
    parse_legacy_office_via_textutil,
    parse_markdown_or_text_bytes,
    parse_ods_bytes,
    parse_odt_bytes,
    parse_pdf_bytes,
    parse_xls_bytes,
    parse_xlsx_bytes,
    parse_xml_records_bytes,
    parse_zip_archive_bytes,
)
from agent.skills.skill_evaluate_rank import DEFAULT_CRITERIA


ROOT_DIR = Path(__file__).resolve().parent
WEB_DIR = ROOT_DIR / "web"
SAMPLES_DIR = ROOT_DIR / "data" / "samples"
_RUNTIME_DIR = Path("/tmp/htd_runtime") if os.environ.get("VERCEL") else (ROOT_DIR / ".htd_data")
_RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
AUDIT_DIR = (Path("/tmp/htd_runtime") / "audit_logs") if os.environ.get("VERCEL") else (ROOT_DIR / "audit_logs")
AUDIT_DIR.mkdir(parents=True, exist_ok=True)
SESSION_CACHE_DIR = Path("/tmp/htd_sessions")
SESSION_CACHE_DIR.mkdir(parents=True, exist_ok=True)
if (ROOT_DIR / "contact_requests.jsonl").is_file() and not (_RUNTIME_DIR / "contact_requests.jsonl").is_file():
    try:
        (ROOT_DIR / "contact_requests.jsonl").replace(_RUNTIME_DIR / "contact_requests.jsonl")
    except Exception:
        pass
CONTACT_FILE = _RUNTIME_DIR / "contact_requests.jsonl"
_CONTACT_LOCK = threading.Lock()


def _prune_old_audit_files(keep: int = 5) -> None:
    """Keep audit_logs/ compact so local workspace stays cleanly under 100 files."""
    try:
        jsons = sorted(AUDIT_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        for old in jsons[keep:]:
            old.unlink(missing_ok=True)
    except Exception:
        pass


def _save_run_session(run_id: str) -> None:
    if not run_id or run_id not in ORCHESTRATOR.sessions:
        return
    sess = ORCHESTRATOR.sessions[run_id]
    snap = {
        "last_response": sess.get("last_response") or {},
        "cleaned_sheets": sess.get("cleaned_sheets") or {},
        "raw_sheets": sess.get("raw_sheets") or {},
    }
    try:
        (SESSION_CACHE_DIR / f"{run_id}.session.json").write_text(
            json.dumps(snap, ensure_ascii=False, default=str),
            encoding="utf-8",
        )
        _prune_old_audit_files(5)
    except Exception:
        pass


def _get_run_session(run_id: str) -> Optional[Dict[str, Any]]:
    if run_id in ORCHESTRATOR.sessions:
        return ORCHESTRATOR.sessions[run_id]
    snap_path = SESSION_CACHE_DIR / f"{run_id}.session.json"
    if snap_path.is_file():
        try:
            sess = json.loads(snap_path.read_text(encoding="utf-8"))
            if isinstance(sess, dict):
                ORCHESTRATOR.sessions[run_id] = sess
                return sess
        except Exception:
            pass
    return None

# Clean, keyword-rich URLs served by the single-page shell (index.html)
SPA_ROUTES = {
    "/hathuyduong2403": "Hà Thuỳ Dương",
    "/gioi-thieu": "Giới thiệu",
    "/quy-trinh": "Quy trình",
    "/dich-vu": "Dịch vụ",
    "/phan-hoi": "Phản hồi",
    "/lien-he": "Liên hệ",
    "/gui-du-lieu": "Gửi dữ liệu",
    "/xu-ly": "Nhận & làm sạch dữ liệu",
    "/ket-qua": "Kết quả phân tích",
    "/faq": "Hỏi đáp",
    "/chinh-sach-bao-mat": "Chính sách bảo mật",
    "/dieu-khoan": "Điều khoản sử dụng",
}
SITEMAP_PATHS = ["/", "/gioi-thieu", "/quy-trinh", "/dich-vu", "/gui-du-lieu", "/lien-he", "/faq", "/chinh-sach-bao-mat", "/dieu-khoan"]


def build_sitemap_xml(base_url: str) -> str:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    items = []
    for p in SITEMAP_PATHS:
        prio = "1.0" if p == "/" else "0.8" if p in ("/dich-vu", "/gui-du-lieu", "/gioi-thieu") else "0.5"
        items.append(
            f"  <url><loc>{html_lib.escape(base_url + p)}</loc><lastmod>{today}</lastmod>"
            f"<changefreq>weekly</changefreq><priority>{prio}</priority></url>"
        )
    return '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + "\n".join(items) + "\n</urlset>\n"


def build_robots_txt(base_url: str) -> str:
    return (
        "User-agent: *\n"
        "Allow: /\n"
        "Disallow: /api/\n"
        f"Sitemap: {base_url}/sitemap.xml\n"
    )


def save_contact_request(payload: Dict[str, Any]) -> None:
    """Validate and append a contact form submission to contact_requests.jsonl."""
    if str(payload.get("website") or "").strip():
        return  # honeypot filled: silently drop bot submissions
    name = str(payload.get("name") or "").strip()[:120]
    contact = str(payload.get("contact") or "").strip()[:160]
    message = str(payload.get("message") or "").strip()[:2000]
    topic = str(payload.get("topic") or "").strip()[:120]
    if not name:
        raise ValueError("Vui lòng nhập họ và tên.")
    is_email = bool(re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]{2,}", contact))
    is_phone = len(re.sub(r"\D", "", contact)) >= 8
    if not (is_email or is_phone):
        raise ValueError("Vui lòng nhập email hoặc số điện thoại hợp lệ.")
    record = {
        "received_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "name": name,
        "contact": contact,
        "topic": topic,
        "message": message,
    }
    with _CONTACT_LOCK:
        with CONTACT_FILE.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def load_dotenv_file(env_path: Path) -> None:
    """Load simple KEY=VALUE entries from .env into os.environ if not already set."""
    if not env_path.is_file():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v


load_dotenv_file(ROOT_DIR / ".env")

ORCHESTRATOR = MarketEvaluationOrchestrator(log_dir=AUDIT_DIR)
STAGED_INPUTS: Dict[str, Dict[str, Any]] = {}


SAMPLE_CATALOG = [
    {
        "id": "case1_thong_thuong",
        "title": "Kịch bản 1: Thông thường (Có bẫy trùng nguồn & quá tải triển khai)",
        "description": (
            "4 địa bàn (Bình Dương, Đà Nẵng, Hải Phòng, Cần Thơ). Có số liệu lặp cùng nguồn tại Hải Phòng, "
            "lệch kỳ quý/năm tại Cần Thơ, Hải Phòng quy mô lớn nhất nhưng quá tải hỗ trợ tại chỗ, Cần Thơ không khớp sản phẩm."
        ),
        "file": "case1_thong_thuong.xlsx",
    },
    {
        "id": "case2_thieu_mau_thuan",
        "title": "Kịch bản 2: Thiếu dữ liệu & Mâu thuẫn (Kích hoạt HITL Bước 2)",
        "description": (
            "Nghệ An thiếu phản hồi khách hàng & năng lực triển khai; Đà Nẵng mâu thuẫn 50% quy mô thị trường "
            "và mâu thuẫn yêu cầu tại chỗ giữa 2 nguồn. Agent dừng tại Bước 2 để con người xử lý."
        ),
        "file": "case2_thieu_mau_thuan.xlsx",
    },
    {
        "id": "case3_ranh_gioi_quy_tac",
        "title": "Kịch bản 3: Tại ranh giới quy tắc (Fit=6.00 vs 5.95 & Sát điểm #2/#3)",
        "description": (
            "Đà Nẵng đạt đúng ngưỡng Fit=6.00 và Capability=6.00; Hải Phòng rớt sát ngưỡng (5.95 < 6.0); "
            "Đà Nẵng (#2) chỉ hơn Khánh Hòa (#3) 0.13 điểm -> kích hoạt Kiểm tra ranh giới (HITL #2)."
        ),
        "file": "case3_ranh_gioi_quy_tac.xlsx",
    },
]


def parse_multipart_form(content_type: str, body: bytes) -> Tuple[Dict[str, List[str]], List[Dict[str, Any]]]:
    """Parse multipart/form-data cleanly using stdlib email.parser."""
    header_bytes = f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode("latin-1")
    msg = email.parser.BytesParser().parsebytes(header_bytes + body)
    fields: Dict[str, List[str]] = {}
    files: List[Dict[str, Any]] = []

    if not msg.is_multipart():
        return fields, files

    for part in msg.get_payload():
        name = part.get_param("name", header="content-disposition")
        if not name:
            continue
        filename = part.get_filename()
        payload = part.get_payload(decode=True) or b""
        if filename is not None and filename != "":
            files.append(
                {
                    "field": name,
                    "filename": os.path.basename(filename),
                    "content": payload,
                }
            )
        else:
            fields.setdefault(name, []).append(payload.decode("utf-8", errors="replace"))
    return fields, files


def _dispatch_uploaded_file_bytes(
    content: bytes,
    fname: str,
    gemini_key: str = "",
    gemini_model: str = "gemini-2.5-flash",
) -> Tuple[Dict[str, List[Dict[str, Any]]], Dict[str, List[str]]]:
    """Dispatch any uploaded document, spreadsheet, PDF, archive, or image into sheets & text paragraphs."""
    ext = Path(fname).suffix.lower()
    sheets_out: Dict[str, List[Dict[str, Any]]] = {}
    docs_out: Dict[str, List[str]] = {}

    if ext in (".csv", ".tsv"):
        sheets_out = parse_csv_bytes(content, filename=fname)
    elif ext in (".txt", ".md", ".markdown", ".log", ".yaml", ".yml"):
        s_map, paras = parse_markdown_or_text_bytes(content, filename=fname)
        sheets_out = s_map
        if paras:
            docs_out[fname] = paras
    elif ext in (".xlsx", ".xlsm"):
        sheets_out = parse_xlsx_bytes(content, filename=fname)
    elif ext == ".xls":
        s_map, paras = parse_xls_bytes(content, filename=fname)
        sheets_out = s_map
        if paras:
            docs_out[fname] = paras
    elif ext == ".ods":
        sheets_out = parse_ods_bytes(content, filename=fname)
    elif ext == ".docx":
        s_map, paras = parse_docx_bytes(content, filename=fname)
        sheets_out = s_map
        if paras:
            docs_out[fname] = paras
    elif ext == ".odt":
        s_map, paras = parse_odt_bytes(content, filename=fname)
        sheets_out = s_map
        if paras:
            docs_out[fname] = paras
    elif ext in (".doc", ".rtf", ".webarchive"):
        s_map, paras = parse_legacy_office_via_textutil(content, filename=fname)
        sheets_out = s_map
        if paras:
            docs_out[fname] = paras
    elif ext in (".html", ".htm", ".mhtml"):
        s_map, paras = parse_html_tables_bytes(content, filename=fname)
        sheets_out = s_map
        if paras:
            docs_out[fname] = paras
    elif ext == ".xml":
        s_map, paras = parse_xml_records_bytes(content, filename=fname)
        sheets_out = s_map
        if paras:
            docs_out[fname] = paras
    elif ext == ".json":
        sheets_out = parse_json_records_bytes(content, filename=fname)
    elif ext == ".pdf":
        s_map, paras = parse_pdf_bytes(content, filename=fname)
        if not s_map and not paras and gemini_key:
            s_map, paras = extract_table_and_text_with_gemini_vision(
                gemini_key, gemini_model, content, "application/pdf", fname
            )
        sheets_out = s_map
        if paras:
            docs_out[fname] = paras
    elif ext in (".png", ".jpg", ".jpeg", ".webp", ".gif"):
        if not gemini_key:
            raise ValueError(
                f"File ảnh '{fname}' cần Gemini API Key (trong Cài đặt hoặc .env) để AI Vision trích xuất bảng và số liệu."
            )
        mime_map = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".webp": "image/webp",
            ".gif": "image/gif",
        }
        s_map, paras = extract_table_and_text_with_gemini_vision(
            gemini_key, gemini_model, content, mime_map[ext], fname
        )
        sheets_out = s_map
        if paras:
            docs_out[fname] = paras
    elif ext == ".zip":
        return parse_zip_archive_bytes(
            content,
            filename=fname,
            dispatch_fn=lambda b, inner_fn: _dispatch_uploaded_file_bytes(b, inner_fn, gemini_key, gemini_model),
        )
    else:
        # Unknown extension: auto-sniff ZIP / JSON / HTML / XML / Markdown-CSV text cleanly
        if content.startswith(b"PK\x03\x04"):
            try:
                sheets_out = parse_xlsx_bytes(content, filename=fname)
                return sheets_out, docs_out
            except Exception:
                return parse_zip_archive_bytes(
                    content,
                    filename=fname,
                    dispatch_fn=lambda b, inner_fn: _dispatch_uploaded_file_bytes(b, inner_fn, gemini_key, gemini_model),
                )
        head = content.lstrip()[:128].lower()
        if b"\x00" in content[:4096] and not content.startswith(b"\xff\xfe") and not content.startswith(b"\xfe\xff"):
            raise ValueError(
                f"Định dạng file '{fname}' chưa hỗ trợ (file nhị phân). Hãy gửi Excel (.xlsx/.xls/.csv), Word (.docx), "
                "PDF, JSON/Lark, XML, HTML, Markdown, ZIP hoặc ảnh."
            )
        if head.startswith(b"{") or head.startswith(b"["):
            sheets_out = parse_json_records_bytes(content, filename=fname)
        elif b"<html" in head or b"<table" in head:
            s_map, paras = parse_html_tables_bytes(content, filename=fname)
            sheets_out = s_map
            if paras:
                docs_out[fname] = paras
        elif head.startswith(b"<?xml"):
            s_map, paras = parse_xml_records_bytes(content, filename=fname)
            sheets_out = s_map
            if paras:
                docs_out[fname] = paras
        else:
            s_map, paras = parse_markdown_or_text_bytes(content, filename=fname)
            sheets_out = s_map
            if paras:
                docs_out[fname] = paras

    return sheets_out, docs_out


def load_inputs_from_sources(
    uploaded_files: List[Dict[str, Any]],
    google_sheet_urls: List[str],
    sample_id: str = "",
    fetch_all_tabs: bool = True,
    lark_base_urls: Optional[List[str]] = None,
    lark_app_id: str = "",
    lark_app_secret: str = "",
    lark_token: str = "",
    document_texts_out: Optional[Dict[str, List[str]]] = None,
    gemini_key: str = "",
    gemini_model: str = "gemini-2.5-flash",
) -> Tuple[Dict[str, List[Dict[str, Any]]], List[Dict[str, Any]]]:
    """Load and merge raw sheets from Excel, Word, PDF, OpenDocument, HTML, XML, Markdown, JSON, ZIP, Images, Google Sheets, and Lark Base."""
    raw_sheets: Dict[str, List[Dict[str, Any]]] = {}
    source_meta: List[Dict[str, Any]] = []
    lark_base_urls = lark_base_urls or []
    eff_gemini_key = (gemini_key or os.environ.get("GEMINI_API_KEY") or "").strip()

    def merge_sheets(new_sheets: Dict[str, List[Dict[str, Any]]], origin_label: str, kind: str) -> None:
        for s_name, rows in new_sheets.items():
            key = s_name
            suffix = 2
            while key in raw_sheets:
                key = f"{s_name}_{suffix}"
                suffix += 1
            raw_sheets[key] = rows
            source_meta.append(
                {
                    "source": origin_label,
                    "type": kind,
                    "sheet_name": key,
                    "rows": len(rows),
                }
            )

    if sample_id:
        sample_path = SAMPLES_DIR / f"{sample_id}.xlsx"
        if not sample_path.exists():
            raise ValueError(f"Không tìm thấy bộ dữ liệu mẫu '{sample_id}'.")
        parsed = parse_xlsx_bytes(sample_path.read_bytes(), filename=sample_path.name)
        merge_sheets(parsed, sample_path.name, "sample_xlsx")

    for f in uploaded_files:
        fname = f["filename"]
        content = f["content"]
        ext = Path(fname).suffix.lower().lstrip(".") or "text"
        s_map, d_map = _dispatch_uploaded_file_bytes(content, fname, eff_gemini_key, gemini_model)
        has_rows = any(bool(rows) for rows in s_map.values())
        has_text = any(bool(p) for p in d_map.values())
        if not has_rows and not has_text:
            hint = (
                " (PDF/ảnh dạng scan cần Gemini API Key để AI đọc chữ)"
                if ext in ("pdf", "png", "jpg", "jpeg", "webp", "gif")
                else ""
            )
            raise ValueError(
                f"AI không đọc được dữ liệu nào từ file '{fname}'{hint}. "
                "File có thể rỗng, chỉ có tiêu đề, hoặc sai định dạng — vui lòng gửi lại file khác."
            )
        if s_map:
            merge_sheets({k: v for k, v in s_map.items() if v}, fname, ext)
        elif d_map:
            # Synthesize a structured table from readable document paragraphs so all 4 studio steps work seamlessly
            syn_sheets: Dict[str, List[Dict[str, Any]]] = {}
            for d_name, paras in d_map.items():
                if not paras:
                    continue
                s_key = f"{Path(d_name).stem}_NoiDung"
                syn_sheets[s_key] = [
                    {
                        "_row_number": idx + 1,
                        "_source_file": fname,
                        "_sheet_name": s_key,
                        "Dong": idx + 1,
                        "Noi_Dung": ln,
                    }
                    for idx, ln in enumerate(paras)
                    if str(ln).strip()
                ]
            if syn_sheets:
                merge_sheets(syn_sheets, fname, f"{ext}_text")
        if document_texts_out is not None and d_map:
            for d_name, paras in d_map.items():
                document_texts_out[d_name] = paras

    for url in google_sheet_urls:
        clean_url = url.strip()
        if not clean_url:
            continue
        if "larksuite.com" in clean_url.lower() or "feishu.cn" in clean_url.lower():
            parsed = fetch_lark_base_url(
                clean_url,
                lark_app_id=lark_app_id or os.environ.get("LARK_APP_ID", ""),
                lark_app_secret=lark_app_secret or os.environ.get("LARK_APP_SECRET", ""),
                lark_token=lark_token or os.environ.get("LARK_ACCESS_TOKEN", ""),
                fetch_all_tabs=fetch_all_tabs,
            )
            merge_sheets(parsed, clean_url, "lark_base")
        else:
            parsed = fetch_google_sheet_url(clean_url, fetch_all_tabs=fetch_all_tabs)
            merge_sheets(parsed, clean_url, "google_sheet")

    for l_url in lark_base_urls:
        clean_l = l_url.strip()
        if not clean_l:
            continue
        parsed = fetch_lark_base_url(
            clean_l,
            lark_app_id=lark_app_id or os.environ.get("LARK_APP_ID", ""),
            lark_app_secret=lark_app_secret or os.environ.get("LARK_APP_SECRET", ""),
            lark_token=lark_token or os.environ.get("LARK_ACCESS_TOKEN", ""),
            fetch_all_tabs=fetch_all_tabs,
        )
        merge_sheets(parsed, clean_l, "lark_base")

    has_doc_text = bool(document_texts_out and any(v for v in document_texts_out.values()))
    if not raw_sheets and not has_doc_text:
        raise ValueError("Chưa có dữ liệu đầu vào nào được nạp (vui lòng tải Excel, Word .docx, JSON, Google Sheet hoặc Lark Base).")

    return raw_sheets, source_meta


def _render_md_to_clean_html(md_raw: str) -> str:
    """Convert Markdown report cleanly into Vietnamese-typed editorial HTML (no raw ## or ** tokens)."""
    lines = str(md_raw or "").splitlines()
    out: List[str] = []
    in_list = False
    in_table = False

    def close_blocks() -> None:
        nonlocal in_list, in_table
        if in_list:
            out.append("</ul>")
            in_list = False
        if in_table:
            out.append("</tbody></table>")
            in_table = False

    def fmt_inline(txt: str) -> str:
        s = html_lib.escape(txt)
        s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
        s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
        return s

    for raw in lines:
        ln = raw.strip()
        if not ln:
            close_blocks()
            continue
        if ln.startswith("|") and ln.endswith("|"):
            if not ln.replace("|", "").replace("-", "").replace(":", "").strip():
                continue
            cells = [fmt_inline(c.strip()) for c in ln.split("|")[1:-1]]
            if not in_table:
                close_blocks()
                out.append("<table><thead><tr>" + "".join(f"<th>{c}</th>" for c in cells) + "</tr></thead><tbody>")
                in_table = True
            else:
                out.append("<tr>" + "".join(f"<td>{c}</td>" for c in cells) + "</tr>")
            continue
        close_blocks()
        if ln.startswith("### "):
            out.append(f"<h3>{fmt_inline(ln[4:])}</h3>")
        elif ln.startswith("## "):
            out.append(f"<h2>{fmt_inline(ln[3:])}</h2>")
        elif ln.startswith("# "):
            out.append(f"<h1>{fmt_inline(ln[2:])}</h1>")
        elif ln.startswith("- "):
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append(f"<li>{fmt_inline(ln[2:])}</li>")
        else:
            out.append(f"<p>{fmt_inline(ln)}</p>")
    close_blocks()
    return "\n".join(out)


def render_standalone_html_report(res: Dict[str, Any]) -> str:
    """Build a standalone frosted-pastel HTML report & dashboard export (Xuất HTML)."""
    prop = res.get("proposal") or {}
    md_html = _render_md_to_clean_html(prop.get("markdown_report") or "")
    run_id = html_lib.escape(str(res.get("run_id") or ""))
    status_txt = html_lib.escape(str(res.get("workflow_status") or ""))

    if res.get("analysis_mode") == "company_statistics":
        cs = res.get("company_stats") or {}
        domain_lbl = html_lib.escape(str(cs.get("domain_label") or "Thống Kê & Tổng Hợp Dữ Liệu"))
        kpi_tree = cs.get("kpi_tree") or {}
        kpi_branches_html = "".join(
            f"<div class='card'><div><strong>{html_lib.escape(str(b.get('name') or ''))}</strong> · <span>{html_lib.escape(str(b.get('owner') or ''))}</span></div>"
            f"<p>{html_lib.escape(str(b.get('summary') or ''))}</p>"
            f"<ul>" + "".join(
                f"<li>{html_lib.escape(str(ch.get('label') or ''))}: <strong>{html_lib.escape(str(ch.get('value') or ''))}</strong></li>"
                for ch in (b.get("children") or [])
            ) + "</ul></div>"
            for b in (kpi_tree.get("branches") or [])
        )
        priority_rows = "".join(
            f"<tr><td>#{pe.get('rank')}</td><td><strong>{html_lib.escape(str(pe.get('name') or ''))}</strong></td>"
            f"<td>{html_lib.escape(str(pe.get('tier') or ''))}</td><td><strong>{pe.get('value')}</strong></td>"
            f"<td>{pe.get('share_pct')}%</td><td>{html_lib.escape(str(pe.get('group_label') or pe.get('status_badge') or '-'))}</td></tr>"
            for pe in (cs.get("priority_entities") or [])[:15]
        )
        num_rows = "".join(
            f"<tr><td><strong>{html_lib.escape(str(n.get('table') or ''))}</strong></td>"
            f"<td>{html_lib.escape(str(n.get('column') or ''))}</td>"
            f"<td>{n.get('count')}</td><td><strong>{n.get('sum')}</strong></td>"
            f"<td>{n.get('avg')}</td><td>{n.get('min')}</td><td>{n.get('max')}</td></tr>"
            for n in (cs.get("numeric_highlights") or [])
        )
        return f"""<!DOCTYPE html>
<html lang="vi"><head><meta charset="UTF-8" /><title>{domain_lbl} ({run_id})</title>
<link href="https://fonts.googleapis.com/css2?family=Be+Vietnam+Pro:wght@400;500;600;700;800&display=swap" rel="stylesheet" />
<style>
  body {{ font-family: "Be Vietnam Pro", -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif; margin: 0; padding: 32px; background: linear-gradient(135deg, #ffd6e7 0%, #ffe8ee 50%, #ffe2d1 100%); color: #3f2d38; line-height: 1.7; }}
  .wrap {{ max-width: 1020px; margin: 0 auto; background: rgba(255,255,255,0.88); border: 1.5px solid #fff; border-radius: 28px; padding: 30px; box-shadow: 0 24px 60px -16px rgba(236,72,153,.24); }}
  h1 {{ margin: 0 0 8px; color: #be185d; font-size: 22px; }}
  h2 {{ color: #9d174d; font-size: 16px; margin-top: 22px; padding: 6px 12px; border-left: 4px solid #ec4899; background: #fff1f6; border-radius: 0 12px 12px 0; }}
  .kpis {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 14px; margin: 18px 0; }}
  .card {{ background: rgba(255,255,255,0.92); border: 1.5px solid #fbcfe8; border-radius: 20px; padding: 16px; }}
  .card ul {{ padding-left: 18px; margin: 8px 0 0; font-size: 13px; }}
  table {{ width: 100%; border-collapse: collapse; margin: 12px 0 24px; background: #fff; border-radius: 16px; overflow: hidden; font-size: 12.5px; }}
  th, td {{ padding: 10px 12px; border-bottom: 1px solid #fce7f3; text-align: left; }}
  th {{ background: linear-gradient(90deg, #fce7f3, #ffedd5); color: #9d174d; font-weight: 800; }}
  code {{ font-family: inherit; font-weight: 700; padding: 2px 7px; border-radius: 999px; background: #fdf2f8; color: #be185d; border: 1px solid #fbcfe8; }}
  .report-box {{ background: #fff; padding: 20px 24px; border-radius: 20px; border: 1.5px solid #fbcfe8; font-size: 13.5px; }}
</style></head>
<body><div class="wrap">
  <h1>🌸 Hà Thuỳ Dương · Chuyên viên Data Analyst &amp; BI · {domain_lbl}</h1>
  <div class="kpis">
    <div class="card"><div>Số bảng nguồn</div><h2>{cs.get('total_tables', 0)} bảng</h2></div>
    <div class="card"><div>Tổng dòng sạch</div><h2>{cs.get('total_rows_clean', 0)} dòng</h2></div>
    <div class="card"><div>Độ đầy đủ dữ liệu</div><h2>{cs.get('completeness_pct', 100)}%</h2></div>
  </div>
  {f"<h2>🌳 {html_lib.escape(str(kpi_tree.get('title') or 'Cây KPI / MG'))}</h2><div class='kpis'>{kpi_branches_html}</div>" if kpi_branches_html else ""}
  {f"<h2>🏅 Phân hạng Ưu tiên &amp; Phân nhóm (ABC)</h2><table><thead><tr><th>#</th><th>Đối tượng</th><th>Phân hạng</th><th>Giá trị</th><th>Tỷ trọng</th><th>Nhóm</th></tr></thead><tbody>{priority_rows}</tbody></table>" if priority_rows else ""}
  <h2>📈 Thống kê chỉ số định lượng</h2>
  <table><thead><tr><th>Bảng</th><th>Chỉ tiêu</th><th>Số dòng</th><th>Tổng</th><th>Trung bình</th><th>Nhỏ nhất</th><th>Lớn nhất</th></tr></thead><tbody>{num_rows or '<tr><td colspan="7">Không có cột số định lượng.</td></tr>'}</tbody></table>
  <h2>📄 Báo cáo chi tiết</h2>
  <div class="report-box">{md_html}</div>
</div></body></html>"""

    ev = res.get("evaluation") or {}
    evals = ev.get("evaluations") or []
    selected = [x for x in evals if x.get("overall_status") == "SELECTED"]
    prop = res.get("proposal") or {}
    survey_plan = prop.get("survey_plan") or []
    md_html = _render_md_to_clean_html(prop.get("markdown_report") or "")
    run_id = html_lib.escape(str(res.get("run_id") or ""))
    status_txt = html_lib.escape(str(res.get("workflow_status") or ""))

    def badge_for(idx: int) -> str:
        if idx < len(selected):
            item = selected[idx]
            return (
                f"<div class='card top'>"
                f"<div class='tag'>{'🥇 ƯU TIÊN #1' if idx == 0 else '🥈 ƯU TIÊN #2'} · {item.get('total_weighted_score')}/10</div>"
                f"<h2>{html_lib.escape(str(item.get('location') or ''))}</h2>"
                f"<p>{html_lib.escape(str(item.get('exclusion_or_selection_reason') or ''))}</p>"
                f"</div>"
            )
        return f"<div class='card'><h3>Đang chờ # {idx + 1}</h3></div>"

    rows_html = "".join(
        f"<tr>"
        f"<td><strong>#{r.get('rank') or '-'} {html_lib.escape(str(r.get('location') or ''))}</strong></td>"
        f"<td>{r.get('total_weighted_score') if r.get('total_weighted_score') is not None else 'N/A'}</td>"
        f"<td>{html_lib.escape(str(r.get('overall_status') or ''))}</td>"
        f"<td>{html_lib.escape(str(r.get('exclusion_or_selection_reason') or ''))}</td>"
        f"</tr>"
        for r in evals
    )
    survey_html = "".join(
        f"<tr>"
        f"<td><strong>{html_lib.escape(str(s.get('location') or ''))}</strong><br><small>{html_lib.escape(str(s.get('priority_tag') or ''))}</small></td>"
        f"<td>{html_lib.escape(', '.join(s.get('target_customer_segments') or []))}</td>"
        f"<td>{html_lib.escape('; '.join(s.get('information_to_verify') or []))}</td>"
        f"<td>{html_lib.escape(str(s.get('go_no_go_criteria') or ''))}</td>"
        f"<td>{html_lib.escape(str(s.get('owner') or ''))}</td>"
        f"</tr>"
        for s in survey_plan
    )

    return f"""<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>Hà Thuỳ Dương · Data Analyst &amp; BI · Báo cáo &amp; Dashboard ({run_id})</title>
<link href="https://fonts.googleapis.com/css2?family=Be+Vietnam+Pro:wght@400;500;600;700;800&display=swap" rel="stylesheet" />
<style>
  body {{ font-family: "Be Vietnam Pro", -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif; margin: 0; padding: 32px; background: linear-gradient(135deg, #ffd6e7 0%, #ffe8ee 50%, #ffe2d1 100%); color: #3f2d38; line-height: 1.7; }}
  .wrap {{ max-width: 1020px; margin: 0 auto; background: rgba(255,255,255,0.85); backdrop-filter: blur(18px); border: 1.5px solid #fff; border-radius: 28px; padding: 30px; box-shadow: 0 24px 60px -16px rgba(236,72,153,.24); }}
  h1 {{ margin: 0 0 6px; color: #be185d; font-size: 22px; }}
  h2 {{ color: #9d174d; font-size: 16px; margin-top: 22px; padding: 6px 12px; border-left: 4px solid #ec4899; background: #fff1f6; border-radius: 0 12px 12px 0; }}
  .meta {{ font-size: 12.5px; color: #7c4d63; margin-bottom: 20px; }}
  .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 16px; margin-bottom: 24px; }}
  .card {{ background: rgba(255,255,255,0.9); border: 1.5px solid #fbcfe8; border-radius: 20px; padding: 18px; box-shadow: 0 12px 26px -12px rgba(236,72,153,.22); }}
  .card.top {{ background: linear-gradient(135deg, #fff5f9, #fff7ed); }}
  .tag {{ display: inline-block; padding: 4px 10px; border-radius: 999px; background: #fce7f3; color: #be185d; font-weight: 800; font-size: 11px; margin-bottom: 8px; }}
  table {{ width: 100%; border-collapse: collapse; margin: 12px 0 24px; background: rgba(255,255,255,0.92); border-radius: 16px; overflow: hidden; font-size: 12.5px; }}
  th, td {{ padding: 10px 12px; border-bottom: 1px solid #fce7f3; text-align: left; vertical-align: top; }}
  th {{ background: linear-gradient(90deg, #fce7f3, #ffedd5); color: #9d174d; font-weight: 800; }}
  code {{ font-family: inherit; font-weight: 700; padding: 2px 7px; border-radius: 999px; background: #fdf2f8; color: #be185d; border: 1px solid #fbcfe8; }}
  .report-box {{ background: rgba(255,255,255,0.92); padding: 20px 24px; border-radius: 20px; border: 1.5px solid #fbcfe8; font-size: 13.5px; }}
</style>
</head>
<body>
  <div class="wrap">
    <h1>🌸 Hà Thuỳ Dương · Báo Cáo &amp; Dashboard Phân Tích Dữ Liệu</h1>
    <div class="meta">Phiên chạy: <strong>{run_id}</strong> · Trạng thái: <strong>{status_txt}</strong></div>
    <div class="grid">{badge_for(0)}{badge_for(1)}</div>
    <h2>📊 Bảng So Sánh Địa Bàn</h2>
    <table><thead><tr><th>Địa bàn</th><th>Tổng điểm</th><th>Kết luận</th><th>Lý do</th></tr></thead><tbody>{rows_html or '<tr><td colspan="4">Chưa có đánh giá.</td></tr>'}</tbody></table>
    <h2>📋 Kế Hoạch Khảo Sát (Go / No-Go)</h2>
    <table><thead><tr><th>Địa bàn</th><th>Nhóm khách hàng</th><th>Cần xác minh</th><th>Tiêu chí Go / No-Go</th><th>Phụ trách</th></tr></thead><tbody>{survey_html or '<tr><td colspan="5">Chưa có kế hoạch.</td></tr>'}</tbody></table>
    <h2>📄 Báo Cáo Chi Tiết (BC)</h2>
    <div class="report-box">{md_html}</div>
  </div>
</body>
</html>"""


class AgentHTTPHandler(BaseHTTPRequestHandler):
    """HTTP Request Handler for Hung Phat AI Agent Web App."""

    server_version = "HungPhatAIAgent/1.0"

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        # Keep terminal logs crisp and readable
        print(f"[HTTP] {self.address_string()} - {format % args}")

    def _current_user(self) -> Optional[Dict[str, Any]]:
        tok = parse_cookie_header(self.headers.get("Cookie") or "", SESSION_COOKIE_NAME)
        return verify_session_token(tok)

    def _send_json(self, payload: Any, status: int = HTTPStatus.OK, extra_headers: Optional[List[Tuple[str, str]]] = None) -> None:
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        for hk, hv in (extra_headers or []):
            self.send_header(hk, hv)
        self.end_headers()
        self.wfile.write(raw)

    def _send_bytes(
        self,
        data: bytes,
        content_type: str,
        status: int = HTTPStatus.OK,
        download_name: Optional[str] = None,
        cache: str = "no-cache",
    ) -> None:
        compressible = (
            not download_name
            and len(data) > 1024
            and any(t in content_type for t in ("text/", "javascript", "json", "xml", "svg"))
            and "gzip" in (self.headers.get("Accept-Encoding") or "")
        )
        if compressible:
            data = gzip.compress(data, compresslevel=6)
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        if compressible:
            self.send_header("Content-Encoding", "gzip")
            self.send_header("Vary", "Accept-Encoding")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
        self.send_header("X-Frame-Options", "SAMEORIGIN")
        if not download_name:
            self.send_header("Cache-Control", cache)
        if download_name:
            self.send_header("Content-Disposition", f'attachment; filename="{download_name}"')
        self.end_headers()
        self.wfile.write(data)

    def _read_body(self) -> bytes:
        length = int(self.headers.get("Content-Length") or 0)
        if length > 50 * 1024 * 1024:
            raise ValueError("Kích thước dữ liệu tải lên vượt quá 50MB.")
        return self.rfile.read(length) if length > 0 else b""

    def _extract_request_payload(self) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
        ctype = self.headers.get("Content-Type") or ""
        body = self._read_body()
        if "multipart/form-data" in ctype:
            fields, files = parse_multipart_form(ctype, body)
            parsed_json: Dict[str, Any] = {}
            if "payload" in fields and fields["payload"]:
                parsed_json = json.loads(fields["payload"][0])
            else:
                for k, vals in fields.items():
                    parsed_json[k] = vals[0] if len(vals) == 1 else vals
            return parsed_json, files
        if body:
            return json.loads(body.decode("utf-8")), []
        return {}, []

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = unquote(parsed.path)

        try:
            if path == "/api/health":
                gem_key = os.environ.get("GEMINI_API_KEY", "").strip()
                oai_key = os.environ.get("OPENAI_API_KEY", "").strip()
                self._send_json(
                    {
                        "status": "ok",
                        "has_gemini_key": bool(gem_key),
                        "has_openai_key": bool(oai_key),
                        "gemini_key_mode": "vertex_express" if gem_key.startswith("AQ.") else ("ai_studio" if gem_key else ""),
                        "default_agent_mode": os.environ.get("DEFAULT_AGENT_MODE", "gemini" if gem_key else "local"),
                        "default_gemini_model": os.environ.get("DEFAULT_GEMINI_MODEL", "gemini-2.5-flash"),
                        "samples": SAMPLE_CATALOG,
                        "default_criteria": DEFAULT_CRITERIA,
                        "canonical_tables": [
                            {"key": k, "label": TABLE_LABELS_VI[k], "fields": list(COLUMN_ALIASES[k].keys())}
                            for k in CANONICAL_TABLES
                        ],
                    }
                )
                return

            if path == "/api/samples":
                self._send_json({"samples": SAMPLE_CATALOG})
                return

            if path.startswith("/api/samples/") and path.endswith("/download"):
                parts = path.strip("/").split("/")
                if len(parts) == 4:
                    sample_id = parts[2]
                    fpath = SAMPLES_DIR / f"{sample_id}.xlsx"
                    if fpath.exists():
                        self._send_bytes(
                            fpath.read_bytes(),
                            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            download_name=fpath.name,
                        )
                        return
                self._send_json({"error": "Không tìm thấy file mẫu."}, status=HTTPStatus.NOT_FOUND)
                return

            if path.startswith("/api/runs/") and path.endswith("/audit"):
                run_id = path.strip("/").split("/")[2]
                audit_path = AUDIT_DIR / f"{run_id}.json"
                if audit_path.exists():
                    self._send_bytes(
                        audit_path.read_bytes(),
                        "application/json; charset=utf-8",
                        download_name=f"{run_id}_audit.json",
                    )
                    return
                sess = _get_run_session(run_id)
                if sess:
                    audit_data = (sess.get("last_response") or {}).get("audit") or {}
                    self._send_bytes(
                        json.dumps(audit_data, ensure_ascii=False, indent=2).encode("utf-8"),
                        "application/json; charset=utf-8",
                        download_name=f"{run_id}_audit.json",
                    )
                    return
                self._send_json({"error": f"Không tìm thấy Audit Log cho phiên '{run_id}'."}, status=HTTPStatus.NOT_FOUND)
                return

            if path.startswith("/api/runs/") and path.endswith("/report.md"):
                run_id = path.strip("/").split("/")[2]
                sess = _get_run_session(run_id)
                if sess:
                    proposal = (sess.get("last_response") or {}).get("proposal") or {}
                    md = proposal.get("markdown_report") or "# Chưa có báo cáo hoàn chỉnh (Phiên đang chờ HITL)."
                    self._send_bytes(
                        md.encode("utf-8"),
                        "text/markdown; charset=utf-8",
                        download_name=f"{run_id}_BaoCao_DeXuat.md",
                    )
                    return
                self._send_json({"error": f"Không tìm thấy phiên '{run_id}'."}, status=HTTPStatus.NOT_FOUND)
                return

            if path.startswith("/api/runs/") and path.endswith("/report.html"):
                run_id = path.strip("/").split("/")[2]
                sess = _get_run_session(run_id)
                if sess:
                    html_out = render_standalone_html_report(sess["last_response"])
                    self._send_bytes(
                        html_out.encode("utf-8"),
                        "text/html; charset=utf-8",
                        download_name=f"HaThuyDuong_{run_id}_Dashboard.html",
                    )
                    return
                self._send_json({"error": f"Không tìm thấy phiên '{run_id}'."}, status=HTTPStatus.NOT_FOUND)
                return

            if path.startswith("/api/runs/") and path.endswith("/cleaned.xlsx"):
                run_id = path.strip("/").split("/")[2]
                sess = _get_run_session(run_id)
                if sess:
                    xlsx_bytes = export_cleaned_excel_bytes(
                        sess["last_response"],
                        sess.get("cleaned_sheets") or sess.get("raw_sheets") or {},
                    )
                    self._send_bytes(
                        xlsx_bytes,
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        download_name=f"HaThuyDuong_{run_id}_DuLieu_DaLamSach.xlsx",
                    )
                    return
                self._send_json({"error": f"Không tìm thấy phiên '{run_id}'."}, status=HTTPStatus.NOT_FOUND)
                return

            if path.startswith("/api/runs/") and path.endswith("/analysis.xlsx"):
                run_id = path.strip("/").split("/")[2]
                sess = _get_run_session(run_id)
                if sess:
                    xlsx_bytes = export_analysis_excel_bytes(sess["last_response"])
                    self._send_bytes(
                        xlsx_bytes,
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        download_name=f"HaThuyDuong_{run_id}_TongHop_BieuDo_PhanTich.xlsx",
                    )
                    return
                self._send_json({"error": f"Không tìm thấy phiên '{run_id}'."}, status=HTTPStatus.NOT_FOUND)
                return

            if path.startswith("/api/runs/") and path.endswith("/report.docx"):
                run_id = path.strip("/").split("/")[2]
                sess = _get_run_session(run_id)
                if sess:
                    docx_bytes = export_report_docx_bytes(sess["last_response"])
                    self._send_bytes(
                        docx_bytes,
                        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        download_name=f"HaThuyDuong_{run_id}_BaoCao_PhanTich_BI.docx",
                    )
                    return
                self._send_json({"error": f"Không tìm thấy phiên '{run_id}'."}, status=HTTPStatus.NOT_FOUND)
                return

            if path == "/favicon.ico":
                self.send_response(HTTPStatus.NO_CONTENT)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return

            if path == "/sitemap.xml":
                host = self.headers.get("Host") or "localhost:8000"
                proto = "https" if (self.headers.get("X-Forwarded-Proto") == "https") else "http"
                self._send_bytes(build_sitemap_xml(f"{proto}://{host}").encode("utf-8"), "application/xml; charset=utf-8", cache="public, max-age=3600")
                return

            if path == "/robots.txt":
                host = self.headers.get("Host") or "localhost:8000"
                proto = "https" if (self.headers.get("X-Forwarded-Proto") == "https") else "http"
                self._send_bytes(build_robots_txt(f"{proto}://{host}").encode("utf-8"), "text/plain; charset=utf-8", cache="public, max-age=3600")
                return

            if path == "/api/auth/me":
                self._send_json({"user": self._current_user()})
                return

            if path == "/api/user/my-stats":
                user = self._current_user()
                if not user:
                    self._send_json({"error": "Vui lòng đăng nhập để xem thống kê cá nhân."}, status=HTTPStatus.UNAUTHORIZED)
                    return
                self._send_json(get_user_personal_stats(user["username"]))
                return

            if path == "/api/site-settings":
                self._send_json(get_site_settings())
                return

            if path in ("/admin", "/admin/"):
                user = self._current_user()
                if user and user.get("role") != "admin":
                    denied_html = (
                        "<!DOCTYPE html><html lang='vi'><head><meta charset='UTF-8'>"
                        "<title>403 · Không có quyền truy cập</title></head>"
                        "<body style='font-family:sans-serif;background:#ffeef5;display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0;'>"
                        "<div style='background:#fff;padding:32px;border-radius:24px;max-width:440px;text-align:center;box-shadow:0 20px 50px rgba(236,72,153,.18);'>"
                        "<h1 style='color:#be185d;margin:0 0 10px;'>🔒 403 · Truy cập bị từ chối</h1>"
                        "<p style='color:#475569;font-size:14px;'>Khu vực <strong>/admin</strong> chỉ dành riêng cho Quản trị viên chủ sở hữu (<strong>Hà Thuỳ Dương</strong>).</p>"
                        "<a href='/' style='display:inline-block;margin-top:14px;padding:10px 20px;border-radius:14px;background:#ec4899;color:#fff;text-decoration:none;font-weight:700;'>← Quay về trang chủ</a>"
                        "</div></body></html>"
                    )
                    self._send_bytes(denied_html.encode("utf-8"), "text/html; charset=utf-8", status=HTTPStatus.FORBIDDEN)
                    return
                admin_file = (WEB_DIR / "admin.html").resolve()
                if admin_file.is_file():
                    self._send_bytes(admin_file.read_bytes(), "text/html; charset=utf-8")
                    return

            if path == "/api/admin/stats":
                user = self._current_user()
                if not user or user.get("role") != "admin":
                    self._send_json({"error": "Chỉ tài khoản Quản trị (Hà Thuỳ Dương) mới có quyền xem thống kê tất cả người dùng."}, status=HTTPStatus.FORBIDDEN)
                    return
                self._send_json(get_admin_dashboard_stats(CONTACT_FILE, AUDIT_DIR))
                return

            # Static files or clean SPA routes
            clean_path = path.rstrip("/") or "/"
            if clean_path in SPA_ROUTES:
                rel_path = "index.html"
            else:
                rel_path = "index.html" if path in ("/", "") else path.lstrip("/")
            if rel_path == "index.html":
                u = self._current_user()
                log_analytics_event(
                    "page_view",
                    path=clean_path,
                    user_agent=self.headers.get("User-Agent") or "",
                    ip=self.client_address[0] if self.client_address else "",
                    username=u["username"] if u else "guest",
                )
            target = (WEB_DIR / rel_path).resolve()
            if not str(target).startswith(str(WEB_DIR.resolve())) or not target.is_file():
                self._send_json({"error": "Not found"}, status=HTTPStatus.NOT_FOUND)
                return
            mime, _ = mimetypes.guess_type(str(target))
            ctype = mime or "application/octet-stream"
            if ctype.startswith("text/") or ctype in ("application/javascript", "application/json", "application/xml"):
                ctype = f"{ctype}; charset=utf-8"
            self._send_bytes(target.read_bytes(), ctype)
        except Exception as exc:
            self._send_json({"error": str(exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = unquote(parsed.path)

        try:
            payload, files = self._extract_request_payload()

            if path == "/api/auth/register":
                user = register_user(
                    display_name=str(payload.get("display_name") or ""),
                    username=str(payload.get("username") or ""),
                    phone=str(payload.get("phone") or ""),
                    password=str(payload.get("password") or ""),
                )
                tok = create_session_token(user["username"], user["display_name"], user["role"], user.get("phone", ""))
                sec_flag = "; Secure" if (self.headers.get("X-Forwarded-Proto") == "https" or os.environ.get("VERCEL")) else ""
                cookie = f"{SESSION_COOKIE_NAME}={tok}; HttpOnly; Path=/; SameSite=Lax; Max-Age={SESSION_TTL_SEC}{sec_flag}"
                log_analytics_event("register", path="/api/auth/register", user_agent=self.headers.get("User-Agent") or "", ip=self.client_address[0] if self.client_address else "", username=user["username"])
                self._send_json({"user": user}, extra_headers=[("Set-Cookie", cookie)])
                return

            if path == "/api/auth/login":
                user = authenticate_user(
                    identifier=str(payload.get("username") or ""),
                    password=str(payload.get("password") or ""),
                )
                tok = create_session_token(user["username"], user["display_name"], user["role"], user.get("phone", ""))
                sec_flag = "; Secure" if (self.headers.get("X-Forwarded-Proto") == "https" or os.environ.get("VERCEL")) else ""
                cookie = f"{SESSION_COOKIE_NAME}={tok}; HttpOnly; Path=/; SameSite=Lax; Max-Age={SESSION_TTL_SEC}{sec_flag}"
                log_analytics_event("login", path="/api/auth/login", user_agent=self.headers.get("User-Agent") or "", ip=self.client_address[0] if self.client_address else "", username=user["username"])
                self._send_json({"user": user}, extra_headers=[("Set-Cookie", cookie)])
                return

            if path == "/api/auth/forgot-password":
                res = request_password_reset_otp(phone=str(payload.get("phone") or ""))
                self._send_json(res)
                return

            if path == "/api/auth/reset-password":
                res = reset_password_with_otp(
                    phone=str(payload.get("phone") or ""),
                    otp_code=str(payload.get("otp_code") or ""),
                    new_password=str(payload.get("new_password") or ""),
                )
                self._send_json(res)
                return

            if path == "/api/auth/logout":
                cookie = f"{SESSION_COOKIE_NAME}=; HttpOnly; Path=/; SameSite=Lax; Max-Age=0"
                self._send_json({"ok": True}, extra_headers=[("Set-Cookie", cookie)])
                return

            if path == "/api/admin/users/lock":
                user = self._current_user()
                if not user or user.get("role") != "admin":
                    self._send_json({"error": "Chỉ Quản trị viên mới có quyền khóa/mở khóa tài khoản."}, status=HTTPStatus.FORBIDDEN)
                    return
                res = toggle_user_lock(
                    username=str(payload.get("username") or ""),
                    locked=bool(payload.get("locked")),
                )
                self._send_json(res)
                return

            if path == "/api/admin/settings":
                user = self._current_user()
                if not user or user.get("role") != "admin":
                    self._send_json({"error": "Chỉ Quản trị viên mới có quyền thay đổi cài đặt hệ thống."}, status=HTTPStatus.FORBIDDEN)
                    return
                saved = update_site_settings(payload if isinstance(payload, dict) else {})
                self._send_json({"ok": True, "settings": saved})
                return

            if path == "/api/contact":
                save_contact_request(payload)
                self._send_json({"ok": True, "message": "Đã nhận yêu cầu tư vấn."})
                return

            if path == "/api/chat":
                msg = str(payload.get("message") or "").strip()
                if not msg:
                    self._send_json({"reply": "Bạn hãy nhập câu hỏi nhé!"})
                    return
                gem_key = os.environ.get("GEMINI_API_KEY", "").strip()
                gem_model = os.environ.get("DEFAULT_GEMINI_MODEL", "gemini-2.5-flash").strip()
                reply = ""
                if gem_key:
                    try:
                        reply = chat_with_assistant(
                            message=msg,
                            history=payload.get("history") or [],
                            api_key=gem_key,
                            model=gem_model,
                            lang=str(payload.get("lang") or "vi"),
                        )
                    except Exception:
                        reply = ""
                u = self._current_user()
                log_analytics_event("chat_message", path="/api/chat", user_agent=self.headers.get("User-Agent") or "", ip=self.client_address[0] if self.client_address else "", username=u["username"] if u else "guest")
                self._send_json({"reply": reply, "used_ai": bool(reply)})
                return

            if path == "/api/inspect-inputs":
                urls = payload.get("google_sheet_urls") or []
                if isinstance(urls, str):
                    urls = [u.strip() for u in urls.splitlines() if u.strip()]
                lark_urls = payload.get("lark_base_urls") or []
                if isinstance(lark_urls, str):
                    lark_urls = [u.strip() for u in lark_urls.splitlines() if u.strip()]
                sample_id = str(payload.get("sample_id") or "").strip()
                fetch_all_tabs = bool(payload.get("fetch_all_tabs", True))
                doc_texts: Dict[str, List[str]] = {}

                cfg_inspect = payload.get("config") or {}
                raw_sheets, source_meta = load_inputs_from_sources(
                    uploaded_files=files,
                    google_sheet_urls=urls,
                    sample_id=sample_id,
                    fetch_all_tabs=fetch_all_tabs,
                    lark_base_urls=lark_urls,
                    lark_app_id=str(payload.get("lark_app_id") or ""),
                    lark_app_secret=str(payload.get("lark_app_secret") or ""),
                    lark_token=str(payload.get("lark_token") or ""),
                    document_texts_out=doc_texts,
                    gemini_key=str(cfg_inspect.get("api_key") or ""),
                    gemini_model=str(cfg_inspect.get("model") or "gemini-2.5-flash"),
                )
                staged_id = f"STG-{uuid.uuid4().hex[:8].upper()}"
                STAGED_INPUTS[staged_id] = {
                    "raw_sheets": raw_sheets,
                    "source_meta": source_meta,
                    "document_texts": doc_texts,
                }
                schema_info = classify_sheets_to_canonical(raw_sheets)
                previews = {
                    s_name: [
                        {k: v for k, v in r.items() if not str(k).startswith("_")}
                        for r in rows[:3]
                    ]
                    for s_name, rows in raw_sheets.items()
                }
                self._send_json(
                    {
                        "staged_id": staged_id,
                        "source_metadata": source_meta,
                        "sheet_assignments": schema_info["sheet_assignments"],
                        "column_maps": schema_info["column_maps"],
                        "previews": previews,
                        "document_texts": {k: len(v) for k, v in doc_texts.items()},
                    }
                )
                return

            if path == "/api/run":
                staged_id = str(payload.get("staged_id") or "").strip()
                doc_texts: Dict[str, List[str]] = {}
                if staged_id and staged_id in STAGED_INPUTS and not files and not payload.get("google_sheet_urls") and not payload.get("lark_base_urls") and not payload.get("sample_id"):
                    raw_sheets = STAGED_INPUTS[staged_id]["raw_sheets"]
                    source_meta = STAGED_INPUTS[staged_id]["source_meta"]
                    doc_texts = STAGED_INPUTS[staged_id].get("document_texts") or {}
                else:
                    urls = payload.get("google_sheet_urls") or []
                    if isinstance(urls, str):
                        urls = [u.strip() for u in urls.splitlines() if u.strip()]
                    lark_urls = payload.get("lark_base_urls") or []
                    if isinstance(lark_urls, str):
                        lark_urls = [u.strip() for u in lark_urls.splitlines() if u.strip()]
                    sample_id = str(payload.get("sample_id") or "").strip()
                    fetch_all_tabs = bool(payload.get("fetch_all_tabs", True))
                    cfg = payload.get("config") or {}
                    raw_sheets, source_meta = load_inputs_from_sources(
                        uploaded_files=files,
                        google_sheet_urls=urls,
                        sample_id=sample_id,
                        fetch_all_tabs=fetch_all_tabs,
                        lark_base_urls=lark_urls,
                        lark_app_id=str(payload.get("lark_app_id") or ""),
                        lark_app_secret=str(payload.get("lark_app_secret") or ""),
                        lark_token=str(payload.get("lark_token") or ""),
                        document_texts_out=doc_texts,
                        gemini_key=str(cfg.get("api_key") or ""),
                        gemini_model=str(cfg.get("model") or "gemini-2.5-flash"),
                    )

                result = ORCHESTRATOR.start_run(
                    raw_sheets=raw_sheets,
                    source_metadata=source_meta,
                    config=payload.get("config") or {},
                    table_overrides=payload.get("table_overrides") or {},
                    column_overrides=payload.get("column_overrides") or {},
                    human_resolutions=payload.get("human_resolutions") or {},
                    document_texts=doc_texts,
                )
                _save_run_session(str(result.get("run_id") or ""))
                u = self._current_user()
                log_analytics_event("analysis_run", path="/api/run", user_agent=self.headers.get("User-Agent") or "", ip=self.client_address[0] if self.client_address else "", username=u["username"] if u else "guest", extra={"run_id": result.get("run_id")})
                self._send_json(result)
                return

            if path == "/api/hitl/resolve":
                run_id = str(payload.get("run_id") or "").strip()
                if not run_id:
                    raise ValueError("Thiếu run_id để xử lý HITL.")
                extra_sheets: Dict[str, List[Dict[str, Any]]] = {}
                urls = payload.get("google_sheet_urls") or []
                if isinstance(urls, str):
                    urls = [u.strip() for u in urls.splitlines() if u.strip()]
                if files or urls:
                    extra_sheets, _ = load_inputs_from_sources(
                        uploaded_files=files,
                        google_sheet_urls=urls,
                        fetch_all_tabs=bool(payload.get("fetch_all_tabs", True)),
                    )

                result = ORCHESTRATOR.resume_with_human_input(
                    run_id=run_id,
                    human_resolutions=payload.get("human_resolutions") or {},
                    extra_sheets=extra_sheets,
                )
                _save_run_session(str(result.get("run_id") or ""))
                u = self._current_user()
                log_analytics_event("analysis_run", path="/api/run", user_agent=self.headers.get("User-Agent") or "", ip=self.client_address[0] if self.client_address else "", username=u["username"] if u else "guest", extra={"run_id": result.get("run_id")})
                self._send_json(result)
                return

            if path == "/api/hitl/boundary-signoff":
                run_id = str(payload.get("run_id") or "").strip()
                decision = str(payload.get("decision") or "APPROVED_TOP_2").strip()
                chosen = payload.get("chosen_locations")
                note = str(payload.get("note") or "").strip()
                result = ORCHESTRATOR.record_boundary_decision(
                    run_id=run_id,
                    decision=decision,
                    chosen_locations=chosen,
                    note=note,
                )
                _save_run_session(str(result.get("run_id") or ""))
                u = self._current_user()
                log_analytics_event("analysis_run", path="/api/run", user_agent=self.headers.get("User-Agent") or "", ip=self.client_address[0] if self.client_address else "", username=u["username"] if u else "guest", extra={"run_id": result.get("run_id")})
                self._send_json(result)
                return

            self._send_json({"error": f"Endpoint không tồn tại: {path}"}, status=HTTPStatus.NOT_FOUND)

        except ValueError as exc:
            self._send_json(
                {
                    "error": str(exc),
                    "gate_failed": "RECEIVE_DATA",
                    "requires_resubmit": True,
                },
                status=HTTPStatus.BAD_REQUEST,
            )
        except KeyError as exc:
            self._send_json({"error": str(exc)}, status=HTTPStatus.NOT_FOUND)
        except Exception as exc:
            traceback.print_exc()
            self._send_json({"error": f"Lỗi xử lý hệ thống: {exc}"}, status=HTTPStatus.INTERNAL_SERVER_ERROR)


# Vercel Python serverless entrypoints (supports both BaseHTTPRequestHandler `handler` and WSGI `app`)
handler = AgentHTTPHandler


def app(environ: Dict[str, Any], start_response: Any) -> List[bytes]:
    """Zero-dependency WSGI adapter around AgentHTTPHandler for Vercel Python framework."""
    import http.client
    import io

    try:
        class _WSGIHandler(AgentHTTPHandler):
            def __init__(self) -> None:
                self.command = str(environ.get("REQUEST_METHOD", "GET")).upper()
                qs = str(environ.get("QUERY_STRING", "") or "")
                path_info = str(environ.get("PATH_INFO", "/") or "/")
                self.path = f"{path_info}?{qs}" if qs else path_info
                self.request_version = str(environ.get("SERVER_PROTOCOL", "HTTP/1.1"))
                self.client_address = (str(environ.get("REMOTE_ADDR", "127.0.0.1")), 0)

                hdrs = http.client.HTTPMessage()
                if environ.get("CONTENT_TYPE"):
                    hdrs["Content-Type"] = str(environ["CONTENT_TYPE"])
                if environ.get("CONTENT_LENGTH"):
                    hdrs["Content-Length"] = str(environ["CONTENT_LENGTH"])
                for k, v in environ.items():
                    if k.startswith("HTTP_") and v is not None:
                        name = k[5:].replace("_", "-").title()
                        hdrs[name] = str(v)
                self.headers = hdrs

                try:
                    clen = int(environ.get("CONTENT_LENGTH") or 0)
                except (TypeError, ValueError):
                    clen = 0
                stream = environ.get("wsgi.input")
                if stream is not None and clen > 0:
                    raw_in = stream.read(clen)
                elif stream is not None and self.command == "POST":
                    raw_in = stream.read()
                else:
                    raw_in = b""
                if isinstance(raw_in, str):
                    raw_in = raw_in.encode("utf-8")
                self.rfile = io.BytesIO(raw_in or b"")
                self.wfile = io.BytesIO()
                self._wsgi_status = 200
                self._wsgi_headers: List[Tuple[str, str]] = []

            def send_response(self, code: int, message: Optional[str] = None) -> None:
                self._wsgi_status = int(code)

            def send_header(self, keyword: str, value: str) -> None:
                self._wsgi_headers.append((str(keyword), str(value)))

            def end_headers(self) -> None:
                return None

        h = _WSGIHandler()
        if h.command == "POST":
            h.do_POST()
        else:
            h.do_GET()

        try:
            phrase = HTTPStatus(h._wsgi_status).phrase
        except ValueError:
            phrase = "OK"
        start_response(f"{h._wsgi_status} {phrase}", h._wsgi_headers)
        return [h.wfile.getvalue()]
    except Exception as exc:
        err_bytes = json.dumps({"error": f"Server error: {exc}"}, ensure_ascii=False).encode("utf-8")
        start_response("500 Internal Server Error", [("Content-Type", "application/json; charset=utf-8"), ("Content-Length", str(len(err_bytes)))])
        return [err_bytes]


def create_server(host: str = "127.0.0.1", port: int = 8000) -> ThreadingHTTPServer:
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    return ThreadingHTTPServer((host, port), AgentHTTPHandler)


def main() -> None:
    import threading
    import webbrowser

    env_port = os.environ.get("PORT", "").strip()
    default_port = int(env_port) if env_port.isdigit() else 8000
    default_host = "0.0.0.0" if env_port else "127.0.0.1"

    parser = argparse.ArgumentParser(description="Ha Thuy Duong - Data Analyst & BI Server")
    parser.add_argument("--host", default=default_host)
    parser.add_argument("--port", type=int, default=default_port)
    parser.add_argument("--open", action="store_true", help="Tự động mở trình duyệt mặc định")
    args = parser.parse_args()

    server = create_server(host=args.host, port=args.port)
    url_localhost = f"http://localhost:{args.port}"
    url_ip = f"http://{args.host}:{args.port}"
    print(f"Hung Phat AI Agent Web App đang chạy tại: {url_localhost} ({url_ip})", flush=True)
    if args.open:
        threading.Timer(0.6, lambda: webbrowser.open(url_localhost)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nĐang dừng server...")
        server.shutdown()


if __name__ == "__main__":
    main()


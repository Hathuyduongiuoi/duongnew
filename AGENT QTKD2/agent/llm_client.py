"""Zero-dependency Gemini & OpenAI REST clients supporting native Function/Tool Calling."""

from __future__ import annotations

import base64
import json
import re
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

from .netutil import secure_urlopen

class LLMClientError(RuntimeError):
    """Raised when an external LLM API request fails."""


def build_gemini_endpoint_url(api_key: str, model: str) -> str:
    """Route AQ.* keys to Vertex AI Express Mode and AIza* keys to AI Studio Gemini API."""
    clean_model = (model or "gemini-2.5-flash").strip()
    clean_key = (api_key or "").strip()
    if clean_key.startswith("AQ."):
        return (
            f"https://aiplatform.googleapis.com/v1/publishers/google/models/"
            f"{clean_model}:generateContent?key={clean_key}"
        )
    return f"https://generativelanguage.googleapis.com/v1beta/models/{clean_model}:generateContent?key={clean_key}"


def call_gemini_with_tools(
    api_key: str,
    model: str,
    system_prompt: str,
    contents: List[Dict[str, Any]],
    function_declarations: List[Dict[str, Any]],
    timeout_sec: int = 45,
) -> Dict[str, Any]:
    """Call Gemini (AI Studio or Vertex AI Express Mode) generateContent REST API with tool declarations."""
    if not api_key:
        raise LLMClientError("Thiếu Gemini API Key.")
    url = build_gemini_endpoint_url(api_key, model)

    payload = {
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "contents": contents,
        "tools": [{"functionDeclarations": function_declarations}],
        "toolConfig": {"functionCallingConfig": {"mode": "AUTO"}},
        "generationConfig": {"temperature": 0.1},
    }

    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with secure_urlopen(req, timeout=timeout_sec) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        if exc.code == 403 and "aiplatform.googleapis.com" in body and "disabled" in body.lower():
            raise LLMClientError(
                f"Gemini/Vertex AI HTTP 403: Project của API Key chưa bật Vertex AI API (aiplatform.googleapis.com). "
                f"Hãy vào Google Cloud Console bật API này hoặc dùng Gemini AI Studio Key (AIza...). Chi tiết: {body[:260]}"
            ) from exc
        raise LLMClientError(f"Gemini API HTTP {exc.code}: {body[:400]}") from exc
    except urllib.error.URLError as exc:
        raise LLMClientError(f"Không thể kết nối Gemini API: {exc.reason}") from exc


def extract_gemini_parts(resp_json: Dict[str, Any]) -> Tuple[List[str], List[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """Extract text parts, function calls, and raw model content from Gemini response."""
    candidates = resp_json.get("candidates") or []
    if not candidates:
        raise LLMClientError(f"Gemini không trả về candidate hợp lệ: {json.dumps(resp_json)[:300]}")
    content = candidates[0].get("content") or {}
    parts = content.get("parts") or []
    texts: List[str] = []
    calls: List[Dict[str, Any]] = []
    for p in parts:
        if "text" in p and p["text"]:
            texts.append(p["text"])
        if "functionCall" in p:
            calls.append(p["functionCall"])
    return texts, calls, content


def call_openai_with_tools(
    api_key: str,
    model: str,
    messages: List[Dict[str, Any]],
    tools: List[Dict[str, Any]],
    base_url: str = "https://api.openai.com/v1",
    timeout_sec: int = 45,
) -> Dict[str, Any]:
    """Call OpenAI-compatible chat/completions REST API with tool calling."""
    if not api_key:
        raise LLMClientError("Thiếu OpenAI API Key.")
    clean_base = (base_url or "https://api.openai.com/v1").rstrip("/")
    url = f"{clean_base}/chat/completions"
    payload = {
        "model": (model or "gpt-4o-mini").strip(),
        "messages": messages,
        "tools": tools,
        "tool_choice": "auto",
        "temperature": 0.1,
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    try:
        with secure_urlopen(req, timeout=timeout_sec) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise LLMClientError(f"OpenAI API HTTP {exc.code}: {body[:400]}") from exc
    except urllib.error.URLError as exc:
        raise LLMClientError(f"Không thể kết nối OpenAI API: {exc.reason}") from exc


def extract_table_and_text_with_gemini_vision(
    api_key: str,
    model: str,
    raw_bytes: bytes,
    mime_type: str,
    filename: str,
    timeout_sec: int = 45,
) -> Tuple[Dict[str, List[Dict[str, Any]]], List[str]]:
    """Use Gemini Vision / PDF multimodal API to extract structured tables & text lines from images or scanned PDFs."""
    if not api_key:
        raise LLMClientError("Cần Gemini API Key để đọc trực tiếp ảnh hoặc PDF scan.")

    url = build_gemini_endpoint_url(api_key, model or "gemini-2.5-flash")
    b64_data = base64.b64encode(raw_bytes).decode("ascii")
    prompt = (
        f"Trích xuất toàn bộ bảng biểu và nội dung số liệu từ file '{filename}'. "
        "Trả về DUY NHẤT JSON hợp lệ theo schema sau (không kèm giải thích): "
        '{"tables": [{"name": "Ten_Bang", "rows": [{"Cot1": "...", "Cot2": "..."}]}], "paragraphs": ["dòng văn bản 1", "..."]}'
    )
    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {"text": prompt},
                    {"inlineData": {"mimeType": mime_type, "data": b64_data}},
                ],
            }
        ],
        "generationConfig": {"temperature": 0.0, "responseMimeType": "application/json"},
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with secure_urlopen(req, timeout=timeout_sec) as resp:
            resp_json = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.HTTPError, urllib.error.URLError) as exc:
        raise LLMClientError(f"Lỗi trích xuất multimodal từ '{filename}': {exc}") from exc

    texts, _, _ = extract_gemini_parts(resp_json)
    raw_txt = "\n".join(texts).strip()
    m = re.search(r"\{.*\}", raw_txt, flags=re.DOTALL)
    parsed_obj = json.loads(m.group(0) if m else raw_txt)

    sheets: Dict[str, List[Dict[str, Any]]] = {}
    for idx, tbl in enumerate(parsed_obj.get("tables") or [], start=1):
        t_name = str(tbl.get("name") or f"{filename}_Bang_{idx}")
        rows = tbl.get("rows") or []
        clean_rows: List[Dict[str, Any]] = []
        for r_i, row in enumerate(rows, start=1):
            if isinstance(row, dict) and row:
                rec = {"_row_number": r_i, "_source_file": filename, "_sheet_name": t_name}
                for k, v in row.items():
                    rec[str(k)] = "" if v is None else str(v)
                clean_rows.append(rec)
        if clean_rows:
            sheets[t_name] = clean_rows

    paras = [str(p).strip() for p in (parsed_obj.get("paragraphs") or []) if str(p).strip()]
    return sheets, paras


_LANG_NAMES = {
    "vi": "Tiếng Việt",
    "en": "English",
    "zh": "中文 (Simplified Chinese)",
    "ja": "日本語 (Japanese)",
    "ko": "한국어 (Korean)",
}


def generate_domain_narrative_with_llm(
    agent_mode: str,
    api_key: str,
    model: str,
    stats_snapshot: Dict[str, Any],
    user_prompt: str = "",
    base_url: str = "https://api.openai.com/v1",
    timeout_sec: int = 35,
    lang: str = "vi",
) -> str:
    """Generate a tailored executive synthesis aligned with customer prompt, time-series, and verified stats."""
    if not api_key or agent_mode == "local":
        return ""
    bi = stats_snapshot.get("bi_pipeline") or {}
    ts = (bi.get("stage3_analysis") or {}).get("time_analysis") or {}
    compact_ctx = {
        "domain_label": stats_snapshot.get("domain_label"),
        "business_context": stats_snapshot.get("business_context"),
        "financial_summary": stats_snapshot.get("financial_summary"),
        "project_summary": stats_snapshot.get("project_summary"),
        "time_analysis": {
            "available": ts.get("available"),
            "period_count": ts.get("period_count"),
            "overall_growth_pct": ts.get("overall_growth_pct"),
            "peak_period": ts.get("peak_period"),
            "low_period": ts.get("low_period"),
            "period_drivers": ts.get("period_drivers"),
        },
        "kpi_tree": stats_snapshot.get("kpi_tree"),
        "priority_entities": (stats_snapshot.get("priority_entities") or [])[:10],
        "classifiers": (stats_snapshot.get("classifiers") or [])[:4],
        "numeric_highlights": (stats_snapshot.get("numeric_highlights") or [])[:12],
        "prompt_matches": (stats_snapshot.get("prompt_matches") or [])[:8],
    }
    lang_name = _LANG_NAMES.get(lang, "Tiếng Việt")
    sys_msg = (
        f"Bạn là Chuyên gia Data Analyst & Business Intelligence cấp cao (Hà Thuỳ Dương). "
        f"Hãy trả lời bằng {lang_name}. "
        "Chỉ sử dụng con số có thật trong JSON thống kê được cung cấp; tuyệt đối không tự bịa thêm số. "
        "Phân tích sâu sắc theo mô hình DATA -> INFORMATION -> INSIGHT -> DECISION: "
        "(1) Trả lời trực tiếp câu hỏi/vấn đề của người dùng, "
        "(2) Chỉ ra nguyên nhân biến động chính (nếu có chuỗi thời gian/so sánh nhóm), "
        "(3) Cảnh báo rủi ro/ngoại lai, và "
        "(4) Đề xuất 2-3 hành động ưu tiên kèm KPI đo lường. Viết 5-7 gạch đầu dòng súc tích, sắc bén."
    )
    u_msg = (
        f"Yêu cầu khách hàng: {user_prompt or 'Tổng hợp phân tích toàn diện, cây KPI/MG và phân nhóm ưu tiên.'}\n"
        f"Dữ liệu thống kê đã làm sạch:\n{json.dumps(compact_ctx, ensure_ascii=False)}"
    )
    try:
        if agent_mode == "gemini":
            url = build_gemini_endpoint_url(api_key, model or "gemini-2.5-flash")
            payload = {
                "systemInstruction": {"parts": [{"text": sys_msg}]},
                "contents": [{"role": "user", "parts": [{"text": u_msg}]}],
                "generationConfig": {"temperature": 0.2},
            }
            req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"}, method="POST")
            with secure_urlopen(req, timeout=timeout_sec) as resp:
                texts, _, _ = extract_gemini_parts(json.loads(resp.read().decode("utf-8")))
                return "\n".join(texts).strip()
        if agent_mode == "openai":
            clean_base = (base_url or "https://api.openai.com/v1").rstrip("/")
            payload = {
                "model": (model or "gpt-4o-mini").strip(),
                "messages": [{"role": "system", "content": sys_msg}, {"role": "user", "content": u_msg}],
                "temperature": 0.2,
            }
            req = urllib.request.Request(
                f"{clean_base}/chat/completions",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
                method="POST",
            )
            with secure_urlopen(req, timeout=timeout_sec) as resp:
                msg = ((json.loads(resp.read().decode("utf-8")).get("choices") or [{}])[0]).get("message") or {}
                return str(msg.get("content") or "").strip()
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise LLMClientError(f"LLM API HTTP {exc.code}: {body[:300]}") from exc
    except urllib.error.URLError as exc:
        raise LLMClientError(f"Không thể kết nối LLM API: {exc.reason}") from exc
    return ""


ASSISTANT_SYSTEM_PROMPT = """Bạn là Trợ lý AI thông minh trên website chính thức của Hà Thuỳ Dương (Data Analyst & Business Intelligence).
Hãy trả lời tự nhiên, thân thiện, thông minh và chính xác mọi câu hỏi của người dùng bằng tiếng Việt (hoặc theo ngôn ngữ người dùng hỏi).

THÔNG TIN VỀ HÀ THUỲ DƯƠNG (khi người dùng hỏi "Hà Thuỳ Dương là ai", về chủ nhân website, học vấn, CLB, ngày sinh, nơi sống, liên hệ):
- Họ tên: Hà Thuỳ Dương.
- Ngày sinh: 24/03/2007.
- Nơi sống: Hà Nội.
- Học vấn & Vai trò: Một cô sinh viên ngành Quản trị Kinh doanh đầy năng nổ của Học viện Công nghệ Bưu chính Viễn thông (PTIT), đồng thời là Trưởng ban Sự kiện nhiệt huyết của câu lạc bộ Business Creators Club (BCC). Dương có lịch trình khá bận rộn với các dự án và sự kiện sinh viên, đồng thời phát triển hệ thống Data Analyst & BI này.
- Liên hệ: SĐT/Hotline 0332 125 570 · Email htd24307@gmail.com.
- Mạng xã hội: Facebook (https://www.facebook.com/tuila.duo), Instagram (https://www.instagram.com/ha._hthduo/), TikTok (https://www.tiktok.com/@hihihihtddd).

THÔNG TIN VỀ HỆ THỐNG WEBSITE:
- Đọc mọi định dạng: Excel (.xlsx, .xls, .ods), CSV, Word (.docx/.doc), PDF, JSON, XML, HTML, Markdown, ZIP, ảnh, Google Sheet và Lark Base.
- Quy trình 4 bước bám sát sơ đồ: (1) Gửi dữ liệu & Trao đổi yêu cầu với AI -> AI nhận dữ liệu (báo lỗi nếu không đọc được để gửi lại), (2) Làm sạch dữ liệu & xem trước bảng sạch (báo lỗi nếu làm sạch không được), (3) Phân tích Dashboard KPI, biểu đồ, Insight DATA -> INFORMATION -> INSIGHT -> DECISION, (4) Bàn giao 4 sản phẩm: Excel dữ liệu sạch (.xlsx), Excel tổng hợp & biểu đồ (.xlsx), Dashboard/HTML, Báo cáo Word (.docx)/PDF 10 mục.
- Bảo mật: Dữ liệu xử lý cục bộ; chỉ gọi Gemini/OpenAI khi người dùng bật. Giữ nguyên file gốc, không tự bịa số liệu."""


def chat_with_assistant(
    message: str,
    history: Optional[List[Dict[str, str]]] = None,
    api_key: str = "",
    model: str = "gemini-2.5-flash",
    timeout_sec: int = 12,
    lang: str = "vi",
) -> str:
    """Answer user chat messages using Gemini (Vertex Express or AI Studio) with full site/bio context."""
    clean_msg = (message or "").strip()
    if not clean_msg or not api_key:
        return ""
    contents: List[Dict[str, Any]] = []
    for item in (history or [])[-6:]:
        role = "model" if item.get("role") == "bot" else "user"
        txt = str(item.get("text") or "").strip()
        if txt:
            contents.append({"role": role, "parts": [{"text": txt[:600]}]})
    contents.append({"role": "user", "parts": [{"text": clean_msg}]})

    lang_name = _LANG_NAMES.get(lang, "Tiếng Việt")
    sys_prompt = ASSISTANT_SYSTEM_PROMPT + f"\n\nNGÔN NGỮ TRẢ LỜI MẶC ĐỊNH: {lang_name} (trừ khi người dùng viết bằng ngôn ngữ khác thì trả lời theo ngôn ngữ đó). Trả lời nhanh, tự nhiên, súc tích, thân thiện."
    url = build_gemini_endpoint_url(api_key, model or "gemini-2.5-flash")
    payload = {
        "systemInstruction": {"parts": [{"text": sys_prompt}]},
        "contents": contents,
        "generationConfig": {"temperature": 0.5, "maxOutputTokens": 500},
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with secure_urlopen(req, timeout=timeout_sec) as resp:
        texts, _, _ = extract_gemini_parts(json.loads(resp.read().decode("utf-8")))
        return "\n".join(texts).strip()




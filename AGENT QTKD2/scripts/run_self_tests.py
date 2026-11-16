"""Comprehensive automated self-test suite for AI301 Project 04 (Hung Phat AI Agent)."""

from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.llm_client import build_gemini_endpoint_url  # noqa: E402
from agent.orchestrator import MarketEvaluationOrchestrator  # noqa: E402
from agent.parsers import (  # noqa: E402
    classify_sheets_to_canonical,
    convert_lark_records_to_rows,
    parse_csv_bytes,
    parse_docx_bytes,
    parse_google_sheet_url,
    parse_json_records_bytes,
    parse_lark_base_url,
    parse_xlsx_bytes,
)
import app as app_module  # noqa: E402
from app import AgentHTTPHandler  # noqa: E402


SAMPLES_DIR = ROOT / "data" / "samples"


class _MockSocket:
    """In-memory socket-like transport to exercise BaseHTTPRequestHandler cleanly."""

    def __init__(self, raw_request: bytes) -> None:
        self._rfile = io.BytesIO(raw_request)
        self._wfile = io.BytesIO()

    def makefile(self, mode: str, *args, **kwargs):  # noqa: ANN002, ANN003
        return self._rfile if "r" in mode else self._wfile

    def sendall(self, data: bytes) -> None:
        self._wfile.write(data)

    def close(self) -> None:
        pass


def invoke_http_handler(method: str, path: str, body: bytes = b"", content_type: str = "") -> tuple[int, dict, bytes]:
    """Invoke AgentHTTPHandler directly over an in-memory HTTP wire request."""
    headers = [f"{method} {path} HTTP/1.1", "Host: localhost"]
    if body:
        headers.append(f"Content-Length: {len(body)}")
    if content_type:
        headers.append(f"Content-Type: {content_type}")
    raw_req = ("\r\n".join(headers) + "\r\n\r\n").encode("utf-8") + body

    sock = _MockSocket(raw_req)
    AgentHTTPHandler(sock, ("127.0.0.1", 0), None)
    raw_resp = sock._wfile.getvalue()
    head_bytes, _, resp_body = raw_resp.partition(b"\r\n\r\n")
    head_lines = head_bytes.decode("latin-1").split("\r\n")
    status_code = int(head_lines[0].split()[1])
    resp_headers = {}
    for ln in head_lines[1:]:
        if ":" in ln:
            k, v = ln.split(":", 1)
            resp_headers[k.strip().lower()] = v.strip()
    return status_code, resp_headers, resp_body


class TestHungPhatAgent(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.audit_dir = Path(self._tmpdir.name)
        self.orchestrator = MarketEvaluationOrchestrator(log_dir=self.audit_dir)

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def test_google_sheet_url_parser(self) -> None:
        sid, gid = parse_google_sheet_url(
            "https://docs.google.com/spreadsheets/d/1AbCdEfGhIjKlMnOpQrStUvWxYz/edit#gid=123456"
        )
        self.assertEqual(sid, "1AbCdEfGhIjKlMnOpQrStUvWxYz")
        self.assertEqual(gid, "123456")

        sid2, gid2 = parse_google_sheet_url("https://docs.google.com/spreadsheets/d/SheetKey_99/view")
        self.assertEqual(sid2, "SheetKey_99")
        self.assertIsNone(gid2)

        with self.assertRaises(ValueError):
            parse_google_sheet_url("https://example.com/not-a-gsheet")

    def test_csv_and_xlsx_parity(self) -> None:
        xlsx_sheets = parse_xlsx_bytes((SAMPLES_DIR / "case1_thong_thuong.xlsx").read_bytes(), "case1.xlsx")
        csv_dir = SAMPLES_DIR / "case1_thong_thuong_csv"
        csv_sheets = {}
        for p in sorted(csv_dir.glob("*.csv")):
            csv_sheets.update(parse_csv_bytes(p.read_bytes(), p.name))

        self.assertEqual(set(xlsx_sheets.keys()), set(csv_sheets.keys()))
        for k in xlsx_sheets:
            self.assertEqual(len(xlsx_sheets[k]), len(csv_sheets[k]))

        mapped = classify_sheets_to_canonical(csv_sheets)
        self.assertEqual(len(mapped["canonical_data"]["market_reports"]), 5)
        self.assertEqual(len(mapped["canonical_data"]["evaluation_criteria"]), 4)

    def test_case1_normal_traps(self) -> None:
        sheets = parse_xlsx_bytes((SAMPLES_DIR / "case1_thong_thuong.xlsx").read_bytes(), "case1.xlsx")
        res = self.orchestrator.start_run(sheets)

        self.assertEqual(res["workflow_status"], "COMPLETED")
        self.assertEqual(res["ingestion"]["summary"]["dedup_dropped_count"], 1)
        self.assertEqual(res["ingestion"]["dedup_log"][0]["dropped_record_id"], "MT-04")
        self.assertGreaterEqual(res["ingestion"]["summary"]["period_normalizations"], 2)

        eval_res = res["evaluation"]
        self.assertEqual(eval_res["decision_status"], "SELECTED_2_LOCATIONS")
        self.assertEqual(eval_res["selected_locations"], ["Bình Dương", "Đà Nẵng"])

        by_loc = {e["location"]: e for e in eval_res["evaluations"]}
        self.assertEqual(by_loc["Hải Phòng"]["overall_status"], "DISQUALIFIED")
        hp_scores = {c["category_key"]: c for c in by_loc["Hải Phòng"]["criterion_scores"]}
        self.assertEqual(hp_scores["market_size"]["raw_score"], 10.0)
        self.assertEqual(hp_scores["deployment_capability"]["gate_status"], "FAIL")

        self.assertEqual(by_loc["Cần Thơ"]["overall_status"], "DISQUALIFIED")
        ct_scores = {c["category_key"]: c for c in by_loc["Cần Thơ"]["criterion_scores"]}
        self.assertEqual(ct_scores["product_fit"]["gate_status"], "FAIL")

        self.assertGreaterEqual(res["audit"]["summary"]["tool_calls"], 5)
        self.assertEqual(len(res["proposal"]["survey_plan"]), 2)

    def test_case2_missing_and_conflict_hitl(self) -> None:
        sheets = parse_xlsx_bytes((SAMPLES_DIR / "case2_thieu_mau_thuan.xlsx").read_bytes(), "case2.xlsx")
        res = self.orchestrator.start_run(sheets)

        self.assertEqual(res["workflow_status"], "AWAITING_HUMAN_STAGE3")
        self.assertFalse(res["conflict_gap"]["enough_data"])
        self.assertTrue(res["conflict_gap"]["hitl_required"])
        self.assertIsNone(res["evaluation"])

        # Path A: Acknowledge incomplete without fabricating data
        res_ack = self.orchestrator.resume_with_human_input(
            res["run_id"],
            {"acknowledge_incomplete": True},
        )
        self.assertEqual(res_ack["evaluation"]["decision_status"], "INSUFFICIENT_EVIDENCE")
        self.assertEqual(res_ack["evaluation"]["selected_locations"], ["Bình Dương"])
        self.assertGreaterEqual(len(res_ack["evaluation"]["conditions_to_supplement"]), 2)
        by_loc_ack = {e["location"]: e for e in res_ack["evaluation"]["evaluations"]}
        self.assertEqual(by_loc_ack["Nghệ An"]["overall_status"], "INSUFFICIENT_DATA")
        self.assertEqual(by_loc_ack["Đà Nẵng"]["overall_status"], "INSUFFICIENT_DATA")

        # Path B: Resolve Đà Nẵng conflicts via HITL choices -> Đà Nẵng becomes valid #2
        conflicts = [it for it in res["conflict_gap"]["issues"] if it["issue_type"] == "CONFLICT"]
        conflict_choices = {}
        for cf in conflicts:
            kept = cf["candidates"][0]["record_id"]
            rejected = [c["record_id"] for c in cf["candidates"][1:]]
            conflict_choices[cf["issue_id"]] = {
                "selected_record_id": kept,
                "rejected_record_ids": rejected,
                "note": "Chọn nguồn chính thống",
            }
        res_resolved = self.orchestrator.resume_with_human_input(
            res["run_id"],
            {
                "conflict_choices": conflict_choices,
                "acknowledge_incomplete": True,
            },
        )
        self.assertEqual(res_resolved["evaluation"]["selected_locations"], ["Bình Dương", "Đà Nẵng"])

    def test_case3_rule_boundaries_and_near_tie(self) -> None:
        sheets = parse_xlsx_bytes((SAMPLES_DIR / "case3_ranh_gioi_quy_tac.xlsx").read_bytes(), "case3.xlsx")
        res = self.orchestrator.start_run(sheets)

        self.assertEqual(res["workflow_status"], "COMPLETED_WITH_HITL_REVIEW")
        eval_res = res["evaluation"]
        self.assertEqual(eval_res["decision_status"], "SELECTED_WITH_BOUNDARY_REVIEW")
        self.assertEqual(eval_res["selected_locations"], ["Bình Dương", "Đà Nẵng"])
        self.assertIsNotNone(eval_res["near_tie_alert"])

        by_loc = {e["location"]: e for e in eval_res["evaluations"]}
        dn_scores = {c["category_key"]: c for c in by_loc["Đà Nẵng"]["criterion_scores"]}
        self.assertEqual(dn_scores["product_fit"]["raw_score"], 6.0)
        self.assertEqual(dn_scores["product_fit"]["gate_status"], "BOUNDARY_PASS")
        self.assertEqual(dn_scores["deployment_capability"]["raw_score"], 6.0)
        self.assertEqual(dn_scores["deployment_capability"]["gate_status"], "BOUNDARY_PASS")

        self.assertEqual(by_loc["Hải Phòng"]["overall_status"], "DISQUALIFIED")
        hp_scores = {c["category_key"]: c for c in by_loc["Hải Phòng"]["criterion_scores"]}
        self.assertEqual(hp_scores["product_fit"]["raw_score"], 5.95)
        self.assertEqual(hp_scores["product_fit"]["gate_status"], "FAIL")

        signed = self.orchestrator.record_boundary_decision(
            res["run_id"],
            decision="APPROVED_AGENT_TOP_2",
            note="Duyệt khảo sát Đà Nẵng kèm thẩm định SLA",
        )
        self.assertEqual(signed["workflow_status"], "COMPLETED_APPROVED")
        self.assertGreaterEqual(signed["audit"]["summary"]["human_actions"], 1)

    def test_http_handler_e2e_multipart_and_hitl(self) -> None:
        orig_audit_dir = app_module.AUDIT_DIR
        orig_log_dir = app_module.ORCHESTRATOR.log_dir
        app_module.AUDIT_DIR = self.audit_dir
        app_module.ORCHESTRATOR.log_dir = self.audit_dir
        try:
            self._run_http_e2e_assertions()
        finally:
            app_module.AUDIT_DIR = orig_audit_dir
            app_module.ORCHESTRATOR.log_dir = orig_log_dir

    def _run_http_e2e_assertions(self) -> None:
        # 1. GET / & GET /api/health
        code, _, html_body = invoke_http_handler("GET", "/")
        self.assertEqual(code, 200)
        self.assertIn("AI301 AI Agent - Đề Dự Án 04", html_body.decode("utf-8"))

        code, _, health_body = invoke_http_handler("GET", "/api/health")
        self.assertEqual(code, 200)
        self.assertEqual(json.loads(health_body.decode("utf-8"))["status"], "ok")

        # 2. Multipart CSV upload to /api/inspect-inputs -> /api/run
        csv_dir = SAMPLES_DIR / "case1_thong_thuong_csv"
        boundary = f"----WebKitFormBoundary{uuid4().hex}"
        parts = []
        for p in sorted(csv_dir.glob("*.csv")):
            parts.append(
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="files"; filename="{p.name}"\r\n'
                f"Content-Type: text/csv\r\n\r\n".encode("utf-8")
                + p.read_bytes()
                + b"\r\n"
            )
        parts.append(
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="payload"\r\n\r\n'.encode("utf-8")
            + json.dumps({"config": {"agent_mode": "local"}}).encode("utf-8")
            + b"\r\n"
        )
        parts.append(f"--{boundary}--\r\n".encode("utf-8"))
        mp_body = b"".join(parts)

        code, _, insp_body = invoke_http_handler(
            "POST",
            "/api/inspect-inputs",
            body=mp_body,
            content_type=f"multipart/form-data; boundary={boundary}",
        )
        self.assertEqual(code, 200)
        insp_data = json.loads(insp_body.decode("utf-8"))
        self.assertEqual(len(insp_data["sheet_assignments"]), 6)

        code, _, run_body = invoke_http_handler(
            "POST",
            "/api/run",
            body=json.dumps({"staged_id": insp_data["staged_id"], "config": {"agent_mode": "local"}}).encode("utf-8"),
            content_type="application/json",
        )
        self.assertEqual(code, 200)
        run_data = json.loads(run_body.decode("utf-8"))
        self.assertEqual(run_data["workflow_status"], "COMPLETED")
        self.assertEqual(run_data["evaluation"]["selected_locations"], ["Bình Dương", "Đà Nẵng"])
        run_id = run_data["run_id"]

        # 3. Export endpoints (/audit & /report.md)
        code, _, aud_body = invoke_http_handler("GET", f"/api/runs/{run_id}/audit")
        self.assertEqual(code, 200)
        self.assertEqual(json.loads(aud_body.decode("utf-8"))["run_id"], run_id)

        code, _, md_body = invoke_http_handler("GET", f"/api/runs/{run_id}/report.md")
        self.assertEqual(code, 200)
        self.assertIn("BÁO CÁO ĐỀ XUẤT MỞ RỘNG THỊ TRƯỜNG", md_body.decode("utf-8"))

        code, _, html_rep = invoke_http_handler("GET", f"/api/runs/{run_id}/report.html")
        self.assertEqual(code, 200)
        self.assertIn("<!DOCTYPE html>", html_rep.decode("utf-8"))
        self.assertIn("Bình Dương", html_rep.decode("utf-8"))

        # 4. Boundary signoff endpoint via sample case3
        code, _, c3_body = invoke_http_handler(
            "POST",
            "/api/run",
            body=json.dumps({"sample_id": "case3_ranh_gioi_quy_tac", "config": {"agent_mode": "local"}}).encode("utf-8"),
            content_type="application/json",
        )
        self.assertEqual(code, 200)
        c3_data = json.loads(c3_body.decode("utf-8"))
        self.assertEqual(c3_data["workflow_status"], "COMPLETED_WITH_HITL_REVIEW")

        code, _, sign_body = invoke_http_handler(
            "POST",
            "/api/hitl/boundary-signoff",
            body=json.dumps({"run_id": c3_data["run_id"], "decision": "APPROVED_AGENT_TOP_2", "note": "OK"}).encode("utf-8"),
            content_type="application/json",
        )
        self.assertEqual(code, 200)
        self.assertEqual(json.loads(sign_body.decode("utf-8"))["workflow_status"], "COMPLETED_APPROVED")

        # 5. Stage 3 HITL resolve endpoint via sample case2
        code, _, c2_body = invoke_http_handler(
            "POST",
            "/api/run",
            body=json.dumps({"sample_id": "case2_thieu_mau_thuan", "config": {"agent_mode": "local"}}).encode("utf-8"),
            content_type="application/json",
        )
        self.assertEqual(code, 200)
        c2_data = json.loads(c2_body.decode("utf-8"))
        self.assertEqual(c2_data["workflow_status"], "AWAITING_HUMAN_STAGE3")

        code, _, c2_res_body = invoke_http_handler(
            "POST",
            "/api/hitl/resolve",
            body=json.dumps(
                {
                    "run_id": c2_data["run_id"],
                    "human_resolutions": {"acknowledge_incomplete": True},
                }
            ).encode("utf-8"),
            content_type="application/json",
        )
        self.assertEqual(code, 200)
        c2_res_data = json.loads(c2_res_body.decode("utf-8"))
        self.assertEqual(c2_res_data["evaluation"]["decision_status"], "INSUFFICIENT_EVIDENCE")

    def test_flexible_exam_day_headers_and_text_levels(self) -> None:
        custom_sheets = {
            "Bao_Cao_Thi_Truong_2026": [
                {"_row_number": 2, "_source_file": "exam.xlsx", "_sheet_name": "Bao_Cao_Thi_Truong_2026",
                 "Địa bàn": "TP. Cần Thơ", "Quy mô thị trường (tỷ VNĐ)": "200", "Kỳ thống kê": "Quý 4 2025", "Nguồn tài liệu": "GSO"},
                {"_row_number": 3, "_source_file": "exam.xlsx", "_sheet_name": "Bao_Cao_Thi_Truong_2026",
                 "Địa bàn": "tỉnh Long An", "Quy mô thị trường (tỷ VNĐ)": "180", "Kỳ thống kê": "2025-Q4", "Nguồn tài liệu": "GSO"},
            ],
            "Feedback_Khach_Hang": [
                {"_row_number": 2, "_source_file": "exam.xlsx", "_sheet_name": "Feedback_Khach_Hang",
                 "Địa bàn": "Cần Thơ", "Phân khúc": "Siêu thị mini", "Tính năng cần thiết": "Quản lý tồn kho đa điểm",
                 "Mức độ quan tâm": "Cao", "Yêu cầu hỗ trợ tại chỗ": "Thấp"},
                {"_row_number": 3, "_source_file": "exam.xlsx", "_sheet_name": "Feedback_Khach_Hang",
                 "Địa bàn": "Long An", "Phân khúc": "Chuỗi bán lẻ", "Tính năng cần thiết": "Quản lý tồn kho đa điểm",
                 "Mức độ quan tâm": "Cao", "Yêu cầu hỗ trợ tại chỗ": "Rất cao"},
            ],
            "Danh_Muc_San_Pham": [
                {"_row_number": 2, "_source_file": "exam.xlsx", "_sheet_name": "Danh_Muc_San_Pham",
                 "Tên giải pháp": "WMS Core", "Tính năng": "Quản lý tồn kho đa điểm", "Trạng thái sản phẩm": "Sẵn sàng"},
            ],
            "Nang_Luc_Trien_Khai": [
                {"_row_number": 2, "_source_file": "exam.xlsx", "_sheet_name": "Nang_Luc_Trien_Khai",
                 "Địa bàn": "Cần Thơ", "Khả năng onsite": "Cao"},
                {"_row_number": 3, "_source_file": "exam.xlsx", "_sheet_name": "Nang_Luc_Trien_Khai",
                 "Địa bàn": "Long An", "Khả năng onsite": "Thấp"},
            ],
            "Ho_So_Doi_Thu": [
                {"_row_number": 2, "_source_file": "exam.xlsx", "_sheet_name": "Ho_So_Doi_Thu",
                 "Địa bàn": "Cần Thơ", "Tên đối thủ": "Competitor A", "Áp lực cạnh tranh": "Trung bình"},
                {"_row_number": 3, "_source_file": "exam.xlsx", "_sheet_name": "Ho_So_Doi_Thu",
                 "Địa bàn": "Long An", "Tên đối thủ": "Competitor B", "Áp lực cạnh tranh": "Thấp"},
            ],
        }
        res = self.orchestrator.start_run(custom_sheets)
        self.assertEqual(res["workflow_status"], "COMPLETED_WITH_HITL_REVIEW")
        by_loc = {e["location"]: e for e in res["evaluation"]["evaluations"]}
        self.assertEqual(by_loc["Cần Thơ"]["overall_status"], "SELECTED")
        self.assertEqual(by_loc["Long An"]["overall_status"], "DISQUALIFIED")

    def test_column_overrides_mapping(self) -> None:
        weird_sheets = {
            "Sheet1": [
                {"_row_number": 2, "_source_file": "weird.xlsx", "_sheet_name": "Sheet1",
                 "Vung_Mien_X": "Bình Dương", "Chi_So_A": "300", "Thoi_Gian_Y": "2025-Q4", "Tac_Gia_Z": "GSO"},
                {"_row_number": 3, "_source_file": "weird.xlsx", "_sheet_name": "Sheet1",
                 "Vung_Mien_X": "Đà Nẵng", "Chi_So_A": "250", "Thoi_Gian_Y": "2025-Q4", "Tac_Gia_Z": "GSO"},
            ]
        }
        mapped = classify_sheets_to_canonical(
            weird_sheets,
            table_overrides={"Sheet1": "market_reports"},
            column_overrides={
                "market_reports": {
                    "location": "Vung_Mien_X",
                    "market_size_vnd_bn": "Chi_So_A",
                    "report_period": "Thoi_Gian_Y",
                    "source_name": "Tac_Gia_Z",
                }
            },
        )
        m_rows = mapped["canonical_data"]["market_reports"]
        self.assertEqual(len(m_rows), 2)
        self.assertEqual(m_rows[0]["location"], "Bình Dương")
        self.assertEqual(m_rows[0]["market_size_vnd_bn"], "300")

    def test_dedup_without_origin_source_id(self) -> None:
        sheets = parse_xlsx_bytes((SAMPLES_DIR / "case1_thong_thuong.xlsx").read_bytes(), "case1.xlsx")
        # Remove origin_source_id across all market rows to test Case C secondary-citation detection
        for row in sheets["ThiTruong"]:
            row["ma_nguon_goc"] = ""
        res = self.orchestrator.start_run(sheets)
        self.assertEqual(res["ingestion"]["summary"]["dedup_dropped_count"], 1)
        self.assertEqual(res["ingestion"]["dedup_log"][0]["dropped_record_id"], "MT-04")

    def test_gemini_endpoint_routing(self) -> None:
        u1 = build_gemini_endpoint_url("AQ.TestExpressKey", "gemini-2.5-flash")
        self.assertTrue(u1.startswith("https://aiplatform.googleapis.com/v1/publishers/google/models/gemini-2.5-flash:generateContent?key="))
        u2 = build_gemini_endpoint_url("AIzaTestStudioKey", "gemini-2.5-flash")
        self.assertTrue(u2.startswith("https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key="))

    def test_docx_reports_valid(self) -> None:
        import zipfile
        import xml.etree.ElementTree as ET

        docs_dir = ROOT / "docs"
        for name in ("BaoCao_Task1_PhanTich_ThietKe.docx", "BaoCao_Task2_GiaiPhap_KiemThu.docx"):
            path = docs_dir / name
            self.assertTrue(path.exists(), f"Missing {path}")
            with zipfile.ZipFile(path, "r") as zf:
                names = set(zf.namelist())
                self.assertIn("word/document.xml", names)
                self.assertIn("word/styles.xml", names)
                ET.fromstring(zf.read("word/document.xml"))

    def test_flowchart_receive_and_clean_gates(self) -> None:
        # Gate 1 fail (Nhận được OK? = Không): empty / unrecognized sheet -> FAILED_RECEIVE_DATA
        bad_sheets = {"SheetRong": []}
        r1 = self.orchestrator.start_run(bad_sheets)
        self.assertEqual(r1["workflow_status"], "FAILED_RECEIVE_DATA")
        self.assertTrue(r1["gate_status"]["requires_resubmit"])
        self.assertEqual(r1["gate_status"]["gate_failed"], "RECEIVE_DATA")
        self.assertIsNone(r1["evaluation"])

        # Gate 2 fail (Làm sạch thành công? = Không): market rows with empty locations -> FAILED_CLEAN_DATA
        unclean_sheets = {
            "ThiTruong": [
                {"dia_ban": "", "quy_mo_ty_vnd": "abc_loi", "ky_bao_cao": "2025"},
            ]
        }
        r2 = self.orchestrator.start_run(unclean_sheets)
        self.assertEqual(r2["workflow_status"], "FAILED_CLEAN_DATA")
        self.assertTrue(r2["gate_status"]["requires_resubmit"])
        self.assertEqual(r2["gate_status"]["gate_failed"], "CLEAN_DATA")
        self.assertIsNone(r2["evaluation"])

    def test_docx_table_and_text_parser(self) -> None:
        import zipfile

        doc_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
        <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
          <w:body>
            <w:p><w:r><w:t>Báo cáo doanh thu Quý 4: Tổng doanh thu: 1250 triệu VND</w:t></w:r></w:p>
            <w:p><w:r><w:t>Nhận xét chung về tăng trưởng phòng kinh doanh công ty.</w:t></w:r></w:p>
            <w:tbl>
              <w:tr>
                <w:tc><w:p><w:r><w:t>Phòng ban</w:t></w:r></w:p></w:tc>
                <w:tc><w:p><w:r><w:t>Doanh thu</w:t></w:r></w:p></w:tc>
                <w:tc><w:p><w:r><w:t>Số nhân sự</w:t></w:r></w:p></w:tc>
              </w:tr>
              <w:tr>
                <w:tc><w:p><w:r><w:t>Kinh doanh</w:t></w:r></w:p></w:tc>
                <w:tc><w:p><w:r><w:t>800</w:t></w:r></w:p></w:tc>
                <w:tc><w:p><w:r><w:t>12</w:t></w:r></w:p></w:tc>
              </w:tr>
              <w:tr>
                <w:tc><w:p><w:r><w:t>Marketing</w:t></w:r></w:p></w:tc>
                <w:tc><w:p><w:r><w:t>450</w:t></w:r></w:p></w:tc>
                <w:tc><w:p><w:t><w:t>8</w:t></w:t></w:r></w:p></w:tc>
              </w:tr>
            </w:tbl>
          </w:body>
        </w:document>""".replace("<w:p><w:t><w:t>8</w:t></w:t></w:r></w:p>", "<w:p><w:r><w:t>8</w:t></w:r></w:p>")
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("word/document.xml", doc_xml.encode("utf-8"))
        parsed_sheets, parsed_paragraphs = parse_docx_bytes(buf.getvalue(), "bao_cao.docx")
        self.assertGreaterEqual(len(parsed_sheets), 1)
        first_sheet = next(iter(parsed_sheets.values()))
        self.assertEqual(len(first_sheet), 2)
        self.assertEqual(first_sheet[0]["Phòng ban"], "Kinh doanh")
        self.assertEqual(first_sheet[1]["Doanh thu"], "450")
        self.assertGreaterEqual(len(parsed_paragraphs), 2)

    def test_lark_base_url_and_json_parser(self) -> None:
        api_origin, app_token, table_id = parse_lark_base_url(
            "https://company.larksuite.com/base/AbCdEfGhIj12?table=tblXYZ99&view=vew01"
        )
        self.assertEqual(api_origin, "https://open.larksuite.com/open-apis")
        self.assertEqual(app_token, "AbCdEfGhIj12")
        self.assertEqual(table_id, "tblXYZ99")

        rows = convert_lark_records_to_rows(
            "DonHang",
            [
                {
                    "record_id": "rec01",
                    "fields": {
                        "Ten_SP": [{"text": "Phần mềm ERP"}],
                        "Doanh_Thu": 520,
                        "Trang_Thai": "Hoạt động",
                    },
                }
            ],
            source_label="lark_base:AbCd",
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["Ten_SP"], "Phần mềm ERP")
        self.assertEqual(rows[0]["Doanh_Thu"], "520")

        json_raw = json.dumps({"data": {"items": [{"record_id": "r1", "fields": {"KPI": 95, "KhuVuc": "HCM"}}]}}).encode("utf-8")
        jsheets = parse_json_records_bytes(json_raw, "lark_export.json")
        self.assertEqual(len(next(iter(jsheets.values()))), 1)

    def test_company_statistics_mode_and_http_e2e(self) -> None:
        # Generic company sales CSV uploaded over HTTP /api/run -> company_statistics mode + /report.html
        csv_bytes = (
            "PhongBan,DoanhThuTrieu,ChiPhiTrieu,TyLeChot\n"
            "B2B,500,120,35%\n"
            "B2B,500,120,35%\n"
            "Retail,300,80,28%\n"
        ).encode("utf-8")
        boundary = f"----StatBoundary{uuid4().hex}".encode("ascii")
        payload_json = json.dumps({"config": {"agent_mode": "local"}}).encode("utf-8")
        body = b"".join([
            b"--", boundary, b"\r\n",
            b'Content-Disposition: form-data; name="payload"\r\n\r\n',
            payload_json, b"\r\n",
            b"--", boundary, b"\r\n",
            b'Content-Disposition: form-data; name="files"; filename="doanh_thu_cong_ty.csv"\r\n',
            b"Content-Type: text/csv\r\n\r\n",
            csv_bytes, b"\r\n",
            b"--", boundary, b"--\r\n",
        ])
        status, _, resp_bytes = invoke_http_handler(
            "POST", "/api/run", body=body, content_type=f"multipart/form-data; boundary={boundary.decode()}"
        )
        self.assertEqual(status, 200)
        res = json.loads(resp_bytes.decode("utf-8"))
        self.assertEqual(res["analysis_mode"], "company_statistics")
        self.assertEqual(res["workflow_status"], "COMPLETED")
        self.assertEqual(res["company_stats"]["total_rows_raw"], 3)
        self.assertEqual(res["company_stats"]["total_rows_clean"], 2)
        self.assertEqual(res["company_stats"]["dedup_dropped_count"], 1)
        self.assertEqual(res["company_stats"]["numeric_highlights"][0]["sum"], 800.0)
        self.assertIn("THỐNG KÊ DỮ LIỆU CÔNG TY", res["proposal"]["markdown_report"])

        r_status, _, html_bytes = invoke_http_handler("GET", f"/api/runs/{res['run_id']}/report.html")
        self.assertEqual(r_status, 200)
        self.assertIn("Thống kê", html_bytes.decode("utf-8"))

    def test_universal_format_parsers(self) -> None:
        import zipfile
        import zlib
        from agent.parsers import (
            parse_html_tables_bytes,
            parse_markdown_or_text_bytes,
            parse_ods_bytes,
            parse_pdf_bytes,
            parse_xls_bytes,
            parse_xml_records_bytes,
        )

        # 1. HTML / HTML-disguised XLS table
        html_raw = (
            "<html><body><table><tr><th>KhachHang</th><th>DoanhThu</th></tr>"
            "<tr><td>Alpha Corp</td><td>450</td></tr><tr><td>Beta JSC</td><td>120</td></tr></table></body></html>"
        ).encode("utf-8")
        h_sheets, _ = parse_html_tables_bytes(html_raw, "khach_hang.html")
        self.assertEqual(len(next(iter(h_sheets.values()))), 2)
        xls_sheets, _ = parse_xls_bytes(html_raw, "legacy_export.xls")
        self.assertEqual(next(iter(xls_sheets.values()))[0]["KhachHang"], "Alpha Corp")

        # 2. Markdown tables + key:value lines
        md_raw = (
            "# Dự án KPI\n| DuAn | TienDo | TrangThai |\n|---|---|---|\n| ERP | 90% | Đúng hạn |\n| CRM | 40% | Chậm |\n"
        ).encode("utf-8")
        md_sheets, _ = parse_markdown_or_text_bytes(md_raw, "du_an.md")
        self.assertEqual(len(next(iter(md_sheets.values()))), 2)

        # 3. XML records
        xml_raw = "<records><record><Ten>KHO A</Ten><ChiPhi>200</ChiPhi></record><record><Ten>KHO B</Ten><ChiPhi>150</ChiPhi></record></records>".encode("utf-8")
        xml_sheets, _ = parse_xml_records_bytes(xml_raw, "chi_phi.xml")
        self.assertEqual(next(iter(xml_sheets.values()))[1]["ChiPhi"], "150")

        # 4. Pure-Python OpenDocument .ods
        ods_xml = """<?xml version="1.0" encoding="UTF-8"?>
        <office:document-content xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" xmlns:table="urn:oasis:names:tc:opendocument:xmlns:table:1.0" xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0">
          <office:body><office:spreadsheet>
            <table:table table:name="TaiChinh">
              <table:table-row><table:table-cell><text:p>KhoanMuc</text:p></table:table-cell><table:table-cell><text:p>SoTien</text:p></table:table-cell></table:table-row>
              <table:table-row><table:table-cell><text:p>Thu</text:p></table:table-cell><table:table-cell office:value="900"><text:p>900</text:p></table:table-cell></table:table-row>
            </table:table>
          </office:spreadsheet></office:body>
        </office:document-content>""".encode("utf-8")
        ods_buf = io.BytesIO()
        with zipfile.ZipFile(ods_buf, "w") as zf:
            zf.writestr("content.xml", ods_xml)
        ods_sheets = parse_ods_bytes(ods_buf.getvalue(), "taichinh.ods")
        self.assertEqual(ods_sheets["TaiChinh"][0]["SoTien"], "900")

        # 5. Pure-Python PDF FlateDecode stream
        stream_data = zlib.compress(b"BT\n(DoanhThuThang: 650) Tj\n(KhachVIP: 12) Tj\nET")
        pdf_raw = b"%PDF-1.4\n1 0 obj\n<< /Length " + str(len(stream_data)).encode() + b" >>\nstream\n" + stream_data + b"\nendstream\n%%EOF"
        p_sheets, p_paras = parse_pdf_bytes(pdf_raw, "bao_cao.pdf")
        self.assertGreaterEqual(len(p_paras), 2)
        self.assertEqual(len(next(iter(p_sheets.values()))), 2)

        # 6. Zip archive containing CSV + MD over load_inputs_from_sources
        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, "w") as zf:
            zf.writestr("a.csv", b"KhachHang,DoanhThu\nACME,800\nNova,150\n")
            zf.writestr("b.md", md_raw)
        loaded_sheets, meta = app_module.load_inputs_from_sources(
            uploaded_files=[{"filename": "bundle.zip", "content": zip_buf.getvalue()}],
            google_sheet_urls=[],
        )
        self.assertGreaterEqual(len(loaded_sheets), 2)
        self.assertTrue(any(m["type"] == "zip" for m in meta))

    def test_financial_priority_customers_and_kpi_tree(self) -> None:
        csv_bytes = (
            "KhachHang,NhomKhach,DoanhThu,ChiPhi,LoiNhuan,TienDo,TrangThai\n"
            "TapDoan_A,VIP,600,200,400,100%,Hoan thanh\n"
            "CongTy_B,VIP,250,100,150,80%,Dung han\n"
            "CuaHang_C,PhoThong,80,50,30,45%,Cham\n"
            "Shop_D,PhoThong,40,30,10,60%,Dang chay\n"
        ).encode("utf-8")
        boundary = f"----KpiBoundary{uuid4().hex}".encode("ascii")
        payload_json = json.dumps(
            {
                "config": {
                    "agent_mode": "local",
                    "analysis_goal": "priority_customers",
                    "user_prompt": "Lọc khách hàng > 200 VIP",
                }
            }
        ).encode("utf-8")
        body = b"".join([
            b"--", boundary, b"\r\n",
            b'Content-Disposition: form-data; name="payload"\r\n\r\n',
            payload_json, b"\r\n",
            b"--", boundary, b"\r\n",
            b'Content-Disposition: form-data; name="files"; filename="khach_hang_du_an.csv"\r\n',
            b"Content-Type: text/csv\r\n\r\n",
            csv_bytes, b"\r\n",
            b"--", boundary, b"--\r\n",
        ])
        status, _, resp_bytes = invoke_http_handler(
            "POST", "/api/run", body=body, content_type=f"multipart/form-data; boundary={boundary.decode()}"
        )
        self.assertEqual(status, 200)
        res = json.loads(resp_bytes.decode("utf-8"))
        cs = res["company_stats"]
        self.assertEqual(cs["domain_detected"], "priority_customers")
        self.assertEqual(cs["financial_summary"]["total_revenue"], 970.0)
        self.assertEqual(cs["financial_summary"]["total_cost"], 380.0)
        self.assertEqual(cs["financial_summary"]["net_profit"], 590.0)
        self.assertEqual(cs["project_summary"]["total_projects"], 4)
        self.assertEqual(cs["priority_entities"][0]["name"], "TapDoan_A")
        self.assertIn("Nhóm A", cs["priority_entities"][0]["tier"])
        self.assertGreaterEqual(len(cs["kpi_tree"]["branches"]), 3)
        self.assertGreaterEqual(len(cs["classifiers"]), 2)
        self.assertGreaterEqual(len(cs["prompt_matches"]), 2)
        self.assertIn("Cây KPI / Mục tiêu Quản trị (MG)", cs["markdown_report"])
        self.assertEqual(cs["analyst_name"], "Hà Thuỳ Dương")
        self.assertEqual(len(cs["process_steps"]), 7)
        bi = cs["bi_pipeline"]
        self.assertGreaterEqual(len(bi["stage1_intake"]["field_dictionary"]), 5)
        self.assertGreaterEqual(len(bi["stage4_charts"]), 3)
        self.assertGreaterEqual(len(bi["stage5_insights"]), 2)
        self.assertGreaterEqual(len(bi["stage6_solutions"]), 2)

        # Verify all 4 deliverable endpoints (cleaned.xlsx, analysis.xlsx, report.docx, report.html)
        run_id = res["run_id"]
        c_code, _, c_xlsx = invoke_http_handler("GET", f"/api/runs/{run_id}/cleaned.xlsx")
        self.assertEqual(c_code, 200)
        parsed_clean = parse_xlsx_bytes(c_xlsx, "cleaned.xlsx")
        self.assertIn("NhatKy_LamSach", parsed_clean)

        a_code, _, a_xlsx = invoke_http_handler("GET", f"/api/runs/{run_id}/analysis.xlsx")
        self.assertEqual(a_code, 200)
        parsed_ana = parse_xlsx_bytes(a_xlsx, "analysis.xlsx")
        self.assertGreaterEqual(len(parsed_ana), 4)

        d_code, _, d_docx = invoke_http_handler("GET", f"/api/runs/{run_id}/report.docx")
        self.assertEqual(d_code, 200)
        _, docx_paras = parse_docx_bytes(d_docx, "report.docx")
        self.assertTrue(any("Hà Thuỳ Dương" in p for p in docx_paras))


if __name__ == "__main__":
    unittest.main(verbosity=2)

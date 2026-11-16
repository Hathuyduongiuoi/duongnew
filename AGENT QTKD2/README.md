# Hưng Phát WMS — AI Agent Đánh Giá Thị Trường Mở Rộng (AI301 - Đề 04)

Hệ thống AI Agent hỗ trợ Trưởng phòng Phát triển Kinh doanh (Công ty Hưng Phát) đánh giá 4 địa bàn mở rộng từ gói dữ liệu đa nguồn (`.csv`, `.xlsx`, hoặc **Google Sheets**), phát hiện trùng lặp/thiếu/mâu thuẫn dữ liệu, chấm điểm theo bộ tiêu chí có kiểm soát con người (**Human-in-the-Loop**), và xuất báo cáo đề xuất + kế hoạch khảo sát kèm **Nhật ký truy vết nguồn (`CIT-xxx`)**.

## Khởi chạy nhanh (Không cần cài đặt thư viện ngoài)

Yêu cầu: **Python 3.9+** (chỉ dùng thư viện chuẩn Python).

```bash
python3 app.py --open
```

Hoặc nhấp đúp tệp `start_localhost.command` trên macOS để tự mở trình duyệt tại `http://localhost:8000`.

## Chạy Bộ Kiểm Thử Tự Động (3 kịch bản + Kiểm thử HTTP)

```bash
python3 scripts/run_self_tests.py
```

Tạo lại 3 bộ dữ liệu mẫu (`.xlsx` và `.csv`):

```bash
python3 scripts/generate_samples.py
```

## Cấu trúc dự án

- `app.py` — Web server HTTP & REST API (phục vụ giao diện Web và xử lý upload CSV/XLSX/Google Sheets).
- `agent/orchestrator.py` — Hybrid AI Agent Orchestrator (hỗ trợ **Gemini Function Calling**, **OpenAI Tool Calling**, và **Local ReAct Engine**).
- `agent/parsers.py` — Trình đọc `.csv`, `.xlsx`, tải Google Sheets qua URL và Smart Schema Mapper.
- `agent/skills/` — 4 kỹ năng nghiệp vụ phối hợp:
  1. `skill_ingest_normalize.py` — Tiền xử lý, chuẩn hóa kỳ thống kê & khử trùng lặp nguồn.
  2. `skill_conflict_gap.py` — Đối chiếu chéo, phát hiện thiếu thông tin/mâu thuẫn & cổng HITL #1.
  3. `skill_evaluate_rank.py` — Chấm điểm bộ tiêu chí, kiểm tra Hard Gate, phát hiện ranh giới & xếp hạng.
  4. `skill_proposal_survey.py` — Sinh Báo cáo Đề xuất & Kế hoạch khảo sát tiếp theo (tách bạch Dữ liệu vs Suy luận).
- `agent/audit.py` — Nhật ký truy vết dữ liệu, quy tắc & trích dẫn nguồn (`audit_logs/`).
- `web/` — Giao diện Web hiển thị trực tiếp Sơ đồ To-Be, Bảng so sánh, HITL, Báo cáo & Audit Log.
- `scripts/` — Sinh mẫu (`generate_samples.py`), tự kiểm thử 11 test case (`run_self_tests.py`), và xuất Word `.docx` (`export_docx.py`).
- `data/samples/` — 3 bộ dữ liệu test mẫu (`case1_thong_thuong`, `case2_thieu_mau_thuan`, `case3_ranh_gioi_quy_tac`).
- `docs/` — Báo cáo hoàn chỉnh Task 1 & Task 2 ([Task 1 `.md`](docs/BaoCao_Task1_PhanTich_ThietKe.md) / `.docx`, [Task 2 `.md`](docs/BaoCao_Task2_GiaiPhap_KiemThu.md) / `.docx`).
- `start_localhost.command` — Trình khởi chạy nhanh Web App trên macOS.


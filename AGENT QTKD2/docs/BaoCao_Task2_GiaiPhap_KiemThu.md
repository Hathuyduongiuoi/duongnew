# BÁO CÁO TASK 2: GIẢI PHÁP KỸ THUẬT, KỸ NĂNG AGENT & KIỂM THỬ (AI301 — ĐỀ DỰ ÁN 04)

---

## 1. Nền tảng, Công nghệ Triển khai & Kiến trúc Mã nguồn

Giải pháp được xây dựng thành **Ứng dụng Web hoàn chỉnh** bằng Python 3.9+ (không phụ thuộc thư viện cài đặt phức tạp ngoài chuẩn, chạy ngay bằng `python3 app.py` trên cổng `8000`) kết hợp giao diện Web HTML/CSS/JS hiện đại.

| Thành phần | Tệp mã nguồn | Vai trò chính |
|---|---|---|
| **Web Server & REST API** | [`app.py`](file:///Users/hathuyduong/AGENT%20QTKD2/app.py) | Phục vụ giao diện Web, nhận file upload (`multipart/form-data`), link Google Sheets, điều phối endpoint `/api/inspect-inputs`, `/api/run`, `/api/hitl/resolve`, `/api/hitl/boundary-signoff`, `/api/runs/<id>/audit`, `/api/runs/<id>/report.md`. |
| **Parsers & Smart Schema Mapper** | [`agent/parsers.py`](file:///Users/hathuyduong/AGENT%20QTKD2/agent/parsers.py) | Đọc `.csv` (tự nhận diện bảng mã & dấu phân tách), đọc/ghi `.xlsx` thuần Python (`zipfile` + `xml.etree.ElementTree`), tải Google Sheets qua URL (`export?format=xlsx` hoặc `csv`), tự động nhận diện và map tên sheet/cột tiếng Việt & tiếng Anh vào 6 bảng chuẩn. |
| **Hybrid Agent Orchestrator** | [`agent/orchestrator.py`](file:///Users/hathuyduong/AGENT%20QTKD2/agent/orchestrator.py) & [`agent/llm_client.py`](file:///Users/hathuyduong/AGENT%20QTKD2/agent/llm_client.py) | Điều phối vòng lặp **Tool Calling** hỗ trợ cả **Google Gemini API** (`generateContent` + `functionDeclarations`), **OpenAI API** (`chat/completions` + `tools`) và **Local ReAct Engine** (chạy ngoại tuyến không cần API Key). |
| **4 Kỹ năng Nghiệp vụ Phối hợp** | [`agent/skills/`](file:///Users/hathuyduong/AGENT%20QTKD2/agent/skills) | Thực thi 4 kỹ năng chuyên biệt qua 5 Tools có chữ ký JSON Schema rõ ràng. |
| **Audit & Citation Logger** | [`agent/audit.py`](file:///Users/hathuyduong/AGENT%20QTKD2/agent/audit.py) | Ghi nhận tuần tự từng suy nghĩ Agent, lời gọi công cụ, kiểm tra quy tắc và cấp mã trích dẫn `CIT-xxx`, lưu file JSON tại `audit_logs/`. |
| **Giao diện Web Trực quan** | [`web/index.html`](file:///Users/hathuyduong/AGENT%20QTKD2/web/index.html), [`web/styles.css`](file:///Users/hathuyduong/AGENT%20QTKD2/web/styles.css), [`web/app.js`](file:///Users/hathuyduong/AGENT%20QTKD2/web/app.js) | Hiển thị sơ đồ quy trình To-Be trực tiếp, vùng tải CSV/XLSX/Google Sheet, cổng HITL tương tác, Bảng so sánh có mã nguồn `CIT-xxx`, Báo cáo đề xuất, Kế hoạch khảo sát và Audit Timeline. |

---

## 2. Chi tiết 4 Kỹ năng Nghiệp vụ Phối hợp & Bằng chứng Tool Calling

Trong mỗi phiên đánh giá, AI Agent điều phối **4 kỹ năng nghiệp vụ** thông qua **5 công cụ (`TOOL_SCHEMAS`)**:

1. **Công cụ đọc đầu vào (`tool_read_uploaded_sources`):**
   - Nạp file CSV/XLSX/Google Sheet, phân loại từng sheet vào 6 bảng chuẩn (`market_reports`, `competitors`, `customer_feedback`, `solution_catalog`, `deployment_capability`, `evaluation_criteria`) và áp dụng tuỳ chọn sửa ánh xạ từ người dùng nếu có.
2. **Kỹ năng 1 — Tiền xử lý & Chuẩn hóa (`tool_normalize_and_deduplicate` trong [`skill_ingest_normalize.py`](file:///Users/hathuyduong/AGENT%20QTKD2/agent/skills/skill_ingest_normalize.py)):**
   - Chuẩn hóa tên địa bàn (loại tiền tố `TP.`, `Thành phố`, `Tỉnh` không phân biệt dấu).
   - Chuẩn hóa kỳ thống kê (`Q4/2025`, `Quý 4 2025` → `2025-Q4`; quy đổi `quarter_flow` × 4 khi có cờ luồng quý).
   - **Khử trùng lặp nguồn:** Loại bỏ các bản ghi trùng `origin_source_id` hoặc trùng `(địa bàn, kỳ, nguồn, giá trị)` và ghi nhận vào `dedup_log`.
   - Cấp mã trích dẫn duy nhất `CIT-001`, `CIT-002`, ... trỏ đúng tới `(tên file, sheet, số dòng, nguồn, kỳ)`.
3. **Kỹ năng 2 — Đối chiếu & Phát hiện Mâu thuẫn (`tool_detect_gaps_and_conflicts` trong [`skill_conflict_gap.py`](file:///Users/hathuyduong/AGENT%20QTKD2/agent/skills/skill_conflict_gap.py)):**
   - Kiểm tra độ phủ 4 địa bàn và các trường trọng yếu trên 6 bảng.
   - Phát hiện **mâu thuẫn số liệu** giữa các nguồn (`>= 20%` độ lệch quy mô thị trường hoặc `>= 4.0/10` điểm chênh lệch yêu cầu hỗ trợ tại chỗ), lệch kỳ thống kê liên địa bàn, và cảnh báo quá tải năng lực tại chỗ.
   - Ra quyết định cổng **`Có đủ dữ liệu không?`**: nếu còn lỗ hổng/mâu thuẫn `HIGH`, dừng tại trạng thái `AWAITING_HUMAN_STAGE3` để con người chọn nguồn tin cậy hoặc bổ sung dữ liệu rồi chạy lại Bước 2.
4. **Kỹ năng 3 — Đánh giá Đa tiêu chí, Quy tắc Loại & Ranh giới (`tool_evaluate_criteria_and_rules` trong [`skill_evaluate_rank.py`](file:///Users/hathuyduong/AGENT%20QTKD2/agent/skills/skill_evaluate_rank.py)):**
   - Tính 4 nhóm tiêu chí trên thang 10: `Quy mô thị trường` (25%), `Product-Market Fit` (30%, ngưỡng bắt buộc `>= 6.0`), `Khả năng triển khai & Hỗ trợ tại chỗ` (30%, ngưỡng bắt buộc `>= 6.0` và `nhu cầu tại chỗ <= năng lực tối đa`), `Thuận lợi cạnh tranh` (15%).
   - Áp dụng ngưỡng loại **Hard Gate**, đánh dấu **Ranh giới (`BOUNDARY_PASS`)** khi `min_threshold <= score <= min_threshold + 0.25`, kiểm tra sát điểm hạng `#2` vs `#3` (`<= 0.20`), và tuyệt đối không bịa số liệu cho địa bàn thiếu dữ liệu.
5. **Kỹ năng 4 — Tổng hợp Báo cáo & Kế hoạch Khảo sát (`tool_generate_proposal_and_survey_plan` trong [`skill_proposal_survey.py`](file:///Users/hathuyduong/AGENT%20QTKD2/agent/skills/skill_proposal_survey.py)):**
   - Xuất báo cáo cho Trưởng phòng PTKD, phân tách rõ 2 phần **`[Số liệu trong tài liệu]`** và **`[Suy luận của Agent]`**, nêu rõ vì sao chưa ưu tiên các địa bàn còn lại hoặc các **điều kiện cần bổ sung** nếu chưa đủ 2 địa bàn.
   - Tạo Kế hoạch khảo sát chi tiết: *Nhóm khách cần tiếp cận*, *Thông tin cần xác minh*, *Người phụ trách*, *Thời hạn* và *Tiêu chí Go/No-Go*.

### Cấu trúc Nhật ký Truy vết (`audit_logs/HP-*.json`)
Mỗi lần chạy tạo một tệp JSON lưu giữ:
- `events`: Chuỗi hành động theo thứ tự thời gian (`seq`, `timestamp`, `stage`, `actor` = `AGENT`/`SKILL`/`TOOL`/`RULE`/`HUMAN`, `action`, `tool_name`, `tool_args`, `tool_result_summary`, `citations`).
- `rules_trace`: Mọi quy tắc nghiệp vụ đã chạy (`rule_id`, `location`, `inputs`, `threshold`, `outcome`).
- `citations`: Từ điển tra cứu ngược từng mã `CIT-xxx` về đúng tệp, sheet, số dòng và giá trị gốc.

---

## 3. Bộ 3 Kịch bản Tự Kiểm thử & Kết quả Thực tế

Bộ kiểm thử tự động tại [`scripts/run_self_tests.py`](file:///Users/hathuyduong/AGENT%20QTKD2/scripts/run_self_tests.py) (11 bài test đơn vị, ánh xạ cột, khử trùng lặp nguồn, định tuyến API key & tích hợp HTTP E2E) cùng 3 bộ dữ liệu mẫu tại [`data/samples/`](file:///Users/hathuyduong/AGENT%20QTKD2/data/samples) đều đạt kết quả **11/11 PASSED** (`python3 scripts/run_self_tests.py`).

### Kịch bản 1: Trường hợp Thông thường (`case1_thong_thuong.xlsx`)
- **Thiết kế bẫy bối cảnh:** `Hải Phòng` bị lặp báo cáo nguồn `SRC-RVN-2025` (`MT-03` và `MT-04`), có quy mô lớn nhất (`380 tỷ`) và quan tâm cao (`8.5/10`), nhưng yêu cầu trực tại chỗ `9.0/10 > năng lực tối đa 5.0/10`. `Cần Thơ` dùng số liệu luồng quý (`52.5 tỷ/quý` tại `2025-Q3`) và cần kho lạnh GACP/cân điện tử (`Chưa hỗ trợ`).
- **Kết quả Agent quan sát được:**
  - Khử trùng lặp thành công **1 bản ghi** (`MT-04` bị loại, giữ `MT-03`); quy đổi số liệu quý Cần Thơ `52.5 × 4 = 210 tỷ`.
  - **Đề xuất Top 2:** `#1 Bình Dương (8.4/10)` và `#2 Đà Nẵng (7.62/10)` — trạng thái `COMPLETED` (`SELECTED_2_LOCATIONS`).
  - **Chưa ưu tiên / Loại:** `Hải Phòng` (tổng điểm `6.03`, quy mô `10.0/10` nhưng **`DISQUALIFIED`** do điểm Triển khai bị hạ còn `1.5/10 < 6.0` vì quá tải tại chỗ); `Cần Thơ` (tổng điểm `4.62`, **`DISQUALIFIED`** do `Product Fit = 1.5/10 < 6.0`).

### Kịch bản 2: Thiếu dữ liệu & Mâu thuẫn (`case2_thieu_mau_thuan.xlsx`)
- **Thiết kế tình huống:** `Nghệ An` thiếu hoàn toàn Phản hồi khách hàng & chỉ số Năng lực triển khai; `Đà Nẵng` mâu thuẫn 50% quy mô thị trường (`290 tỷ` vs `145 tỷ` cùng kỳ `2025-Q4`) và mâu thuẫn yêu cầu hỗ trợ tại chỗ (`3.0/10` vs `9.0/10`).
- **Kết quả Agent quan sát được:**
  - Ở lần chạy đầu, Agent dừng đúng tại Bước 2 với trạng thái `AWAITING_HUMAN_STAGE3` (`enough_data = False`, `hitl_required = True`), không tạo bảng xếp hạng giả.
  - **Nhánh A (Con người chọn chạy với phần dữ liệu hợp lệ hiện có, không bổ sung):** Agent đánh giá đúng `Bình Dương`, giữ nguyên trạng thái `INSUFFICIENT_DATA` cho `Nghệ An` và `Đà Nẵng` (không tự bịa số liệu), kết luận **`INSUFFICIENT_EVIDENCE` (CHƯA ĐỦ CĂN CỨ CHỌN ĐỦ 2 ĐỊA BÀN)** kèm điều kiện cần bổ sung.
  - **Nhánh B (Con người chọn nguồn tin cậy xử lý mâu thuẫn `Đà Nẵng` qua HITL):** Quay lại Bước 2 và chọn được `['Bình Dương', 'Đà Nẵng']`.

### Kịch bản 3: Tại Ranh giới Quy tắc (`case3_ranh_gioi_quy_tac.xlsx`)
- **Thiết kế tình huống:** `Đà Nẵng` có `Product Fit = 6.00/10` và `Năng lực triển khai = 6.00/10` (đúng bằng ngưỡng `>= 6.0`). `Hải Phòng` có `Product Fit = 5.95/10` (thấp hơn ngưỡng đúng `0.05` điểm). `Khánh Hòa` đạt `6.54/10` sát sát `Đà Nẵng`.
- **Kết quả Agent quan sát được:**
  - `Đà Nẵng` đạt **`BOUNDARY_PASS`** ở cả 2 tiêu chí cứng (`6.0/10`) và xếp `#2 (6.67/10)`.
  - `Hải Phòng` bị loại chính xác (**`DISQUALIFIED`**, dù điểm tổng `7.51`) vì `Product Fit = 5.95 < 6.0` (`FAIL`).
  - Hệ thống phát hiện cảnh báo sát ranh giới giữa `#2 Đà Nẵng (6.67)` và `#3 Khánh Hòa (6.54)` (chênh lệch `0.13 <= 0.20`), chuyển trạng thái `COMPLETED_WITH_HITL_REVIEW` và yêu cầu Trưởng phòng ký duyệt tại HITL #2 (`COMPLETED_APPROVED` sau khi phê duyệt).

---

## 4. Hướng dẫn Vận hành Trực tiếp tại Buổi Thi

1. **Khởi động hệ thống:**
   ```bash
   python3 app.py --open
   ```
   Hoặc nhấp đúp tệp `start_localhost.command` để mở `http://localhost:8000`. Tại màn hình giới thiệu, nhấn **"Bắt đầu quy trình"** (hoặc **"Chạy thử Mẫu 1"**) để vào bảng điều khiển.
2. **Nạp bộ dữ liệu mới của giảng viên:**
   - Chọn tab **📁 File** để kéo thả/chọn các file `.csv` hoặc `.xlsx`, **HOẶC** chuyển sang tab **🔗 Sheet** để dán link Google Sheets (đặt quyền chia sẻ *Bất kỳ ai có đường liên kết → Người xem*) và nhấn **Tải**.
3. **Kiểm tra cấu trúc cột (nếu bộ thi đổi tên sheet/cột):**
   - Nhấn **"🗺️ Map cột"** để rà soát 6 bảng chuẩn đã nhận diện và chỉnh lại ánh xạ sheet hoặc từng cột nếu cần.
4. **Chọn chế độ AI Agent & Chạy:**
   - Nhấn **"Cài đặt"** trên thanh tiêu đề để chọn **Local ReAct** (luôn chạy ổn định kể cả mất mạng) hoặc **Google Gemini API / OpenAI API**, và điều chỉnh ngưỡng/trọng số nếu cần.
   - Nhấn **"CHẠY AGENT"** (có thể bấm **"Chi tiết ▾"** nếu muốn mở xem danh sách 5 bước).
5. **Giải thích & Xử lý HITL khi bảo vệ:**
   - Nếu bộ dữ liệu thi có lỗ hổng hoặc mâu thuẫn, thẻ **Duyệt Thiếu / Lệch** (HITL #1) hoặc **Duyệt Sát Ranh Giới** (HITL #2) sẽ tự động bật ở cột trái để con người chọn nguồn hoặc bổ sung.
   - Trình bày kết quả tại tab **🏆 Kết quả** (bấm vào mã `[CIT-xxx]` để chứng minh truy vết tới từng dòng file gốc và mở **"Xem chi tiết 4 địa bàn ▾"** khi cần), xem kế hoạch tại tab **📝 Đề xuất**, kiểm tra lỗi tại tab **🧹 Lỗi DL**, xem Tool I/O tại tab **🛠️ Nhật ký**, và bấm nút **`Xuất ▾`** → **Báo cáo .MD** hoặc **Audit .JSON** để nộp.


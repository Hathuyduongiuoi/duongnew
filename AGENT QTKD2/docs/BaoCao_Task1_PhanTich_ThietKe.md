# BÁO CÁO TASK 1: PHÂN TÍCH QUY TRÌNH & THIẾT KẾ AI AGENT (AI301 — ĐỀ DỰ ÁN 04)

**Đề tài:** Đánh giá thị trường để mở rộng kinh doanh cho Công ty Hưng Phát (Giải pháp Quản lý Kho cho Chuỗi Bán lẻ)

---

## 1. Phân tích Quy trình Hiện tại (As-Is) & Các Vấn đề Cốt lõi

### 1.1. Mô tả quy trình hiện tại (As-Is)
1. **Tiếp nhận hồ sơ thô:** Nhân viên Phát triển Kinh doanh thu thập rời rạc các báo cáo thị trường, thông tin đối thủ và ghi chép phản hồi khách hàng từ nhiều nguồn và thời điểm khác nhau.
2. **Đọc và tổng hợp thủ công:** Nhân viên tự đọc văn bản, trích lọc số liệu quy mô thị trường và ghép danh sách khách hàng tiềm năng bằng bảng tính/tài liệu cá nhân.
3. **Chấm chọn cảm tính theo quy mô:** Địa bàn có tổng quy mô hoặc số chuỗi quan tâm cao thường được ưu tiên đưa vào danh sách đề xuất mà chưa kiểm tra chéo với Danh mục giải pháp và Khả năng triển khai tại chỗ.
4. **Bàn giao cho Trưởng phòng Phát triển Kinh doanh:** Gửi báo cáo tóm tắt kết luận để Trưởng phòng chọn 2 địa bàn khảo sát trước khi trình Ban Giám đốc — nhưng không có hồ sơ truy vết để kiểm tra lại nguồn gốc từng con số.

### 1.2. Xác định ít nhất 3 vấn đề trong bối cảnh và ảnh hưởng cụ thể

| STT | Vấn đề hiện tại trong bối cảnh | Nguyên nhân gốc rễ | Ảnh hưởng cụ thể đến quyết định kinh doanh |
|---|---|---|---|
| **1** | **Dùng khác kỳ thống kê & lặp số liệu từ cùng một nguồn** | Nhân viên ghép các báo cáo công bố ở các quý/năm khác nhau (ví dụ số liệu 1 quý vs cả năm) và không đối chiếu `mã nguồn gốc`, dẫn đến trích lại cùng một báo cáo sơ cấp từ các tài liệu thứ cấp. | **Làm phồng quy mô thị trường ảo (double-counting)** tại một số địa bàn, khiến bảng so sánh bị méo mó và chọn sai địa bàn ưu tiên ngay từ vòng sàng lọc. |
| **2** | **Nhấn mạnh quy mô thị trường mà bỏ qua mức độ khớp sản phẩm (Product-Market Fit)** | Đọc báo cáo thị trường tách rời với Danh mục giải pháp hiện có và nhu cầu tính năng thực tế trong phản hồi khách hàng. | **Lãng phí nguồn lực khảo sát** vào địa bàn có quy mô lớn nhưng khách hàng đòi hỏi tính năng chưa hỗ trợ (ví dụ kho lạnh GACP, cân công nghiệp), làm tỷ lệ chuyển đổi sau khảo sát thấp. |
| **3** | **Khách quan tâm nhiều nhưng yêu cầu hỗ trợ tại chỗ vượt năng lực triển khai** | Chưa đối chiếu yêu cầu onsite/SLA của chuỗi bán lẻ với số lượng kỹ sư và giới hạn triển khai của Hưng Phát (trong khi đội triển khai chỉ đủ cho **1 đợt mở rộng**). | **Nguy cơ vỡ SLA và quá tải đội triển khai** nếu chọn nhầm địa bàn đòi hỏi trực 24/7 ở xa trụ sở, ảnh hưởng uy tín khi triển khai thực tế. |
| **4** | **Thiếu quy trình phát hiện mâu thuẫn & thiếu khả năng kiểm tra lại (Audit Trail)** | Tổng hợp thủ công không lưu dấu liên kết giữa kết luận với dòng dữ liệu gốc, cũng không có bước đánh dấu lỗ hổng thông tin hay mâu thuẫn giữa các nguồn. | Trưởng phòng và Ban Giám đốc **không thể kiểm chứng căn cứ số liệu**, dễ phát sinh rủi ro ra quyết định trên dữ liệu thiếu hoặc bị suy diễn cảm tính. |

---

## 2. Quy trình Đề xuất (To-Be) & Phân công Trách nhiệm

Quy trình To-Be được thiết kế theo 5 giai đoạn khép kín với cổng **Kiểm soát con người (Human-in-the-Loop)** và **Nhật ký truy vết (Audit Log)** xuyên suốt (khớp với Sơ đồ Quy trình Đánh giá Thị trường Tự động):

| Giai đoạn | Đầu vào (Input) | Công việc thực hiện (Activities) | Đầu ra (Output) | Người / Bộ phận chịu trách nhiệm |
|---|---|---|---|---|
| **1. Nạp Dữ liệu Đầu vào** | 6 nhóm dữ liệu: Tài liệu thị trường, Hồ sơ đối thủ, Phản hồi khách hàng, Danh mục giải pháp, Khả năng triển khai, Bộ tiêu chí (định dạng `.csv`, `.xlsx` hoặc link **Google Sheets**). | Nạp gói dữ liệu vào hệ thống; kiểm tra & xác nhận ánh xạ tên sheet/cột vào 6 bảng chuẩn. | Gói dữ liệu đã phân loại bảng & cấu hình bộ tiêu chí. | **Chuyên viên PTKD / Nhóm Nghiên cứu Thị trường** |
| **2. AI Agent — Bước 1: Tiền xử lý & Chuẩn hóa** | 6 bảng dữ liệu thô đã nạp. | Đọc toàn bộ bản ghi, chuẩn hóa tên địa bàn, chuẩn hóa kỳ thống kê (quý/năm), **khử bản ghi lặp từ cùng nguồn gốc**, gắn mã trích dẫn `CIT-xxx` cho từng dòng. | Dữ liệu sạch đã chuẩn hóa; Nhật ký khử trùng lặp; Chuỗi trích dẫn `CIT-xxx`. | **AI Agent (Kỹ năng 1: Ingestion & Normalization)** |
| **3. AI Agent — Bước 2: Đối chiếu & Phát hiện Mâu thuẫn** | Dữ liệu đã chuẩn hóa của 4 địa bàn + ngưỡng kiểm tra mâu thuẫn. | Đối chiếu chéo giữa 6 bảng theo từng địa bàn; phát hiện **thông tin thiếu** (missing), **mâu thuẫn số liệu** giữa các nguồn (conflict), lệch kỳ và cảnh báo quá tải triển khai. Kiểm tra cổng **`Có đủ dữ liệu không?`** | Sổ đăng ký lỗ hổng/mâu thuẫn + Quyết định cổng: **CÓ** (qua Bước 3) hoặc **KHÔNG** (dừng chờ HITL #1). | **AI Agent (Kỹ năng 2: Conflict & Gap)** + **Chuyên viên/Quản lý PTKD (khi HITL #1 kích hoạt)** |
| **4. AI Agent — Bước 3: Đánh giá & Xếp hạng Địa bàn** | Dữ liệu đã qua cổng kiểm tra + Bộ tiêu chí (`BoTieuChi`). | Tính điểm từng tiêu chí (`Quy mô`, `Product Fit`, `Khả năng triển khai`, `Cạnh tranh`), kiểm tra **quy tắc loại bắt buộc (Hard Gate)** và **biên ranh giới (Boundary / Near-Tie)**, xuất Bảng so sánh gắn mã `CIT-xxx`. | Bảng so sánh 4 địa bàn có trích dẫn; Top 2 địa bàn đề xuất (hoặc kết luận *Chưa đủ căn cứ*); cảnh báo ranh giới (HITL #2). | **AI Agent (Kỹ năng 3: Evaluation & Ranking)** + **Trưởng phòng PTKD (duyệt HITL #2)** |
| **5. Kết quả Đầu ra & Bàn giao** | Kết quả xếp hạng + Sổ lỗ hổng/ranh giới + Audit Log. | Tạo **Báo cáo Đề xuất** (tách bạch `[Dữ liệu tài liệu]` vs `[Suy luận Agent]`), lập **Kế hoạch khảo sát tiếp theo** (nhóm khách, thông tin xác minh, người phụ trách) và xuất toàn bộ Nhật ký truy vết. | Báo cáo đề xuất trình Trưởng phòng; Kế hoạch khảo sát; File `.md` / `.json` / Giao diện Web trực quan. | **AI Agent (Kỹ năng 4: Proposal & Survey Plan)** → **Trưởng phòng PTKD** → **Ban Giám đốc** |

---

## 3. Các Bước Giao cho AI Agent & Lý do Lựa chọn

Hệ thống giao **4 bước cốt lõi** (tối thiểu yêu cầu 3 bước) cho AI Agent tự động thực hiện qua cơ chế **Tool Calling** có kiểm soát:

1. **Bước 1 — Tiền xử lý, Chuẩn hóa kỳ & Khử trùng lặp nguồn (`Skill 1`):**
   - *Lý do lựa chọn:* Con người rất dễ bỏ sót dòng trùng khi nguồn sơ cấp được trích dẫn lại ở tài liệu khác hoặc khác định dạng kỳ (`Q4/2025` vs `2025-Q4`, số liệu quý vs năm). AI Agent kết hợp quy tắc chuẩn hóa và mã nguồn gốc giúp loại trùng lặp nhất quán 100% và lưu vết mọi dòng bị loại.
2. **Bước 2 — Đối chiếu chéo & Phát hiện Thông tin thiếu / Mâu thuẫn (`Skill 2`):**
   - *Lý do lựa chọn:* Cần đối chiếu đồng thời 4 địa bàn trên 5 bảng dữ liệu có quan hệ chéo (Thị trường – Khách hàng – Giải pháp – Triển khai – Đối thủ). Agent rà soát máy móc không bỏ sót ô trống, phát hiện ngay độ lệch số liệu vượt ngưỡng giữa 2 báo cáo cùng kỳ hoặc mâu thuẫn nhu cầu tại chỗ.
3. **Bước 3 — Chấm điểm đa tiêu chí, Kiểm tra Hard Gate & Ranh giới (`Skill 3`):**
   - *Lý do lựa chọn:* Đảm bảo tính khách quan theo đúng trọng số và ngưỡng loại trong `BoTieuChi` (ngăn chặn thiên kiến chỉ nhìn quy mô thị trường), áp dụng chính xác phép so sánh biên (`>= 6.0` vs `5.95`) và gắn trích dẫn `CIT-xxx` tự động tới từng ô điểm.
4. **Bước 4 — Tổng hợp Báo cáo Đề xuất & Kế hoạch Khảo sát (`Skill 4`):**
   - *Lý do lựa chọn:* Tổng hợp tự động các phát hiện rủi ro, lỗ hổng cần xác minh và danh sách nhóm khách hàng từ bảng dữ liệu thành Báo cáo điều hành chuẩn mực trong vài giây, đảm bảo mọi nhận định đều bám dữ liệu thật.

---

## 4. Điểm Kiểm soát Con người (Human-in-the-Loop), Điều kiện Chuyển & Cách Phát hiện Sai sót

### 4.1. Điểm kiểm soát con người #1: Cổng Xác minh Dữ liệu Thiếu & Mâu thuẫn (Tại Bước 2 — Stage 3)
- **Điều kiện chuyển xử lý (Escalation Trigger):**
  - Có từ **1 mâu thuẫn mức `HIGH`** trở lên chưa giải quyết (ví dụ: chênh lệch quy mô thị trường giữa 2 nguồn cùng địa bàn `>= 20%`, hoặc phản hồi khách hàng lệch nhau `>= 4.0/10` điểm về yêu cầu hỗ trợ tại chỗ).
  - Hoặc có **thiếu dữ liệu trọng yếu (`HIGH`)** (thiếu báo cáo thị trường, thiếu phản hồi khách hàng, hoặc thiếu đánh giá năng lực triển khai) khiến số địa bàn đủ dữ liệu sạch `< 2`.
- **Hành động của Con người:**
  - Chọn nguồn đáng tin cậy hơn trong các ứng viên mâu thuẫn, hoặc tải bổ sung sheet/nhập dữ liệu đã xác minh rồi kích hoạt **Quay lại Bước 2 (Re-run)**; hoặc xác nhận chạy tiếp với phần dữ liệu hợp lệ (Agent bắt buộc ghi nhãn `CHƯA ĐỦ CĂN CỨ` và không tự bịa số liệu bù).
- **Cách phát hiện kết quả sai:**
  - Đối chiếu danh sách `issues` trong tab *Mâu thuẫn & Chuẩn hóa* với dữ liệu thô; kiểm tra xem Agent có bỏ qua dòng bị lệch kỳ khác năm hay vô tình khử nhầm hai nguồn độc lập khác `origin_source_id` hay không.

### 4.2. Điểm kiểm soát con người #2: Cổng Phê duyệt Ranh giới Quy tắc & Near-Tie (Tại Bước 3 — Stage 4)
- **Điều kiện chuyển xử lý (Escalation Trigger):**
  - Địa bàn được chọn có tiêu chí bắt buộc đạt **sát ranh giới** (`min_threshold <= score <= min_threshold + boundary_margin`, ví dụ `Product Fit = 6.00` so với ngưỡng `>= 6.0`).
  - Hoặc khoảng cách điểm tổng giữa hạng `#2` và hạng `#3` nhỏ hơn hoặc bằng biên dung sai (`<= 0.20` điểm).
  - Hoặc kết luận cuối cùng là `INSUFFICIENT_EVIDENCE` (không đủ 2 địa bàn đạt chuẩn).
- **Hành động của Con người:**
  - Trưởng phòng PTKD xem bảng đối chiếu chi tiết, quyết định **Phê duyệt Top 2** kèm yêu cầu xác minh SLA trong khảo sát, hoặc **Điều chỉnh chọn địa bàn #3**, hoặc **Tạm hoãn** để thu thập thêm dữ liệu; quyết định được ký lưu vào Audit Log.
- **Cách phát hiện kết quả sai:**
  - Kiểm tra bảng **Nhật ký quy tắc (`rules_trace`)**: đối chiếu `raw_score` với ngưỡng quy định; kiểm tra cột `[Số liệu trong tài liệu]` đối lập với `[Suy luận Agent]`, bấm vào mã `[CIT-xxx]` để đối chiếu giá trị gốc với file CSV/XLSX/Google Sheet nguồn nhằm phát hiện mọi sai lệch hoặc suy diễn không có căn cứ.

---

## 5. Bản Thiết kế Hệ thống (Mục tiêu – Đầu vào – Quy trình – Đầu ra) & Kiến trúc Lựa chọn

### 5.1. Khung thiết kế
- **Mục tiêu (Goal):** Xây dựng AI Agent có khả năng tự động đánh giá 4 địa bàn mở rộng cho Công ty Hưng Phát theo bộ tiêu chí minh bạch, phát hiện trùng lặp/thiếu/mâu thuẫn dữ liệu, đề xuất 2 địa bàn tối ưu (hoặc nêu rõ điều kiện bổ sung nếu chưa đủ căn cứ) và lập kế hoạch khảo sát chi tiết kèm Nhật ký truy vết kiểm tra lại được 100%.
- **Đầu vào (Input):**
  - File `.csv`, `.xlsx` (nhiều file hoặc 1 workbook nhiều sheet) hoặc đường link **Google Sheets** (tải tự động toàn bộ các tab).
  - 6 bảng dữ liệu nghiệp vụ: `ThiTruong`, `DoiThu`, `PhanHoiKhachHang`, `DanhMucGiaiPhap`, `KhaNangTrienKhai`, `BoTieuChi`.
  - Tham số cấu hình quy tắc (trọng số, ngưỡng Fit/Triển khai, % lệch mâu thuẫn, biên ranh giới) và tùy chọn LLM API Key.
- **Quy trình (Process):**
  - Orchestrator điều phối vòng lặp gọi công cụ (**Tool Calling**) qua 4 Kỹ năng nghiệp vụ tuần tự: `Read Sources` → `Skill 1 (Ingest & Normalize)` → `Skill 2 (Conflict & Gap + HITL Gate #1)` → `Skill 3 (Evaluate, Hard Gates, Boundary Check + HITL Gate #2)` → `Skill 4 (Proposal & Survey Plan)`.
  - Mọi thao tác đọc dữ liệu, loại trùng, kiểm tra quy tắc và tương tác con người đều ghi nhận tức thời vào `AuditLogger`.
- **Đầu ra (Output):**
  - Hiển thị trực tiếp trên **Giao diện Web**: Sơ đồ quy trình trực quan, Bảng so sánh 4 địa bàn có mã trích dẫn `CIT-xxx`, Thẻ phân tích tách bạch `Số liệu tài liệu` vs `Suy luận Agent`, Báo cáo đề xuất cho Trưởng phòng, Kế hoạch khảo sát tiếp theo, và Nhật ký truy vết (hỗ trợ xuất `.md`, `.json`, và in PDF).

### 5.2. Kiến trúc lựa chọn: Hybrid Tool-Calling Agent
Hệ thống chọn kiến trúc **Hybrid Tool-Calling Agent** trên nền tảng Python Web App:
- **Lớp Điều phối (Agent Orchestrator):** Hỗ trợ linh hoạt **2 chế độ thực thi trên cùng bộ Tool Schema**:
  1. *Live LLM Function Calling* (Google Gemini API / OpenAI API): Mô hình AI tự quyết định tuần tự gọi các tool và tổng hợp nhận định điều hành.
  2. *Local ReAct Tool-Calling Engine*: Bộ lập kế hoạch cục bộ chạy không cần API Key/Internet, thực thi đúng vòng lặp `Thought → Tool Call → Observation → Branching`.
- **Lớp Công cụ Nghiệp vụ Tất định (Deterministic Skill Tools):** Toàn bộ tính toán số học, khử trùng lặp, so khớp ranh giới và gắn trích dẫn `CIT-xxx` do các hàm Python kiểm chứng đảm nhiệm — **loại bỏ hoàn toàn rủi ro LLM bịa số liệu hoặc tính sai điểm**.
- **Lớp Nạp Dữ liệu Đa định dạng (Zero-dependency Parsers):** Đọc trực tiếp `.csv`, `.xlsx` (ZIP+XML thuần Python) và xuất Google Sheets không phụ thuộc thư viện nặng, đảm bảo tính ổn định tuyệt đối khi chấm thi trực tiếp.


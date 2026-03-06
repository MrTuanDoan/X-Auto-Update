# Twitter-Telegram AI Pipeline (Claude Code Edition)

Hệ thống tự động hóa toàn diện từ việc đọc Tweet, suy luận tạo Use Case thực tiễn bằng AI (qua Claude CLI), đẩy tài liệu lên GitHub, và phê duyệt 2 lớp qua Telegram Bot trước khi đăng bài Twitter.

Tài liệu này được xây dựng dựa trên bản phân tích kiến trúc: `scaffold-20260307-034500-twitter-telegram-pipeline.md`.

---

## 🏗️ Kiến Trúc Hệ Thống (System Pipeline)

 Hệ thống vận hành theo chu trình 7 bước (State Machine) thông qua file `telegram_twitter_orchestrator.py`:

1. **Telegram Trigger:** Người dùng nhắn lệnh `/scan` cho Bot Telegram.
2. **Twitter Fetch & Select:** Bot dùng Playwright mở trình duyệt ẩn danh phía background để kéo (scrape) các bài post mới nhất từ các tài khoản (KOLs) được chỉ định trước (Cách này lách luật được biểu phí 100$/tháng của API v2). Bot gửi danh sách các tweet này về Telegram để người dùng chọn bài phân tích (bằng lệnh `/analyze`).
3. **AI Scaffold Analysis (Claude CLI):** Các tweet **được chọn** sẽ được truyền thẳng vào **Claude Code CLI** dưới background. Claude trực tiếp thực thi các framework tùy chỉnh (`/scaffold` và `/cot`) để phân tích, tổng hợp và đề xuất một **Use Case thực tiễn**.
4. **Git Sync:** Nội dung Use Case được lưu xuất thành Markdown (`.md`) và được tự động commit & push lên trực tiếp repository GitHub của Tool này (`outputs/usecases/`).
5. **Approval 1 (Use Case):** Bot Telegram gửi cho bạn link/summary Use Case. Tại đây, bạn có quyền Duyệt (nhắn lệnh `/approve_usecase`) hoặc Từ chối (`/cancel`).
6. **AI Implementation & Approval 2:** Nếu duyệt, hệ thống gọi Claude CLI lần thứ hai để từ Markdown đó "dịch" ra một bài Post Twitter hoàn chỉnh. Bản nháp được gửi lại qua Telegram để bạn duyệt lần 2 (`/approve_post`).
7. **Twitter Publisher:** Sau khi chốt, Bot sẽ đính kèm bản nháp bắn thẳng lên tài khoản Twitter cá nhân của bạn thông qua Twitter API.

---

## 🛠️ Chuẩn Bị Yêu Cầu (Requirements)

Bạn cần gom đủ các thông tin Key/Token sau:

1. **Telegram Bot Token:**
   - Lấy thông qua [@BotFather](https://t.me/BotFather) trên Telegram.
   - Bạn cũng cần cung cấp `CHAT_ID` của cá nhân bạn (Lấy qua [@userinfobot](https://t.me/userinfobot)) để Bot chặn những người ngoài không có quyền điều khiển.

2. **Twitter Developer API Keys:**
   - Mở [Twitter Developer Portal](https://developer.twitter.com).
   - Đảm bảo bạn có tài khoản phù hợp (ít nhất Free hoặc Basic tùy theo limits đọc Timeline).
   - Gom đủ 5 mã: `API KEY`, `API SECRET`, `ACCESS TOKEN`, `ACCESS SECRET` (Quyền Read & Write), và `BEARER TOKEN`.

3. **Môi Trường Mặc Định Của Máy (Claude CLI & Git):**
   - Đảm bảo lệnh `git` đã đăng nhập/có sẵn quyền push thẳng vào Github (không cần nhập lại pass).
   - Đảm bảo lệnh `claude` (Claude Code) đã được xác thực trước.

---

## ⚙️ Cài Đặt (Installation)

**Bước 1: Clone Tool & Cài Thư Viện**
Mở thư mục code và cài packages Python:
```bash
cd d:\_Tuan_AI\_2026\_code\TuanDoan_Workspace\twitter-telegram-pipeline\
pip install -r requirements.txt
```

**Bước 2: Cài đặt Biến Môi Trường (Environment Variables)**
Mở file `telegram_twitter_orchestrator.py` và điền/tạo các System Env cho thông tin của bạn. Đối với Windows (PowerShell), bạn có thể chạy:

```powershell
$env:TELEGRAM_BOT_TOKEN="token_bot_cua_ban"
$env:TELEGRAM_CHAT_ID="so_id_cua_ban"
$env:TWITTER_API_KEY="..."
$env:TWITTER_API_SECRET="..."
$env:TWITTER_ACCESS_TOKEN="..."
$env:TWITTER_ACCESS_SECRET="..."
$env:TWITTER_BEARER_TOKEN="..."
```
*(Nếu muốn tiện, bạn có thể hard-code điền thẳng chuỗi string vào các biến ở đầu file code).*

**Bước 3: Chỉ định danh sách theo dõi**
Tìm biến `TARGET_TWITTER_HANDLES = ["sama", "elonmusk", "ylecun"]` và đổi tên acc thành nguồn dữ liệu bạn muốn AI phân tích.

**Bước 4: Xác thực Twitter (Chỉ làm 1 lần)**
Vì chúng ta dùng Playwright scrape timeline để lách giới hạn API Free, bạn cần đăng nhập Twitter vào file hệ thống:
```bash
python twitter_auth.py
```
*(Trình duyệt sẽ mở, bạn đăng nhập xong là nó tự đóng và lưu file bảo mật `twitter_state.json`)*.

---

## 🚀 Hướng Dẫn Sử Dụng (Usage)

**1. Khởi chạy Bot liên tục:**
```bash
python telegram_twitter_orchestrator.py
```
*(Cửa sổ Terminal này cần được giữ mở. Khi chạy, nó sẽ in ra: `Starting Telegram <-> Twitter Orchestrator...`)*

**2. Giao tiếp qua Telegram:**
Mở ứng dụng Telegram, vào chat với con Bot của bạn và sử dụng các lệnh sau:

- Ngay khi có hứng tìm ý tưởng, gõ lệnh:
  👉 `/scan`
  *(Bot sẽ kết nối Twitter, kéo các bài viết mới về và hiển thị thành danh sách đánh số 1, 2, 3... cho bạn chọn).*

- Đọc qua danh sách, bạn chọn các tweet thấy hứng thú và gõ lệnh:
  👉 `/analyze 1,3` (Chọn bài số 1 và số 3)
  *(Claude Code CLI sẽ bắt đầu nạp nội dung để phân tích. Đợi khoảng ~30 giây vì phân rã /scaffold tốn thời gian).*

- Bot sẽ trả về tin nhắn:
  `🎉 Use Case Generated! ✅ Synced to GitHub....`
  
- Nếu bạn thấy ý tưởng đó dở, gõ:
  👉 `/cancel` (Dừng phiên xử lý hiện tại).

- Nếu ý tưởng hay và bạn quyết định làm, gõ:
  👉 `/approve_usecase`
  *(Claude Code sẽ soạn luôn nháp đăng Twitter dựa theo văn phong tài liệu).*

- Bot sẽ gửi nháp tweet về cho bạn đọc:
  `📝 Draft Tweet Ready...`

- Chốt đăng bài lên tường nhà mình, gõ lệnh chốt:
  👉 `/approve_post`
  *(Bot báo "BOOM! Your tweet is now live" là xong).*

---
## 💡 Các Lưu Ý Technical
1. **Free Tier Limit Twitter:** Tùy thuộc vào chính sách thay đổi liên tục của API Twitter, lệnh get timeline các tài khoản khác có thể yêu cầu gói Basic ($100/tháng). Nếu bạn dính lỗi 403 Forbidden Access, báo log API về Twitter thì bạn cần chuyển `TARGET_TWITTER_HANDLES` về đọc Timeline mặc định của chính account bạn.
2. **Path System:** Nếu setup Bot lên VPS/Server Linux, cần chú ý thay path biến `WORKSPACE_DIR` lại sao cho phù hợp với git folder hiện hành để tính năng Auto Push GitHub chạy ổn định.

# YT Recent Videos

Project độc lập: kết nối YouTube Data API v3 theo cấu hình đã lưu, liệt kê video
đăng trong N ngày gần nhất (mặc định 2 ngày) từ danh sách kênh theo dõi. Hỗ trợ
tải video, upload video, xem/sửa mô tả, đăng bình luận. Giao diện giữ chung style
SubExtractor (dark `#111114`, accent `#4d93ff`, `double-bezel`, `btn-island`, `glass-panel`).

## Vì sao dùng OAuth 2.0 (không chỉ API key)?

| Nhu cầu | API key | OAuth |
|---|---|---|
| List video mới, xem mô tả | ✅ | ✅ |
| Tải video (yt-dlp, không cần API) | ✅ | ✅ |
| Upload video | ❌ | ✅ (`youtube.upload`) |
| Sửa tiêu đề/mô tả | ❌ | ✅ (`youtube.force-ssl`) |
| Đăng (bình luận) | ❌ | ✅ (`youtube.force-ssl`) |

→ Project dùng **OAuth 2.0** làm phương thức chính, API key là fallback read-only
khi chưa login. Lưu ý: YouTube Data API **không cho tạo community post** —
endpoint comment đăng bình luận top-level và ghi rõ giới hạn này.

## Hướng dẫn lấy key và cấu hình YouTube

### 1. Tạo Google Cloud project và bật YouTube API

1. Mở [Google Cloud Console](https://console.cloud.google.com/), đăng nhập Google.
2. Bấm bộ chọn project ở thanh trên → **New project** → đặt tên, ví dụ
   `YT Recent Videos` → **Create**, rồi chọn đúng project vừa tạo.
3. Vào **APIs & Services → Library**, tìm **YouTube Data API v3** → **Enable**.
   API key và OAuth client ở các bước dưới phải thuộc project đã bật API này.

### 2. Lấy YouTube API key (tùy chọn, dùng đọc dữ liệu công khai)

1. Vào **APIs & Services → Credentials → Create credentials → API key**.
2. Copy key, mở chi tiết key → **API restrictions → Restrict key** → chọn
   **YouTube Data API v3** → **Save**.
3. Với **Application restrictions**, ứng dụng gọi Google từ backend Python nên
   không chọn **Websites / HTTP referrers**. Khi chạy trên server có IP ra ngoài
   cố định, có thể giới hạn theo **IP addresses**; chạy local với IP thay đổi có
   thể để **None** ở mục này và vẫn giữ giới hạn API ở bước 2.
4. Mở ứng dụng → **Cấu hình → API key (optional)** → dán key → **Lưu cấu hình**.

Chỉ dùng API key thì đọc được dữ liệu public; muốn upload, sửa video, bình luận
hoặc xem dữ liệu riêng của kênh, tiếp tục cấu hình OAuth bên dưới.

### 3. Thiết lập màn hình đồng ý OAuth

1. Trong cùng project, mở **Google Auth Platform** → **Get started** nếu chưa
   cấu hình. Giao diện cũ có thể nằm ở **APIs & Services → OAuth consent screen**.
2. Ở **Branding**, điền tên ứng dụng, email hỗ trợ và email liên hệ.
3. Ở **Audience**, chọn **External** nếu dùng Gmail cá nhân. Khi ứng dụng ở
   trạng thái **Testing**, thêm email Google sẽ đăng nhập vào **Test users**.
4. Ở **Data Access → Add or remove scopes**, thêm các scope ứng dụng đang dùng:

   ```text
   https://www.googleapis.com/auth/youtube.readonly
   https://www.googleapis.com/auth/youtube.upload
   https://www.googleapis.com/auth/youtube.force-ssl
   ```

5. Lưu cấu hình. Với External ở chế độ Testing và các scope YouTube này,
   refresh token thường hết hạn sau **7 ngày**; khi đó cần kết nối Google lại.
   Nếu triển khai cho người dùng bên ngoài, làm theo yêu cầu xác minh OAuth
   của Google trước khi phát hành rộng rãi.

### 4. Lấy Client ID / Client Secret và kết nối kênh

1. Vào **Google Auth Platform → Clients → Create client** (hoặc
   **APIs & Services → Credentials → Create credentials → OAuth client ID**).
2. Chọn **Application type: Web application**, đặt tên tùy ý.
3. Trong **Authorized redirect URIs**, thêm chính xác:

   ```text
   http://localhost:8001/api/youtube/auth/callback
   ```

   Đây là URL callback của **backend cổng 8001**. Nếu đổi host/cổng, phải sửa
   đồng thời ở Google Cloud và ô **Redirect URI** trong ứng dụng; `localhost`
   và `127.0.0.1` được coi là hai địa chỉ khác nhau.
4. Bấm **Create**, copy **Client ID** và **Client Secret** được cấp.
5. Chạy ứng dụng theo mục [Chạy](#chạy), mở `http://localhost:3001` → **Cấu hình**:

   | Ô cấu hình | Giá trị |
   |---|---|
   | Client ID | ID của OAuth Web client, thường kết thúc bằng `.apps.googleusercontent.com` |
   | Client Secret | Secret của cùng OAuth client |
   | API key (optional) | Key ở bước 2, nếu có |
   | Redirect URI | `http://localhost:8001/api/youtube/auth/callback` |
   | Kênh theo dõi | Mỗi dòng một channel ID `UC...` hoặc handle `@tenkenh` |

6. Bấm **Lưu cấu hình** trước, sau đó **Kết nối Google** → chọn tài khoản/kênh
   YouTube cần thao tác → đồng ý các quyền được yêu cầu.
7. Khi quay lại ứng dụng, kiểm tra trạng thái **Đã kết nối** và tên kênh.
   Với tài khoản có nhiều kênh/Brand Account, chọn đúng kênh muốn quản lý.

Có thể lấy channel ID của kênh mình tại
[YouTube → Cài đặt nâng cao](https://www.youtube.com/account_advanced), hoặc
dùng trực tiếp handle trong URL `https://www.youtube.com/@tenkenh`.

**Cấu hình bằng `.env` (tùy chọn):** copy `backend/.env.example` thành
`backend/.env`, điền các biến sau rồi khởi động lại backend:

```dotenv
YTV_youtube_client_id=YOUR_CLIENT_ID.apps.googleusercontent.com
YTV_youtube_client_secret=YOUR_CLIENT_SECRET
YTV_youtube_api_key=YOUR_YOUTUBE_API_KEY
YTV_oauth_redirect_uri=http://localhost:8001/api/youtube/auth/callback
YTV_frontend_url=http://localhost:3001
```

Giá trị đã lưu qua giao diện trong `backend/temp/yt_config.json` được ưu tiên;
`.env` chỉ là giá trị dự phòng khi trường tương ứng chưa được điền.
Sau khi cấu hình bằng `.env`, vẫn cần bấm **Kết nối Google** để cấp quyền OAuth.

## Hướng dẫn lấy Facebook Page ID và Page access token

### 1. Chuẩn bị Page và Meta app

1. Dùng tài khoản Facebook có quyền quản lý Page và tạo nội dung trên Page đó.
2. Mở [Meta for Developers](https://developers.facebook.com/apps/) → đăng ký
   tài khoản developer nếu được yêu cầu → **Create App**.
3. Chọn use case hỗ trợ quản lý **Facebook Page / Pages API** và thiết lập
   Facebook Login theo hướng dẫn của dashboard. Tên use case/menu có thể thay
   đổi theo loại app; nếu có lựa chọn loại app, chọn loại hỗ trợ quản lý Page
   cho doanh nghiệp (**Business**).
4. Khi thử nghiệm trong chế độ **Development**, tài khoản cấp token phải có
   vai trò phù hợp trên app (Admin/Developer/Tester, đã chấp nhận lời mời),
   đồng thời có quyền trên Page. Để phục vụ người dùng ngoài các vai trò này,
   cần quyền truy cập tương ứng, App Review/Advanced Access và xác minh doanh
   nghiệp nếu Meta yêu cầu; chỉ chuyển app sang Live chưa tự cấp thêm quyền.

### 2. Lấy User token để truy vấn các Page được quản lý

1. Mở [Graph API Explorer](https://developers.facebook.com/tools/explorer/).
2. Chọn đúng **Meta App** vừa tạo và phiên bản Graph API dùng cho ứng dụng
   (mặc định cấu hình của project là `v25.0`).
3. Chọn **Get Token → Get User Access Token**, thêm các quyền:

   | Quyền | Mục đích |
   |---|---|
   | `pages_show_list` | Liệt kê Page được quản lý qua `/me/accounts` |
   | `pages_read_engagement` | Đọc thông tin/nội dung Page phục vụ kiểm tra và luồng đăng |
   | `pages_manage_posts` | Tạo và quản lý bài đăng/video trên Page |

4. Bấm **Generate Access Token**, đăng nhập và cấp quyền cho đúng Page cần
   đăng. Nếu đã cấp quyền trước đó, kiểm tra lại danh sách Page được cho phép.
   Nếu không thấy các quyền cần thiết, quay lại dashboard kiểm tra use case
   và mục **Permissions and Features** của app.

### 3. Lấy Page ID và Page access token

Trong Explorer, dùng **User access token** vừa lấy để gửi yêu cầu **GET**:

```text
/me/accounts?fields=id,name,access_token,tasks
```

Kết quả ví dụ (các giá trị dưới đây chỉ là minh họa):

```json
{
  "data": [
    {
      "id": "123456789012345",
      "name": "Ten Page cua ban",
      "access_token": "YOUR_PAGE_ACCESS_TOKEN",
      "tasks": ["CREATE_CONTENT", "MANAGE"]
    }
  ]
}
```

- Tìm đúng Page theo `name`; nếu có nhiều Page, xem tiếp phân trang khi cần.
- Copy `id` vào ô **Facebook Page ID**.
- Copy `access_token` **trong cùng đối tượng Page đó** vào ô **Page access token**.
  Token dùng để gọi `/me/accounts` là User token; token ứng dụng cần lưu là
  **Page token trả về trong kết quả**, không phải App ID/App Secret.

### 4. Lưu và kiểm tra trong ứng dụng

1. Mở **Cấu hình → Facebook Page · video / Reels**.
2. Nhập **Facebook Page ID**, **Page access token** và **Graph API version**
   (ví dụ `v25.0`, có chữ `v` ở đầu và khớp phiên bản đã dùng trong Explorer).
3. Bấm **Lưu cấu hình**, sau đó **Kiểm tra Page đã lưu**.
4. Kết quả thành công sẽ hiển thị tên và ID Page. Bước này xác nhận token khớp
   Page; quyền upload/publish được Meta kiểm tra khi thực sự đăng video.

Facebook hiện được cấu hình qua giao diện; các giá trị được lưu ở backend
trong `backend/temp/yt_config.json`. Ô token trống sau khi lưu là bình thường:
giao diện hiển thị **đã lưu**, để trống khi lưu tiếp sẽ giữ token hiện có.

### 5. Kiểm tra thời hạn token và dùng lâu dài

- Mở [Access Token Debugger](https://developers.facebook.com/tools/debug/accesstoken/)
  để xem app, loại token, các quyền, thời điểm hết hạn và thời hạn truy cập dữ liệu.
- Để dùng lâu dài, đổi User token ngắn hạn sang **long-lived User access token**
  theo [hướng dẫn của Meta](https://developers.facebook.com/docs/facebook-login/guides/access-tokens/get-long-lived/),
  rồi dùng User token mới gọi lại `/me/accounts` ở bước 3 để lấy Page token mới.
  Việc đổi token cần App ID/App Secret của Meta app và thực hiện ở phía server.
- Kiểm tra Page token mới trong Debugger trước khi lưu lại. Kể cả khi không có
  ngày hết hạn cố định, token vẫn có thể mất hiệu lực khi bị thu hồi quyền,
  thay đổi quyền truy cập Page hoặc thay đổi bảo mật tài khoản. Ứng dụng chưa
  tự gia hạn Facebook token; khi token mất hiệu lực, lấy lại và lưu token mới.

## Lỗi cấu hình thường gặp

| Lỗi / hiện tượng | Cách kiểm tra |
|---|---|
| Google `redirect_uri_mismatch` | So khớp toàn bộ Redirect URI ở app và OAuth Web client: giao thức, host, cổng, đường dẫn và dấu `/` cuối. |
| Google `access_denied` khi Testing | Thêm đúng email đăng nhập vào Test users và cấp đủ quyền; nếu dùng Workspace, kiểm tra chính sách quản trị. |
| Google báo ứng dụng chưa xác minh | Với app thử nghiệm do bạn tạo, kiểm tra đúng tên app/project và tài khoản Test user; triển khai rộng rãi cần hoàn thành xác minh theo yêu cầu của Google. |
| Google `invalid_client` | Kiểm tra Client ID và Client Secret thuộc cùng OAuth Web client, secret còn hiệu lực và đã lưu trước khi kết nối. |
| YouTube báo API chưa bật / key bị từ chối | Bật YouTube Data API v3 trong project cấp key; kiểm tra API restrictions và giới hạn IP, không dùng HTTP referrer cho backend. |
| YouTube `quotaExceeded` | Xem quota của YouTube Data API v3 trong Cloud Console; chờ quota được làm mới hoặc xin tăng quota. |
| Google mất kết nối sau vài ngày / `invalid_grant` | Kết nối lại Google; kiểm tra trạng thái Testing và thời hạn refresh token. |
| Facebook `/me/accounts` trả `data: []` | Kiểm tra đang dùng User token, đã cấp `pages_show_list`, chọn đúng Page khi đăng nhập và tài khoản có quyền trên Page; kiểm tra vai trò trên app nếu đang Development. |
| Facebook token không khớp Page ID | Lấy `id` và `access_token` từ cùng một Page trong kết quả `/me/accounts`. |
| Facebook OAuth lỗi `190` | Kiểm tra trong Access Token Debugger; token hết hạn/bị thu hồi thì cấp lại và lưu token mới. |
| Facebook lỗi quyền `(#10)` / `(#200)` | Kiểm tra `pages_manage_posts`, `pages_read_engagement`, quyền tạo nội dung trên Page và mức truy cập quyền của Meta app. |

Tài liệu tham khảo:
[YouTube Data API](https://developers.google.com/youtube/v3/getting-started),
[Google OAuth cho web server](https://developers.google.com/youtube/v3/guides/auth/server-side-web-apps),
[Meta Pages API](https://developers.facebook.com/docs/pages-api/getting-started/).

## Chạy

```bash
# Backend :8001
cd yt-recent-videos/backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8001

# Frontend :3001
cd yt-recent-videos/frontend
npm install && npm run dev   # http://localhost:3001
```

Mở http://localhost:3001 → tab **Cấu hình** → lưu Client ID/Secret + danh sách
kênh (channel ID `UC...` hoặc handle `@tenkenh`) → **Kết nối Google** → sang tab
**Mới nhất** bấm Tải lại để xem video 2 ngày qua.

## API

| Method | Path | Mô tả |
|---|---|---|
| GET | `/api/health` | Health check |
| GET/POST | `/api/config` | Đọc/lưu cấu hình (client id/secret, api key, kênh, days) |
| GET | `/api/youtube/auth/url` | URL login Google |
| GET | `/api/youtube/auth/callback` | OAuth callback (redirect về FE) |
| GET | `/api/youtube/auth/status` | Trạng thái kết nối |
| POST | `/api/youtube/auth/disconnect` | Ngắt kết nối |
| GET | `/api/videos/recent?days=2` | Video N ngày qua từ kênh theo dõi |
| GET | `/api/videos/{id}` | Chi tiết + mô tả đầy đủ |
| PUT | `/api/videos/{id}` | Sửa tiêu đề/mô tả/tags/privacy (OAuth) |
| GET | `/api/videos/{id}/download?quality=best` | Tải mp4 đồng bộ (chỉ file nhỏ — file lớn dùng tasks bên dưới) |
| POST | `/api/videos/{id}/download-tasks?quality=best` | Tạo tác vụ tải nền → `{task_id}` (không timeout) |
| GET | `/api/download-tasks` | List tác vụ + % tiến độ (FE polling 2s) |
| GET | `/api/download-tasks/{task_id}/file` | Tải file khi task done (tên = tên video) |
| DELETE | `/api/download-tasks/{task_id}` | Hủy task đang chạy / xóa task + file |
| GET | `/api/videos/{id}/thumbnail` | Ảnh thumbnail phân giải cao nhất (đính kèm khi đăng bài) |
| POST | `/api/videos/upload` | Upload video mới (OAuth, multipart) |
| POST | `/api/videos/{id}/comment` | Đăng bình luận (OAuth) |
| POST | `/api/analyze` | Phân tích link YT bất kỳ → tiêu đề, mô tả, thumbnail, tags, hashtag |
| POST | `/api/analyze/title-ai` | Gemini dịch + gợi ý 3–4 tiêu đề ~70 ký tự |
| GET/POST | `/api/analyzed` | List / lưu phân tích video (kèm kết quả AI) |
| GET/DELETE | `/api/analyzed/{video_id}` | Mở / xóa phân tích đã lưu |
| GET | `/api/analyzed/{video_id}/image` | Ảnh thumbnail gốc đã lưu local (link chết vẫn xem được) |
| POST/GET | `/api/analyzed/{video_id}/generated-thumbnail` | Lưu / xem thumbnail ChatGPT đã tạo |
| POST | `/api/chatgpt/login` | Mở Chrome profile riêng để đăng nhập ChatGPT Plus (Next.js route) |
| POST | `/api/chatgpt-thumbnail` | Upload ảnh gốc vào chatgpt.com, gửi prompt và lưu ảnh kết quả (Next.js route) |
| POST | `/api/facebook/check` | Kiểm tra Page ID khớp Page access token đã lưu |
| GET/POST | `/api/facebook/flows` | Lịch sử / tạo flow YouTube → cắt → Facebook (chạy nền; GET tách `active` / `uploaded`) |
| POST | `/api/facebook/flows/batch` | Thêm tối đa 20 video vào hàng đợi → `{tasks, skipped, count}` |
| POST | `/api/facebook/flows/{task_id}/resume` | Kiểm tra và tiếp tục cùng video Facebook đã upload xong |
| GET | `/api/facebook/flows/{task_id}/clip` | Tải MP4 đã cắt |
| GET | `/api/facebook/flows/{task_id}/thumbnail` | Thumbnail gốc dùng cho flow |
| DELETE | `/api/facebook/flows/{task_id}` | Xóa lịch sử và file local của flow đã dừng; không xóa bài Facebook |

## Flow YouTube → Facebook Page (khoảng 30 phút)

1. Máy chạy backend cần **yt-dlp nightly, FFmpeg và ffprobe** trong `PATH`.
2. Trong **Cấu hình → Facebook Page**, nhập Page ID dạng số, **Page access token**
   của chính Page đó và Graph API version (mặc định `v25.0`). Token cần quyền
   `pages_manage_posts`, `pages_read_engagement` và tài khoản có quyền tạo nội dung
   trên Page. Khi lấy Page token qua `/me/accounts`, cần thêm `pages_show_list`.
   Lưu rồi bấm **Kiểm tra Page đã lưu**. Phép kiểm tra này xác nhận danh tính Page;
   quyền đăng thực tế được Meta kiểm tra khi upload/publish. Token được giữ tại
   backend trong file cấu hình gitignored; GET config chỉ trả cờ đã lưu.
3. Chọn video trong **Mới nhất → Chi tiết → Cắt 30 phút → Facebook**, hoặc tab
   **YT → Facebook** để chọn video / dán URL. Cần API key YouTube hoặc OAuth để
   đọc đầy đủ mô tả và tags. Sửa tiêu đề, mô tả, thẻ nếu muốn trước khi chạy.
4. Bấm **Tải → Cắt → Đăng Facebook** cho 1 video đã chỉnh nội dung, hoặc tích
   chọn nhiều video rồi bấm **Thêm N video vào hàng đợi**. Hàng đợi xử lý tuần
   tự từng video (tải → tìm khoảng lặng → cắt → đăng), có số thứ tự
   `#1, #2…`; video trùng đang chạy bị bỏ qua và báo rõ trong thông báo.
   Tác vụ tiếp tục khi đổi tab hoặc đóng trình duyệt (backend vẫn phải chạy).
   Cookie YouTube tùy chọn lấy từ trình duyệt trên máy backend, dành cho video
   yêu cầu đăng nhập. **Video bị chặn/bản quyền (lỗi "The page needs to be
   reloaded") gần như bắt buộc phải chọn cookie** trình duyệt đã đăng nhập
   YouTube — app tự thử client thường rồi tới Android, kèm script giải
   JS challenge (`--remote-components ejs:github`).
5. Mục **Đã upload** giữ các video đăng xong sau khi mở app lại: mở bài
   Facebook, xem lại video đã cắt và nội dung đã đăng, tải lại bản MP4.
   File cắt, thumbnail và lịch sử nằm trong
   `backend/temp/facebook_flows/{task_id}/` nên chừng nào chưa xóa thì vẫn
   xem/tải lại được.

### Video bị chặn → upload full + tự comment

Tab **Bị chặn**: tích chọn video rồi bấm **Upload Facebook full + tự comment**.
Các video được thêm vào cùng hàng đợi nhưng ở chế độ `full_video`: bỏ qua tìm
khoảng lặng và cắt, upload toàn bộ lên Facebook. Đăng xong, backend tự đăng
comment lên đúng video YouTube đó theo mẫu:

```text
Do video đã bị YT block ad phải che toàn bộ nội dung nên mng ghé phở bò của ad để xem full nha: {link bài Facebook}
Ủng hộ ad 1 like và 1 cmt giúp kênh phát triển hơn nha !!!
```

Lưu ý:

- Đăng comment cần OAuth tài khoản chủ kênh (tab Bị chặn vốn đã yêu cầu).
  Comment lỗi (video tắt bình luận, hết quyền…) không làm hỏng flow — trạng
  thái ghi lại trên card để đăng tay.
- **Ghim comment phải làm tay trong Studio**: YouTube Data API không có
  endpoint ghim comment. Nút Studio có sẵn trên mỗi video bị chặn.

### Điểm cắt và đầu ra

- Mặc định lấy từ đầu đến gần **30 phút**, tìm trong **29–31 phút** bằng
  `silencedetect`, ngưỡng **−35 dB**, khoảng lặng tối thiểu **0,5 giây**; chọn giữa
  khoảng lặng gần mốc nhất. Có thể chỉnh các tham số trên UI.
- Không tìm được khoảng lặng → báo lỗi, không tự cắt giữa câu rồi đăng. Video
  ngắn hơn 30 phút giữ toàn bộ; video không có audio cắt đúng mốc.
- Đây là phân tích mức âm lượng, không phải nhận biết ngữ nghĩa/câu nói. Nhạc nền
  có thể che khoảng nghỉ; điều chỉnh dB/vùng tìm nếu cần.
- Encode H.264/AAC MP4 để điểm cắt chính xác hơn stream-copy theo keyframe;
  giữ tỉ lệ hình gốc. Cắt xong thì xóa video gốc YouTube cho nhẹ đĩa, chỉ giữ
  file cắt, thumbnail, nội dung đăng và lịch sử trong
  `backend/temp/facebook_flows/{task_id}/`. Có thể xem/tải clip trên UI.
- Thẻ YouTube được chuyển thành hashtag (bỏ dấu cách/ký tự phân tách, giữ chữ
  Unicode), nối vào cuối mô tả, tránh trùng hashtag sẵn có. Không dùng YouTube
  tag làm Facebook `content_tags` vì field đó có ý nghĩa khác.

### Đăng video dài / Reels

Flow dùng **Page Video API `/{page_id}/videos`** với upload chia chunk, phù hợp
video dài. Upload xong ở trạng thái chưa xuất bản → đợi xử lý → đặt thumbnail
YouTube làm ảnh bìa ưu tiên → xuất bản → kiểm tra `published` và `video_status`.
UI chỉ báo thành công khi đã xác nhận và trả link thực tế từ Facebook.

[Meta thông báo hợp nhất video thành Reels](https://about.fb.com/news/2025/06/making-it-easier-create-videos-facebook/)
với mọi độ dài/tỉ lệ. Tuy nhiên, API `/video_reels` có đặc tả riêng; flow này
**không ép video 30 phút qua endpoint Reels ngắn** và không đảm bảo nhãn Reel
trên Page chưa được Meta hỗ trợ hợp nhất. Kiểm tra cách hiển thị trên Page đích.

Nếu lỗi sau khi upload hoàn tất, **Tiếp tục video đã upload** kiểm tra và dùng
lại đúng Facebook video ID, không tạo bản upload mới. Nếu backend restart,
flow đang chạy chuyển sang lỗi gián đoạn; không tự đăng lại. Lỗi trước khi
upload hoàn tất cần kiểm tra video nháp trên Page trước khi tạo flow mới.
Xóa lịch sử/file local không xóa video đã tạo trên Facebook.

Kiểm tra offline (không đăng Facebook thật):

```bash
cd yt-recent-videos/backend
python -B -m unittest discover -s tests -v
```

## Tab Đăng bài (YouTube Community)

YouTube Data API **không có endpoint tạo community post** nên bước đăng cuối là
bán tự động: tab **Đăng bài** liệt kê video theo số ngày (1/2/3/7), tích chọn
nhiều clip, template động với biến `{title} {url} {video_id} {channel} {date}`
(lưu vào config, có preview trực tiếp từng bài + số ký tự + ảnh thumbnail),
rồi **Copy từng bài / Copy tất cả / Tải thumbnails / Mở YouTube Studio** để dán
và đăng. Muốn full-auto ngầm thì phải automation trình duyệt (fragile, dễ die
khi YouTube đổi giao diện) — chưa làm.

## Thumbnail bằng ChatGPT Plus

Tab **Phân tích** có khối **ChatGPT Plus · tạo lại thumbnail**. Luồng này không
cần OpenAI API key: Next.js dùng `puppeteer-core` mở Chrome profile riêng tại
`~/.yt-recent-videos/chatgpt-profile`, người dùng đăng nhập `chatgpt.com` một
lần rồi profile được tái sử dụng. Trước khi tạo, app tự lưu thumbnail gốc local,
đính kèm ảnh vào chat, gửi prompt 16:9 có tiêu đề tiếng Việt và `Phần N` (mặc
định 1), chờ ảnh tạo xong rồi lưu tại
`backend/temp/analyzed/{video_id}.generated.png`. Ảnh kết quả có preview phóng
to, copy clipboard và tải xuống. Nếu UI ChatGPT thay đổi selector, automation có
thể cần cập nhật.

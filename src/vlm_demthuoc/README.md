# VLM Pills Counter — đếm thuốc từ webcam

Hệ thống đọc webcam, **khi khung hình đứng yên đủ 3 giây** thì tự chụp một ảnh,
gửi lên Claude (vision) để đếm và in ra số **viên nang / viên nén / tuýp / lọ /
hộp**.

Đây là nhánh VLM, chạy độc lập với bot Telegram + YOLO (`best.pt`) ở thư mục cha.

Không bắt buộc dùng key của Claude. Hệ thống hỗ trợ **mọi endpoint tương thích
OpenAI** (OpenRouter, Groq, Together, OpenAI gốc, hoặc model chạy local qua
Ollama / LM Studio / vLLM) — xem mục 2.

## 1. Cài đặt

```bash
cd vlm
pip install -r requirements.txt
```

## 2. Điền cấu hình — mở file `vlm/api_key.json`

Toàn bộ thông tin kết nối nằm trong một file duy nhất:
**[`api_key.json`](api_key.json)**. Điền 4 trường rồi lưu lại.

### Ví dụ: Google AI Studio (Gemini)

Lấy key tại <https://aistudio.google.com/apikey>. Google có sẵn lớp tương thích
OpenAI nên vẫn dùng `"provider": "openai"`:

```json
{
  "provider": "openai",
  "base_url": "gemini",
  "model":    "gemini-2.5-flash",
  "api_key":  "AIza..."
}
```

### Ví dụ: OpenRouter (gom nhiều model của nhiều hãng vào một key)

```json
{
  "provider": "openai",
  "base_url": "openrouter",
  "model":    "google/gemini-2.5-flash",
  "api_key":  "sk-or-v1-xxxxxxxx"
}
```

> ⚠️ Trên OpenRouter, tên model **có tiền tố hãng**: `openai/gpt-4o`, không phải
> `gpt-4o`. Điền thiếu tiền tố sẽ báo `Không tìm thấy model`.

### Ví dụ: OpenAI gốc

```json
{
  "provider": "openai",
  "base_url": "openai",
  "model":    "gpt-4o",
  "api_key":  "sk-proj-xxxxxxxx"
}
```

### Ví dụ: model chạy local, không cần key và không tốn tiền

```json
{
  "provider": "openai",
  "base_url": "ollama",
  "model":    "qwen2.5vl:7b",
  "api_key":  ""
}
```

### Ví dụ: Claude

```json
{
  "provider": "claude",
  "base_url": "",
  "model":    "claude-opus-5",
  "api_key":  "sk-ant-api03-xxxxxxxx"
}
```

Giải thích từng trường:

| Trường | Ý nghĩa |
|---|---|
| `provider` | `openai` = dùng SDK `openai`, chạy được với mọi endpoint tương thích. `claude` = dùng SDK `anthropic`. |
| `base_url` | Tên viết tắt (`gemini`, `openrouter`, `groq`, `together`, `ollama`, `lmstudio`, `openai`) hoặc URL đầy đủ dạng `https://.../v1`. Để rỗng khi dùng `claude`. |
| `model` | Tên model, **bắt buộc hỗ trợ ảnh (vision)**. Chạy `python list_models.py` để xem đúng tên — model chỉ đọc văn bản sẽ báo lỗi. |
| `api_key` | Key của chính dịch vụ trong `base_url`. Server local thường để rỗng. |

Hai cách khác nếu bạn thích:

- **Biến môi trường** (ưu tiên cao hơn file): `OPENAI_API_KEY` / `ANTHROPIC_API_KEY`
  cho key, `VLM_BASE_URL` / `VLM_MODEL` / `VLM_PROVIDER` cho phần còn lại.
- **Tham số dòng lệnh** (ưu tiên cao nhất):
  `--provider openai --base-url groq --model <tên-model>`.

> `api_key.json` đã nằm trong `.gitignore`. Đừng commit hoặc chia sẻ file này.
> Nếu lỡ lộ key, vào trang quản lý của dịch vụ thu hồi rồi tạo key mới.

### Không biết điền tên model gì?

```bash
python list_models.py                     # theo cấu hình trong api_key.json
python list_models.py --base-url gemini   # xem model của Google AI Studio
python list_models.py --filter gemini     # lọc theo từ khoá
```

Script hỏi thẳng máy chủ nên tên trả về luôn đúng với dịch vụ bạn đang dùng.
Nó **không** cho biết model nào nhìn được ảnh — cái đó phải xem tài liệu của
dịch vụ.

### Chọn model nào?

Model phải **nhìn được ảnh**. Ngoài ra, đếm vật thể nhỏ và chồng lấp là bài toán
khó hơn mô tả ảnh thông thường — model nhỏ/rẻ hay đếm sót. Cách chọn đúng đắn:
lấy 20–30 ảnh mẫu đã đếm tay, chạy `analyze_image.py` với vài model rồi so, thay
vì tin vào bảng xếp hạng chung.

## 3. Chạy

```bash
python camera_counter.py
```

hoặc nháy đúp `run.bat` trên Windows.

Cách dùng: đặt thuốc vào khung hình → **bỏ tay ra và giữ yên 3 giây** → chương
trình tự chụp và đếm. Góc dưới cửa sổ hiển thị trạng thái:

| Hiển thị | Nghĩa là |
|---|---|
| `Dang chuyen dong (do lech 8.4)` | cảnh còn động, chưa đếm |
| `On dinh 1.8/3s` | đang đếm ngược, giữ yên thêm |
| `DANG DEM...` | đã chụp, đang chờ model trả lời |
| `Da dem xong - doi canh thay doi` | đã đếm xong, đổi thuốc để đếm tiếp |

Phím tắt trong cửa sổ camera:

| Phím | Tác dụng |
|---|---|
| `q` hoặc `ESC` | thoát |
| `SPACE` | chụp và đếm ngay, không cần chờ ổn định |
| `s` | lưu khung hình hiện tại ra `capture_<thời-gian>.jpg` |

Kết quả in ra terminal:

```
====================================================
[14:32:07] Lần đếm #3  (4.1s)
  Viên nang  : 6
  Viên nén   : 12
  Tuýp thuốc : 1
  Lọ thuốc   : 2
  Hộp thuốc  : 1
  ---------------------------------
  Tổng số viên (nang + nén): 18
  Độ tin cậy : cao
  Ghi chú    : Ảnh rõ nét, các viên tách rời, không có vật thể mơ hồ.
====================================================
```

Cửa sổ camera hiển thị con số mới nhất ở góc trái (không dấu, vì OpenCV không
vẽ được tiếng Việt có dấu).

## 4. Tuỳ chọn dòng lệnh

```bash
python camera_counter.py --camera 1              # webcam thứ hai
python camera_counter.py --stable-seconds 5      # phải giữ yên 5 giây
python camera_counter.py --motion-threshold 4    # camera nhiễu, khó vào trạng thái ổn định
python camera_counter.py --mode frames --interval 30   # quay lại kiểu đếm theo số khung
python camera_counter.py --min-interval 5        # tối thiểu 5 giây giữa 2 lần gọi API
python camera_counter.py --model <tên-model>     # đổi model
python camera_counter.py --provider openai --base-url groq --model <tên-model>
python camera_counter.py --json-mode object      # endpoint không hỗ trợ json_schema
python camera_counter.py --effort high           # chỉ có tác dụng với provider claude
python camera_counter.py --no-blister            # không đếm viên còn trong vỉ
python camera_counter.py --log ket_qua.jsonl     # ghi mọi kết quả ra file
python camera_counter.py --no-window             # máy không có giao diện đồ hoạ
```

Tất cả đều có biến môi trường tương ứng (`VLM_CAMERA`, `VLM_STABLE_SECONDS`,
`VLM_MOTION_THRESHOLD`, `VLM_TRIGGER_MODE`, `VLM_MIN_INTERVAL_SEC`, `VLM_EFFORT`,
`VLM_MODEL`, `VLM_MAX_IMAGE_EDGE`…) — xem `config.py`.

## 5. Test prompt trên ảnh có sẵn (không cần camera)

```bash
python analyze_image.py mau/anh1.jpg mau/anh2.jpg --json ket_qua.jsonl
```

Dùng cách này để so kết quả model với số đếm tay trước khi sửa prompt.

## 6. Cơ chế "ổn định 3 giây" hoạt động thế nào

Mỗi khung hình được thu nhỏ về 320px, chuyển sang ảnh xám và làm mờ nhẹ (để
nhiễu cảm biến không bị tính là chuyển động), rồi so với khung ngay trước đó.
Chênh lệch pixel trung bình chính là **độ lệch** hiển thị trên cửa sổ:

- độ lệch **> `--motion-threshold`** (mặc định 2.0) → đang chuyển động, đồng hồ
  đếm ngược reset về 0;
- độ lệch **≤ ngưỡng** liên tục đủ `--stable-seconds` giây → chụp và gửi đi đếm.

Sau khi đếm xong, chương trình **khoá lại** cho tới khi phát hiện chuyển động
mới. Nhờ vậy để nguyên đĩa thuốc trên bàn sẽ không bị đếm lặp mỗi 3 giây (đây là
điểm quan trọng nhất về chi phí so với kiểu đếm theo số khung hình).

Hai chốt chặn phụ vẫn giữ nguyên:

- **Một yêu cầu tại một thời điểm** — lần gọi trước chưa xong thì không gửi tiếp.
- **Khoảng cách tối thiểu 3 giây** giữa 2 lần gọi API (`--min-interval`).

Chỉnh ngưỡng:

| Hiện tượng | Cách sửa |
|---|---|
| Không bao giờ vào được trạng thái ổn định (webcam nhiễu, đèn nhấp nháy) | tăng `--motion-threshold` lên 3–5 |
| Chụp cả khi tay còn đang di chuyển | giảm `--motion-threshold` xuống 1.0–1.5 |
| Muốn có thêm thời gian rút tay ra | tăng `--stable-seconds` |

## 7. Cấu trúc thư mục

| File | Vai trò |
|---|---|
| `api_key.json` | **Điền provider / base_url / model / api_key ở đây.** |
| `prompts.py` | System prompt + user prompt. **Sửa prompt ở đây.** |
| `providers.py` | Lớp gọi API riêng cho từng nhà cung cấp (Claude / OpenAI-compatible) |
| `vlm_client.py` | JSON schema, mã hoá ảnh, bóc & làm sạch JSON — dùng chung mọi provider |
| `config.py` | Nạp cấu hình + API key |
| `camera_counter.py` | Vòng lặp webcam, overlay, thông báo (chương trình chính) |
| `analyze_image.py` | Đếm trên file ảnh, dùng để test prompt |

## 8. Ba chế độ ép JSON (`--json-mode`)

Mức hỗ trợ ép JSON khác nhau nhiều giữa các nhà cung cấp, nên có 3 mức, **tự
động hạ cấp** khi máy chủ báo không hỗ trợ (in ra terminal khi hạ cấp, và nhớ
lại nên chỉ thử lại 1 lần):

| Mức | Cách làm | Bảo đảm được gì |
|---|---|---|
| `schema` (mặc định) | `response_format: json_schema` | JSON hợp lệ **và** đúng schema |
| `object` | `response_format: json_object` | JSON hợp lệ, schema thì không |
| `off` | không ép gì | không gì cả, tự bóc JSON khỏi văn bản |

Ở mức `object` và `off`, chương trình **tự nối thêm khối ép định dạng vào system
prompt** (mục 7 trong [prompts.py](prompts.py)) vì lúc đó chỉ còn prompt để dựa
vào. Với `schema` thì khối đó bị bỏ đi cho đỡ tốn token.

Ngoài ra `extract_json()` chịu được các kiểu đầu ra bẩn: bọc trong ` ```json `,
có câu dẫn phía trước, có thẻ `<thinking>`, có dấu `{` `}` bên trong chuỗi.

## 9. Chi phí

Mỗi lần đếm gửi 1 ảnh (~1.500–4.800 token ảnh tuỳ độ phân giải) + system prompt
(~4.100 ký tự). Với provider `claude`, system prompt được **cache** nên từ lần
thứ hai chỉ tốn khoảng 10% giá cho phần đó.

Muốn giảm chi phí:

- tăng `--min-interval` (ít lần gọi hơn — hiệu quả nhất);
- giảm `--max-edge` xuống 1024 (ảnh nhẹ hơn, nhưng khó thấy viên nhỏ);
- đổi sang model rẻ hơn, hoặc chạy model local (`base_url: "ollama"`) — miễn phí
  hoàn toàn, đổi lại độ chính xác thường thấp hơn;
- với `claude`: hạ `--effort` xuống `low`.

## 10. Lỗi hay gặp

| Hiện tượng | Xử lý |
|---|---|
| `Chưa chọn model` | Điền `"model"` trong `api_key.json` — endpoint OpenAI-compatible không có model mặc định |
| `Không tìm thấy model 'x' tại ...` | Sai tên model; lấy đúng tên từ trang model của dịch vụ |
| `API key không hợp lệ với endpoint này` | Key và `base_url` không khớp nhau (ví dụ key OpenRouter nhưng base_url trỏ Groq) |
| Model trả lời nhưng không thấy ảnh / bảo không có ảnh | Model đó không hỗ trợ vision — đổi model khác |
| `Không đọc được JSON` lặp lại | Đặt `--json-mode off` rồi xem model trả về gì; model quá nhỏ có thể không giữ được định dạng |
| `Không kết nối được tới ...` | Sai `base_url`, hoặc server local chưa bật |
| `Không mở được camera index 0` | Đóng app đang chiếm webcam, hoặc thử `--camera 1` |
| `Bị giới hạn tốc độ (429)` | Tăng `--min-interval` |
| `Trả lời bị cắt do hết max_tokens` | Đặt `VLM_MAX_TOKENS=8000` |
| Terminal hiện `?????` thay chữ Việt | Chạy `chcp 65001` trước khi chạy script |

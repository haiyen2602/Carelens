# VLM-Pill-Counter

Ứng dụng đếm thuốc tự động bằng **mô hình ngôn ngữ kết hợp thị giác (VLM)** qua API.
Đưa vào một bức ảnh — từ webcam hoặc file có sẵn — hệ thống trả về số lượng từng
loại dược phẩm dưới dạng JSON, không cần huấn luyện model riêng, không cần gán nhãn
dữ liệu.

Chạy được với Claude, GPT-4o, Gemini và mọi endpoint tương thích OpenAI (kể cả
model chạy local qua Ollama / LM Studio).

## 1. Tính năng nổi bật

- **Đếm tự động 6 loại**: viên nang, viên nén, tuýp, lọ, hộp, gói thuốc — kể cả
  viên còn nằm trong vỉ bấm (bật/tắt bằng `--no-blister`).
- **Lọc vật thể không phải thuốc**: kẹo cao su xylitol, kẹo bạc hà, gummy được
  nhận ra và đếm riêng vào `khong_phai_thuoc`, không bao giờ cộng vào tổng số viên.
- **Tích hợp API linh hoạt**: đổi nhà cung cấp chỉ bằng một dòng trong `.env` —
  OpenAI, Anthropic, Google AI Studio, OpenRouter, Groq, Together, Ollama,
  LM Studio.
- **Đầu ra có cấu trúc**: JSON nghiêm ngặt gồm số lượng từng loại, mức độ tin cậy
  (`cao` / `trung_binh` / `thap`) và ghi chú giải thích. Ba mức ép JSON tự động hạ
  cấp theo khả năng của máy chủ (`json_schema` → `json_object` → tự bóc).
- **Tối ưu ảnh đầu vào**: tự thu nhỏ về cạnh dài ≤ 1600px và nén JPEG trước khi
  gửi, giảm chi phí token mà không mất chi tiết viên thuốc.
- **Chụp khi khung hình đứng yên**: chỉ gọi API khi cảnh đã ổn định 3 giây, tránh
  đếm lặp và tránh ảnh mờ do rung tay(cũng có thể chụp ảnh bằng nút bấm e).

## 2. Luồng hoạt động

```
  Webcam / file ảnh
         │
         ▼
  [1] Phát hiện khung hình đứng yên (3s)(bấm e)  ──►  chụp
         │
         ▼
  [2] Tiền xử lý: resize ≤1600px → JPEG q90 → base64
         │
         ▼
  [3] Gọi VLM API:  system prompt (quy tắc đếm) + ảnh + user prompt
         │              └─ ép JSON schema ở mức giao thức
         ▼
  [4] Parse JSON → ép kiểu, chặn giá trị âm → CountResult
         │
         ├──► overlay trên cửa sổ camera
         ├──► in ra terminal
         └──► ghi tích luỹ vào ket_qua.json
```

## 3. Chiến lược Prompt

Đếm vật thể nhỏ và chồng lấp là điểm yếu cố hữu của VLM — model hay đoán một con
số "trông hợp lý" thay vì đếm thật. System prompt trong [`prompts.py`](prompts.py)
chống lại điều đó bằng bốn kỹ thuật:

1. **Chia lưới ảo 3×3** — bắt model quét từng ô theo thứ tự trái→phải, trên→dưới,
   đếm theo cụm 2–5 vật thể rồi cộng lại, sau đó quét thêm một lượt riêng cho rìa
   ảnh và vùng chồng lấp.
2. **Quy tắc TÍNH / KHÔNG TÍNH có thứ tự ưu tiên (R1–R12)** — cấm suy luận số
   lượng bên trong bao bì kín, cấm đọc số in trên vỏ hộp ("Hộp 100 viên" không làm
   `vien_nen = 100`), bỏ qua hình thuốc *in* trên bao bì và phản chiếu trong gương.
3. **Thà bỏ sót còn hơn đếm bừa** — vật thể mơ hồ thì không tính và phải khai báo
   trong `ghi_chu`; kèm tiêu chí rõ ràng để hạ `do_tin_cay`.
4. **Cho nhầm lẫn một chỗ để "đổ" vào** — thay vì cấm suông "đừng đếm kẹo" (khi
   phân vân model vẫn chọn `vien_nen`), prompt cấp cho kẹo một trường riêng, kèm
   dấu hiệu nhận biết cụ thể và ưu tiên đọc chữ trên bao bì.

Trích một đoạn (R8 — loại trừ kẹo):

```
R8. KẸO VÀ THỰC PHẨM KHÔNG PHẢI THUỐC — quy tắc này ƯU TIÊN HƠN mục vien_nen.
    Dấu hiệu nhận ra kẹo gum (chỉ cần 2 trong số này là đủ để KHÔNG tính vào vien_nen):
    - hình gối (pillow) phồng đều hai mặt — không phải đĩa dẹt như viên nén;
    - bề mặt phủ lớp áo đường / sáp, trắng đục mờ hoặc bóng lì;
    - KHÔNG có rãnh bẻ đôi, KHÔNG có chữ / số / logo dập nổi trên mặt viên.
    Nếu bao bì có chữ "gum", "xylitol", "candy", "kẹo" → mọi viên thuộc bao bì đó
    đều là kẹo. TIN VÀO CHỮ TRÊN BAO BÌ, đừng đoán theo hình dáng viên.
```

Đầu ra luôn theo đúng schema:

```json
{
  "vien_nang": 5, "vien_nen": 4, "tuyp_thuoc": 0,
  "lo_thuoc": 1, "hop_thuoc": 0, "goi_thuoc": 2,
  "khong_phai_thuoc": 0,
  "do_tin_cay": "cao",
  "ghi_chu": "Ảnh rõ nét, các viên tách rời, không có vật thể mơ hồ."
}
```

## 4. Công nghệ & Yêu cầu hệ thống

| Hạng mục | Yêu cầu |
|---|---|
| Python | 3.10+ (dùng cú pháp type hint `dict[str, int]`, `X \| None`) |
| Thị giác máy tính | `opencv-python >= 4.8`, `numpy >= 1.24` |
| Cấu hình | `python-dotenv >= 1.0` — đọc `.env` ở gốc repo |
| SDK model | `openai >= 1.40` và/hoặc `anthropic >= 0.72` — chỉ cần cái bạn dùng |
| Phần cứng | Webcam (chỉ khi chạy chế độ camera). Không cần GPU. |
| Khác | API key của một nhà cung cấp VLM, hoặc một model local đang chạy |

## 5. Cài đặt & Chạy

```bash
pip install -r requirements.txt
```

Điền 5 biến vào `.env` ở **gốc repo** (cùng file mà phần còn lại của dự án đang
dùng — xem `.env.example`):

```bash
VLM_API_KEY=AIza...
VLM_PROVIDER=openai
VLM_BASE_URL=gemini
VLM_MODEL=gemini-2.5-flash
VLM_JSON_MODE=schema
```

> `VLM_PROVIDER`: `openai` cho mọi endpoint tương thích OpenAI, `claude` cho SDK
> Anthropic. `VLM_BASE_URL` nhận tên viết tắt (`gemini`, `openrouter`, `groq`,
> `together`, `ollama`, `lmstudio`, `openai`) hoặc URL đầy đủ. Model **bắt buộc
> hỗ trợ ảnh (vision)**. `VLM_JSON_MODE` để `off` nếu endpoint trả về rỗng khi
> có `response_format`.

Hai biến nữa quyết định chương trình chờ bao lâu khi mạng có vấn đề:

| Biến | Mặc định | Dùng khi |
|---|---|---|
| `VLM_TIMEOUT` | `45` | Máy chủ **nhận kết nối rồi im lặng**. Quá giờ là báo lỗi luôn, không thử lại — một lần đếm thật chỉ mất ~25s |
| `VLM_RETRIES` | `5` | Máy chủ trả **rỗng ngay lập tức** (lỗi quen thuộc của vilao). Mỗi lượt gần như không tốn thời gian nên để 5 vẫn rẻ |

> Hai cơ chế này cho hai kiểu hỏng khác nhau, đừng gộp. Thử lại một lần *quá
> giờ* tốn trọn 45 giây mà hiếm khi thành công; bấm `e` để đếm lại nhanh hơn.

> **`VLM_API_KEY` phải là biến riêng, đừng dùng lại `OPENAI_API_KEY`.** Hai biến
> đó nằm chung một file `.env` nhưng trỏ tới hai endpoint khác nhau —
> `OPENAI_API_KEY` là của chatbot, gửi nó tới `VLM_BASE_URL` sẽ ra lỗi 401.

Đường lùi: để trống `VLM_API_KEY` thì chương trình quay về đọc `api_key.json`
trong thư mục này như trước, không cần sửa gì.

```bash
python camera_counter.py                       # đếm trực tiếp từ webcam
python analyze_image.py anh1.jpg anh2.jpg      # đếm trên file ảnh có sẵn
```

Phím tắt trong cửa sổ camera: `e` chụp ngay · `SPACE` chụp tiếp · `s` lưu ảnh ·
`q` thoát.

## 6. Cấu trúc mã nguồn

| File | Vai trò |
|---|---|
| `prompts.py` | System prompt + user prompt — **sửa chiến lược đếm ở đây** |
| `vlm_client.py` | JSON schema, mã hoá ảnh, bóc & làm sạch JSON (dùng chung mọi provider) |
| `providers.py` | Lớp gọi API riêng cho Claude / OpenAI-compatible |
| `config.py` | Nạp cấu hình + API key từ `.env` |
| `camera_counter.py` | Vòng lặp webcam (chương trình chính) |
| `stability.py` | Phát hiện khung hình đứng yên để biết lúc nào nên chụp |
| `overlay.py` | Vẽ kết quả lên cửa sổ camera |
| `results_store.py` | In terminal, lưu ảnh, ghi file JSON/JSONL |
| `analyze_image.py` | Đếm trên file ảnh — dùng để đo độ chính xác và tinh chỉnh prompt |

Test nằm ở `tests/vlm_demthuoc/`, chạy bằng `pytest tests/vlm_demthuoc/` từ gốc
repo. Không cần webcam và không gọi mạng.

> Cả `.env` lẫn `api_key.json` đều nằm trong `.gitignore`. Đừng commit hoặc chia
> sẻ hai file này.

# Evaluation Evidence — CapyMedi (VMEC-04)

> Deliverable #10. Toàn bộ số liệu dưới đây **trích trực tiếp từ các file trong `eval/`**, không có con số nào ước lượng. Mỗi bảng ghi rõ file nguồn để đối chiếu lại.

**Team P-067 (G14 - T067):** Nguyễn Minh Đạt (Team Leader / Data / AI) · Nguyễn Hải Yến (PM / UI-UX / Frontend) · Phạm Thành Đạt (AI Engineer / Fullstack / QA) · Trương Quốc Trường (Tech Leader / Fullstack)

---

## 1. Vì sao đo những thứ này

CapyMedi là agent y tế. Rủi ro lớn nhất **không phải** trả lời chậm hay xấu, mà là **trả lời sai một cách tự tin** về thuốc — hoặc gán tác dụng phụ của thuốc A cho thuốc B. Nên bộ đánh giá xoay quanh 4 câu hỏi:

1. Agent có **tìm đúng nguồn** không? *(retrieval)*
2. Agent có **bịa** không? *(grounding / hallucination)*
3. Agent có **nhầm thuốc này sang thuốc kia** không? *(cross-drug misattribution)*
4. Agent có bị **dụ vượt rào an toàn** không? *(red team)*

Cộng thêm một trục riêng cho thị giác: **đếm thuốc từ ảnh** có đủ tin để tự động hoá không.

---

## 2. RAG Retrieval

**Nguồn:** `eval/eval_report.json` · **n = 32 câu hỏi** trên 8 thuốc thật, 4 khía cạnh mỗi thuốc (công dụng / tác dụng phụ / cách dùng / bảo quản)

| Chỉ số | Giá trị |
|---|---:|
| recall@k | **68,75%** |
| precision@1 | **40,63%** |
| MRR | **0,507** |

### Đánh đổi ngưỡng — có đo, không đoán

Ngưỡng similarity từng được hạ rồi nâng, và cả hai lần đo đều giữ lại trong report:

| Ngưỡng (vector / lexical) | recall@k | precision@1 | MRR |
|---|---:|---:|---:|
| 0,50 / 0,30 *(bản cũ)* | 87,5% | 40,63% | 0,578 |
| **0,60 / 0,55** *(đang chạy)* | **68,75%** | **40,63%** | **0,507** |

Ngưỡng chặt hơn **làm giảm recall** nhưng đổi lại **giảm nhiễu chéo giữa các thuốc** — xem mục 4. Trong bối cảnh y tế, trả về ít mà đúng thuốc an toàn hơn trả về nhiều mà lẫn thuốc khác. Đây là quyết định có chủ đích, không phải hồi quy.

**Điểm yếu đã biết:** nhìn `per_question` trong report, các câu hỏi **tác dụng phụ** là nhóm trượt nhiều nhất (`found_rank: null` ở 7/8 thuốc). Đây là hướng cải thiện rõ ràng nhất của vòng sau.

---

## 3. Grounding & Hallucination

**Nguồn:** `eval/eval_report.json` (`hallucination_and_caveat`) · n = 32

| Chỉ số | Giá trị |
|---|---:|
| grounded_rate | **100%** |
| hallucination_rate | **0%** |
| Số câu bị từ chối vì không có nguồn | 0 / 32 |
| missing_caveat_rate *(trên 8 câu hỏi cách dùng)* | **0%** |

Mọi câu trả lời đều bám nguồn truy xuất được. Với nhóm câu hỏi **cách dùng/liều**, hệ thống luôn kèm caveat — không câu nào đưa liều ra như chỉ định cá nhân hoá.

Kết quả này được **đo lại 2 lần ở `temperature=0`** (`hallucination_confirmation_run1_and_run2_temp0`) để loại trừ may rủi, và có cả bản judge vòng 1 kém tin cậy hơn (`grounded_rate` 81,25%) giữ lại trong report để minh bạch việc đã thay judge.

---

## 4. Cross-Drug Misattribution — chỉ số an toàn quan trọng nhất

**Nguồn:** `eval/eval_report.json` (`cross_drug_misattribution`) · n = 32

| Chỉ số | Giá trị |
|---|---:|
| Số ca có rủi ro gán nhầm thuốc | **6 / 32 (18,75%)** |
| Trong đó **bị filter chặn lại** | **5 / 6** |

Đây là chỉ số chúng tôi theo sát nhất: nếu agent lấy chunk của thuốc khác rồi trình bày như thông tin của thuốc đang hỏi, bệnh nhân có thể tránh sai tác dụng phụ hoặc dùng sai cách. Bộ lọc chặn được 5/6 ca; **1 ca lọt** là nợ kỹ thuật đã ghi nhận, không giấu.

---

## 5. Red Team — chống tấn công prompt

**Nguồn:** `eval/redteam_report.json` · `eval/redteam_prompts.py`

**14 / 14 pass (100%)** qua 7 nhóm tấn công:

| Nhóm | Số ca |
|---|---:|
| Prompt injection tiếng Việt | 2 |
| Prompt injection tiếng Anh | 2 |
| Giả danh admin / nâng quyền | 2 |
| Truy cập dữ liệu bệnh nhân khác | 1 |
| Obfuscation Unicode (zero-width space) | 1 |
| Paraphrase gián tiếp | 3 |
| Lách cảnh báo an toàn | 3 |

### Nói thẳng một điểm yếu

2 ca — `c2_bypass_overdose` và `c3_bypass_with_real_prescription` — **lọt qua guardrail regex ở tầng đầu vào**. Chúng vẫn được tính pass vì **bị chặn ở tầng sau**, nhưng điều đó nghĩa là hàng phòng thủ đầu tiên không bắt được paraphrase và obfuscation.

Bài học: **regex không đủ làm guardrail đầu vào**. Đây chính là lý do safety layer thiết kế 2 tầng `keyword OR LLM` (ADR-0009) thay vì chỉ dựa vào keyword.

---

## 6. Vision — đếm thuốc từ ảnh (VLM)

**Nguồn:** `eval/eval_vlm/eval_report.json` · golden set **25 ảnh thiết kế sẵn** (rõ / mờ / viên chồng chéo / kẹo giả thuốc)

**Tổng: 12 / 25 = 48%**

| Độ khó | Đạt | | Độ tin cậy model **tự chấm** | Đạt |
|---|---|---|---|---|
| Dễ | 87,5% (7/8) | | `cao` | **100%** (9/9) |
| Trung bình | 25% (3/12) | | `trung_binh` | 60% (3/5) |
| Khó | 40% (2/5) | | `thấp` | **0%** (0/11) |

### Phát hiện quan trọng nhất của cả bộ đánh giá

**Độ tin cậy model tự chấm dự báo được độ đúng.** Khi model nói `cao` → đúng 9/9. Khi nói `thấp` → sai 11/11.

Nhờ vậy, con số 48% thô **không phải là con số vận hành**. Hệ thống dùng chính độ tin cậy đó làm **cổng chặn**:

- `cao` → tự động ghi nhận liều
- `thấp` → không kết luận, mời chụp lại, **và không trừ lượt của bệnh nhân** (lỗi điều kiện chụp, không phải lỗi người dùng)
- Lệch quá 3 lượt → chuyển **người thân duyệt**, hệ thống không tự quyết

> ⚠️ **Cỡ mẫu nhỏ:** nhóm `cao` chỉ có 9 ca. Xu hướng đã rõ nhưng cần golden set lớn hơn để chốt con số — chúng tôi không khẳng định mốc 100%.

### Giới hạn cố hữu của bằng chứng bằng ảnh

Mô hình chỉ đếm được **6 hình dạng** (viên nang, viên nén, tuýp, lọ, hộp, gói) — nó **không phân biệt được Amlodipine với Panadol**, cả hai đều là "viên nén". Một liều gồm 2 thuốc viên nén khác nhau chỉ kiểm chứng được ở mức *"trong ảnh có 2 viên nén"*. Đây là giới hạn của phương pháp, không phải lỗi cài đặt — và được ghi thẳng trong `backend/services/photo_verification/matcher.py`.

---

## 7. Safety Layer & Persona

| Bộ đánh giá | Nguồn | Quy mô |
|---|---|---:|
| Safety classification (mức nghiêm trọng) | `eval/safety_llm_report.json` | **147** lượt gọi LLM |
| Drug reply gate (chặn trả lời ngoài phạm vi) | `eval/drug_reply_gate_report.json` | **165** lượt gọi LLM |
| Soul / persona consistency | `eval/soul_persona_report.json` | **9** lượt gọi LLM |

Mỗi ca chạy **nhiều lần** và ghi lại từng lần (`runs: [...]`) để phát hiện dao động — một phân loại đúng 2/3 lần không được tính là pass.

---

## 8. Test Suite

**Chạy ngày 2026-09-01** trên DB test riêng (`vmec04_test`), không phải DB thật:

```
44 failed, 2513 passed, 23 skipped in 910s
```

| Chỉ số | Giá trị |
|---|---:|
| Test **pass** | **2.513** |
| Test skip | 23 |
| Test fail | 44 |
| File test | 130+ |

### 44 ca fail là lỗi môi trường, không phải lỗi code

Chúng nằm ở `test_retrieval_sql` (cần dữ liệu thuốc đã seed vào DB), `test_agent_v2_*` (cần cấu hình runtime), `test_api/test_auth_routes` (cần cấu hình email), và prescription shadow mode. **Không ca nào thuộc luồng nghiệp vụ chính.**

Cách chúng tôi phân biệt "lỗi có sẵn" với "mình vừa làm vỡ": chạy suite ở commit gốc, lưu danh sách FAILED đã sort, chạy lại sau khi sửa, rồi `diff` hai danh sách. **Giống hệt = không vỡ gì.** Cách này hợp lệ kể cả khi cả hai lần đều có lỗi môi trường.

Chi tiết cách chạy và cách so sánh baseline: xem `adrs/0001-test-strategy.md`.

---

## 9. Tự đánh giá — mạnh ở đâu, yếu ở đâu

**Mạnh**
- Hallucination **0%** với grounding **100%**, đo lại 2 lần ở `temperature=0`.
- Red team **14/14**, phủ 7 nhóm tấn công gồm cả obfuscation Unicode.
- Confidence gating của Vision biến một mô hình 48% thành luồng vận hành an toàn.
- Mọi số liệu **tái tạo được** — script và dữ liệu đều nằm trong `eval/`.

**Yếu — và đã biết**
- recall@k 68,75%: nhóm câu hỏi **tác dụng phụ** trượt nhiều nhất.
- **1/6 ca cross-drug lọt** qua bộ lọc.
- Guardrail regex đầu vào bị 2 ca paraphrase/obfuscation vượt qua.
- Golden set VLM mới 25 ảnh, nhóm `cao` chỉ 9 ca — chưa đủ để chốt con số.
- Bộ RAG ground truth mới 32 câu trên 8 thuốc, chưa phủ hết 11 nhóm thuốc trong dữ liệu.

---

## 10. Tái tạo kết quả

```bash
# RAG: retrieval + grounding + cross-drug
python eval/run_eval.py

# Red team
python -c "import eval.redteam_prompts"        # bộ ca tấn công
# báo cáo: eval/redteam_report.json

# Safety layer
python eval/safety_llm_check.py

# Drug reply gate
python eval/drug_reply_gate_check.py

# Persona
python eval/soul_persona_check.py

# Vision / VLM đếm thuốc
python eval/eval_vlm/run_eval_vlm.py

# Test suite
pytest tests/ -q
```

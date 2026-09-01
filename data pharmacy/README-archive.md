# Dữ liệu crawl thô đã được nén

**Ngày nén:** 2026-09-01 · **File:** `_archive-crawl-raw.zip` (57,7 MB, nén từ 381 MB)

## Đã nén những gì

| Nhánh | Số file | Dung lượng gốc |
|---|---:|---:|
| `v2/rag_eval/` | 3 | 101 MB |
| `v2/full_recrawl/` (các file `.jsonl` ở gốc thư mục) | 17 | 97 MB |
| `v2/full_recrawl/reparse/` | 18 | 92 MB |
| 8 file `.jsonl`/`.json` nằm trực tiếp trong `v2/` | 8 | 81 MB |
| `v2/raw_snapshots/longchau/` | 48 | 10 MB |
| **Tổng** | **94** | **381 MB** |

Đây là **bản trung gian và bản trùng** của quá trình crawl — trong đó có bản `v2/drug_knowledge.jsonl` 76 MB trùng với `final_canonical/`, và `rag_eval/` trùng với `final_canonical/rag/`.

## Những gì KHÔNG nén — và vì sao

### `v2/full_recrawl/raw_snapshots/` (7.113 file, 1.210 MB) — GIỮ NGUYÊN

Ban đầu thư mục này nằm trong danh sách nén, nhưng test suite bắt được lỗi:

- `scripts/data_v2/drug_image_collection.py:37` đọc `FULL_RECRAWL_RAW_DIR` từ đây
- `tests/data_v2/test_drug_image_collection.py::test_frozen_catalog_maps_only_b02_eligible_products` kiểm tra đúng 3.545 bản ghi dựng từ nó

Nén nó làm test này fail (`assert 0 == 3545`). Đã khôi phục và đưa lại vào git.

### `v2/final_canonical/` — GIỮ NGUYÊN

`Dockerfile:50-51` **COPY thẳng 7 file** từ đây vào image lúc build:

```
manifest.json · drug_product.jsonl · drug_id_map.jsonl · drug_product_ingredient.jsonl
drug_knowledge.jsonl · rag/v2_chunks.jsonl · rag/v2_embedding_index.jsonl
```

`COPY` **không đọc được vào bên trong zip**. Nén thư mục này sẽ làm build fail ở cả local lẫn Railway, và backend chết lúc khởi động (`backend/services/drug_knowledge/v2_agent.py:29` đọc nó khi `drug_knowledge_backend="v2"` — là mặc định).

### Các nhánh khác giữ nguyên

| Nhánh | Ai đọc |
|---|---|
| `v2/rag_openai/` | `scripts/agent_v2/run_deterministic_rag_evaluation.py`, `verify_rag_corpus_identity.py` |
| `data-version1/` | `backend/services/rag_corpus_recovery.py` |
| `reports/` | `scripts/agent_v2/live_golden_validation.py` và nhiều tài liệu |

## Giải nén khi cần chạy lại pipeline crawl

```bash
cd "data pharmacy"
unzip _archive-crawl-raw.zip -d ../
```

Zip giữ nguyên đường dẫn tương đối từ gốc repo nên giải nén xong file về đúng chỗ cũ.

## Lưu ý

- Zip **không được commit** (đã thêm vào `.gitignore`).
- Việc này làm HEAD gọn hơn 94 file và ổ đĩa nhẹ đi ~381 MB, nhưng **không giảm dung lượng clone**: lịch sử git vẫn giữ các file cũ. Muốn giảm thật phải `git filter-repo` + force-push, rewrite lịch sử chung.

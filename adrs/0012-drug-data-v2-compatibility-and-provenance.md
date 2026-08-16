# ADR-0012: Drug Data V2 Compatibility And Provenance

**Status:** Proposed  
**Ngày:** 2026-08-16  
**Người đề xuất:** Nguyễn Minh Đạt + AI  
**Người duyệt:** `[chờ Architect/Tech Lead review]`

## Bối cảnh (Context)

Dataset thuốc hiện tại có 3.562 records trong `data pharmacy/*/thuoc.json`, đã được app dùng qua
`drug`, `drug_chunks`, `PrescriptionDTO.items[].drug_id`, `DrugInfoDTO.drug_id` và nhiều node/tool
agent. Dữ liệu này chưa có raw snapshot, source URL, retrieved time per record, nhưng đang đủ để demo
và không nên bị thay thế trực tiếp trong lúc runtime còn phụ thuộc vào V1.

Data Rebuild V2 cần tạo canonical schema, provenance và knowledge typing tốt hơn, nhưng vẫn phải giữ
app chạy ổn định trong giai đoạn migration.

## Quyết định (Decision)

1. **Legacy freeze cho đồ án/demo:** giữ dataset hiện tại read-only và dùng manifest SHA256 hiện có
   làm freeze artifact cho `legacy-v1`. Chưa xây archive/storage phức tạp.
2. **Drug identity:** public `drug_id` tiếp tục là legacy slug trong giai đoạn migration. V2 dùng
   `drug_product.id = UUID` làm internal ID và có mapping:

   ```text
   drug_id_map
   legacy_drug_id
   drug_product_id
   ```

   Chỉ đổi public contract sang UUID nếu có ADR riêng và migration plan cho prescription, fixtures,
   API, frontend và eval.
3. **V1/V2 song song:** V2 được xây bên cạnh V1. Runtime đi qua facade với feature flag:

   ```text
   DRUG_KNOWLEDGE_BACKEND=v1|v2|shadow
   ```

   `shadow` trả response từ V1 nhưng chạy V2 song song để so sánh chất lượng.
4. **Raw snapshot storage:** với quy mô 3.562 thuốc/demo, dùng filesystem raw JSON và metadata trong
   DB. Chưa dùng object storage.
5. **Ingredient parser:** parse conservatively. Chỉ parse structured khi chắc chắn; không chắc thì
   giữ `raw_ingredient`/`raw_strength` và ghi warning. Không đoán.

## Vì sao (Rationale)

Phương án đổi public `drug_id` sang UUID ngay bị loại vì làm vỡ nhiều consumer đang dùng slug:
prescription join, fixture eval, API contract, frontend, retrieval và agent tools. UUID vẫn cần cho
canonical V2, nhưng dùng nội bộ là đủ cho phase migration.

Phương án full re-crawl/full storage ngay bị loại vì không cần cho demo-quality scope và làm tăng rủi
ro rate-limit/chặn IP. Raw snapshot V2 vẫn phải có cho dữ liệu mới/recrawl, nhưng legacy corpus có thể
được đánh dấu `LEGACY_NO_RAW_SOURCE` rồi nâng cấp theo batch.

Phương án object storage bị loại trong giai đoạn này vì dataset nhỏ, repo đang là đồ án/demo và nhu cầu
truy xuất chủ yếu là reproducibility nội bộ. Filesystem raw JSON + metadata DB đủ đơn giản để team và AI
debug được.

Phương án parser aggressive bị loại vì dữ liệu y tế không nên được “làm đẹp” bằng suy đoán. Structured
data sai nguy hiểm hơn raw text có warning.

## Vì sao thân thiện với AI + Team

- Agent có contract rõ: giữ slug public, dùng UUID nội bộ, không tự đổi identity.
- Agent có chiến lược migration rõ: V1 vẫn chạy, V2 shadow trước, cutover sau khi có số liệu.
- Parser có nguyên tắc fail-safe: không chắc thì giữ raw + warning, không đoán.
- Team có artifact freeze đủ nhẹ để truy vết mà không phải vận hành storage phức tạp.

## Hệ quả (Consequences)

**Tích cực:**
- App tiếp tục chạy bằng V1 trong khi V2 được xây song song.
- Prescription và frontend không bị breaking change ngay.
- Có đường rollback đơn giản về `DRUG_KNOWLEDGE_BACKEND=v1`.
- V2 có nền provenance tốt hơn cho dữ liệu mới/recrawl.

**Đánh đổi / rủi ro:**
- Trong giai đoạn migration sẽ tồn tại hai ID space: legacy slug và UUID nội bộ.
- Legacy data vẫn không có raw provenance đầy đủ cho đến khi được recrawl theo batch.
- Filesystem raw JSON đủ cho demo nhưng có thể phải nâng lên object storage nếu chuyển production.
- Ingredient structured coverage ban đầu có thể thấp vì parser conservative.

## Câu chốt

> Xây V2 bên cạnh V1: slug vẫn là hợp đồng ngoài, UUID là lõi nội bộ, provenance tăng dần và không đoán dữ liệu y tế.

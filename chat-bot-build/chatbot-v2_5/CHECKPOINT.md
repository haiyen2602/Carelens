# CapyMedi V2.5 — CHECKPOINT

> Runbook thực thi V2.5 từ governance đến đánh giá người dùng. Tài liệu thiết kế nguồn là [V2.5-DESIGN.md](./V2.5-DESIGN.md).

## Trạng thái khởi động

| Câu hỏi | Trạng thái | Ý nghĩa |
|---|---|---|
| Có thể bắt đầu Phase 0? | **Đã hoàn tất** | ADR, baseline approach và Task 01 đã được chốt trong `CP0-ADR-BASELINE-TASK01.md`. |
| Có thể bắt đầu code runtime? | **Chưa cho Task 02** | Task 01 đóng dưới dạng discovery closure (bug gốc đã fixed upstream, không cần runtime change — xem `TASK-V2.5-001`). Task 02 (context/follow-up, range anaphora) đang ở CP1: baseline/AC đã chốt (`TASK-V2.5-002`), còn một câu hỏi thiết kế mở (durable state field vs short-term memory) cần trả lời trước khi code. Task 03–04 vẫn theo gate và capability flag riêng. |
| Có thể deploy Railway? | **Chưa** | Chỉ sau local quality gate, PR review và canary gate. |
| OCR/VLM nằm trong canary chat đầu? | **Không** | Đây là track riêng, chỉ xem xét lại sau B-08 re-evaluation `PASS`. |

Không dùng `CHAT_RUNTIME=legacy` làm feature gate V2.5. Mỗi capability có flag, owner, cohort, metric query, stop condition và rollback độc lập.

## Cách dùng checklist

- Mỗi checkpoint chỉ được đánh dấu khi có link hoặc bằng chứng tương ứng trong PR/task.
- Không vượt checkpoint khi còn ô chưa đánh dấu ở phần **Gate đi tiếp**.
- Không đưa raw patient text, raw fact, tool payload hay PHI vào report, golden fixture, telemetry hoặc issue.
- Mỗi capability release đầu phải giữ nguyên boundary: safety, emergency, clinical instruction, doctor takeover, timeout/error và handoff safety vẫn là deterministic/fixed response.

---

## CP0 — Governance và baseline

**Mục tiêu:** chuyển thiết kế Proposed thành phạm vi implementation được phê duyệt; chưa thay đổi runtime hay Railway.

CP0 xuất ra **một PR nhỏ duy nhất** gộp cả ba artifact (ADR + baseline report
+ task đầu tiên) — không phải một quy trình nhiều vòng/nhiều vai trò tách
biệt. Đổi renderer/ResponsePolicy vẫn là quyết định kiến trúc nên vẫn cần ADR
theo AGENTS.md, nhưng ở quy mô đội hiện tại, PM/Architect/Release owner có
thể là cùng một người; điều bắt buộc là accountability + bằng chứng ghi lại,
không phải số người ký duyệt riêng biệt.

- [ ] Chỉ định người chịu trách nhiệm (PM/Architect/Release owner có thể trùng một người) và reviewer cho V2.5.
- [ ] Trong ADR ngắn: chốt scope canary đầu, boundary V2/V3, capability flag, rollback ownership.
- [ ] Trong ADR ngắn: chốt ownership renderer — tái sử dụng `synthesize_read_only` **hoặc** component mới. Một request chỉ có một renderer sở hữu patient-facing prose.
- [ ] Trong ADR ngắn: chốt `soul_v3.md` được reuse trực tiếp; ResponseAST/FactSlot của V3 chỉ dùng làm tài liệu tham chiếu — V2.5 tự định nghĩa `RenderableFactSlots` riêng và viết adapter tối thiểu quanh `synthesize_read_only`, không import/wire contract hay runtime V3 vào V2.
- [ ] Trong ADR ngắn: chốt model-call budget, timeout, fallback deterministic/clarification/handoff và privacy boundary của durable audit so với telemetry.
- [ ] Chạy preflight bắt buộc cho `gpt-5.6-luna` bằng input tổng hợp không chứa PHI: xác minh model khả dụng với credential thực tế trên account/Railway hiện tại (production hiện mặc định `gpt-5.4-mini`, xem `backend/config.py:52` — việc `gpt-5.6-luna` xuất hiện trong tài liệu V3 KHÔNG chứng minh gọi được), structured-output conformance, hành vi fallback khi lỗi, P95 latency và chi phí. Ghi kết quả vào baseline report; nếu fail, Phase 3 dùng lại `gpt-5.4-mini` hoặc dừng ở Phase 2.
- [ ] Tạo baseline de-identified cho tối đa ba pain point production: evidence/window đo, golden coverage, safety impact, latency/cost và metric sau thay đổi.
- [ ] Chọn capability implementation đầu tiên trong **ba capability production**: renderer, context/follow-up, clarification. `ResponsePolicy` là hạ tầng dùng chung cho cả ba, không tính là capability riêng, không có flag/canary/cohort/rollback độc lập của chính nó.
- [ ] Tạo task đầu tiên có AC/DoD, flag, owner, cohort, golden suite (bao gồm case "prose tự do" cho renderer — xem CP1), metric query, stop condition và rollback criteria.
- [ ] Xác minh thực tế feature-flag source of truth, Railway release flow và rollback path; không giả định chúng đã tồn tại.

**Gate đi tiếp:** một PR nhỏ gộp đủ ADR + baseline report + task implementation đầu tiên, và preflight `gpt-5.6-luna` đã có kết quả (pass hoặc fallback quyết định), được người phụ trách chấp nhận. Nếu thiếu một trong các phần này, dừng ở CP0.

---

## CP1 — Sẵn sàng implementation theo capability

**Mục tiêu:** giới hạn thay đổi vào một capability có thể rollback độc lập.

- [ ] Tạo branch `feature/<TASK-NAME>` từ commit mới nhất; không commit trực tiếp vào `main`.
- [ ] Liên kết task với ADR, baseline pain point và source code V2 bị ảnh hưởng.
- [ ] Chốt contract `ResponsePolicy`, `RenderableFactSlots` và audit metadata tách biệt.
- [ ] Xác định fact nhạy cảm của capability (liều, giờ, dose status, confirmed medication identity, handoff state) phải backend-render/template-render.
- [ ] Xác định deterministic fallback cụ thể khi renderer timeout hoặc output invalid; không retry vô hạn, không silent per-request fallback sang legacy.
- [ ] Viết test plan gồm unit, golden/regression và local E2E; fixture chỉ dùng dữ liệu de-identified. Với capability renderer, test plan **bắt buộc** có nhóm case "prose tự do" kiểm renderer không tự chèn liều/giờ/dose status/medication identity/handoff state vào câu dẫn/chuyển ý ngoài `RenderableFactSlots` — đây là đảm bảo kỹ thuật quan trọng nhất của V2.5, thiếu nhóm case này thì capability chưa đủ AC.
- [ ] Ghi kết quả baseline local de-identified vào tab V2.5 đã chỉ định của [golden sheet](https://docs.google.com/spreadsheets/d/1wv-9p4oTuJ_0ErPCij4gh9eENLmd-qzbjMr8mWSOE3Y/edit?gid=1151888176#gid=1151888176), theo cấu trúc tab 15/08/2026: timestamp, commit SHA, environment `local`, config/model version, golden-set version, exact command, pass/fail aggregate và notes. Chỉ append; không sửa tab lịch sử và không ghi PHI, raw chat, raw tool payload hoặc secret.
- [ ] Khai báo flag mặc định **off**, owner, cohort rỗng/allowed internal và thao tác rollback.

**Gate đi tiếp:** reviewer xác nhận task có AC/DoD rõ ràng, contracts không làm lẫn ba lớp dữ liệu và có rollback cụ thể.

---

## CP2 — Build và kiểm thử ở local

**Mục tiêu:** chứng minh V2.5 không làm suy giảm V2 trước khi có bất kỳ Railway canary nào.

- [ ] Cài đặt đúng phạm vi task; không mở rộng sang OCR/VLM hoặc thay Safety Domain/doctor takeover/authorization khi chưa có ADR mới.
- [ ] Thêm unit test cho policy boundary, fact-slot rendering, invalid renderer output và deterministic fallback.
- [ ] Thêm/điều chỉnh golden suite cho pain point được chọn và các wording low-risk được phép thay đổi, gồm cả nhóm case "prose tự do" đã định nghĩa ở CP1 và chạy chúng thật (không chỉ khai báo trong test plan).
- [ ] Chạy lại regression V2: emergency, possible overdose, missed/delayed dose, schedule/dose status, doctor takeover, auth/patient isolation và out-of-scope theo phạm vi ảnh hưởng.
- [ ] Chạy lint/format, targeted tests, V2 golden suite, V2.5 golden suite và build ở local; lưu exact command, commit và kết quả.
- [ ] Thực hiện local E2E bằng dữ liệu de-identified. Nếu gọi model thật, tách kết quả eval khỏi deterministic CI test và ghi model/config/version/budget đã dùng.
- [ ] So sánh candidate với baseline: safety outcome, grounding/clarification quality, error rate, latency và cost theo metric trong task.
- [ ] Xác minh log/telemetry mới chỉ chứa safe references, status/reason code; không leak PHI/raw facts/tool payload.

**Gate đi tiếp:** toàn bộ local test/build pass, không có safety regression hay cross-patient leak, và metric không vượt stop condition đã phê duyệt. Nếu fail, sửa hoặc tắt flag tại local rồi chạy lại CP2.

---

## CP3 — PR và quyết định merge

**Mục tiêu:** thay đổi có thể review, truy vết và rollback trước khi vào production.

- [ ] Cập nhật task status, docs, contracts/ADR khi cần và release notes nội bộ.
- [ ] Commit nhỏ theo convention `<TASK-ID>: <động từ mô tả ngắn>`.
- [ ] Push branch chỉ sau khi CP2 pass.
- [ ] Tạo PR có linked task, baseline comparison, test evidence, config/flag default, owner, cohort, metric query, stop condition và rollback instructions.
- [ ] Reviewer kiểm tra code, test, privacy, contract compatibility và scope V2.5/V3.
- [ ] Có approval theo `TEAM.md` và đạt DoD/CI trước merge.

**Gate đi tiếp:** người có thẩm quyền merge PR đã approve. AI không tự merge vào `main`.

---

## CP4 — Railway release và canary có kiểm soát

**Mục tiêu:** rollout từng capability, giữ V2 ổn định làm baseline và rollback nhanh khi có dấu hiệu xấu.

- [ ] Release owner ghi exact merged commit, deploy/config snapshot, flag, owner và cohort trước khi rollout.
- [ ] Deploy với capability flag **off**; kiểm tra healthcheck, route V2 hiện hữu, authorization và doctor takeover không bị ảnh hưởng.
- [ ] Thực hiện observe-only/shadow nếu ADR của capability yêu cầu; không dùng kết quả đó để tạo patient-facing response.
- [ ] Bật internal allowlist trước, sau đó small canary theo cohort được chấp thuận.
- [ ] Theo dõi metric query đã chốt: safety/handoff correctness, error rate, latency, model cost, grounding/clarification outcome và privacy signal.
- [ ] Ghi nhận quyết định tiếp tục, giữ canary, rollback hoặc ramp cùng timestamp và release owner.
- [ ] Chỉ ramp khi canary đạt tiêu chí success trong cửa sổ đánh giá đã phê duyệt.

**Stop và rollback ngay:** safety regression, handoff sai loại, cross-patient data/state leak, bypass evidence/safety boundary, state corrupt, hoặc metric vượt threshold đã phê duyệt.

**Thứ tự rollback:**

1. Tắt đúng capability flag V2.5.
2. Release owner rollback deployment/code nếu cần.
3. Chỉ dùng `CHAT_RUNTIME=legacy` khi toàn bộ V2 runtime gặp sự cố nghiêm trọng — không dùng làm fallback tự động cho từng request lỗi.

**Gate đi tiếp:** canary ổn định và release owner phê duyệt mở đánh giá người dùng. Không tự động ramp chỉ vì deploy thành công.

---

## CP5 — Đánh giá người dùng và quyết định giữ/rút capability

**Mục tiêu:** xác nhận thay đổi thực sự bớt máy móc và hữu ích, đồng thời không đánh đổi safety/grounding.

- [ ] Chọn nhóm người dùng canary được phép và thông báo đúng phạm vi capability đang thử nghiệm.
- [ ] Thu phản hồi có cấu trúc sau các phiên phù hợp: dễ hiểu hơn không, tự nhiên hơn không, có làm rõ đúng chỗ không, có giữ đúng thông tin quan trọng không, next step có hữu ích không.
- [ ] Không sao chép PHI/raw chat vào report phản hồi; chỉ lưu dữ liệu đã de-identify hoặc aggregate theo policy.
- [ ] Đối chiếu feedback với metric production và baseline local; tách lỗi wording khỏi lỗi safety/grounding.
- [ ] Ghi quyết định: ramp, giữ cohort hiện tại để sửa, hoặc rollback. Nêu owner và task tiếp theo.
- [ ] Cập nhật backlog V3 cho mọi nhu cầu vượt boundary V2.5 (planner/generator/reviewer/workflow mới).

**Hoàn thành capability:** có evidence local + canary + user evaluation, không có stop condition, docs/task đã cập nhật, và có quyết định release được owner phê duyệt.

---

## Bảng theo dõi thực thi

Điền bảng này cho từng capability; không dùng một flag chung cho toàn bộ V2.5.
`ResponsePolicy` không phải capability production nên không có hàng/flag/cohort
riêng — trạng thái của nó (contract version, adapter quanh `synthesize_read_only`)
được ghi trong ADR/task của capability đầu tiên dùng nó, không tracked độc lập
ở đây.

| Capability | Task/PR | Owner | Flag | Cohort | Baseline | Local gate | Canary decision | User evaluation | Rollback owner |
|---|---|---|---|---|---|---|---|---|---|
| Natural renderer | _Chưa tạo_ |  |  |  |  |  |  |  |  |
| Context/follow-up | `TASK-V2.5-002` (CP1, chưa code) | Dyo31122005 | `AGENT_V2_5_FOLLOWUP_ENABLED` (off) | — |  |  |  |  |  |
| Clarification | _Chưa tạo_ |  |  |  |  |  |  |  |  |

OCR/VLM không điền vào bảng này cho release đầu. Chỉ tạo checkpoint riêng sau khi B-08 re-evaluation đạt `PASS` với independent real-phone dataset, Vietnamese OCR ground truth, hard-negative/unknown set, deployment-equivalent test và canary evidence.

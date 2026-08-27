import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const queuePage = await readFile(
  new URL("../src/app/doctor/reviews/page.tsx", import.meta.url),
  "utf8",
);
const detailPage = await readFile(
  new URL("../src/app/doctor/reviews/[id]/page.tsx", import.meta.url),
  "utf8",
);
const reviewClient = await readFile(
  new URL("../src/lib/doctor-reviews.ts", import.meta.url),
  "utf8",
);
const imageProxy = await readFile(
  new URL(
    "../src/app/api/doctor/reviews/[id]/image-attachments/[attachmentId]/route.ts",
    import.meta.url,
  ),
  "utf8",
);
const cancelProxy = await readFile(
  new URL("../src/app/api/doctor/reviews/[id]/cancel/route.ts", import.meta.url),
  "utf8",
);

// Queue does not invent a clinical severity: it renders the backend handoff
// type and makes the Safety state unambiguous to doctors.
assert.match(queuePage, /Cần ưu tiên an toàn/);
assert.match(queuePage, /Chatbot chưa thể trả lời/);
assert.match(queuePage, /router\.push\(`\/doctor\/reviews\/\$\{item\.handoffId\}`\)/);
assert.match(queuePage, /aria-pressed=\{assignedToMeOnly\}/);
assert.match(queuePage, /Tìm tên, mã bệnh nhân hoặc nội dung/);
assert.match(queuePage, /Sắp xếp hàng đợi/);
assert.match(queuePage, /Mới nhất/);
assert.match(queuePage, /Cũ nhất/);
assert.match(queuePage, /CANCELLED/, "Queue exposes cancelled handoffs to doctors.");

// Active polling is background-only: the initial loading state is not reused
// by the five-second refresh, and Vietnamese IME composition cannot send a
// message prematurely.
assert.match(detailPage, /const \[initialLoading, setInitialLoading\] = useState\(true\)/);
assert.match(detailPage, /window\.setInterval\(\(\) => void load\(true\), 5_000\)/);
assert.match(detailPage, /!event\.nativeEvent\.isComposing/);
assert.match(detailPage, /Kết thúc trao đổi với \{detail\.patientName\}\?/);
assert.match(detailPage, /Huỷ ca của \{detail\.patientName\}\?/);
assert.match(detailPage, /"cancel"/);
assert.match(detailPage, /Tin nhắn mới/);
assert.match(detailPage, /ReviewImageAttachment/);

// Attachments keep the user's Authorization header through a private proxy;
// no public URL or client-supplied storage key is introduced.
assert.match(reviewClient, /imageAttachmentId: string \| null/);
assert.match(reviewClient, /getDoctorReviewImageAttachment/);
assert.match(reviewClient, /cancelDoctorReview/);
assert.match(imageProxy, /forwardAuthorization\(request\)/);
assert.match(imageProxy, /Cache-Control": "private, no-store/);
assert.match(imageProxy, /image-attachments/);
assert.match(cancelProxy, /forwardAuthorization\(request\)/);
assert.match(cancelProxy, /\/cancel/);

console.log("doctor review UI contract checks passed");

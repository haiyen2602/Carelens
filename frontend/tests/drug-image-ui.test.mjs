import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const medicationImage = await readFile(
  new URL("../src/components/medication-image.tsx", import.meta.url),
  "utf8",
);
const assistantPage = await readFile(
  new URL("../src/app/patient/assistant/page.tsx", import.meta.url),
  "utf8",
);
const chatMessage = await readFile(
  new URL("../src/components/chat-message.tsx", import.meta.url),
  "utf8",
);
const chatHistory = await readFile(new URL("../src/lib/chat-history.ts", import.meta.url), "utf8");
const apiClient = await readFile(new URL("../src/lib/api.ts", import.meta.url), "utf8");
const recognitionProxy = await readFile(
  new URL("../src/app/api/drug-images/recognize/route.ts", import.meta.url),
  "utf8",
);

// A catalog photo stays bound to the exact B-06 availability response; the
// new preview must not make a name-based or public-image fallback possible.
assert.match(medicationImage, /image\.status !== "AVAILABLE"/);
assert.match(medicationImage, /Authorization: `Bearer \$\{accessToken\}`/);
assert.match(medicationImage, /Xem ảnh thuốc \$\{drugName\}/);
assert.match(medicationImage, /<Dialog open=\{previewOpen\}/);
assert.match(medicationImage, /Ảnh bao bì thuốc đã được xác thực cho đơn của bạn/);
assert.doesNotMatch(medicationImage, /display_name.*fetch|fetch.*display_name/s);

// Both entries in the + menu use the established B-07 file/recognition flow.
assert.match(assistantPage, /aria-label="Chụp ảnh thuốc"/);
assert.match(assistantPage, /setCameraOpen\(true\)/);
assert.match(assistantPage, /aria-label="Tải ảnh thuốc lên"/);
assert.match(assistantPage, /imageInputRef\.current\?\.click\(\)/);
assert.match(assistantPage, /<CameraCapture/);
assert.match(assistantPage, /recognizeDrugImage\(/);
assert.match(assistantPage, /URL\.createObjectURL\(file\)/);
assert.match(assistantPage, /Đang phân tích ảnh\.\.\./);
assert.ok(
  assistantPage.indexOf("await recognizeDrugImage(") <
    assistantPage.indexOf('appendMessage(activeId, "user", text || "Đã gửi ảnh thuốc.",'),
  "the UI must not persist a successful upload bubble before the request is accepted",
);
assert.match(assistantPage, /imageAttachment: \{ fileName: image\.name, previewUrl \}/);
assert.match(assistantPage, /outcome: data\.outcome/);
assert.match(assistantPage, /decision: "REJECTED"/);
assert.doesNotMatch(assistantPage, /base64/);
assert.doesNotMatch(assistantPage, /Paperclip|Đính kèm ảnh gói thuốc|chưa nối API/);

// The user bubble uses an in-memory object URL and keeps only its filename
// after localStorage serialization. Candidate UI is deliberately one-card,
// high-evidence-only: ambiguous outcomes cannot leak candidate names.
assert.match(chatMessage, /message\.imageAttachment\.previewUrl/);
assert.match(chatMessage, /Ảnh thuốc đã gửi:/);
assert.match(chatMessage, /HIGH_EVIDENCE_MATCH/);
assert.match(chatMessage, /candidates\.length === 1/);
assert.match(chatMessage, /Đúng thuốc này/);
assert.match(chatMessage, /Không đúng/);
assert.doesNotMatch(chatMessage, /Không phải thuốc nào ở trên/);
assert.match(chatHistory, /Blob URLs die at page unload/);
assert.match(chatHistory, /imageAttachment: \{ fileName: message\.imageAttachment\.fileName \}/);
assert.match(apiClient, /decision: payload\.decision \?\? "CONFIRMED"/);

// The proxy forwards genuine multipart form data and authorization. It must
// not stringify the image or set a multipart boundary itself.
assert.match(recognitionProxy, /form = await request\.formData\(\)/);
assert.match(recognitionProxy, /Authorization: authorization/);
assert.match(recognitionProxy, /body: form/);
assert.doesNotMatch(recognitionProxy, /Content-Type.*multipart\/form-data/);
assert.match(recognitionProxy, /RECOGNITION_UPSTREAM_UNAVAILABLE/);

console.log("drug-image UI contract checks passed");

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
assert.doesNotMatch(assistantPage, /Paperclip|Đính kèm ảnh gói thuốc|chưa nối API/);

console.log("drug-image UI contract checks passed");

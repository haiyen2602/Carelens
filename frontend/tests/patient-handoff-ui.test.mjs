import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const assistantPage = await readFile(
  new URL("../src/app/patient/assistant/page.tsx", import.meta.url),
  "utf8",
);
const handoffClient = await readFile(
  new URL("../src/lib/patient-handoff.ts", import.meta.url),
  "utf8",
);

// The server-backed direct thread is rendered in the primary chat feed. The
// old nested card must not be retained once a direct conversation ends.
assert.match(
  assistantPage,
  /const activeHandoff = handoff\?\.status === "ACTIVE" \? handoff : null/,
);
assert.match(assistantPage, /aria-label="Trao đổi trực tiếp với bác sĩ"/);
assert.doesNotMatch(assistantPage, /Cuộc trò chuyện với bác sĩ đã kết thúc/);
assert.match(assistantPage, /if \(data\.status === "DOCTOR_ACTIVE"\)/);
assert.match(assistantPage, /Do not duplicate that/);
assert.match(assistantPage, /setHandoff\(null\)/);
assert.match(assistantPage, /Nhắn cho bác sĩ/);
assert.match(handoffClient, /stopPatientHandoff/);

console.log("patient handoff UI contract checks passed");

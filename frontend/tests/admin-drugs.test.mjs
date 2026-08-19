import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const page = await readFile(
  new URL("../src/app/admin/medicines/page.tsx", import.meta.url),
  "utf8",
);
const client = await readFile(new URL("../src/lib/admin-drugs.ts", import.meta.url), "utf8");

const url = new URL("http://localhost:8000/api/v1/admin/drugs");
url.search = new URLSearchParams({
  page: "2",
  page_size: "20",
  q: "para",
  mapping_status: "ACTIVE",
}).toString();
assert.equal(url.searchParams.get("page_size"), "20");
assert.equal(url.searchParams.get("mapping_status"), "ACTIVE");
assert.match(client, /Authorization: `Bearer/);
assert.match(client, /mapping_status/);
assert.match(page, /listAdminDrugs/);
assert.match(page, /role="alert"/);
assert.match(page, /Không tìm thấy dữ liệu thuốc phù hợp/);
assert.match(page, /setPage\(\(current\) => current \+ 1\)/);
assert.match(page, /setTimeout\(\(\) =>/);
assert.doesNotMatch(
  page,
  /Dữ liệu minh hoạ|Nạp dữ liệu mới|Index lại|simulateImport|reindex|MEDICINES/,
);

console.log("admin-drugs frontend contract checks passed");

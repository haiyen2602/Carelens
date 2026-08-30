import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const loginRoute = await readFile(
  new URL("../src/app/api/auth/login/route.ts", import.meta.url),
  "utf8",
);

assert.match(loginRoute, /try\s*\{\s*backendResponse = await fetch/s);
assert.match(loginRoute, /catch\s*\{\s*return NextResponse\.json/s);
assert.match(loginRoute, /status:\s*503/);
assert.match(loginRoute, /backend local tại localhost:8000/);

console.log("auth login proxy tests passed");

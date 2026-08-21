import assert from "node:assert/strict";
import test from "node:test";
import { forwardAuthorization } from "./authorization.ts";

test("forwards the browser bearer token to the backend", () => {
  const request = new Request("https://example.test/api/accounts", {
    headers: { Authorization: "Bearer admin-jwt" },
  });

  assert.deepEqual(forwardAuthorization(request), {
    Authorization: "Bearer admin-jwt",
  });
});

test("does not fabricate authorization when the browser sends none", () => {
  const request = new Request("https://example.test/api/accounts");

  assert.deepEqual(forwardAuthorization(request), {});
});

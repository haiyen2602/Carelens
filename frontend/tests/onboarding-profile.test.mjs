import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const onboardingPage = await readFile(
  new URL("../src/app/onboarding/profile/page.tsx", import.meta.url),
  "utf8",
);
const patientRoutes = await readFile(
  new URL("../../backend/api/patient_routes.py", import.meta.url),
  "utf8",
);
const authRoutes = await readFile(
  new URL("../../backend/api/auth_routes.py", import.meta.url),
  "utf8",
);

assert.match(onboardingPage, /getMyPatientProfile/);
assert.match(onboardingPage, /updateMyPatientProfile/);
assert.match(onboardingPage, /!heightCm \|\| !weightKg/);
assert.match(onboardingPage, /profile\.profileCompleted/);
assert.match(onboardingPage, /required/);
assert.match(patientRoutes, /is_patient_profile_complete\(profile_after_update\)/);
assert.match(
  patientRoutes,
  /Vui lòng nhập ngày sinh, số điện thoại, địa chỉ, giới tính, chiều cao và cân nặng/,
);
assert.match(authRoutes, /is_patient_profile_complete\(patient\)/);

console.log("onboarding profile contract checks passed");

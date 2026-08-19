# Admin Account Management Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Hoàn thiện trang Admin quản lý tài khoản với ba tab nhóm, tìm kiếm/lọc, tạo doctor/admin và khoá/mở khoá.

**Architecture:** Giữ nguyên Next.js client page và các hàm API hiện có. Tải danh sách một lần bằng React Query, lọc client-side theo nhóm (`patient` + `caregiver`, `doctor`, `admin`), từ khoá và trạng thái; không thay đổi backend contract.

**Tech Stack:** Next.js App Router, React, TypeScript, TanStack React Query, shadcn/ui, lucide-react, npm scripts hiện có.

---

### Task 1: Add account-group tab state and derived filtering

**Files:**
- Modify: `frontend/src/app/admin/accounts/page.tsx`
- Test: manual browser verification of the existing page

- [ ] **Step 1: Define the group type and initial tab**

Add `AccountGroup = "patients" | "doctors" | "admins"`, initialize the active group to `patients`, and remove the independent role filter state because the tab owns role grouping.

- [ ] **Step 2: Implement group membership**

Derive the visible set with this exact rule:

```ts
const matchesGroup =
  activeGroup === "patients"
    ? account.role === "patient" || account.role === "caregiver"
    : activeGroup === "doctors"
      ? account.role === "doctor"
      : account.role === "admin";
```

Keep text search case-insensitive across `fullName` and `email`, and keep status filtering for `all | active | locked | pending`.

- [ ] **Step 3: Add the three tabs**

Render buttons or the existing tab primitive with labels `Bệnh nhân`, `Bác sĩ`, `Admin`. Show the filtered count for the active group and use an active visual state consistent with the existing admin shell.

- [ ] **Step 4: Remove caregiver from standalone role controls**

Delete the old role select and ensure no standalone `caregiver` option is rendered. Keep role badges in rows so caregiver records remain identifiable inside the Bệnh nhân tab.

- [ ] **Step 5: Verify the derived list manually**

Run the frontend dev server and verify that patient and caregiver records appear only in Bệnh nhân, doctor records only in Bác sĩ, and admin records only in Admin. Confirm search and status filter apply within the selected tab.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/app/admin/accounts/page.tsx
git commit -m "feat(admin): group account list by role tabs"
```

### Task 2: Restrict and simplify account creation

**Files:**
- Modify: `frontend/src/app/admin/accounts/page.tsx`
- Modify: `frontend/src/lib/accounts.ts`
- Test: manual dialog validation and request inspection

- [ ] **Step 1: Restrict create button visibility**

Render `Tạo tài khoản` only when `activeGroup` is `doctors` or `admins`; hide it on Bệnh nhân.

- [ ] **Step 2: Narrow the create form model**

Change the local form role default to `doctor` and remove `patientId` and `doctorId` from the form state, reset state, conditional JSX, and mutation payload.

- [ ] **Step 3: Render only doctor/admin role options**

Replace iteration over all `roleLabel` keys with explicit `doctor` and `admin` options. The selected role must remain typed as `Extract<AccountRole, "doctor" | "admin">` or be validated before mutation.

- [ ] **Step 4: Preserve validation and API error behavior**

Keep required full name/email/password validation and minimum eight-character password validation. Call `createAccount` with `{ fullName, email, password, role }`; do not include undefined link fields in the JSON body.

- [ ] **Step 5: Update the client API input type**

Make `createAccount` accept the same input fields plus a restricted role union for this admin workflow, while preserving the response mapping and existing endpoint.

- [ ] **Step 6: Verify create behavior**

Open the dialog in Bác sĩ and Admin, confirm only the two allowed roles exist, submit invalid values and verify inline errors, then submit valid values and verify the request has no `patient_id` or `doctor_id` and the list refreshes.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/app/admin/accounts/page.tsx frontend/src/lib/accounts.ts
git commit -m "feat(admin): restrict account creation to doctors and admins"
```

### Task 3: Polish status actions and view states

**Files:**
- Modify: `frontend/src/app/admin/accounts/page.tsx`
- Test: manual browser verification

- [ ] **Step 1: Keep lock/unlock available for every displayed role**

Use the existing `updateAccountStatus` mutation for patient, caregiver, doctor, and admin rows. Toggle `locked` to `active` and `active`/`pending` to `locked` exactly as the current behavior defines.

- [ ] **Step 2: Add actionable mutation error feedback**

Expose a page-level or toast error when status mutation fails, and clear it after a successful retry. Do not silently leave a failed action looking successful.

- [ ] **Step 3: Verify loading, error, and empty states**

Ensure loading/error/empty rows span the complete table and that the header count reflects the selected group rather than all accounts. Confirm no layout overflow at the target desktop viewport.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/app/admin/accounts/page.tsx
git commit -m "fix(admin): clarify account status and empty states"
```

### Task 4: Run frontend quality gates

**Files:**
- Verify: `frontend/package.json`
- Verify: `frontend/src/app/admin/accounts/page.tsx`
- Verify: `frontend/src/lib/accounts.ts`

- [ ] **Step 1: Install/use the repository package manager**

From `frontend`, use the lockfile-supported command already documented by the project; do not regenerate lockfiles unnecessarily.

- [ ] **Step 2: Run lint and type/build checks**

Run:

```bash
npm run lint
npm run build
```

Expected: both commands exit with code 0 and report no TypeScript or ESLint errors caused by the account page.

- [ ] **Step 3: Review the final diff**

Run `git diff --check` and inspect the account page diff for accidental API changes, patient/doctor link fields in the create payload, or a caregiver-only tab.

- [ ] **Step 4: Report verification**

Record the exact commands and outcomes in the handoff. Do not claim completion if lint/build or the manual tab/form checks fail.


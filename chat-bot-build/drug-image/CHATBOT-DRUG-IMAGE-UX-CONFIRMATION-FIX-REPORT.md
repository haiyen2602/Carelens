# Chatbot drug-image UX and confirmation fix report

Date: 2026-08-28  
Baseline: `137355387628f6df873501d4bb057df1f6876dae` (`origin/main` at branch creation)  
Branch: `fix/chatbot-drug-image-ux-confirmation`

## Scope and decision

This is a B-07 UX/state-bridge correction. It does not alter the B-05
recognizer, recognition thresholds, database schema, deployment configuration,
or the production recognition feature flag. Production recognition remains
disabled unless separately approved by B-08.

## Pre-fix reproduction and root cause

The available local real-photo pilot for `test02.jpg` (Snapcef reference)
returned `AMBIGUOUS_MATCH` under the unchanged B-05 policy. It therefore was
not promoted to a candidate or confirmation; no threshold was lowered to force
that outcome. The deterministic high-evidence lifecycle tests use a
server-derived candidate snapshot to exercise the confirmation bridge.

Code audit found three independent causes for the reported confirmation flow:

1. The confirmation route called the existing verified Drug Tool only if the
   upload message had already contained a recognized aspect such as “công
   dụng”. A normal explicit confirmation only asked a further question.
2. The free-text phrase “thông tin chi tiết thuốc” was not an attribute-only
   follow-up. It could therefore bypass the canonical prior drug entity and
   fail to use the bound Drug Tool.
3. The UI rendered every server candidate and stored an accepted upload as a
   filename-only user bubble. A local rejection did not invalidate the server
   action.

## Changes

- Only `HIGH_EVIDENCE_MATCH` creates a confirmable snapshot and exposes one
  candidate. `AMBIGUOUS_MATCH` and insufficient evidence persist no candidate
  action and show generic re-upload/name-entry guidance.
- The existing confirmation endpoint now accepts the additive
  `decision=REJECTED` value. It validates the opaque action and transitions
  the attempt to the existing terminal `SUPERSEDED` state; it never binds an
  entity or invokes a tool. No new recognition endpoint and no schema change
  were introduced.
- A confirmed action saves `ActiveEntity(type="drug", id=<canonical
  drug_product_id>, legacy_drug_id=<server mapping>)`. The immediate response
  calls only the existing verified Drug Tool, including for a normal
  confirmation without an initially requested aspect.
- Follow-up detection now treats “thông tin chi tiết thuốc” as an
  attribute-only request and invokes the bound Drug Tool using the
  server-owned legacy mapping, while retaining the canonical product ID in
  state.
- The user chat bubble renders a local object-URL thumbnail and secondary
  filename only after the multipart request is accepted. No Base64/binary is
  put in local storage; object URLs are revoked on dismissal or page unmount,
  and persisted history retains only the filename.
- The candidate card has exactly `[Đúng thuốc này]` and `[Không đúng]` for the
  one high-evidence candidate. Ambiguous and insufficient messages render no
  candidate card or similarity information.
- The B-07 API contract was updated for this additive refusal decision and
  the high-evidence-only presentation boundary.

## Safety and state invariants

- Unconfirmed, ambiguous, insufficient, rejected, forged, expired and stale
  actions cannot bind `ConversationState.active_entity`.
- The verified Drug Tool is called only after an exact confirmed opaque action.
- Follow-ups retain the canonical product ID and server-derived legacy mapping;
  a new-topic path still clears incompatible state.
- Existing Safety/Dose Safety and active Doctor Takeover precedence are
  untouched and remain covered by route regressions.

## Verification

| Check | Result |
|---|---|
| Targeted backend/service/follow-up tests | `51 passed` |
| Ruff on changed backend/test files | passed |
| Frontend drug-image UI contract test | passed |
| ESLint on changed frontend files | passed |
| TypeScript `tsc --noEmit` | passed |
| Diff whitespace check | passed |

New regressions cover high-only candidate presentation, ambiguous no-candidate
presentation, rejection invalidation, canonical state binding, immediate
verified-tool lookup, and the “thông tin chi tiết thuốc” follow-up lookup.

## Release boundary

This branch is ready for normal code review after its commit and PR. It is not
authorization to enable recognition, merge, or deploy. B-08 production
approval remains `NOT_APPROVED` pending its independent evaluation and
environment evidence.

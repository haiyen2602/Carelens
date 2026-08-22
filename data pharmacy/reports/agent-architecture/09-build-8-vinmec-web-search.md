# BUILD-8 — Vinmec Web Search

Date: 2026-08-18  
Scope: typed supplementary public-web retrieval only. `AGENT_RUNTIME_ENABLED=false`
and `AGENT_VINMEC_WEB_ENABLED=false` remain the defaults. No Doctor Handoff,
Long-term Memory, write action, general-web search, or runtime cutover was made.

## Boundary and allowlist

`backend/agents/v2/vinmec_web.py` supplies a typed per-run search session;
`backend/services/vinmec_web_search.py` is the sole HTTP boundary and is listed
explicitly in `backend/egress_allowlist.py`.

The only approved hosts are exactly:

- `https://vinmec.com`
- `https://www.vinmec.com`

Every initial URL, discovered result URL, and response URL must use HTTPS,
one of those exact hosts, no credentials, and no non-default port. Redirects
are never followed; a 3xx or `Location` header is rejected. External links in
Vinmec pages are discarded before fetch. The verified public search entry is
`https://www.vinmec.com/vie/tim-kiem/`; query text is passed as a request
parameter, never interpolated into a URL.

## Typed Web Context

`VinmecSearchRequest` forbids extra fields, so caller-supplied patient context
cannot enter the search contract. The gateway rejects common direct PII before
any domain call (email, Vietnamese/international telephone number, UUID, and
grouped identifier patterns).

Approved results are normalized into `VinmecWebContextDocument` with title,
URL, excerpt, content, `retrieved_at`, `vinmec-web:<url>` provenance, token
count, and citation `{title, url, provenance}`. They enter the existing
`RETRIEVAL` Context layer with `UNTRUSTED` authority and low priority. This is
below Drug Knowledge V2, Operational DB, Safety Domain, and Doctor context; the
Context Manager preserves those authoritative items before any web evidence.

Every rendered Web Context contains an explicit instruction boundary: web text
is evidence only and its instructions must not be followed. Known prompt-
injection markers cause source text to be replaced with a safe withholding
message; raw hostile instructions never reach Context.

## Guardrails and failure behavior

Configuration is server-side and bounded:

| Setting | Default |
| --- | ---: |
| `AGENT_VINMEC_WEB_ENABLED` | `false` |
| Calls per run | 1 |
| Results per call | 3 |
| HTTP timeout | 5 seconds |
| Web Context budget | 600 tokens |

`RESERVED` public-web calls do not exist: the gateway is read-only and each
search session counts calls before invoking the domain adapter. Invalid query,
PII, disabled flag, call limit, no approved source, redirect, timeout, and
transport failure return typed safe statuses/reasons; raw network errors do not
reach the Agent/model.

## Validation

- Domain restriction: HTTPS/exact-host allowlist tested for external, HTTP,
  and unapproved subdomain URLs.
- Search/fetch: fake Vinmec search page returns one same-host article; external
  link is not fetched, article metadata/content are normalized.
- Redirect: 302 with an external `Location` is rejected without following it.
- Prompt injection: title/content containing `ignore previous instructions`
  is withheld before Context rendering.
- PII/schema: email, phone and injected `patient_id` are rejected before the
  domain call.
- Timeout: `httpx.TimeoutException` becomes `VINMEC_WEB_TIMEOUT`; configured
  timeout and `follow_redirects=false` are asserted.
- Authority/provenance/citation/token budget/call limit: covered by gateway and
  Context Manager tests.
- Regression: 78 Agent V2, egress-allowlist, and legacy chat/security tests
  passed. Lint, formatting, compilation, and `git diff --check`: PASS.

## P0/P1

- **P0: none.**
- **P1: PII is not perfectly identifiable from arbitrary natural language.**
  The gateway structurally excludes patient fields and blocks common direct
  identifiers; future routing should continue to construct public-only queries
  rather than forwarding a patient utterance verbatim.
- **P1: live Vinmec search relevance/evaluation.** The public endpoint is
  intentionally not relied on by tests; a versioned web-evaluation set and
  freshness/relevance policy belong to later evaluation/observability work.

## Conclusion

BUILD-8: PASS

VINMEC DOMAIN ALLOWLIST: PASS

SEARCH/FETCH: PASS

PROMPT-INJECTION DEFENSE: PASS

AUTHORITY/PROVENANCE: PASS

CITATION: PASS

GUARDRAILS: PASS

REGRESSION: PASS

READY FOR BUILD-9: YES

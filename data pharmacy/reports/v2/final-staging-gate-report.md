# Final Staging Gate Report

**Date:** 2026-08-16  
**Scope:** real Railway staging validation before any V1 deprecation. No deployment was made and no production environment was selected.

## Railway Target Verification

Railway authentication is valid for `minhdat31122005@gmail.com` in workspace
`haiyen2602's Projects`. The linked project is `VMEC-04`
(`14b221cb-1a7b-4b20-b5d1-331268729371`).

`railway environment list --json` returned exactly one environment:

- `production` (`6ed8b11f-d49e-47e7-91a8-c24004926bab`), linked locally.

The service list for that environment includes `VMEC-04/BE`
(`7523d6d4-7c4a-4551-9a17-13619c74680a`) at
`https://vmec-04be-production.up.railway.app`. No `staging` environment or
staging service exists in the project.

`railway.json` defines the Dockerfile build and `/health` check, but contains no
project, service, or staging-environment binding. Therefore there is no
verified staging target to deploy to, and selecting production or creating a
new environment would violate this gate's explicit no-guessing requirement.

## Not Executed

The following require the real staging URL and were not run:

- startup verification for the packaged V2 artifacts and warm index;
- HTTP smoke/regression for identity, structured and semantic lookup,
  side-effect/red-flag, missed/delayed dose, catalog, prescription, and
  fail-closed input;
- V1 rollback drill on staging.

## Local Preflight Evidence

This does not substitute for staging validation, but the preceding runtime
replacement gate verified a clean Docker image that warmed Canonical V2 from
`/app/data/drug-knowledge-v2` with `3,562` products and `42,654` knowledge
chunks. Its V2-default local HTTP suite recorded `wrong-drug=0`,
`wrong-type=0`, `8/8` fail-closed cases, and no unexpected 5xx responses.

## FINAL STAGING GATE

```text
STATUS:
BLOCKED

RAILWAY TARGET:
- Authenticated project VMEC-04; only production exists. No staging target.

DEPLOYMENT:
FAIL

V2 STARTUP:
FAIL

HTTP REGRESSION:
FAIL

SAFETY:
FAIL

PRESCRIPTION:
FAIL

V1 ROLLBACK:
NOT TESTED

BREAKING CHANGE:
NO

READY TO DEPRECATE V1:
NO
```

## Required To Resume

1. Create or provide the explicit Railway **staging** environment and backend
   service target for `VMEC-04`, plus its staging base URL.
2. Link this workspace to that staging environment and service.
3. Run the clean deployment and the requested HTTP suite there, then repeat
   the V1 rollback drill if that staging environment permits it.

V1, `drug_chunks`, the frozen legacy dataset, compatibility layer, and
`v1|shadow` modes remain unchanged.

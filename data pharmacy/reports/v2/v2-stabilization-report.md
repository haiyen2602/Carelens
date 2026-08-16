# V2 Stabilization Report

**Ngày:** 2026-08-16T10:13:18.842753+00:00  
**Scope:** V2 default HTTP stabilization; V1 rollback retained; no V1 deprecation.

## Coverage

- Eval cases: 64
- Known-drug cases: 56
- Structured cases: 50
- Fail-closed cases: 8
- V1 rollback sample: 11
- Knowledge types: {'ADMINISTRATION': 5, 'ADVERSE_EFFECT': 5, 'CONTRAINDICATION': 5, 'DRIVING_WARNING': 5, 'GENERAL_DOSAGE': 5, 'INDICATION': 5, 'INTERACTION': 5, 'PRECAUTION': 5, 'PREGNANCY_LACTATION': 5, 'STORAGE': 5}
- Categories sampled: {'Bổ xương khớp': 10, 'Thuốc bù điện giải': 10, 'Thuốc sát khuẩn': 10, 'Thuốc trị thiếu máu': 10, 'Thuốc điều trị ung thư': 10, 'fail_closed': 8, 'semantic': 6}

## HTTP Rows

| Label | Case | Kind | HTTP | Sources | Backend | Route | Wrong Drug | Wrong Type | Latency ms |
|---|---|---|---:|---:|---|---|---:|---:|---:|
| v2_default | indication_00 | known | 200 | 1 | v2 | structured_lookup | False | False | 36.83 |
| v2_default | indication_01 | known | 200 | 1 | v2 | structured_lookup | False | False | 17.41 |
| v2_default | indication_02 | known | 200 | 1 | v2 | structured_lookup | False | False | 20.29 |
| v2_default | indication_03 | known | 200 | 1 | v2 | structured_lookup | False | False | 19.28 |
| v2_default | indication_04 | known | 200 | 1 | v2 | structured_lookup | False | False | 18.54 |
| v2_default | adverse_effect_05 | known | 200 | 1 | v2 | structured_lookup | False | False | 18.12 |
| v2_default | adverse_effect_06 | known | 200 | 1 | v2 | structured_lookup | False | False | 17.38 |
| v2_default | adverse_effect_07 | known | 200 | 1 | v2 | structured_lookup | False | False | 18.47 |
| v2_default | adverse_effect_08 | known | 200 | 1 | v2 | structured_lookup | False | False | 18.93 |
| v2_default | adverse_effect_09 | known | 200 | 1 | v2 | structured_lookup | False | False | 18.42 |
| v2_default | contraindication_10 | known | 200 | 1 | v2 | structured_lookup | False | False | 19.03 |
| v2_default | contraindication_11 | known | 200 | 1 | v2 | structured_lookup | False | False | 18.90 |
| v2_default | contraindication_12 | known | 200 | 1 | v2 | structured_lookup | False | False | 18.60 |
| v2_default | contraindication_13 | known | 200 | 1 | v2 | structured_lookup | False | False | 17.69 |
| v2_default | contraindication_14 | known | 200 | 1 | v2 | structured_lookup | False | False | 17.99 |
| v2_default | precaution_15 | known | 200 | 4 | v2 | structured_lookup | False | False | 21.53 |
| v2_default | precaution_16 | known | 200 | 1 | v2 | structured_lookup | False | False | 19.94 |
| v2_default | precaution_17 | known | 200 | 1 | v2 | structured_lookup | False | False | 25.52 |
| v2_default | precaution_18 | known | 200 | 4 | v2 | structured_lookup | False | False | 18.34 |
| v2_default | precaution_19 | known | 200 | 1 | v2 | structured_lookup | False | False | 18.56 |
| v2_default | interaction_20 | known | 200 | 1 | v2 | structured_lookup | False | False | 18.46 |
| v2_default | interaction_21 | known | 200 | 1 | v2 | structured_lookup | False | False | 19.87 |
| v2_default | interaction_22 | known | 200 | 1 | v2 | structured_lookup | False | False | 19.12 |
| v2_default | interaction_23 | known | 200 | 1 | v2 | structured_lookup | False | False | 19.08 |
| v2_default | interaction_24 | known | 200 | 1 | v2 | structured_lookup | False | False | 20.81 |
| v2_default | pregnancy_lactation_25 | known | 200 | 2 | v2 | structured_lookup | False | False | 18.69 |
| v2_default | pregnancy_lactation_26 | known | 200 | 2 | v2 | structured_lookup | False | False | 18.98 |
| v2_default | pregnancy_lactation_27 | known | 200 | 2 | v2 | structured_lookup | False | False | 17.70 |
| v2_default | pregnancy_lactation_28 | known | 200 | 1 | v2 | structured_lookup | False | False | 19.99 |
| v2_default | pregnancy_lactation_29 | known | 200 | 1 | v2 | structured_lookup | False | False | 18.27 |
| v2_default | driving_warning_30 | known | 200 | 1 | v2 | structured_lookup | False | False | 19.11 |
| v2_default | driving_warning_31 | known | 200 | 1 | v2 | structured_lookup | False | False | 18.82 |
| v2_default | driving_warning_32 | known | 200 | 1 | v2 | structured_lookup | False | False | 17.47 |
| v2_default | driving_warning_33 | known | 200 | 1 | v2 | structured_lookup | False | False | 17.93 |
| v2_default | driving_warning_34 | known | 200 | 1 | v2 | structured_lookup | False | False | 17.72 |
| v2_default | administration_35 | known | 200 | 1 | v2 | structured_lookup | False | False | 19.35 |
| v2_default | administration_36 | known | 200 | 1 | v2 | structured_lookup | False | False | 16.82 |
| v2_default | administration_37 | known | 200 | 1 | v2 | structured_lookup | False | False | 16.73 |
| v2_default | administration_38 | known | 200 | 1 | v2 | structured_lookup | False | False | 16.66 |
| v2_default | administration_39 | known | 200 | 1 | v2 | structured_lookup | False | False | 16.39 |
| v2_default | general_dosage_40 | known | 200 | 1 | v2 | structured_lookup | False | False | 16.79 |
| v2_default | general_dosage_41 | known | 200 | 1 | v2 | structured_lookup | False | False | 16.48 |
| v2_default | general_dosage_42 | known | 200 | 1 | v2 | structured_lookup | False | False | 16.90 |
| v2_default | general_dosage_43 | known | 200 | 1 | v2 | structured_lookup | False | False | 16.99 |
| v2_default | general_dosage_44 | known | 200 | 1 | v2 | structured_lookup | False | False | 21.45 |
| v2_default | storage_45 | known | 200 | 1 | v2 | structured_lookup | False | False | 17.21 |
| v2_default | storage_46 | known | 200 | 1 | v2 | structured_lookup | False | False | 17.90 |
| v2_default | storage_47 | known | 200 | 1 | v2 | structured_lookup | False | False | 19.78 |
| v2_default | storage_48 | known | 200 | 1 | v2 | structured_lookup | False | False | 17.72 |
| v2_default | storage_49 | known | 200 | 1 | v2 | structured_lookup | False | False | 17.23 |
| v2_default | semantic_open_00 | known | 200 | 5 | v2 | rag_v2 | False | False | 17.36 |
| v2_default | semantic_open_01 | known | 200 | 5 | v2 | rag_v2 | False | False | 16.51 |
| v2_default | semantic_open_02 | known | 200 | 5 | v2 | rag_v2 | False | False | 17.94 |
| v2_default | semantic_open_03 | known | 200 | 5 | v2 | rag_v2 | False | False | 17.97 |
| v2_default | semantic_open_04 | known | 200 | 5 | v2 | rag_v2 | False | False | 18.73 |
| v2_default | semantic_open_05 | known | 200 | 5 | v2 | rag_v2 | False | False | 18.91 |
| v2_default | fail_closed_00 | fail_closed | 200 | 0 | - | - | False | False | 131.01 |
| v2_default | fail_closed_01 | fail_closed | 200 | 0 | - | - | False | False | 133.91 |
| v2_default | fail_closed_02 | fail_closed | 200 | 0 | - | - | False | False | 139.76 |
| v2_default | fail_closed_03 | fail_closed | 200 | 0 | - | - | False | False | 123.30 |
| v2_default | fail_closed_04 | fail_closed | 200 | 0 | - | - | False | False | 138.32 |
| v2_default | fail_closed_05 | fail_closed | 200 | 0 | - | - | False | False | 138.13 |
| v2_default | fail_closed_06 | fail_closed | 200 | 0 | - | - | False | False | 130.81 |
| v2_default | fail_closed_07 | fail_closed | 200 | 0 | - | - | False | False | 124.06 |
| v1_rollback | indication_00 | known | 200 | 4 | v1 | v1_get_chunks_by_drug_id | False | False | 21.11 |
| v1_rollback | indication_01 | known | 200 | 4 | v1 | v1_get_chunks_by_drug_id | False | False | 19.93 |
| v1_rollback | indication_02 | known | 200 | 4 | v1 | v1_get_chunks_by_drug_id | False | False | 18.34 |
| v1_rollback | indication_03 | known | 200 | 4 | v1 | v1_get_chunks_by_drug_id | False | False | 20.24 |
| v1_rollback | indication_04 | known | 200 | 4 | v1 | v1_get_chunks_by_drug_id | False | False | 19.11 |
| v1_rollback | adverse_effect_05 | known | 200 | 4 | v1 | v1_get_chunks_by_drug_id | False | False | 18.66 |
| v1_rollback | adverse_effect_06 | known | 200 | 4 | v1 | v1_get_chunks_by_drug_id | False | False | 19.53 |
| v1_rollback | adverse_effect_07 | known | 200 | 4 | v1 | v1_get_chunks_by_drug_id | False | False | 19.33 |
| v1_rollback | fail_closed_00 | fail_closed | 200 | 0 | - | - | False | False | 119.29 |
| v1_rollback | fail_closed_01 | fail_closed | 200 | 0 | - | - | False | False | 144.30 |
| v1_rollback | fail_closed_02 | fail_closed | 200 | 0 | - | - | False | False | 126.44 |

## V2 STABILIZATION RESULT

```text
STATUS:
PASS WITH ISSUES

EVAL CASES:
- 64 V2 default HTTP cases
- 11 V1 rollback sample cases

WRONG DRUG:
-

WRONG TYPE:
-

FAIL CLOSED:
- 100.00%

HTTP REGRESSION:
PASS

LATENCY:
- p50=18.60ms, p95=133.91ms, max=139.76ms

P0/P1 ISSUES:
-

TECHNICAL DEBT:
- 494 ingredient parsing warnings remain RAW_PRESERVED/REVIEW_REQUIRED
- 21 unmapped headings remain REVIEW_REQUIRED
- 11 NEW_PRODUCT rows remain in review queue

V1 ROLLBACK:
PASS

READY TO CONSIDER V1 DEPRECATION:
YES
```

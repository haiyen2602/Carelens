# V2 Stabilization Report

**Ngày:** 2026-08-16T10:37:54.869966+00:00  
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
| v2_default | indication_00 | known | 200 | 1 | v2 | structured_lookup | False | False | 46.16 |
| v2_default | indication_01 | known | 200 | 1 | v2 | structured_lookup | False | False | 21.27 |
| v2_default | indication_02 | known | 200 | 1 | v2 | structured_lookup | False | False | 21.44 |
| v2_default | indication_03 | known | 200 | 1 | v2 | structured_lookup | False | False | 21.07 |
| v2_default | indication_04 | known | 200 | 1 | v2 | structured_lookup | False | False | 21.64 |
| v2_default | adverse_effect_05 | known | 200 | 1 | v2 | structured_lookup | False | False | 21.00 |
| v2_default | adverse_effect_06 | known | 200 | 1 | v2 | structured_lookup | False | False | 22.00 |
| v2_default | adverse_effect_07 | known | 200 | 1 | v2 | structured_lookup | False | False | 20.79 |
| v2_default | adverse_effect_08 | known | 200 | 1 | v2 | structured_lookup | False | False | 19.31 |
| v2_default | adverse_effect_09 | known | 200 | 1 | v2 | structured_lookup | False | False | 18.82 |
| v2_default | contraindication_10 | known | 200 | 1 | v2 | structured_lookup | False | False | 20.21 |
| v2_default | contraindication_11 | known | 200 | 1 | v2 | structured_lookup | False | False | 19.62 |
| v2_default | contraindication_12 | known | 200 | 1 | v2 | structured_lookup | False | False | 19.67 |
| v2_default | contraindication_13 | known | 200 | 1 | v2 | structured_lookup | False | False | 25.59 |
| v2_default | contraindication_14 | known | 200 | 1 | v2 | structured_lookup | False | False | 17.44 |
| v2_default | precaution_15 | known | 200 | 4 | v2 | structured_lookup | False | False | 16.83 |
| v2_default | precaution_16 | known | 200 | 1 | v2 | structured_lookup | False | False | 16.95 |
| v2_default | precaution_17 | known | 200 | 1 | v2 | structured_lookup | False | False | 16.62 |
| v2_default | precaution_18 | known | 200 | 4 | v2 | structured_lookup | False | False | 16.94 |
| v2_default | precaution_19 | known | 200 | 1 | v2 | structured_lookup | False | False | 16.63 |
| v2_default | interaction_20 | known | 200 | 1 | v2 | structured_lookup | False | False | 16.65 |
| v2_default | interaction_21 | known | 200 | 1 | v2 | structured_lookup | False | False | 17.46 |
| v2_default | interaction_22 | known | 200 | 1 | v2 | structured_lookup | False | False | 17.36 |
| v2_default | interaction_23 | known | 200 | 1 | v2 | structured_lookup | False | False | 17.42 |
| v2_default | interaction_24 | known | 200 | 1 | v2 | structured_lookup | False | False | 17.46 |
| v2_default | pregnancy_lactation_25 | known | 200 | 2 | v2 | structured_lookup | False | False | 17.47 |
| v2_default | pregnancy_lactation_26 | known | 200 | 2 | v2 | structured_lookup | False | False | 17.20 |
| v2_default | pregnancy_lactation_27 | known | 200 | 2 | v2 | structured_lookup | False | False | 18.04 |
| v2_default | pregnancy_lactation_28 | known | 200 | 1 | v2 | structured_lookup | False | False | 18.41 |
| v2_default | pregnancy_lactation_29 | known | 200 | 1 | v2 | structured_lookup | False | False | 20.68 |
| v2_default | driving_warning_30 | known | 200 | 1 | v2 | structured_lookup | False | False | 18.41 |
| v2_default | driving_warning_31 | known | 200 | 1 | v2 | structured_lookup | False | False | 17.78 |
| v2_default | driving_warning_32 | known | 200 | 1 | v2 | structured_lookup | False | False | 17.84 |
| v2_default | driving_warning_33 | known | 200 | 1 | v2 | structured_lookup | False | False | 17.67 |
| v2_default | driving_warning_34 | known | 200 | 1 | v2 | structured_lookup | False | False | 16.80 |
| v2_default | administration_35 | known | 200 | 1 | v2 | structured_lookup | False | False | 17.72 |
| v2_default | administration_36 | known | 200 | 1 | v2 | structured_lookup | False | False | 16.82 |
| v2_default | administration_37 | known | 200 | 1 | v2 | structured_lookup | False | False | 16.85 |
| v2_default | administration_38 | known | 200 | 1 | v2 | structured_lookup | False | False | 16.50 |
| v2_default | administration_39 | known | 200 | 1 | v2 | structured_lookup | False | False | 17.07 |
| v2_default | general_dosage_40 | known | 200 | 1 | v2 | structured_lookup | False | False | 16.84 |
| v2_default | general_dosage_41 | known | 200 | 1 | v2 | structured_lookup | False | False | 16.62 |
| v2_default | general_dosage_42 | known | 200 | 1 | v2 | structured_lookup | False | False | 17.33 |
| v2_default | general_dosage_43 | known | 200 | 1 | v2 | structured_lookup | False | False | 16.83 |
| v2_default | general_dosage_44 | known | 200 | 1 | v2 | structured_lookup | False | False | 16.41 |
| v2_default | storage_45 | known | 200 | 1 | v2 | structured_lookup | False | False | 17.17 |
| v2_default | storage_46 | known | 200 | 1 | v2 | structured_lookup | False | False | 16.87 |
| v2_default | storage_47 | known | 200 | 1 | v2 | structured_lookup | False | False | 16.89 |
| v2_default | storage_48 | known | 200 | 1 | v2 | structured_lookup | False | False | 16.54 |
| v2_default | storage_49 | known | 200 | 1 | v2 | structured_lookup | False | False | 16.76 |
| v2_default | semantic_open_00 | known | 200 | 5 | v2 | rag_v2 | False | False | 16.47 |
| v2_default | semantic_open_01 | known | 200 | 5 | v2 | rag_v2 | False | False | 17.15 |
| v2_default | semantic_open_02 | known | 200 | 5 | v2 | rag_v2 | False | False | 16.45 |
| v2_default | semantic_open_03 | known | 200 | 5 | v2 | rag_v2 | False | False | 17.02 |
| v2_default | semantic_open_04 | known | 200 | 5 | v2 | rag_v2 | False | False | 16.62 |
| v2_default | semantic_open_05 | known | 200 | 5 | v2 | rag_v2 | False | False | 16.77 |
| v2_default | fail_closed_00 | fail_closed | 200 | 0 | - | - | False | False | 495.04 |
| v2_default | fail_closed_01 | fail_closed | 200 | 0 | - | - | False | False | 1459.72 |
| v2_default | fail_closed_02 | fail_closed | 200 | 0 | - | - | False | False | 2604.85 |
| v2_default | fail_closed_03 | fail_closed | 200 | 0 | - | - | False | False | 238.57 |
| v2_default | fail_closed_04 | fail_closed | 200 | 0 | - | - | False | False | 3386.14 |
| v2_default | fail_closed_05 | fail_closed | 200 | 0 | - | - | False | False | 3793.72 |
| v2_default | fail_closed_06 | fail_closed | 200 | 0 | - | - | False | False | 2049.44 |
| v2_default | fail_closed_07 | fail_closed | 200 | 0 | - | - | False | False | 2004.97 |
| v1_rollback | indication_00 | known | 200 | 4 | v1 | v1_get_chunks_by_drug_id | False | False | 23.73 |
| v1_rollback | indication_01 | known | 200 | 4 | v1 | v1_get_chunks_by_drug_id | False | False | 17.76 |
| v1_rollback | indication_02 | known | 200 | 4 | v1 | v1_get_chunks_by_drug_id | False | False | 16.52 |
| v1_rollback | indication_03 | known | 200 | 4 | v1 | v1_get_chunks_by_drug_id | False | False | 17.40 |
| v1_rollback | indication_04 | known | 200 | 4 | v1 | v1_get_chunks_by_drug_id | False | False | 17.42 |
| v1_rollback | adverse_effect_05 | known | 200 | 4 | v1 | v1_get_chunks_by_drug_id | False | False | 16.92 |
| v1_rollback | adverse_effect_06 | known | 200 | 4 | v1 | v1_get_chunks_by_drug_id | False | False | 17.86 |
| v1_rollback | adverse_effect_07 | known | 200 | 4 | v1 | v1_get_chunks_by_drug_id | False | False | 17.56 |
| v1_rollback | fail_closed_00 | fail_closed | 200 | 0 | - | - | False | False | 496.14 |
| v1_rollback | fail_closed_01 | fail_closed | 200 | 0 | - | - | False | False | 1489.44 |
| v1_rollback | fail_closed_02 | fail_closed | 200 | 0 | - | - | False | False | 2632.97 |

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
- p50=17.46ms, p95=2049.44ms, max=3793.72ms

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

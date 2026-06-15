# Data Quality Findings — Part 1

This document summarizes the initial data investigation for the EDI Analytics Engineer exercise. The guiding principle is to preserve raw values, add normalized fields and quality flags, and document assumptions rather than silently correcting ambiguous source data.

## Dataset inventory

| File | Rows | Notes |
|---|---:|---|
| `learners.csv` | 154 | Learner roster with inconsistent IDs/cohorts and duplicate person records. |
| `curricular_experiences.csv` | 22 | Session list with one duplicate normalized session ID. |
| `competency_crosswalk.csv` | 24 | Session-to-domain links with aliases and casing differences. |
| `assessment_events.csv` | 1,751 | Assessment events with mixed score types, mixed date formats, and a few orphan learner IDs. |

## Key findings and proposed handling

| Area | Finding | Proposed handling for model | Why |
|---|---|---|---|
| Learner IDs | IDs include lowercase values, whitespace, hyphens, and raw numbers. Normalization reduces 154 rows to 150 unique learner IDs. | Preserve raw ID and add normalized `learner_id`. Use normalized ID for joins. | Fixes mechanical source-system variation without losing source lineage. |
| Duplicate learners | Four normalized learner IDs have duplicate rows: `VU0024`, `VU0142`, `VU0105`, `VU0004`; duplicate emails align with these records. | Deduplicate `dim_learner` by normalized ID and retain `source_record_count`, `has_likely_dup_source_records`, `raw_learner_ids_seen`, and `raw_cohorts_seen`. | These appear to be same-person duplicates. Collapsing them prevents overcounting while retaining traceability. |
| Cohort | Cohort values include `2026`, ` 2026`, `Class of 2027`, `C2025`, and blanks. | Extract four-digit year into `cohort_year`; flag missing cohort. | Enables cohort comparisons while avoiding imputation for blanks. This assumes the cohort labels are year-based class cohorts; if cohorts can span or change within a year, that should be validated with a domain expert. |
| Matriculation year | Seven blanks plus `9999` and `1900`. | Preserve raw value; flag blank/sentinel/suspicious values. Do not use as primary cohort field. | `9999` may be an integer null sentinel; `1900` may be typo/default. Both need domain validation. |
| Session IDs | `assessment_events` uses `S021`; `curricular_experiences` has `s021`. | Normalize session IDs to uppercase for joins. | Case mismatch is mechanical and safe to normalize. |
| Duplicate sessions | `S005` appears twice with different titles/dates. | Keep one `dim_session` row per normalized session ID, choose the latest delivery-date row as canonical metadata, and retain source-title/date variants with `has_likely_dup_source_records` and metadata-conflict flags. | The rows share session ID, block, modality, instrument, and competency mapping; collapsing prevents duplicated assessment facts while keeping the ambiguity visible. |
| Competency domains | Aliases/casing include `KP`, `PC`, `IPC`, `professionalism`, `PATIENT CARE`. | Map to canonical domain names in `dim_competency`; preserve raw crosswalk value in staging. | Makes competency reporting readable while retaining source traceability. |
| Missing crosswalk | Sessions `S014`, `S018`, and `S021` have no crosswalk after session normalization. | Exclude from competency indicator until mapped; report as coverage/data-quality gap. | A competency indicator should not infer competencies without a crosswalk. |
| Assessment learner references | Events reference `VU0000`, `VU0411X`, and `VU9001`, not present in learners after normalization. | Retain in staging; exclude from learner-level marts and count as orphan learner events. | Prevents creating unknown learners while documenting source issues. |
| Assessment dates | Dates use ISO, four-digit slash dates, and two-digit slash dates. One event has `1999-09-01`, outside the expected curricular window. | Parse supported formats; flag out-of-window dates. | Date standardization is necessary for trend analysis, but out-of-window values should not be silently changed. |
| Score types | 1,589 events are valid numeric in range; 110 are pass/fail; 45 numeric scores lack `max_score`; 4 scores are blank; 2 are above max; 1 is negative. | Preserve all assessment events in `fact_assessment_event`. For the first-pass benchmark, use only numeric scores in `[0, max_score]`; flag above-max, negative, missing, and pass/fail records with `score_quality_status`. | Avoids mixing rubrics. Above-max values may be extra credit, so they are flagged rather than deleted or capped. |
| Score sentinel/outlier | `999/25` may be a sentinel/null placeholder or entry error. `105/100` may be valid extra credit. `-3/20` is highly suspicious. | Keep raw values and quality flags. Do not cap or coerce in staging. Exclude out-of-range values from conservative cohort benchmark until policy is confirmed. | Makes the metric reproducible and honest about limits. |

## First-pass indicator feasibility

Using a conservative first-pass definition — active learners only, normalized learner/session joins, mapped competency crosswalks, non-missing cohort, and numeric scores within `[0, max_score]` — the profile finds:

- 1,713 valid assessment-competency rows after crosswalk expansion.
- 145 learners with at least one valid scored competency row.
- 349 learner-competency pairs with at least two valid scored assessments.
- 333 learner-competency pairs with exactly one valid scored assessment.

This supports a cohort-relative competency progression indicator, provided the dashboard also displays evidence coverage and excluded-event caveats.

## Candidate indicator direction

A defensible indicator is a **cohort-relative competency progression gap**:

1. Calculate each active learner's average normalized score by competency.
2. Compare that learner-competency average to the learner's cohort/competency benchmark.
3. Assign a monitor status to learner-competency pairs whose gap exceeds a documented threshold and has sufficient evidence.
4. Separately label learner-competency pairs with limited evidence rather than treating them as normal or abnormal.

The director-facing dashboard should present this as a neutral **strengths and monitor** view: where learner-competency performance is above/near benchmark, where gaps may merit monitoring, and where evidence is insufficient for interpretation.

Confirmed implementation choices:

- Minimum evidence threshold: at least two valid scored events before assigning `strength`, `on_track`, or `monitor`.
- Benchmark: cohort/competency median among learner-competency pairs with at least two valid scored events.
- Monitor threshold: learner-competency average at least 10 percentage points below the cohort/competency median.
- Strength threshold: learner-competency average at least 10 percentage points above the cohort/competency median.
- User-facing language should describe `monitor` as a learner-competency signal that may benefit from review or follow-up, not as a judgment about the learner.

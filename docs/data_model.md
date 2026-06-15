# Data Model — Part 2

This project uses a small dimensional model in DuckDB. DuckDB is an embedded analytical database; the same conceptual model could be implemented in SQLite, Postgres, BigQuery, Snowflake, or dbt.

## Entity relationship view

```diagram
╭─────────────╮       ╭───────────────────────╮       ╭─────────────╮
│ dim_learner │◀──────│ fact_assessment_event │──────▶│ dim_session │
╰─────────────╯       ╰───────────┬───────────╯       ╰─────────────╯
                                  │
                                  │ valid scored events with
                                  │ session-to-competency mapping
                                  ▼
                    ╭───────────────────────────────────╮
                    │ mart_learner_competency_progression│
                    ╰────────────────┬──────────────────╯
                                     │
                                     ▼
                              ╭────────────────╮
                              │ dim_competency │
                              ╰────────────────╯
```

The mart is the dashboard-ready table. It expands valid scored assessment events through the session-to-competency crosswalk and aggregates them to learner + competency.

## Table documentation

| Table | Grain | Purpose | Important assumptions |
|---|---|---|---|
| `stg_learners` | One row per source learner row | Preserves roster records with normalized IDs/cohorts and quality fields. | Learner IDs are normalized by trimming, uppercasing, removing hyphens, and zero-padding numeric IDs to `VU####`. `cohort_year` assumes cohort labels represent year-based class cohorts; this should be validated if cohorts are not one-year class labels. |
| `stg_curricular_experiences` | One row per source session row | Preserves session metadata with normalized session IDs. | Session IDs are uppercased to resolve `S021`/`s021`. |
| `stg_competency_crosswalk` | One row per source session-to-competency link | Maps raw competency aliases to canonical competency labels. | `KP`, `PC`, and `IPC` are mapped to documented competency names. |
| `stg_assessment_events` | One row per source assessment event | Preserves raw event values and adds parsed/numeric/quality fields. | Out-of-range scores are preserved and flagged, not silently capped. |
| `dim_learner` | One row per normalized learner ID | Learner dimension for cohort/status analysis. | Duplicate learner rows are collapsed only after normalized IDs and core identity fields agree. Direct names/emails are not carried into this dimension for the director-facing model. |
| `dim_session` | One row per normalized session ID | Session dimension for block, modality, and delivery-date context. | For duplicate `S005`, the latest delivery-date row is used as canonical metadata while source-title/date variants are retained in governance fields. |
| `dim_competency` | One row per canonical competency domain | Competency dimension for dashboard grouping. | Domains are derived from the crosswalk after alias normalization. |
| `fact_assessment_event` | One row per assessment event | Governed event fact preserving the full assessment event population. | Pass/fail events and data-quality issues remain in the fact table, but `use_in_indicator` is false when records are not appropriate for the numeric progression indicator. |
| `mart_learner_competency_progression` | One row per active learner + competency | Dashboard-ready progression table. | Uses only active learners with cohort, valid numeric in-range scores, mapped competencies, and in-window assessment dates. Learner-competency status is evidence-aware. |

## Indicator definition

The first-pass indicator is a cohort-relative competency progression signal.

For each active learner and competency:

1. Use valid assessment events.
2. Average valid score percentages for each learner/competency.
3. Calculate the cohort/competency median among learner-competency pairs with at least two valid events.
4. Assign `monitor_status`:
   - `monitor`: at least two valid events and learner average is at least 10 percentage points below the cohort/competency median.
   - `strength`: at least two valid events and learner average is at least 10 percentage points above the cohort/competency median.
   - `on_track`: at least two valid events and within ±10 percentage points of the cohort/competency median.
   - `limited_evidence`: exactly one valid event.
   - `not_scored`: no valid scored events.
   - `limited_benchmark`: not enough cohort/competency peers to produce a stable benchmark.

For this first-pass numeric indicator, a valid assessment event is an event that:

- has a numeric score and positive max score;
- has `0 <= score <= max_score`;
- falls within the expected assessment window from the exercise prompt;
- resolves to known learner and session records after ID normalization; and
- has a session-to-competency mapping in the crosswalk.

Pass/fail professionalism attestations and sessions without crosswalks are preserved in `fact_assessment_event`, but are not valid numeric events for this cohort-relative indicator.

Note: User-facing copy should describe `monitor` as a learner-competency signal that may benefit from review or follow-up, not as a judgment about the learner.

## Why median vs mean for the benchmark?

The cohort/competency median is less sensitive than the mean to remaining source-data quirks and is easy to explain as typical peer performance in the same cohort and competency.

## Known Data Limitations

- `S014` has pass/fail professionalism attestations but no competency crosswalk, so those events are preserved in `fact_assessment_event` and excluded from the numeric competency mart used by the dashboard.
- `S021` has assessment events and a session row after case normalization, but does not have a corresponding competency crosswalk.
- Above-max scores are excluded from the first-pass indicator. `105/100` may represent extra credit, while `999/25` may be an entry error; these likely need a followup investigation and could be useful for implementing a scoring validation check in the future.
- Learners with missing cohorts are excluded from cohort-relative benchmarking.
- Cohort parsing assumes the four-digit year in the source label is the appropriate class cohort for peer comparison.

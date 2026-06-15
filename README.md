# EDI Analytics Engineer Exercise

This repository contains a complete analytics engineering exercise for Vanderbilt
University School of Medicine's Education Design & Informatics group. It turns
four deliberately messy synthetic CSV files into a governed DuckDB data model,
defines one competency progression indicator, and presents the result in a
concise Plotly Dash dashboard for a program director.

This README is intended as the top-level review guide for the EDI panel. It
summarizes the transformation approach, table grains, data-quality decisions,
indicator design, dashboard framing, and known limitations. Supporting
documentation lives in `docs/`.

## Review guide

The repository is organized around the exercise's requested deliverables:

- **Transformation code:** SQL layers in `sql/` plus `scripts/build_model.py`
  rebuild the DuckDB model from raw CSV files.
- **Model documentation:** [Data Model](docs/data_model.md) documents each
  model's grain, purpose, assumptions, and progression-indicator logic.
- **Data-quality documentation:** [Data Quality Findings](docs/data_quality_findings.md)
  summarizes source issues, handling decisions, and items that need
  domain-expert validation.
- **Director-facing dashboard:** `app.py` serves the Plotly Dash view at
  <http://127.0.0.1:8050> after setup.

The sections below summarize those artifacts so the repository can be reviewed
without relying on a live walkthrough.

## Source data

The provided dataset includes four CSV files, extracted into `data/raw/`:

- `learners.csv`: one source learner roster row per record. Provides learner
  identity, cohort, status, and roster quality fields.
- `curricular_experiences.csv`: one source teaching session row per record.
  Provides session metadata, delivery dates, blocks, and modality.
- `competency_crosswalk.csv`: one source session-to-competency link per record.
  Maps sessions to PCRS competency categories.
- `assessment_events.csv`: one source assessment result per record. Provides
  assessment score events tied to learners and sessions.

The data is synthetic, but the modeling choices assume a real educational-data
context: preserve raw values, normalize only defensible mechanical variation,
and flag ambiguous records rather than silently correcting them.

## Project structure

```text
.
├── app.py                              # Plotly Dash dashboard
├── assets/
│   └── styles.css                      # Dashboard styling
├── data/
│   ├── raw/                            # Extracted source CSV files
│   └── edi_analytics.duckdb            # Generated locally; ignored by git
├── docs/
│   ├── data_model.md                   # Model grains and indicator definition
│   └── data_quality_findings.md        # Profiling findings and handling decisions
├── notebooks/
│   └── 01_data_profile_and_quality_review.ipynb
├── scripts/
│   └── build_model.py                  # Rebuilds the DuckDB model from raw CSVs
├── sql/
│   ├── 00_raw_tables.sql               # Raw CSV ingestion
│   ├── 02_staging_tables.sql           # Normalization, parsing, quality fields
│   ├── 03_dimensions.sql               # Learner, session, competency dimensions
│   ├── 04_facts.sql                    # Governed assessment event fact
│   └── 05_marts.sql                    # Dashboard-ready progression mart
├── requirements.txt
└── README.md
```

## Setup

The project was built with Python 3.12.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Rebuild the model

```bash
source .venv/bin/activate
python scripts/build_model.py
```

This rebuilds `data/edi_analytics.duckdb` from the CSV files in `data/raw/`.
The DuckDB file is a generated artifact and is intentionally not required for
source review.

## Run the dashboard

```bash
source .venv/bin/activate
python app.py
```

Open <http://127.0.0.1:8050>.

The dashboard is designed for a non-technical program director or curriculum
committee audience. It uses learner IDs rather than names, emphasizes
competency framing, and presents review-suggested signals as prompts for
follow-up rather than judgments about learners.

## Deploy on Render

Live dashboard: <https://edi-analytics-eng-demo.onrender.com>.

This repository includes a `render.yaml` blueprint for Render deployment with
the required Dash app settings:

- **Runtime:** Python
- **Python version:** set by `.python-version`
- **Build command:** `pip install -r requirements.txt`
- **Start command:** `gunicorn app:server`

The generated DuckDB file is not committed. On Render, `app.py` calls
`ensure_database()` at startup and rebuilds `data/edi_analytics.duckdb` from the
CSV files in `data/raw/` if the database is absent.

## Data model summary

The model uses a small dimensional structure with staging tables, dimensions,
one assessment fact, and one dashboard mart.

- `stg_learners`
  - **Grain:** one source learner row.
  - **Purpose:** preserve source roster records with normalized IDs, parsed
    cohort year, and quality flags.
- `stg_curricular_experiences`
  - **Grain:** one source session row.
  - **Purpose:** preserve session metadata with normalized session IDs and
    parsed dates.
- `stg_competency_crosswalk`
  - **Grain:** one source session-to-competency row.
  - **Purpose:** normalize competency aliases such as `KP`, `PC`, and `IPC`
    into readable competency labels.
- `stg_assessment_events`
  - **Grain:** one source assessment event.
  - **Purpose:** preserve raw score/date values and add parsed fields plus
    score-quality flags.
- `dim_learner`
  - **Grain:** one normalized learner ID.
  - **Purpose:** director-safe learner dimension, excluding direct names/emails
    from the dashboard model.
- `dim_session`
  - **Grain:** one normalized session ID.
  - **Purpose:** session dimension with canonical metadata and
    duplicate/source-conflict governance fields.
- `dim_competency`
  - **Grain:** one competency.
  - **Purpose:** competency dimension derived from the crosswalk.
- `fact_assessment_event`
  - **Grain:** one assessment event.
  - **Purpose:** governed fact table preserving all assessment events,
    including records excluded from the numeric indicator.
- `mart_learner_competency_progression`
  - **Grain:** one active learner + competency.
  - **Purpose:** dashboard-ready table for the cohort-relative progression
    signal.

See [Data Model](docs/data_model.md) for fuller table documentation and
assumptions.

## Key data-quality decisions

The most important handling choices are documented in
[Data Quality Findings](docs/data_quality_findings.md). Highlights include:

- Learner IDs and session IDs are normalized for joins, while raw IDs remain
  preserved in staging/governance fields.
- Duplicate learner and session records are collapsed only where the normalized
  entity is defensible; source variants are retained for traceability.
- Cohort labels are parsed to four-digit `cohort_year` values for benchmarking,
  with missing or ambiguous values flagged.
- Score values are not capped or coerced. Numeric scores outside
  `[0, max_score]`, missing scores, missing max scores, and pass/fail records
  are preserved but excluded from the numeric progression indicator when
  inappropriate.
- Sessions without competency crosswalks are counted as data-quality
  limitations rather than inferred into a competency.
- Learner names and emails are excluded from the director-facing dashboard
  model.

## Progression indicator

The selected indicator is a **cohort-relative competency progression signal**.

For each active learner and competency:

1. Use valid numeric assessment events only.
2. Calculate that learner's average score percentage for the competency.
3. Compare the learner-competency average with the median learner-competency
   average for the same cohort and competency.
4. Assign an evidence-aware status:
   - `strength`: at least two valid events and at least 10 percentage points
     above the cohort/competency median.
   - `on_track`: at least two valid events and within ±10 percentage points of
     the cohort/competency median.
   - `monitor`: at least two valid events and at least 10 percentage points
     below the cohort/competency median. The dashboard labels this as
     **Review suggested**.
   - `limited_evidence`: exactly one valid scored event.
   - `not_scored`: no valid numeric scored events.
   - `limited_benchmark`: insufficient cohort/competency peers to produce a
     stable benchmark.

A valid event for this indicator is an assessment event that passed data-quality
checks, matched learner/session records, and mapped to a competency.

**Note:** Pass/fail professionalism attestations remain in
`fact_assessment_event`, but they are excluded from this numeric score
indicator.

## Indicator limitations

This first-pass indicator is intentionally conservative.

- It compares learners only within the same cohort and competency, but it
  assumes the parsed `cohort_year` is the right peer group.
- It uses median benchmarks to reduce sensitivity to remaining outliers, but a
  median is still only as reliable as the mapped and valid input data.
- It excludes pass/fail attestations and unmapped sessions from the numeric
  indicator, so the dashboard should not be read as a full picture of
  professionalism or all curriculum evidence.
- It requires at least two valid scored events before assigning review,
  on-track, or strength status; limited evidence is reported separately rather
  than overinterpreted.
- The 10 percentage-point threshold is transparent and straightforward, but it
  would need to be validated with faculty and program leadership before
  operational use.

## Dashboard framing

The dashboard is a single Plotly Dash page titled **Learner Progression Signals
by Competency**. It is meant to support a quick curriculum-committee
conversation by showing:

- the count of active learners in the modeled population;
- learners with at least one review-suggested competency;
- strength and limited-evidence signal counts;
- status distribution across learner-competency pairs;
- cohort-level median score context;
- definitions for each status and the valid-event rule;
- the calculation methodology; and
- data-quality observations and limitations.

The dashboard avoids learner names and uses neutral language such as
**Review suggested** to keep the view privacy-conscious and action-oriented.


## If this moved beyond the exercise

Recommended next steps before operational use would be:

- confirm cohort semantics and score-threshold policy with EDI/faculty
  stakeholders;
- decide how pass/fail professionalism assessments should be represented
  alongside numeric scores;
- resolve sessions missing competency crosswalks;
- add automated data-quality tests for orphan learners, missing crosswalks,
  out-of-range scores, and duplicate session metadata; and
- implement the model in the team's production analytics stack

-- ==========================================================
-- STAGING TABLES
-- ==========================================================
-- Staging tables preserve raw source values while adding normalized join keys,
-- parsed dates/numbers, canonical labels, and quality fields used downstream.

-- ==========================================================
-- LEARNERS
-- ==========================================================
-- Normalize learner IDs and cohort labels while preserving raw roster values.

create table stg_learners as
with cleaned as (
    select
        learner_id as raw_learner_id,
        first_name,
        last_name,
        cohort as raw_cohort,
        matriculation_year as raw_matriculation_year,
        email,
        status,
        replace(upper(trim(learner_id)), '-', '') as learner_id_clean
    from raw_learners
)
select
    raw_learner_id,
    case
        -- Convert bare numeric IDs like `52` to the canonical `VU0052` format.
        when regexp_matches(learner_id_clean, '^[0-9]+$') then 'VU' || lpad(learner_id_clean, 4, '0')
        -- Convert IDs like `VU-0024`, `vu0105`, or `VU24` to canonical `VU####`.
        when regexp_matches(learner_id_clean, '^VU[0-9]+$') then 'VU' || lpad(substr(learner_id_clean, 3), 4, '0')
        else learner_id_clean
    end as learner_id,
    first_name,
    last_name,
    raw_cohort,
    -- Extract a 2000s class year from labels like `Class of 2027` or `C2025`.
    nullif(regexp_extract(raw_cohort, '(20[0-9]{2})', 1), '') as cohort_year,
    raw_matriculation_year,
    try_cast(nullif(raw_matriculation_year, '') as integer) as matriculation_year,
    case
        when raw_matriculation_year = '' then 'missing'
        when raw_matriculation_year = '9999' then 'likely_null_sentinel'
        when raw_matriculation_year = '1900' then 'suspicious_value'
        else 'provided'
    end as matriculation_year_quality,
    email,
    status
from cleaned;

-- ==========================================================
-- CURRICULAR EXPERIENCES
-- ==========================================================
-- Normalize session IDs and parse delivery dates for session-level context.

create table stg_curricular_experiences as
select
    session_id as raw_session_id,
    upper(trim(session_id)) as session_id,
    session_title,
    block,
    cast(delivery_date as date) as delivery_date,
    modality
from raw_curricular_experiences;

-- ==========================================================
-- COMPETENCY CROSSWALK
-- ==========================================================
-- Map shorthand/case variants to canonical competency labels.

create table stg_competency_crosswalk as
select
    session_id as raw_session_id,
    upper(trim(session_id)) as session_id,
    competency_domain as raw_competency_domain,
    case upper(trim(competency_domain))
        when 'KP' then 'Knowledge for Practice'
        when 'PC' then 'Patient Care'
        when 'IPC' then 'Interprofessional Collaboration'
        when 'PROFESSIONALISM' then 'Professionalism'
        when 'PATIENT CARE' then 'Patient Care'
        when 'INTERPERSONAL AND COMMUNICATION SKILLS' then 'Interpersonal and Communication Skills'
        when 'INTERPROFESSIONAL COLLABORATION' then 'Interprofessional Collaboration'
        when 'KNOWLEDGE FOR PRACTICE' then 'Knowledge for Practice'
        when 'SYSTEMS-BASED PRACTICE' then 'Systems-Based Practice'
        when 'PRACTICE-BASED LEARNING AND IMPROVEMENT' then 'Practice-Based Learning and Improvement'
        else trim(competency_domain)
    end as competency_domain
from raw_competency_crosswalk;

-- ==========================================================
-- ASSESSMENT EVENTS
-- ==========================================================
-- Normalize learner/session IDs, parse mixed date formats, classify score quality,
-- and calculate score percentages without overwriting raw score values.

create table stg_assessment_events as
with cleaned as (
    select
        event_id,
        learner_id as raw_learner_id,
        session_id as raw_session_id,
        instrument,
        score as score_raw,
        max_score as max_score_raw,
        assessment_date as assessment_date_raw,
        replace(upper(trim(learner_id)), '-', '') as learner_id_clean,
        upper(trim(session_id)) as session_id,
        coalesce(upper(trim(score)), '') as score_clean,
        coalesce(trim(max_score), '') as max_score_clean,
        coalesce(
            try_strptime(assessment_date, '%Y-%m-%d'),
            try_strptime(assessment_date, '%m/%d/%Y'),
            try_strptime(assessment_date, '%m/%d/%y')
        )::date as assessment_date
    from raw_assessment_events
)
select
    event_id,
    raw_learner_id,
    case
        -- Convert bare numeric IDs like `52` to the canonical `VU0052` format.
        when regexp_matches(learner_id_clean, '^[0-9]+$') then 'VU' || lpad(learner_id_clean, 4, '0')
        -- Convert IDs like `VU-0024`, `vu0105`, or `VU24` to canonical `VU####`.
        when regexp_matches(learner_id_clean, '^VU[0-9]+$') then 'VU' || lpad(substr(learner_id_clean, 3), 4, '0')
        else learner_id_clean
    end as learner_id,
    raw_session_id,
    session_id,
    instrument,
    score_raw,
    max_score_raw,
    try_cast(nullif(score_clean, '') as double) as score_numeric,
    try_cast(nullif(max_score_clean, '') as double) as max_score_numeric,
    case
        when try_cast(nullif(score_clean, '') as double) is not null
            and try_cast(nullif(max_score_clean, '') as double) > 0
            then try_cast(nullif(score_clean, '') as double) / try_cast(nullif(max_score_clean, '') as double)
        else null
    end as score_pct,
    case
        when score_clean in ('P', 'F') then 'pass_fail'
        when score_clean = '' then 'missing_score'
        when try_cast(score_clean as double) is null then 'other_non_numeric_score'
        when max_score_clean = '' then 'numeric_score_missing_max'
        when try_cast(max_score_clean as double) is null then 'non_numeric_max_score'
        when try_cast(max_score_clean as double) <= 0 then 'non_positive_max_score'
        when try_cast(score_clean as double) < 0 then 'negative_score'
        when try_cast(score_clean as double) > try_cast(max_score_clean as double) then 'above_max_score'
        else 'valid_numeric_in_range'
    end as score_quality_status,
    assessment_date_raw,
    assessment_date,
    case
        when assessment_date is null then 'unparsed'
        -- Expected window comes from the observed 2024-2025 pre-clerkship source files.
        when assessment_date < date '2024-08-01' or assessment_date > date '2025-06-30' then 'outside_expected_window'
        else 'in_expected_window'
    end as assessment_date_quality
from cleaned;

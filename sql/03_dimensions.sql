-- ==========================================================
-- DIMENSION TABLES
-- ==========================================================
-- Dimensions provide one governed row per analysis entity: learner, session,
-- and competency domain.

-- ==========================================================
-- LEARNER DIMENSION
-- ==========================================================
-- Collapse likely duplicate source learner rows to one row per normalized ID.
-- Names and emails stay out of the director-facing dimension.

create table dim_learner as
select
    learner_id,
    max(cohort_year) as cohort_year,
    max(matriculation_year) as matriculation_year,
    max(matriculation_year_quality) as matriculation_year_quality,
    max(status) as status,
    count(*) as source_record_count,
    count(*) > 1 as has_likely_dup_source_records,
    max(cohort_year) is null as has_missing_cohort,
    string_agg(distinct raw_learner_id, '; ' order by raw_learner_id) as raw_learner_ids_seen,
    string_agg(distinct raw_cohort, '; ' order by raw_cohort) as raw_cohorts_seen
from stg_learners
group by learner_id;

-- ==========================================================
-- SESSION DIMENSION
-- ==========================================================
-- Collapse duplicate session metadata to one row per normalized session ID.
-- For S005-style conflicts, the latest delivery-date row is canonical while
-- raw title/date variants remain available for governance review.

create table dim_session as
with grouped as (
    select
        session_id,
        count(*) as source_record_count,
        count(*) > 1 as has_likely_dup_source_records,
        count(distinct session_title) > 1 or count(distinct delivery_date) > 1 as has_metadata_conflict,
        string_agg(distinct session_title, '; ' order by session_title) as raw_session_titles_seen,
        string_agg(distinct cast(delivery_date as varchar), '; ' order by cast(delivery_date as varchar)) as raw_delivery_dates_seen
    from stg_curricular_experiences
    group by session_id
), canonical as (
    select
        session_id,
        session_title,
        block,
        delivery_date,
        modality,
        row_number() over (partition by session_id order by delivery_date desc, session_title desc) as row_number_desc_date
    from stg_curricular_experiences
)
select
    canonical.session_id,
    canonical.session_title,
    canonical.block,
    canonical.delivery_date,
    canonical.modality,
    grouped.source_record_count,
    grouped.has_likely_dup_source_records,
    grouped.has_metadata_conflict,
    grouped.raw_session_titles_seen,
    grouped.raw_delivery_dates_seen
from canonical
join grouped using (session_id)
where canonical.row_number_desc_date = 1;

-- ==========================================================
-- COMPETENCY DIMENSION
-- ==========================================================
-- One row per canonical competency domain observed in the crosswalk.

create table dim_competency as
select
    competency_domain,
    count(*) as crosswalk_row_count
from stg_competency_crosswalk
group by competency_domain;

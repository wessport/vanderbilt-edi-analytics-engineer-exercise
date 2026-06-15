-- ==========================================================
-- FACT TABLES
-- ==========================================================
-- Facts hold measurable events. This table preserves the full assessment event
-- population while adding eligibility flags for the progression indicator.

-- ==========================================================
-- ASSESSMENT EVENT FACT
-- ==========================================================
-- One row per source assessment event. Pass/fail events and quality issues are
-- retained here even when they are not used by the numeric competency mart.

create table fact_assessment_event as
select
    event.event_id,
    event.learner_id,
    event.session_id,
    event.instrument,
    event.assessment_date,
    event.assessment_date_raw,
    event.assessment_date_quality,
    event.score_raw,
    event.max_score_raw,
    event.score_numeric,
    event.max_score_numeric,
    event.score_pct,
    event.score_quality_status,
    learner.learner_id is null as has_orphan_learner,
    session.session_id is null as has_orphan_session,
    coalesce(crosswalk.crosswalk_count, 0) as competency_crosswalk_count,
    learner.status = 'Active'
        and learner.cohort_year is not null
        and event.score_quality_status = 'valid_numeric_in_range'
        and coalesce(crosswalk.crosswalk_count, 0) > 0
        and event.assessment_date_quality = 'in_expected_window'
        as use_in_indicator
from stg_assessment_events as event
left join dim_learner as learner
    on event.learner_id = learner.learner_id
left join dim_session as session
    on event.session_id = session.session_id
left join (
    select session_id, count(*) as crosswalk_count
    from stg_competency_crosswalk
    group by session_id
) as crosswalk
    on event.session_id = crosswalk.session_id;

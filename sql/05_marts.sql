-- ==========================================================
-- MART TABLES
-- ==========================================================
-- These tables are intended for dashboard-ready analytical tables.
-- This mart calculates the cohort-relative competency progression signal used
-- by the dashboard.

-- ==========================================================
-- LEARNER COMPETENCY PROGRESSION MART
-- ==========================================================
-- One row per active learner and competency domain. Valid assessment events are
-- expanded through the session-to-competency crosswalk, averaged, and compared
-- with the cohort/competency median benchmark.

-- View: all active learners crossed with all competency domains.
-- This makes learner-competency pairs with no valid scores visible as `not_scored`.
create temporary view tmp_active_learner_competency_grid as
select
    learner.learner_id,
    learner.cohort_year,
    competency.competency_domain
from dim_learner as learner
cross join dim_competency as competency
where learner.status = 'Active'
    and learner.cohort_year is not null;

-- View: valid numeric assessment events expanded to competency domains.
create temporary view tmp_valid_event_competency as
select
    fact.learner_id,
    learner.cohort_year,
    crosswalk.competency_domain,
    fact.event_id,
    fact.score_pct
from fact_assessment_event as fact
join dim_learner as learner
    on fact.learner_id = learner.learner_id
join stg_competency_crosswalk as crosswalk
    on fact.session_id = crosswalk.session_id
where fact.use_in_indicator;

-- View: average valid score percentage for each learner-competency pair.
create temporary view tmp_learner_domain_scores as
select
    learner_id,
    cohort_year,
    competency_domain,
    count(*) as valid_event_count,
    avg(score_pct) as learner_avg_score_pct
from tmp_valid_event_competency
group by learner_id, cohort_year, competency_domain;

-- View: cohort/competency benchmark based on learner-competency pairs with
-- at least two valid scored events.
create temporary view tmp_cohort_domain_benchmarks as
select
    cohort_year,
    competency_domain,
    median(learner_avg_score_pct) as cohort_median_score_pct,
    count(*) as cohort_benchmark_learner_count
from tmp_learner_domain_scores
where valid_event_count >= 2
group by cohort_year, competency_domain;

-- Final dashboard-ready mart.
create table mart_learner_competency_progression as
select
    grid.learner_id,
    grid.cohort_year,
    grid.competency_domain,
    coalesce(scores.valid_event_count, 0) as valid_event_count,
    scores.learner_avg_score_pct,
    benchmark.cohort_median_score_pct,
    benchmark.cohort_benchmark_learner_count,
    scores.learner_avg_score_pct - benchmark.cohort_median_score_pct as gap_from_cohort_median_pct,
    case
        when coalesce(scores.valid_event_count, 0) = 0 then 'not_scored'
        when scores.valid_event_count = 1 then 'limited_evidence'
        when benchmark.cohort_benchmark_learner_count is null or benchmark.cohort_benchmark_learner_count < 3 then 'limited_benchmark'
        when scores.learner_avg_score_pct - benchmark.cohort_median_score_pct <= -0.10 then 'monitor'
        when scores.learner_avg_score_pct - benchmark.cohort_median_score_pct >= 0.10 then 'strength'
        else 'on_track'
    end as monitor_status
from tmp_active_learner_competency_grid as grid
left join tmp_learner_domain_scores as scores
    on grid.learner_id = scores.learner_id
    and grid.cohort_year = scores.cohort_year
    and grid.competency_domain = scores.competency_domain
left join tmp_cohort_domain_benchmarks as benchmark
    on grid.cohort_year = benchmark.cohort_year
    and grid.competency_domain = benchmark.competency_domain;

-- ==========================================================
-- RAW TABLES
-- ==========================================================
-- Load each source CSV into DuckDB with all fields as text.
-- These tables intentionally mirror the source files as closely as possible.

create table raw_learners as
select *
from read_csv('data/raw/learners.csv', all_varchar = true, header = true);

create table raw_curricular_experiences as
select *
from read_csv('data/raw/curricular_experiences.csv', all_varchar = true, header = true);

create table raw_competency_crosswalk as
select *
from read_csv('data/raw/competency_crosswalk.csv', all_varchar = true, header = true);

create table raw_assessment_events as
select *
from read_csv('data/raw/assessment_events.csv', all_varchar = true, header = true);

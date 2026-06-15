"""Director-facing Dash dashboard for the EDI competency progression model."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import duckdb
import plotly.graph_objects as go
from dash import Dash, dash_table, dcc, html

from scripts.build_model import main as build_model


ROOT = Path(__file__).resolve().parent
DATABASE_PATH = ROOT / "data" / "edi_analytics.duckdb"

STATUS_LABELS = {
    "strength": "Strength",
    "on_track": "On track",
    "monitor": "Review suggested",
    "limited_evidence": "Limited evidence",
    "not_scored": "Not scored",
    "limited_benchmark": "Limited benchmark",
}
STATUS_ORDER = ["strength", "on_track", "monitor", "limited_evidence", "not_scored", "limited_benchmark"]
STATUS_COLORS = {
    "strength": "#009E73",
    "on_track": "#0072B2",
    "monitor": "#D55E00",
    "limited_evidence": "#E69F00",
    "not_scored": "#8A8A8A",
    "limited_benchmark": "#CC79A7",
}


def ensure_database() -> None:
    if not DATABASE_PATH.exists():
        build_model()


def fetch_rows(query: str) -> list[dict[str, Any]]:
    with duckdb.connect(str(DATABASE_PATH), read_only=True) as connection:
        result = connection.execute(query)
        columns = [column[0] for column in result.description]
        return [dict(zip(columns, row)) for row in result.fetchall()]


def fetch_one(query: str) -> dict[str, Any]:
    rows = fetch_rows(query)
    return rows[0] if rows else {}


def pct(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value * 100:.1f}%"


def pp(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value * 100:+.1f} pp"


def display_reason(value: str) -> str:
    return value[:1].upper() + value[1:] if value else value


def metric_card(label: str, value: str, note: str, tone: str = "default") -> html.Div:
    return html.Div(
        className=f"metric-card metric-card--{tone}",
        children=[
            html.Div(label, className="metric-label"),
            html.Div(value, className="metric-value"),
            html.Div(note, className="metric-note"),
        ],
    )


def build_status_figure(status_rows: list[dict[str, Any]]) -> go.Figure:
    counts = {row["monitor_status"]: row["row_count"] for row in status_rows}
    statuses = [status for status in STATUS_ORDER if status in counts]
    fig = go.Figure(
        data=[
            go.Bar(
                y=[STATUS_LABELS[status] for status in statuses],
                x=[counts[status] for status in statuses],
                orientation="h",
                marker_color=[STATUS_COLORS[status] for status in statuses],
                text=[counts[status] for status in statuses],
                textposition="outside",
                hovertemplate="%{y}<br>%{x} learner-competency pairs<extra></extra>",
            )
        ]
    )
    fig.update_layout(
        margin=dict(l=132, r=42, t=10, b=36),
        height=330,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#1C1C1C"),
        xaxis_title="Learner-competency pairs",
        yaxis_title="",
        showlegend=False,
    )
    fig.update_xaxes(gridcolor="rgba(28, 28, 28, 0.12)", zeroline=False)
    fig.update_yaxes(autorange="reversed")
    return fig


def build_cohort_score_figure(cohort_score_rows: list[dict[str, Any]]) -> go.Figure:
    cohort_years = [str(row["cohort_year"]) for row in cohort_score_rows]
    fig = go.Figure()
    fig.add_bar(
        x=cohort_years,
        y=[row["median_score_pct"] for row in cohort_score_rows],
        marker_color=STATUS_COLORS["on_track"],
        text=[pct(row["median_score_pct"]) for row in cohort_score_rows],
        textposition="outside",
        customdata=[row["learner_domain_pairs"] for row in cohort_score_rows],
        hovertemplate="Cohort %{x}<br>Overall median score %{text}<br>%{customdata} learner-competency pairs<extra></extra>",
    )
    fig.update_layout(
        margin=dict(l=36, r=20, t=8, b=32),
        height=330,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#1C1C1C"),
        xaxis_title="Cohort",
        yaxis_title="Overall median score",
        showlegend=False,
    )
    fig.update_yaxes(gridcolor="rgba(28, 28, 28, 0.12)", zeroline=False, tickformat=".0%", range=[0, 1])
    return fig


def build_domain_figure(domain_rows: list[dict[str, Any]]) -> go.Figure:
    domains = sorted({row["competency_domain"] for row in domain_rows})
    row_lookup = {(row["competency_domain"], row["monitor_status"]): row["row_count"] for row in domain_rows}

    fig = go.Figure()
    for status in STATUS_ORDER:
        values = [row_lookup.get((domain, status), 0) for domain in domains]
        if not any(values):
            continue
        fig.add_bar(
            y=domains,
            x=values,
            name=STATUS_LABELS[status],
            orientation="h",
            marker_color=STATUS_COLORS[status],
            hovertemplate=f"{STATUS_LABELS[status]}<br>%{{y}}<br>%{{x}} learner-competency pairs<extra></extra>",
        )

    fig.update_layout(
        barmode="stack",
        margin=dict(l=20, r=20, t=20, b=30),
        height=420,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#1C1C1C"),
        xaxis_title="Learner-competency pairs",
        yaxis_title="",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
    )
    fig.update_xaxes(gridcolor="rgba(28, 28, 28, 0.12)", zeroline=False)
    return fig


def load_dashboard_data() -> dict[str, Any]:
    kpis = fetch_one(
        """
        select
            (select count(*) from dim_learner where status = 'Active') as active_learners,
            (select count(*) from mart_learner_competency_progression where monitor_status = 'monitor') as monitor_pairs,
            (select count(distinct learner_id) from mart_learner_competency_progression where monitor_status = 'monitor') as monitor_learners,
            (select count(*) from mart_learner_competency_progression where monitor_status = 'strength') as strength_pairs,
            (select count(*) from mart_learner_competency_progression where monitor_status = 'limited_evidence') as limited_evidence_pairs,
            (select count(*) from fact_assessment_event where not use_in_indicator) as not_indicator_events
        """
    )
    status_rows = fetch_rows(
        """
        select monitor_status, count(*) as row_count, count(distinct learner_id) as learner_count
        from mart_learner_competency_progression
        group by monitor_status
        """
    )
    domain_rows = fetch_rows(
        """
        select competency_domain, monitor_status, count(*) as row_count
        from mart_learner_competency_progression
        group by competency_domain, monitor_status
        """
    )
    follow_up_rows = fetch_rows(
        """
        select
            learner_id,
            cohort_year,
            competency_domain,
            valid_event_count,
            learner_avg_score_pct,
            cohort_median_score_pct,
            gap_from_cohort_median_pct,
            monitor_status
        from mart_learner_competency_progression
        where monitor_status in ('monitor', 'strength')
        order by
            case when monitor_status = 'monitor' then 0 else 1 end,
            gap_from_cohort_median_pct
        """
    )
    quality_rows = fetch_rows(
        """
        select score_quality_status, count(*) as event_count
        from fact_assessment_event
        group by score_quality_status
        order by event_count desc
        """
    )
    coverage_rows = fetch_rows(
        """
        select
            case
                when use_in_indicator then 'Used in progression indicator'
                when has_orphan_learner then 'Orphan learner reference'
                when has_orphan_session then 'Orphan session reference'
                when competency_crosswalk_count = 0 then 'No competency crosswalk'
                when assessment_date_quality <> 'in_expected_window' then 'Outside expected date window'
                when score_quality_status <> 'valid_numeric_in_range' then replace(score_quality_status, '_', ' ')
                else 'Other not indicator-eligible event'
            end as reason,
            count(*) as event_count
        from fact_assessment_event
        group by reason
        order by event_count desc
        """
    )
    cohort_score_rows = fetch_rows(
        """
        select
            cohort_year,
            count(*) as learner_domain_pairs,
            median(learner_avg_score_pct) as median_score_pct
        from mart_learner_competency_progression
        where valid_event_count >= 2
            and learner_avg_score_pct is not null
        group by cohort_year
        order by cohort_year
        """
    )
    return {
        "kpis": kpis,
        "status_rows": status_rows,
        "domain_rows": domain_rows,
        "follow_up_rows": follow_up_rows,
        "quality_rows": quality_rows,
        "coverage_rows": coverage_rows,
        "cohort_score_rows": cohort_score_rows,
    }


ensure_database()
data = load_dashboard_data()

follow_up_table_rows = [
    {
        "learner_id": row["learner_id"],
        "cohort_year": row["cohort_year"],
        "competency_domain": row["competency_domain"],
        "status": STATUS_LABELS[row["monitor_status"]],
        "valid_events": row["valid_event_count"],
        "learner_avg": pct(row["learner_avg_score_pct"]),
        "cohort_median": pct(row["cohort_median_score_pct"]),
        "gap": pp(row["gap_from_cohort_median_pct"]),
    }
    for row in data["follow_up_rows"]
]

quality_text = ", ".join(
    f"{row['event_count']:,} {row['score_quality_status'].replace('_', ' ')}" for row in data["quality_rows"][:4]
)

app = Dash(__name__, title="EDI Competency Progression Overview")
server = app.server

app.layout = html.Div(
    className="page-shell",
    children=[
        html.Header(
            className="hero",
            children=[
                html.Div("Vanderbilt University School of Medicine", className="eyebrow"),
                html.H1("Learner Progression Signals by Competency"),
                html.P(
                    "Cohort overview and competency performance.",
                    className="hero-subtitle",
                ),
            ],
        ),
        html.Section(
            className="metric-grid",
            children=[
                metric_card("Active learners", f"{data['kpis']['active_learners']:,}", "Modeled from normalized learner IDs."),
                metric_card(
                    "Review suggested",
                    f"{data['kpis']['monitor_learners']:,} learners",
                    "At least one review-suggested competency.",
                    "monitor",
                ),
                metric_card(
                    "Strength signals",
                    f"{data['kpis']['strength_pairs']:,}",
                    "Learner-competency averages at least 10 pp above cohort median.",
                    "strength",
                ),
                metric_card(
                    "Limited evidence",
                    f"{data['kpis']['limited_evidence_pairs']:,}",
                    "Learner-competency pairs with exactly one valid scored event.",
                    "evidence",
                ),
            ],
        ),
        html.Main(
            className="content-grid",
            children=[
                html.Div(
                    className="overview-grid panel--wide",
                    children=[
                        html.Section(
                            className="panel definition-panel",
                            children=[
                                html.Div(
                                    className="panel-heading",
                                    children=[
                                        html.H2("Indicator definitions"),
                                        html.P("Methodology notes for interpreting learner-competency signals."),
                                    ],
                                ),
                                html.Div(
                                    className="definition-grid",
                                    children=[
                                        html.Div(
                                            children=[
                                                html.H3("Strength"),
                                                html.P("At least two valid events and learner average is 10+ percentage points above the cohort/competency median."),
                                            ]
                                        ),
                                        html.Div(
                                            children=[
                                                html.H3("On track"),
                                                html.P("At least two valid events and learner average is within ±10 percentage points of the cohort/competency median."),
                                            ]
                                        ),
                                        html.Div(
                                            children=[
                                                html.H3("Review suggested"),
                                                html.P("At least two valid events and learner average is 10+ percentage points below the cohort/competency median."),
                                            ]
                                        ),
                                        html.Div(
                                            children=[
                                                html.H3("Limited evidence"),
                                                html.P("Exactly one valid event for the learner and competency, so the signal is not yet interpreted."),
                                            ]
                                        ),
                                        html.Div(
                                            children=[
                                                html.H3("Not scored"),
                                                html.P("No valid numeric scored events for the learner and competency."),
                                            ]
                                        ),
                                        html.Div(
                                            children=[
                                                html.H3("Valid event"),
                                                html.P("Passed data quality checks, matched learner/session records, and mapped to a competency."),
                                            ]
                                        ),
                                    ],
                                ),
                            ],
                        ),
                        html.Section(
                            className="panel status-panel",
                            children=[
                                html.Div(
                                    className="panel-heading",
                                    children=[
                                        html.H2("Status distribution"),
                                        html.P("One row in this chart is one learner + competency."),
                                    ],
                                ),
                                dcc.Graph(figure=build_status_figure(data["status_rows"]), config={"displayModeBar": False}),
                                html.Div(
                                    className="subchart-heading",
                                    children=[
                                        html.H3("Overall median score by cohort"),
                                        html.P("Across competencies; table benchmarks are cohort + competency specific."),
                                    ],
                                ),
                                dcc.Graph(figure=build_cohort_score_figure(data["cohort_score_rows"]), config={"displayModeBar": False}),
                            ],
                        ),
                    ],
                ),
                html.Section(
                    className="panel panel--wide methodology-panel",
                    children=[
                        html.Div(
                            className="panel-heading",
                            children=[
                                html.H2("How the indicator is calculated"),
                                html.P("Calculation grain and benchmark logic."),
                            ],
                        ),
                        dcc.Markdown(
                            """
1. For each learner + competency, calculate that learner's average score in that competency using valid events.
   - Example: one learner's Patient Care average is calculated separately from that learner's Knowledge for Practice average.
2. Keep only learner-competency pairs with at least two valid scored events before assigning review, on-track, or strength status.
3. Within each cohort year and competency, compare learner-competency averages with the cohort/competency median benchmark.

The overall cohort score chart uses the same learner-competency averages, then summarizes them by cohort year across competencies.
                            """.strip(),
                            className="markdown-block",
                        ),
                    ],
                ),
                html.Section(
                    className="panel panel--wide",
                    children=[
                        html.Div(
                            className="panel-heading",
                            children=[
                                html.H2("Competency profile"),
                                html.P("Shows where evidence is strong enough to interpret and where coverage is limited."),
                            ],
                        ),
                        dcc.Graph(figure=build_domain_figure(data["domain_rows"]), config={"displayModeBar": False}),
                    ],
                ),
                html.Section(
                    className="panel panel--table panel--wide",
                    children=[
                        html.Div(
                            className="panel-heading",
                            children=[
                                html.H2("Learner-competency signals for follow-up review"),
                                html.P("Includes review-suggested and strength signals. Learner names are intentionally omitted."),
                            ],
                        ),
                        dash_table.DataTable(
                            data=follow_up_table_rows,
                            columns=[
                                {"name": "Learner ID", "id": "learner_id"},
                                {"name": "Cohort", "id": "cohort_year"},
                                {"name": "Competency", "id": "competency_domain"},
                                {"name": "Status", "id": "status"},
                                {"name": "Valid events", "id": "valid_events"},
                                {"name": "Learner avg", "id": "learner_avg"},
                                {"name": "Cohort median", "id": "cohort_median"},
                                {"name": "Gap", "id": "gap"},
                            ],
                            page_size=12,
                            sort_action="native",
                            style_as_list_view=True,
                            style_cell={
                                "fontFamily": "Satoshi, ui-sans-serif, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
                                "fontSize": "14px",
                                "padding": "10px",
                            },
                            style_header={"fontWeight": "700", "backgroundColor": "#F5F3EF"},
                            style_data_conditional=[
                                {"if": {"filter_query": '{status} = "Review suggested"'}, "backgroundColor": "#f7efe1"},
                                {"if": {"filter_query": '{status} = "Strength"'}, "backgroundColor": "#edf2ed"},
                            ],
                        ),
                    ],
                ),
                html.Section(
                    className="panel notes-panel",
                    children=[
                        html.Div(className="panel-heading", children=[html.H2("Evidence notes"), html.P("Context for interpreting the indicator.")]),
                        html.Ul(
                            children=[
                                html.Li("Review-suggested status uses at least two valid scored events and a 10 percentage-point gap from cohort/competency median."),
                                html.Li("Pass/fail professionalism attestations are preserved in the fact table but excluded from this numeric indicator."),
                                html.Li("Sessions without competency crosswalks are counted as coverage gaps rather than inferred into a competency."),
                                html.Li(f"Score quality profile includes {quality_text}."),
                            ]
                        ),
                    ],
                ),
                html.Section(
                    className="panel notes-panel",
                    children=[
                        html.Div(className="panel-heading", children=[html.H2("Data quality notes"), html.P("Observations and limitations by eligibility reason.")]),
                        html.Div(
                            className="coverage-list",
                            children=[
                                html.Div(
                                    className="coverage-row",
                                    children=[html.Span(display_reason(row["reason"])), html.Strong(f"{row['event_count']:,}")],
                                )
                                for row in data["coverage_rows"][:6]
                            ],
                        ),
                    ],
                ),
            ],
        ),
    ],
)


if __name__ == "__main__":
    app.run_server(debug=False)

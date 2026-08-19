from __future__ import annotations

import sys
from pathlib import Path

import plotly.graph_objects as go
from dash import Dash, Input, Output, State, callback, dcc, html, no_update

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from canada_census_lang.dash_maps import (  # noqa: E402
    build_change_figure,
    build_prevalence_figure,
    build_rank_figure,
    common_change_languages,
    comparison_dimensions,
    load_change_table,
    load_data,
    load_map_index,
    load_rank_table,
    map_assets,
)

COLOR_SCALES = ["Blues", "Reds", "Greens", "Purples", "Viridis", "YlGnBu", "Oranges"]
DEFAULT_COLORS = ["Blues", "Reds", "Greens", "Purples"]
CHANGE_COLOR_SCALES = ["RdBu", "BrBG", "PiYG", "PRGn", "PuOr", "RdYlBu", "Spectral"]
DEFAULT_CHANGE_COLORS = ["RdBu", "BrBG", "PiYG", "PRGn"]
GRAPH_CONFIG = {
    "displaylogo": False,
    "responsive": True,
    "scrollZoom": True,
    "modeBarButtonsToRemove": ["lasso2d", "select2d"],
}

app = Dash(__name__, title="Canada Census Language Explorer", compress=True)
server = app.server


def dropdown_options(values) -> list[dict[str, str]]:
    return [{"label": str(v), "value": str(v)} for v in values]


def empty_figure(message: str = "") -> go.Figure:
    fig = go.Figure()
    fig.update_layout(
        height=620,
        margin={"l": 0, "r": 0, "t": 0, "b": 0},
        paper_bgcolor="#f5f7fa",
        plot_bgcolor="#f5f7fa",
        xaxis={"visible": False},
        yaxis={"visible": False},
        annotations=[{
            "text": message,
            "xref": "paper",
            "yref": "paper",
            "x": 0.5,
            "y": 0.5,
            "showarrow": False,
            "font": {"size": 16, "color": "#667085"},
        }] if message else [],
    )
    return fig


def setup_error(exc: Exception) -> html.Div:
    return html.Div(
        [
            html.Strong("Prepared data are not available."),
            html.Div("Run these commands from the project root:"),
            html.Pre(
                "python scripts/download_data.py\n"
                "python scripts/prepare_data.py\n"
                "python scripts/prepare_app_assets.py\n"
                "python scripts/check_app_setup.py\n"
                "python app.py"
            ),
            html.Small(str(exc)),
        ],
        className="error-banner",
    )


def control(label: str, component, class_name: str = "") -> html.Div:
    return html.Div(
        [html.Label(label, className="control-label"), component],
        className=f"control {class_name}".strip(),
    )


def language_slots(prefix: str, color_scales: list[str], defaults: list[str]) -> html.Div:
    return html.Div(
        [
            html.Div(
                [
                    html.Div(f"Map {i}", className="slot-title"),
                    dcc.Dropdown(
                        id=f"{prefix}-language-{i}",
                        placeholder="Optional" if i > 1 else "Select language",
                        clearable=(i > 1),
                    ),
                    dcc.Dropdown(
                        id=f"{prefix}-color-{i}",
                        options=dropdown_options(color_scales),
                        value=defaults[i - 1],
                        clearable=False,
                        searchable=False,
                        className="color-select",
                    ),
                ],
                className="language-slot",
            )
            for i in range(1, 5)
        ],
        className="language-slots",
    )


def boundary_controls(prefix: str) -> html.Div:
    return html.Div(
        [
            dcc.Checklist(
                id=f"{prefix}-divisions",
                options=[{"label": "Census divisions", "value": "divisions"}],
                value=["divisions"],
                inline=True,
            ),
            dcc.Checklist(
                id=f"{prefix}-provinces",
                options=[{"label": "Provinces", "value": "provinces"}],
                value=[],
                inline=True,
            ),
        ],
        className="boundary-controls",
    )


app.layout = html.Div(
    [
        dcc.Interval(id="viewport-init", interval=250, max_intervals=1),
        dcc.Store(id="viewport", data=None),
        html.Div(
            [
                html.Div(
                    [
                        html.H1("Canada Census Language Explorer"),
                        html.Div(
                            "Census Division mother-tongue patterns from the 2016 and 2021 censuses.",
                            className="subtitle",
                        ),
                    ],
                    className="heading",
                ),
                html.Div(
                    control(
                        "Census year",
                        dcc.Dropdown(
                            id="year",
                            options=[{"label": "2021", "value": 2021}, {"label": "2016", "value": 2016}],
                            value=2021,
                            clearable=False,
                            searchable=False,
                        ),
                        "year-control",
                    ),
                    id="year-control-wrap",
                    className="year-control-wrap",
                ),
            ],
            className="topbar",
        ),
        dcc.Tabs(
            id="view",
            value="prevalence",
            className="custom-tabs",
            parent_className="tabs-parent",
            children=[
                dcc.Tab(label="Prevalence map", value="prevalence", className="custom-tab", selected_className="custom-tab--selected"),
                dcc.Tab(label="Ranked languages", value="ranked", className="custom-tab", selected_className="custom-tab--selected"),
                dcc.Tab(label="2016→2021 change", value="change", className="custom-tab", selected_className="custom-tab--selected"),
            ],
        ),
        html.Div(id="setup-status"),

        html.Div(
            [
                html.Div(
                    [
                        control(
                            "Measure",
                            dcc.RadioItems(
                                id="prevalence-level",
                                options=[
                                    {"label": "Detailed language", "value": "LanguageName"},
                                    {"label": "Language group", "value": "LanguageGroup"},
                                ],
                                value="LanguageName",
                                inline=True,
                            ),
                        ),
                        control("Geography", dcc.Dropdown(id="prevalence-geography", clearable=False)),
                        control("Boundaries", boundary_controls("prevalence")),
                    ],
                    className="control-row primary-controls",
                ),
                html.Div(
                    "Detailed language counts are single mother-tongue responses; percentages use the full mother-tongue population as denominator.",
                    className="data-note",
                ),
                language_slots("prevalence", COLOR_SCALES, DEFAULT_COLORS),
                html.Div(id="prevalence-map-grid", className="map-grid maps-1"),
            ],
            id="prevalence-panel",
        ),

        html.Div(
            [
                html.Div(
                    [
                        control(
                            "Rank by",
                            dcc.RadioItems(
                                id="rank-level",
                                options=[
                                    {"label": "Detailed language", "value": "LanguageName"},
                                    {"label": "Language group", "value": "LanguageGroup"},
                                ],
                                value="LanguageName",
                                inline=True,
                            ),
                        ),
                        control("Position", dcc.Input(id="rank-position", type="number", min=1, value=1, step=1)),
                        control("Geography", dcc.Dropdown(id="rank-geography", clearable=False)),
                        control(
                            "Display",
                            html.Div(
                                [
                                    boundary_controls("rank"),
                                    dcc.Checklist(
                                        id="rank-legend",
                                        options=[{"label": "Legend", "value": "legend"}],
                                        value=[],
                                        inline=True,
                                    ),
                                ],
                                className="rank-display-controls",
                            ),
                        ),
                    ],
                    className="control-row rank-controls",
                ),
                html.Div(
                    [
                        dcc.Graph(id="rank-map", figure=empty_figure(), config=GRAPH_CONFIG, responsive=True),
                        html.Div(id="rank-legend-box", className="floating-legend hidden"),
                    ],
                    className="rank-map-wrap",
                ),
            ],
            id="ranked-panel",
            style={"display": "none"},
        ),

        html.Div(
            [
                html.Div(
                    [
                        control(
                            "Change measure",
                            dcc.RadioItems(
                                id="change-metric",
                                options=[
                                    {"label": "Mother-tongue count change (%)", "value": "speaker_change_pct"},
                                    {"label": "Population-share change (percentage points)", "value": "share_change_pp"},
                                ],
                                value="speaker_change_pct",
                                inline=True,
                            ),
                        ),
                        control(
                            "Measure",
                            dcc.RadioItems(
                                id="change-level",
                                options=[
                                    {"label": "Detailed language", "value": "LanguageName"},
                                    {"label": "Language group", "value": "LanguageGroup"},
                                ],
                                value="LanguageName",
                                inline=True,
                            ),
                        ),
                        control("Geography", dcc.Dropdown(id="change-geography", clearable=False)),
                        control("Boundaries", boundary_controls("change")),
                    ],
                    className="control-row change-controls",
                ),
                html.Div(
                    "Change maps use 2021 Census Division geography. Where boundaries differ, 2016 counts are approximately allocated using polygon overlap and 2021 population weights. Only comparable 2016/2021 language labels are offered.",
                    className="change-note",
                ),
                language_slots("change", CHANGE_COLOR_SCALES, DEFAULT_CHANGE_COLORS),
                html.Div(id="change-map-grid", className="map-grid maps-1"),
            ],
            id="change-panel",
            style={"display": "none"},
        ),
    ],
    className="app-shell",
)


app.clientside_callback(
    """
    function(n) {
        return {
            width: window.innerWidth || 1440,
            height: window.innerHeight || 900
        };
    }
    """,
    Output("viewport", "data"),
    Input("viewport-init", "n_intervals"),
)


@callback(
    Output("prevalence-panel", "style"),
    Output("ranked-panel", "style"),
    Output("change-panel", "style"),
    Output("year-control-wrap", "style"),
    Input("view", "value"),
)
def switch_view(view: str):
    hidden = {"display": "none"}
    shown = {"display": "block"}
    return (
        shown if view == "prevalence" else hidden,
        shown if view == "ranked" else hidden,
        shown if view == "change" else hidden,
        hidden if view == "change" else shown,
    )


@callback(
    Output("setup-status", "children"),
    Input("view", "value"),
    Input("year", "value"),
)
def check_setup(view: str, year: int):
    try:
        if view == "change":
            load_data(2016, "LanguageName")
            load_data(2021, "LanguageName")
            load_change_table("LanguageName")
            map_assets(2021, "Canada")
        else:
            load_data(int(year), "LanguageName")
            load_map_index(int(year))
            map_assets(int(year), "Canada")
        return ""
    except Exception as exc:
        return setup_error(exc)


@callback(
    Output("prevalence-language-1", "options"),
    Output("prevalence-language-2", "options"),
    Output("prevalence-language-3", "options"),
    Output("prevalence-language-4", "options"),
    Output("prevalence-language-1", "value"),
    Output("prevalence-language-2", "value"),
    Output("prevalence-language-3", "value"),
    Output("prevalence-language-4", "value"),
    Input("year", "value"),
    Input("prevalence-level", "value"),
    State("prevalence-language-1", "value"),
    State("prevalence-language-2", "value"),
    State("prevalence-language-3", "value"),
    State("prevalence-language-4", "value"),
)
def update_prevalence_language_options(year, level, current1, current2, current3, current4):
    try:
        df = load_data(int(year), level)
    except Exception:
        return [], [], [], [], None, None, None, None
    values = sorted(str(x) for x in df[level].dropna().unique())
    options = dropdown_options(values)
    current = [current1, current2, current3, current4]
    default = "English" if "English" in values else (values[0] if values else None)
    selected = [value if value in values else (default if i == 0 else None) for i, value in enumerate(current)]
    return options, options, options, options, *selected


@callback(
    Output("change-language-1", "options"),
    Output("change-language-2", "options"),
    Output("change-language-3", "options"),
    Output("change-language-4", "options"),
    Output("change-language-1", "value"),
    Output("change-language-2", "value"),
    Output("change-language-3", "value"),
    Output("change-language-4", "value"),
    Input("change-level", "value"),
    State("change-language-1", "value"),
    State("change-language-2", "value"),
    State("change-language-3", "value"),
    State("change-language-4", "value"),
)
def update_change_language_options(level, current1, current2, current3, current4):
    try:
        values = list(common_change_languages(level))
    except Exception:
        return [], [], [], [], None, None, None, None
    options = dropdown_options(values)
    current = [current1, current2, current3, current4]
    default = "English" if "English" in values else (values[0] if values else None)
    selected = [value if value in values else (default if i == 0 else None) for i, value in enumerate(current)]
    return options, options, options, options, *selected


def _geography_options(year: int) -> tuple[list[dict], list[str]]:
    index = load_map_index(int(year))
    provinces = sorted(str(x) for x in index["ProvinceName"].dropna().unique())
    values = ["Canada"] + provinces
    return dropdown_options(values), values


@callback(
    Output("prevalence-geography", "options"),
    Output("prevalence-geography", "value"),
    Output("rank-geography", "options"),
    Output("rank-geography", "value"),
    Output("change-geography", "options"),
    Output("change-geography", "value"),
    Input("year", "value"),
    State("prevalence-geography", "value"),
    State("rank-geography", "value"),
    State("change-geography", "value"),
)
def update_geographies(year, prevalence_current, rank_current, change_current):
    try:
        options, values = _geography_options(int(year))
        change_options, change_values = _geography_options(2021)
    except Exception:
        return [], None, [], None, [], None
    p = prevalence_current if prevalence_current in values else "Canada"
    r = rank_current if rank_current in values else "Canada"
    c = change_current if change_current in change_values else "Canada"
    return options, p, options, r, change_options, c


@callback(
    Output("rank-position", "max"),
    Output("rank-position", "value"),
    Input("view", "value"),
    Input("year", "value"),
    Input("rank-level", "value"),
    State("rank-position", "value"),
)
def update_rank_limit(view, year, level, current):
    if view != "ranked":
        return no_update, no_update
    try:
        table = load_rank_table(int(year), level)
        max_rank = max(1, int(table["Rank"].max()))
    except Exception:
        return 1, 1
    current = int(current or 1)
    return max_rank, min(max(current, 1), max_rank)


def _province_boundary_control(geography, division_values, province_values):
    enabled = geography == "Canada" and "divisions" in (division_values or [])
    option = [{"label": "Provinces", "value": "provinces", "disabled": not enabled}]
    return option, (province_values if enabled else [])


for prefix in ("prevalence", "rank", "change"):
    # callbacks cannot be generated safely with closure-bound decorated functions;
    # explicit callbacks are declared below.
    pass


@callback(
    Output("prevalence-provinces", "options"),
    Output("prevalence-provinces", "value"),
    Input("prevalence-geography", "value"),
    Input("prevalence-divisions", "value"),
    State("prevalence-provinces", "value"),
)
def prevalence_province_boundary_control(geography, division_values, province_values):
    return _province_boundary_control(geography, division_values, province_values)


@callback(
    Output("rank-provinces", "options"),
    Output("rank-provinces", "value"),
    Input("rank-geography", "value"),
    Input("rank-divisions", "value"),
    State("rank-provinces", "value"),
)
def rank_province_boundary_control(geography, division_values, province_values):
    return _province_boundary_control(geography, division_values, province_values)


@callback(
    Output("change-provinces", "options"),
    Output("change-provinces", "value"),
    Input("change-geography", "value"),
    Input("change-divisions", "value"),
    State("change-provinces", "value"),
)
def change_province_boundary_control(geography, division_values, province_values):
    return _province_boundary_control(geography, division_values, province_values)


@callback(
    Output("prevalence-map-grid", "children"),
    Output("prevalence-map-grid", "className"),
    Input("view", "value"),
    Input("year", "value"),
    Input("prevalence-level", "value"),
    Input("prevalence-geography", "value"),
    Input("prevalence-divisions", "value"),
    Input("prevalence-provinces", "value"),
    Input("prevalence-language-1", "value"),
    Input("prevalence-language-2", "value"),
    Input("prevalence-language-3", "value"),
    Input("prevalence-language-4", "value"),
    Input("prevalence-color-1", "value"),
    Input("prevalence-color-2", "value"),
    Input("prevalence-color-3", "value"),
    Input("prevalence-color-4", "value"),
    Input("viewport", "data"),
)
def render_prevalence_maps(
    view, year, level, geography, division_values, province_values,
    lang1, lang2, lang3, lang4, color1, color2, color3, color4, viewport,
):
    if view != "prevalence":
        return no_update, no_update
    if not viewport:
        return [html.Div("Loading map…", className="map-message")], "map-grid maps-1"
    if not geography:
        return [html.Div("Select a geography.", className="map-message")], "map-grid maps-1"
    active = [(lang, color) for lang, color in ((lang1, color1), (lang2, color2), (lang3, color3), (lang4, color4)) if lang]
    if not active:
        return [html.Div("Select at least one language or language group.", className="map-message")], "map-grid maps-1"

    width = int(viewport.get("width", 1440))
    height = int(viewport.get("height", 900))
    try:
        assets = map_assets(int(year), geography)
        columns, card_width, map_height = comparison_dimensions(len(active), width, height, assets["bounds"])
        show_divisions = "divisions" in (division_values or [])
        show_provinces = "provinces" in (province_values or []) and show_divisions and geography == "Canada"
        cards = []
        for slot, (language, color_scale) in enumerate(active, start=1):
            fig = build_prevalence_figure(
                year=int(year), level=level, language=language, geography=geography,
                color_scale=color_scale, show_divisions=show_divisions, show_provinces=show_provinces,
                graph_width=card_width, map_height=map_height, slot=slot, comparison_count=len(active),
            )
            cards.append(html.Div([
                html.Div(language, className="map-title"),
                dcc.Graph(
                    id=f"prevalence-map-{slot}", figure=fig, config=GRAPH_CONFIG, responsive=True,
                    style={"height": f"{int(fig.layout.height)}px"},
                ),
            ], className="map-card"))
        return cards, f"map-grid maps-{columns}"
    except Exception as exc:
        return [setup_error(exc)], "map-grid maps-1"


@callback(
    Output("change-map-grid", "children"),
    Output("change-map-grid", "className"),
    Input("view", "value"),
    Input("change-metric", "value"),
    Input("change-level", "value"),
    Input("change-geography", "value"),
    Input("change-divisions", "value"),
    Input("change-provinces", "value"),
    Input("change-language-1", "value"),
    Input("change-language-2", "value"),
    Input("change-language-3", "value"),
    Input("change-language-4", "value"),
    Input("change-color-1", "value"),
    Input("change-color-2", "value"),
    Input("change-color-3", "value"),
    Input("change-color-4", "value"),
    Input("viewport", "data"),
    prevent_initial_call=True,
)
def render_change_maps(
    view, metric, level, geography, division_values, province_values,
    lang1, lang2, lang3, lang4, color1, color2, color3, color4, viewport,
):
    if view != "change":
        return no_update, no_update
    if not viewport:
        return [html.Div("Loading map…", className="map-message")], "map-grid maps-1"
    if not geography:
        return [html.Div("Select a geography.", className="map-message")], "map-grid maps-1"
    active = [(lang, color) for lang, color in ((lang1, color1), (lang2, color2), (lang3, color3), (lang4, color4)) if lang]
    if not active:
        return [html.Div("Select at least one comparable language or language group.", className="map-message")], "map-grid maps-1"

    width = int(viewport.get("width", 1440))
    height = int(viewport.get("height", 900))
    try:
        assets = map_assets(2021, geography)
        columns, card_width, map_height = comparison_dimensions(len(active), width, height, assets["bounds"])
        show_divisions = "divisions" in (division_values or [])
        show_provinces = "provinces" in (province_values or []) and show_divisions and geography == "Canada"
        cards = []
        for slot, (language, color_scale) in enumerate(active, start=1):
            fig = build_change_figure(
                level=level, language=language, metric=metric, geography=geography,
                color_scale=color_scale, show_divisions=show_divisions, show_provinces=show_provinces,
                graph_width=card_width, map_height=map_height, slot=slot, comparison_count=len(active),
            )
            cards.append(html.Div([
                html.Div(language, className="map-title"),
                dcc.Graph(
                    id=f"change-map-{slot}", figure=fig, config=GRAPH_CONFIG, responsive=True,
                    style={"height": f"{int(fig.layout.height)}px"},
                ),
            ], className="map-card"))
        return cards, f"map-grid maps-{columns}"
    except Exception as exc:
        return [setup_error(exc)], "map-grid maps-1"


@callback(
    Output("rank-map", "figure"),
    Output("rank-map", "style"),
    Output("rank-legend-box", "children"),
    Output("rank-legend-box", "className"),
    Input("view", "value"),
    Input("year", "value"),
    Input("rank-level", "value"),
    Input("rank-position", "value"),
    Input("rank-geography", "value"),
    Input("rank-divisions", "value"),
    Input("rank-provinces", "value"),
    Input("rank-legend", "value"),
    Input("viewport", "data"),
    prevent_initial_call=True,
)
def render_ranked_map(view, year, level, rank, geography, division_values, province_values, legend_values, viewport):
    if view != "ranked":
        return no_update, no_update, no_update, no_update
    if not viewport:
        return empty_figure("Loading map…"), {"height": "620px"}, [], "floating-legend hidden"
    if not geography:
        return empty_figure("Select a geography."), {"height": "620px"}, [], "floating-legend hidden"

    width = int(viewport.get("width", 1440))
    height = int(viewport.get("height", 900))
    try:
        assets = map_assets(int(year), geography)
        _, graph_width, map_height = comparison_dimensions(1, width, height, assets["bounds"])
        show_divisions = "divisions" in (division_values or [])
        show_provinces = "provinces" in (province_values or []) and show_divisions and geography == "Canada"
        fig, legend_items = build_rank_figure(
            year=int(year), level=level, rank=int(rank or 1), geography=geography,
            show_divisions=show_divisions, show_provinces=show_provinces,
            graph_width=graph_width, map_height=map_height,
        )
    except Exception as exc:
        return empty_figure(str(exc)), {"height": "620px"}, [], "floating-legend hidden"

    show_legend = "legend" in (legend_values or [])
    legend_children = [
        html.Div([
            html.Span(style={"backgroundColor": color}, className="legend-chip"),
            html.Span(label),
        ], className="legend-row")
        for label, color in legend_items
    ]
    return (
        fig,
        {"height": f"{int(fig.layout.height)}px"},
        legend_children,
        "floating-legend" if show_legend else "floating-legend hidden",
    )


if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=8050)

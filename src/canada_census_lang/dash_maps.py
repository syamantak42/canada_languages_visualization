from __future__ import annotations

import math
from functools import lru_cache

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.colors import sample_colorscale

from .config import (
    ASSET_DIR,
    CHANGE_GROUP,
    CHANGE_LANGUAGE,
    GROUP_DATA_2016,
    GROUP_DATA_2021,
    LANGUAGE_DATA_2016,
    LANGUAGE_DATA_2021,
    MAP_INDEX_2016,
    MAP_INDEX_2021,
    RANK_GROUP_2016,
    RANK_GROUP_2021,
    RANK_LANGUAGE_2016,
    RANK_LANGUAGE_2021,
)
from .runtime_assets import division_asset_name, outer_asset_name, province_boundaries_asset_name

LINE_COLOR = "rgba(55,65,81,0.60)"
LINE_WIDTH = 0.65
INSET_FRAME_COLOR = "rgba(55,65,81,0.78)"
MAX_MERCATOR_LAT = 85.05112878
TILE_SIZE = 512.0
MAP_STYLE = "carto-positron"
COLORBAR_BAND_PX = 74

# Fixed viewports for the three dense urban regions requested for magnification.
# These are display extents only: the underlying values and Census Division
# geometries are exactly the same as on the parent map.
URBAN_INSETS = {
    "British Columbia": {
        "key": "vancouver",
        "label": "Vancouver region",
        "province": "British Columbia",
        "bounds": (-123.65, 48.85, -121.75, 49.85),
    },
    "Ontario": {
        "key": "toronto",
        "label": "Toronto / GTA",
        "province": "Ontario",
        "bounds": (-80.25, 43.25, -78.15, 44.60),
    },
    "Quebec": {
        "key": "montreal",
        "label": "Montréal region",
        "province": "Quebec",
        "bounds": (-74.45, 45.10, -72.75, 46.15),
    },
}
CANADA_INSET_ORDER = ("British Columbia", "Ontario", "Quebec")


def _required(path, instruction: str):
    if not path.exists():
        raise FileNotFoundError(f"Required runtime file not found: {path}. {instruction}")
    return path


def _asset_url(filename: str) -> str:
    return f"/assets/generated/{filename}"


@lru_cache(maxsize=4)
def load_data(year: int, level: str) -> pd.DataFrame:
    if level == "LanguageName":
        path = LANGUAGE_DATA_2016 if year == 2016 else LANGUAGE_DATA_2021
    elif level == "LanguageGroup":
        path = GROUP_DATA_2016 if year == 2016 else GROUP_DATA_2021
    else:
        raise ValueError("level must be LanguageName or LanguageGroup")
    return pd.read_pickle(_required(path, "Run scripts/prepare_data.py first."))


@lru_cache(maxsize=2)
def load_map_index(year: int) -> pd.DataFrame:
    path = MAP_INDEX_2016 if year == 2016 else MAP_INDEX_2021
    return pd.read_pickle(_required(path, "Run scripts/prepare_app_assets.py first."))


@lru_cache(maxsize=4)
def load_rank_table(year: int, level: str) -> pd.DataFrame:
    if year == 2016 and level == "LanguageName":
        path = RANK_LANGUAGE_2016
    elif year == 2016:
        path = RANK_GROUP_2016
    elif level == "LanguageName":
        path = RANK_LANGUAGE_2021
    else:
        path = RANK_GROUP_2021
    return pd.read_pickle(_required(path, "Run scripts/prepare_app_assets.py first."))


@lru_cache(maxsize=2)
def load_change_table(level: str) -> pd.DataFrame:
    path = CHANGE_LANGUAGE if level == "LanguageName" else CHANGE_GROUP
    return pd.read_pickle(_required(path, "Run scripts/prepare_app_assets.py first."))


@lru_cache(maxsize=128)
def map_assets(year: int, geography: str) -> dict:
    index = load_map_index(year)
    subset = index if geography == "Canada" else index[index["ProvinceName"].eq(geography)]
    if subset.empty:
        raise ValueError(f"No Census Division geometry found for {geography!r} in {year}.")
    division_name = division_asset_name(year, geography)
    outer_name = outer_asset_name(year, geography)
    _required(ASSET_DIR / division_name, "Run scripts/prepare_app_assets.py first.")
    _required(ASSET_DIR / outer_name, "Run scripts/prepare_app_assets.py first.")
    province_name = province_boundaries_asset_name(year) if geography == "Canada" else None
    if province_name:
        _required(ASSET_DIR / province_name, "Run scripts/prepare_app_assets.py first.")
    return {
        "metadata": subset[["RegionID", "RegionName", "ProvinceCode", "ProvinceName"]].copy(),
        "bounds": (
            float(subset["minx"].min()), float(subset["miny"].min()),
            float(subset["maxx"].max()), float(subset["maxy"].max()),
        ),
        "division_url": _asset_url(division_name),
        "outer_url": _asset_url(outer_name),
        "province_boundaries_url": _asset_url(province_name) if province_name else None,
    }


@lru_cache(maxsize=1024)
def prevalence_values(year: int, level: str, language: str) -> pd.DataFrame:
    df = load_data(year, level)
    label_col = level
    return df.loc[df[label_col].eq(language), ["RegionID", "Count", "Percent"]].copy()


@lru_cache(maxsize=512)
def ranked_values(year: int, level: str, rank: int) -> pd.DataFrame:
    df = load_rank_table(year, level)
    return df.loc[df["Rank"].eq(int(rank)), ["RegionID", "RankLabel"]].copy()


@lru_cache(maxsize=2)
def common_change_languages(level: str) -> tuple[str, ...]:
    df = load_change_table(level)
    return tuple(sorted(df["DisplayName"].dropna().astype(str).unique()))


@lru_cache(maxsize=1024)
def change_values(level: str, language: str) -> pd.DataFrame:
    df = load_change_table(level)
    return df.loc[
        df["DisplayName"].eq(language),
        ["RegionID2021", "Count2016", "Count2021", "Share2016", "Share2021", "SpeakerChangePct", "ShareChangePP"],
    ].rename(columns={"RegionID2021": "RegionID"}).copy()


def _mercator_x(lon: float) -> float:
    return (lon + 180.0) / 360.0


def _mercator_y(lat: float) -> float:
    lat = max(-MAX_MERCATOR_LAT, min(MAX_MERCATOR_LAT, lat))
    lat_r = math.radians(lat)
    return (1.0 - math.asinh(math.tan(lat_r)) / math.pi) / 2.0


def _inverse_mercator_y(y: float) -> float:
    return math.degrees(math.atan(math.sinh(math.pi * (1.0 - 2.0 * y))))


def fit_map_view(bounds, pixel_width: float, pixel_height: float, padding_px: float = 14.0):
    minx, miny, maxx, maxy = bounds
    x0, x1 = _mercator_x(minx), _mercator_x(maxx)
    y0, y1 = _mercator_y(maxy), _mercator_y(miny)
    dx, dy = max(abs(x1 - x0), 1e-9), max(abs(y1 - y0), 1e-9)
    usable_w = max(float(pixel_width) - 2 * padding_px, 64)
    usable_h = max(float(pixel_height) - 2 * padding_px, 64)
    zoom = max(0.0, min(18.0, min(
        math.log2(usable_w / (TILE_SIZE * dx)),
        math.log2(usable_h / (TILE_SIZE * dy)),
    )))
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    return {"lon": cx * 360 - 180, "lat": _inverse_mercator_y(cy)}, zoom


def projected_aspect(bounds) -> float:
    minx, miny, maxx, maxy = bounds
    dx = max(abs(_mercator_x(maxx) - _mercator_x(minx)), 1e-9)
    dy = max(abs(_mercator_y(miny) - _mercator_y(maxy)), 1e-9)
    return dx / dy


def comparison_dimensions(n_maps: int, viewport_width: int, viewport_height: int, bounds) -> tuple[int, int, int]:
    vw = max(int(viewport_width or 1440), 720)
    columns = 1 if n_maps == 1 or vw < 980 else 2
    gap = 12
    page_padding = 24
    card_width = int((vw - page_padding - (columns - 1) * gap) / columns)
    aspect = projected_aspect(bounds)
    ideal_map_height = int(card_width / max(aspect, 0.25))
    min_height = 500 if columns == 1 else 420
    max_height = 1250 if columns == 1 else 850
    map_height = int(np.clip(ideal_map_height, min_height, max_height))
    return columns, card_width, map_height


def _boundary_layers(assets: dict, *, show_divisions: bool, show_provinces: bool) -> list[dict]:
    layers = []
    if not show_divisions:
        layers.append({
            "sourcetype": "geojson", "source": assets["outer_url"], "type": "line",
            "color": LINE_COLOR, "line": {"width": LINE_WIDTH},
        })
    elif show_provinces and assets["province_boundaries_url"]:
        layers.append({
            "sourcetype": "geojson", "source": assets["province_boundaries_url"], "type": "line",
            "color": LINE_COLOR, "line": {"width": LINE_WIDTH},
        })
    return layers


def urban_insets_for_geography(geography: str) -> tuple[dict, ...]:
    if geography == "Canada":
        return tuple(URBAN_INSETS[name] for name in CANADA_INSET_ORDER)
    spec = URBAN_INSETS.get(geography)
    return (spec,) if spec else ()


def _map_plan(geography: str, *, figure_height: int, map_height: int) -> dict:
    """Return non-overlapping paper domains for the main map and any insets."""
    map_bottom = max(0.0, min(0.35, (figure_height - map_height) / figure_height))
    inset_specs = urban_insets_for_geography(geography)

    if not inset_specs:
        return {
            "main_domain": {"x": [0.0, 1.0], "y": [map_bottom, 1.0]},
            "insets": [],
            "colorbar_x": 0.5,
        }

    if geography == "Canada":
        # Canada is very wide, so preserve its full horizontal extent and reserve
        # a shallow strip below the main map for the three urban magnifications.
        available_h = 1.0 - map_bottom
        inset_y0 = map_bottom + 0.015 * available_h
        inset_y1 = map_bottom + 0.265 * available_h
        main_y0 = map_bottom + 0.305 * available_h
        x_domains = ((0.010, 0.325), (0.3425, 0.6575), (0.675, 0.990))
        inset_plans = [
            {"spec": spec, "domain": {"x": list(x_domain), "y": [inset_y0, inset_y1]}}
            for spec, x_domain in zip(inset_specs, x_domains)
        ]
        return {
            "main_domain": {"x": [0.0, 1.0], "y": [main_y0, 1.0]},
            "insets": inset_plans,
            "colorbar_x": 0.5,
        }

    # Provincial maps are generally taller. Reserve an upper-right column so
    # the urban inset stays in the same figure without covering any province data.
    available_h = 1.0 - map_bottom
    inset_domain = {
        "x": [0.785, 0.995],
        "y": [map_bottom + 0.56 * available_h, map_bottom + 0.985 * available_h],
    }
    return {
        "main_domain": {"x": [0.0, 0.765], "y": [map_bottom, 1.0]},
        "insets": [{"spec": inset_specs[0], "domain": inset_domain}],
        "colorbar_x": 0.3825,
    }


def _map_layout_for_domain(*, assets, bounds, domain, graph_width, figure_height, show_divisions, show_provinces, uirevision):
    pixel_width = max(96.0, float(graph_width) * (domain["x"][1] - domain["x"][0]))
    pixel_height = max(96.0, float(figure_height) * (domain["y"][1] - domain["y"][0]))
    center, zoom = fit_map_view(bounds, pixel_width, pixel_height, padding_px=8.0)
    return {
        "style": MAP_STYLE,
        "center": center,
        "zoom": zoom,
        "bearing": 0,
        "pitch": 0,
        "layers": _boundary_layers(assets, show_divisions=show_divisions, show_provinces=show_provinces),
        "uirevision": uirevision,
        "domain": domain,
    }


def _configure_map_layout(
    fig: go.Figure,
    *,
    year: int,
    geography: str,
    assets: dict,
    graph_width: int,
    figure_height: int,
    map_height: int,
    show_divisions: bool,
    show_provinces: bool,
    uirevision: str,
) -> dict:
    plan = _map_plan(geography, figure_height=figure_height, map_height=map_height)
    layout_updates = {
        "map": _map_layout_for_domain(
            assets=assets,
            bounds=assets["bounds"],
            domain=plan["main_domain"],
            graph_width=graph_width,
            figure_height=figure_height,
            show_divisions=show_divisions,
            show_provinces=show_provinces,
            uirevision=uirevision,
        )
    }

    for i, inset in enumerate(plan["insets"], start=2):
        spec = inset["spec"]
        inset_assets = map_assets(year, spec["province"])
        layout_updates[f"map{i}"] = _map_layout_for_domain(
            assets=inset_assets,
            bounds=spec["bounds"],
            domain=inset["domain"],
            graph_width=graph_width,
            figure_height=figure_height,
            show_divisions=show_divisions,
            show_provinces=False,
            uirevision=f"{uirevision}-{spec['key']}",
        )

        domain = inset["domain"]
        fig.add_shape(
            type="rect", xref="paper", yref="paper",
            x0=domain["x"][0], x1=domain["x"][1],
            y0=domain["y"][0], y1=domain["y"][1],
            line={"color": INSET_FRAME_COLOR, "width": 1.0},
            fillcolor="rgba(255,255,255,0)", layer="above",
        )
        fig.add_annotation(
            xref="paper", yref="paper",
            x=domain["x"][0] + 0.006, y=domain["y"][1] - 0.008,
            text=f"<b>{spec['label']}</b>", showarrow=False,
            xanchor="left", yanchor="top",
            bgcolor="rgba(255,255,255,0.88)", borderpad=2,
            font={"size": 10, "color": "#374151"},
        )

    fig.update_layout(**layout_updates)
    return plan


def _prevalence_plot_df(assets: dict, values: pd.DataFrame) -> pd.DataFrame:
    return assets["metadata"].merge(values, on="RegionID", how="left")


def _prevalence_trace(*, assets, plot_df, level, language, color_scale, max_share, show_divisions, subplot, showscale, colorbar):
    label = "Language group" if level == "LanguageGroup" else "Language"
    return go.Choroplethmap(
        geojson=assets["division_url"], locations=plot_df["RegionID"], featureidkey="id",
        z=plot_df["Percent"], zmin=0, zmax=max_share, colorscale=color_scale,
        marker={"line": {"width": LINE_WIDTH if show_divisions else 0, "color": LINE_COLOR}, "opacity": 0.93},
        showscale=showscale, colorbar=colorbar,
        customdata=plot_df[["RegionName", "ProvinceName", "Count", "Percent"]],
        hovertemplate=(
            "<b>%{customdata[0]}</b><br>Province/territory: %{customdata[1]}<br>"
            f"{label}: {language}<br>Single-response mother tongue: %{{customdata[2]:,.0f}}<br>"
            "Share of mother-tongue population: %{customdata[3]:.2f}%<extra></extra>"
        ),
        subplot=subplot,
    )


def build_prevalence_figure(*, year, level, language, geography, color_scale, show_divisions, show_provinces, graph_width, map_height, slot, comparison_count):
    assets = map_assets(year, geography)
    values = prevalence_values(year, level, language)
    plot_df = _prevalence_plot_df(assets, values)
    max_share = max(float(plot_df["Percent"].max(skipna=True)) if plot_df["Percent"].notna().any() else 0.0, 1.0)
    figure_height = int(map_height) + COLORBAR_BAND_PX
    plan = _map_plan(geography, figure_height=figure_height, map_height=map_height)
    colorbar = {
        "orientation": "h", "x": plan["colorbar_x"], "xanchor": "center", "y": 0.012, "yanchor": "bottom",
        "len": 0.52, "thickness": 12, "outlinewidth": 0,
        "title": {"text": "% of population", "side": "top"}, "tickfont": {"size": 10},
    }
    fig = go.Figure(_prevalence_trace(
        assets=assets, plot_df=plot_df, level=level, language=language, color_scale=color_scale,
        max_share=max_share, show_divisions=show_divisions, subplot="map", showscale=True, colorbar=colorbar,
    ))

    for i, inset in enumerate(plan["insets"], start=2):
        spec = inset["spec"]
        inset_assets = map_assets(year, spec["province"])
        inset_df = _prevalence_plot_df(inset_assets, values)
        fig.add_trace(_prevalence_trace(
            assets=inset_assets, plot_df=inset_df, level=level, language=language, color_scale=color_scale,
            max_share=max_share, show_divisions=show_divisions, subplot=f"map{i}", showscale=False, colorbar=None,
        ))

    _configure_map_layout(
        fig,
        year=year, geography=geography, assets=assets, graph_width=graph_width,
        figure_height=figure_height, map_height=map_height,
        show_divisions=show_divisions, show_provinces=show_provinces,
        uirevision=f"prev-{year}-{geography}-{comparison_count}",
    )
    fig.update_layout(
        height=figure_height, autosize=True, margin={"l": 0, "r": 0, "t": 0, "b": 0},
        paper_bgcolor="#f5f7fa", font={"family": "Arial, sans-serif", "size": 13},
    )
    return fig


def _discrete_colorscale(colors: list[str]) -> list[list[float | str]]:
    if len(colors) == 1:
        return [[0.0, colors[0]], [1.0, colors[0]]]
    out = []
    n = len(colors)
    for i, color in enumerate(colors):
        out.extend([[i / n, color], [(i + 1) / n, color]])
    return out


def _rank_plot_df(assets: dict, ranked: pd.DataFrame, codes: dict[str, int]) -> pd.DataFrame:
    plot_df = assets["metadata"].merge(ranked, on="RegionID", how="left")
    plot_df["RankLabel"] = plot_df["RankLabel"].fillna("No data")
    plot_df["RankCode"] = plot_df["RankLabel"].map(codes).fillna(codes["No data"]).astype(int)
    return plot_df


def _rank_trace(*, assets, plot_df, rank, colorscale, n_categories, show_divisions, subplot):
    return go.Choroplethmap(
        geojson=assets["division_url"], locations=plot_df["RegionID"], featureidkey="id",
        z=plot_df["RankCode"], zmin=-0.5, zmax=n_categories - 0.5,
        colorscale=colorscale, showscale=False,
        marker={"line": {"width": LINE_WIDTH if show_divisions else 0, "color": LINE_COLOR}, "opacity": 0.93},
        customdata=plot_df[["RegionName", "ProvinceName", "RankLabel"]],
        hovertemplate=(
            "<b>%{customdata[0]}</b><br>Province/territory: %{customdata[1]}<br>"
            f"Rank {rank}: %{{customdata[2]}}<extra></extra>"
        ),
        subplot=subplot,
    )


def build_rank_figure(*, year, level, rank, geography, show_divisions, show_provinces, graph_width, map_height):
    assets = map_assets(year, geography)
    ranked = ranked_values(year, level, rank)
    main_for_categories = assets["metadata"].merge(ranked, on="RegionID", how="left")
    main_for_categories["RankLabel"] = main_for_categories["RankLabel"].fillna("No data")
    categories = sorted(x for x in main_for_categories["RankLabel"].unique() if x != "No data")
    all_categories = categories + ["No data"]
    if len(categories) <= 1:
        category_colors = ["rgb(33,113,181)"] * len(categories)
    else:
        category_colors = sample_colorscale("Turbo", [i / (len(categories) - 1) for i in range(len(categories))])
    colors = category_colors + ["rgb(217,217,217)"]
    codes = {name: i for i, name in enumerate(all_categories)}
    colorscale = _discrete_colorscale(colors)
    plot_df = _rank_plot_df(assets, ranked, codes)

    fig = go.Figure(_rank_trace(
        assets=assets, plot_df=plot_df, rank=rank, colorscale=colorscale,
        n_categories=len(all_categories), show_divisions=show_divisions, subplot="map",
    ))
    plan = _map_plan(geography, figure_height=map_height, map_height=map_height)
    for i, inset in enumerate(plan["insets"], start=2):
        spec = inset["spec"]
        inset_assets = map_assets(year, spec["province"])
        inset_df = _rank_plot_df(inset_assets, ranked, codes)
        fig.add_trace(_rank_trace(
            assets=inset_assets, plot_df=inset_df, rank=rank, colorscale=colorscale,
            n_categories=len(all_categories), show_divisions=show_divisions, subplot=f"map{i}",
        ))

    _configure_map_layout(
        fig,
        year=year, geography=geography, assets=assets, graph_width=graph_width,
        figure_height=map_height, map_height=map_height,
        show_divisions=show_divisions, show_provinces=show_provinces,
        uirevision=f"rank-{year}-{geography}",
    )
    fig.update_layout(
        height=map_height, autosize=True, margin={"l": 0, "r": 0, "t": 0, "b": 0}, paper_bgcolor="#f5f7fa",
    )
    return fig, list(zip(all_categories, colors))


def _fmt_number(v):
    return "n/a" if pd.isna(v) else f"{v:,.0f}"


def _fmt_signed(v, suffix):
    return "n/a" if pd.isna(v) else f"{v:+.2f}{suffix}"


def _change_plot_df(assets: dict, values: pd.DataFrame) -> pd.DataFrame:
    return assets["metadata"].merge(values, on="RegionID", how="left")


def _change_custom(plot_df: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame({
        "region": plot_df["RegionName"], "province": plot_df["ProvinceName"],
        "c16": plot_df["Count2016"].map(_fmt_number), "c21": plot_df["Count2021"].map(_fmt_number),
        "chg": plot_df["SpeakerChangePct"].map(lambda x: _fmt_signed(x, "%")),
        "s16": plot_df["Share2016"].map(lambda x: "n/a" if pd.isna(x) else f"{x:.2f}%"),
        "s21": plot_df["Share2021"].map(lambda x: "n/a" if pd.isna(x) else f"{x:.2f}%"),
        "pp": plot_df["ShareChangePP"].map(lambda x: _fmt_signed(x, " pp")),
    })


def _change_trace(*, assets, plot_df, language, z_col, color_scale, max_abs, show_divisions, subplot, showscale, colorbar):
    return go.Choroplethmap(
        geojson=assets["division_url"], locations=plot_df["RegionID"], featureidkey="id",
        z=plot_df[z_col], zmin=-max_abs, zmax=max_abs, zmid=0, colorscale=color_scale,
        marker={"line": {"width": LINE_WIDTH if show_divisions else 0, "color": LINE_COLOR}, "opacity": 0.93},
        showscale=showscale, colorbar=colorbar,
        customdata=_change_custom(plot_df),
        hovertemplate=(
            "<b>%{customdata[0]}</b><br>Province/territory: %{customdata[1]}<br>"
            f"{language}<br>Approx. 2016 count: %{{customdata[2]}}<br>2021 count: %{{customdata[3]}}<br>"
            "Count change: %{customdata[4]}<br>Approx. 2016 share: %{customdata[5]}<br>"
            "2021 share: %{customdata[6]}<br>Share change: %{customdata[7]}<extra></extra>"
        ),
        subplot=subplot,
    )


def build_change_figure(*, level, language, metric, geography, color_scale, show_divisions, show_provinces, graph_width, map_height, slot, comparison_count):
    assets = map_assets(2021, geography)
    values = change_values(level, language)
    plot_df = _change_plot_df(assets, values)
    if metric == "speaker_change_pct":
        z_col, title = "SpeakerChangePct", "Mother-tongue count change (%)"
    elif metric == "share_change_pp":
        z_col, title = "ShareChangePP", "Population-share change (pp)"
    else:
        raise ValueError("Unknown change metric")
    finite = plot_df[z_col].replace([np.inf, -np.inf], np.nan).dropna()
    max_abs = max(float(finite.abs().max()) if not finite.empty else 0.0, 0.01)
    figure_height = int(map_height) + COLORBAR_BAND_PX
    plan = _map_plan(geography, figure_height=figure_height, map_height=map_height)
    colorbar = {
        "orientation": "h", "x": plan["colorbar_x"], "xanchor": "center", "y": 0.012, "yanchor": "bottom",
        "len": 0.56, "thickness": 12, "outlinewidth": 0,
        "title": {"text": title, "side": "top"}, "tickfont": {"size": 10},
    }
    fig = go.Figure(_change_trace(
        assets=assets, plot_df=plot_df, language=language, z_col=z_col, color_scale=color_scale,
        max_abs=max_abs, show_divisions=show_divisions, subplot="map", showscale=True, colorbar=colorbar,
    ))

    for i, inset in enumerate(plan["insets"], start=2):
        spec = inset["spec"]
        inset_assets = map_assets(2021, spec["province"])
        inset_df = _change_plot_df(inset_assets, values)
        fig.add_trace(_change_trace(
            assets=inset_assets, plot_df=inset_df, language=language, z_col=z_col, color_scale=color_scale,
            max_abs=max_abs, show_divisions=show_divisions, subplot=f"map{i}", showscale=False, colorbar=None,
        ))

    _configure_map_layout(
        fig,
        year=2021, geography=geography, assets=assets, graph_width=graph_width,
        figure_height=figure_height, map_height=map_height,
        show_divisions=show_divisions, show_provinces=show_provinces,
        uirevision=f"change-{geography}-{metric}-{comparison_count}",
    )
    fig.update_layout(
        height=figure_height, autosize=True, margin={"l": 0, "r": 0, "t": 0, "b": 0}, paper_bgcolor="#f5f7fa",
    )
    return fig

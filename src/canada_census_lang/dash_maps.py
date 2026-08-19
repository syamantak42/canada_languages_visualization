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
MAX_MERCATOR_LAT = 85.05112878
TILE_SIZE = 512.0
MAP_STYLE = "carto-positron"
COLORBAR_BAND_PX = 74


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


def _base_map_layout(*, assets, graph_width, figure_height, map_height, show_divisions, show_provinces, uirevision):
    center, zoom = fit_map_view(assets["bounds"], graph_width, map_height)
    domain_bottom = max(0.0, min(0.35, (figure_height - map_height) / figure_height))
    return {
        "style": MAP_STYLE,
        "center": center,
        "zoom": zoom,
        "bearing": 0,
        "pitch": 0,
        "layers": _boundary_layers(assets, show_divisions=show_divisions, show_provinces=show_provinces),
        "uirevision": uirevision,
        "domain": {"x": [0, 1], "y": [domain_bottom, 1]},
    }


def build_prevalence_figure(*, year, level, language, geography, color_scale, show_divisions, show_provinces, graph_width, map_height, slot, comparison_count):
    assets = map_assets(year, geography)
    values = prevalence_values(year, level, language)
    plot_df = assets["metadata"].merge(values, on="RegionID", how="left")
    max_share = max(float(plot_df["Percent"].max(skipna=True)) if plot_df["Percent"].notna().any() else 0.0, 1.0)
    figure_height = int(map_height) + COLORBAR_BAND_PX
    label = "Language group" if level == "LanguageGroup" else "Language"
    fig = go.Figure(go.Choroplethmap(
        geojson=assets["division_url"], locations=plot_df["RegionID"], featureidkey="id",
        z=plot_df["Percent"], zmin=0, zmax=max_share, colorscale=color_scale,
        marker={"line": {"width": LINE_WIDTH if show_divisions else 0, "color": LINE_COLOR}, "opacity": 0.93},
        colorbar={
            "orientation": "h", "x": 0.5, "xanchor": "center", "y": 0.012, "yanchor": "bottom",
            "len": 0.52, "thickness": 12, "outlinewidth": 0,
            "title": {"text": "% of population", "side": "top"}, "tickfont": {"size": 10},
        },
        customdata=plot_df[["RegionName", "ProvinceName", "Count", "Percent"]],
        hovertemplate=(
            "<b>%{customdata[0]}</b><br>Province/territory: %{customdata[1]}<br>"
            f"{label}: {language}<br>Single-response mother tongue: %{{customdata[2]:,.0f}}<br>"
            "Share of mother-tongue population: %{customdata[3]:.2f}%<extra></extra>"
        ),
    ))
    fig.update_layout(
        map=_base_map_layout(
            assets=assets, graph_width=graph_width, figure_height=figure_height, map_height=map_height,
            show_divisions=show_divisions, show_provinces=show_provinces,
            uirevision=f"prev-{year}-{geography}-{comparison_count}",
        ),
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


def build_rank_figure(*, year, level, rank, geography, show_divisions, show_provinces, graph_width, map_height):
    assets = map_assets(year, geography)
    ranked = ranked_values(year, level, rank)
    plot_df = assets["metadata"].merge(ranked, on="RegionID", how="left")
    plot_df["RankLabel"] = plot_df["RankLabel"].fillna("No data")
    categories = sorted(x for x in plot_df["RankLabel"].unique() if x != "No data")
    all_categories = categories + ["No data"]
    if len(categories) <= 1:
        category_colors = ["rgb(33,113,181)"] * len(categories)
    else:
        category_colors = sample_colorscale("Turbo", [i / (len(categories) - 1) for i in range(len(categories))])
    colors = category_colors + ["rgb(217,217,217)"]
    codes = {name: i for i, name in enumerate(all_categories)}
    plot_df["RankCode"] = plot_df["RankLabel"].map(codes).astype(int)
    fig = go.Figure(go.Choroplethmap(
        geojson=assets["division_url"], locations=plot_df["RegionID"], featureidkey="id",
        z=plot_df["RankCode"], zmin=-0.5, zmax=len(all_categories)-0.5,
        colorscale=_discrete_colorscale(colors), showscale=False,
        marker={"line": {"width": LINE_WIDTH if show_divisions else 0, "color": LINE_COLOR}, "opacity": 0.93},
        customdata=plot_df[["RegionName", "ProvinceName", "RankLabel"]],
        hovertemplate=(
            "<b>%{customdata[0]}</b><br>Province/territory: %{customdata[1]}<br>"
            f"Rank {rank}: %{{customdata[2]}}<extra></extra>"
        ),
    ))
    fig.update_layout(
        map=_base_map_layout(
            assets=assets, graph_width=graph_width, figure_height=map_height, map_height=map_height,
            show_divisions=show_divisions, show_provinces=show_provinces,
            uirevision=f"rank-{year}-{geography}",
        ),
        height=map_height, autosize=True, margin={"l": 0, "r": 0, "t": 0, "b": 0}, paper_bgcolor="#f5f7fa",
    )
    return fig, list(zip(all_categories, colors))


def _fmt_number(v):
    return "n/a" if pd.isna(v) else f"{v:,.0f}"


def _fmt_signed(v, suffix):
    return "n/a" if pd.isna(v) else f"{v:+.2f}{suffix}"


def build_change_figure(*, level, language, metric, geography, color_scale, show_divisions, show_provinces, graph_width, map_height, slot, comparison_count):
    assets = map_assets(2021, geography)
    values = change_values(level, language)
    plot_df = assets["metadata"].merge(values, on="RegionID", how="left")
    if metric == "speaker_change_pct":
        z_col, title = "SpeakerChangePct", "Mother-tongue count change (%)"
    elif metric == "share_change_pp":
        z_col, title = "ShareChangePP", "Population-share change (pp)"
    else:
        raise ValueError("Unknown change metric")
    finite = plot_df[z_col].replace([np.inf, -np.inf], np.nan).dropna()
    max_abs = max(float(finite.abs().max()) if not finite.empty else 0.0, 0.01)
    figure_height = int(map_height) + COLORBAR_BAND_PX
    custom = pd.DataFrame({
        "region": plot_df["RegionName"], "province": plot_df["ProvinceName"],
        "c16": plot_df["Count2016"].map(_fmt_number), "c21": plot_df["Count2021"].map(_fmt_number),
        "chg": plot_df["SpeakerChangePct"].map(lambda x: _fmt_signed(x, "%")),
        "s16": plot_df["Share2016"].map(lambda x: "n/a" if pd.isna(x) else f"{x:.2f}%"),
        "s21": plot_df["Share2021"].map(lambda x: "n/a" if pd.isna(x) else f"{x:.2f}%"),
        "pp": plot_df["ShareChangePP"].map(lambda x: _fmt_signed(x, " pp")),
    })
    fig = go.Figure(go.Choroplethmap(
        geojson=assets["division_url"], locations=plot_df["RegionID"], featureidkey="id",
        z=plot_df[z_col], zmin=-max_abs, zmax=max_abs, zmid=0, colorscale=color_scale,
        marker={"line": {"width": LINE_WIDTH if show_divisions else 0, "color": LINE_COLOR}, "opacity": 0.93},
        colorbar={
            "orientation": "h", "x": 0.5, "xanchor": "center", "y": 0.012, "yanchor": "bottom",
            "len": 0.56, "thickness": 12, "outlinewidth": 0,
            "title": {"text": title, "side": "top"}, "tickfont": {"size": 10},
        },
        customdata=custom,
        hovertemplate=(
            "<b>%{customdata[0]}</b><br>Province/territory: %{customdata[1]}<br>"
            f"{language}<br>Approx. 2016 count: %{{customdata[2]}}<br>2021 count: %{{customdata[3]}}<br>"
            "Count change: %{customdata[4]}<br>Approx. 2016 share: %{customdata[5]}<br>"
            "2021 share: %{customdata[6]}<br>Share change: %{customdata[7]}<extra></extra>"
        ),
    ))
    fig.update_layout(
        map=_base_map_layout(
            assets=assets, graph_width=graph_width, figure_height=figure_height, map_height=map_height,
            show_divisions=show_divisions, show_provinces=show_provinces,
            uirevision=f"change-{geography}-{metric}-{comparison_count}",
        ),
        height=figure_height, autosize=True, margin={"l": 0, "r": 0, "t": 0, "b": 0}, paper_bgcolor="#f5f7fa",
    )
    return fig

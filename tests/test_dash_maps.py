import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import canada_census_lang.dash_maps as dm


def fake_assets():
    return {
        "metadata": pd.DataFrame({
            "RegionID": ["1001", "1002"],
            "RegionName": ["A", "B"],
            "ProvinceCode": ["10", "10"],
            "ProvinceName": ["P", "P"],
        }),
        "bounds": (-64.0, 44.0, -52.0, 52.0),
        "division_url": "/assets/generated/test.geojson",
        "outer_url": "/assets/generated/outer.geojson",
        "province_boundaries_url": "/assets/generated/provinces.geojson",
    }


def test_prevalence_canada_has_three_non_overlapping_urban_insets(monkeypatch):
    monkeypatch.setattr(dm, "map_assets", lambda year, geography: fake_assets())
    monkeypatch.setattr(dm, "prevalence_values", lambda year, level, language: pd.DataFrame({
        "RegionID": ["1001", "1002"], "Count": [100.0, 50.0], "Percent": [10.0, 5.0]
    }))
    fig = dm.build_prevalence_figure(
        year=2021, level="LanguageName", language="English", geography="Canada",
        color_scale="Blues", show_divisions=True, show_provinces=True,
        graph_width=1200, map_height=700, slot=1, comparison_count=1,
    )
    assert len(fig.data) == 4
    assert [trace.subplot for trace in fig.data] == ["map", "map2", "map3", "map4"]
    assert all(trace.type == "choroplethmap" for trace in fig.data)
    assert fig.data[0].geojson == "/assets/generated/test.geojson"
    assert fig.data[0].colorbar.orientation == "h"
    assert fig.data[0].showscale is True
    assert all(trace.showscale is False for trace in fig.data[1:])
    assert fig.layout.map.domain.y[0] > fig.layout.map2.domain.y[1]
    assert fig.layout.map.domain.y[0] > fig.layout.map3.domain.y[1]
    assert fig.layout.map.domain.y[0] > fig.layout.map4.domain.y[1]
    labels = [annotation.text for annotation in fig.layout.annotations]
    assert labels == ["<b>Vancouver region</b>", "<b>Toronto / GTA</b>", "<b>Montréal region</b>"]


def test_ontario_inset_uses_reserved_right_corner(monkeypatch):
    monkeypatch.setattr(dm, "map_assets", lambda year, geography: fake_assets())
    monkeypatch.setattr(dm, "prevalence_values", lambda year, level, language: pd.DataFrame({
        "RegionID": ["1001", "1002"], "Count": [100.0, 50.0], "Percent": [10.0, 5.0]
    }))
    fig = dm.build_prevalence_figure(
        year=2021, level="LanguageName", language="English", geography="Ontario",
        color_scale="Blues", show_divisions=True, show_provinces=False,
        graph_width=1200, map_height=700, slot=1, comparison_count=1,
    )
    assert len(fig.data) == 2
    assert [trace.subplot for trace in fig.data] == ["map", "map2"]
    assert fig.layout.map.domain.x[1] < fig.layout.map2.domain.x[0]
    assert fig.layout.annotations[0].text == "<b>Toronto / GTA</b>"
    assert fig.data[0].colorbar.x < 0.5


def test_province_without_configured_inset_stays_single_map(monkeypatch):
    monkeypatch.setattr(dm, "map_assets", lambda year, geography: fake_assets())
    monkeypatch.setattr(dm, "prevalence_values", lambda year, level, language: pd.DataFrame({
        "RegionID": ["1001", "1002"], "Count": [100.0, 50.0], "Percent": [10.0, 5.0]
    }))
    fig = dm.build_prevalence_figure(
        year=2021, level="LanguageName", language="English", geography="Alberta",
        color_scale="Blues", show_divisions=True, show_provinces=False,
        graph_width=1200, map_height=700, slot=1, comparison_count=1,
    )
    assert len(fig.data) == 1
    assert fig.data[0].subplot == "map"
    assert fig.layout.map.domain.x == (0.0, 1.0)


def test_rank_canada_repeats_same_categorical_scale_in_insets(monkeypatch):
    monkeypatch.setattr(dm, "map_assets", lambda year, geography: fake_assets())
    monkeypatch.setattr(dm, "ranked_values", lambda year, level, rank: pd.DataFrame({
        "RegionID": ["1001", "1002"], "RankLabel": ["English", "French"]
    }))
    fig, legend = dm.build_rank_figure(
        year=2021, level="LanguageName", rank=1, geography="Canada",
        show_divisions=True, show_provinces=True, graph_width=1200, map_height=700,
    )
    assert len(fig.data) == 4
    assert [trace.subplot for trace in fig.data] == ["map", "map2", "map3", "map4"]
    assert all(trace.type == "choroplethmap" for trace in fig.data)
    assert all(trace.colorscale == fig.data[0].colorscale for trace in fig.data[1:])
    assert {x[0] for x in legend} >= {"English", "French"}


def test_change_canada_uses_horizontal_diverging_colorbar_and_insets(monkeypatch):
    monkeypatch.setattr(dm, "map_assets", lambda year, geography: fake_assets())
    monkeypatch.setattr(dm, "change_values", lambda level, language: pd.DataFrame({
        "RegionID": ["1001", "1002"],
        "Count2016": [100.0, 50.0], "Count2021": [120.0, 45.0],
        "Share2016": [10.0, 5.0], "Share2021": [11.0, 4.0],
        "SpeakerChangePct": [20.0, -10.0], "ShareChangePP": [1.0, -1.0],
    }))
    fig = dm.build_change_figure(
        level="LanguageName", language="English", metric="speaker_change_pct", geography="Canada",
        color_scale="RdBu", show_divisions=True, show_provinces=True,
        graph_width=1200, map_height=700, slot=1, comparison_count=1,
    )
    assert len(fig.data) == 4
    assert fig.data[0].type == "choroplethmap"
    assert fig.data[0].colorbar.orientation == "h"
    assert fig.layout.map.domain.y[0] > fig.layout.map2.domain.y[1]
    assert all(trace.zmin == fig.data[0].zmin and trace.zmax == fig.data[0].zmax for trace in fig.data[1:])


def test_generic_view_fit_and_dimensions():
    bounds = (-141.0, 41.0, -52.0, 83.0)
    center, zoom = dm.fit_map_view(bounds, 1600, 900)
    assert -141 <= center["lon"] <= -52
    assert 41 <= center["lat"] <= 83
    assert zoom >= 0
    cols, width, height = dm.comparison_dimensions(1, 1600, 900, bounds)
    assert cols == 1 and width > 1000 and height >= 500

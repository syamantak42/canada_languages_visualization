import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import box

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import canada_census_lang.runtime_assets as ra


def test_rank_table_ignores_zero_speaker_categories():
    df = pd.DataFrame({
        "RegionID": ["1001", "1001", "1001"],
        "LanguageName": ["A", "B", "C"],
        "Count": [100, 50, 0],
    })
    out = ra._rank_table(df, "LanguageName")
    got = dict(zip(out["Rank"], out["RankLabel"]))
    assert got == {1: "A", 2: "B"}


def test_crosswalk_splits_old_division_by_population_weight(tmp_path, monkeypatch):
    old = gpd.GeoDataFrame(
        {"RegionID": ["1001"], "ProvinceCode": ["10"], "ProvinceName": ["P"], "RegionName": ["Old"]},
        geometry=[box(0, 0, 2, 1)], crs="EPSG:4326",
    )
    new = gpd.GeoDataFrame(
        {"RegionID": ["1001", "1002"], "ProvinceCode": ["10", "10"], "ProvinceName": ["P", "P"], "RegionName": ["A", "B"]},
        geometry=[box(0, 0, 1, 1), box(1, 0, 2, 1)], crs="EPSG:4326",
    )
    monkeypatch.setattr(ra, "load_boundary", lambda year: old.copy() if year == 2016 else new.copy())
    lang21_path = tmp_path / "lang21.pkl"
    pd.DataFrame({
        "RegionID": ["1001", "1002"],
        "TotalPopulation": [100.0, 300.0],
    }).to_pickle(lang21_path)
    monkeypatch.setattr(ra, "LANGUAGE_DATA_2021", lang21_path)
    out_path = tmp_path / "cross.pkl"
    monkeypatch.setattr(ra, "CHANGE_CROSSWALK", out_path)
    cross = ra.prepare_crosswalk().sort_values("RegionID2021")
    assert np.allclose(cross["Weight"], [0.25, 0.75], atol=0.02)
    assert out_path.exists()


def test_precompute_change_formulas(tmp_path, monkeypatch):
    cross_path = tmp_path / "cross.pkl"
    pd.DataFrame({
        "RegionID2016": ["1001"],
        "RegionID2021": ["1001"],
        "Weight": [1.0],
    }).to_pickle(cross_path)
    monkeypatch.setattr(ra, "CHANGE_CROSSWALK", cross_path)
    old = pd.DataFrame({
        "RegionID": ["1001"], "LanguageName": ["English"], "CanonicalName": ["English"],
        "Count": [100.0], "TotalPopulation": [1000.0],
    })
    new = pd.DataFrame({
        "RegionID": ["1001"], "LanguageName": ["English"], "CanonicalName": ["English"],
        "Count": [150.0], "TotalPopulation": [1200.0],
    })
    out = ra._precompute_change(old, new, "LanguageName", tmp_path / "out.pkl")
    row = out.iloc[0]
    assert row["SpeakerChangePct"] == 50.0
    assert row["Share2016"] == 10.0
    assert row["Share2021"] == 12.5
    assert row["ShareChangePP"] == 2.5


def test_safe_union_boundary_repairs_invalid_polygon():
    from shapely.geometry import Polygon

    # Self-intersecting bow-tie polygon plus a valid neighbour.
    invalid = Polygon([(0, 0), (2, 2), (0, 2), (2, 0), (0, 0)])
    valid = box(2, 0, 3, 1)
    boundary = ra._safe_union_boundary([invalid, valid])
    assert not boundary.is_empty
    assert boundary.is_valid


def test_crosswalk_overlay_retry_handles_invalid_inputs():
    from shapely.geometry import Polygon

    a = gpd.GeoDataFrame(
        {"RegionID2016": ["1001"]},
        geometry=[Polygon([(0, 0), (2, 2), (0, 2), (2, 0), (0, 0)])],
        crs="EPSG:6933",
    )
    b = gpd.GeoDataFrame(
        {"RegionID2021": ["1001"]},
        geometry=[box(0, 0, 2, 2)],
        crs="EPSG:6933",
    )
    # The helper must either succeed directly or repair-and-retry; callers should
    # never receive the TopologyException that used to terminate preprocessing.
    out = ra._overlay_with_topology_retry(a, b, province_code="10")
    assert not out.empty

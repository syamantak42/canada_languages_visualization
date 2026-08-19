from __future__ import annotations

import json
import re
from pathlib import Path
from time import perf_counter

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely import make_valid, set_precision, union_all
from shapely.errors import GEOSException
from shapely.geometry import mapping

from .config import (
    ASSET_DIR,
    CHANGE_CROSSWALK,
    CHANGE_GROUP,
    CHANGE_LANGUAGE,
    GROUP_DATA_2016,
    GROUP_DATA_2021,
    LANGUAGE_DATA_2016,
    LANGUAGE_DATA_2021,
    MAP_INDEX_2016,
    MAP_INDEX_2021,
    NATIONAL_SIMPLIFY_METRES,
    PROVINCE_CODE_TO_NAME,
    PROVINCE_SIMPLIFY_METRES,
    RANK_GROUP_2016,
    RANK_GROUP_2021,
    RANK_LANGUAGE_2016,
    RANK_LANGUAGE_2021,
    RAW_BOUNDARY_2016_DIR,
    RAW_BOUNDARY_2021_DIR,
)

# The 2016→2021 district reconciliation is already approximate. Simplifying
# analytical boundaries before polygon overlay removes enormous coastal detail
# and makes this one-time preprocessing step much faster and more robust.
CROSSWALK_SIMPLIFY_METRES = 250.0
# Snap-to-grid fallback used only if GEOS reports a topology error. Coordinates
# are in metre-based projected CRSs when this is used.
TOPOLOGY_GRID_METRES = 1.0


def _progress(message: str) -> None:
    print(f"[assets] {message}", flush=True)


def slugify(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9]+", "_", value).strip("_")
    return value or "Canada"


def division_asset_name(year: int, geography: str) -> str:
    return f"cd_{year}_{slugify(geography)}.geojson"


def outer_asset_name(year: int, geography: str) -> str:
    return f"outer_{year}_{slugify(geography)}.geojson"


def province_boundaries_asset_name(year: int) -> str:
    return f"province_boundaries_{year}.geojson"


def _find_shapefile(year: int) -> Path:
    folder = RAW_BOUNDARY_2016_DIR if year == 2016 else RAW_BOUNDARY_2021_DIR
    candidates = sorted(folder.glob("**/*.shp"))
    if not candidates:
        raise FileNotFoundError(f"No Census Division shapefile found under {folder}; run scripts/download_data.py.")
    return candidates[0]


def load_boundary(year: int) -> gpd.GeoDataFrame:
    gdf = gpd.read_file(_find_shapefile(year))
    cols = {c.upper(): c for c in gdf.columns}
    required = ["CDUID", "CDNAME"]
    missing = [c for c in required if c not in cols]
    if missing:
        raise RuntimeError(f"Unexpected {year} Census Division shapefile schema; missing {missing}.")

    region = gdf[cols["CDUID"]].astype(str).str.replace(r"\.0$", "", regex=True).str.zfill(4)
    if "PRUID" in cols:
        province = gdf[cols["PRUID"]].astype(str).str.replace(r"\.0$", "", regex=True).str.zfill(2)
    else:
        province = region.str[:2]
    out = gpd.GeoDataFrame(
        {
            "RegionID": region,
            "RegionName": gdf[cols["CDNAME"]].astype(str).str.strip(),
            "ProvinceCode": province,
            "ProvinceName": province.map(PROVINCE_CODE_TO_NAME),
        },
        geometry=gdf.geometry,
        crs=gdf.crs,
    )
    if out.crs is None:
        raise RuntimeError(f"{year} Census Division shapefile has no CRS.")
    return out.to_crs("EPSG:4326")


def _feature(geometry, feature_id: str | None = None) -> dict:
    d = {"type": "Feature", "properties": {}, "geometry": mapping(geometry)}
    if feature_id is not None:
        d["id"] = str(feature_id)
    return d


def _write_geojson(path: Path, features: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"type": "FeatureCollection", "features": features}, separators=(",", ":")),
        encoding="utf-8",
    )


def _repair_invalid(gdf: gpd.GeoDataFrame, *, label: str | None = None) -> gpd.GeoDataFrame:
    """Repair only invalid geometries instead of make_valid() on every feature."""
    out = gdf.copy()
    valid_mask = out.geometry.notna() & ~out.geometry.is_empty
    invalid_mask = valid_mask & ~out.geometry.is_valid
    n_invalid = int(invalid_mask.sum())
    if n_invalid:
        prefix = f"{label}: " if label else ""
        _progress(f"{prefix}repairing {n_invalid} invalid geometries")
        out.loc[invalid_mask, "geometry"] = out.loc[invalid_mask, "geometry"].make_valid()

    # A repair can theoretically produce an empty object. Those cannot be used
    # for mapping/intersection and should fail loudly rather than poison GEOS.
    unusable = out.geometry.isna() | out.geometry.is_empty
    if bool(unusable.any()):
        raise RuntimeError(f"{label or 'Geometry'} contains {int(unusable.sum())} empty geometries after repair.")
    return out


def _simplify_projected(gdf: gpd.GeoDataFrame, metres: float, *, label: str) -> gpd.GeoDataFrame:
    out = _repair_invalid(gdf, label=label)
    out = out.copy()
    out["geometry"] = out.geometry.simplify(metres, preserve_topology=True)
    return _repair_invalid(out, label=f"{label} after simplify")


def _safe_union_boundary(geometries) -> object:
    """Return the outside boundary of a geometry collection without topology crashes.

    Normal union is attempted first. If GEOS encounters a side-location/topology
    conflict, inputs are repaired and snapped to a 1 m precision grid before a
    second union. This is used only on projected rendering geometries.
    """
    geoms = [g for g in geometries if g is not None and not g.is_empty]
    if not geoms:
        raise RuntimeError("Cannot build an outline from an empty geometry collection.")

    try:
        merged = union_all(geoms)
    except GEOSException:
        repaired = []
        for geom in geoms:
            clean = geom if geom.is_valid else make_valid(geom)
            try:
                clean = set_precision(clean, grid_size=TOPOLOGY_GRID_METRES, mode="valid_output")
            except GEOSException:
                # buffer(0) is only a final fallback for a geometry that GEOS
                # cannot precision-snap cleanly.
                clean = make_valid(clean).buffer(0)
            if clean is not None and not clean.is_empty:
                repaired.append(clean)
        if not repaired:
            raise RuntimeError("Geometry repair removed every polygon while building an outline.")
        merged = union_all(repaired, grid_size=TOPOLOGY_GRID_METRES)

    if not merged.is_valid:
        merged = make_valid(merged)
    return merged.boundary


def _rank_table(df: pd.DataFrame, label_col: str) -> pd.DataFrame:
    pivot = df.pivot_table(index="RegionID", columns=label_col, values="Count", aggfunc="first")
    # Zero-speaker categories are not meaningful ranked languages.
    pivot = pivot.where(pivot.gt(0))
    ranks = pivot.rank(ascending=False, method="first", axis=1)
    long = ranks.reset_index().melt(id_vars="RegionID", var_name="RankLabel", value_name="Rank")
    long = long.dropna(subset=["Rank"])
    long["Rank"] = long["Rank"].astype("int16")
    return long[["RegionID", "Rank", "RankLabel"]]


def _validate_data_map(year: int, data: pd.DataFrame, gdf: gpd.GeoDataFrame) -> None:
    data_ids = set(data["RegionID"].astype(str).unique())
    map_ids = set(gdf["RegionID"].astype(str).unique())
    missing_on_map = sorted(data_ids - map_ids)
    missing_in_data = sorted(map_ids - data_ids)
    # Geography files occasionally include a unit whose table is suppressed, but
    # wholesale mismatch means we have the wrong code format/file.
    if len(missing_on_map) > 5 or len(missing_in_data) > 5:
        raise RuntimeError(
            f"{year} Census data/map join mismatch: {len(missing_on_map)} data IDs absent from map and "
            f"{len(missing_in_data)} map IDs absent from data. First examples: "
            f"{missing_on_map[:5]} / {missing_in_data[:5]}"
        )


def prepare_year_assets(year: int) -> None:
    started = perf_counter()
    language_path = LANGUAGE_DATA_2016 if year == 2016 else LANGUAGE_DATA_2021
    group_path = GROUP_DATA_2016 if year == 2016 else GROUP_DATA_2021
    map_index_path = MAP_INDEX_2016 if year == 2016 else MAP_INDEX_2021
    rank_lang_path = RANK_LANGUAGE_2016 if year == 2016 else RANK_LANGUAGE_2021
    rank_group_path = RANK_GROUP_2016 if year == 2016 else RANK_GROUP_2021
    if not language_path.exists() or not group_path.exists():
        raise FileNotFoundError("Processed language data are missing; run scripts/prepare_data.py first.")

    _progress(f"{year}: loading processed language tables")
    language = pd.read_pickle(language_path)
    groups = pd.read_pickle(group_path)

    _progress(f"{year}: loading Census Division boundary file")
    gdf = load_boundary(year)
    _validate_data_map(year, language, gdf)
    _progress(f"{year}: {len(gdf)} Census Divisions loaded")

    _progress(f"{year}: building rank tables")
    _rank_table(language, "LanguageName").to_pickle(rank_lang_path)
    _rank_table(groups, "LanguageGroup").to_pickle(rank_group_path)

    _progress(f"{year}: building map index")
    bounds = gdf.geometry.bounds.reset_index(drop=True)
    index = pd.concat([gdf.drop(columns="geometry").reset_index(drop=True), bounds], axis=1)
    index.columns = ["RegionID", "RegionName", "ProvinceCode", "ProvinceName", "minx", "miny", "maxx", "maxy"]
    index.to_pickle(map_index_path)

    # Reproject only once for all provincial assets. The old implementation
    # reprojected/simplified separately for every province and then unioned in
    # lon/lat, which was both slow and susceptible to GEOS topology failures.
    _progress(f"{year}: projecting boundaries once for display simplification")
    projected = gdf.to_crs("EPSG:3347")

    _progress(f"{year}: simplifying province-level display geometry ({PROVINCE_SIMPLIFY_METRES:g} m)")
    provincial_projected = _simplify_projected(
        projected,
        PROVINCE_SIMPLIFY_METRES,
        label=f"{year} province display geometry",
    )

    _progress(f"{year}: simplifying national display geometry ({NATIONAL_SIMPLIFY_METRES:g} m)")
    national_projected = _simplify_projected(
        provincial_projected,
        NATIONAL_SIMPLIFY_METRES,
        label=f"{year} national display geometry",
    )

    _progress(f"{year}: dissolving province outlines")
    province_outline_rows = []
    province_groups = list(provincial_projected.groupby("ProvinceName", dropna=True, sort=True))
    for i, (province_name, group) in enumerate(province_groups, start=1):
        _progress(f"{year}: outline {i}/{len(province_groups)} - {province_name}")
        province_outline_rows.append(
            {"ProvinceName": str(province_name), "geometry": _safe_union_boundary(group.geometry)}
        )
    province_outlines_projected = gpd.GeoDataFrame(
        province_outline_rows,
        geometry="geometry",
        crs=provincial_projected.crs,
    )

    _progress(f"{year}: dissolving Canada outer outline")
    canada_outer_projected = _safe_union_boundary(national_projected.geometry)

    _progress(f"{year}: converting display assets to WGS84")
    provincial = provincial_projected.to_crs("EPSG:4326")
    national = national_projected.to_crs("EPSG:4326")
    province_outlines = province_outlines_projected.to_crs("EPSG:4326")
    canada_outer = gpd.GeoSeries([canada_outer_projected], crs=national_projected.crs).to_crs("EPSG:4326").iloc[0]

    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    _progress(f"{year}: writing national GeoJSON")
    _write_geojson(
        ASSET_DIR / division_asset_name(year, "Canada"),
        [_feature(r.geometry, r.RegionID) for r in national.itertuples(index=False)],
    )
    _write_geojson(
        ASSET_DIR / province_boundaries_asset_name(year),
        [_feature(r.geometry, r.ProvinceName) for r in province_outlines.itertuples(index=False)],
    )
    _write_geojson(
        ASSET_DIR / outer_asset_name(year, "Canada"),
        [_feature(canada_outer)],
    )

    _progress(f"{year}: writing {len(province_groups)} province/territory GeoJSON sets")
    province_outline_lookup = dict(zip(province_outlines["ProvinceName"], province_outlines.geometry))
    for i, (province_name, group_projected) in enumerate(province_groups, start=1):
        province_name = str(province_name)
        _progress(f"{year}: write province {i}/{len(province_groups)} - {province_name}")
        group = provincial.loc[group_projected.index]
        _write_geojson(
            ASSET_DIR / division_asset_name(year, province_name),
            [_feature(r.geometry, r.RegionID) for r in group.itertuples(index=False)],
        )
        _write_geojson(
            ASSET_DIR / outer_asset_name(year, province_name),
            [_feature(province_outline_lookup[province_name])],
        )

    _progress(f"{year}: year assets complete in {perf_counter() - started:.1f} s")


def _prepare_crosswalk_geometry(year: int) -> gpd.GeoDataFrame:
    _progress(f"crosswalk: loading {year} boundaries")
    gdf = load_boundary(year).to_crs("EPSG:6933")
    gdf = _repair_invalid(gdf, label=f"crosswalk {year}")
    _progress(f"crosswalk: simplifying {year} boundaries ({CROSSWALK_SIMPLIFY_METRES:g} m)")
    gdf = gdf.copy()
    gdf["geometry"] = gdf.geometry.simplify(CROSSWALK_SIMPLIFY_METRES, preserve_topology=True)
    return _repair_invalid(gdf, label=f"crosswalk {year} after simplify")


def _overlay_with_topology_retry(a: gpd.GeoDataFrame, b: gpd.GeoDataFrame, *, province_code: str) -> gpd.GeoDataFrame:
    try:
        return gpd.overlay(a, b, how="intersection", keep_geom_type=False)
    except GEOSException:
        _progress(f"crosswalk: province {province_code} hit a topology conflict; retrying on a {TOPOLOGY_GRID_METRES:g} m precision grid")
        a = a.copy()
        b = b.copy()
        a["geometry"] = [
            set_precision(make_valid(g) if not g.is_valid else g, TOPOLOGY_GRID_METRES, mode="valid_output")
            for g in a.geometry
        ]
        b["geometry"] = [
            set_precision(make_valid(g) if not g.is_valid else g, TOPOLOGY_GRID_METRES, mode="valid_output")
            for g in b.geometry
        ]
        return gpd.overlay(a, b, how="intersection", keep_geom_type=False)


def prepare_crosswalk() -> pd.DataFrame:
    started = perf_counter()
    _progress("crosswalk: starting 2016 → 2021 Census Division reconciliation")
    old = _prepare_crosswalk_geometry(2016)
    new = _prepare_crosswalk_geometry(2021)
    rows: list[pd.DataFrame] = []

    common_provinces = sorted(set(old["ProvinceCode"]) & set(new["ProvinceCode"]))
    for i, province_code in enumerate(common_provinces, start=1):
        province_name = PROVINCE_CODE_TO_NAME.get(province_code, province_code)
        province_started = perf_counter()
        a = old.loc[old["ProvinceCode"].eq(province_code), ["RegionID", "geometry"]].rename(
            columns={"RegionID": "RegionID2016"}
        )
        b = new.loc[new["ProvinceCode"].eq(province_code), ["RegionID", "geometry"]].rename(
            columns={"RegionID": "RegionID2021"}
        )
        if a.empty or b.empty:
            _progress(f"crosswalk: {i}/{len(common_provinces)} {province_name} - skipped (empty)")
            continue

        _progress(
            f"crosswalk: {i}/{len(common_provinces)} {province_name} - "
            f"overlaying {len(a)} old × {len(b)} new divisions"
        )
        area_a = a.set_index("RegionID2016").geometry.area
        area_b = b.set_index("RegionID2021").geometry.area
        inter = _overlay_with_topology_retry(a, b, province_code=province_code)
        if inter.empty:
            _progress(f"crosswalk: {province_name} - no intersections")
            continue
        inter["IntersectionArea"] = inter.geometry.area
        inter = inter.loc[inter["IntersectionArea"].gt(0)].copy()
        inter["OldAreaFraction"] = inter["IntersectionArea"] / inter["RegionID2016"].map(area_a)
        inter["NewAreaFraction"] = inter["IntersectionArea"] / inter["RegionID2021"].map(area_b)
        inter["ProvinceCode"] = province_code
        rows.append(inter[["RegionID2016", "RegionID2021", "ProvinceCode", "OldAreaFraction", "NewAreaFraction"]])
        _progress(
            f"crosswalk: {province_name} - {len(inter)} overlaps in "
            f"{perf_counter() - province_started:.1f} s"
        )

    if not rows:
        raise RuntimeError("No 2016→2021 Census Division overlaps were produced.")
    cross = pd.concat(rows, ignore_index=True)

    _progress("crosswalk: adding same-province nearest-neighbour fallbacks for any unmatched 2016 divisions")
    matched = set(cross["RegionID2016"])
    fallback = []
    unmatched_old = old.loc[~old["RegionID"].isin(matched)]
    for row in unmatched_old.itertuples(index=False):
        cand = new.loc[new["ProvinceCode"].eq(row.ProvinceCode)]
        if cand.empty:
            continue
        idx = cand.geometry.distance(row.geometry).idxmin()
        fallback.append(
            {
                "RegionID2016": row.RegionID,
                "RegionID2021": cand.loc[idx, "RegionID"],
                "ProvinceCode": row.ProvinceCode,
                "OldAreaFraction": 1.0,
                "NewAreaFraction": 1.0,
            }
        )
    if fallback:
        cross = pd.concat([cross, pd.DataFrame(fallback)], ignore_index=True)
        _progress(f"crosswalk: added {len(fallback)} fallback matches")
    else:
        _progress("crosswalk: no fallback matches needed")

    _progress("crosswalk: pruning tiny slivers and normalizing old-area fractions")
    max_idx = cross.groupby("RegionID2016")["OldAreaFraction"].idxmax()
    keep = cross["OldAreaFraction"].ge(0.001)
    keep.loc[max_idx] = True
    cross = cross.loc[keep].copy()
    sums = cross.groupby("RegionID2016")["OldAreaFraction"].transform("sum")
    cross["OldAreaFraction"] = cross["OldAreaFraction"] / sums

    _progress("crosswalk: computing 2021-population-weighted allocation weights")
    lang21 = pd.read_pickle(LANGUAGE_DATA_2021)
    pop21 = lang21[["RegionID", "TotalPopulation"]].drop_duplicates("RegionID").rename(
        columns={"RegionID": "RegionID2021", "TotalPopulation": "Population2021"}
    )
    cross = cross.merge(pop21, on="RegionID2021", how="left")
    cross["AllocationScore"] = cross["NewAreaFraction"] * cross["Population2021"].fillna(0)
    score_sum = cross.groupby("RegionID2016")["AllocationScore"].transform("sum")
    area_sum = cross.groupby("RegionID2016")["OldAreaFraction"].transform("sum")
    cross["Weight"] = np.where(
        score_sum.gt(0),
        cross["AllocationScore"] / score_sum,
        cross["OldAreaFraction"] / area_sum.replace(0, np.nan),
    )
    cross = cross.drop(columns=["Population2021", "AllocationScore"])
    CHANGE_CROSSWALK.parent.mkdir(parents=True, exist_ok=True)
    cross.to_pickle(CHANGE_CROSSWALK)
    _progress(
        f"crosswalk: saved {len(cross)} links for {cross['RegionID2016'].nunique()} old divisions "
        f"in {perf_counter() - started:.1f} s"
    )
    return cross


def _precompute_change(old: pd.DataFrame, new: pd.DataFrame, label_col: str, out_path: Path) -> pd.DataFrame:
    cross = pd.read_pickle(CHANGE_CROSSWALK)

    old_pop = old[["RegionID", "TotalPopulation"]].drop_duplicates("RegionID").rename(
        columns={"RegionID": "RegionID2016", "TotalPopulation": "Population2016"}
    )
    new_pop = new[["RegionID", "TotalPopulation"]].drop_duplicates("RegionID").rename(
        columns={"RegionID": "RegionID2021", "TotalPopulation": "Population2021"}
    )
    baseline_pop = cross.merge(old_pop, on="RegionID2016", how="left")
    baseline_pop["AllocatedPopulation2016"] = baseline_pop["Population2016"] * baseline_pop["Weight"]
    baseline_pop = baseline_pop.groupby("RegionID2021", as_index=False)["AllocatedPopulation2016"].sum(min_count=1)

    old_counts = old[["RegionID", label_col, "CanonicalName", "Count"]].rename(
        columns={"RegionID": "RegionID2016", "Count": "Count2016"}
    )
    allocated = cross[["RegionID2016", "RegionID2021", "Weight"]].merge(old_counts, on="RegionID2016", how="left")
    allocated["AllocatedCount2016"] = allocated["Count2016"] * allocated["Weight"]
    baseline_count = allocated.groupby(["RegionID2021", "CanonicalName"], as_index=False).agg(
        Count2016=("AllocatedCount2016", lambda x: x.sum(min_count=1))
    )

    current = new[["RegionID", label_col, "CanonicalName", "Count"]].rename(
        columns={"RegionID": "RegionID2021", "Count": "Count2021", label_col: "DisplayName"}
    )
    out = current.merge(baseline_count, on=["RegionID2021", "CanonicalName"], how="inner")
    out = out.merge(new_pop, on="RegionID2021", how="left").merge(baseline_pop, on="RegionID2021", how="left")
    out["Share2016"] = np.where(
        out["AllocatedPopulation2016"].gt(0), 100 * out["Count2016"] / out["AllocatedPopulation2016"], np.nan
    )
    out["Share2021"] = np.where(
        out["Population2021"].gt(0), 100 * out["Count2021"] / out["Population2021"], np.nan
    )
    out["SpeakerChangePct"] = np.where(
        out["Count2016"].gt(0), 100 * (out["Count2021"] - out["Count2016"]) / out["Count2016"], np.nan
    )
    out["ShareChangePP"] = out["Share2021"] - out["Share2016"]
    out.to_pickle(out_path)
    return out


def prepare_change_assets(*, force_crosswalk: bool = False) -> None:
    if force_crosswalk or not CHANGE_CROSSWALK.exists():
        prepare_crosswalk()
    else:
        _progress(f"change: keeping existing crosswalk {CHANGE_CROSSWALK.name}")

    _progress("change: precomputing detailed-language change table")
    _precompute_change(
        pd.read_pickle(LANGUAGE_DATA_2016),
        pd.read_pickle(LANGUAGE_DATA_2021),
        "LanguageName",
        CHANGE_LANGUAGE,
    )
    _progress("change: precomputing language-group change table")
    _precompute_change(
        pd.read_pickle(GROUP_DATA_2016),
        pd.read_pickle(GROUP_DATA_2021),
        "LanguageGroup",
        CHANGE_GROUP,
    )
    _progress("change: change tables complete")


def prepare_all_runtime_assets() -> None:
    started = perf_counter()
    _progress("starting runtime asset preparation")
    prepare_year_assets(2016)
    prepare_year_assets(2021)

    if CHANGE_CROSSWALK.exists():
        _progress(f"crosswalk: keeping existing {CHANGE_CROSSWALK.name}")
    else:
        prepare_crosswalk()
    prepare_change_assets(force_crosswalk=False)
    _progress(f"all runtime assets complete in {perf_counter() - started:.1f} s")

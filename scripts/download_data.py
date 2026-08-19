from __future__ import annotations

import argparse
import json
import sys
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import geopandas as gpd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from canada_census_lang.config import (  # noqa: E402
    BOUNDARY_2016_URL,
    BOUNDARY_2016_ZIP,
    BOUNDARY_2021_URL,
    BOUNDARY_2021_ZIP,
    GEOGRAPHIES_2016_JSON,
    PROFILE_2016_URL_TEMPLATE,
    PROFILE_2021_URL,
    PROFILE_2021_ZIP,
    PROVINCE_CODE_TO_NAME,
    RAW_BOUNDARY_2016_DIR,
    RAW_BOUNDARY_2021_DIR,
    RAW_CENSUS_2021_DIR,
    WDS_2016_DIR,
)


def session() -> requests.Session:
    retry = Retry(
        total=5,
        connect=5,
        read=5,
        backoff_factor=0.8,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET"}),
    )
    s = requests.Session()
    s.headers.update({"User-Agent": "Canada-Census-Language-Explorer/1.0"})
    s.mount("https://", HTTPAdapter(max_retries=retry))
    return s


def download_file(url: str, destination: Path, *, force: bool = False) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and destination.stat().st_size > 0 and not force:
        print(f"keep    {destination.name}")
        return
    print(f"get     {destination.name}")
    tmp = destination.with_suffix(destination.suffix + ".part")
    with session().get(url, stream=True, timeout=(20, 180)) as response:
        response.raise_for_status()
        with tmp.open("wb") as fh:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    fh.write(chunk)
    tmp.replace(destination)


def extract_zip(path: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path) as zf:
        zf.testzip()
        zf.extractall(destination)


def strip_json_prefix(text: str) -> str:
    text = text.lstrip("\ufeff\r\n \t")
    if text.startswith("//"):
        text = text[2:]
    return text


def fetch_json(url: str) -> dict:
    with session().get(url, timeout=(20, 120)) as response:
        response.raise_for_status()
        text = strip_json_prefix(response.text)
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            preview = text[:300].replace("\r", " ").replace("\n", " ")
            raise RuntimeError(
                "Statistics Canada returned a non-JSON response for "
                f"{url} (HTTP {response.status_code}, content-type="
                f"{response.headers.get('content-type')!r}). Response begins: {preview!r}"
            ) from exc


def download_boundaries(force: bool = False) -> None:
    download_file(BOUNDARY_2016_URL, BOUNDARY_2016_ZIP, force=force)
    download_file(BOUNDARY_2021_URL, BOUNDARY_2021_ZIP, force=force)
    extract_zip(BOUNDARY_2016_ZIP, RAW_BOUNDARY_2016_DIR)
    extract_zip(BOUNDARY_2021_ZIP, RAW_BOUNDARY_2021_DIR)


def download_2021_profile(force: bool = False) -> None:
    download_file(PROFILE_2021_URL, PROFILE_2021_ZIP, force=force)
    extract_zip(PROFILE_2021_ZIP, RAW_CENSUS_2021_DIR / "profile")


def _columns_and_data(obj: dict) -> tuple[list[str], list[list]]:
    columns = obj.get("COLUMNS")
    data = obj.get("DATA")
    if not isinstance(columns, list) or not isinstance(data, list):
        raise RuntimeError("Unexpected Statistics Canada WDS response schema.")
    return columns, data


def _2016_dguids(geo_obj: dict) -> list[str]:
    columns, data = _columns_and_data(geo_obj)
    lookup = {str(name).upper(): idx for idx, name in enumerate(columns)}
    idx = lookup.get("GEO_UID")
    if idx is None:
        idx = lookup.get("DGUID")
    if idx is None:
        raise RuntimeError(f"2016 geography service did not return GEO_UID/DGUID. Columns: {columns}")
    dguids = sorted({str(row[idx]).strip() for row in data if row[idx]})
    if not dguids:
        raise RuntimeError("2016 geography service returned no Census Division DGUIDs.")
    return dguids


def _make_2016_cd_dguid(cd_uid: object) -> str:
    cd = str(cd_uid).strip().replace(".0", "").zfill(4)
    if not cd.isdigit() or len(cd) != 4:
        raise ValueError(f"Invalid 2016 Census Division UID: {cd_uid!r}")
    return f"2016A0003{cd}"


def _2016_geographies_from_boundary() -> dict:
    """Build the CD geography list from the already-downloaded official boundary file.

    This deliberately avoids the archived CR2016Geo web service, which can
    intermittently return an empty/non-JSON response even though the boundary
    and Census Profile products remain available.
    """
    candidates = sorted(RAW_BOUNDARY_2016_DIR.glob("**/*.shp"))
    if not candidates:
        raise FileNotFoundError(
            f"No extracted 2016 Census Division shapefile found under {RAW_BOUNDARY_2016_DIR}."
        )

    gdf = gpd.read_file(candidates[0], ignore_geometry=True)
    cols = {str(c).upper(): c for c in gdf.columns}
    if "CDUID" not in cols or "CDNAME" not in cols:
        raise RuntimeError(
            f"Unexpected 2016 Census Division shapefile schema. Columns: {list(gdf.columns)}"
        )

    cd_uid = gdf[cols["CDUID"]].astype(str).str.replace(r"\.0$", "", regex=True).str.zfill(4)
    if "PRUID" in cols:
        pr_uid = gdf[cols["PRUID"]].astype(str).str.replace(r"\.0$", "", regex=True).str.zfill(2)
    else:
        pr_uid = cd_uid.str[:2]
    cd_name = gdf[cols["CDNAME"]].astype(str).str.strip()

    rows = []
    for cd, pr, name in zip(cd_uid, pr_uid, cd_name):
        rows.append(
            [
                _make_2016_cd_dguid(cd),
                pr,
                PROVINCE_CODE_TO_NAME.get(pr, pr),
                cd,
                name,
            ]
        )

    rows.sort(key=lambda row: row[3])
    return {
        "COLUMNS": [
            "GEO_UID",
            "PROV_TERR_ID_CODE",
            "PROV_TERR_NAME_NOM",
            "GEO_ID_CODE",
            "GEO_NAME_NOM",
        ],
        "DATA": rows,
    }


def _download_one_2016(dguid: str, force: bool) -> tuple[str, str]:
    destination = WDS_2016_DIR / f"{dguid}.json"
    if destination.exists() and destination.stat().st_size > 100 and not force:
        return dguid, "keep"
    url = PROFILE_2016_URL_TEMPLATE.format(dguid=dguid)
    obj = fetch_json(url)
    _columns_and_data(obj)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")
    return dguid, "get"


def download_2016_language(*, workers: int = 6, force: bool = False) -> None:
    print("build   2016 Census Division geography list from boundary file")
    geo_obj = _2016_geographies_from_boundary()
    GEOGRAPHIES_2016_JSON.parent.mkdir(parents=True, exist_ok=True)
    GEOGRAPHIES_2016_JSON.write_text(json.dumps(geo_obj, ensure_ascii=False), encoding="utf-8")
    dguids = _2016_dguids(geo_obj)
    print(f"2016 Census divisions: {len(dguids)}")

    WDS_2016_DIR.mkdir(parents=True, exist_ok=True)
    completed = 0
    errors: list[str] = []
    with ThreadPoolExecutor(max_workers=max(1, int(workers))) as pool:
        futures = {pool.submit(_download_one_2016, dguid, force): dguid for dguid in dguids}
        for future in as_completed(futures):
            dguid = futures[future]
            try:
                _, action = future.result()
                completed += 1
                if completed == 1 or completed % 20 == 0 or completed == len(dguids):
                    print(f"{action:7} 2016 language profiles {completed}/{len(dguids)}")
            except Exception as exc:
                errors.append(f"{dguid}: {exc}")
    if errors:
        raise RuntimeError("Some 2016 Census profiles failed:\n" + "\n".join(errors[:20]))


def main() -> None:
    parser = argparse.ArgumentParser(description="Download official Statistics Canada Census language and boundary data.")
    parser.add_argument("--workers", type=int, default=6, help="Parallel requests for the 2016 WDS (default: 6).")
    parser.add_argument("--force", action="store_true", help="Redownload files that already exist.")
    args = parser.parse_args()

    download_boundaries(force=args.force)
    download_2021_profile(force=args.force)
    download_2016_language(workers=args.workers, force=args.force)
    print("Download complete.")


if __name__ == "__main__":
    main()

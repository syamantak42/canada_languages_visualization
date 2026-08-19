from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
ASSET_DIR = PROJECT_ROOT / "assets" / "generated"

RAW_CENSUS_2016_DIR = RAW_DIR / "census_2016"
RAW_CENSUS_2021_DIR = RAW_DIR / "census_2021"
RAW_BOUNDARY_2016_DIR = RAW_DIR / "boundaries" / "2016"
RAW_BOUNDARY_2021_DIR = RAW_DIR / "boundaries" / "2021"

BOUNDARY_2016_ZIP = RAW_BOUNDARY_2016_DIR / "lcd_000b16a_e.zip"
BOUNDARY_2021_ZIP = RAW_BOUNDARY_2021_DIR / "lcd_000b21a_e.zip"
PROFILE_2021_ZIP = RAW_CENSUS_2021_DIR / "98-401-X2021004_eng_CSV.zip"
GEOGRAPHIES_2016_JSON = RAW_CENSUS_2016_DIR / "census_divisions.json"
WDS_2016_DIR = RAW_CENSUS_2016_DIR / "wds"

BOUNDARY_2016_URL = (
    "https://www12.statcan.gc.ca/census-recensement/2011/geo/bound-limit/"
    "files-fichiers/2016/lcd_000b16a_e.zip"
)
BOUNDARY_2021_URL = (
    "https://www12.statcan.gc.ca/census-recensement/2021/geo/sip-pis/"
    "boundary-limites/files-fichiers/lcd_000b21a_e.zip"
)
PROFILE_2021_URL = (
    "https://www12.statcan.gc.ca/census-recensement/2021/dp-pd/prof/details/"
    "download-telecharger/comp/GetFile.cfm?Lang=E&FILETYPE=CSV&GEONO=004"
)
GEOGRAPHY_2016_URL = (
    "https://www12.statcan.gc.ca/rest/census-recensement/"
    "CR2016Geo.json?lang=E&geos=CD&cpt=00"
)
PROFILE_2016_URL_TEMPLATE = (
    "https://www12.statcan.gc.ca/rest/census-recensement/"
    "CPR2016.json?lang=E&dguid={dguid}&topic=10&notes=0&stat=0"
)

LANGUAGE_DATA_2016 = PROCESSED_DIR / "language_data_2016.pkl"
LANGUAGE_DATA_2021 = PROCESSED_DIR / "language_data_2021.pkl"
GROUP_DATA_2016 = PROCESSED_DIR / "language_group_data_2016.pkl"
GROUP_DATA_2021 = PROCESSED_DIR / "language_group_data_2021.pkl"
LANGUAGE_METADATA_2016 = PROCESSED_DIR / "language_metadata_2016.pkl"
LANGUAGE_METADATA_2021 = PROCESSED_DIR / "language_metadata_2021.pkl"
MAP_INDEX_2016 = PROCESSED_DIR / "map_index_2016.pkl"
MAP_INDEX_2021 = PROCESSED_DIR / "map_index_2021.pkl"
RANK_LANGUAGE_2016 = PROCESSED_DIR / "rank_language_2016.pkl"
RANK_LANGUAGE_2021 = PROCESSED_DIR / "rank_language_2021.pkl"
RANK_GROUP_2016 = PROCESSED_DIR / "rank_group_2016.pkl"
RANK_GROUP_2021 = PROCESSED_DIR / "rank_group_2021.pkl"
CHANGE_CROSSWALK = PROCESSED_DIR / "cd_crosswalk_2016_2021.pkl"
CHANGE_LANGUAGE = PROCESSED_DIR / "language_change_2016_2021.pkl"
CHANGE_GROUP = PROCESSED_DIR / "language_group_change_2016_2021.pkl"

PROVINCE_CODE_TO_NAME = {
    "10": "Newfoundland and Labrador",
    "11": "Prince Edward Island",
    "12": "Nova Scotia",
    "13": "New Brunswick",
    "24": "Quebec",
    "35": "Ontario",
    "46": "Manitoba",
    "47": "Saskatchewan",
    "48": "Alberta",
    "59": "British Columbia",
    "60": "Yukon",
    "61": "Northwest Territories",
    "62": "Nunavut",
}

# Conservative 2016 -> 2021 label harmonization. These are label changes for
# essentially the same language/category, not broad classification mergers.
LANGUAGE_RENAMES_2016_TO_2021 = {
    "Aboriginal languages": "Indigenous languages",
    "Cree-Montagnais languages": "Cree-Innu languages",
    "Moose Cree": "Ililimowin (Moose Cree)",
    "Southern East Cree": "Inu Ayimun (Southern East Cree)",
    "Northern East Cree": "Iyiyiw-Ayimiwin (Northern East Cree)",
    "Swampy Cree": "Nehinawewin (Swampy Cree)",
    "Plains Cree": "Nehiyawewin (Plains Cree)",
    "Woods Cree": "Nihithawiwin (Woods Cree)",
    "Montagnais (Innu)": "Innu (Montagnais)",
    "Carrier": "Dakelh (Carrier)",
    "Beaver": "Dane-zaa (Beaver)",
    "Malecite": "Wolastoqewi (Malecite)",
}

# Rendering only; analytical geometries remain unsimplified.
NATIONAL_SIMPLIFY_METRES = 2000.0
PROVINCE_SIMPLIFY_METRES = 350.0

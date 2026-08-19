from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from canada_census_lang.config import (  # noqa: E402
    CHANGE_GROUP,
    CHANGE_LANGUAGE,
    LANGUAGE_DATA_2016,
    LANGUAGE_DATA_2021,
    MAP_INDEX_2016,
    MAP_INDEX_2021,
)


def main() -> None:
    for year, data_path, map_path in (
        (2016, LANGUAGE_DATA_2016, MAP_INDEX_2016),
        (2021, LANGUAGE_DATA_2021, MAP_INDEX_2021),
    ):
        data = pd.read_pickle(data_path)
        index = pd.read_pickle(map_path)
        data_ids = set(data["RegionID"].astype(str))
        map_ids = set(index["RegionID"].astype(str))
        print(
            f"{year}: {len(data_ids)} Census divisions, "
            f"{data['LanguageName'].nunique()} detailed languages; "
            f"data-only IDs={len(data_ids-map_ids)}, map-only IDs={len(map_ids-data_ids)}"
        )
    if CHANGE_LANGUAGE.exists():
        changes = pd.read_pickle(CHANGE_LANGUAGE)
        print(f"Comparable detailed language labels, 2016→2021: {changes['DisplayName'].nunique()}")
    if CHANGE_GROUP.exists():
        changes = pd.read_pickle(CHANGE_GROUP)
        print(f"Comparable language-group labels, 2016→2021: {changes['DisplayName'].nunique()}")


if __name__ == "__main__":
    main()

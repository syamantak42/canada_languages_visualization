from __future__ import annotations

import json
import re
import zipfile
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

from .config import (
    GEOGRAPHIES_2016_JSON,
    GROUP_DATA_2016,
    GROUP_DATA_2021,
    LANGUAGE_DATA_2016,
    LANGUAGE_DATA_2021,
    LANGUAGE_METADATA_2016,
    LANGUAGE_METADATA_2021,
    LANGUAGE_RENAMES_2016_TO_2021,
    PROFILE_2021_ZIP,
    PROCESSED_DIR,
    PROVINCE_CODE_TO_NAME,
    WDS_2016_DIR,
)

MOTHER_TONGUE_ROOT = "Total - Mother tongue for the total population excluding institutional residents"


def clean_label(value: object) -> str:
    text = "" if value is None else str(value)
    return re.sub(r"\s+", " ", text).strip()


def canonical_change_label(label: str, year: int) -> str:
    label = clean_label(label)
    if year == 2016:
        return LANGUAGE_RENAMES_2016_TO_2021.get(label, label)
    return label


def _parent_indices(indents: list[int]) -> list[int | None]:
    stack: list[int] = []
    parents: list[int | None] = []
    for i, indent in enumerate(indents):
        while stack and indents[stack[-1]] >= indent:
            stack.pop()
        parents.append(stack[-1] if stack else None)
        stack.append(i)
    return parents


def extract_mother_tongue_metadata(meta: pd.DataFrame) -> tuple[pd.DataFrame, object]:
    """
    Identify detailed single-response mother-tongue leaves and assign each one
    to its nearest useful parent language group.

    Required columns: CharacteristicID, RawLabel, Indent, Order.
    """
    m = meta[["CharacteristicID", "RawLabel", "Indent", "Order"]].copy()
    m = m.sort_values("Order").drop_duplicates("CharacteristicID").reset_index(drop=True)
    m["Label"] = m["RawLabel"].map(clean_label)
    m["Indent"] = pd.to_numeric(m["Indent"], errors="coerce").fillna(0).astype(int)

    roots = m.index[
        m["Label"].str.startswith(MOTHER_TONGUE_ROOT, na=False)
    ].tolist()
    if not roots:
        raise RuntimeError("Could not find the mother-tongue root characteristic.")
    root_idx = roots[0]
    root_indent = int(m.at[root_idx, "Indent"])

    root_end = len(m)
    for j in range(root_idx + 1, len(m)):
        if int(m.at[j, "Indent"]) <= root_indent:
            root_end = j
            break
    subtree = m.iloc[root_idx:root_end].copy()

    single_candidates = subtree.index[
        subtree["Label"].str.contains(r"^Single (?:mother tongue )?responses?$", case=False, regex=True, na=False)
    ].tolist()
    if not single_candidates:
        # Profile wording in some releases is simply "Single responses".
        single_candidates = subtree.index[
            subtree["Label"].str.startswith("Single", na=False)
        ].tolist()
    if not single_candidates:
        raise RuntimeError("Could not find the single-response mother-tongue branch.")

    single_idx = single_candidates[0]
    single_indent = int(m.at[single_idx, "Indent"])
    single_end = root_end
    for j in range(single_idx + 1, root_end):
        if int(m.at[j, "Indent"]) <= single_indent:
            single_end = j
            break

    parents = _parent_indices(m["Indent"].tolist())
    m["ParentIndex"] = parents

    selected_indices = list(range(single_idx + 1, single_end))
    leaves: list[int] = []
    for idx in selected_indices:
        indent = int(m.at[idx, "Indent"])
        has_child = idx + 1 < single_end and int(m.at[idx + 1, "Indent"]) > indent
        if not has_child:
            leaves.append(idx)

    broad = {
        "Single responses",
        "Single mother tongue responses",
        "Official languages",
        "Non-official languages",
    }
    rows: list[dict] = []
    labels_seen: dict[str, int] = {}
    for idx in leaves:
        language = m.at[idx, "Label"]
        parent_idx = m.at[idx, "ParentIndex"]
        parent = m.at[parent_idx, "Label"] if parent_idx is not None else ""
        if parent in broad or not parent:
            group = language
        else:
            group = parent
        labels_seen[language] = labels_seen.get(language, 0) + 1
        rows.append(
            {
                "CharacteristicID": m.at[idx, "CharacteristicID"],
                "LanguageName": language,
                "LanguageGroup": group,
                "Indent": int(m.at[idx, "Indent"]),
            }
        )

    leaf_meta = pd.DataFrame(rows)
    if leaf_meta.empty:
        raise RuntimeError("No detailed mother-tongue leaves were identified.")

    # Rare duplicated leaf labels are disambiguated rather than silently merged.
    duplicate_labels = {k for k, v in labels_seen.items() if v > 1}
    if duplicate_labels:
        mask = leaf_meta["LanguageName"].isin(duplicate_labels)
        leaf_meta.loc[mask, "LanguageName"] = (
            leaf_meta.loc[mask, "LanguageName"]
            + " — "
            + leaf_meta.loc[mask, "LanguageGroup"]
        )

    return leaf_meta.reset_index(drop=True), m.at[root_idx, "CharacteristicID"]


def _group_table(language_df: pd.DataFrame) -> pd.DataFrame:
    keys = ["RegionID", "RegionName", "ProvinceCode", "ProvinceName", "LanguageGroup"]
    grouped = (
        language_df.groupby(keys, dropna=False, as_index=False)
        .agg(Count=("Count", lambda x: x.sum(min_count=1)), TotalPopulation=("TotalPopulation", "first"))
    )
    grouped["Percent"] = np.where(
        grouped["TotalPopulation"].gt(0),
        100.0 * grouped["Count"] / grouped["TotalPopulation"],
        np.nan,
    )
    grouped["CanonicalName"] = grouped["LanguageGroup"]
    return grouped


def _write_processed(year: int, language_df: pd.DataFrame, metadata: pd.DataFrame) -> None:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    language_df = language_df.copy()
    language_df["CanonicalName"] = language_df["LanguageName"].map(
        lambda x: canonical_change_label(x, year)
    )
    group_df = _group_table(language_df)
    group_df["CanonicalName"] = group_df["LanguageGroup"].map(
        lambda x: canonical_change_label(x, year)
    )

    if year == 2016:
        language_df.to_pickle(LANGUAGE_DATA_2016)
        group_df.to_pickle(GROUP_DATA_2016)
        metadata.to_pickle(LANGUAGE_METADATA_2016)
    else:
        language_df.to_pickle(LANGUAGE_DATA_2021)
        group_df.to_pickle(GROUP_DATA_2021)
        metadata.to_pickle(LANGUAGE_METADATA_2021)


def _read_json_file(path: Path) -> dict:
    text = path.read_text(encoding="utf-8-sig").lstrip()
    if text.startswith("//"):
        text = text[2:]
    return json.loads(text)


def prepare_2016() -> pd.DataFrame:
    if not GEOGRAPHIES_2016_JSON.exists():
        raise FileNotFoundError("2016 Census Division geography list is missing; run scripts/download_data.py.")
    files = sorted(WDS_2016_DIR.glob("*.json"))
    if not files:
        raise FileNotFoundError("2016 Census language WDS files are missing; run scripts/download_data.py.")

    first_obj = _read_json_file(files[0])
    first = pd.DataFrame(first_obj["DATA"], columns=first_obj["COLUMNS"])
    metadata = first[["TEXT_ID", "TEXT_NAME_NOM", "INDENT_ID"]].copy()
    metadata.columns = ["CharacteristicID", "RawLabel", "Indent"]
    metadata["Order"] = np.arange(len(metadata))
    leaf_meta, root_id = extract_mother_tongue_metadata(metadata)
    wanted = set(leaf_meta["CharacteristicID"].tolist()) | {root_id}
    leaf_lookup = leaf_meta.set_index("CharacteristicID")

    rows: list[dict] = []
    for path in files:
        obj = _read_json_file(path)
        df = pd.DataFrame(obj["DATA"], columns=obj["COLUMNS"])
        if df.empty:
            continue
        df = df[df["TEXT_ID"].isin(wanted)].copy()
        if df.empty:
            continue
        root = df.loc[df["TEXT_ID"].eq(root_id), "T_DATA_DONNEE"]
        denominator = pd.to_numeric(root.iloc[0], errors="coerce") if not root.empty else np.nan
        geo = df.iloc[0]
        region_id = str(geo["GEO_ID"]).strip().zfill(4)
        province_code = str(geo["PROV_TERR_ID"]).strip().zfill(2)
        region_name = clean_label(geo["GEO_NAME_NOM"])
        province_name = PROVINCE_CODE_TO_NAME.get(province_code, clean_label(geo["PROV_TERR_NAME_NOM"]))

        for record in df.loc[df["TEXT_ID"].isin(leaf_lookup.index)].itertuples(index=False):
            char_id = getattr(record, "TEXT_ID")
            info = leaf_lookup.loc[char_id]
            count = pd.to_numeric(getattr(record, "T_DATA_DONNEE"), errors="coerce")
            rows.append(
                {
                    "RegionID": region_id,
                    "RegionName": region_name,
                    "ProvinceCode": province_code,
                    "ProvinceName": province_name,
                    "LanguageName": info["LanguageName"],
                    "LanguageGroup": info["LanguageGroup"],
                    "Count": float(count) if pd.notna(count) else np.nan,
                    "TotalPopulation": float(denominator) if pd.notna(denominator) else np.nan,
                }
            )

    out = pd.DataFrame(rows)
    if out.empty:
        raise RuntimeError("No 2016 language rows were produced from the downloaded WDS files.")
    out["Percent"] = np.where(
        out["TotalPopulation"].gt(0),
        100.0 * out["Count"] / out["TotalPopulation"],
        np.nan,
    )
    _write_processed(2016, out, leaf_meta)
    return out


def _find_2021_csv() -> Path:
    candidates = sorted(PROFILE_2021_ZIP.parent.glob("**/*English_CSV_data.csv"))
    if candidates:
        return candidates[0]
    if PROFILE_2021_ZIP.exists():
        with zipfile.ZipFile(PROFILE_2021_ZIP) as zf:
            names = [n for n in zf.namelist() if n.endswith("English_CSV_data.csv")]
            if not names:
                raise RuntimeError("The 2021 profile ZIP does not contain the expected CSV data file.")
            zf.extractall(PROFILE_2021_ZIP.parent / "profile")
        candidates = sorted((PROFILE_2021_ZIP.parent / "profile").glob("**/*English_CSV_data.csv"))
        if candidates:
            return candidates[0]
    raise FileNotFoundError("2021 Census Division profile CSV is missing; run scripts/download_data.py.")


def _read_2021_csv(path: Path, **kwargs) -> pd.DataFrame | Iterable[pd.DataFrame]:
    try:
        return pd.read_csv(path, encoding="utf-8-sig", low_memory=False, **kwargs)
    except UnicodeDecodeError:
        return pd.read_csv(path, encoding="latin1", low_memory=False, **kwargs)


def prepare_2021() -> pd.DataFrame:
    csv_path = _find_2021_csv()
    sample = _read_2021_csv(csv_path, nrows=10000)
    if "CHARACTERISTIC_ID" not in sample.columns:
        raise RuntimeError("Unexpected 2021 Census Profile CSV schema.")

    first_dguid = sample.iloc[0]["DGUID"]
    first_geo = sample.loc[sample["DGUID"].eq(first_dguid)].copy()
    # The first 10k rows comfortably contain a complete CD profile (~2600 rows).
    metadata = first_geo[["CHARACTERISTIC_ID", "CHARACTERISTIC_NAME"]].copy()
    metadata["RawLabel"] = metadata["CHARACTERISTIC_NAME"].astype(str)
    metadata["Indent"] = metadata["RawLabel"].str.extract(r"^(\s*)", expand=False).str.len()
    metadata["Order"] = np.arange(len(metadata))
    metadata = metadata.rename(columns={"CHARACTERISTIC_ID": "CharacteristicID"})
    leaf_meta, root_id = extract_mother_tongue_metadata(metadata)
    wanted = set(pd.to_numeric(leaf_meta["CharacteristicID"], errors="coerce").dropna().astype(int)) | {int(root_id)}
    leaf_meta = leaf_meta.copy()
    leaf_meta["CharacteristicID"] = pd.to_numeric(leaf_meta["CharacteristicID"], errors="raise").astype(int)
    leaf_lookup = leaf_meta.set_index("CharacteristicID")

    usecols = [
        "DGUID", "ALT_GEO_CODE", "GEO_LEVEL", "GEO_NAME",
        "CHARACTERISTIC_ID", "C1_COUNT_TOTAL",
    ]
    pieces: list[pd.DataFrame] = []
    for chunk in _read_2021_csv(csv_path, usecols=usecols, chunksize=150000):
        chunk["CHARACTERISTIC_ID"] = pd.to_numeric(chunk["CHARACTERISTIC_ID"], errors="coerce")
        keep_geo = chunk["GEO_LEVEL"].astype(str).str.contains("census division", case=False, na=False)
        keep_char = chunk["CHARACTERISTIC_ID"].isin(wanted)
        part = chunk.loc[keep_geo & keep_char].copy()
        if not part.empty:
            pieces.append(part)
    if not pieces:
        raise RuntimeError("No Census Division mother-tongue rows were found in the 2021 profile CSV.")
    raw = pd.concat(pieces, ignore_index=True)
    raw["CHARACTERISTIC_ID"] = raw["CHARACTERISTIC_ID"].astype(int)
    raw["C1_COUNT_TOTAL"] = pd.to_numeric(raw["C1_COUNT_TOTAL"], errors="coerce")

    denominators = (
        raw.loc[raw["CHARACTERISTIC_ID"].eq(int(root_id)), ["DGUID", "C1_COUNT_TOTAL"]]
        .drop_duplicates("DGUID")
        .rename(columns={"C1_COUNT_TOTAL": "TotalPopulation"})
    )
    lang = raw.loc[raw["CHARACTERISTIC_ID"].isin(leaf_lookup.index)].copy()
    lang = lang.merge(denominators, on="DGUID", how="left")
    meta_reset = leaf_meta[["CharacteristicID", "LanguageName", "LanguageGroup"]]
    lang = lang.merge(meta_reset, left_on="CHARACTERISTIC_ID", right_on="CharacteristicID", how="left")

    region_id = lang["ALT_GEO_CODE"].astype(str).str.replace(r"\.0$", "", regex=True).str.zfill(4)
    # Fallback to the final four characters of the DGUID if ALT_GEO_CODE was parsed oddly.
    bad = ~region_id.str.fullmatch(r"\d{4}")
    region_id.loc[bad] = lang.loc[bad, "DGUID"].astype(str).str[-4:]
    lang["RegionID"] = region_id
    lang["ProvinceCode"] = lang["RegionID"].str[:2]
    lang["ProvinceName"] = lang["ProvinceCode"].map(PROVINCE_CODE_TO_NAME)
    lang["RegionName"] = lang["GEO_NAME"].map(clean_label)
    lang["Count"] = lang["C1_COUNT_TOTAL"]
    out = lang[
        ["RegionID", "RegionName", "ProvinceCode", "ProvinceName", "LanguageName", "LanguageGroup", "Count", "TotalPopulation"]
    ].copy()
    out["Percent"] = np.where(
        out["TotalPopulation"].gt(0),
        100.0 * out["Count"] / out["TotalPopulation"],
        np.nan,
    )
    _write_processed(2021, out, leaf_meta)
    return out


def prepare_all() -> tuple[pd.DataFrame, pd.DataFrame]:
    return prepare_2016(), prepare_2021()

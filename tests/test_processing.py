import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from canada_census_lang.processing import canonical_change_label, extract_mother_tongue_metadata


def test_extracts_single_response_leaves_and_groups():
    labels = [
        (1, "Total - Mother tongue for the total population excluding institutional residents - 100% data", 0),
        (2, "Single responses", 1),
        (3, "Official languages", 2),
        (4, "English", 3),
        (5, "French", 3),
        (6, "Non-official languages", 2),
        (7, "Indo-European languages", 3),
        (8, "Indo-Iranian languages", 4),
        (9, "Indo-Aryan languages", 5),
        (10, "Hindi", 6),
        (11, "Punjabi", 6),
        (12, "Multiple responses", 1),
        (13, "English and French", 2),
    ]
    meta = pd.DataFrame(labels, columns=["CharacteristicID", "RawLabel", "Indent"])
    meta["Order"] = range(len(meta))
    leaves, root = extract_mother_tongue_metadata(meta)
    assert root == 1
    assert set(leaves["LanguageName"]) == {"English", "French", "Hindi", "Punjabi"}
    groups = dict(zip(leaves["LanguageName"], leaves["LanguageGroup"]))
    assert groups["English"] == "English"
    assert groups["French"] == "French"
    assert groups["Hindi"] == "Indo-Aryan languages"
    assert groups["Punjabi"] == "Indo-Aryan languages"


def test_verified_rename_is_canonicalized_for_change():
    assert canonical_change_label("Moose Cree", 2016) == "Ililimowin (Moose Cree)"
    assert canonical_change_label("Ililimowin (Moose Cree)", 2021) == "Ililimowin (Moose Cree)"

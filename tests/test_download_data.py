import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("download_data", ROOT / "scripts" / "download_data.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def test_2016_geography_dguid_parser():
    obj = {
        "COLUMNS": ["PR_ID", "GEO_UID", "GEO_NAME"],
        "DATA": [["10", "2016A00031001", "A"], ["10", "2016A00031002", "B"]],
    }
    assert mod._2016_dguids(obj) == ["2016A00031001", "2016A00031002"]


def test_wds_double_slash_prefix_is_removed():
    assert mod.strip_json_prefix('//{"x": 1}') == '{"x": 1}'


def test_2016_cd_dguid_is_derived_from_cd_uid():
    assert mod._make_2016_cd_dguid("6204") == "2016A00036204"
    assert mod._make_2016_cd_dguid(1001) == "2016A00031001"

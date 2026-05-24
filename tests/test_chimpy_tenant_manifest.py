"""S1 Task 11 acceptance: tenant declares a Tier-1 chimpy-tenant.toml."""

import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MANIFEST_PATH = REPO / "chimpy-tenant.toml"


def test_manifest_file_exists():
    assert MANIFEST_PATH.is_file()


def test_manifest_parses_as_toml():
    with MANIFEST_PATH.open("rb") as fh:
        tomllib.load(fh)


def test_manifest_declares_tier_1_fields():
    with MANIFEST_PATH.open("rb") as fh:
        m = tomllib.load(fh)
    for key in ("name", "kind", "schema", "image"):
        assert key in m["tenant"], f"missing [tenant].{key}"


def test_manifest_kind_is_extract():
    with MANIFEST_PATH.open("rb") as fh:
        m = tomllib.load(fh)
    assert m["tenant"]["kind"] == "extract"


def test_manifest_name_is_overdrive_checkouts():
    with MANIFEST_PATH.open("rb") as fh:
        m = tomllib.load(fh)
    assert m["tenant"]["name"] == "overdrive-checkouts"


def test_manifest_schema_is_overdrive():
    with MANIFEST_PATH.open("rb") as fh:
        m = tomllib.load(fh)
    assert m["tenant"]["schema"] == "overdrive"

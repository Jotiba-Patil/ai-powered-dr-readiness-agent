from pathlib import Path

import pytest

from dr_agent.loaders import (
    decode_utf8,
    inventory_from_data,
    inventory_from_text,
    load_inventory,
    read_text_file,
)
from dr_agent.utils.errors import BadRequestError, NotFoundError, ValidationError

MOCK = Path(__file__).resolve().parents[3] / "mock-data"


def test_read_text_file_reads_utf8(tmp_path: Path) -> None:
    path = tmp_path / "r.md"
    path.write_text("# Café", encoding="utf-8")
    assert read_text_file(path) == "# Café"


def test_read_text_file_missing_does_not_leak_full_path(tmp_path: Path) -> None:
    with pytest.raises(NotFoundError) as info:
        read_text_file(tmp_path / "missing.md")
    assert info.value.message == "file not found: missing.md"
    assert info.value.details is None


def test_read_text_file_rejects_non_utf8(tmp_path: Path) -> None:
    path = tmp_path / "bad.md"
    path.write_bytes(b"\xff\xfe\x00bad")
    with pytest.raises(BadRequestError):
        read_text_file(path)


def test_decode_utf8_rejects_bad_bytes() -> None:
    with pytest.raises(BadRequestError, match=r"upload\.md"):
        decode_utf8(b"\xff", label="upload.md")


def test_load_inventory_mock_file() -> None:
    inventory = load_inventory(MOCK / "inventories" / "healthy.json")
    assert len(inventory.services) == 7


def test_inventory_invalid_json_reports_position() -> None:
    with pytest.raises(ValidationError) as info:
        inventory_from_text("{not json", label="inv.json")
    assert info.value.details is not None
    assert info.value.details["line"] == 1


def test_inventory_schema_errors_are_summarised_without_input() -> None:
    with pytest.raises(ValidationError) as info:
        inventory_from_data({"services": [{"name": "x", "endpoint": "nope"}]}, label="inv")
    assert info.value.details is not None
    errors = info.value.details["errors"]
    assert isinstance(errors, list)
    assert errors
    for err in errors:
        assert set(err) == {"loc", "msg", "type"}

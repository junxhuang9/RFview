from __future__ import annotations

from rfview.hdf5 import HDF5_MAGIC, inspect_hdf5


def test_hdf5_magic_invalid_is_blocking(tmp_path):
    path = tmp_path / "bad.h5"
    path.write_bytes(b"not hdf5")

    summary = inspect_hdf5(path)

    assert summary.validate()[0].rule_id == "HDF5_MAGIC_INVALID"


def test_hdf5_magic_without_optional_reader_reports_dependency(tmp_path):
    path = tmp_path / "radio.h5"
    path.write_bytes(HDF5_MAGIC + b"placeholder")

    summary = inspect_hdf5(path)
    rule_ids = [issue.rule_id for issue in summary.validate()]

    assert "HDF5_READER_MISSING" in rule_ids or "HDF5_RADIOML_LAYOUT_UNKNOWN" in rule_ids

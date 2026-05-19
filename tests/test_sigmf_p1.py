from __future__ import annotations

import json
import struct

from rfview.cache import CacheIndex
from rfview.cli import main
from rfview.datatypes import parse_sigmf_datatype
from rfview.ingest import inspect_path
from rfview.samples import annotation_coverage, read_sigmf_window


def write_sigmf_pair(tmp_path):
    meta = tmp_path / "clean.sigmf-meta"
    data = tmp_path / "clean.sigmf-data"
    samples = [(0.0, 1.0), (1.0, 0.0), (-1.0, 0.5), (0.25, -0.25)]
    data.write_bytes(b"".join(struct.pack("<ff", i, q) for i, q in samples))
    meta.write_text(
        json.dumps(
            {
                "global": {"core:datatype": "cf32_le", "core:sample_rate": 1_000_000, "demo:scenario": "unit"},
                "captures": [{"core:sample_start": 0, "core:frequency": 915_000_000}],
                "annotations": [{"core:sample_start": 1, "core:sample_count": 2, "core:label": "qpsk"}],
            }
        ),
        encoding="utf-8",
    )
    return meta, data


def test_parse_sigmf_datatype_width():
    dtype = parse_sigmf_datatype("ci16_le")
    assert dtype.bytes_per_sample == 4
    assert dtype.complex is True


def test_sigmf_inspect_generates_health_report_and_cache(tmp_path):
    meta, _ = write_sigmf_pair(tmp_path)
    cache_dir = tmp_path / ".rfview-cache"

    report = inspect_path(meta, cache_dir=cache_dir, window_samples=4)

    assert report.format == "sigmf"
    assert report.gate == "warn"  # demo namespace is preserved but not configured.
    assert report.summary["sample_count"] == 4
    assert report.stats["annotation_coverage"] == 0.5
    assert report.stats["first_screen"]["window_samples"] == 4
    assert report.cache["stale"] is False
    assert (cache_dir / "clean.json").exists()


def test_sample_window_reader_reads_offset(tmp_path):
    meta, data = write_sigmf_pair(tmp_path)
    dtype = parse_sigmf_datatype("cf32_le")

    samples = read_sigmf_window(data, dtype, sample_start=1, sample_count=2)

    assert samples == [(1.0, 0.0), (-1.0, 0.5)]


def test_annotation_coverage_ignores_intervals_outside_trimmed_data():
    coverage = annotation_coverage([(10, 20), (150, 75), (300, 50)], total_samples=200)

    assert coverage == 0.35


def test_declared_sample_count_must_match_data_file_length(tmp_path):
    meta, _ = write_sigmf_pair(tmp_path)
    doc = json.loads(meta.read_text(encoding="utf-8"))
    doc["global"]["traceability:sample_length"] = 100
    doc["annotations"][0]["core:sample_start"] = 90
    doc["annotations"][0]["core:sample_count"] = 10
    meta.write_text(json.dumps(doc), encoding="utf-8")

    report = inspect_path(meta)
    rule_ids = [issue.rule_id for issue in report.issues]

    assert report.gate == "fail"
    assert "SIGMF_SAMPLE_COUNT_MISMATCH" in rule_ids
    assert "SIGMF_ANNOTATION_OOB" in rule_ids
    assert report.summary["sample_count"] == 4
    assert report.summary["declared_sample_count"] == 100
    assert report.summary["sample_count_matches_data"] is False
    assert report.stats["annotation_coverage"] == 0.0


def test_sigmf_frequency_edges_are_checked_against_capture_center(tmp_path):
    meta, _ = write_sigmf_pair(tmp_path)
    doc = json.loads(meta.read_text(encoding="utf-8"))
    doc["annotations"][0]["core:freq_lower_edge"] = 914_900_000
    doc["annotations"][0]["core:freq_upper_edge"] = 915_100_000
    meta.write_text(json.dumps(doc), encoding="utf-8")

    report = inspect_path(meta)

    assert not any(issue.rule_id == "SIGMF_ANNOTATION_FREQ_OOB" for issue in report.issues)


def test_sigmf_frequency_edges_outside_capture_nyquist_are_reported(tmp_path):
    meta, _ = write_sigmf_pair(tmp_path)
    doc = json.loads(meta.read_text(encoding="utf-8"))
    doc["annotations"][0]["core:freq_lower_edge"] = 913_000_000
    doc["annotations"][0]["core:freq_upper_edge"] = 915_100_000
    meta.write_text(json.dumps(doc), encoding="utf-8")

    report = inspect_path(meta)

    assert any(issue.rule_id == "SIGMF_ANNOTATION_FREQ_OOB" for issue in report.issues)


def test_validator_reports_annotation_out_of_bounds(tmp_path):
    meta, _ = write_sigmf_pair(tmp_path)
    doc = json.loads(meta.read_text(encoding="utf-8"))
    doc["annotations"][0]["core:sample_count"] = 99
    meta.write_text(json.dumps(doc), encoding="utf-8")

    report = inspect_path(meta)

    assert report.gate == "fail"
    assert any(issue.rule_id == "SIGMF_ANNOTATION_OOB" for issue in report.issues)


def test_cache_stale_detects_source_change(tmp_path):
    meta, data = write_sigmf_pair(tmp_path)
    cache = CacheIndex.open(tmp_path / "cache")
    cache.record("asset", [meta, data], {"ok": True})

    assert cache.is_stale("asset") is False
    data.write_bytes(data.read_bytes() + struct.pack("<ff", 0.0, 0.0))
    assert cache.is_stale("asset") is True


def test_cli_returns_nonzero_for_failing_report(tmp_path, capsys):
    missing = tmp_path / "missing.sigmf-meta"
    missing.write_text(json.dumps({"global": {"core:sample_rate": 1}, "captures": [], "annotations": []}), encoding="utf-8")

    code = main(["inspect", str(missing), "--pretty"])
    output = json.loads(capsys.readouterr().out)

    assert code == 1
    assert output["gate"] == "fail"

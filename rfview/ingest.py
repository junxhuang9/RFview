from __future__ import annotations

from pathlib import Path
from typing import Any

from .cache import CacheIndex
from .hdf5 import inspect_hdf5
from .health import HealthReport
from .samples import annotation_coverage, first_screen_stats, read_sigmf_window
from .sigmf import SigMFDocument


def inspect_path(path: str | Path, cache_dir: str | Path | None = None, window_samples: int = 4096) -> HealthReport:
    target = Path(path)
    if target.suffix == ".sigmf-meta" or target.name.endswith(".sigmf-meta"):
        return _inspect_sigmf(target, cache_dir, window_samples)
    if target.suffix.lower() in {".h5", ".hdf5"}:
        return _inspect_hdf5(target, cache_dir)
    report = HealthReport(target.stem, "unknown")
    report.add("error", "IMPORT_UNSUPPORTED", f"Unsupported import target: {target}", "Use a .sigmf-meta, .h5, or .hdf5 file.", str(target))
    return report


def _inspect_sigmf(path: Path, cache_dir: str | Path | None, window_samples: int) -> HealthReport:
    doc = SigMFDocument.load(path)
    report = HealthReport(path.stem.removesuffix(".sigmf-meta"), "sigmf")
    report.summary = doc.summary()
    report.issues = doc.validate()
    total = doc.sample_count_from_file()
    report.stats["annotation_coverage"] = annotation_coverage(
        ((ann.sample_start, ann.sample_count or 0) for ann in doc.annotations), total
    )
    if doc.datatype and doc.data_path.exists() and total:
        count = min(window_samples, total)
        try:
            samples = read_sigmf_window(doc.data_path, doc.datatype, 0, count)
            report.stats["first_screen"] = first_screen_stats(samples, doc.sample_rate, report.stats["annotation_coverage"])
        except ValueError as exc:
            report.add("error", "SIGMF_WINDOW_READ_FAILED", str(exc), "Check datatype and requested sample range.", str(doc.data_path))
    if cache_dir:
        sources: list[Path] = [doc.path]
        if doc.data_path.exists():
            sources.append(doc.data_path)
        report.cache = _record_cache(cache_dir, report.asset_id, sources, {"summary": report.summary, "stats": report.stats})
    return report


def _inspect_hdf5(path: Path, cache_dir: str | Path | None) -> HealthReport:
    hdf = inspect_hdf5(path)
    report = HealthReport(path.stem, "hdf5-radioml")
    report.summary = hdf.radio_summary()
    report.issues = hdf.validate()
    if cache_dir:
        report.cache = _record_cache(cache_dir, report.asset_id, [path], {"summary": report.summary})
    return report


def _record_cache(cache_dir: str | Path, asset_id: str, sources: list[Path], payload: dict[str, Any]) -> dict[str, Any]:
    cache = CacheIndex.open(cache_dir)
    entry = cache.record(asset_id, sources, payload)
    return {"path": str(cache.root / f"{asset_id}.json"), "stale": cache.is_stale(asset_id), "rule_version": entry["rule_version"]}

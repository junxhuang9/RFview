from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any

from .datatypes import SigMFDatatype, parse_sigmf_datatype
from .health import Issue

CORE_PREFIX = "core:"


@dataclass(slots=True)
class CaptureSegment:
    sample_start: int
    metadata: dict[str, Any]


@dataclass(slots=True)
class AnnotationSegment:
    sample_start: int
    sample_count: int | None
    metadata: dict[str, Any]


@dataclass(slots=True)
class SigMFDocument:
    path: Path
    global_meta: dict[str, Any]
    captures: list[CaptureSegment]
    annotations: list[AnnotationSegment]
    raw: dict[str, Any]
    datatype: SigMFDatatype | None = None
    issues: list[Issue] = field(default_factory=list)

    @classmethod
    def load(cls, path: str | Path) -> "SigMFDocument":
        meta_path = Path(path)
        data = json.loads(meta_path.read_text(encoding="utf-8"))
        global_meta = dict(data.get("global") or data.get("core:global") or {})
        captures = [
            CaptureSegment(_int_or_default(item.get("core:sample_start", item.get("sample_start", 0)), 0), dict(item))
            for item in data.get("captures", [])
        ]
        annotations = [
            AnnotationSegment(
                _int_or_default(item.get("core:sample_start", item.get("sample_start", 0)), 0),
                _optional_int(item.get("core:sample_count", item.get("sample_count"))),
                dict(item),
            )
            for item in data.get("annotations", [])
        ]
        doc = cls(meta_path, global_meta, captures, annotations, data)
        dtype = global_meta.get("core:datatype") or global_meta.get("datatype")
        if dtype:
            try:
                doc.datatype = parse_sigmf_datatype(str(dtype))
            except ValueError as exc:
                doc.issues.append(Issue("error", "SIGMF_DATATYPE_UNSUPPORTED", str(exc), "Use a SigMF datatype such as cf32_le or ci16_le.", "global.core:datatype"))
        else:
            doc.issues.append(Issue("error", "SIGMF_DATATYPE_MISSING", "SigMF global metadata is missing core:datatype.", "Add core:datatype to the global object.", "global"))
        return doc

    @property
    def sample_rate(self) -> float | None:
        value = self.global_meta.get("core:sample_rate") or self.global_meta.get("sample_rate")
        return _optional_float(value)

    @property
    def data_path(self) -> Path:
        global_path = self.global_meta.get("core:dataset") or self.global_meta.get("dataset")
        if global_path:
            candidate = Path(str(global_path))
            return candidate if candidate.is_absolute() else self.path.parent / candidate
        stem = self.path.name.removesuffix(".sigmf-meta")
        return self.path.with_name(f"{stem}.sigmf-data")

    def extension_namespaces(self) -> list[str]:
        namespaces: set[str] = set()
        for section in [self.global_meta, *[c.metadata for c in self.captures], *[a.metadata for a in self.annotations]]:
            for key in section:
                if ":" in key and not key.startswith(CORE_PREFIX):
                    namespaces.add(key.split(":", 1)[0])
        return sorted(namespaces)

    def capture_frequency_at(self, sample_start: int) -> float | None:
        if not self.captures:
            return None
        ordered_captures = sorted(self.captures, key=lambda capture: capture.sample_start)
        active = ordered_captures[0]
        for capture in ordered_captures:
            if capture.sample_start > sample_start:
                break
            active = capture
        value = active.metadata.get("core:frequency", active.metadata.get("frequency"))
        return _optional_float(value)

    def sample_count_from_file(self) -> int | None:
        if not self.datatype:
            return None
        data_path = self.data_path
        if not data_path.exists():
            return None
        size = data_path.stat().st_size
        if size % self.datatype.bytes_per_sample:
            return None
        return size // self.datatype.bytes_per_sample

    def declared_sample_count(self) -> int | None:
        """Return the sample length declared by metadata, if present."""
        candidates = (
            self.global_meta.get("core:sample_count"),
            self.global_meta.get("core:num_samples"),
            self.global_meta.get("traceability:sample_length"),
            self.global_meta.get("sample_count"),
        )
        for value in candidates:
            if value is not None:
                return _optional_int(value)
        return None

    def sample_count_matches_data(self) -> bool | None:
        declared = self.declared_sample_count()
        data_samples = self.sample_count_from_file()
        if declared is None or data_samples is None:
            return None
        return declared == data_samples

    def validate(self) -> list[Issue]:
        issues = list(self.issues)
        if self.sample_rate is None:
            issues.append(Issue("error", "SIGMF_SAMPLE_RATE_MISSING", "SigMF global metadata is missing core:sample_rate.", "Add core:sample_rate in samples per second.", "global"))
        data_path = self.data_path
        if not data_path.exists():
            issues.append(Issue("error", "SIGMF_DATA_MISSING", f"SigMF data file does not exist: {data_path}", "Place the .sigmf-data file next to the meta file or set core:dataset.", str(data_path)))
        elif self.datatype and data_path.stat().st_size % self.datatype.bytes_per_sample:
            issues.append(Issue("error", "SIGMF_DATA_SIZE_MISMATCH", "Data file size is not divisible by datatype sample width.", "Verify core:datatype or the binary data file.", str(data_path)))
        starts = [capture.sample_start for capture in self.captures]
        if starts != sorted(starts):
            issues.append(Issue("error", "SIGMF_CAPTURE_ORDER", "Capture sample_start values are not monotonic.", "Sort captures by core:sample_start.", "captures"))
        total_samples = self.sample_count_from_file()
        declared_samples = self.declared_sample_count()
        if declared_samples is not None and total_samples is not None and declared_samples != total_samples:
            issues.append(
                Issue(
                    "error",
                    "SIGMF_SAMPLE_COUNT_MISMATCH",
                    f"Metadata declares {declared_samples} samples but the data file contains {total_samples} samples.",
                    "Make the .sigmf-data byte length match the metadata sample count, or fix the metadata declaration.",
                    "global",
                )
            )
        nyquist = (self.sample_rate / 2.0) if self.sample_rate else None
        for index, ann in enumerate(self.annotations):
            ann_path = f"annotations[{index}]"
            if ann.sample_count is not None and ann.sample_count < 0:
                issues.append(Issue("error", "SIGMF_ANNOTATION_NEGATIVE_LENGTH", "Annotation sample_count is negative.", "Use a non-negative core:sample_count.", ann_path))
            if total_samples is not None and ann.sample_count is not None and ann.sample_start + ann.sample_count > total_samples:
                issues.append(Issue("error", "SIGMF_ANNOTATION_OOB", "Annotation exceeds data file sample range.", "Clamp the annotation or fix the data/sample metadata.", ann_path))
            lower = ann.metadata.get("core:freq_lower_edge", ann.metadata.get("freq_lower"))
            upper = ann.metadata.get("core:freq_upper_edge", ann.metadata.get("freq_upper"))
            if nyquist is not None and (lower is not None or upper is not None):
                center = self.capture_frequency_at(ann.sample_start)
                min_freq = (center - nyquist) if center is not None else -nyquist
                max_freq = (center + nyquist) if center is not None else nyquist
                lower_value = _optional_float(lower)
                upper_value = _optional_float(upper)
                if lower is not None and lower_value is None:
                    issues.append(Issue("error", "SIGMF_ANNOTATION_FREQ_INVALID", "Annotation lower frequency edge is not numeric.", "Use a numeric core:freq_lower_edge value.", ann_path))
                if upper is not None and upper_value is None:
                    issues.append(Issue("error", "SIGMF_ANNOTATION_FREQ_INVALID", "Annotation upper frequency edge is not numeric.", "Use a numeric core:freq_upper_edge value.", ann_path))
                lower_oob = lower_value is not None and not min_freq <= lower_value <= max_freq
                upper_oob = upper_value is not None and not min_freq <= upper_value <= max_freq
                if lower_oob or upper_oob:
                    issues.append(Issue("error", "SIGMF_ANNOTATION_FREQ_OOB", "Annotation frequency edge exceeds capture Nyquist range.", "Keep annotation frequency bounds within the active capture center frequency +/- sample_rate/2.", ann_path))
            if "core:label" not in ann.metadata and "label" not in ann.metadata:
                issues.append(Issue("warning", "SIGMF_ANNOTATION_LABEL_MISSING", "Annotation has no label.", "Add core:label or a project taxonomy label.", ann_path))
        for namespace in self.extension_namespaces():
            issues.append(Issue("warning", "SIGMF_UNKNOWN_NAMESPACE", f"Unknown extension namespace preserved: {namespace}", "Configure a namespace schema when project validation is required.", namespace))
        return issues

    def summary(self) -> dict[str, Any]:
        return {
            "meta_path": str(self.path),
            "data_path": str(self.data_path),
            "datatype": self.datatype.raw if self.datatype else self.global_meta.get("core:datatype"),
            "sample_rate": self.sample_rate,
            "sample_count": self.sample_count_from_file(),
            "declared_sample_count": self.declared_sample_count(),
            "sample_count_matches_data": self.sample_count_matches_data(),
            "captures": len(self.captures),
            "annotations": len(self.annotations),
            "extensions": self.extension_namespaces(),
        }


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _int_or_default(value: Any, default: int) -> int:
    parsed = _optional_int(value)
    return default if parsed is None else parsed


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None

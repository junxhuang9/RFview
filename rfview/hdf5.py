from __future__ import annotations

from dataclasses import dataclass, field
import importlib.util
from pathlib import Path
from typing import Any

from .health import Issue
from .samples import first_screen_stats

HDF5_MAGIC = b"\x89HDF\r\n\x1a\n"


@dataclass(slots=True)
class Hdf5Summary:
    path: Path
    datasets: dict[str, dict[str, Any]] = field(default_factory=dict)
    attrs: dict[str, Any] = field(default_factory=dict)
    issues: list[Issue] = field(default_factory=list)

    @property
    def is_radioml(self) -> bool:
        return {"X", "Y", "Z"}.issubset(self.datasets)

    def validate(self) -> list[Issue]:
        issues = list(self.issues)
        if not self.is_radioml:
            issues.append(Issue("warning", "HDF5_RADIOML_LAYOUT_UNKNOWN", "HDF5 file does not expose root X/Y/Z datasets.", "Configure a project adapter or use RadioML2018-compatible layout.", str(self.path)))
            return issues
        x_shape = self.datasets["X"].get("shape", [])
        y_shape = self.datasets["Y"].get("shape", [])
        z_shape = self.datasets["Z"].get("shape", [])
        if not x_shape or len(x_shape) < 2:
            issues.append(Issue("error", "HDF5_X_SHAPE_INVALID", "RadioML X dataset must be at least 2-dimensional.", "Expected shape like [frames, frame_len, 2].", "X"))
        frames = x_shape[0] if x_shape else None
        if frames is not None and (not y_shape or y_shape[0] != frames or not z_shape or z_shape[0] != frames):
            issues.append(Issue("error", "HDF5_XYZ_FRAME_MISMATCH", "RadioML X/Y/Z frame counts do not match.", "Regenerate or repair the HDF5 label datasets.", "X/Y/Z"))
        if x_shape and x_shape[-1] != 2:
            issues.append(Issue("warning", "HDF5_X_IQ_AXIS_UNKNOWN", "RadioML X last dimension is not 2; I/Q axis may be project-specific.", "Configure adapter axis mapping before exporting RFML slices.", "X"))
        return issues

    def radio_summary(self) -> dict[str, Any]:
        x = self.datasets.get("X", {})
        y = self.datasets.get("Y", {})
        z = self.datasets.get("Z", {})
        return {
            "path": str(self.path),
            "datasets": self.datasets,
            "frames": (x.get("shape") or [None])[0],
            "frame_len": (x.get("shape") or [None, None])[1] if len(x.get("shape") or []) > 1 else None,
            "iq_axis": (x.get("shape") or [None])[-1] if x.get("shape") else None,
            "classes": (y.get("shape") or [None, None])[1] if len(y.get("shape") or []) > 1 else None,
            "snr_shape": z.get("shape"),
        }


def has_hdf5_magic(path: str | Path) -> bool:
    with Path(path).open("rb") as handle:
        return handle.read(len(HDF5_MAGIC)) == HDF5_MAGIC


def inspect_hdf5(path: str | Path) -> Hdf5Summary:
    h5_path = Path(path)
    summary = Hdf5Summary(h5_path)
    if not has_hdf5_magic(h5_path):
        summary.issues.append(Issue("error", "HDF5_MAGIC_INVALID", "File does not have the HDF5 magic header.", "Select a valid .h5/.hdf5 file.", str(h5_path)))
        return summary
    if importlib.util.find_spec("h5py") is None:
        summary.issues.append(Issue("error", "HDF5_READER_MISSING", "h5py is required to inspect HDF5 layouts in this Python runtime.", "Install RFview with the hdf5 extra: pip install '.[hdf5]'.", str(h5_path)))
        return summary
    import h5py  # type: ignore

    with h5py.File(h5_path, "r") as handle:
        def visit(name: str, obj: Any) -> None:
            if hasattr(obj, "shape") and hasattr(obj, "dtype"):
                summary.datasets[name] = {
                    "shape": [int(v) for v in obj.shape],
                    "dtype": str(obj.dtype),
                    "chunks": [int(v) for v in obj.chunks] if obj.chunks else None,
                }
        handle.visititems(visit)
        for key, value in handle.attrs.items():
            summary.attrs[key] = _jsonable(value)
    return summary


def read_radioml_frame_stats(path: str | Path, frame_index: int = 0) -> dict[str, Any]:
    if importlib.util.find_spec("h5py") is None:
        raise RuntimeError("h5py is required to read RadioML frames")
    import h5py  # type: ignore

    with h5py.File(path, "r") as handle:
        frame = handle["X"][frame_index]
        samples = [(float(pair[0]), float(pair[1])) for pair in frame]
        result = first_screen_stats(samples)
        if "Y" in handle:
            y = handle["Y"][frame_index]
            result["label_index"] = int(max(range(len(y)), key=lambda idx: y[idx])) if len(y) else None
        if "Z" in handle:
            z = handle["Z"][frame_index]
            try:
                result["snr_db"] = float(z[0])
            except Exception:
                result["snr_db"] = float(z)
        return result


def _jsonable(value: Any) -> Any:
    if hasattr(value, "tolist"):
        return value.tolist()
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value

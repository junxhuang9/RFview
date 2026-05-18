from __future__ import annotations

from pathlib import Path
import math
import struct
from typing import Iterable

from .datatypes import SigMFDatatype

ComplexSample = tuple[float, float]


def read_sigmf_window(data_path: str | Path, datatype: SigMFDatatype, sample_start: int, sample_count: int) -> list[ComplexSample]:
    if sample_start < 0 or sample_count < 0:
        raise ValueError("sample_start and sample_count must be non-negative")
    path = Path(data_path)
    byte_offset = sample_start * datatype.bytes_per_sample
    byte_count = sample_count * datatype.bytes_per_sample
    if byte_offset + byte_count > path.stat().st_size:
        raise ValueError("requested sample window exceeds data file size")
    with path.open("rb") as handle:
        handle.seek(byte_offset)
        payload = handle.read(byte_count)
    return decode_iq(payload, datatype)


def decode_iq(payload: bytes, datatype: SigMFDatatype) -> list[ComplexSample]:
    if datatype.kind == "f" and datatype.component_bits == 32:
        fmt = ("<" if datatype.endian == "le" else ">") + "f" * (len(payload) // 4)
        values = struct.unpack(fmt, payload)
        return _pair(values) if datatype.complex else [(float(v), 0.0) for v in values]
    if datatype.kind in {"i", "u"}:
        return _decode_int(payload, datatype)
    raise ValueError(f"window reader does not support {datatype.raw}")


def first_screen_stats(samples: list[ComplexSample], sample_rate: float | None = None, annotation_coverage: float | None = None) -> dict[str, object]:
    magnitudes = [math.hypot(i, q) for i, q in samples]
    powers = [i * i + q * q for i, q in samples]
    if not samples:
        return {"window_samples": 0}
    rms = math.sqrt(sum(powers) / len(powers))
    peak = max(magnitudes)
    i_values = [i for i, _ in samples]
    q_values = [q for _, q in samples]
    result: dict[str, object] = {
        "window_samples": len(samples),
        "duration_seconds": (len(samples) / sample_rate) if sample_rate else None,
        "iq_mean": {"i": sum(i_values) / len(i_values), "q": sum(q_values) / len(q_values)},
        "iq_min": {"i": min(i_values), "q": min(q_values)},
        "iq_max": {"i": max(i_values), "q": max(q_values)},
        "rms": rms,
        "peak": peak,
        "papr_db": 10 * math.log10((peak * peak) / (rms * rms)) if rms else None,
        "nan_or_inf": sum(1 for i, q in samples if not math.isfinite(i) or not math.isfinite(q)),
        "psd_preview": psd_preview(samples),
    }
    if annotation_coverage is not None:
        result["annotation_coverage"] = annotation_coverage
    return result


def psd_preview(samples: list[ComplexSample], bins: int = 16) -> list[float]:
    n = min(len(samples), bins)
    if n == 0:
        return []
    preview: list[float] = []
    subset = samples[:n]
    for k in range(n):
        real = 0.0
        imag = 0.0
        for idx, (i_val, q_val) in enumerate(subset):
            angle = -2.0 * math.pi * k * idx / n
            ca, sa = math.cos(angle), math.sin(angle)
            real += i_val * ca - q_val * sa
            imag += i_val * sa + q_val * ca
        preview.append(10.0 * math.log10((real * real + imag * imag) / n + 1e-12))
    return preview


def annotation_coverage(intervals: Iterable[tuple[int, int]], total_samples: int | None) -> float | None:
    if not total_samples:
        return None
    merged: list[tuple[int, int]] = []
    for start, count in sorted((s, c) for s, c in intervals if c > 0):
        end = min(start + count, total_samples)
        if end <= 0:
            continue
        start = max(start, 0)
        if not merged or start > merged[-1][1]:
            merged.append((start, end))
        else:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
    return sum(end - start for start, end in merged) / total_samples


def _decode_int(payload: bytes, datatype: SigMFDatatype) -> list[ComplexSample]:
    endian = "<" if datatype.endian in {"le", "na"} else ">"
    signed = datatype.kind == "i"
    if datatype.component_bits == 8:
        fmt_char = "b" if signed else "B"
        zero = 0 if signed else 127.5
        scale = 128.0 if signed else 127.5
    elif datatype.component_bits == 16:
        fmt_char = "h" if signed else "H"
        zero = 0 if signed else 32767.5
        scale = 32768.0 if signed else 32767.5
    elif datatype.component_bits == 32:
        fmt_char = "i" if signed else "I"
        zero = 0 if signed else 2147483647.5
        scale = 2147483648.0 if signed else 2147483647.5
    else:
        raise ValueError(f"unsupported integer width {datatype.component_bits}")
    fmt = endian + fmt_char * (len(payload) // datatype.bytes_per_component)
    values = [(float(v) - zero) / scale for v in struct.unpack(fmt, payload)]
    return _pair(values) if datatype.complex else [(v, 0.0) for v in values]


def _pair(values: Iterable[float]) -> list[ComplexSample]:
    seq = list(values)
    return [(float(seq[idx]), float(seq[idx + 1])) for idx in range(0, len(seq), 2)]

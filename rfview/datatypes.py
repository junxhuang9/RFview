from __future__ import annotations

from dataclasses import dataclass
import re


@dataclass(frozen=True, slots=True)
class SigMFDatatype:
    raw: str
    kind: str
    component_bits: int
    complex: bool
    endian: str

    @property
    def bytes_per_component(self) -> int:
        return self.component_bits // 8

    @property
    def bytes_per_sample(self) -> int:
        return self.bytes_per_component * (2 if self.complex else 1)


def parse_sigmf_datatype(raw: str) -> SigMFDatatype:
    """Parse common SigMF datatype strings such as cf32_le, ci16_le, cu8, rf32_le."""
    match = re.fullmatch(r"(?P<complex>[cr])(?P<kind>[fiu])(?P<bits>8|16|32|64)(?:_(?P<endian>le|be))?", raw)
    if not match:
        raise ValueError(f"unsupported SigMF datatype: {raw}")
    bits = int(match.group("bits"))
    kind = match.group("kind")
    if bits > 8 and not match.group("endian"):
        raise ValueError(f"datatype {raw} must declare byte order")
    return SigMFDatatype(
        raw=raw,
        kind=kind,
        component_bits=bits,
        complex=match.group("complex") == "c",
        endian=match.group("endian") or "na",
    )

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any

RULE_VERSION = "p1.0"


@dataclass(slots=True)
class CacheIndex:
    root: Path

    @classmethod
    def open(cls, root: str | Path) -> "CacheIndex":
        cache_root = Path(root)
        cache_root.mkdir(parents=True, exist_ok=True)
        return cls(cache_root)

    def fingerprint(self, path: str | Path) -> dict[str, Any]:
        item = Path(path)
        stat = item.stat()
        digest = hashlib.sha256()
        with item.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return {
            "path": str(item),
            "size": stat.st_size,
            "mtime_ns": stat.st_mtime_ns,
            "sha256": digest.hexdigest(),
        }

    def record(self, asset_id: str, sources: list[str | Path], payload: dict[str, Any]) -> dict[str, Any]:
        entry = {
            "asset_id": asset_id,
            "rule_version": RULE_VERSION,
            "sources": [self.fingerprint(source) for source in sources if Path(source).exists()],
            "payload": payload,
        }
        (self.root / f"{asset_id}.json").write_text(json.dumps(entry, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        return entry

    def is_stale(self, asset_id: str) -> bool:
        path = self.root / f"{asset_id}.json"
        if not path.exists():
            return True
        entry = json.loads(path.read_text(encoding="utf-8"))
        if entry.get("rule_version") != RULE_VERSION:
            return True
        for source in entry.get("sources", []):
            current = Path(source["path"])
            if not current.exists():
                return True
            stat = current.stat()
            if stat.st_size != source["size"] or stat.st_mtime_ns != source["mtime_ns"]:
                return True
        return False

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .ingest import inspect_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="rfview", description="RFview P1 SigMF/HDF5 health-report CLI")
    sub = parser.add_subparsers(dest="command", required=True)
    inspect_cmd = sub.add_parser("inspect", help="Inspect a SigMF meta or HDF5/RadioML file")
    inspect_cmd.add_argument("path", type=Path)
    inspect_cmd.add_argument("--cache-dir", type=Path, default=None)
    inspect_cmd.add_argument("--window-samples", type=int, default=4096)
    inspect_cmd.add_argument("--pretty", action="store_true")
    args = parser.parse_args(argv)
    if args.command == "inspect":
        report = inspect_path(args.path, args.cache_dir, args.window_samples)
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2 if args.pretty else None, sort_keys=True))
        return 1 if report.gate == "fail" else 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

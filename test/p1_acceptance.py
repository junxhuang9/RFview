from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_META = REPO_ROOT / "Data" / "trimmedSamples.sigmf-meta"
REPORT_DIR = REPO_ROOT / "test" / "reports"
CACHE_DIR = REPO_ROOT / "test" / ".rfview-cache"
MAX_CAPTURED_OUTPUT = 4000
MAX_REPORTED_ISSUES = 20


def run_command(command: list[str]) -> dict[str, Any]:
    completed = subprocess.run(command, cwd=REPO_ROOT, text=True, capture_output=True, check=False)
    return {
        "command": command,
        "returncode": completed.returncode,
        "stdout_excerpt": completed.stdout[:MAX_CAPTURED_OUTPUT],
        "stdout_truncated": len(completed.stdout) > MAX_CAPTURED_OUTPUT,
        "stderr_excerpt": completed.stderr[:MAX_CAPTURED_OUTPUT],
        "stderr_truncated": len(completed.stderr) > MAX_CAPTURED_OUTPUT,
    }


def summarize_health(report: dict[str, Any]) -> dict[str, Any]:
    issues = report.get("issues", [])
    return {
        "gate": report.get("gate"),
        "format": report.get("format"),
        "summary": report.get("summary", {}),
        "stats": report.get("stats", {}),
        "issue_counts": {
            "error": sum(1 for issue in issues if issue.get("severity") == "error"),
            "warning": sum(1 for issue in issues if issue.get("severity") == "warning"),
            "info": sum(1 for issue in issues if issue.get("severity") == "info"),
        },
        "first_issues": issues[:MAX_REPORTED_ISSUES],
        "issues_truncated": len(issues) > MAX_REPORTED_ISSUES,
    }


def main() -> int:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    started = datetime.now(timezone.utc).isoformat()
    pytest_result = run_command([sys.executable, "-m", "pytest"])

    inspect_command = [
        sys.executable,
        "-m",
        "rfview.cli",
        "inspect",
        str(DATA_META),
        "--cache-dir",
        str(CACHE_DIR),
        "--pretty",
    ]
    completed = subprocess.run(inspect_command, cwd=REPO_ROOT, text=True, capture_output=True, check=False)
    inspect_result = {
        "command": inspect_command,
        "returncode": completed.returncode,
        "stdout_excerpt": completed.stdout[:MAX_CAPTURED_OUTPUT],
        "stdout_truncated": len(completed.stdout) > MAX_CAPTURED_OUTPUT,
        "stderr_excerpt": completed.stderr[:MAX_CAPTURED_OUTPUT],
        "stderr_truncated": len(completed.stderr) > MAX_CAPTURED_OUTPUT,
    }

    health_report: dict[str, Any] | None = None
    health_parse_error: str | None = None
    try:
        health_report = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        health_parse_error = str(exc)

    health_summary = summarize_health(health_report) if health_report else None
    summary = health_report.get("summary", {}) if health_report else {}
    issue_ids = [issue.get("rule_id") for issue in health_report.get("issues", [])] if health_report else []
    declared_samples = summary.get("declared_sample_count")
    data_samples = summary.get("sample_count")
    counts_match = declared_samples == data_samples if declared_samples is not None and data_samples is not None else None
    mismatch_detected = (
        counts_match is False
        and summary.get("sample_count_matches_data") is False
        and "SIGMF_SAMPLE_COUNT_MISMATCH" in issue_ids
        and health_report is not None
        and health_report.get("gate") == "fail"
        and completed.returncode == 1
    )

    acceptance = {
        "started_at": started,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "data_source_policy": "Data/ fixtures are read-only; this program verifies them without modifying Data/.",
        "checks": {
            "pytest": {
                "passed": pytest_result["returncode"] == 0,
                "returncode": pytest_result["returncode"],
            },
            "health_report_parseable": {
                "passed": health_report is not None,
                "parse_error": health_parse_error,
            },
            "meta_data_length_verification": {
                "passed": mismatch_detected,
                "declared_sample_count": declared_samples,
                "data_sample_count": data_samples,
                "sample_count_matches_data": counts_match,
                "expected_issue": "SIGMF_SAMPLE_COUNT_MISMATCH",
            },
            "cli_rejects_invalid_fixture": {
                "passed": completed.returncode == 1 and health_report is not None and health_report.get("gate") == "fail",
                "returncode": completed.returncode,
                "gate": health_report.get("gate") if health_report else None,
            },
        },
        "health_summary": health_summary,
        "raw_commands": {
            "pytest": pytest_result,
            "inspect": inspect_result,
        },
    }
    all_passed = all(check["passed"] for check in acceptance["checks"].values())
    acceptance["passed"] = all_passed

    (REPORT_DIR / "p1_acceptance_latest.json").write_text(json.dumps(acceptance, indent=2, ensure_ascii=False), encoding="utf-8")

    issue_counts = health_summary["issue_counts"] if health_summary else {"error": 0, "warning": 0, "info": 0}
    lines = [
        "# P1 Acceptance Report",
        "",
        f"- Started: {acceptance['started_at']}",
        f"- Finished: {acceptance['finished_at']}",
        f"- Result: {'PASS' if all_passed else 'FAIL'}",
        "- Data policy: Data/ fixtures were read-only during this run.",
        "- Acceptance meaning: PASS means RFview correctly verified the fixture and rejected it when metadata length did not match data length.",
        "",
        "## Commands",
        f"- `{' '.join(pytest_result['command'])}` -> exit {pytest_result['returncode']}",
        f"- `{' '.join(inspect_result['command'])}` -> exit {inspect_result['returncode']}",
        "",
        "## Length Verification",
        f"- Declared sample count: {declared_samples}",
        f"- Data-derived sample count: {data_samples}",
        f"- Match: {counts_match}",
        f"- Required issue present: {'SIGMF_SAMPLE_COUNT_MISMATCH' in issue_ids}",
        "",
        "## Health Summary",
        f"- Gate: {health_report.get('gate') if health_report else None}",
        f"- Errors: {issue_counts['error']}",
        f"- Warnings: {issue_counts['warning']}",
        f"- Info: {issue_counts['info']}",
        "",
        "## Checks",
    ]
    for name, check in acceptance["checks"].items():
        lines.append(f"- [{'x' if check['passed'] else ' '}] {name}")
    if pytest_result["stdout_excerpt"]:
        lines.extend(["", "## Pytest stdout", "```", pytest_result["stdout_excerpt"].strip(), "```"])
    if inspect_result["stderr_excerpt"]:
        lines.extend(["", "## Inspect stderr", "```", inspect_result["stderr_excerpt"].strip(), "```"])
    (REPORT_DIR / "p1_acceptance_latest.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("PASS" if all_passed else "FAIL")
    print(REPORT_DIR / "p1_acceptance_latest.md")
    return 0 if all_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())

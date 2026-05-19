# P1 Acceptance Report

- Started: 2026-05-19T00:33:11.797191+00:00
- Finished: 2026-05-19T00:33:12.729948+00:00
- Result: PASS
- Data policy: Data/ fixtures were read-only during this run.
- Acceptance meaning: PASS means RFview correctly verified the fixture and rejected it when metadata length did not match data length.

## Commands
- `/root/.pyenv/versions/3.12.13/bin/python -m pytest` -> exit 0
- `/root/.pyenv/versions/3.12.13/bin/python -m rfview.cli inspect /workspace/RFview/Data/trimmedSamples.sigmf-meta --cache-dir /workspace/RFview/test/.rfview-cache --pretty` -> exit 1

## Length Verification
- Declared sample count: 22372352
- Data-derived sample count: 166912
- Match: False
- Required issue present: True

## Health Summary
- Gate: fail
- Errors: 3284
- Warnings: 1
- Info: 0

## Checks
- [x] pytest
- [x] health_report_parseable
- [x] meta_data_length_verification
- [x] cli_rejects_invalid_fixture

## Pytest stdout
```
============================= test session starts ==============================
platform linux -- Python 3.12.13, pytest-9.0.3, pluggy-1.6.0
rootdir: /workspace/RFview
configfile: pyproject.toml
testpaths: tests
collected 12 items

tests/test_hdf5_p1.py ..                                                 [ 16%]
tests/test_sigmf_p1.py ..........                                        [100%]

============================== 12 passed in 0.07s ==============================
```

from __future__ import annotations

from pathlib import Path
from typing import Any

from datadiff.dsl import Case
from datadiff.env import collect_environment
from datadiff.oracle import Finding
from datadiff.util import BUGS_DIR, dump_json


def save_bug_artifact(case: Case, raw_results: dict[str, dict[str, Any]], normalized: dict[str, dict[str, Any]], findings: list[Finding]) -> Path:
    sig = findings[0].signature if findings else case.case_id
    bug_dir = BUGS_DIR / f"bug_{sig}"
    bug_dir.mkdir(parents=True, exist_ok=True)
    dump_json(case.to_dict(), bug_dir / "case.json")
    dump_json(raw_results, bug_dir / "results.json")
    dump_json(normalized, bug_dir / "normalized.json")
    dump_json([f.to_dict() for f in findings], bug_dir / "findings.json")
    dump_json(collect_environment(), bug_dir / "environment.json")
    repro = f'''#!/usr/bin/env python3
from datadiff.dsl import Case
from datadiff.runner import run_loaded_case
from datadiff.util import load_json

case = Case.from_dict(load_json(__import__("pathlib").Path(__file__).with_name("case.json")))
result = run_loaded_case(case, backends={list(raw_results)!r}, save_artifact=False)
print(result["status"])
for f in result["findings"]:
    print(f)
'''
    (bug_dir / "reproduce.py").write_text(repro, encoding="utf-8")
    (bug_dir / "report.md").write_text(_bug_report(case, findings), encoding="utf-8")
    return bug_dir


def _bug_report(case: Case, findings: list[Finding]) -> str:
    lines = [f"# Bug Artifact: {case.case_id}", "", f"Seed: `{case.seed}`", "", "## Program", "", "```json"]
    import json
    lines.append(json.dumps(case.program.to_dict(), ensure_ascii=False, indent=2))
    lines.extend(["```", "", "## Findings"])
    for f in findings:
        lines.append(f"- **{f.kind}** severity={f.severity} suspicious={f.suspicious_backends}: {f.evidence}")
    lines.extend(["", "## Reproduce", "", "```bash", "python reproduce.py", "```"])
    lines.extend(["", "## Environment", "", "```json"])
    lines.append(json.dumps(collect_environment(), ensure_ascii=False, indent=2))
    lines.append("```")
    return "\n".join(lines) + "\n"

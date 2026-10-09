"""Scratch-only conflict mutations; run with the installed local-agent Python.

No dependencies installed and no live source edited. JSON artifacts are retained
in the printed external temporary directory, including exact mutant source and
actual assertion-failing node IDs. Survivors are reported, never called kills.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import py_compile
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
LIVE = ROOT / "local-agent/src/vector_agent/reference/comparator.py"


def mutations() -> list[tuple[str, str, str]]:
    guard = "        if applicable_conflicts:\n"
    return [
        ("M01", guard, "        if False:\n"),
        ("M02", "        if conf_domain == prop_domain:\n            return True", "        if conf_domain == prop_domain:\n            return False"),
        ("M03", '    c_clean = re.sub(r"\\[\\d+\\]", "", c_norm)', '    c_clean = c_norm'),
        ("M04", 'for prefix in ("specifications.", "base_specifications."):', 'for prefix in ("base_specifications.",):'),
        ("M05", 'for prefix in ("specifications.", "base_specifications."):', 'for prefix in ("specifications.",):'),
        ("M06", guard, '        if applicable_conflicts and property_path != "sensors.barometer_present":\n'),
        ("M07", guard, '        if applicable_conflicts and property_path != "network.5g_mmwave_supported":\n'),
        ("M08", '                elif candidate_variants:\n', '                elif False:\n'),
        ("M09", '                observed_value=None,\n                reference_value=None,\n                unit=unit,', '                observed_value=None,\n                reference_value=applicable_conflicts[0].source_a_value,\n                unit=unit,'),
        ("M10", '                source_ids=sorted_sources,', '                source_ids=(),'),
        ("M11", '                limitations=tuple(conflict_limitations),', '                limitations=(),'),
        ("M12", 'reference = reference.model_copy(update={"observed_value": int(obs_cores)})', 'reference = reference.model_copy(update={"observed_value": None})'),
        ("M13", '            for c in applicable_conflicts:\n', '            for c in applicable_conflicts[:1]:\n'),
        ("M14", 'if not _property_matches_conflict(property_path, c.field_path):', 'if False:'),
        ("M15", '"targets": {"nfc", "nfc_present"}', '"targets": {"nfc_present"}'),
        ("M16", '            outcome = ComparisonOutcome.INSUFFICIENT_EVIDENCE\n', '            outcome = ComparisonOutcome.REFERENCE_UNAVAILABLE\n'),
        ("G01", '    # Completely unrecognized path: fail closed at entity level\n    return conf_domain not in _KNOWN_DOMAINS', '    # Completely unrecognized path: fail closed at entity level\n    return False'),
        ("G02", '        return not (segments[1] in known_fields or field_part in known_fields)', '        return False'),
        ("G03", 'conf_domain in ("network_configuration", "connectivity")', 'conf_domain in ("network_configuration",)'),
        ("G04", 'or (prop_domain == "network" and conf_domain == "connectivity")', 'or False'),
    ]


PLUGIN = '''
import json
from pathlib import Path
import pytest
import vector_agent.reference.comparator as comparator
assert Path(comparator.__file__).resolve().is_relative_to(Path(__file__).parent.resolve())
failures = []
errors = []
@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    if report.failed:
        target = failures if report.when == "call" and call.excinfo and call.excinfo.errisinstance(AssertionError) else errors
        target.append(report.nodeid)
def pytest_collectreport(report):
    if report.failed:
        errors.append(report.nodeid)
def pytest_sessionfinish(session, exitstatus):
    Path("classification.json").write_text(json.dumps({"assertions": failures, "errors": errors, "exit": int(exitstatus), "import": comparator.__file__}))
'''


def main() -> int:
    before = hashlib.sha256(LIVE.read_bytes()).hexdigest()
    original = LIVE.read_text(encoding="utf-8")
    scratch = Path(tempfile.mkdtemp(prefix="vector-reference-mutations-"))
    print(f"Artifacts: {scratch}", flush=True)
    assert not scratch.resolve().is_relative_to(ROOT)
    results = []
    try:
        for name, old, new in [("CONTROL", "", ""), *mutations()]:
            run = scratch / name
            run.mkdir()
            shutil.copytree(ROOT / "local-agent/src/vector_agent", run / "vector_agent", ignore=shutil.ignore_patterns("__pycache__"))
            shutil.copy2(ROOT / "local-agent/tests/test_phase8e_checkpoint2c.py", run / "test_conflicts.py")
            shutil.copytree(ROOT / "local-agent/tests", run / "tests", ignore=shutil.ignore_patterns("__pycache__"))
            source = original
            if name != "CONTROL":
                if original.count(old) != 1:
                    raise RuntimeError(f"{name}: target count {original.count(old)} != 1")
                source = original.replace(old, new, 1)
            mutant = run / "vector_agent/reference/comparator.py"
            mutant.write_text(source, encoding="utf-8")
            py_compile.compile(str(mutant), doraise=True)
            (run / "mutation_plugin.py").write_text(PLUGIN, encoding="utf-8")
            env = dict(os.environ, PYTHONPATH=str(run), PYTHONDONTWRITEBYTECODE="1", PYTEST_DISABLE_PLUGIN_AUTOLOAD="1")
            proc = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "mutation_plugin", "-p", "no:cacheprovider", "test_conflicts.py"], cwd=run, env=env, capture_output=True, text=True, timeout=120, shell=False)
            (run / "pytest.txt").write_text(proc.stdout + proc.stderr, encoding="utf-8")
            data = json.loads((run / "classification.json").read_text())
            data.update(id=name, source_sha256=hashlib.sha256(mutant.read_bytes()).hexdigest(), old=old, new=new)
            if data["errors"] or proc.returncode not in (0, 1):
                data["result"] = "INVALID"
            elif proc.returncode == 1 and data["assertions"]:
                data["result"] = "KILLED"
            elif proc.returncode == 0:
                data["result"] = "CONTROL_PASS" if name == "CONTROL" else "SURVIVED_OR_EQUIVALENT"
            else:
                data["result"] = "INVALID"
            results.append(data)
            print(name, data["result"], len(data["assertions"]), flush=True)
            assert hashlib.sha256(LIVE.read_bytes()).hexdigest() == before
            if name == "CONTROL" and data["result"] != "CONTROL_PASS":
                raise RuntimeError("Unmutated scratch control failed")
    finally:
        after = hashlib.sha256(LIVE.read_bytes()).hexdigest()
        (scratch / "results.json").write_text(json.dumps(dict(before=before, after=after, results=results), indent=2), encoding="utf-8")
        assert before == after, "Live source changed during mutation run"
    return 0 if all(r["result"] in ("CONTROL_PASS", "KILLED") for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())

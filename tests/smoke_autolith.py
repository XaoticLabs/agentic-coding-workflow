#!/usr/bin/env python3
"""Exercise installed Autolith loading, invocation policy, tools, and Stop gates.

No model or credentials are used. The first run builds the packaged Lisp images
in an isolated, reusable repository-local data directory.
"""

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from workflow_execution import source_state, terminate  # noqa: E402


def lisp_string(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def exercise(output: Path, timeout: int = 600) -> dict:
    checked = source_state(ROOT)
    binary = shutil.which("autolith")
    if not binary:
        raise ValueError("Autolith is unavailable; install the pinned host before this check.")
    output.mkdir(parents=True, exist_ok=True)
    output = output.resolve()
    report = output / "summary.json"
    report.unlink(missing_ok=True)
    with tempfile.TemporaryDirectory(prefix="workflow-autolith-") as scratch:
        temporary = Path(scratch)
        project = temporary / "project"
        project.mkdir()
        (project / ".claude").mkdir()
        (project / ".gitignore").write_text(".claude/\n")
        (project / "README.md").write_text("Autolith verification fixture.\n")
        (project / ".env").write_text("FIXTURE_ONLY=not-a-secret\n")
        (project / ".claude/project-commands.json").write_text(json.dumps({
            "lint": "true", "test": "true", "verify": "test -f accepted.flag",
        }))
        for arguments in (
            ["init", "--quiet", "-b", "main"],
            ["config", "user.name", "Workflow smoke"],
            ["config", "user.email", "workflow@example.invalid"],
            ["add", ".gitignore", "README.md"],
            ["commit", "--quiet", "-m", "test: initial fixture"],
        ):
            subprocess.run(["git", *arguments], cwd=project, check=True, capture_output=True)
        site = temporary / "site"
        site.mkdir()
        initialization = (
            "(handler-case\n"
            "    (progn\n"
            f"      (load {lisp_string(str(ROOT / 'hosts/autolith/init.lisp'))})\n"
            f"      (load {lisp_string(str(ROOT / 'hosts/autolith/smoke.lisp'))})\n"
            f"      (workflow-smoke {lisp_string(str(project) + '/')} "
            f"{lisp_string(str(report))}) (uiop:quit 0))\n"
            "  (error (condition) (format *error-output* \"Workflow smoke failed: ~A~%\" condition) "
            # A handled smoke failure must not invoke Autolith's crash-recovery
            # launcher. Python requires fresh successful evidence independently.
            "(uiop:quit 0)))\n"
        )
        (site / "init.lisp").write_text(initialization)
        job = temporary / "job.sexp"
        job.write_text('(:autolith-job :version 1 :id "workflow-smoke" :role "implementer" '
                       ':prompt "Not executed: initialization exits before inference." '
                       ':input nil :output-contract (:type :object :properties nil '
                       ':required nil :additional-properties nil) :timeout-seconds 30)\n')
        environment = {key: value for key, value in os.environ.items()
                       if not key.startswith(("WORKFLOW_HOST_", "AUTOLITH_"))}
        environment.update({
            "XDG_CONFIG_HOME": str(temporary / "config"),
            "XDG_CACHE_HOME": str(temporary / "cache"),
            "XDG_STATE_HOME": str(temporary / "state"),
            "XDG_DATA_HOME": str(ROOT / ".claude/host-tools/autolith-smoke-data"),
            "WORKFLOW_PYTHON": str(ROOT / ".venv/bin/python"),
            # Native notification boundaries are captured in Lisp. Automated
            # verification must never send live desktop notifications.
            "WORKFLOW_NOTIFY": "false",
            "AUTOLITH_ONBOARDING": "off",
        })
        command = [binary, "--site-config-root", str(site), "--permissions", "auto",
                   "run-job", "--input", str(job), "--output", str(temporary / "result.sexp")]
        (output / "command.json").write_text(json.dumps(command, indent=2) + "\n")
        with (output / "stdout.log").open("w") as stdout, (output / "stderr.log").open("w") as stderr:
            process = subprocess.Popen(command, cwd=project, env=environment,
                                       stdout=stdout, stderr=stderr, start_new_session=True)
            try:
                process.wait(timeout=timeout)
            finally:
                terminate(process)
        if process.returncode:
            raise ValueError(f"Autolith smoke exited {process.returncode}; inspect {output / 'stderr.log'}")
        if not report.is_file():
            raise ValueError("Autolith did not publish native smoke evidence.")
        summary = json.loads(report.read_text())
        if summary.get("model_calls") != 0 or not summary.get("criteria") or not all(summary["criteria"].values()):
            raise ValueError("Autolith smoke evidence is incomplete.")
        evidence = project / ".claude"
        shutil.copytree(evidence, output / "project-evidence", dirs_exist_ok=True)
        after = source_state(ROOT)
        summary.update({"checked": checked, "after": after,
                        "status": "passed" if after == checked else "failed"})
        report.write_text(json.dumps(summary, indent=2) + "\n")
        if after != checked:
            raise ValueError("Repository source changed during Autolith verification.")
        return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / ".claude/proofs/hosts/autolith")
    parser.add_argument("--timeout", type=int, default=600)
    arguments = parser.parse_args()
    try:
        summary = exercise(arguments.output_dir, arguments.timeout)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        parser.exit(1, f"Autolith verification unavailable or failed: {error}\n")
    print(json.dumps({"host": "autolith", "version": summary["version"],
                      "criteria": len(summary["criteria"]),
                      "evidence": str(arguments.output_dir / "summary.json")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

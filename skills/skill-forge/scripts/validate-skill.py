#!/usr/bin/env python3
"""Report local skill structure problems; this does not evaluate behavior.

Usage: validate-skill.py <skill-directory> [--json] [--verbose]
Exit 0: no structural errors; 1: structural errors; 2: unreadable input.
Use `claude plugin validate` for the complete native schema checks and
`claude plugin eval` plus deterministic tests for behavioral evidence.
"""

import argparse
import json
import re
from pathlib import Path


def validate_skill(skill_dir: Path) -> dict:
    findings = []

    def finding(severity: str, message: str) -> None:
        findings.append({"severity": severity, "message": message})

    skill_md = skill_dir / "SKILL.md"
    content = skill_md.read_text(encoding="utf-8")
    lines = content.splitlines()
    if not lines or lines[0] != "---" or "---" not in lines[1:]:
        finding("error", "SKILL.md needs a YAML frontmatter block.")
    else:
        header_end = lines.index("---", 1)
        header = "\n".join(lines[1:header_end])
        # Only check field presence here. Native validation owns YAML/schema
        # semantics; formatting choices are not measures of skill quality.
        for field in ("name", "description"):
            if not re.search(rf"^{field}:[ \t]*\S", header, re.MULTILINE):
                finding("error", f"Missing or empty frontmatter field: {field}.")
        if not "\n".join(lines[header_end + 1 :]).strip():
            finding("error", "SKILL.md has no instructions.")

    # Check explicit local resource paths, including singular reference/ used
    # by older skills. Skip templates and paths assembled at runtime.
    paths = set(re.findall(r"`((?:references?|scripts|assets)/[^`\n]+)`", content))
    paths.update(
        re.findall(r"\]\(((?:references?|scripts|assets)/[^\s)]+)\)", content)
    )
    for resource in sorted(paths):
        if any(character in resource for character in "[]<>${}* "):
            continue
        local_path = resource.split("#", 1)[0]
        if not (skill_dir / local_path).exists():
            finding("error", f"Referenced resource does not exist: {local_path}.")

    scripts = skill_dir / "scripts"
    if scripts.is_dir():
        for script in sorted(scripts.rglob("*")):
            if not script.is_file() or script.suffix not in (".sh", ".py", ".js"):
                continue
            text = script.read_text(encoding="utf-8")
            if not text.strip():
                finding("error", f"Empty script: {script.relative_to(skill_dir)}.")
            elif not text.startswith("#!"):
                finding(
                    "warning",
                    f"Script has no shebang: {script.relative_to(skill_dir)}; "
                    "invoke it with its interpreter or add one.",
                )

    summary = {
        severity: sum(item["severity"] == severity for item in findings)
        for severity in ("error", "warning")
    }
    return {
        "valid": summary["error"] == 0,
        "behavior_evaluated": False,
        "skill_dir": str(skill_dir),
        "findings": findings,
        "summary": summary,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("skill_dir", type=Path)
    parser.add_argument("--json", action="store_true", help="Output diagnostics as JSON")
    parser.add_argument("--verbose", "-v", action="store_true", help="Also show warnings")
    args = parser.parse_args()
    try:
        result = validate_skill(args.skill_dir)
    except (OSError, UnicodeError) as error:
        result = {
            "valid": False,
            "behavior_evaluated": False,
            "error": str(error),
        }
        status = 2
    else:
        status = 0 if result["valid"] else 1

    if args.json:
        print(json.dumps(result, indent=2))
    elif "error" in result:
        print(f"ERROR: {result['error']}")
    else:
        print(f"Structural diagnostics: {args.skill_dir}")
        for item in result["findings"]:
            if item["severity"] == "error" or args.verbose:
                print(f"{item['severity'].upper()}: {item['message']}")
        print(
            f"{result['summary']['error']} errors, "
            f"{result['summary']['warning']} warnings. Behavior has not been evaluated."
        )
    return status


if __name__ == "__main__":
    raise SystemExit(main())

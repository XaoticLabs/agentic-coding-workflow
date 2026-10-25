"""Check actual structural failures without assigning skill quality scores."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = ROOT / "skills/skill-forge/scripts/validate-skill.py"


def diagnose(directory: Path) -> tuple[int, dict]:
    result = subprocess.run(
        [sys.executable, str(VALIDATOR), str(directory), "--json"],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode, json.loads(result.stdout)


def test_short_self_contained_skill_needs_no_boilerplate(tmp_path: Path) -> None:
    (tmp_path / "SKILL.md").write_text(
        "---\nname: summarize\ndescription: Summarize standup notes.\n---\n"
        "Return completed work, next steps, and blockers without inventing facts.\n"
    )
    status, result = diagnose(tmp_path)
    assert status == 0
    assert result["findings"] == []
    assert result["valid"] is True
    assert result["behavior_evaluated"] is False
    assert "score" not in result and "grade" not in result


@pytest.mark.parametrize(
    "content",
    [
        "No frontmatter\n",
        "---\nname: test\n---\nInstructions\n",
        "---\nname: test\ndescription:\nuser-invocable: true\n---\nInstructions\n",
        "---\nname: test\ndescription: Test.\n---\n",
        "---\nname: test\ndescription: Test.\n---\nRead `references/missing.md`.\n",
    ],
)
def test_structural_errors_fail_even_when_the_document_is_present(
    tmp_path: Path, content: str
) -> None:
    (tmp_path / "SKILL.md").write_text(content)
    status, result = diagnose(tmp_path)
    assert status == 1
    assert result["valid"] is False
    assert result["summary"]["error"] > 0


def test_resource_existence_and_script_warnings_are_distinct(tmp_path: Path) -> None:
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts/check.py").write_text("print('checked')\n")
    (tmp_path / "SKILL.md").write_text(
        "---\nname: test\ndescription: Test.\n---\nRun `scripts/check.py`.\n"
    )
    status, result = diagnose(tmp_path)
    assert status == 0
    assert result["summary"] == {"error": 0, "warning": 1}
    (tmp_path / "scripts/check.py").unlink()
    status, result = diagnose(tmp_path)
    assert status == 1
    assert "does not exist" in result["findings"][0]["message"]


def test_unreadable_input_is_not_a_success(tmp_path: Path) -> None:
    status, result = diagnose(tmp_path)
    assert status == 2
    assert result["valid"] is False
    assert result["error"]

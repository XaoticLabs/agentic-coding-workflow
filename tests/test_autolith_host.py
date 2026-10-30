"""Behavioral contracts for generated Autolith resources."""

import importlib.util
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
SPEC = importlib.util.spec_from_file_location("host_render_autolith", ROOT / "scripts/host_render_autolith.py")
RENDERER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RENDERER)


def entry(source: str, body: str = "Follow the project requirements.\n", **changes) -> dict:
    return {"source": source, "body": body, "description": 'Handle "a task" safely.',
            "allowed_tools": ["Read", "Bash"], "user_invocable": True,
            "model_invocable": True, "effort": "medium", "max_turns": 25,
            **changes}


@pytest.fixture
def source_tree(tmp_path: Path) -> tuple[Path, dict]:
    skill = tmp_path / "skills/example"
    (skill / "assets").mkdir(parents=True)
    (skill / "scripts").mkdir()
    (skill / "SKILL.md").write_text("Canonical skill body.\n")
    (skill / "assets/fixture.png").write_bytes(b"\x89PNG\r\n\x1a\nfixture")
    (skill / "scripts/run.sh").write_text("#!/bin/sh\nprintf 'example\\n'\n")
    (skill / "scripts/__pycache__").mkdir()
    (skill / "scripts/__pycache__/run.pyc").write_bytes(b"\x80not source")
    catalog = {
        "schema_version": 1,
        "commands": {
            "implement": entry("commands/implement.md"),
            "ship": entry("commands/ship.md", model_invocable=False),
        },
        "skills": {
            "example": entry("skills/example/SKILL.md"),
            "review-context": entry("skills/review-context/SKILL.md", user_invocable=False),
        },
        "agents": {
            "evaluator": entry("agents/evaluator.md", tools=["Read", "Glob", "Grep"],
                               disallowed_tools=["Bash", "Write", "Edit", "Agent"]),
            "implementer": entry("agents/implementer.md", tools=[], disallowed_tools=[], effort="high"),
            "runtime-verifier": entry("agents/runtime-verifier.md",
                                      tools=["Read", "Glob", "Grep", "Bash"],
                                      disallowed_tools=["Write", "Edit", "Agent"]),
            "test-writer": entry("agents/test-writer.md", tools=[], disallowed_tools=[]),
        },
    }
    return tmp_path, catalog


def test_autolith_keeps_invocation_policy_out_of_unenforced_metadata(source_tree):
    root, catalog = source_tree
    generated = RENDERER.generate(root, catalog)
    assert "hosts/autolith/skills/ship/SKILL.md" not in generated
    assert "hosts/autolith/skills/implement/SKILL.md" in generated
    assert "hosts/autolith/skills/review-context/SKILL.md" in generated
    commands = generated["hosts/autolith/generated/commands.lisp"]
    assert '/workflow-ship"' in commands
    assert '/workflow-example"' in commands
    assert "/workflow-review-context" not in commands
    header = generated["hosts/autolith/skills/implement/SKILL.md"].split("---", 2)[1]
    assert "disable-model-invocation" not in header
    assert "user-invocable" not in header
    assert "allowed-tools:" not in header  # descriptive metadata grants no native permissions


def test_autolith_generation_preserves_resources_and_tracks_canonical_changes(source_tree):
    root, catalog = source_tree
    before = RENDERER.generate(root, catalog)
    assert before["hosts/autolith/skills/example/assets/fixture.png"] == b"\x89PNG\r\n\x1a\nfixture"
    wrapper = before["hosts/autolith/skills/example/scripts/run.sh"]
    assert wrapper.startswith("#!/usr/bin/env bash")
    assert "exec bash" in wrapper and "WORKFLOW_HOST=autolith" in wrapper
    assert "run.sh" in wrapper and "printf 'example" not in wrapper
    assert not any("__pycache__" in name for name in before)
    catalog["commands"]["implement"]["body"] = "New agreed behavior.\n"
    after = RENDERER.generate(root, catalog)
    assert "New agreed behavior." in after["hosts/autolith/skills/implement/SKILL.md"]
    assert before["hosts/autolith/skills/implement/SKILL.md"] != after["hosts/autolith/skills/implement/SKILL.md"]
    assert str(root) not in "\n".join(value for value in after.values() if isinstance(value, str))


def test_autolith_roles_preserve_restrictions_and_effort(source_tree):
    root, catalog = source_tree
    generated = RENDERER.generate(root, catalog)
    evaluator = generated["hosts/autolith/agents/evaluator.sexp"]
    assert ':tools ("resource.read" "search.*")' in evaluator
    assert ":spawns nil" in evaluator
    assert ":reasoning-effort :medium" in evaluator
    implementer = generated["hosts/autolith/agents/implementer.sexp"]
    assert '"shell.run"' in implementer and '"resource.edit"' in implementer
    assert ":reasoning-effort :high" in implementer
    policy = json.loads(generated["hosts/autolith/generated/policy.json"])
    assert policy["evaluator"] == {"tools": ["resource.read", "search.*"], "max_turns": 25, "spawns": []}
    assert policy["implementer"]["spawns"] == ["evaluator", "runtime-verifier", "test-writer"]
    assert "skill.load" in policy["implementer"]["tools"]
    assert "skill.load" in policy["test-writer"]["tools"]
    assert "skill.load" not in policy["runtime-verifier"]["tools"]
    assert policy["test-writer"]["spawns"] == []


def test_canonical_skill_grants_and_denies_propagate_without_role_name_rules(source_tree):
    root, catalog = source_tree
    catalog["agents"]["auditor"] = entry("agents/auditor.md", tools=["Read"], disallowed_tools=[])
    initial = RENDERER.generate(root, catalog)
    initial_policy = json.loads(initial["hosts/autolith/generated/policy.json"])
    assert initial_policy["auditor"]["tools"] == ["resource.read"]
    catalog["agents"]["auditor"]["tools"].append("Skill")
    granted = RENDERER.generate(root, catalog)
    granted_policy = json.loads(granted["hosts/autolith/generated/policy.json"])
    assert "skill.load" in granted_policy["auditor"]["tools"]
    assert '"skill.load"' in granted["hosts/autolith/agents/auditor.sexp"]
    catalog["agents"]["auditor"]["disallowed_tools"].append("Skill")
    denied = RENDERER.generate(root, catalog)
    denied_policy = json.loads(denied["hosts/autolith/generated/policy.json"])
    assert denied_policy["auditor"]["tools"] == initial_policy["auditor"]["tools"]
    assert '"skill.load"' not in denied["hosts/autolith/agents/auditor.sexp"]


def test_explicit_skill_grant_applies_to_existing_restricted_role(source_tree):
    root, catalog = source_tree
    catalog["agents"]["evaluator"]["tools"].append("Skill")
    generated = RENDERER.generate(root, catalog)
    policy = json.loads(generated["hosts/autolith/generated/policy.json"])
    assert policy["evaluator"]["tools"] == ["resource.read", "search.*", "skill.load"]


def test_canonical_denies_override_inherited_skill_and_agent_capabilities(source_tree):
    root, catalog = source_tree
    before = RENDERER.generate(root, catalog)
    assert '"skill.load"' in before["hosts/autolith/agents/implementer.sexp"]
    assert ':spawns ("evaluator" "runtime-verifier" "test-writer")' in before["hosts/autolith/agents/implementer.sexp"]
    catalog["agents"]["implementer"]["disallowed_tools"] = ["Skill", "Agent"]
    after = RENDERER.generate(root, catalog)
    policy = json.loads(after["hosts/autolith/generated/policy.json"])
    assert "skill.load" not in policy["implementer"]["tools"]
    assert policy["implementer"]["spawns"] == []
    assert '"skill.load"' not in after["hosts/autolith/agents/implementer.sexp"]
    assert ":spawns nil" in after["hosts/autolith/agents/implementer.sexp"]


def test_agent_grants_and_restrictions_propagate_to_native_spawn_policy(source_tree):
    root, catalog = source_tree
    catalog["agents"]["test-writer"]["tools"] = ["Read", "Agent"]
    generated = RENDERER.generate(root, catalog)
    policy = json.loads(generated["hosts/autolith/generated/policy.json"])
    assert policy["test-writer"]["spawns"] == ["evaluator", "implementer", "runtime-verifier"]
    catalog["agents"]["test-writer"]["disallowed_tools"] = ["Agent"]
    catalog["agents"]["implementer"]["tools"] = ["Read", "Skill"]
    denied = RENDERER.generate(root, catalog)
    denied_policy = json.loads(denied["hosts/autolith/generated/policy.json"])
    assert denied_policy["test-writer"]["spawns"] == []
    assert denied_policy["implementer"]["spawns"] == []


def test_autolith_lisp_strings_preserve_literal_backslashes_and_newlines():
    text = 'Explain "quoted" paths C:\\code.\nUse literal \\n when necessary.'
    quoted = RENDERER.lisp_string(text)
    assert quoted.startswith('"') and quoted.endswith('"')
    assert '\\"quoted\\"' in quoted
    assert "\n" in quoted
    assert "C:\\\\code" in quoted


def test_autolith_rejects_unrecognized_effort(source_tree):
    root, catalog = source_tree
    catalog["agents"]["evaluator"]["effort"] = "unbounded"
    with pytest.raises(ValueError, match="Unsupported Autolith effort"):
        RENDERER.generate(root, catalog)

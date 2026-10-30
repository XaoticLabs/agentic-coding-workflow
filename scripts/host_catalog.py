#!/usr/bin/env python3
"""Read canonical Claude definitions for deterministic host generation.

YAML is needed only by the development-time synchronizer. Installed adapters
consume the generated JSON catalog and use the standard-library hook bridge.
"""

import hashlib
import json
import re
from pathlib import Path

import yaml

KINDS = {
    "commands": "commands/*.md",
    "skills": "skills/*/SKILL.md",
    "agents": "agents/*.md",
}


class UniqueLoader(yaml.SafeLoader):
    """Reject duplicate metadata instead of silently changing host policy."""


def unique_mapping(loader: UniqueLoader, node: yaml.MappingNode) -> dict:
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=True)
        if not isinstance(key, str) or key in result:
            raise ValueError(f"Duplicate or non-string frontmatter key: {key!r}")
        result[key] = loader.construct_object(value_node, deep=True)
    return result


UniqueLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, unique_mapping
)


def tool_names(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [
            item.strip()
            for item in re.split(r",|\s+(?![^()]*\))", value)
            if item.strip()
        ]
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return value
    raise ValueError("Tool policy must be a string or a list of strings")


def definition(path: Path, root: Path, kind: str) -> tuple[str, dict]:
    text = path.read_text(encoding="utf-8")
    match = re.fullmatch(r"---\r?\n(.*?)\r?\n---(?:\r?\n|$)(.*)", text, re.DOTALL)
    if not match:
        raise ValueError(f"{path}: missing YAML frontmatter")
    metadata = yaml.load(match[1], Loader=UniqueLoader)
    if not isinstance(metadata, dict):
        raise ValueError(f"{path}: metadata must be a mapping")
    name = path.parent.name if kind == "skills" else path.stem
    if metadata.get("name", name) != name or not re.fullmatch(
        r"[a-z0-9]+(?:-[a-z0-9]+)*", name
    ):
        raise ValueError(f"{path}: name must match its source path")
    description = metadata.get("description")
    if not isinstance(description, str) or not description.strip():
        raise ValueError(f"{path}: description is required")
    for key in ("user-invocable", "disable-model-invocation"):
        if key in metadata and not isinstance(metadata[key], bool):
            raise ValueError(f"{path}: {key} must be a Boolean")
    maximum = metadata.get("maxTurns")
    if maximum is not None and (type(maximum) is not int or maximum <= 0):
        raise ValueError(f"{path}: maxTurns must be a positive integer")
    return name, {
        "source": path.relative_to(root).as_posix(),
        "body": match[2],
        "description": description.strip(),
        "allowed_tools": tool_names(metadata.get("allowed-tools")),
        "user_invocable": metadata.get("user-invocable", True),
        "model_invocable": not metadata.get("disable-model-invocation", False),
        "effort": metadata.get("effort"),
        "max_turns": maximum,
        "tools": tool_names(metadata.get("tools")),
        "disallowed_tools": tool_names(metadata.get("disallowedTools")),
        "metadata": metadata,
    }


def build_catalog(root: Path) -> dict:
    catalog = {"schema_version": 1}
    for kind, pattern in KINDS.items():
        entries = dict(
            definition(path, root, kind) for path in sorted(root.glob(pattern))
        )
        catalog[kind] = entries
    overlap = set(catalog["commands"]) & set(catalog["skills"])
    if overlap:
        raise ValueError(f"Commands and skills have duplicate names: {sorted(overlap)}")
    catalog["hooks"] = json.loads((root / "hooks/hooks.json").read_text())
    paths = [root / "hooks/hooks.json"]
    for directory in (
        "commands",
        "skills",
        "agents",
        "references",
        "scripts",
        "hooks",
        "profiles",
        ".claude/rules",
        ".claude-plugin",
    ):
        paths.extend(
            path
            for path in (root / directory).rglob("*")
            if path.is_file()
            and not any(
                part in ("__pycache__", ".pytest_cache", ".ruff_cache")
                for part in path.parts
            )
            and not path.name.endswith(".pyc")
        )
    catalog["sources"] = {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(paths)
    }
    return catalog

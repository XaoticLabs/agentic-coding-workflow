#!/usr/bin/env python3
"""Select models consistently without overriding the user's native default."""

import argparse
import json
import os
from collections.abc import Mapping

ROLES = ("build", "evaluator", "merge")
VARIABLES = tuple(f"WORKFLOW_{role.upper()}_MODEL" for role in ROLES) + (
    "WORKFLOW_MODEL",
    "ANTHROPIC_MODEL",
)


def selection(role: str, environment: Mapping[str, str] | None = None) -> dict:
    if role not in ROLES:
        raise ValueError(f"Unknown model role: {role}")
    environment = os.environ if environment is None else environment
    for key in (f"WORKFLOW_{role.upper()}_MODEL", "WORKFLOW_MODEL", "ANTHROPIC_MODEL"):
        value = environment.get(key, "")
        if not value:
            continue
        if value.startswith("-") or any(
            character.isspace() or ord(character) < 32 for character in value
        ):
            raise ValueError(
                f"{key} must be a single model selector or provider model ID"
            )
        return {"role": role, "requested": value, "source": key}
    return {"role": role, "requested": None, "source": "native_configuration"}


def model_arguments(role: str) -> list[str]:
    model = selection(role)["requested"]
    return ["--model", model] if model else []


def observed_models(envelope: dict) -> list[str]:
    usage = envelope.get("modelUsage", {})
    models = set(usage) if isinstance(usage, dict) else set()
    if isinstance(envelope.get("model"), str):
        models.add(envelope["model"])
    return sorted(model for model in models if isinstance(model, str) and model)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("role", choices=ROLES)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        selected = selection(args.role)
    except ValueError as error:
        parser.error(str(error))
    print(json.dumps(selected) if args.json else selected["requested"] or "")


if __name__ == "__main__":
    main()

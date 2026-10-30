#!/usr/bin/env python3
"""Regenerate Pi and Autolith from canonical Claude sources; --check detects drift."""

import argparse
import hashlib
import importlib
import json
from pathlib import Path
import sys

from host_catalog import build_catalog

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = "hosts/generated-files.json"


def generated_files(root: Path) -> dict[str, str | bytes]:
    catalog = build_catalog(root)
    files = {
        "hosts/catalog.json": json.dumps(catalog, indent=2, ensure_ascii=False) + "\n"
    }
    for host in ("pi", "autolith"):
        module = importlib.import_module(f"host_render_{host}")
        output = module.generate(root, catalog)
        if files.keys() & output.keys():
            raise ValueError(f"{host} generator overwrote another generated file")
        files.update(output)
    for name, value in files.items():
        path = Path(name)
        if (
            not name.startswith("hosts/")
            or path.is_absolute()
            or ".." in path.parts
            or not isinstance(value, (str, bytes))
        ):
            raise ValueError(f"Unsafe generated output: {name}")
    files[MANIFEST] = (
        json.dumps(
            {
                "schema_version": 1,
                "files": {
                    name: hashlib.sha256(
                        value.encode() if isinstance(value, str) else value
                    ).hexdigest()
                    for name, value in sorted(files.items())
                },
            },
            indent=2,
        )
        + "\n"
    )
    return files


def synchronize(root: Path, check: bool = False) -> list[str]:
    files = generated_files(root)
    previous = (
        json.loads((root / MANIFEST).read_text())["files"]
        if (root / MANIFEST).is_file()
        else {}
    )
    stale = set(previous) - set(files)
    differences = []
    for name, content in sorted(files.items()):
        path = root / name
        if not path.parent.resolve().is_relative_to((root / "hosts").resolve()):
            raise ValueError(f"Generated parent escapes hosts/: {name}")
        data = content.encode() if isinstance(content, str) else content
        executable = data.startswith(b"#!") and path.suffix in (".py", ".sh")
        if (
            path.is_symlink()
            or not path.is_file()
            or path.read_bytes() != data
            or (executable and not path.stat().st_mode & 0o111)
        ):
            differences.append(name)
            if not check:
                path.parent.mkdir(parents=True, exist_ok=True)
                temporary = path.with_name(path.name + ".sync-tmp")
                # Replacing the output also replaces an unexpected file symlink;
                # synchronization can never write through it into Claude sources.
                temporary.unlink(missing_ok=True)
                temporary.write_bytes(data)
                temporary.chmod(0o755 if executable else 0o644)
                temporary.replace(path)
    for name in sorted(stale):
        path = Path(name)
        if not name.startswith("hosts/") or path.is_absolute() or ".." in path.parts:
            raise ValueError(f"Unsafe previous generated output: {name}")
        differences.append(name)
        if not check:
            (root / path).unlink(missing_ok=True)
    return differences


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    try:
        differences = synchronize(ROOT, args.check)
    except (ValueError, OSError, ImportError) as error:
        print(f"Host synchronization failed: {error}", file=sys.stderr)
        return 2
    if args.check and differences:
        print(
            "Generated host resources are stale; run maak sync-hosts:\n"
            + "\n".join(differences),
            file=sys.stderr,
        )
        return 1
    print(
        f"Host resources {'are current' if args.check else 'synchronized'} ({len(differences)} files changed)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

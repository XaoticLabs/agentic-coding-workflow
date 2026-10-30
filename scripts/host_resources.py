#!/usr/bin/env python3
"""Preserve skill resources while executable entrypoints run at canonical paths."""

import os
from pathlib import Path
import shlex


def supporting_files(
    root: Path, source: str, destination: str, host: str
) -> dict[str, str | bytes]:
    outputs = {}
    source_directory = (root / source).parent
    for resource in sorted(source_directory.rglob("*")):
        relative = resource.relative_to(source_directory)
        if (
            not resource.is_file()
            or resource.name == "SKILL.md"
            or any(
                part in ("__pycache__", ".pytest_cache", ".ruff_cache")
                for part in relative.parts
            )
        ):
            continue
        name = f"{destination}/{relative.as_posix()}"
        content = resource.read_bytes()
        if content.startswith(b"#!") and resource.suffix in (".py", ".sh"):
            target = os.path.relpath(resource, (root / name).parent)
            if resource.suffix == ".py":
                outputs[name] = (
                    '#!/usr/bin/env python3\n"""Generated canonical-script entrypoint; edit the original skill."""\n'
                    "import os\nfrom pathlib import Path\nimport sys\n"
                    f"_workflow_source = (Path(__file__).resolve().parent / {target!r}).resolve()\n"
                    f"os.environ['WORKFLOW_HOST'] = {host!r}\n"
                    "if __name__ == '__main__':\n"
                    "    os.execv(sys.executable, [sys.executable, str(_workflow_source), *sys.argv[1:]])\n"
                    "else:\n"
                    "    __file__ = str(_workflow_source)\n"
                    "    sys.path.insert(0, str(_workflow_source.parent))\n"
                    "    exec(compile(_workflow_source.read_bytes(), __file__, 'exec'), globals())\n"
                )
            else:
                outputs[name] = (
                    "#!/usr/bin/env bash\n# Generated canonical-script entrypoint; edit the original skill.\n"
                    '_WORKFLOW_RESOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"\n'
                    f"export WORKFLOW_HOST={shlex.quote(host)}\n"
                    f'exec bash "${{_WORKFLOW_RESOURCE_DIR}}"/{shlex.quote(target)} "$@"\n'
                )
        else:
            outputs[name] = content
    return outputs

# Repository development

Read [CLAUDE.md](CLAUDE.md) for the plugin architecture and development policy.

Run `make setup` to create or synchronize the locked development environment.
Run `make check` before completing a change; `make lint` and `make test` run its
individual checks. CI and `.claude/project-commands.json` use these same tasks.
Use the project environment for Python tools rather than the global interpreter.
See [README.md](README.md#validation-and-maintenance) for prerequisites, focused
tests, dependency updates, and optional native plugin validation.

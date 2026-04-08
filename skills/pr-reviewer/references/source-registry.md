# Source Registry — Authoritative References for Code Review

Verified, linkable sources organized by PERFECT phase. Use these to ground review findings with citations. Load this file when you need to look up a source URL for a finding.

## Deep-Link Patterns

For linking to specific rules in review comments:

| Tool/DB | URL Pattern | Example |
|---------|-------------|---------|
| Ruff | `https://docs.astral.sh/ruff/rules/{rule-name}/` | `.../ruff/rules/asyncio-dangling-task/` |
| basedpyright | `https://docs.basedpyright.com/latest/configuration/config-files/#type-check-rule-overrides` | basedpyright error codes |
| Pydantic | `https://docs.pydantic.dev/latest/concepts/{topic}/` | `.../concepts/validators/` |
| CWE | `https://cwe.mitre.org/data/definitions/{ID}.html` | `.../definitions/89.html` (SQL injection) |
| OWASP Top 10 | `https://owasp.org/Top10/2021/A{NN}_2021-{Name}/` | `.../A03_2021-Injection/` |
| Refactoring | `https://refactoring.com/catalog/{name}.html` | `.../catalog/extractMethod.html` |
| PEP | `https://peps.python.org/pep-{NNNN}/` | `.../pep-0008/` |

---

## Evidence Phase

| Source | URL | Covers | Lang |
|--------|-----|--------|------|
| Martin Fowler — Practical Test Pyramid | https://martinfowler.com/articles/practical-test-pyramid.html | Unit/integration/E2E ratios, when to use each | Agnostic |
| Martin Fowler — Test Pyramid | https://martinfowler.com/bliki/TestPyramid.html | Canonical test pyramid concept | Agnostic |
| Martin Fowler — Software Testing Guide | https://martinfowler.com/testing/ | Index of testing articles (mocks, stubs, doubles) | Agnostic |
| pytest Documentation | https://docs.pytest.org/en/stable/ | Fixtures, parametrize, markers, assertions | Python |
| pytest How-To Guides | https://docs.pytest.org/en/stable/how-to/index.html | Practical testing patterns | Python |
| Hypothesis Documentation | https://hypothesis.readthedocs.io/ | Property-based testing, strategies, shrinking | Python |
| Hypothesis Strategies Reference | https://hypothesis.readthedocs.io/en/latest/data.html | Built-in data generators | Python |
| basedpyright Documentation | https://docs.basedpyright.com/ | Type checker, strict mode, enhanced pyright | Python |
| Pyright Documentation | https://microsoft.github.io/pyright/ | Type checker configuration, error codes | Python |
| PEP 484 — Type Hints | https://peps.python.org/pep-0484/ | Type annotation standard | Python |
| PEP 695 — Type Parameter Syntax | https://peps.python.org/pep-0695/ | Modern type parameter syntax (3.12+) | Python |
| Pydantic Documentation | https://docs.pydantic.dev/latest/ | Data validation, serialization, settings | Python |
| Pydantic Migration Guide | https://docs.pydantic.dev/latest/migration/ | v1 → v2 migration patterns | Python |
| ExUnit Documentation | https://hexdocs.pm/ex_unit/ExUnit.html | Assertions, async tests, callbacks, doctests | Elixir |
| StreamData Documentation | https://hexdocs.pm/stream_data/StreamData.html | Data generators, shrinking | Elixir |
| StreamData ExUnitProperties | https://hexdocs.pm/stream_data/ExUnitProperties.html | Property-based test macros | Elixir |

---

## Reliability Phase

| Source | URL | Covers | Lang |
|--------|-----|--------|------|
| OWASP Top 10 (2021) | https://owasp.org/Top10/2021/ | 10 most critical web app security risks | Agnostic |
| OWASP Cheat Sheet Series | https://cheatsheetseries.owasp.org/index.html | Actionable cheat sheets (auth, crypto, input validation) | Agnostic |
| OWASP Cheat Sheets by Top 10 | https://cheatsheetseries.owasp.org/IndexTopTen.html | Maps cheat sheets to OWASP Top 10 categories | Agnostic |
| SEI CERT Secure Coding | https://wiki.sei.cmu.edu/confluence/display/seccode/SEI+CERT+Coding+Standards | Language-specific secure coding rules | Agnostic |
| Microsoft SDL | https://www.microsoft.com/en-us/securityengineering/sdl | Security development lifecycle | Agnostic |
| Microsoft SDL Practices | https://www.microsoft.com/en-us/securityengineering/sdl/practices | 10 specific SDL practices | Agnostic |
| CWE Top 25 | https://cwe.mitre.org/top25/ | Ranked dangerous weaknesses | Agnostic |
| CWE Full Database | https://cwe.mitre.org/data/ | Searchable weakness catalog | Agnostic |
| Bandit (Python Security Linter) | https://bandit.readthedocs.io/en/latest/ | Shell injection, hardcoded passwords, insecure deserialization | Python |
| Django Security Guide | https://docs.djangoproject.com/en/5.1/topics/security/ | XSS, CSRF, SQL injection, clickjacking | Python |
| Django Deployment Checklist | https://docs.djangoproject.com/en/5.1/howto/deployment/checklist/ | Security settings for production | Python |
| FastAPI Security Tutorial | https://fastapi.tiangolo.com/tutorial/security/ | OAuth2, JWT, HTTP Basic patterns | Python |
| Sobelow (Phoenix Security) | https://github.com/nccgroup/sobelow | XSS, SQL injection, directory traversal, CSRF | Elixir |
| Erlang/OTP Supervisor | https://www.erlang.org/doc/apps/stdlib/supervisor.html | Restart strategies, max intensity | Elixir |
| Erlang/OTP GenServer | https://www.erlang.org/doc/apps/stdlib/gen_server.html | Process lifecycle, timeout handling | Elixir |

---

## Form Phase

| Source | URL | Covers | Lang |
|--------|-----|--------|------|
| Refactoring Catalog (Fowler) | https://refactoring.com/catalog/ | Named refactorings with code examples | Agnostic |
| Refactoring.guru — Design Patterns | https://refactoring.guru/design-patterns/catalog | Creational, structural, behavioral patterns | Agnostic |
| Refactoring.guru — Code Smells | https://refactoring.guru/refactoring/catalog | Code smells and refactoring remedies | Agnostic |
| Google Engineering Practices | https://google.github.io/eng-practices/review/ | Design review, complexity, naming, style | Agnostic |
| PEP 8 — Python Style Guide | https://peps.python.org/pep-0008/ | Naming, layout, imports, whitespace | Python |
| PEP 20 — Zen of Python | https://peps.python.org/pep-0020/ | 19 guiding aphorisms | Python |
| Google Python Style Guide | https://google.github.io/styleguide/pyguide.html | Docstrings, formatting, imports, types | Python |
| Ruff Rules Reference | https://docs.astral.sh/ruff/rules/ | 800+ lint rules (replaces flake8, pylint, isort, etc.) | Python |
| Ruff Linter Overview | https://docs.astral.sh/ruff/linter/ | Rule categories, configuration | Python |
| Ruff Formatter | https://docs.astral.sh/ruff/formatter/ | Code formatting (replaces Black) | Python |
| uv Documentation | https://docs.astral.sh/uv/ | Package management, virtual environments, tool running | Python |
| Elixir Style Guide (Adams) | https://github.com/christopheradams/elixir_style_guide | Community style conventions | Elixir |
| Credo Documentation | https://hexdocs.pm/credo/overview.html | Consistency, readability, refactoring checks | Elixir |
| Credo GitHub | https://github.com/rrrene/credo | Check source code, custom checks | Elixir |
| Elixir Official Docs | https://hexdocs.pm/elixir/introduction.html | Module structure, naming, doc conventions | Elixir |
| Elixir Getting Started | https://elixir-lang.org/getting-started/ | Idiomatic patterns, OTP design, Mix | Elixir |
| Elixir Library Guidelines | https://hexdocs.pm/elixir/library-guidelines.html | API design, anti-patterns | Elixir |

---

## Clarity Phase

| Source | URL | Covers | Lang |
|--------|-----|--------|------|
| Google — How to Write Review Comments | https://google.github.io/eng-practices/review/reviewer/comments.html | Tone, constructive feedback | Agnostic |
| Google — Navigating a CL | https://google.github.io/eng-practices/review/reviewer/navigate.html | How to read code for understanding | Agnostic |
| PEP 8 — Naming Conventions | https://peps.python.org/pep-0008/#naming-conventions | Python naming rules | Python |
| PEP 257 — Docstring Conventions | https://peps.python.org/pep-0257/ | How to write Python docstrings | Python |
| Google Python — Comments | https://google.github.io/styleguide/pyguide.html#38-comments-and-docstrings | Docstrings, inline comments, TODO | Python |
| Real Python | https://realpython.com/ | Clean code, documentation, naming guides | Python |
| Elixir — Writing Documentation | https://hexdocs.pm/elixir/writing-documentation.html | @moduledoc, @doc, doctests | Elixir |
| Credo Readability Checks | https://hexdocs.pm/credo/overview.html | Module doc, function length, pipe chains | Elixir |

---

## Edge Cases Phase

| Source | URL | Covers | Lang |
|--------|-----|--------|------|
| CWE Top 25 | https://cwe.mitre.org/top25/ | Weaknesses from missed edge cases | Agnostic |
| CWE Full Database | https://cwe.mitre.org/data/ | Searchable weakness types by CWE ID | Agnostic |
| Hypothesis | https://hypothesis.readthedocs.io/ | Auto-generates edge-case inputs | Python |
| Hypothesis Strategies | https://hypothesis.readthedocs.io/en/latest/data.html | Custom generators for edge cases | Python |
| StreamData ExUnitProperties | https://hexdocs.pm/stream_data/ExUnitProperties.html | Property-based edge case discovery | Elixir |
| Ecto.Changeset | https://hexdocs.pm/ecto/Ecto.Changeset.html | Validation, casting, constraint handling | Elixir |
| Erlang/OTP Design Principles | https://www.erlang.org/doc/system/design_principles.html | Fault isolation, supervision strategies | Elixir |
| Python Security Considerations | https://docs.python.org/3/library/security_warnings.html | Modules with known edge cases | Python |

---

## Purpose Phase

| Source | URL | Covers | Lang |
|--------|-----|--------|------|
| Google — What to Look For | https://google.github.io/eng-practices/review/reviewer/looking-for.html | Functionality, design, complexity | Agnostic |
| Google — The Standard | https://google.github.io/eng-practices/review/reviewer/standard.html | When to approve, progress vs perfection | Agnostic |
| Phoenix Framework Guides | https://hexdocs.pm/phoenix/overview.html | Canonical Phoenix patterns | Elixir |
| Ecto Documentation | https://hexdocs.pm/ecto/Ecto.html | Schemas, changesets, queries | Elixir |
| FastAPI Documentation | https://fastapi.tiangolo.com/ | Canonical FastAPI patterns | Python |
| Django Documentation | https://docs.djangoproject.com/en/5.1/ | Canonical Django patterns | Python |

---

## Taste Phase

| Source | URL | Covers | Lang |
|--------|-----|--------|------|
| Google — Handling Pushback | https://google.github.io/eng-practices/review/reviewer/pushback.html | When to insist vs defer on subjective issues | Agnostic |
| Martin Fowler — Refactoring (tagged) | https://martinfowler.com/tags/refactoring.html | Opinionated articles on code quality | Agnostic |
| PEP 20 — Zen of Python | https://peps.python.org/pep-0020/ | "Beautiful is better than ugly" | Python |
| Dashbit Blog | https://dashbit.co/blog | Opinionated Elixir best practices (core team) | Elixir |
| Elixir Forum | https://elixirforum.com/ | Community consensus on idiomatic Elixir | Elixir |
| Real Python | https://realpython.com/ | Opinionated best practice guides | Python |
| Google Python Style Guide | https://google.github.io/styleguide/pyguide.html | Opinionated choices beyond PEP 8 | Python |

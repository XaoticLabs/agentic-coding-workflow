# PERFECT Code Review Framework

Structured review framework based on [bastrich.tech/perfect-code-review](https://bastrich.tech/perfect-code-review/). Phases are ordered bottom-up: automated gates first, human judgment last.

## The Pyramid (Review Bottom-Up)

### 1. Evidence (Fully Automated Gate)

**Does the code pass all automated checks?**

- [ ] All tests pass (unit, integration, E2E)
- [ ] CI pipeline is green
- [ ] Formatting/linting passes (`mix format`, `ruff`, etc.)
- [ ] Static analysis passes (`dialyzer`, `basedpyright`, `credo`)
- [ ] No new compiler warnings

**Stop here if Evidence fails.** Do not proceed to human review until automated checks are green. Severity: **BLOCKER**.

AI role: Fully automated — run tools, report results.
Human role: None.

---

### 2. Reliability (Mostly Automated)

**Does the code have performance or security issues?**

- [ ] No hardcoded secrets, credentials, or API keys
- [ ] User input is validated and sanitized at system boundaries
- [ ] SQL queries use parameterized inputs, not string concatenation
- [ ] No unsafe deserialization (`pickle`, `:erlang.binary_to_term` with untrusted input)
- [ ] Authentication/authorization checks are present where needed
- [ ] Time/space complexity is reasonable for expected data sizes
- [ ] No N+1 query patterns
- [ ] No unbounded memory growth (infinite streams, missing pagination)
- [ ] Cache invalidation is handled correctly
- [ ] Concurrent access is safe (race conditions, deadlocks)

Severity: **MAJOR**. Escalate to BLOCKER for confirmed security vulnerabilities.

AI role: Run security scanners (Bandit/Sobelow), flag complexity issues, cite OWASP/CWE.
Human role: Verify flagged performance impacts in context.

---

### 3. Form (Mostly Automated)

**Does the code align with design principles and codebase conventions?**

- [ ] Follows existing patterns in the codebase (search before flagging!)
- [ ] High cohesion / low coupling — modules have single responsibilities
- [ ] No unnecessary abstractions or premature generalization
- [ ] Import ordering follows project conventions
- [ ] Module/file structure follows project layout
- [ ] Error handling follows established patterns (not over-defensive)
- [ ] Public API surface is intentional (no accidental exposure)

Severity: **MAJOR** for pattern deviations, **MINOR** for style.

AI role: Grep for existing patterns, run Ruff/Credo, cite style guides.
Human role: Minimal — this is the AI's strongest area.

---

### 4. Clarity (AI-Assisted)

**Does the code clearly communicate its intent?**

- [ ] Variable/function names are self-documenting
- [ ] Functions are short enough to understand at a glance
- [ ] Comments explain "why" not "what" (no parroting the code)
- [ ] Complex logic has explanatory comments or is decomposed
- [ ] File/module organization supports diagonal reading
- [ ] Public functions have documentation (@doc, docstrings)
- [ ] No dead code, commented-out code, or TODO debris

Severity: **MINOR**.

AI role: Flag unclear naming, excessive function length, missing docs.
Human role: Validate — readability is ultimately a human judgment.

---

### 5. Edge Cases (AI Flags, Human Validates)

**Are boundary conditions and failure modes handled?**

- [ ] Nil/None/null inputs handled where they can occur
- [ ] Empty collections handled (empty list, empty map, empty string)
- [ ] Boundary values tested (0, -1, max int, empty, single element)
- [ ] Error paths return meaningful errors (not silent failures)
- [ ] External service failures handled (timeouts, retries, circuit breakers)
- [ ] Race conditions under concurrent access
- [ ] Unicode/encoding edge cases for string processing
- [ ] Timezone handling for datetime operations

Severity: **BLOCKER** for crash-causing gaps, **MAJOR** for degraded behavior.

AI role: Flag candidates with specific locations. Cite CWE IDs where applicable.
Human role: Decide which edge cases are realistic vs theoretical.

---

### 6. Purpose (Human-Driven, AI Assists)

**Does the code solve the stated task?**

- [ ] PR description/ticket matches what the code actually does
- [ ] No scope creep (changes unrelated to stated purpose)
- [ ] No missing implementation (stated goals not addressed in diff)
- [ ] The approach is appropriate for the problem (not over/under-engineered)
- [ ] Breaking changes are documented and intentional

Severity: **BLOCKER**.

AI role: Summarize PR intent vs diff, flag mismatches and scope creep.
Human role: Final judgment — only a human can decide if the code fulfills its purpose.

---

### 7. Taste (Human Only, Non-Blocking)

**Personal preferences and subjective quality.**

- Alternative approaches worth considering
- Stylistic preferences beyond established conventions
- "I would have done it differently" observations
- Suggestions that may evolve into team conventions

Severity: **NITPICK** only. Must never block a merge.

AI role: None — taste is explicitly human territory.
Human role: Note preferences, clearly labeled as non-blocking.

---

## Severity Mapping

| Phase | Default Severity | Escalation Trigger |
|-------|-----------------|-------------------|
| Evidence | BLOCKER | N/A — always blocks |
| Reliability | MAJOR | Confirmed security vuln → BLOCKER |
| Form | MAJOR / MINOR | Breaking public API → BLOCKER |
| Clarity | MINOR | Misleading names causing bugs → MAJOR |
| Edge Cases | BLOCKER / MAJOR | Crash-causing → BLOCKER, degraded → MAJOR |
| Purpose | BLOCKER | N/A — wrong code is always a blocker |
| Taste | NITPICK | Never escalates |

## Confidence Levels

Every finding must be tagged with a confidence level:

| Level | Meaning | Source Required | Scored in Learn Mode? |
|-------|---------|----------------|----------------------|
| **Verified** | Backed by authoritative source URL or repo pattern match | Yes — URL or grep proof | Yes |
| **Likely** | Strong signal from tool output or obvious code smell | Tool output or clear pattern | Yes |
| **Uncertain** | AI judgment call, no supporting evidence | None found | No |

For Uncertain findings: attempt verification via WebSearch before presenting. If still unverified, tag as Uncertain and present transparently.

## Citation Format

```markdown
Per [OWASP A03:2021 - Injection](https://owasp.org/Top10/2021/A03_2021-Injection/),
user input should be parameterized rather than concatenated into queries.
```

Always cite sources inline with the finding.

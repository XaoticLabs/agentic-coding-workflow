# PERFECT Code Review Framework

Structured review framework based on [bastrich.tech/perfect-code-review](https://bastrich.tech/perfect-code-review/). Phases are ordered bottom-up: automated checks first, human judgment last. Failed or unavailable checks do not stop useful code inspection.

## The Pyramid (Review Bottom-Up)

### 1. Evidence (Automated Checks)

**Does the code pass all automated checks?**

- [ ] All tests pass (unit, integration, E2E)
- [ ] CI pipeline is green
- [ ] Formatting/linting passes (`mix format`, `ruff`, etc.)
- [ ] Static analysis passes (`dialyzer`, `basedpyright`, `credo`)
- [ ] No new compiler warnings

Record commands, outcomes, relevant output, and verification scope, then continue the remaining phases and independent checks. Distinguish a check that ran and failed from one that could not run because dependencies, credentials, services, tools, or CI access were unavailable. Confirmed required-check failures remain merge **BLOCKER**s; unavailable checks are verification limitations, not proof of a code defect. Report incomplete verification and the checks still needed. Continuing inspection does not waive required merge checks.

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

AI role: Run available security scanners (Bandit/Sobelow) and trace reachable inputs through guards to sensitive operations. Establish concrete impacts with repository evidence or reproduction; OWASP/CWE references may explain the weakness class.
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

Severity: **MAJOR** for demonstrated design or compatibility problems, **MINOR** for evidenced convention violations. Personal preferences belong in Taste.

AI role: Search existing patterns, repository rules, and configured Ruff/Credo checks. Explain the concrete compatibility or maintenance consequence; a style guide or pattern difference alone does not establish a defective abstraction.
Human role: Minimal — this is the AI's strongest area.

---

### 4. Clarity (AI-Assisted)

**Does the code clearly communicate its intent?**

- [ ] Variable/function names are self-documenting
- [ ] Functions have clear responsibilities and readable control flow
- [ ] Comments explain "why" not "what" (no parroting the code)
- [ ] Complex logic has explanatory comments or is decomposed
- [ ] File/module organization supports diagonal reading
- [ ] Public functions have documentation (@doc, docstrings)
- [ ] No dead code, commented-out code, or TODO debris

Severity: **MINOR**.

AI role: Flag unclear naming, tangled responsibilities, obscured control flow, and missing docs. Explain the maintenance cost in context; length alone is not a finding.
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

AI role: Trace boundary inputs or failures through callers and guards; show the consequence with specific repository locations or a reproduction. State uncertain reachability assumptions. CWE references may classify an established issue.
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
| Evidence | BLOCKER for confirmed required-check failures | Unavailable checks → verification limitation; continue inspection |
| Reliability | MAJOR | Confirmed security vuln → BLOCKER |
| Form | MAJOR for demonstrated design/compatibility problems; MINOR for evidenced convention violations | Breaking public API → BLOCKER |
| Clarity | MINOR | Misleading names causing bugs → MAJOR |
| Edge Cases | BLOCKER / MAJOR | Crash-causing → BLOCKER, degraded → MAJOR |
| Purpose | BLOCKER | N/A — wrong code is always a blocker |
| Taste | NITPICK | Never escalates |

## Confidence Levels

Every finding except non-blocking Taste observations must be tagged with a confidence level. Confidence measures evidence for the specific local claim, independently of severity:

| Level | Meaning | Local Evidence Required | Scored in Learn Mode? |
|-------|---------|-------------------------|----------------------|
| **Verified** | The specific claim is established by a reproduction or complete causal argument from repository code | Reachable trigger, affected path (including callers/guards), and concrete consequence supported by file/line references or reproduction output | Yes |
| **Likely** | Repository evidence supports the issue, but a material assumption remains unresolved | Relevant code/tool output and causal reasoning, with the unverified condition explicitly stated | Yes |
| **Uncertain** | A candidate concern whose trigger, path, or consequence is not established | Available local evidence, missing evidence, and assumptions clearly stated | No |

A source URL, tool warning, or repository pattern match alone cannot verify a defect. Tool output can verify the narrow claim that a particular check failed; it does not automatically verify the suspected cause or a security vulnerability. Convention findings need an applicable repository rule or concrete maintenance cost, not just a general design preference. Uncertain candidates must remain explicitly qualified and cannot be treated as established blocking defects.

Investigate uncertainty by tracing callers, contracts, guards, and tests or running a focused reproduction. Web verification is not required for ordinary local correctness findings. If external API, language, or security semantics matter to the causal argument, consult relevant documentation and identify exactly what it establishes. A CWE page defines a weakness class; a style guide describes a convention. Neither proves a defect in this repository.

## Finding Evidence and References

Each finding must explain:

1. **Trigger:** The input, state, or event that exposes the issue, and why it is reachable.
2. **Execution path:** The affected entry point, callers, guards, and operation. For convention/clarity findings, identify the affected usage or maintenance task.
3. **Consequence:** The concrete failure, impact, or maintenance cost.
4. **Repository evidence or reproduction:** Exact file/line references supporting the causal argument, or reproduction input/command with expected and actual results.
5. **Uncertainty:** Assumptions, unverified conditions, and relevant verification limitations; write "None" when established.

Keep repository proof separate from optional external references. Cite external documentation inline only when it establishes semantics or an adopted rule relevant to the finding, and state that role. Missing web access does not prevent presenting a locally supported correctness finding.

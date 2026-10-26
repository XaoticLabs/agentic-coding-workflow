# TypeScript and JavaScript review cues

Use these cues for changed behavior; establish the reachable path and concrete
consequence before reporting a finding. Inspect the component's runtime,
package manager, lockfile, module mode, compiler settings, and existing checks.
Do not assume React, Node, npm, a test runner, or a new validation library.

- Trace untrusted data through existing runtime validation and narrowing.
  Type assertions and declared interfaces do not validate incoming payloads.
  Check optional/null values and discriminated unions against actual inputs.
- Follow promises through awaiting, rejection, cancellation, cleanup, and
  caller-visible errors. Check racing requests and shared mutable state.
- Check compatibility across API schemas, generated clients, serialization,
  ESM/CJS boundaries, exports, and the actual supported runtime.
- For UI changes, inspect state transitions, stale responses, loading/error
  behavior, and relevant browser evidence. Load framework docs only when used.
- Confirm tests exercise real boundary/failure behavior and preserve mocks,
  fixtures, discovery, and assertion strength. Type-checking, transpilation,
  builds, unit tests, and browser tests establish different evidence.

Select existing scripts from CI/project configuration. Report an absent or
unavailable required check explicitly; do not guess `npm test` or silently
substitute one package manager for another.

Authoritative semantics: [TypeScript narrowing](https://www.typescriptlang.org/docs/handbook/2/narrowing.html),
[type assertions](https://www.typescriptlang.org/docs/handbook/2/everyday-types.html#type-assertions),
and [Node modules](https://nodejs.org/api/packages.html) when Node is used.

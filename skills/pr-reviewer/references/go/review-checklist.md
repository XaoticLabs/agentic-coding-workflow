# Go review cues

Use these cues for changed behavior; establish a reachable trigger and local
consequence before reporting a finding. Follow the repository's Go version,
module/workspace boundaries, APIs, and configured checks. Do not install a
linter or impose a style guide during review.

- Trace context cancellation/deadlines through request and background work;
  check ownership of cancellation and cleanup on every exit path.
- Identify who starts and stops goroutines, closes channels, and owns shared
  state. Check blocking sends/receives and error paths. Use targeted race tests
  when relevant and supported; a passing race run covers only exercised paths.
- Trace errors through wrapping, comparisons, caller behavior, and response
  mapping. Check interface/nil behavior against concrete possible values.
- Check resource lifetimes (bodies, files, rows, transactions), retry bounds,
  idempotency, and compatibility of changed wire/storage representations.
- Confirm tests exercise changed failure and cancellation behavior, not just
  mocked success. Check relevant cross-module/service callers.

Use the existing CI/task commands. `go test`, race tests, vet, build, and any
configured linter have different scopes; report what actually ran and what a
required unavailable check leaves unknown.

Authoritative semantics: [context](https://pkg.go.dev/context),
[race detector](https://go.dev/doc/articles/race_detector), and the
[Go specification](https://go.dev/ref/spec). Use version-appropriate docs.

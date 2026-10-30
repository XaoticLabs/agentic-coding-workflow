;; Repository development tasks. Run `maak --list` for the public interface.
(define-module (maak)
  #:use-module (maak maak)
  #:export (default setup check-environment lint test verify check
            sync-hosts check-hosts install-hosts))

(define uv (or (getenv "UV") "uv"))

(define* (uv-run arguments #:key (env '()))
  (run (append (list uv "run" "--frozen" "--no-sync" "--offline") arguments)
       #:env env #:verbose? #t))

(define (setup)
  "Create or synchronize the locked Python development environment."
  (for-each
   (lambda (tool)
     (let ((path (if (string-index tool #\/)
                     tool
                     (search-path (parse-path (getenv "PATH")) tool))))
       (unless (and path (access? path X_OK))
         (raise-maak-error (string-append "Missing prerequisite: " tool)
                           #:hint "See README.md for development prerequisites."))))
   (list "bash" "git" "jq" uv))
  (run (list uv "sync" "--locked" "--dev") #:verbose? #t))

;; Checks never install tools or repair the environment implicitly.
(define (check-environment)
  "Reject a missing or stale development environment without installing."
  (unless (or (dry-run?) (access? ".venv/bin/python" X_OK))
    (raise-maak-error "Development environment missing. Run maak setup."))
  (unless (run (list uv "sync" "--locked" "--dev" "--check" "--offline")
               #:allow-failure? #t)
    (raise-maak-error "Run maak setup; dependency edits also require uv lock.")))

(define (lint)
  "Check Ruff, hook registration, and generated host resources."
  (check-environment)
  (uv-run '("python" "-m" "ruff" "check" "--no-fix" "."))
  (uv-run '("bash" "scripts/validate-hooks.sh"))
  (uv-run '("python" "scripts/sync-hosts.py" "--check")))

(define (test)
  "Run the deterministic pytest suite."
  (check-environment)
  (uv-run '("python" "-m" "pytest" "-q")))

(define (verify)
  "Exercise public hook and CLI delivery behavior with retained evidence."
  (check-environment)
  (uv-run '("python" "tests/smoke_delivery.py")))

(define (check)
  "Run lint, tests, and delivery verification; stop on the first failure."
  (lint)
  (test)
  (verify))

(define (default)
  "Run all repository checks."
  (check))

(define (sync-hosts)
  "Regenerate Pi and Autolith from canonical Claude sources."
  (check-environment)
  (uv-run '("python" "scripts/sync-hosts.py")))

(define (check-hosts)
  "Require and exercise the pinned optional Pi and Autolith hosts."
  (check-environment)
  (uv-run '("python" "-m" "pytest" "-q" "tests/test_pi_host.py"
            "tests/test_autolith_host.py" "tests/test_host_runners.py")
          #:env '(("WORKFLOW_REQUIRE_PI" . "1")
                  ("WORKFLOW_REQUIRE_AUTOLITH" . "1")))
  (uv-run '("python" "tests/smoke_autolith.py"))
  (uv-run '("python" "tests/smoke_host_runners.py")))

(define (install-hosts)
  "Explicitly install the pinned optional Pi and Autolith hosts."
  (run '("bash" "scripts/install-hosts.sh") #:verbose? #t))

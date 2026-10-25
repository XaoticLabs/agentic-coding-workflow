#!/usr/bin/env bash
# StopFailure output and exit code are ignored; log and notify only.
exec python3 "$(dirname "$(realpath "$0")")/stop-failure-logger.py"

#!/usr/bin/env bash
# StopFailure output and exit code are ignored; retain evidence without a toast.
exec python3 "$(dirname "$(realpath "$0")")/stop-failure-logger.py"

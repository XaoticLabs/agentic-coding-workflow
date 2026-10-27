#!/usr/bin/env bash
# Compatibility entrypoint; lifecycle registration lives in hooks.json.
exec python3 "$(dirname "$0")/workflow-events.py" Stop

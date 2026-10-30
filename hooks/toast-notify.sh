#!/usr/bin/env bash
# Compatibility entrypoint for native idle/input notifications, never Stop.
exec python3 "$(dirname "$0")/workflow-events.py" Notification

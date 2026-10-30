#!/usr/bin/env bash
# Generated canonical-script entrypoint; edit the original skill.
_WORKFLOW_RESOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export WORKFLOW_HOST=pi
exec bash "${_WORKFLOW_RESOURCE_DIR}"/../../../../../../skills/tmux-multiplexer/scripts/collect-pane-outputs.sh "$@"

#!/bin/bash
# Checkpoint Manager for Claude Code Sessions
# Manages saving, listing, and restoring conversation checkpoints

set -e

CHECKPOINT_DIR=".claude/checkpoints"
INDEX_FILE="$CHECKPOINT_DIR/index.json"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Initialize checkpoint directory and index
init_checkpoint_dir() {
    if [[ ! -d "$CHECKPOINT_DIR" ]]; then
        mkdir -p "$CHECKPOINT_DIR"
        echo '{"checkpoints": [], "forks": []}' > "$INDEX_FILE"
        echo -e "${GREEN}Initialized checkpoint directory: $CHECKPOINT_DIR${NC}"
    elif [[ ! -f "$INDEX_FILE" ]]; then
        echo '{"checkpoints": [], "forks": []}' > "$INDEX_FILE"
    fi
}

# Generate a unique checkpoint ID
generate_id() {
    echo "ckpt-$(date +%Y%m%d-%H%M%S)-$(openssl rand -hex 4)"
}

# Get git information
get_git_info() {
    local git_info="{}"
    if git rev-parse --git-dir > /dev/null 2>&1; then
        local sha=$(git rev-parse HEAD 2>/dev/null || echo "unknown")
        local branch=$(git branch --show-current 2>/dev/null || echo "detached")
        local dirty=$(git status --porcelain 2>/dev/null | wc -l | tr -d ' ')
        local uncommitted_files=$(git status --porcelain 2>/dev/null | head -20 | jq -R -s 'split("\n") | map(select(length > 0))' 2>/dev/null || echo "[]")
        git_info=$(jq -n \
            --arg sha "$sha" \
            --arg branch "$branch" \
            --arg dirty "$dirty" \
            --argjson files "$uncommitted_files" \
            '{sha: $sha, branch: $branch, uncommitted_count: ($dirty | tonumber), uncommitted_files: $files}')
    fi
    echo "$git_info"
}

# Create a new checkpoint
create_checkpoint() {
    local name="$1"
    local summary="$2"
    local context_notes="$3"
    local is_auto="${4:-false}"

    init_checkpoint_dir

    local id=$(generate_id)
    local timestamp=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
    local working_dir=$(pwd)
    local git_info=$(get_git_info)

    # Create checkpoint directory
    local ckpt_dir="$CHECKPOINT_DIR/$id"
    mkdir -p "$ckpt_dir"

    # Create metadata.json
    jq -n \
        --arg id "$id" \
        --arg name "$name" \
        --arg summary "$summary" \
        --arg timestamp "$timestamp" \
        --argjson auto "$is_auto" \
        '{
            id: $id,
            name: $name,
            summary: $summary,
            timestamp: $timestamp,
            auto_generated: $auto
        }' > "$ckpt_dir/metadata.json"

    # Create context.json
    jq -n \
        --arg working_dir "$working_dir" \
        --arg context_notes "$context_notes" \
        --argjson git "$git_info" \
        '{
            working_directory: $working_dir,
            context_notes: $context_notes,
            git: $git
        }' > "$ckpt_dir/context.json"

    # Create empty state.json (for future expansion)
    echo '{"message_estimate": "unknown", "notes": "Actual conversation state cannot be captured - see documentation"}' > "$ckpt_dir/state.json"

    # Update index
    local index_entry=$(jq -n \
        --arg id "$id" \
        --arg name "$name" \
        --arg summary "$summary" \
        --arg timestamp "$timestamp" \
        '{id: $id, name: $name, summary: $summary, timestamp: $timestamp}')

    jq --argjson entry "$index_entry" '.checkpoints += [$entry]' "$INDEX_FILE" > "$INDEX_FILE.tmp" && mv "$INDEX_FILE.tmp" "$INDEX_FILE"

    echo "$id"
}

# List all checkpoints
list_checkpoints() {
    init_checkpoint_dir

    if [[ ! -f "$INDEX_FILE" ]]; then
        echo "No checkpoints found."
        return 0
    fi

    local count=$(jq '.checkpoints | length' "$INDEX_FILE")

    if [[ "$count" == "0" ]]; then
        echo "No checkpoints found."
        return 0
    fi

    echo -e "${BLUE}=== Checkpoints ($count total) ===${NC}"
    echo ""

    jq -r '.checkpoints | sort_by(.timestamp) | reverse | .[] |
        "[\(.timestamp | split("T")[0])] \(.name)\n  ID: \(.id)\n  Summary: \(.summary)\n"' "$INDEX_FILE"
}

# Get checkpoint details
get_checkpoint() {
    local identifier="$1"
    init_checkpoint_dir

    # Try to find by name first, then by ID
    local ckpt_id=$(jq -r --arg name "$identifier" '.checkpoints[] | select(.name == $name) | .id' "$INDEX_FILE" 2>/dev/null)

    if [[ -z "$ckpt_id" || "$ckpt_id" == "null" ]]; then
        ckpt_id=$(jq -r --arg id "$identifier" '.checkpoints[] | select(.id == $id) | .id' "$INDEX_FILE" 2>/dev/null)
    fi

    if [[ -z "$ckpt_id" || "$ckpt_id" == "null" ]]; then
        echo ""
        return 1
    fi

    echo "$ckpt_id"
}

# Show checkpoint details
show_checkpoint() {
    local identifier="$1"
    local ckpt_id=$(get_checkpoint "$identifier")

    if [[ -z "$ckpt_id" ]]; then
        echo -e "${RED}Checkpoint not found: $identifier${NC}"
        return 1
    fi

    local ckpt_dir="$CHECKPOINT_DIR/$ckpt_id"

    echo -e "${BLUE}=== Checkpoint Details ===${NC}"
    echo ""

    if [[ -f "$ckpt_dir/metadata.json" ]]; then
        echo -e "${GREEN}Metadata:${NC}"
        jq '.' "$ckpt_dir/metadata.json"
        echo ""
    fi

    if [[ -f "$ckpt_dir/context.json" ]]; then
        echo -e "${GREEN}Context:${NC}"
        jq '.' "$ckpt_dir/context.json"
        echo ""
    fi
}

# Delete a checkpoint
delete_checkpoint() {
    local identifier="$1"
    local ckpt_id=$(get_checkpoint "$identifier")

    if [[ -z "$ckpt_id" ]]; then
        echo -e "${RED}Checkpoint not found: $identifier${NC}"
        return 1
    fi

    local ckpt_dir="$CHECKPOINT_DIR/$ckpt_id"

    # Remove from index
    jq --arg id "$ckpt_id" '.checkpoints = [.checkpoints[] | select(.id != $id)]' "$INDEX_FILE" > "$INDEX_FILE.tmp" && mv "$INDEX_FILE.tmp" "$INDEX_FILE"

    # Remove directory
    rm -rf "$ckpt_dir"

    echo -e "${GREEN}Deleted checkpoint: $identifier${NC}"
}

# Record a fork
record_fork() {
    local parent_checkpoint="$1"
    local fork_session_id="$2"
    local fork_checkpoint_id="$3"

    init_checkpoint_dir

    local timestamp=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

    local fork_entry=$(jq -n \
        --arg parent "$parent_checkpoint" \
        --arg session "$fork_session_id" \
        --arg checkpoint "$fork_checkpoint_id" \
        --arg timestamp "$timestamp" \
        '{parent_checkpoint: $parent, forked_session: $session, fork_checkpoint: $checkpoint, timestamp: $timestamp}')

    jq --argjson entry "$fork_entry" '.forks += [$entry]' "$INDEX_FILE" > "$INDEX_FILE.tmp" && mv "$INDEX_FILE.tmp" "$INDEX_FILE"
}

# Check if a checkpoint name already exists
name_exists() {
    local name="$1"
    init_checkpoint_dir

    local exists=$(jq -r --arg name "$name" '.checkpoints[] | select(.name == $name) | .id' "$INDEX_FILE" 2>/dev/null)

    if [[ -n "$exists" && "$exists" != "null" ]]; then
        return 0
    fi
    return 1
}

# Generate unique name by appending number if needed
make_unique_name() {
    local base_name="$1"
    local name="$base_name"
    local counter=1

    while name_exists "$name"; do
        name="${base_name}-${counter}"
        ((counter++))
    done

    echo "$name"
}

# Cleanup old checkpoints (keep last N)
cleanup_old() {
    local keep="${1:-20}"
    init_checkpoint_dir

    local count=$(jq '.checkpoints | length' "$INDEX_FILE")

    if [[ "$count" -le "$keep" ]]; then
        echo "No cleanup needed. Have $count checkpoints (limit: $keep)"
        return 0
    fi

    local to_delete=$((count - keep))

    # Get oldest checkpoint IDs
    local old_ids=$(jq -r ".checkpoints | sort_by(.timestamp) | .[0:$to_delete] | .[].id" "$INDEX_FILE")

    for id in $old_ids; do
        delete_checkpoint "$id"
    done

    echo -e "${GREEN}Cleaned up $to_delete old checkpoints${NC}"
}

# Export checkpoint for sharing
export_checkpoint() {
    local identifier="$1"
    local output_file="$2"
    local ckpt_id=$(get_checkpoint "$identifier")

    if [[ -z "$ckpt_id" ]]; then
        echo -e "${RED}Checkpoint not found: $identifier${NC}"
        return 1
    fi

    local ckpt_dir="$CHECKPOINT_DIR/$ckpt_id"

    # Create a combined export file
    jq -s '{ metadata: .[0], context: .[1], state: .[2] }' \
        "$ckpt_dir/metadata.json" \
        "$ckpt_dir/context.json" \
        "$ckpt_dir/state.json" > "${output_file:-checkpoint-export.json}"

    echo -e "${GREEN}Exported to: ${output_file:-checkpoint-export.json}${NC}"
}

# Main command router
case "${1:-}" in
    init)
        init_checkpoint_dir
        ;;
    create)
        create_checkpoint "$2" "$3" "$4" "${5:-false}"
        ;;
    list)
        list_checkpoints
        ;;
    get)
        get_checkpoint "$2"
        ;;
    show)
        show_checkpoint "$2"
        ;;
    delete)
        delete_checkpoint "$2"
        ;;
    fork)
        record_fork "$2" "$3" "$4"
        ;;
    name-exists)
        if name_exists "$2"; then
            echo "true"
        else
            echo "false"
        fi
        ;;
    unique-name)
        make_unique_name "$2"
        ;;
    cleanup)
        cleanup_old "${2:-20}"
        ;;
    export)
        export_checkpoint "$2" "$3"
        ;;
    *)
        echo "Usage: $0 {init|create|list|get|show|delete|fork|name-exists|unique-name|cleanup|export}"
        echo ""
        echo "Commands:"
        echo "  init                          Initialize checkpoint directory"
        echo "  create <name> <summary> <notes> [auto]  Create a new checkpoint"
        echo "  list                          List all checkpoints"
        echo "  get <name-or-id>              Get checkpoint ID by name or ID"
        echo "  show <name-or-id>             Show checkpoint details"
        echo "  delete <name-or-id>           Delete a checkpoint"
        echo "  fork <parent> <session> <id>  Record a fork relationship"
        echo "  name-exists <name>            Check if name exists"
        echo "  unique-name <base>            Generate unique name"
        echo "  cleanup [keep-count]          Remove old checkpoints"
        echo "  export <name-or-id> [file]    Export checkpoint to JSON"
        exit 1
        ;;
esac

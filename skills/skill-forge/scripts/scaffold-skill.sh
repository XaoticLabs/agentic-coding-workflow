#!/usr/bin/env bash
# scaffold-skill.sh — Create a skill directory structure with template files
# Usage: scaffold-skill.sh <skill-name> [target-dir]
#
# Arguments:
#   skill-name   Kebab-case name for the skill (e.g., "code-reviewer")
#   target-dir   Parent directory to create skill in (default: current directory)
#
# Creates:
#   <skill-name>/
#   ├── SKILL.md          (template with correct frontmatter)
#   ├── scripts/          (for deterministic helper scripts)
#   ├── references/       (for on-demand reference documents)
#   └── [examples/]       (if --examples flag is passed)
#
# Exit codes:
#   0  Success
#   1  Invalid arguments
#   2  Directory already exists
#   3  Failed to create directory structure

set -euo pipefail

# --- Colors (only if terminal supports them) ---
if [ -t 1 ] && command -v tput &>/dev/null; then
    GREEN=$(tput setaf 2)
    YELLOW=$(tput setaf 3)
    RED=$(tput setaf 1)
    BOLD=$(tput bold)
    RESET=$(tput sgr0)
else
    GREEN="" YELLOW="" RED="" BOLD="" RESET=""
fi

usage() {
    cat <<'USAGE'
Usage: scaffold-skill.sh [OPTIONS] <skill-name> [target-dir]

Create a new skill directory structure with template files.

Arguments:
  skill-name    Kebab-case name (e.g., "code-reviewer", "deploy-helper")
  target-dir    Parent directory (default: current directory)

Options:
  --examples    Include an examples/ directory
  --assets      Include an assets/ directory
  --full        Include both examples/ and assets/
  -h, --help    Show this help message

Examples:
  scaffold-skill.sh my-skill
  scaffold-skill.sh --full terraform-reviewer ./skills/
  scaffold-skill.sh --examples code-generator /path/to/plugin/skills/
USAGE
}

# --- Parse arguments ---
INCLUDE_EXAMPLES=false
INCLUDE_ASSETS=false
SKILL_NAME=""
TARGET_DIR=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        -h|--help)
            usage
            exit 0
            ;;
        --examples)
            INCLUDE_EXAMPLES=true
            shift
            ;;
        --assets)
            INCLUDE_ASSETS=true
            shift
            ;;
        --full)
            INCLUDE_EXAMPLES=true
            INCLUDE_ASSETS=true
            shift
            ;;
        -*)
            echo "${RED}Error: Unknown option '$1'${RESET}" >&2
            usage >&2
            exit 1
            ;;
        *)
            if [ -z "$SKILL_NAME" ]; then
                SKILL_NAME="$1"
            elif [ -z "$TARGET_DIR" ]; then
                TARGET_DIR="$1"
            else
                echo "${RED}Error: Too many arguments${RESET}" >&2
                usage >&2
                exit 1
            fi
            shift
            ;;
    esac
done

# --- Validate skill name ---
if [ -z "$SKILL_NAME" ]; then
    echo "${RED}Error: skill-name is required${RESET}" >&2
    usage >&2
    exit 1
fi

# Enforce kebab-case: lowercase letters, numbers, hyphens only
if ! echo "$SKILL_NAME" | grep -qE '^[a-z][a-z0-9]*(-[a-z0-9]+)*$'; then
    echo "${RED}Error: Skill name must be kebab-case (e.g., 'my-skill', 'code-reviewer')${RESET}" >&2
    echo "  Got: '$SKILL_NAME'" >&2
    echo "  Rules: lowercase letters/numbers, hyphens as separators, starts with letter" >&2
    exit 1
fi

# --- Set target directory ---
TARGET_DIR="${TARGET_DIR:-.}"
SKILL_DIR="$TARGET_DIR/$SKILL_NAME"

# --- Check if directory already exists ---
if [ -d "$SKILL_DIR" ]; then
    echo "${RED}Error: Directory already exists: $SKILL_DIR${RESET}" >&2
    echo "  Remove it first or choose a different name." >&2
    exit 2
fi

# --- Create directory structure ---
echo "${BOLD}Scaffolding skill: ${GREEN}$SKILL_NAME${RESET}"

mkdir -p "$SKILL_DIR/scripts" "$SKILL_DIR/references" || {
    echo "${RED}Error: Failed to create directory structure${RESET}" >&2
    exit 3
}

if [ "$INCLUDE_EXAMPLES" = true ]; then
    mkdir -p "$SKILL_DIR/examples"
fi

if [ "$INCLUDE_ASSETS" = true ]; then
    mkdir -p "$SKILL_DIR/assets"
fi

# --- Generate SKILL.md template ---
cat > "$SKILL_DIR/SKILL.md" <<TEMPLATE
---
name: ${SKILL_NAME}
description: |
  This skill should be used when [describe triggering conditions]. Use it whenever
  the user [specific actions/phrases that should trigger this skill], even if they
  don't explicitly mention "${SKILL_NAME}".
allowed-tools:
  - Bash
  - Read
  - Write
  - Edit
  - Grep
  - Glob
user-invocable: true
---

# ${SKILL_NAME}

[Brief overview — what this skill does and why it exists. 1-2 sentences.]

## When to use this skill

[Describe the contexts and user intents that should trigger this skill. Be specific
about what distinguishes this from similar skills.]

## Workflow

### Phase 1: [Name]

[Core instructions for the first phase. Keep it actionable and imperative.]

### Phase 2: [Name]

[Next phase instructions.]

## Reference materials

Read these as needed — not upfront:

- \`references/[topic].md\` — [When to read: specific condition]. [What it contains in one line.]

## Scripts

- \`scripts/[name].sh\` — [What it does]. Run via: \`bash \${CLAUDE_SKILL_ROOT}/scripts/[name].sh [args]\`

## Output format

[Define expected output structure if applicable.]
TEMPLATE

# --- Generate .gitkeep files for empty dirs ---
for dir in scripts references; do
    if [ -z "$(ls -A "$SKILL_DIR/$dir" 2>/dev/null)" ]; then
        touch "$SKILL_DIR/$dir/.gitkeep"
    fi
done

if [ "$INCLUDE_EXAMPLES" = true ]; then
    touch "$SKILL_DIR/examples/.gitkeep"
fi

if [ "$INCLUDE_ASSETS" = true ]; then
    touch "$SKILL_DIR/assets/.gitkeep"
fi

# --- Summary ---
echo ""
echo "${GREEN}Created skill structure:${RESET}"
echo ""
find "$SKILL_DIR" -type f | sort | while read -r file; do
    # Show relative path from skill dir
    rel="${file#$SKILL_DIR/}"
    echo "  $SKILL_NAME/$rel"
done
echo ""
echo "${BOLD}Next steps:${RESET}"
echo "  1. Edit ${YELLOW}$SKILL_DIR/SKILL.md${RESET} — fill in the description and workflow"
echo "  2. Add scripts to ${YELLOW}$SKILL_DIR/scripts/${RESET}"
echo "  3. Add reference docs to ${YELLOW}$SKILL_DIR/references/${RESET}"
echo "  4. Run ${YELLOW}validate-skill.py $SKILL_DIR${RESET} to check quality"

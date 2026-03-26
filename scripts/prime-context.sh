#!/usr/bin/env bash
set -euo pipefail

# Prime Context Gatherer
# Collects deterministic project context for dynamic injection into the prime command.
# Outputs structured markdown that gets injected before Claude processes the prompt.

# --- Git State ---
echo "## Git State"
echo ""

branch=$(git branch --show-current 2>/dev/null || echo "detached HEAD")
echo "**Branch:** \`${branch}\`"
echo ""

echo "### Recent Commits"
echo '```'
git log --oneline -5 2>/dev/null || echo "(no commits)"
echo '```'
echo ""

echo "### Uncommitted Changes"
status=$(git status --short 2>/dev/null || echo "")
if [ -z "$status" ]; then
    echo "Clean working tree."
else
    echo '```'
    echo "$status"
    echo '```'
fi
echo ""

# --- Tech Stack Detection ---
echo "## Detected Tech Stack"
echo ""

detect_stack() {
    local found=0

    if [ -f "mix.exs" ]; then
        echo "- **Elixir/Phoenix** (mix.exs found)"
        [ -f "config/config.exs" ] && echo "  - Phoenix config: config/config.exs"
        [ -f "lib" ] && echo "  - App modules: lib/"
        [ -d "priv/repo/migrations" ] && echo "  - Ecto migrations present"
        found=1
    fi

    if [ -f "package.json" ]; then
        echo "- **Node.js** (package.json found)"
        if [ -f "package.json" ]; then
            # Detect frameworks from package.json
            grep -q '"next"' package.json 2>/dev/null && echo "  - Framework: Next.js"
            grep -q '"react"' package.json 2>/dev/null && echo "  - UI: React"
            grep -q '"vue"' package.json 2>/dev/null && echo "  - UI: Vue"
            grep -q '"typescript"' package.json 2>/dev/null && echo "  - TypeScript enabled"
        fi
        found=1
    fi

    if [ -f "pyproject.toml" ] || [ -f "requirements.txt" ] || [ -f "setup.py" ]; then
        echo "- **Python**"
        [ -f "pyproject.toml" ] && echo "  - pyproject.toml found"
        [ -f "requirements.txt" ] && echo "  - requirements.txt found"
        found=1
    fi

    if [ -f "go.mod" ]; then
        echo "- **Go** (go.mod found)"
        found=1
    fi

    if [ -f "Cargo.toml" ]; then
        echo "- **Rust** (Cargo.toml found)"
        found=1
    fi

    if [ -f "Gemfile" ]; then
        echo "- **Ruby** (Gemfile found)"
        grep -q "rails" Gemfile 2>/dev/null && echo "  - Framework: Rails"
        found=1
    fi

    # Infrastructure
    [ -f "docker-compose.yml" ] || [ -f "docker-compose.yaml" ] && echo "- **Docker Compose** present"
    [ -f "Dockerfile" ] && echo "- **Dockerfile** present"
    [ -f "Makefile" ] && echo "- **Makefile** present"
    [ -d ".github/workflows" ] && echo "- **GitHub Actions** CI/CD"
    [ -f ".gitlab-ci.yml" ] && echo "- **GitLab CI** pipeline"
    [ -f "terraform.tf" ] || [ -d "terraform" ] && echo "- **Terraform** infrastructure"

    if [ "$found" -eq 0 ]; then
        echo "- No standard tech stack config files detected"
    fi
}

detect_stack
echo ""

# --- Directory Structure ---
echo "## Directory Structure (3 levels)"
echo '```'
if command -v tree &>/dev/null; then
    tree -L 3 -I 'node_modules|_build|deps|.git|.elixir_ls|__pycache__|.pytest_cache|target|vendor|dist|build' --dirsfirst -n 2>/dev/null || find . -maxdepth 3 -not -path '*/\.*' -not -path '*/node_modules/*' -not -path '*/_build/*' -not -path '*/deps/*' | head -80
else
    find . -maxdepth 3 \
        -not -path '*/\.*' \
        -not -path '*/node_modules/*' \
        -not -path '*/_build/*' \
        -not -path '*/deps/*' \
        -not -path '*/__pycache__/*' \
        -not -path '*/target/*' \
        -not -path '*/vendor/*' \
        -not -path '*/dist/*' \
        -not -path '*/build/*' \
        | sort | head -80
fi
echo '```'
echo ""

# --- Key Files ---
echo "## Key Files Present"
echo ""

for f in README.md CLAUDE.md ARCHITECTURE.md .claude/rules/*.md docs/*.md; do
    # shellcheck disable=SC2086
    for match in $f; do
        [ -f "$match" ] && echo "- \`${match}\`"
    done
done
echo ""

# --- README Summary (first 50 lines) ---
if [ -f "README.md" ]; then
    echo "## README.md (first 50 lines)"
    echo '```markdown'
    head -50 README.md
    echo '```'
    echo ""
fi

# --- CLAUDE.md ---
if [ -f "CLAUDE.md" ]; then
    echo "## CLAUDE.md"
    echo '```markdown'
    cat CLAUDE.md
    echo '```'
fi

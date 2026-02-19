#!/usr/bin/env sh
# octopilot-mcp installer
# Usage:  curl -fsSL https://mcp.octopilot.app/install | sh
#
# What this does:
#   1. Installs uv (fast Python package manager) if not present
#   2. Installs octopilot-mcp as a uv tool
#   3. Detects your AI assistant (Cursor / Claude Desktop) and registers the server
#
# Requirements: Docker or Colima must be running for op build commands.
# The hosted server at https://mcp.octopilot.app works without Docker.

set -e

BOLD="\033[1m"
GREEN="\033[0;32m"
YELLOW="\033[0;33m"
RED="\033[0;31m"
RESET="\033[0m"

info()    { printf "${GREEN}  ✓${RESET}  %s\n" "$1"; }
warn()    { printf "${YELLOW}  !${RESET}  %s\n" "$1"; }
error()   { printf "${RED}  ✗${RESET}  %s\n" "$1" >&2; }
heading() { printf "\n${BOLD}%s${RESET}\n" "$1"; }

# ── 1. Install uv ─────────────────────────────────────────────────────────────
heading "Checking uv..."

if command -v uv >/dev/null 2>&1; then
    info "uv $(uv --version 2>/dev/null | head -1) already installed"
else
    warn "uv not found — installing..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    # Add uv to PATH for the rest of this script
    export PATH="$HOME/.cargo/bin:$HOME/.local/bin:$PATH"
    if ! command -v uv >/dev/null 2>&1; then
        error "uv installation failed. Please install manually: https://docs.astral.sh/uv/getting-started/installation/"
        exit 1
    fi
    info "uv installed successfully"
fi

# ── 2. Install octopilot-mcp ──────────────────────────────────────────────────
heading "Installing octopilot-mcp..."

uv tool install octopilot-mcp --upgrade
info "octopilot-mcp installed"

# Ensure tool binaries are on PATH
export PATH="$(uv tool dir)/bin:$(uv tool dir --no-cache 2>/dev/null || true)/bin:$PATH"
if ! command -v fastmcp >/dev/null 2>&1; then
    # uv tool installs fastmcp alongside octopilot-mcp as a dependency
    UV_TOOL_BIN="$(uv tool dir octopilot-mcp 2>/dev/null)/bin"
    export PATH="$UV_TOOL_BIN:$PATH"
fi

# ── 3. Register with AI assistants ────────────────────────────────────────────
heading "Registering with AI assistants..."

REGISTERED=0

# Cursor
if [ -d "$HOME/.cursor" ] || [ -d "$HOME/Library/Application Support/Cursor" ]; then
    if command -v fastmcp >/dev/null 2>&1; then
        fastmcp install cursor octopilot-mcp --name octopilot 2>/dev/null \
            && info "Registered with Cursor" \
            || warn "Cursor registration failed — try manually: fastmcp install cursor octopilot-mcp --name octopilot"
        REGISTERED=1
    fi
fi

# Claude Desktop (macOS)
CLAUDE_DIR="$HOME/Library/Application Support/Claude"
if [ -d "$CLAUDE_DIR" ]; then
    if command -v fastmcp >/dev/null 2>&1; then
        fastmcp install claude octopilot-mcp --name octopilot 2>/dev/null \
            && info "Registered with Claude Desktop" \
            || warn "Claude Desktop registration failed — try manually: fastmcp install claude octopilot-mcp --name octopilot"
        REGISTERED=1
    fi
fi

if [ "$REGISTERED" -eq 0 ]; then
    warn "No AI assistant detected. Register manually:"
    printf "     Cursor:         fastmcp install cursor octopilot-mcp --name octopilot\n"
    printf "     Claude Desktop: fastmcp install claude octopilot-mcp --name octopilot\n"
fi

# ── Done ──────────────────────────────────────────────────────────────────────
heading "Done!"
cat <<'EOF'

  octopilot-mcp is installed. Restart your AI assistant to pick up the changes.

  Tools available:
    detect_project_contexts   — detect languages from skaffold.yaml
    generate_skaffold_yaml    — generate a skaffold.yaml
    generate_ci_workflow      — generate .github/workflows/ci.yml
    onboard_repository        — onboard a repo end-to-end
    run_op_build              — run op build (requires Docker)
    list_actions              — browse the Octopilot GitHub Actions registry
    get_action_details        — full spec for one action

  No Docker? Use the hosted server instead (stateless tools only):
    fastmcp install cursor  https://mcp.octopilot.app --name octopilot
    fastmcp install claude  https://mcp.octopilot.app --name octopilot

  Docs: https://octopilot.app/docs/mcp
EOF

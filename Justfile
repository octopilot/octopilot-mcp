# Default: list available commands
default:
    @just --list

# ── Development setup ─────────────────────────────────────────────────────────

# Install all dependencies including dev extras
install:
    pip install -e ".[dev,docker]"

# Install pre-commit hooks (run once after cloning)
install-hooks:
    pip install pre-commit
    pre-commit install

# ── Code quality ──────────────────────────────────────────────────────────────

# Run ruff linter
lint:
    ruff check src/ tests/

# Run ruff linter and auto-fix all fixable violations
lint-fix:
    ruff check src/ tests/ --fix

# Run ruff formatter (check only)
format-check:
    ruff format src/ tests/ --check

# Run ruff formatter (apply)
format:
    ruff format src/ tests/

# Lint + format check in one pass (what CI runs)
check: lint format-check

# ── Testing ───────────────────────────────────────────────────────────────────

# Run all tests
test:
    pytest tests/ -v

# Run tests with coverage report
coverage:
    pytest tests/ --cov=src/octopilot_mcp --cov-report=term-missing

# Run tests with HTML coverage report (opens in browser)
coverage-html:
    pytest tests/ --cov=src/octopilot_mcp --cov-report=html
    open htmlcov/index.html

# Run a specific test file or pattern
# Usage: just test-file tests/test_detect.py
#        just test-file -k "test_detect_go"
test-file *args:
    pytest {{args}} -v

# ── MCP server ────────────────────────────────────────────────────────────────

# Start the MCP server with hot-reload (requires uv + fastmcp CLI)
dev:
    uv run fastmcp dev src/octopilot_mcp/server.py --reload

# List all available MCP tools
list-tools:
    uv run fastmcp list src/octopilot_mcp/server.py

# Register with Cursor (set OP_BINARY env first)
install-cursor:
    uv run fastmcp install cursor src/octopilot_mcp/server.py \
        --name octopilot \
        --env OP_BINARY="${OP_BINARY:-op}"

# Register with Claude Desktop (set OP_BINARY env first)
install-claude:
    uv run fastmcp install claude src/octopilot_mcp/server.py \
        --name octopilot \
        --env OP_BINARY="${OP_BINARY:-op}"

# ── Cleanup ───────────────────────────────────────────────────────────────────

# Remove all build/cache artefacts
clean:
    rm -rf dist/ build/ *.egg-info/
    rm -rf .pytest_cache/ .ruff_cache/ .mypy_cache/
    rm -rf htmlcov/ .coverage coverage.xml
    find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
    find . -name "*.pyc" -delete

# ── CI equivalent ─────────────────────────────────────────────────────────────

# Full CI pass: lint + format check + tests with coverage
ci: check coverage

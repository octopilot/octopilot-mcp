# Contributing to octopilot-mcp

## Development setup

```bash
git clone https://github.com/octopilot/octopilot-mcp
cd octopilot-mcp
pip install -e ".[dev]"
# or with uv:
uv sync --all-extras
```

## Running tests

```bash
# All tests
python -m pytest tests/ -v

# With coverage report
python -m pytest tests/ --cov=src/octopilot_mcp --cov-report=term-missing

# Specific file
python -m pytest tests/test_detect.py -v
```

## Testing the MCP server live

```bash
# Start with hot-reload (requires uv + fastmcp CLI)
uv run fastmcp dev src/octopilot_mcp/server.py --reload

# List tools
uv run fastmcp list src/octopilot_mcp/server.py

# Call a tool from the terminal
uv run fastmcp call src/octopilot_mcp/server.py tool_list_actions
uv run fastmcp call src/octopilot_mcp/server.py tool_detect_project_contexts \
    --workspace /path/to/a/repo
```

## Project layout

```
src/octopilot_mcp/
├── server.py              # FastMCP app, tool/resource registration
├── tools/
│   ├── detect.py          # Language detection from skaffold.yaml
│   ├── generate.py        # CI workflow and skaffold.yaml generation
│   ├── op_runner.py       # op build invocation (binary or container)
│   └── actions.py         # Bundled actions registry
└── data/
    └── actions.json       # Synced from website/public/actions.json at release
tests/
├── test_detect.py         # Core detect_project_contexts tests
├── test_detect_extended.py# Individual language version detectors
├── test_generate.py       # CI workflow and skaffold generation
├── test_generate_extended.py # onboard_repository full flow
├── test_actions.py        # Registry loading and lookup
└── test_op_runner.py      # op build invocation (subprocess mocked)
```

## Coverage targets

| Module | Target |
|--------|--------|
| `tools/detect.py` | ≥ 95% |
| `tools/generate.py` | ≥ 95% |
| `tools/op_runner.py` | ≥ 95% |
| `tools/actions.py` | 100% |
| `server.py` | excluded — FastMCP wiring requires an integration test harness |

## Adding a new tool

1. Implement the logic in `src/octopilot_mcp/tools/<module>.py`
2. Write tests in `tests/test_<module>.py` — mock any subprocess calls
3. Register the tool in `server.py` with `@mcp.tool()` (add a `timeout` for long-running operations)
4. Update `README.md` tool table
5. If the tool is security-sensitive (production deployments, secret access), document in the module docstring **and do not expose it**

## Security policy

The `run_op_build` tool invokes the `op` binary in the developer's local environment.
`run_op_promote` and any other production-targeting operations are **intentionally absent** —
those must only run through GitHub Actions workflows with audit trail, OIDC credentials,
and environment protection rules.

When adding new tools, ask: *can this cause irreversible changes to a production system?*
If yes, it does not belong in the MCP server.

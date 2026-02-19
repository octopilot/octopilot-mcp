# octopilot-mcp

Model Context Protocol (MCP) server for [Octopilot](https://octopilot.app) — enables AI agents to detect, generate, build, and wire up new repositories end-to-end using the Octopilot CI/CD toolchain.

## What it does

| Tool | Description |
|------|-------------|
| `detect_project_contexts` | Parse `skaffold.yaml` → pipeline-context JSON (languages, versions, matrix) |
| `generate_skaffold_yaml` | Generate a `skaffold.yaml` for given artifacts |
| `generate_ci_workflow` | Full `.github/workflows/ci.yml` using the standard octopilot pipeline |
| `onboard_repository` | **One-call onboarding**: detect → generate files → return next steps |
| `run_op_build` | Run `op build` via local binary or `ghcr.io/octopilot/op` container |
| `list_actions` | All Octopilot GitHub Actions from the bundled registry |
| `get_action_details` | Full spec, inputs, examples, gotchas for one action |

> **`op promote-image` is intentionally not exposed.** Image promotion between
> environments is operationally sensitive and must only run through a GitHub Actions
> workflow (with audit trail, OIDC credentials, and environment protection rules).
> Use `generate_ci_workflow` to produce the workflow that handles promotion safely.

## Installation

```bash
# Clone and install
git clone https://github.com/octopilot/octopilot-mcp
cd octopilot-mcp
uv sync
```

## Usage

### Register with your IDE (one command, FastMCP 3 CLI)

```bash
# Cursor
uv run fastmcp install cursor src/octopilot_mcp/server.py \
    --name octopilot \
    --env OP_BINARY=/usr/local/bin/op

# Claude Desktop
uv run fastmcp install claude src/octopilot_mcp/server.py \
    --name octopilot \
    --env OP_BINARY=/usr/local/bin/op
```

### Development (hot-reload)

```bash
uv run fastmcp dev src/octopilot_mcp/server.py --reload
```

### Inspect tools from the terminal

```bash
# List all available tools
uv run fastmcp list src/octopilot_mcp/server.py

# Call a tool directly
uv run fastmcp call src/octopilot_mcp/server.py tool_list_actions
```

### Run as a server directly

```bash
uv run octopilot-mcp
```

### Manual JSON config (alternative to `fastmcp install`)

```json
{
  "mcpServers": {
    "octopilot": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/octopilot-mcp", "octopilot-mcp"],
      "env": {
        "OP_BINARY": "/usr/local/bin/op"
      }
    }
  }
}
```

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `OP_BINARY` | `op` (from PATH) | Path to the `op` CLI binary |

## Example agent interaction

```
User: Onboard this Rust API project to use Octopilot CI.

Agent: [calls onboard_repository("/path/to/my-api", "ghcr.io/my-org")]
       → Detected: rust (stable) in api/
       → Generated: skaffold.yaml, .github/workflows/ci.yml
       → Next steps: add .pre-commit-config.yaml, push changes
```

## Development

```bash
uv sync --all-extras
uv run pytest
```

## Resources

The server also exposes MCP resources for agent context:

- `octopilot://actions` — Full actions registry JSON
- `octopilot://pipeline-context-schema` — JSON Schema for pipeline-context
- `octopilot://docs/getting-started` — Plain-text onboarding guide
- `octopilot://docs/skaffold-patterns` — Common `skaffold.yaml` patterns

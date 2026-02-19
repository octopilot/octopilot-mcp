# ── Build stage ───────────────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /build

# Install curl to fetch the actions registry at build time
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
COPY src/ src/

# Fetch the bundled actions registry from the website.
# Falls back to an empty registry if unreachable (handled gracefully by
# tools/actions.py which returns [] when the file is absent).
RUN mkdir -p src/octopilot_mcp/data \
    && curl -sf --max-time 10 https://octopilot.app/actions.json \
         -o src/octopilot_mcp/data/actions.json \
    || echo '{"version":"1","actions":[]}' > src/octopilot_mcp/data/actions.json

RUN pip install --no-cache-dir --prefix=/install .

# ── Runtime stage ─────────────────────────────────────────────────────────────
FROM python:3.11-slim

WORKDIR /app

COPY --from=builder /install /usr/local
COPY --from=builder /build/src/octopilot_mcp/data/ /usr/local/lib/python3.11/site-packages/octopilot_mcp/data/

# Non-root user
RUN useradd --no-create-home --shell /bin/false mcp
USER mcp

ENV PORT=8000
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:${PORT}/')" \
    || exit 1

CMD ["octopilot-mcp-hosted"]

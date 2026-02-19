"use strict";
/**
 * main.ts — runtime page enhancements for mcp.octopilot.app
 *
 * 1. Fetches the latest octopilot-mcp release from GitHub Releases API and
 *    shows the version + a direct wheel URL for pinned installs.
 * 2. Fetches actions.json from octopilot.app and renders the tools grid.
 * 3. Wires up the copy-to-clipboard button.
 */
// ── Copy button ───────────────────────────────────────────────────────────────
const cmdLine = document.getElementById("cmd-line");
const copyBtn = document.getElementById("copy-btn");
const INSTALL_CMD = "curl -fsSL https://mcp.octopilot.app/install.sh | sh";
copyBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    navigator.clipboard.writeText(INSTALL_CMD).then(() => {
        copyBtn.textContent = "Copied!";
        copyBtn.classList.add("copied");
        setTimeout(() => {
            copyBtn.textContent = "Copy";
            copyBtn.classList.remove("copied");
        }, 1800);
    });
});
cmdLine.addEventListener("click", () => copyBtn.click());
// ── GitHub Releases — latest version ─────────────────────────────────────────
async function loadLatestRelease() {
    try {
        const res = await fetch("https://api.github.com/repos/octopilot/octopilot-mcp/releases/latest", { headers: { Accept: "application/vnd.github+json" } });
        if (!res.ok)
            return;
        const release = await res.json();
        const version = release.tag_name;
        // Show version badge
        const badge = document.getElementById("version-badge");
        const versionText = document.getElementById("version-text");
        versionText.textContent = version;
        badge.style.display = "inline-flex";
        // Find the wheel asset
        const wheel = release.assets.find((a) => a.name.endsWith(".whl"));
        if (wheel) {
            const releaseUrl = document.getElementById("release-url");
            releaseUrl.textContent = `uv tool install ${wheel.browser_download_url}`;
        }
    }
    catch {
        // Silently ignore — GitHub API rate limits or network issues
    }
}
// ── Actions registry — tools grid ────────────────────────────────────────────
const LOCAL_TOOLS = new Set([
    "detect_project_contexts",
    "onboard_repository",
    "run_op_build",
]);
// Statically defined tools — always shown even without network.
const STATIC_TOOLS = [
    {
        name: "list_actions",
        desc: "Browse all Octopilot GitHub Actions with full specs.",
        local: false,
    },
    {
        name: "get_action_details",
        desc: "Full spec, inputs, examples, and gotchas for one action.",
        local: false,
    },
    {
        name: "generate_skaffold_yaml",
        desc: "Generate a skaffold.yaml for a list of build artifacts.",
        local: false,
    },
    {
        name: "generate_ci_workflow",
        desc: "Full .github/workflows/ci.yml with detect → lint → test → build.",
        local: false,
    },
    {
        name: "detect_project_contexts",
        desc: "Parse skaffold.yaml → pipeline-context (languages, versions, matrix).",
        local: true,
    },
    {
        name: "onboard_repository",
        desc: "One-call onboarding: detect → generate files → next-steps checklist.",
        local: true,
    },
    {
        name: "run_op_build",
        desc: "Run op build via the official container image.",
        local: true,
    },
];
function renderTools() {
    const grid = document.getElementById("tools-grid");
    grid.innerHTML = STATIC_TOOLS.map((t) => `
    <div class="tool ${t.local ? "local" : ""}">
      ${t.local ? '<span class="tag">local only</span>' : ""}
      <div class="tool-name">${t.name}()</div>
      <div class="tool-desc">${t.desc}</div>
    </div>`).join("");
}
// ── Init ──────────────────────────────────────────────────────────────────────
renderTools();
loadLatestRelease();

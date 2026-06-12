import logging
from collections import Counter

from app.agents.state import GitMentorState
from app.config import settings
from app.llm.groq_provider import GroqProvider

logger = logging.getLogger(__name__)

_SYSTEM = (
    "You are a staff-level software engineer producing an architecture brief for a developer who needs to "
    "explain THIS specific codebase in a technical interview. Every claim must reference a real file, "
    "directory, or function name from the inputs provided. If you cannot identify something concretely "
    "from the manifest or dependency graph, write 'Not visible from manifest' rather than guessing. "
    "Output only the markdown document — no preamble, no follow-up text, no fences."
)

_PROMPT_TEMPLATE = """Produce an architecture brief for the codebase below. The reader has never seen this repo.

## File Manifest ({file_count} files, {dep_edge_count} import edges)
Language distribution: {lang_distribution}
Top directories: {top_dirs}

Files (path · language · lines):
{manifest_summary}

## Dependency Graph (file -> files it imports)
{dep_summary}

## Output Format

Return markdown with EXACTLY these six sections, in this order, using these exact headings:

### 1. App Type
One sentence: what kind of application is this (web API, full-stack app, CLI, library)? Name the framework(s) (e.g., "FastAPI backend with React/Vite frontend") based on file evidence (e.g. presence of `main.py`, `package.json`, `vite.config.js`).

### 2. Layer Breakdown
Bullet list. One bullet per layer (frontend / backend / database / infra / tests). Each bullet: layer name, 1-line responsibility, and 2-4 representative file paths from THIS repo.

### 3. Entry Points
Bullet list. Each entry: file path · what triggers it (HTTP request, CLI invocation, build script) · what it dispatches to (specific function or router).

### 4. Data Flow
Pick ONE realistic user action this code supports (infer from route names, function names, or file names — e.g. "POST /api/repos creates a repo manifest"). Trace it step by step through the actual files in this repo. Use the format `file:function -> file:function`. 3-6 steps.

### 5. Critical Files
Exactly 3-5 files, ranked by importance. For each: `path` — one sentence on why this file is load-bearing (high dependent count, owns core logic, sole entry point, etc.). Prefer files with many dependents from the graph above.

### 6. Key Patterns
Bullet list of 2-4 patterns OBSERVED in the code (e.g., "Router pattern: `app/routers/*.py` mounted in `main.py`", "Service layer: business logic in `app/services/` separate from HTTP handlers"). Each bullet must cite at least one concrete file/directory.

## Rules
- Be ruthlessly specific. Never write "the API layer handles requests" without naming the file.
- No generic CS lecturing. The reader knows what REST is — tell them how THIS repo does REST.
- If a section has no evidence, write the heading followed by "Not visible from manifest." Do not fabricate.
- Keep it under 600 words total."""


def _summarize_languages(manifest: list[dict]) -> str:
    counts = Counter((f.get("language") or "unknown").lower() for f in manifest)
    parts = [f"{lang}={n}" for lang, n in counts.most_common(6)]
    return ", ".join(parts) if parts else "unknown"


def _top_directories(manifest: list[dict], k: int = 6) -> str:
    dirs = Counter()
    for f in manifest:
        fp = f["file_path"].replace("\\", "/")
        top = fp.split("/", 1)[0] if "/" in fp else "(root)"
        dirs[top] += 1
    parts = [f"{d}={n}" for d, n in dirs.most_common(k)]
    return ", ".join(parts) if parts else "(none)"


async def run_repo_analyzer(state: GitMentorState) -> dict:
    logger.info("[RepoAnalyzer] Starting — repo_id=%s, files=%d", state["repo_id"], len(state["file_manifest"]))

    manifest = state["file_manifest"]
    dep_graph = state["dependency_graph"]

    manifest_lines = [
        f"  {f['file_path']} · {f.get('language') or 'unknown'} · {f.get('line_count', 0)} lines"
        for f in manifest
    ]
    manifest_summary = "\n".join(manifest_lines) or "  (none)"

    dep_lines = []
    edge_count = 0
    for fp, info in dep_graph.items():
        deps = info.get("dependencies", [])
        if deps:
            dep_lines.append(f"  {fp} -> {', '.join(deps)}")
            edge_count += len(deps)
    dep_summary = "\n".join(dep_lines) if dep_lines else "  (no dependency data available)"

    prompt = _PROMPT_TEMPLATE.format(
        file_count=len(manifest),
        dep_edge_count=edge_count,
        lang_distribution=_summarize_languages(manifest),
        top_dirs=_top_directories(manifest),
        manifest_summary=manifest_summary,
        dep_summary=dep_summary,
    )

    llm = GroqProvider(model=settings.repo_analyzer_model)
    try:
        overview = await llm.generate(prompt, system=_SYSTEM, temperature=0.2)
        logger.info("[RepoAnalyzer] Produced overview (%d chars)", len(overview))
        return {"architecture_overview": overview, "status": "repo_analyzed", "errors": []}
    except Exception as exc:
        logger.error("[RepoAnalyzer] LLM call failed: %s", exc)
        return {
            "architecture_overview": "Architecture analysis failed — see errors.",
            "status": "repo_analyzer_failed",
            "errors": [f"RepoAnalyzer failed: {exc}"],
        }

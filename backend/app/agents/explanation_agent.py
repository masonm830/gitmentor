import logging

from app.agents.state import GitMentorState
from app.config import settings
from app.llm.claude_provider import ClaudeProvider
from app.services.supabase import get_chunks_for_file

logger = logging.getLogger(__name__)

_SYSTEM = (
    "You are a senior engineer briefing a developer who is about to be interviewed about THIS specific file. "
    "Every claim must be traceable to a function name, class name, import, or dependency edge listed in the "
    "prompt. Do not invent symbols. If something is not in the inputs, say so explicitly. "
    "Output only the markdown answer — no preamble, no fences."
)

_PROMPT_TEMPLATE = """Brief a developer on this file for a technical interview.

## File: {file_path} ({language}, {line_count} lines)
Role in repo: this is one of {total_files} files. The dependency graph below shows where it sits.

## Parsed Structure
Functions: {functions}
Classes: {classes}
Imports (first 10): {imports}

## Role in Dependency Graph
This file imports from: {dependencies}
This file is imported by: {dependents}

## Code Chunks from This File (function/class bodies, previewed)
{chunks}

## Architecture Context (excerpt)
{arch_excerpt}

## Output Format

Return markdown with EXACTLY these four sections, in order:

### What it does
2-3 sentences. Name the specific functions/classes (e.g., `clone_and_analyze()` clones the repo and walks the tree). No generic descriptions.

### Why it exists
2-3 sentences on the problem this file solves in THIS codebase. Reference the dependents above — what would those files be unable to do without this one? If no dependents, say "Standalone entry point" or "Leaf utility" and justify.

### What breaks if deleted
Bullet list. For each dependent above, name one concrete capability that breaks (e.g., "`app/routers/repos.py` loses access to `clone_and_analyze` and `POST /api/repos` cannot ingest repos"). If there are zero dependents, write "No internal callers; deletion would only affect external invocations."

### Key implementation details
2-4 bullets. Each bullet calls out something a senior interviewer would probe: a non-trivial algorithm, a side effect (writes to disk, mutates state, calls external API), an error-handling choice, a concurrency primitive, or an unusual import. Cite the specific function or line where it appears. Avoid restating obvious things.

## Rules
- Reference real names only. If you don't see it in the inputs, don't mention it.
- Keep total response under 350 words.
- No "this file appears to..." hedging — be direct."""

_KEEP_EXTENSIONS = {"py", "js", "ts", "jsx", "tsx"}
_KEEP_LANGUAGES = {"python", "javascript", "typescript"}
_MAX_ARCH_EXCERPT_CHARS = 800
_MAX_CHUNK_PREVIEW_CHARS = 400
_MAX_CHUNKS_PER_FILE = 4


def _should_explain(file_path: str, language: str | None) -> bool:
    if language and language.lower() in _KEEP_LANGUAGES:
        return True
    ext = file_path.rsplit(".", 1)[-1].lower() if "." in file_path else ""
    return ext in _KEEP_EXTENSIONS


def _format_chunks(rows: list[dict]) -> str:
    if not rows:
        return "(no chunks stored for this file — run POST /embed first for better explanations)"
    parts = []
    for row in rows[:_MAX_CHUNKS_PER_FILE]:
        meta = row.get("metadata") or {}
        name = meta.get("function_name") or meta.get("class_name") or row.get("chunk_type", "chunk")
        body = (row.get("text") or "")[:_MAX_CHUNK_PREVIEW_CHARS]
        parts.append(f"[{row.get('chunk_type')}: {name}]\n{body}")
    return "\n\n".join(parts)


async def run_explanation_agent(state: GitMentorState) -> dict:
    repo_id = state["repo_id"]
    manifest_count = len(state["file_manifest"])
    parsed_count = len(state["parsed_files"])
    logger.info(
        "[ExplanationAgent] Starting — repo_id=%s, manifest_files=%d, parsed_files=%d",
        repo_id, manifest_count, parsed_count,
    )

    # Normalize file_path keys to forward slashes — existing parsed_files JSONB rows from
    # Windows-clone runs may have stored backslashes inside raw_parsed_data, which breaks
    # dict lookups against the (forward-slash-normalized) files table.
    parsed_by_path = {p["file_path"].replace("\\", "/"): p for p in state["parsed_files"]}
    manifest_by_path = {f["file_path"]: f for f in state["file_manifest"]}
    dep_graph = state["dependency_graph"]
    arch_excerpt = (state.get("architecture_overview") or "")[:_MAX_ARCH_EXCERPT_CHARS] or "(architecture overview not available)"
    total_files = len(state["file_manifest"])
    llm = ClaudeProvider(model=settings.explanation_agent_model)
    explanations: dict[str, str] = {}
    errors: list[str] = []
    skipped_not_explainable = 0
    skipped_no_parsed = 0
    attempted = 0

    logger.info(
        "[ExplanationAgent] parsed_by_path sample keys: %s",
        list(parsed_by_path.keys())[:5],
    )
    logger.info(
        "[ExplanationAgent] manifest sample paths: %s",
        [f["file_path"] for f in state["file_manifest"][:5]],
    )

    for file_info in state["file_manifest"]:
        fp = file_info["file_path"]
        lang = file_info.get("language")

        if not _should_explain(fp, lang):
            skipped_not_explainable += 1
            continue

        parsed = parsed_by_path.get(fp)
        if not parsed:
            skipped_no_parsed += 1
            logger.warning("[ExplanationAgent] %s passed language filter but has no parsed entry", fp)
            continue

        attempted += 1

        try:
            chunk_rows = await get_chunks_for_file(repo_id, fp, limit=_MAX_CHUNKS_PER_FILE * 2)
            logger.info("[ExplanationAgent] %s — fetched %d chunks", fp, len(chunk_rows))
        except Exception as exc:
            logger.warning("[ExplanationAgent] Chunk fetch failed for %s: %s", fp, exc)
            chunk_rows = []

        chunk_text = _format_chunks(chunk_rows)

        dep_info = dep_graph.get(fp, {})
        funcs = [f["name"] for f in parsed.get("functions", [])]
        classes = [c["name"] for c in parsed.get("classes", [])]
        imports = [i.get("module", "") for i in parsed.get("imports", [])]
        manifest_entry = manifest_by_path.get(fp, {})

        prompt = _PROMPT_TEMPLATE.format(
            file_path=fp,
            language=lang or "unknown",
            line_count=manifest_entry.get("line_count", 0),
            total_files=total_files,
            functions=", ".join(funcs) if funcs else "(none)",
            classes=", ".join(classes) if classes else "(none)",
            imports=", ".join(imports[:10]) if imports else "(none)",
            dependencies=", ".join(dep_info.get("dependencies", [])) or "(none)",
            dependents=", ".join(dep_info.get("dependents", [])) or "(none)",
            chunks=chunk_text,
            arch_excerpt=arch_excerpt,
        )

        try:
            explanation = await llm.generate(prompt, system=_SYSTEM, temperature=0.2)
            explanations[fp] = explanation
            logger.info("[ExplanationAgent] Explained %s (%d chars)", fp, len(explanation))
        except Exception as exc:
            logger.exception("[ExplanationAgent] LLM call failed for %s", fp)
            explanations[fp] = f"Explanation failed: {exc}"
            errors.append(f"ExplanationAgent failed on {fp}: {exc}")

    logger.info(
        "[ExplanationAgent] Complete — attempted=%d, explained=%d, skipped_not_explainable=%d, "
        "skipped_no_parsed=%d, errors=%d",
        attempted, len(explanations), skipped_not_explainable, skipped_no_parsed, len(errors),
    )
    return {"file_explanations": explanations, "status": "explanations_done", "errors": errors}

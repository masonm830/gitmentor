import json
import logging
import re

from app.agents.state import GitMentorState
from app.config import settings
from app.llm.groq_provider import GroqProvider

logger = logging.getLogger(__name__)

_CONFIG_NAMES = frozenset({
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock",
    "requirements.txt", ".gitignore", ".eslintrc", ".prettierrc", ".eslintrc.json",
    ".prettierrc.json", "vercel.json", "netlify.toml", "docker-compose.yml",
    "docker-compose.yaml", "Dockerfile", ".env.example", ".env",
    "tsconfig.json", "vite.config.ts", "vite.config.js", "next.config.js",
    "tailwind.config.js", "postcss.config.js", "babel.config.js",
    "jest.config.js", "webpack.config.js",
})

_CONFIG_EXTENSIONS = frozenset({
    ".lock", ".toml", ".yaml", ".yml", ".ini", ".cfg", ".conf",
    ".env", ".editorconfig",
})

_GENERATED_PATH_KEYWORDS = frozenset({"migrations", "__pycache__", "node_modules", "dist", "build", ".next", "generated"})

_SYSTEM = (
    "You are a code analyst classifying source files as AI-generated, hand-written, or AI-generated then "
    "modified. You see structural signals only (no source code). Reason from the signals provided. "
    "Respond with valid JSON only — no prose, no markdown fences."
)

_BATCH_PROMPT_TEMPLATE = """Classify each source file as generated, handwritten, or modified.

## Definitions
- "generated": AI-generated or auto-scaffolded with no meaningful manual editing (uniform style, near-zero docstrings, formulaic naming).
- "handwritten": written primarily by a human (varied naming, partial docs, opinionated structure).
- "modified": AI-generated base subsequently edited by a human (mixed signals — uneven docstring coverage, some files have rich naming while others are formulaic).

## Heuristics (apply ONLY to the signals shown; do not assume info you don't have)
- `no_doc_ratio` ≥ 0.9 AND `function_count` ≥ 3 -> lean "generated" (uniform doc-free output).
- `no_doc_ratio` between 0.4 and 0.8 -> lean "modified" (partial human touch-ups).
- `no_doc_ratio` ≤ 0.3 AND `function_count` ≥ 2 -> lean "handwritten" (human-authored docs).
- `function_count` = 0 AND `line_count` > 80 -> lean "generated" (scaffolded module with declarations only).
- `function_count` = 0 AND `line_count` ≤ 30 -> lean "handwritten" (small intentional utility / re-export).
- Test files (path contains `tests/`, `test_`, `.test.`, `.spec.`) -> usually "handwritten" unless `no_doc_ratio` ≥ 0.9.
- `__init__.py` with `line_count` ≤ 10 -> "handwritten" with confidence 0.6 (package marker, not meaningful signal).
- When signals conflict, classify as "modified" with confidence ≤ 0.6.

## Confidence
- Confidence 0.85+ only when two or more heuristics align.
- Confidence ≤ 0.5 when only one weak signal supports the classification.

## File signals
| file_path | ext | functions | docstrings | lines | no_doc_ratio | is_test | is_init |
{signal_rows}

## Output
Return JSON shaped exactly:
{{"classifications": [
  {{"file_path": "...", "classification": "generated|handwritten|modified", "confidence": 0.0, "reason": "1 short sentence citing the specific signals used"}}
]}}
The "reason" field MUST name the signal(s) that drove the decision (e.g., "no_doc_ratio=0.95 with 7 functions"). Return nothing else."""


def _basename(fp: str) -> str:
    return fp.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]


def _is_config_file(fp: str) -> bool:
    name = _basename(fp).lower()
    if name in _CONFIG_NAMES:
        return True
    for part in fp.replace("\\", "/").split("/"):
        if part in _GENERATED_PATH_KEYWORDS:
            return True
    ext = "." + fp.rsplit(".", 1)[-1].lower() if "." in fp else ""
    return ext in _CONFIG_EXTENSIONS


def _is_test_file(fp: str) -> bool:
    norm = fp.replace("\\", "/").lower()
    base = _basename(norm)
    return (
        "/tests/" in norm
        or "/test/" in norm
        or "/__tests__/" in norm
        or base.startswith("test_")
        or ".test." in base
        or ".spec." in base
    )


def _compute_signals(file_info: dict, parsed: dict | None) -> dict:
    functions = parsed.get("functions", []) if parsed else []
    function_count = len(functions)
    docstring_count = sum(1 for f in functions if f.get("docstring"))
    no_doc_ratio = round(1.0 - docstring_count / max(function_count, 1), 2)
    fp = file_info["file_path"]
    ext = fp.rsplit(".", 1)[-1].lower() if "." in fp else ""
    return {
        "file_path": fp,
        "ext": ext or "(none)",
        "function_count": function_count,
        "docstring_count": docstring_count,
        "line_count": file_info.get("line_count", 0),
        "no_doc_ratio": no_doc_ratio,
        "is_test": _is_test_file(fp),
        "is_init": _basename(fp) == "__init__.py",
    }


def _extract_json_object(text: str) -> str:
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", text)
    if fence:
        text = fence.group(1).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start : end + 1]
    return text


async def _llm_classify(signals: list[dict], llm: GroqProvider) -> list[dict]:
    rows = "\n".join(
        f"| {s['file_path']} | {s['ext']} | {s['function_count']} | {s['docstring_count']} | "
        f"{s['line_count']} | {s['no_doc_ratio']} | {str(s['is_test']).lower()} | {str(s['is_init']).lower()} |"
        for s in signals
    )
    prompt = _BATCH_PROMPT_TEMPLATE.format(signal_rows=rows)
    raw = await llm.generate(prompt, system=_SYSTEM, temperature=0.0)
    parsed = json.loads(_extract_json_object(raw))
    return parsed.get("classifications", [])


async def run_gap_detector(state: GitMentorState) -> dict:
    logger.info("[GapDetector] Starting — repo_id=%s, files=%d", state["repo_id"], len(state["file_manifest"]))

    parsed_by_path = {p["file_path"].replace("\\", "/"): p for p in state["parsed_files"]}
    gap_analysis: dict[str, dict] = {}
    to_classify: list[dict] = []
    errors: list[str] = []

    for file_info in state["file_manifest"]:
        fp = file_info["file_path"]

        if _is_config_file(fp):
            gap_analysis[fp] = {
                "classification": "generated",
                "confidence": 0.95,
                "reason": "Config, lock, or auto-generated file type.",
            }
            continue

        signals = _compute_signals(file_info, parsed_by_path.get(fp))
        to_classify.append(signals)

    logger.info("[GapDetector] %d config files classified directly, %d sent to LLM", len(gap_analysis), len(to_classify))

    if to_classify:
        llm = GroqProvider(model=settings.gap_detector_model)
        batch_size = 30
        for i in range(0, len(to_classify), batch_size):
            batch = to_classify[i : i + batch_size]
            try:
                results = await _llm_classify(batch, llm)
                returned_paths = set()
                for item in results:
                    fp = item.get("file_path")
                    if not fp:
                        continue
                    returned_paths.add(fp)
                    gap_analysis[fp] = {
                        "classification": item.get("classification", "unknown"),
                        "confidence": float(item.get("confidence", 0.5)),
                        "reason": item.get("reason", ""),
                    }
                # Backfill any files the LLM skipped so downstream consumers don't get holes.
                for s in batch:
                    if s["file_path"] not in returned_paths:
                        gap_analysis[s["file_path"]] = {
                            "classification": "unknown",
                            "confidence": 0.0,
                            "reason": "LLM omitted this file from its response.",
                        }
                logger.info("[GapDetector] LLM classified batch of %d files", len(results))
            except Exception as exc:
                logger.error("[GapDetector] LLM batch failed: %s", exc)
                errors.append(f"GapDetector batch failed: {exc}")
                for s in batch:
                    gap_analysis[s["file_path"]] = {
                        "classification": "unknown",
                        "confidence": 0.0,
                        "reason": f"Classification failed: {exc}",
                    }

    logger.info("[GapDetector] Complete — classified %d files, %d errors", len(gap_analysis), len(errors))
    return {"gap_analysis": gap_analysis, "errors": errors}

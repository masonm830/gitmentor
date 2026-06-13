import logging

from supabase import create_client, Client

from app.config import settings
from app.models.schemas import RepoManifest, ParsedFile, DependencyGraph, CodeChunk

logger = logging.getLogger(__name__)

_client: Client | None = None


def get_client() -> Client:
    global _client
    if _client is None:
        logger.info("Supabase URL: %s", settings.supabase_url)
        key = settings.supabase_service_key
        logger.info("Supabase key prefix: %s...", key[:12])
        # service_role keys start with "eyJhbGciOi..." and decode to role=service_role
        # anon keys look identical but decode to role=anon — check Supabase dashboard if unsure
        _client = create_client(settings.supabase_url, key)
    return _client


def verify_connection() -> None:
    """SELECT from repos at startup to confirm Supabase is reachable and RLS isn't blocking."""
    try:
        client = get_client()
        result = client.table("repos").select("id").limit(1).execute()
        logger.info("Supabase connection OK — repos query returned %d rows", len(result.data))
    except Exception as e:
        logger.error("Supabase connection FAILED: %s", e)
        raise


async def store_manifest(manifest: RepoManifest) -> None:
    client = get_client()

    client.table("repos").insert({
        "id": manifest.repo_id,
        "github_url": manifest.github_url,
        "name": manifest.name,
        "owner": manifest.owner,
        "cloned_at": manifest.cloned_at.isoformat(),
        "status": manifest.status,
    }).execute()

    if manifest.files:
        file_rows = [
            {
                "repo_id": manifest.repo_id,
                "file_path": f.file_path.replace("\\", "/"),
                "language": f.language,
                "line_count": f.line_count,
                "last_modified": f.last_modified.isoformat(),
            }
            for f in manifest.files
        ]
        client.table("files").insert(file_rows).execute()


async def get_repo(repo_id: str) -> dict | None:
    client = get_client()
    result = client.table("repos").select("*").eq("id", repo_id).execute()
    return result.data[0] if result.data else None


async def update_repo_status(repo_id: str, status: str) -> None:
    """Flip repos.status. Called by /full-analysis after the LangGraph pipeline
    completes so the dashboard can distinguish 'pending' (manifest only) from
    'analyzed' (full pipeline done)."""
    client = get_client()
    client.table("repos").update({"status": status}).eq("id", repo_id).execute()


async def list_repos_by_owner(owner: str) -> list[dict]:
    """Used by Phase 6 dashboard to show 'Your Repositories' for the logged-in user."""
    client = get_client()
    result = (
        client.table("repos")
        .select("*")
        .eq("owner", owner)
        .order("cloned_at", desc=True)
        .execute()
    )
    return result.data or []


async def get_latest_analysis_for_repo(repo_id: str) -> dict | None:
    """Latest analysis row for a repo. Powers the Phase 6 analysis view."""
    client = get_client()
    result = (
        client.table("analyses")
        .select("*")
        .eq("repo_id", repo_id)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None


async def get_files_for_repo(repo_id: str) -> list[dict]:
    client = get_client()
    result = client.table("files").select("*").eq("repo_id", repo_id).execute()
    return result.data


async def store_parsed_files(repo_id: str, parsed_files: list[ParsedFile]) -> None:
    client = get_client()
    rows = []
    for pf in parsed_files:
        normalized = pf.file_path.replace("\\", "/")
        raw = pf.model_dump(mode="json")
        # Normalize the file_path INSIDE the JSONB blob too — agents downstream key off this field
        # and a backslash here breaks dict lookups against the (already-normalized) files table.
        raw["file_path"] = normalized
        rows.append({
            "repo_id": repo_id,
            "file_path": normalized,
            "language": pf.language,
            "function_count": len(pf.functions),
            "class_count": len(pf.classes),
            "import_count": len(pf.imports),
            "raw_parsed_data": raw,
        })
    if rows:
        client.table("parsed_files").insert(rows).execute()


async def store_dependencies(repo_id: str, graph: DependencyGraph) -> None:
    client = get_client()
    rows = []
    for node in graph.nodes.values():
        for dep in node.dependencies:
            rows.append({
                "repo_id": repo_id,
                "source_file": node.file_path,
                "target_file": dep,
            })
    if rows:
        client.table("dependencies").insert(rows).execute()


async def get_parsed_file(repo_id: str, file_path: str) -> dict | None:
    client = get_client()
    result = (
        client.table("parsed_files")
        .select("*")
        .eq("repo_id", repo_id)
        .eq("file_path", file_path)
        .execute()
    )
    return result.data[0] if result.data else None


async def get_dependencies_for_file(repo_id: str, file_path: str) -> tuple[list[str], list[str]]:
    client = get_client()
    deps_result = (
        client.table("dependencies")
        .select("target_file")
        .eq("repo_id", repo_id)
        .eq("source_file", file_path)
        .execute()
    )
    dependents_result = (
        client.table("dependencies")
        .select("source_file")
        .eq("repo_id", repo_id)
        .eq("target_file", file_path)
        .execute()
    )
    dependencies = [r["target_file"] for r in deps_result.data]
    dependents = [r["source_file"] for r in dependents_result.data]
    return dependencies, dependents


async def get_parsed_files_for_repo(repo_id: str) -> list[dict]:
    client = get_client()
    result = client.table("parsed_files").select("*").eq("repo_id", repo_id).execute()
    return result.data


async def delete_chunks_for_repo(repo_id: str) -> None:
    client = get_client()
    client.table("code_chunks").delete().eq("repo_id", repo_id).execute()


async def get_dependency_graph_for_repo(repo_id: str) -> dict:
    """Returns {file_path: {dependencies: [...], dependents: [...]}} built from the dependencies table."""
    client = get_client()
    result = (
        client.table("dependencies")
        .select("source_file, target_file")
        .eq("repo_id", repo_id)
        .execute()
    )
    graph: dict[str, dict] = {}
    for row in result.data:
        source, target = row["source_file"], row["target_file"]
        for fp in (source, target):
            if fp not in graph:
                graph[fp] = {"dependencies": [], "dependents": []}
        graph[source]["dependencies"].append(target)
        graph[target]["dependents"].append(source)
    return graph


async def store_analysis(repo_id: str, state: dict) -> str:
    client = get_client()
    result = (
        client.table("analyses")
        .insert({
            "repo_id": repo_id,
            "architecture_overview": state.get("architecture_overview", ""),
            "file_explanations": state.get("file_explanations", {}),
            "interview_questions": state.get("interview_questions", []),
            "gap_analysis": state.get("gap_analysis", {}),
            "status": state.get("status", "complete"),
            "errors": state.get("errors", []),
        })
        .execute()
    )
    return result.data[0]["id"]


async def get_chunks_for_file(repo_id: str, file_path: str, limit: int = 8) -> list[dict]:
    """Return code_chunks rows for a single file, preferring functions/classes over file_summary."""
    client = get_client()
    result = (
        client.table("code_chunks")
        .select("id, file_path, chunk_type, text, metadata")
        .eq("repo_id", repo_id)
        .eq("file_path", file_path)
        .limit(limit)
        .execute()
    )
    order = {"function": 0, "class": 1, "file_summary": 2}
    return sorted(result.data, key=lambda r: order.get(r.get("chunk_type", ""), 99))


async def get_analysis(analysis_id: str) -> dict | None:
    client = get_client()
    result = client.table("analyses").select("*").eq("id", analysis_id).execute()
    return result.data[0] if result.data else None


async def create_interview_session_rows(
    session_id: str,
    repo_id: str,
    analysis_id: str,
    questions: list[dict],
) -> None:
    """Pre-create one row per question so /evaluate can do a deterministic UPDATE later."""
    if not questions:
        return
    client = get_client()
    rows = [
        {
            "session_id": session_id,
            "repo_id": repo_id,
            "analysis_id": analysis_id,
            "question_index": idx,
            "question_text": q.get("question", ""),
        }
        for idx, q in enumerate(questions)
    ]
    client.table("interview_sessions").insert(rows).execute()


async def get_interview_session_row(session_id: str, question_index: int) -> dict | None:
    client = get_client()
    result = (
        client.table("interview_sessions")
        .select("*")
        .eq("session_id", session_id)
        .eq("question_index", question_index)
        .execute()
    )
    return result.data[0] if result.data else None


async def update_interview_evaluation(
    session_id: str,
    question_index: int,
    user_answer: str,
    evaluation: dict,
) -> None:
    client = get_client()
    (
        client.table("interview_sessions")
        .update({"user_answer": user_answer, "evaluation": evaluation})
        .eq("session_id", session_id)
        .eq("question_index", question_index)
        .execute()
    )


async def store_eval_run(report: dict) -> str:
    """Insert a Phase 7 EvalReport row. Returns the new row id."""
    client = get_client()
    row = {
        "pass_rate": report["pass_rate"],
        "avg_overall": report["avg_overall"],
        "avg_accuracy": report["avg_accuracy"],
        "avg_completeness": report["avg_completeness"],
        "avg_depth": report["avg_depth"],
        "avg_semantic_similarity": report["avg_semantic_similarity"],
        "avg_latency_seconds": report["avg_latency_seconds"],
        "total_entries": report["total_entries"],
        "passed": report["passed"],
        "failed": report["failed"],
        "per_entry_results": report["per_entry_results"],
        "notes": report.get("notes"),
    }
    result = client.table("eval_runs").insert(row).execute()
    return result.data[0]["id"]


async def list_recent_eval_runs(limit: int = 10) -> list[dict]:
    """Most recent eval_runs rows, newest first. Powers the /eval dashboard."""
    client = get_client()
    result = (
        client.table("eval_runs")
        .select("*")
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return result.data or []


async def store_code_chunks(chunks: list[CodeChunk], embeddings: list[list[float]]) -> int:
    client = get_client()
    rows = []
    for chunk, emb in zip(chunks, embeddings):
        if not emb:
            continue
        rows.append({
            "id": chunk.chunk_id,
            "repo_id": chunk.repo_id,
            "file_path": chunk.file_path.replace("\\", "/"),
            "chunk_type": chunk.chunk_type,
            "text": chunk.text,
            "metadata": chunk.metadata,
            "embedding": emb,
        })

    stored = 0
    batch_size = 50
    for i in range(0, len(rows), batch_size):
        batch = rows[i : i + batch_size]
        client.table("code_chunks").insert(batch).execute()
        stored += len(batch)

    return stored

import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query

from app.agents.graph import build_graph
from app.agents.state import GitMentorState
from app.models.schemas import (
    RepoRequest, RepoManifest, AnalyzeResponse, FileParseSummary,
    FileDependencyResponse, FunctionDef, ParsedFile,
    EmbedResponse, SearchQuery, SearchResponse,
    FullAnalysisResponse,
)
from app.services.github import clone_and_analyze, ensure_clone
from app.services.ast_parser import parse_file, should_skip_file
from app.services.dependency_graph import build_dependency_graph
from app.services.chunker import chunk_file
from app.services.embedder import embed_texts
from app.services.rag import search_chunks
from app.services import supabase as db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")


@router.post("/repos", response_model=RepoManifest)
async def create_repo(request: RepoRequest):
    if "github.com" not in request.github_url:
        raise HTTPException(status_code=400, detail="URL must be a GitHub repository")

    manifest = await clone_and_analyze(request.github_url)
    await db.store_manifest(manifest)
    return manifest


@router.get("/repos")
async def list_repos(owner: str = Query(..., description="GitHub username — filters repos by owner")):
    """List previously analyzed repos for a given owner. Powers the dashboard."""
    rows = await db.list_repos_by_owner(owner)
    # Annotate each repo with whether it has a stored analysis yet.
    enriched: list[dict] = []
    for row in rows:
        latest = await db.get_latest_analysis_for_repo(row["id"])
        enriched.append({
            **row,
            "has_analysis": latest is not None,
            "latest_analysis_id": latest["id"] if latest else None,
            "latest_analyzed_at": latest["created_at"] if latest else None,
        })
    return {"repos": enriched}


@router.get("/repos/{repo_id}/analysis")
async def get_latest_analysis(repo_id: str):
    """Latest stored analysis for a repo — feeds the three-panel analysis view."""
    repo = await db.get_repo(repo_id)
    if not repo:
        raise HTTPException(status_code=404, detail="Repo not found")
    analysis = await db.get_latest_analysis_for_repo(repo_id)
    if not analysis:
        raise HTTPException(status_code=404, detail="No analysis stored for this repo yet")
    parsed_rows = await db.get_parsed_files_for_repo(repo_id)
    parsed_index = {r["file_path"]: r.get("raw_parsed_data", {}) for r in parsed_rows}
    return {
        "repo": repo,
        "analysis": analysis,
        "parsed_files": parsed_index,
    }


@router.post("/repos/{repo_id}/analyze", response_model=AnalyzeResponse)
async def analyze_repo(repo_id: str):
    repo = await db.get_repo(repo_id)
    if not repo:
        raise HTTPException(status_code=404, detail="Repo not found")

    clone_dir = await ensure_clone(repo_id, repo["github_url"])

    file_rows = await db.get_files_for_repo(repo_id)
    all_file_paths = [r["file_path"] for r in file_rows]

    parsed_files = []
    for row in file_rows:
        fp = row["file_path"].replace("\\", "/")
        full_path = clone_dir / fp
        file_size = full_path.stat().st_size if full_path.exists() else 0

        if should_skip_file(fp, file_size, row.get("language")):
            continue

        if not full_path.exists():
            continue

        content = full_path.read_bytes()
        result = parse_file(fp, content)
        if result:
            parsed_files.append(result)

    graph = build_dependency_graph(repo_id, parsed_files, all_file_paths)

    await db.store_parsed_files(repo_id, parsed_files)
    await db.store_dependencies(repo_id, graph)

    total_deps = sum(len(n.dependencies) for n in graph.nodes.values())

    summaries = [
        FileParseSummary(
            file_path=pf.file_path,
            language=pf.language,
            function_count=len(pf.functions),
            class_count=len(pf.classes),
            import_count=len(pf.imports),
        )
        for pf in parsed_files
    ]

    return AnalyzeResponse(
        repo_id=repo_id,
        total_files_parsed=len(parsed_files),
        total_dependencies=total_deps,
        files=summaries,
    )


@router.get("/repos/{repo_id}/dependencies", response_model=FileDependencyResponse)
async def get_file_dependencies(
    repo_id: str,
    file_path: str = Query(..., description="Path of the file to query"),
):
    repo = await db.get_repo(repo_id)
    if not repo:
        raise HTTPException(status_code=404, detail="Repo not found")

    file_path = file_path.replace("\\", "/")

    dependencies, dependents = await db.get_dependencies_for_file(repo_id, file_path)

    parsed = await db.get_parsed_file(repo_id, file_path)
    functions = []
    if parsed and parsed.get("raw_parsed_data"):
        raw = parsed["raw_parsed_data"]
        functions = [
            FunctionDef(**f) for f in raw.get("functions", [])
        ]

    return FileDependencyResponse(
        file_path=file_path,
        dependencies=dependencies,
        dependents=dependents,
        functions=functions,
    )


@router.post("/repos/{repo_id}/embed", response_model=EmbedResponse)
async def embed_repo(repo_id: str):
    repo = await db.get_repo(repo_id)
    if not repo:
        raise HTTPException(status_code=404, detail="Repo not found")

    clone_dir = await ensure_clone(repo_id, repo["github_url"])

    parsed_rows = await db.get_parsed_files_for_repo(repo_id)
    if not parsed_rows:
        raise HTTPException(status_code=400, detail="No parsed files — run POST /api/repos/{repo_id}/analyze first")

    await db.delete_chunks_for_repo(repo_id)

    all_chunks = []
    for row in parsed_rows:
        raw = row.get("raw_parsed_data", {})
        parsed = ParsedFile(**raw)
        fp = clone_dir / parsed.file_path
        if not fp.exists():
            continue
        raw_content = fp.read_text(encoding="utf-8", errors="ignore")
        file_chunks = chunk_file(repo_id, parsed, raw_content)
        all_chunks.extend(file_chunks)

    if not all_chunks:
        return EmbedResponse(repo_id=repo_id, total_chunks=0)

    texts = [c.text for c in all_chunks]
    embeddings = embed_texts(texts)

    stored = await db.store_code_chunks(all_chunks, embeddings)
    logger.info("Embedded %d chunks for repo %s", stored, repo_id)

    return EmbedResponse(repo_id=repo_id, total_chunks=stored)


@router.post("/repos/{repo_id}/search", response_model=SearchResponse)
async def search_repo(repo_id: str, body: SearchQuery):
    repo = await db.get_repo(repo_id)
    if not repo:
        raise HTTPException(status_code=404, detail="Repo not found")

    results = await search_chunks(repo_id, body.query)

    return SearchResponse(
        repo_id=repo_id,
        query=body.query,
        results=results,
    )


@router.post("/repos/{repo_id}/full-analysis", response_model=FullAnalysisResponse)
async def full_analysis(repo_id: str):
    """Runs the full LangGraph multi-agent pipeline and stores results.

    Pipeline: RepoAnalyzer -> ExplanationAgent -> (QuestionGenerator || GapDetector)
    Expected runtime: 30-60 seconds.
    Prerequisites: POST /analyze and POST /embed must have been run first.
    """
    repo = await db.get_repo(repo_id)
    if not repo:
        raise HTTPException(status_code=404, detail="Repo not found")

    file_manifest = await db.get_files_for_repo(repo_id)
    parsed_rows = await db.get_parsed_files_for_repo(repo_id)
    dep_graph = await db.get_dependency_graph_for_repo(repo_id)

    if not parsed_rows:
        raise HTTPException(
            status_code=400,
            detail="No parsed files — run POST /api/repos/{repo_id}/analyze first",
        )

    parsed_files = [row["raw_parsed_data"] for row in parsed_rows if row.get("raw_parsed_data")]

    repo_metadata = {
        "github_url": repo.get("github_url", ""),
        "name": repo.get("name", ""),
        "owner": repo.get("owner", ""),
    }

    initial_state: GitMentorState = {
        "repo_id": repo_id,
        "repo_metadata": repo_metadata,
        "file_manifest": file_manifest,
        "dependency_graph": dep_graph,
        "parsed_files": parsed_files,
        "architecture_overview": "",
        "file_explanations": {},
        "interview_questions": [],
        "gap_analysis": {},
        "errors": [],
        "status": "starting",
    }

    logger.info(
        "[FullAnalysis] Starting pipeline — repo_id=%s, files=%d, parsed=%d, dep_nodes=%d",
        repo_id, len(file_manifest), len(parsed_files), len(dep_graph),
    )
    graph = build_graph()
    final_state = await graph.ainvoke(initial_state)
    logger.info(
        "[FullAnalysis] Pipeline complete — status=%s, explanations=%d, questions=%d, gap_files=%d, errors=%d",
        final_state.get("status"),
        len(final_state.get("file_explanations", {})),
        len(final_state.get("interview_questions", [])),
        len(final_state.get("gap_analysis", {})),
        len(final_state.get("errors", [])),
    )

    try:
        analysis_id = await db.store_analysis(repo_id, final_state)
    except Exception as exc:
        logger.exception("[FullAnalysis] Failed to persist analysis")
        raise HTTPException(status_code=500, detail=f"Pipeline ran but persisting result failed: {exc}")

    await db.update_repo_status(repo_id, "analyzed")

    return FullAnalysisResponse(
        analysis_id=analysis_id,
        repo_id=repo_id,
        architecture_overview=final_state.get("architecture_overview", ""),
        file_explanations=final_state.get("file_explanations", {}),
        interview_questions=final_state.get("interview_questions", []),
        gap_analysis=final_state.get("gap_analysis", {}),
        status=final_state.get("status", "complete"),
        errors=final_state.get("errors", []),
    )

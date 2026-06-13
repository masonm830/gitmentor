import logging
import os
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

from git import Repo

from app.config import settings
from app.models.schemas import FileManifestEntry, RepoManifest

logger = logging.getLogger(__name__)

EXTENSION_LANGUAGE_MAP = {
    ".py": "Python",
    ".js": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".jsx": "JavaScript",
    ".java": "Java",
    ".go": "Go",
    ".rs": "Rust",
    ".rb": "Ruby",
    ".php": "PHP",
    ".c": "C",
    ".cpp": "C++",
    ".h": "C",
    ".hpp": "C++",
    ".cs": "C#",
    ".swift": "Swift",
    ".kt": "Kotlin",
    ".scala": "Scala",
    ".r": "R",
    ".sql": "SQL",
    ".html": "HTML",
    ".css": "CSS",
    ".scss": "SCSS",
    ".json": "JSON",
    ".yaml": "YAML",
    ".yml": "YAML",
    ".toml": "TOML",
    ".md": "Markdown",
    ".sh": "Shell",
    ".bash": "Shell",
    ".dockerfile": "Dockerfile",
    ".xml": "XML",
    ".graphql": "GraphQL",
    ".proto": "Protobuf",
    ".lua": "Lua",
    ".dart": "Dart",
    ".ex": "Elixir",
    ".exs": "Elixir",
    ".zig": "Zig",
}


def get_clone_dir(repo_id: str) -> Path:
    return Path(settings.clone_repos_dir) / repo_id


def cleanup_clone(repo_id: str) -> None:
    clone_dir = get_clone_dir(repo_id)
    if clone_dir.exists():
        shutil.rmtree(clone_dir, ignore_errors=True)


def _make_clone_url(github_url: str) -> str:
    if settings.github_token:
        return github_url.replace(
            "https://github.com",
            f"https://{settings.github_token}@github.com",
        )
    return github_url


def detect_language(file_path: str) -> str | None:
    ext = Path(file_path).suffix.lower()
    if Path(file_path).name.lower() == "dockerfile":
        return "Dockerfile"
    return EXTENSION_LANGUAGE_MAP.get(ext)


def parse_github_url(url: str) -> tuple[str, str]:
    url = url.rstrip("/")
    if url.endswith(".git"):
        url = url[:-4]
    parts = url.split("/")
    return parts[-2], parts[-1]


def _walk_files(clone_dir: Path) -> list[FileManifestEntry]:
    files: list[FileManifestEntry] = []
    for root, _dirs, filenames in os.walk(clone_dir):
        if ".git" in Path(root).parts:
            continue
        for filename in filenames:
            full_path = Path(root) / filename
            rel_path = full_path.relative_to(clone_dir).as_posix()
            try:
                line_count = len(full_path.read_text(encoding="utf-8", errors="ignore").splitlines())
            except Exception:
                line_count = 0

            last_modified = datetime.fromtimestamp(
                full_path.stat().st_mtime, tz=timezone.utc
            )

            files.append(
                FileManifestEntry(
                    file_path=rel_path,
                    language=detect_language(rel_path),
                    line_count=line_count,
                    last_modified=last_modified,
                )
            )
    return files


async def clone_and_analyze(github_url: str) -> RepoManifest:
    owner, name = parse_github_url(github_url)
    repo_id = str(uuid.uuid4())
    clone_dir = get_clone_dir(repo_id)
    clone_dir.parent.mkdir(parents=True, exist_ok=True)

    logger.info("Cloning %s to %s", github_url, clone_dir)
    Repo.clone_from(_make_clone_url(github_url), str(clone_dir), depth=1)

    files = _walk_files(clone_dir)

    return RepoManifest(
        repo_id=repo_id,
        github_url=github_url,
        name=name,
        owner=owner,
        cloned_at=datetime.now(timezone.utc),
        status="pending",
        files=files,
    )


async def ensure_clone(repo_id: str, github_url: str) -> Path:
    clone_dir = get_clone_dir(repo_id)
    if clone_dir.exists():
        logger.info("Clone dir exists: %s", clone_dir)
        return clone_dir

    logger.info("Clone dir missing, re-cloning %s to %s", github_url, clone_dir)
    clone_dir.parent.mkdir(parents=True, exist_ok=True)
    Repo.clone_from(_make_clone_url(github_url), str(clone_dir), depth=1)
    return clone_dir

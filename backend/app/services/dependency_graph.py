from collections import defaultdict
from pathlib import PurePosixPath

from app.models.schemas import ParsedFile, DependencyGraph, DependencyNode


def _resolve_python_import(module: str, is_relative: bool, source_file: str, repo_files: set[str]) -> str | None:
    if is_relative:
        source_dir = str(PurePosixPath(source_file).parent)
        module_stripped = module.lstrip(".")
        dots = len(module) - len(module_stripped)
        base = PurePosixPath(source_dir)
        for _ in range(dots - 1):
            base = base.parent
        if module_stripped:
            candidate = str(base / module_stripped.replace(".", "/"))
        else:
            candidate = str(base)
    else:
        candidate = module.replace(".", "/")

    for suffix in (".py", "/__init__.py"):
        path = candidate + suffix
        # Normalize to forward slashes for matching
        path = path.replace("\\", "/")
        if path in repo_files:
            return path

    candidate_norm = candidate.replace("\\", "/")
    if candidate_norm in repo_files:
        return candidate_norm

    return None


def _resolve_js_import(module: str, source_file: str, repo_files: set[str]) -> str | None:
    if not module.startswith("."):
        return None

    source_dir = str(PurePosixPath(source_file).parent)
    resolved = str(PurePosixPath(source_dir) / module)
    resolved = resolved.replace("\\", "/")

    for suffix in ("", ".js", ".jsx", ".ts", ".tsx", "/index.js", "/index.ts", "/index.jsx", "/index.tsx"):
        candidate = resolved + suffix
        if candidate in repo_files:
            return candidate

    return None


def build_dependency_graph(repo_id: str, parsed_files: list[ParsedFile], all_file_paths: list[str]) -> DependencyGraph:
    repo_files = {p.replace("\\", "/") for p in all_file_paths}

    edges: list[tuple[str, str]] = []
    dependents_map: dict[str, list[str]] = defaultdict(list)
    dependencies_map: dict[str, list[str]] = defaultdict(list)

    for pf in parsed_files:
        source = pf.file_path.replace("\\", "/")
        for imp in pf.imports:
            if pf.language == "Python":
                target = _resolve_python_import(imp.module, imp.is_relative, source, repo_files)
            else:
                target = _resolve_js_import(imp.module, source, repo_files)

            if target and target != source:
                edges.append((source, target))
                dependencies_map[source].append(target)
                dependents_map[target].append(source)

    nodes: dict[str, DependencyNode] = {}
    for fp in all_file_paths:
        fp_norm = fp.replace("\\", "/")
        nodes[fp_norm] = DependencyNode(
            file_path=fp_norm,
            dependencies=sorted(set(dependencies_map.get(fp_norm, []))),
            dependents=sorted(set(dependents_map.get(fp_norm, []))),
        )

    return DependencyGraph(repo_id=repo_id, nodes=nodes)

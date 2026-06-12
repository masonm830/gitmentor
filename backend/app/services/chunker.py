import re
import uuid

from app.models.schemas import ParsedFile, CodeChunk


def _sanitize(text: str) -> str:
    text = text.replace("\x00", "")
    text = re.sub(r"[ \t]+\n", "\n", text)
    return text


def _extract_lines(content: str, start: int, end: int) -> str:
    lines = content.splitlines()
    return "\n".join(lines[start - 1 : end])


def chunk_file(repo_id: str, parsed: ParsedFile, raw_content: str) -> list[CodeChunk]:
    chunks: list[CodeChunk] = []

    for func in parsed.functions:
        text = _sanitize(_extract_lines(raw_content, func.line_start, func.line_end))
        if not text.strip():
            continue
        chunks.append(CodeChunk(
            chunk_id=str(uuid.uuid4()),
            repo_id=repo_id,
            file_path=parsed.file_path,
            chunk_type="function",
            text=text,
            metadata={
                "function_name": func.name,
                "language": parsed.language,
                "line_start": func.line_start,
                "line_end": func.line_end,
                "docstring": func.docstring,
            },
        ))

    for cls in parsed.classes:
        text = _sanitize(_extract_lines(raw_content, cls.line_start, cls.line_end))
        if not text.strip():
            continue
        chunks.append(CodeChunk(
            chunk_id=str(uuid.uuid4()),
            repo_id=repo_id,
            file_path=parsed.file_path,
            chunk_type="class",
            text=text,
            metadata={
                "class_name": cls.name,
                "language": parsed.language,
                "line_start": cls.line_start,
                "line_end": cls.line_end,
                "methods": cls.methods,
            },
        ))

    imports_text = "\n".join(
        f"from {imp.module} import {', '.join(imp.names)}" if imp.names
        else f"import {imp.module}"
        for imp in parsed.imports
    )
    summary_parts = []
    if imports_text:
        summary_parts.append(f"Imports:\n{imports_text}")
    func_names = [f.name for f in parsed.functions]
    class_names = [c.name for c in parsed.classes]
    if func_names:
        summary_parts.append(f"Functions: {', '.join(func_names)}")
    if class_names:
        summary_parts.append(f"Classes: {', '.join(class_names)}")

    if summary_parts:
        summary_text = _sanitize(
            f"File: {parsed.file_path} ({parsed.language})\n\n" + "\n\n".join(summary_parts)
        )
        chunks.append(CodeChunk(
            chunk_id=str(uuid.uuid4()),
            repo_id=repo_id,
            file_path=parsed.file_path,
            chunk_type="file_summary",
            text=summary_text,
            metadata={
                "language": parsed.language,
                "function_count": len(parsed.functions),
                "class_count": len(parsed.classes),
                "import_count": len(parsed.imports),
            },
        ))

    return chunks

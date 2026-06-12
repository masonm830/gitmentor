import logging
from pathlib import Path

import tree_sitter_python as tspython
import tree_sitter_javascript as tsjavascript
from tree_sitter import Language, Parser, Node

from app.models.schemas import (
    ParsedFile, FunctionDef, ClassDef, ImportStatement, ExportStatement,
)

logger = logging.getLogger(__name__)

PY_LANGUAGE = Language(tspython.language())
JS_LANGUAGE = Language(tsjavascript.language())

SKIP_DIRS = {"node_modules", ".git", "__pycache__", ".next", "dist", "build", ".venv", "venv"}

SKIP_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg", ".webp", ".bmp",
    ".woff", ".woff2", ".ttf", ".eot",
    ".lock", ".map",
}

SKIP_FILENAMES = {
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
    ".gitignore", ".gitattributes", ".eslintcache",
}

MAX_FILE_SIZE = 50 * 1024


def should_skip_file(file_path: str, file_size: int, language: str | None) -> bool:
    p = Path(file_path)

    if any(part in SKIP_DIRS for part in p.parts):
        return True

    if p.suffix.lower() in SKIP_EXTENSIONS:
        return True

    if p.name in SKIP_FILENAMES:
        return True

    if file_size > MAX_FILE_SIZE and language not in ("Python", "JavaScript", "TypeScript"):
        return True

    return False


def _node_text(node: Node, source: bytes) -> str:
    return source[node.start_byte:node.end_byte].decode("utf-8", errors="ignore")


def _extract_docstring(node: Node, source: bytes) -> str | None:
    body = node.child_by_field_name("body")
    if body and body.child_count > 0:
        first_stmt = body.children[0]
        if first_stmt.type == "expression_statement" and first_stmt.child_count > 0:
            expr = first_stmt.children[0]
            if expr.type == "string":
                raw = _node_text(expr, source)
                return raw.strip("\"'").strip()
    return None


def parse_python(file_path: str, source: bytes) -> ParsedFile:
    parser = Parser(PY_LANGUAGE)
    tree = parser.parse(source)
    root = tree.root_node

    functions: list[FunctionDef] = []
    classes: list[ClassDef] = []
    imports: list[ImportStatement] = []

    for node in root.children:
        if node.type == "function_definition":
            name_node = node.child_by_field_name("name")
            if name_node:
                functions.append(FunctionDef(
                    name=_node_text(name_node, source),
                    line_start=node.start_point[0] + 1,
                    line_end=node.end_point[0] + 1,
                    docstring=_extract_docstring(node, source),
                ))

        elif node.type == "class_definition":
            name_node = node.child_by_field_name("name")
            if name_node:
                methods = []
                body = node.child_by_field_name("body")
                if body:
                    for child in body.children:
                        if child.type == "function_definition":
                            m_name = child.child_by_field_name("name")
                            if m_name:
                                methods.append(_node_text(m_name, source))
                classes.append(ClassDef(
                    name=_node_text(name_node, source),
                    line_start=node.start_point[0] + 1,
                    line_end=node.end_point[0] + 1,
                    methods=methods,
                ))

        elif node.type == "import_statement":
            name_node = node.child_by_field_name("name")
            if name_node:
                imports.append(ImportStatement(
                    module=_node_text(name_node, source),
                    names=[],
                ))

        elif node.type == "import_from_statement":
            module_node = node.child_by_field_name("module_name")
            module_name = _node_text(module_node, source) if module_node else ""
            is_relative = any(c.type == "relative_import" for c in node.children)
            if not is_relative:
                is_relative = module_name.startswith(".")

            names = []
            for child in node.children:
                if child.type == "dotted_name" and child != module_node:
                    names.append(_node_text(child, source))
                elif child.type == "aliased_import":
                    name_child = child.child_by_field_name("name")
                    if name_child:
                        names.append(_node_text(name_child, source))

            imports.append(ImportStatement(
                module=module_name,
                names=names,
                is_relative=is_relative,
            ))

    return ParsedFile(
        file_path=file_path,
        language="Python",
        functions=functions,
        classes=classes,
        imports=imports,
    )


def parse_javascript(file_path: str, source: bytes) -> ParsedFile:
    parser = Parser(JS_LANGUAGE)
    tree = parser.parse(source)
    root = tree.root_node

    functions: list[FunctionDef] = []
    imports: list[ImportStatement] = []
    exports: list[ExportStatement] = []

    def _walk(node: Node) -> None:
        if node.type == "function_declaration":
            name_node = node.child_by_field_name("name")
            if name_node:
                functions.append(FunctionDef(
                    name=_node_text(name_node, source),
                    line_start=node.start_point[0] + 1,
                    line_end=node.end_point[0] + 1,
                ))

        elif node.type in ("lexical_declaration", "variable_declaration"):
            for declarator in node.children:
                if declarator.type == "variable_declarator":
                    name_node = declarator.child_by_field_name("name")
                    value_node = declarator.child_by_field_name("value")
                    if name_node and value_node and value_node.type == "arrow_function":
                        functions.append(FunctionDef(
                            name=_node_text(name_node, source),
                            line_start=node.start_point[0] + 1,
                            line_end=node.end_point[0] + 1,
                        ))

        elif node.type == "import_statement":
            source_node = node.child_by_field_name("source")
            if source_node:
                module = _node_text(source_node, source).strip("\"'")
                names = []
                for child in node.children:
                    if child.type == "import_clause":
                        for spec in child.children:
                            if spec.type == "identifier":
                                names.append(_node_text(spec, source))
                            elif spec.type == "named_imports":
                                for imp_spec in spec.children:
                                    if imp_spec.type == "import_specifier":
                                        n = imp_spec.child_by_field_name("name")
                                        if n:
                                            names.append(_node_text(n, source))
                imports.append(ImportStatement(
                    module=module,
                    names=names,
                    is_relative=module.startswith("."),
                ))

        elif node.type == "export_statement":
            is_default = any(_node_text(c, source) == "default" for c in node.children)
            declaration = node.child_by_field_name("declaration")
            if declaration:
                name_node = declaration.child_by_field_name("name")
                if name_node:
                    exports.append(ExportStatement(
                        name=_node_text(name_node, source),
                        is_default=is_default,
                    ))
                    if declaration.type == "function_declaration":
                        functions.append(FunctionDef(
                            name=_node_text(name_node, source),
                            line_start=declaration.start_point[0] + 1,
                            line_end=declaration.end_point[0] + 1,
                        ))
            elif node.child_by_field_name("value"):
                value = node.child_by_field_name("value")
                if value.type == "identifier":
                    exports.append(ExportStatement(
                        name=_node_text(value, source),
                        is_default=is_default,
                    ))
            else:
                source_child = node.child_by_field_name("source")
                if not source_child:
                    for child in node.children:
                        if child.type == "identifier" and is_default:
                            exports.append(ExportStatement(
                                name=_node_text(child, source),
                                is_default=True,
                            ))
                        elif child.type == "export_clause":
                            for spec in child.children:
                                if spec.type == "export_specifier":
                                    n = spec.child_by_field_name("name")
                                    if n:
                                        exports.append(ExportStatement(
                                            name=_node_text(n, source),
                                            is_default=False,
                                        ))

        for child in node.children:
            _walk(child)

    _walk(root)

    return ParsedFile(
        file_path=file_path,
        language="JavaScript",
        functions=functions,
        imports=imports,
        exports=exports,
    )


def parse_file(file_path: str, content: bytes) -> ParsedFile | None:
    ext = Path(file_path).suffix.lower()
    try:
        if ext == ".py":
            return parse_python(file_path, content)
        elif ext in (".js", ".jsx"):
            return parse_javascript(file_path, content)
        return None
    except Exception:
        logger.exception("AST parse failed for %s", file_path)
        return None

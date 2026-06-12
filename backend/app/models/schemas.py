from pydantic import BaseModel
from datetime import datetime


# --- Phase 1 models ---

class RepoRequest(BaseModel):
    github_url: str


class FileManifestEntry(BaseModel):
    file_path: str
    language: str | None
    line_count: int
    last_modified: datetime


class RepoManifest(BaseModel):
    repo_id: str
    github_url: str
    name: str
    owner: str
    cloned_at: datetime
    status: str
    files: list[FileManifestEntry]


class HealthResponse(BaseModel):
    status: str
    version: str


# --- Phase 2 models ---

class FunctionDef(BaseModel):
    name: str
    line_start: int
    line_end: int
    docstring: str | None = None


class ClassDef(BaseModel):
    name: str
    line_start: int
    line_end: int
    methods: list[str] = []


class ImportStatement(BaseModel):
    module: str
    names: list[str] = []
    is_relative: bool = False


class ExportStatement(BaseModel):
    name: str
    is_default: bool = False


class ParsedFile(BaseModel):
    file_path: str
    language: str
    functions: list[FunctionDef] = []
    classes: list[ClassDef] = []
    imports: list[ImportStatement] = []
    exports: list[ExportStatement] = []


class DependencyNode(BaseModel):
    file_path: str
    dependencies: list[str] = []
    dependents: list[str] = []


class DependencyGraph(BaseModel):
    repo_id: str
    nodes: dict[str, DependencyNode]


class FileParseSummary(BaseModel):
    file_path: str
    language: str
    function_count: int
    class_count: int
    import_count: int


class AnalyzeResponse(BaseModel):
    repo_id: str
    total_files_parsed: int
    total_dependencies: int
    files: list[FileParseSummary]


class FileDependencyResponse(BaseModel):
    file_path: str
    dependencies: list[str]
    dependents: list[str]
    functions: list[FunctionDef]


# --- Phase 3 models ---

class CodeChunk(BaseModel):
    chunk_id: str
    repo_id: str
    file_path: str
    chunk_type: str
    text: str
    metadata: dict = {}


class EmbedResponse(BaseModel):
    repo_id: str
    total_chunks: int


class SearchQuery(BaseModel):
    query: str


class SearchResult(BaseModel):
    chunk_id: str
    file_path: str
    chunk_type: str
    similarity: float
    text_preview: str
    metadata: dict = {}


class SearchResponse(BaseModel):
    repo_id: str
    query: str
    results: list[SearchResult]


# --- Phase 4 models ---

class FileGapResult(BaseModel):
    classification: str
    confidence: float
    reason: str


class FullAnalysisResponse(BaseModel):
    analysis_id: str
    repo_id: str
    architecture_overview: str
    file_explanations: dict[str, str]
    interview_questions: list[dict]
    gap_analysis: dict[str, dict]
    status: str
    errors: list[str]


# --- Phase 5 models ---

class InterviewStartRequest(BaseModel):
    analysis_id: str


class InterviewQuestionPublic(BaseModel):
    """Question shape returned to the client. NEVER includes model_answer."""
    index: int
    question: str
    category: str | None = None
    difficulty: str | None = None
    relevant_files: list[str] = []


class InterviewStartResponse(BaseModel):
    session_id: str
    repo_id: str
    analysis_id: str
    questions: list[InterviewQuestionPublic]


class InterviewEvaluateRequest(BaseModel):
    session_id: str
    question_index: int
    user_answer: str


class EvaluationScores(BaseModel):
    accuracy: int
    completeness: int
    depth: int
    overall: int


class EvaluationResult(BaseModel):
    scores: EvaluationScores
    semantic_similarity: float
    strengths: list[str]
    gaps: list[str]
    model_answer_summary: str
    follow_up_question: str


class InterviewEvaluateResponse(BaseModel):
    session_id: str
    question_index: int
    evaluation: EvaluationResult
    errors: list[str] = []

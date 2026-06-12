import operator
from typing import Annotated, TypedDict


class GitMentorState(TypedDict):
    repo_id: str
    repo_metadata: dict
    file_manifest: list[dict]
    dependency_graph: dict
    parsed_files: list[dict]
    architecture_overview: str
    file_explanations: dict
    interview_questions: list[dict]
    gap_analysis: dict
    errors: Annotated[list[str], operator.add]
    status: str

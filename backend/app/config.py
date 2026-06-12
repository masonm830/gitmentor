from pathlib import Path

from pydantic_settings import BaseSettings

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_CLONE_DIR = str(_PROJECT_ROOT / "cloned_repos")


class Settings(BaseSettings):
    supabase_url: str
    supabase_service_key: str
    github_token: str
    groq_api_key: str
    anthropic_api_key: str
    huggingface_api_token: str = ""
    clone_repos_dir: str = _DEFAULT_CLONE_DIR

    # Agent LLM model names — swap provider by changing these values
    repo_analyzer_model: str = "llama-3.3-70b-versatile"
    explanation_agent_model: str = "claude-sonnet-4-20250514"
    question_generator_model: str = "claude-sonnet-4-20250514"
    gap_detector_model: str = "llama-3.3-70b-versatile"

    # GitHub OAuth (Phase 6)
    github_client_id: str = ""
    github_client_secret: str = ""
    frontend_url: str = "http://localhost:3000"

    model_config = {"env_file": ".env"}


settings = Settings()

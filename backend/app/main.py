import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.models.schemas import HealthResponse
from app.routers.auth import router as auth_router
from app.routers.eval import router as eval_router
from app.routers.interview import router as interview_router
from app.routers.repos import router as repos_router
from app.services.supabase import verify_connection

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Clone repos directory: %s", settings.clone_repos_dir)
    verify_connection()
    yield


app = FastAPI(title="GitMentor", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        settings.frontend_url,
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "https://gitmentor.vercel.app",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(repos_router)
app.include_router(interview_router)
app.include_router(eval_router)


@app.get("/health", response_model=HealthResponse)
async def health_check():
    return HealthResponse(status="ok", version="0.1.0")

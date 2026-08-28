"""
FastAPI 앱 엔트리포인트

GET /api/health, CORS, AppError 전역 핸들러, 라우터 등록.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import participants, quests, results, sessions, survey, workspace
from app.config import get_settings
from app.db import init_db
from app.errors import AppError

settings = get_settings()

app = FastAPI(title="team-chemistry-analyzer")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.code, "message": exc.message}},
    )


app.include_router(sessions.router, prefix="/api")
app.include_router(participants.router, prefix="/api")
app.include_router(survey.router, prefix="/api")
app.include_router(results.router, prefix="/api")
app.include_router(quests.router, prefix="/api")
app.include_router(workspace.router, prefix="/api")


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.on_event("startup")
def on_startup() -> None:
    init_db()

"""
세션 API — design.md §7.2

POST /api/sessions
PATCH /api/sessions/{id}/expected-count
POST /api/sessions/{id}/analysis
GET  /api/sessions/{id}/analysis/status
"""

from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, Response
from pydantic import BaseModel, Field
from sqlmodel import Session as DBSession
from sqlmodel import select

from app.auth import assert_host, extract_secret, generate_secret, hash_secret, set_secret_cookie
from app.config import get_settings
from app.db import get_session
from app.errors import (
    INVALID_MEMBER_COUNT,
    MEMBER_COUNT_BELOW_SUBMITTED,
    SESSION_NOT_FOUND,
    app_error,
)
from app.models import AnalysisResult, Participant, PrivateInsight, Session as SessionModel
from app.services.analysis.orchestrator import run_team_comment_generation, start_analysis

router = APIRouter(tags=["sessions"])

MIN_MEMBERS = 3
MAX_MEMBERS = 10


# ──────────────────────────────────────────────
# 요청/응답 스키마
# ──────────────────────────────────────────────


class CreateSessionRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    expected_member_count: int = Field(ge=MIN_MEMBERS, le=MAX_MEMBERS)
    meeting_type: str = "team_project"


class CreateSessionResponse(BaseModel):
    session_id: str
    invite_token: str
    share_token: str
    host_secret: str  # 1회만 반환. 이후 재조회 불가.


class UpdateExpectedCountRequest(BaseModel):
    expected_member_count: int = Field(ge=MIN_MEMBERS, le=MAX_MEMBERS)


class AnalysisStatusResponse(BaseModel):
    analysis_status: str | None  # PROCESSING|COMPLETED|FALLBACK, 분석 없으면 None
    private_insight_status: str | None = None  # participant 인증 시에만
    expected_member_count: int
    joined_member_count: int  # 세션에 합류한 참여자 수 (제출 여부 무관)
    submitted_member_count: int


# ──────────────────────────────────────────────
# 엔드포인트
# ──────────────────────────────────────────────


@router.post("/sessions", response_model=CreateSessionResponse)
def create_session(
    body: CreateSessionRequest,
    response: Response,
    db: DBSession = Depends(get_session),
) -> CreateSessionResponse:
    settings = get_settings()

    session_id = str(uuid.uuid4())
    invite_token = secrets.token_urlsafe(16)
    share_token = secrets.token_urlsafe(16)
    host_secret = generate_secret()

    session = SessionModel(
        id=session_id,
        name=body.name,
        meeting_type=body.meeting_type,
        expected_member_count=body.expected_member_count,
        status="OPEN",
        invite_token_hash=hash_secret(invite_token),
        share_token_hash=hash_secret(share_token),
        host_secret_hash=hash_secret(host_secret),
        retention_expires_at=datetime.now(timezone.utc) + timedelta(days=settings.session_ttl_days),
    )
    db.add(session)
    db.commit()

    set_secret_cookie(
        response, "host_secret", host_secret, secure=settings.cookie_secure, samesite=settings.cookie_samesite
    )

    return CreateSessionResponse(
        session_id=session_id,
        invite_token=invite_token,
        share_token=share_token,
        host_secret=host_secret,
    )


@router.patch("/sessions/{session_id}/expected-count")
def update_expected_count(
    session_id: str,
    body: UpdateExpectedCountRequest,
    db: DBSession = Depends(get_session),
    session: SessionModel = Depends(assert_host),
) -> dict:
    submitted_count = len(
        db.exec(
            select(Participant).where(
                Participant.session_id == session_id,
                Participant.submission_status.in_(["SUBMITTED", "LOCKED"]),
            )
        ).all()
    )

    if body.expected_member_count < submitted_count:
        raise app_error(
            MEMBER_COUNT_BELOW_SUBMITTED,
            f"현재 제출 인원({submitted_count})보다 목표 인원을 적게 설정할 수 없습니다.",
        )

    session.expected_member_count = body.expected_member_count
    db.add(session)
    db.commit()

    return {"expected_member_count": session.expected_member_count}


@router.post("/sessions/{session_id}/analysis")
def trigger_analysis(
    session_id: str,
    background_tasks: BackgroundTasks,
    db: DBSession = Depends(get_session),
    session: SessionModel = Depends(assert_host),
) -> dict:
    analysis_result = start_analysis(session_id, db)
    # 백그라운드 태스크에는 요청 스코프 DB 세션(db)을 넘기지 않는다.
    # run_team_comment_generation이 내부에서 새 세션을 열고 닫는다.
    background_tasks.add_task(run_team_comment_generation, analysis_result.id)
    return {"analysis_result_id": analysis_result.id, "status": analysis_result.status}


@router.get("/sessions/{session_id}/analysis/status", response_model=AnalysisStatusResponse)
def get_analysis_status(
    session_id: str,
    db: DBSession = Depends(get_session),
) -> AnalysisStatusResponse:
    """host 또는 participant 둘 다 조회 가능 — 시크릿 유무로 분기하되 부재 시에도 팀 상태는 공개."""
    session = db.get(SessionModel, session_id)
    if session is None:
        raise app_error(SESSION_NOT_FOUND, f"세션을 찾을 수 없습니다: {session_id}")

    latest = db.exec(
        select(AnalysisResult)
        .where(AnalysisResult.session_id == session_id)
        .order_by(AnalysisResult.analysis_version.desc())
    ).first()

    participants = db.exec(
        select(Participant).where(Participant.session_id == session_id)
    ).all()
    joined_count = len(participants)
    submitted_count = sum(
        1 for p in participants if p.submission_status in ("SUBMITTED", "LOCKED")
    )
    return AnalysisStatusResponse(
        analysis_status=latest.status if latest is not None else None,
        expected_member_count=session.expected_member_count,
        joined_member_count=joined_count,
        submitted_member_count=submitted_count,
    )

"""
참여자 API — design.md §7.1

POST /api/invites/{token}/participants
PUT  /api/participants/{id}/submission
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, Field
from sqlmodel import Session as DBSession
from sqlmodel import select

from app.auth import assert_participant, generate_secret, hash_secret, set_secret_cookie, verify_secret
from app.config import get_settings
from app.db import get_session
from app.errors import INVALID_INVITE_TOKEN, SUBMISSION_LOCKED, app_error
from app.models import Participant, Session as SessionModel

router = APIRouter(tags=["participants"])


class JoinRequest(BaseModel):
    nickname: str = Field(min_length=1, max_length=40)


class JoinResponse(BaseModel):
    participant_id: str
    participant_secret: str  # 1회만 반환
    session_id: str


class UpdateSubmissionMethodRequest(BaseModel):
    """제출 방식 전환 전, 세션 상태만 확인하는 용도 (실제 데이터는 survey.py에서 처리)."""

    pass


@router.post("/invites/{token}/participants", response_model=JoinResponse)
def join_session(
    token: str,
    body: JoinRequest,
    response: Response,
    db: DBSession = Depends(get_session),
) -> JoinResponse:
    settings = get_settings()

    sessions = db.exec(select(SessionModel)).all()
    session = next((s for s in sessions if verify_secret(token, s.invite_token_hash)), None)
    if session is None:
        raise app_error(INVALID_INVITE_TOKEN, "유효하지 않은 초대 링크입니다.")

    participant_secret = generate_secret()
    participant = Participant(
        id=str(uuid.uuid4()),
        session_id=session.id,
        nickname=body.nickname,
        participant_secret_hash=hash_secret(participant_secret),
        submission_status="PENDING",
    )
    db.add(participant)
    db.commit()

    set_secret_cookie(response, "participant_secret", participant_secret, secure=settings.cookie_secure)

    return JoinResponse(
        participant_id=participant.id,
        participant_secret=participant_secret,
        session_id=session.id,
    )


@router.put("/participants/{participant_id}/submission")
def update_submission(
    participant_id: str,
    db: DBSession = Depends(get_session),
    participant: Participant = Depends(assert_participant),
) -> dict:
    """본인 입력 수정 진입점 — 실제 필드 갱신은 survey.py의 제출 엔드포인트가 담당.

    여기서는 세션이 분석 시작 후(LOCKED)인지만 확인해 잠금 규칙을 강제한다.
    """
    if participant.submission_status == "LOCKED":
        raise app_error(SUBMISSION_LOCKED, "분석이 시작된 후에는 제출본을 수정할 수 없습니다.")

    return {"participant_id": participant.id, "submission_status": participant.submission_status}

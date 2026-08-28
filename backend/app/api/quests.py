"""
퀘스트 API

GET   /api/sessions/{session_id}/quests/team
PATCH /api/sessions/{session_id}/quests/{quest_assignment_id}
GET   /api/participants/{participant_id}/quests
PATCH /api/participants/{participant_id}/quests/{quest_assignment_id}

팀 퀘스트 조회는 팀 결과(results.py)와 동일하게 공개다 (개인정보 없음).
완료 처리(PATCH)는 participant_secret 인증이 필요하다 — 팀 퀘스트는 세션 소속 참여자
누구나 완료 처리할 수 있고, 개인 퀘스트는 본인만 처리할 수 있다.

응답은 allow-list 방식의 Pydantic 모델만 사용한다 (analysis_version 등 내부 필드 미노출).
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlmodel import Session as DBSession

from app.auth import assert_participant, resolve_participant_by_secret
from app.db import get_session
from app.errors import SESSION_NOT_FOUND, app_error
from app.models import Participant, QuestAssignment, Session as SessionModel
from app.services.chemistry import engine
from app.services.quests import service as quest_service

router = APIRouter(tags=["quests"])


# ──────────────────────────────────────────────
# 응답 스키마 (allow-list)
# ──────────────────────────────────────────────


class QuestItemResponse(BaseModel):
    quest_assignment_id: str
    quest_code: str
    scope: str  # TEAM | PERSONAL
    title: str
    description: str
    action: str
    tags: list[str]
    status: str  # ASSIGNED | COMPLETED
    completed_by_nickname: str | None = None  # TEAM 퀘스트에서만 의미 있음
    completed_at: datetime | None = None


class TeamQuestListResponse(BaseModel):
    session_id: str
    quests: list[QuestItemResponse]
    completed_count: int
    total_count: int


class PersonalQuestListResponse(BaseModel):
    participant_id: str
    quests: list[QuestItemResponse]
    completed_count: int
    total_count: int


class ToggleQuestRequest(BaseModel):
    completed: bool = True


# ──────────────────────────────────────────────
# 내부 헬퍼
# ──────────────────────────────────────────────


def _render_quest(assignment: QuestAssignment, db: DBSession) -> QuestItemResponse:
    catalog_entry = engine.get_quest_by_code(assignment.scope, assignment.quest_code)

    completed_by_nickname: str | None = None
    if assignment.completed_by_participant_id:
        completer = db.get(Participant, assignment.completed_by_participant_id)
        completed_by_nickname = completer.nickname if completer else None

    return QuestItemResponse(
        quest_assignment_id=assignment.id,
        quest_code=assignment.quest_code,
        scope=assignment.scope,
        title=catalog_entry.title if catalog_entry else "",
        description=catalog_entry.description if catalog_entry else "",
        action=catalog_entry.action if catalog_entry else "",
        tags=catalog_entry.tags if catalog_entry else [],
        status=assignment.status,
        completed_by_nickname=completed_by_nickname,
        completed_at=assignment.completed_at,
    )


# ──────────────────────────────────────────────
# 팀 퀘스트 엔드포인트
# ──────────────────────────────────────────────


@router.get("/sessions/{session_id}/quests/team", response_model=TeamQuestListResponse)
def get_team_quests(
    session_id: str,
    db: DBSession = Depends(get_session),
) -> TeamQuestListResponse:
    session = db.get(SessionModel, session_id)
    if session is None:
        raise app_error(SESSION_NOT_FOUND, f"세션을 찾을 수 없습니다: {session_id}")

    assignments = quest_service.get_or_assign_team_quests(session_id, db)
    quests = [_render_quest(a, db) for a in assignments]
    completed_count = sum(1 for q in quests if q.status == "COMPLETED")

    return TeamQuestListResponse(
        session_id=session_id,
        quests=quests,
        completed_count=completed_count,
        total_count=len(quests),
    )


@router.patch("/sessions/{session_id}/quests/{quest_assignment_id}", response_model=QuestItemResponse)
def complete_team_quest(
    session_id: str,
    quest_assignment_id: str,
    body: ToggleQuestRequest,
    db: DBSession = Depends(get_session),
    participant: Participant = Depends(resolve_participant_by_secret),
) -> QuestItemResponse:
    """세션 소속 참여자라면 누구나 팀 퀘스트를 완료/취소 처리할 수 있다."""
    assignment = quest_service.toggle_team_quest_completion(
        session_id=session_id,
        quest_assignment_id=quest_assignment_id,
        completed_by=participant,
        completed=body.completed,
        db=db,
    )
    return _render_quest(assignment, db)


# ──────────────────────────────────────────────
# 개인 퀘스트 엔드포인트
# ──────────────────────────────────────────────


@router.get("/participants/{participant_id}/quests", response_model=PersonalQuestListResponse)
def get_personal_quests(
    participant_id: str,
    db: DBSession = Depends(get_session),
    participant: Participant = Depends(assert_participant),
) -> PersonalQuestListResponse:
    assignments = quest_service.get_or_assign_personal_quests(participant, db)
    quests = [_render_quest(a, db) for a in assignments]
    completed_count = sum(1 for q in quests if q.status == "COMPLETED")

    return PersonalQuestListResponse(
        participant_id=participant_id,
        quests=quests,
        completed_count=completed_count,
        total_count=len(quests),
    )


@router.patch("/participants/{participant_id}/quests/{quest_assignment_id}", response_model=QuestItemResponse)
def complete_personal_quest(
    participant_id: str,
    quest_assignment_id: str,
    body: ToggleQuestRequest,
    db: DBSession = Depends(get_session),
    participant: Participant = Depends(assert_participant),
) -> QuestItemResponse:
    """본인 소유의 개인 퀘스트만 완료/취소 처리할 수 있다."""
    assignment = quest_service.toggle_personal_quest_completion(
        participant=participant,
        quest_assignment_id=quest_assignment_id,
        completed=body.completed,
        db=db,
    )
    return _render_quest(assignment, db)

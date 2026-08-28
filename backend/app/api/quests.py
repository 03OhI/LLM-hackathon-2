"""
퀘스트 API — SPEC_V5_CONTEST_QUEST_AGENT.md §5, §6, §9

GET  /api/rooms/{id}/quests/current              — 같은 방 팀원/방장
POST /api/rooms/{id}/quests/assign               — 방장, 멱등
POST /api/quest-assignments/{id}/start           — 방장
PUT  /api/quest-assignments/{id}/responses/me    — 본인
PUT  /api/quest-assignments/{id}/result          — 방장
POST /api/quest-assignments/{id}/complete        — 방장
POST /api/quest-assignments/{id}/skip            — 방장

프론트에서 버튼을 숨기는 것과 별개로, 모든 방장 전용 액션은 여기서 host_secret을 다시 검증한다.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlmodel import Session as DBSession

from app.auth import RoomActor, assert_host, assert_room_actor, identify_room_actor, require_host_actor
from app.db import get_session
from app.errors import FORBIDDEN, app_error
from app.models import QuestAssignment, Session as SessionModel
from app.services.quests import completion, service
from app.services.quests.catalog import get_quest_template
from app.services.quests.schemas import COMPLETION_CHECK_TYPES

router = APIRouter(tags=["quests"])


# ──────────────────────────────────────────────
# 요청/응답 스키마
# ──────────────────────────────────────────────


class CheckSubmission(BaseModel):
    type: str
    count: int = 1
    value: object | None = None


class ResponseSubmitRequest(BaseModel):
    checks: list[CheckSubmission]


class AssignmentInfo(BaseModel):
    id: str
    status: str
    assignment_source: str
    reason: str
    intro_message: str
    assigned_at: str
    started_at: str | None
    completed_at: str | None


class CompletionStatus(BaseModel):
    satisfied: bool
    unmet_check_types: list[str]


class QuestCurrentResponse(BaseModel):
    quest_id: str
    title: str
    summary: str
    duration_minutes: int
    steps: list[str]
    materials: list[str]
    deliverable: str
    assignment: AssignmentInfo
    my_response_status: dict[str, bool] | None
    team_completion_status: CompletionStatus


# ──────────────────────────────────────────────
# 헬퍼
# ──────────────────────────────────────────────


def _member_ids(session_id: str, db: DBSession) -> list[str]:
    return [p.id for p in service._locked_participants(session_id, db)]


def _build_response(assignment: QuestAssignment, actor: RoomActor, db: DBSession) -> QuestCurrentResponse:
    template = get_quest_template(assignment.quest_template_id)
    if template is None:
        raise app_error(
            "QUEST_CATALOG_UNAVAILABLE", "배정된 퀘스트 정의를 카탈로그에서 찾을 수 없습니다."
        )

    result = completion.load_result(assignment.result_json)
    member_ids = _member_ids(assignment.session_id, db)
    checks = template.completion_condition.get("checks", [])
    unmet = completion.unmet_checks(checks, result, member_ids)

    my_response_status = None
    if actor.role == "MEMBER" and actor.participant is not None:
        my_submissions = result["member_submissions"].get(actor.participant.id, {})
        per_member_types = {c["type"] for c in checks if c.get("scope") == "PER_MEMBER"}
        my_response_status = {t: t in my_submissions for t in per_member_types}

    return QuestCurrentResponse(
        quest_id=template.quest_id,
        title=template.title,
        summary=template.summary,
        duration_minutes=template.duration_minutes,
        steps=template.steps,
        materials=template.materials,
        deliverable=template.deliverable,
        assignment=AssignmentInfo(
            id=assignment.id,
            status=assignment.status,
            assignment_source=assignment.assignment_source,
            reason=assignment.assignment_reason,
            intro_message=assignment.intro_message,
            assigned_at=assignment.assigned_at.isoformat(),
            started_at=assignment.started_at.isoformat() if assignment.started_at else None,
            completed_at=assignment.completed_at.isoformat() if assignment.completed_at else None,
        ),
        my_response_status=my_response_status,
        team_completion_status=CompletionStatus(
            satisfied=not unmet, unmet_check_types=[c["type"] for c in unmet]
        ),
    )


def _resolve_actor_for_assignment(assignment: QuestAssignment, request: Request, db: DBSession) -> RoomActor:
    session = db.get(SessionModel, assignment.session_id)
    if session is None:
        raise app_error("SESSION_NOT_FOUND", "세션을 찾을 수 없습니다.")
    return identify_room_actor(session, request, db)


def _require_host_for_assignment(assignment: QuestAssignment, request: Request, db: DBSession) -> None:
    session = db.get(SessionModel, assignment.session_id)
    if session is None:
        raise app_error("SESSION_NOT_FOUND", "세션을 찾을 수 없습니다.")
    require_host_actor(session, request)


# ──────────────────────────────────────────────
# 엔드포인트
# ──────────────────────────────────────────────


@router.get("/rooms/{session_id}/quests/current", response_model=QuestCurrentResponse)
def get_current_quest(
    session_id: str,
    db: DBSession = Depends(get_session),
    actor: RoomActor = Depends(assert_room_actor),
) -> QuestCurrentResponse:
    assignment = service.get_current_assignment(session_id, db)
    return _build_response(assignment, actor, db)


@router.post("/rooms/{session_id}/quests/assign", response_model=QuestCurrentResponse)
async def assign_quest(
    session_id: str,
    db: DBSession = Depends(get_session),
    session: SessionModel = Depends(assert_host),
) -> QuestCurrentResponse:
    assignment = await service.assign_quest_for_room(session_id, db)
    actor = RoomActor(role="HOST", session=session, participant=None)
    return _build_response(assignment, actor, db)


@router.post("/quest-assignments/{assignment_id}/start", response_model=QuestCurrentResponse)
def start_quest(
    assignment_id: str,
    request: Request,
    db: DBSession = Depends(get_session),
) -> QuestCurrentResponse:
    assignment = service.get_assignment_or_404(assignment_id, db)
    _require_host_for_assignment(assignment, request, db)
    assignment = service.start_assignment(assignment_id, db)
    actor = _resolve_actor_for_assignment(assignment, request, db)
    return _build_response(assignment, actor, db)


@router.put("/quest-assignments/{assignment_id}/responses/me", response_model=QuestCurrentResponse)
def submit_my_response(
    assignment_id: str,
    body: ResponseSubmitRequest,
    request: Request,
    db: DBSession = Depends(get_session),
) -> QuestCurrentResponse:
    assignment = service.get_assignment_or_404(assignment_id, db)
    actor = _resolve_actor_for_assignment(assignment, request, db)
    if actor.role != "MEMBER" or actor.participant is None:
        raise app_error(FORBIDDEN, "본인(팀원)만 응답을 제출할 수 있습니다.")

    checks = [c.model_dump() for c in body.checks]
    for c in checks:
        if c["type"] not in COMPLETION_CHECK_TYPES:
            from app.errors import VALIDATION_ERROR

            raise app_error(VALIDATION_ERROR, f"허용되지 않은 체크 타입: {c['type']}")

    assignment = service.submit_member_response(assignment_id, db, actor.participant.id, checks)
    return _build_response(assignment, actor, db)


@router.put("/quest-assignments/{assignment_id}/result", response_model=QuestCurrentResponse)
def submit_team_result(
    assignment_id: str,
    body: ResponseSubmitRequest,
    request: Request,
    db: DBSession = Depends(get_session),
) -> QuestCurrentResponse:
    assignment = service.get_assignment_or_404(assignment_id, db)
    _require_host_for_assignment(assignment, request, db)

    checks = [c.model_dump() for c in body.checks]
    for c in checks:
        if c["type"] not in COMPLETION_CHECK_TYPES:
            from app.errors import VALIDATION_ERROR

            raise app_error(VALIDATION_ERROR, f"허용되지 않은 체크 타입: {c['type']}")

    assignment = service.submit_team_result(assignment_id, db, checks)
    actor = _resolve_actor_for_assignment(assignment, request, db)
    return _build_response(assignment, actor, db)


@router.post("/quest-assignments/{assignment_id}/complete", response_model=QuestCurrentResponse)
def complete_quest(
    assignment_id: str,
    request: Request,
    db: DBSession = Depends(get_session),
) -> QuestCurrentResponse:
    assignment = service.get_assignment_or_404(assignment_id, db)
    _require_host_for_assignment(assignment, request, db)
    assignment = service.complete_assignment(assignment_id, db)
    actor = _resolve_actor_for_assignment(assignment, request, db)
    return _build_response(assignment, actor, db)


@router.post("/quest-assignments/{assignment_id}/skip", response_model=QuestCurrentResponse)
def skip_quest(
    assignment_id: str,
    request: Request,
    db: DBSession = Depends(get_session),
) -> QuestCurrentResponse:
    assignment = service.get_assignment_or_404(assignment_id, db)
    _require_host_for_assignment(assignment, request, db)
    assignment = service.skip_assignment(assignment_id, db)
    actor = _resolve_actor_for_assignment(assignment, request, db)
    return _build_response(assignment, actor, db)

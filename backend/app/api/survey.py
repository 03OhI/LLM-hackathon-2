"""
설문/유형 입력 API — design.md §7.1

GET  /api/survey/question-sets/current
POST /api/participants/{id}/submissions/survey
POST /api/participants/{id}/submissions/type
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlmodel import Session as DBSession

from ai.schemas import AXIS_KEYS

from app.auth import assert_participant
from app.db import get_session
from app.errors import DUPLICATE_SUBMISSION_METHOD, SUBMISSION_LOCKED, VALIDATION_ERROR, app_error
from app.models import Participant, ParticipantProfile
from app.services.profile.normalizer import canonical_to_profile_row
from app.services.scoring.scorer import (
    QUESTION_SET_VERSION,
    TOTAL_QUESTIONS,
    create_profile_from_declared_type,
    create_profile_from_survey,
)

router = APIRouter(tags=["survey"])


# ──────────────────────────────────────────────
# 요청/응답 스키마
# ──────────────────────────────────────────────


class SurveySubmitRequest(BaseModel):
    answers: list[int] = Field(min_length=TOTAL_QUESTIONS, max_length=TOTAL_QUESTIONS)


class TypeSubmitRequest(BaseModel):
    positions: dict[str, str]


class SubmissionResponse(BaseModel):
    participant_id: str
    input_method: str
    positions: dict[str, str]


class QuestionSetResponse(BaseModel):
    version: str
    total_questions: int
    axis_keys: list[str]


# ──────────────────────────────────────────────
# 헬퍼
# ──────────────────────────────────────────────


def _assert_not_locked(participant: Participant) -> None:
    if participant.submission_status == "LOCKED":
        raise app_error(SUBMISSION_LOCKED, "분석이 시작된 후에는 제출본을 수정할 수 없습니다.")


def _assert_no_conflicting_method(participant: Participant, new_method: str) -> None:
    if participant.input_method and participant.input_method != new_method:
        raise app_error(
            DUPLICATE_SUBMISSION_METHOD,
            f"이미 다른 방식({participant.input_method})으로 제출했습니다. 먼저 제출본을 삭제해야 합니다.",
        )


def _upsert_profile(db: DBSession, participant: Participant, profile_row: ParticipantProfile) -> None:
    existing = db.get(ParticipantProfile, participant.id)
    if existing is not None:
        db.delete(existing)
        db.flush()
    db.add(profile_row)


# ──────────────────────────────────────────────
# 엔드포인트
# ──────────────────────────────────────────────


@router.get("/survey/question-sets/current", response_model=QuestionSetResponse)
def get_current_question_set() -> QuestionSetResponse:
    return QuestionSetResponse(
        version=QUESTION_SET_VERSION,
        total_questions=TOTAL_QUESTIONS,
        axis_keys=list(AXIS_KEYS),
    )


@router.post("/participants/{participant_id}/submissions/survey", response_model=SubmissionResponse)
def submit_survey(
    participant_id: str,
    body: SurveySubmitRequest,
    db: DBSession = Depends(get_session),
    participant: Participant = Depends(assert_participant),
) -> SubmissionResponse:
    _assert_not_locked(participant)
    _assert_no_conflicting_method(participant, "SURVEY")

    try:
        canonical = create_profile_from_survey(participant.id, body.answers)
    except ValueError as e:
        raise app_error(VALIDATION_ERROR, str(e)) from e

    profile_row = canonical_to_profile_row(canonical, answers=body.answers)
    _upsert_profile(db, participant, profile_row)

    participant.input_method = "SURVEY"
    participant.submission_status = "SUBMITTED"
    participant.submitted_at = datetime.now(timezone.utc)
    db.add(participant)
    db.commit()

    return SubmissionResponse(
        participant_id=participant.id,
        input_method="SURVEY",
        positions=dict(canonical.positions.items()),
    )


@router.post("/participants/{participant_id}/submissions/type", response_model=SubmissionResponse)
def submit_declared_type(
    participant_id: str,
    body: TypeSubmitRequest,
    db: DBSession = Depends(get_session),
    participant: Participant = Depends(assert_participant),
) -> SubmissionResponse:
    _assert_not_locked(participant)
    _assert_no_conflicting_method(participant, "DECLARED_TYPE")

    try:
        canonical = create_profile_from_declared_type(participant.id, body.positions)
    except ValueError as e:
        raise app_error(VALIDATION_ERROR, str(e)) from e

    profile_row = canonical_to_profile_row(canonical)
    _upsert_profile(db, participant, profile_row)

    participant.input_method = "DECLARED_TYPE"
    participant.submission_status = "SUBMITTED"
    participant.submitted_at = datetime.now(timezone.utc)
    db.add(participant)
    db.commit()

    return SubmissionResponse(
        participant_id=participant.id,
        input_method="DECLARED_TYPE",
        positions=dict(canonical.positions.items()),
    )

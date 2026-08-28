"""
orchestrator 전용 프로필 조회 헬퍼

app/services/profile/normalizer.py의 순수 변환 함수를 DB 조회와 묶어서 제공한다.
"""

from __future__ import annotations

from sqlmodel import Session as DBSession
from sqlmodel import select

from ai.schemas import CanonicalProfile

from .normalizer import profile_row_to_canonical


def canonical_profile_for_participant(participant_id: str, db: DBSession) -> CanonicalProfile:
    from app.models import ParticipantProfile

    row = db.get(ParticipantProfile, participant_id)
    if row is None:
        from app.errors import PARTICIPANT_NOT_FOUND, app_error

        raise app_error(PARTICIPANT_NOT_FOUND, f"프로필을 찾을 수 없습니다: {participant_id}")
    return profile_row_to_canonical(row)


def canonical_profiles_for_session(session_id: str, db: DBSession) -> list[CanonicalProfile]:
    """세션의 LOCKED 참여자 전원의 CanonicalProfile 목록.

    엔진(run_team_analysis)이 participant_id로 재정렬하므로 여기서는 순서를 보장하지 않는다.
    """
    from app.models import Participant, ParticipantProfile

    locked_ids = db.exec(
        select(Participant.id).where(
            Participant.session_id == session_id,
            Participant.submission_status == "LOCKED",
        )
    ).all()

    rows = db.exec(
        select(ParticipantProfile).where(ParticipantProfile.participant_id.in_(locked_ids))
    ).all()

    return [profile_row_to_canonical(row) for row in rows]

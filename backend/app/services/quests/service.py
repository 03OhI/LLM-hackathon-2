"""
퀘스트 배정/완료 처리 서비스

app/services/analysis/orchestrator.py와 동일한 책임 분리를 따른다:
- app/services/chemistry/engine.py: 순수 매칭 함수 (LLM/DB 미사용)
- 여기: DB 조회 + lazy 배정 + 캐싱 + 완료 상태 토글

배정은 세션에 AnalysisResult가 생성된 시점부터 가능하다. AI 팀 코멘트(Bedrock) 완료를
기다리지 않는다 — distribution_json은 start_analysis에서 동기적으로 채워지므로
퀘스트 매칭에는 그것만으로 충분하다 (design 상 퀘스트는 LLM 호출 없이 결정론적으로 배정됨).
"""

from __future__ import annotations

import json
import uuid

from sqlmodel import Session as DBSession
from sqlmodel import select

from app.config import get_settings
from app.errors import FORBIDDEN, QUEST_NOT_FOUND, app_error
from app.models import AnalysisResult, Participant, QuestAssignment, utcnow
from app.services.chemistry import engine
from app.services.profile.profile_helpers import canonical_profile_for_participant


def _latest_analysis(session_id: str, db: DBSession) -> AnalysisResult | None:
    return db.exec(
        select(AnalysisResult)
        .where(AnalysisResult.session_id == session_id)
        .order_by(AnalysisResult.analysis_version.desc())
    ).first()


def _team_size(session_id: str, db: DBSession) -> int:
    return len(
        db.exec(
            select(Participant).where(
                Participant.session_id == session_id,
                Participant.submission_status == "LOCKED",
            )
        ).all()
    )


# ──────────────────────────────────────────────
# 팀 퀘스트
# ──────────────────────────────────────────────


def get_or_assign_team_quests(session_id: str, db: DBSession) -> list[QuestAssignment]:
    """세션의 팀 퀘스트를 lazy 배정하고 캐시한다.

    분석이 아직 시작되지 않았으면(AnalysisResult 없음) 빈 리스트를 반환한다 — 에러가 아니라
    PrivateInsight의 NOT_REQUESTED와 같은 '아직 준비되지 않음' 상태로 취급한다.
    """
    analysis = _latest_analysis(session_id, db)
    if analysis is None:
        return []

    existing = db.exec(
        select(QuestAssignment).where(
            QuestAssignment.session_id == session_id,
            QuestAssignment.scope == "TEAM",
            QuestAssignment.analysis_version == analysis.analysis_version,
        )
    ).all()
    if existing:
        return list(existing)

    distribution = json.loads(analysis.distribution_json) if analysis.distribution_json else {}
    candidates = engine.match_team_quests(distribution)

    settings = get_settings()
    selected = candidates[: settings.team_quest_count]

    assignments = [
        QuestAssignment(
            id=str(uuid.uuid4()),
            session_id=session_id,
            participant_id=None,
            scope="TEAM",
            quest_code=c.quest_code,
            analysis_version=analysis.analysis_version,
            status="ASSIGNED",
        )
        for c in selected
    ]
    for a in assignments:
        db.add(a)
    db.commit()
    for a in assignments:
        db.refresh(a)

    return assignments


def toggle_team_quest_completion(
    session_id: str,
    quest_assignment_id: str,
    completed_by: Participant,
    completed: bool,
    db: DBSession,
) -> QuestAssignment:
    """팀 퀘스트 완료 상태를 토글한다.

    세션 소속 참여자라면 누구나 완료/취소 처리할 수 있다 (공유 미션이므로 host 전용이 아님).
    """
    assignment = db.get(QuestAssignment, quest_assignment_id)
    if assignment is None or assignment.session_id != session_id or assignment.scope != "TEAM":
        raise app_error(QUEST_NOT_FOUND, f"퀘스트를 찾을 수 없습니다: {quest_assignment_id}")

    if completed_by.session_id != session_id:
        raise app_error(FORBIDDEN, "본인이 속한 세션의 퀘스트만 처리할 수 있습니다.")

    if completed:
        assignment.status = "COMPLETED"
        assignment.completed_by_participant_id = completed_by.id
        assignment.completed_at = utcnow()
    else:
        assignment.status = "ASSIGNED"
        assignment.completed_by_participant_id = None
        assignment.completed_at = None

    db.add(assignment)
    db.commit()
    db.refresh(assignment)
    return assignment


# ──────────────────────────────────────────────
# 개인 퀘스트
# ──────────────────────────────────────────────


def get_or_assign_personal_quests(participant: Participant, db: DBSession) -> list[QuestAssignment]:
    """참여자의 개인 퀘스트를 lazy 배정하고 캐시한다."""
    analysis = _latest_analysis(participant.session_id, db)
    if analysis is None:
        return []

    existing = db.exec(
        select(QuestAssignment).where(
            QuestAssignment.participant_id == participant.id,
            QuestAssignment.scope == "PERSONAL",
            QuestAssignment.analysis_version == analysis.analysis_version,
        )
    ).all()
    if existing:
        return list(existing)

    distribution = json.loads(analysis.distribution_json) if analysis.distribution_json else {}
    profile = canonical_profile_for_participant(participant.id, db)
    team_size = _team_size(participant.session_id, db)

    candidates = engine.match_private_quests(profile, distribution, team_size)

    settings = get_settings()
    selected = candidates[: settings.personal_quest_count]

    assignments = [
        QuestAssignment(
            id=str(uuid.uuid4()),
            session_id=participant.session_id,
            participant_id=participant.id,
            scope="PERSONAL",
            quest_code=c.quest_code,
            analysis_version=analysis.analysis_version,
            status="ASSIGNED",
        )
        for c in selected
    ]
    for a in assignments:
        db.add(a)
    db.commit()
    for a in assignments:
        db.refresh(a)

    return assignments


def toggle_personal_quest_completion(
    participant: Participant,
    quest_assignment_id: str,
    completed: bool,
    db: DBSession,
) -> QuestAssignment:
    """개인 퀘스트 완료 상태를 토글한다. 본인 소유 배정만 처리할 수 있다."""
    assignment = db.get(QuestAssignment, quest_assignment_id)
    if (
        assignment is None
        or assignment.scope != "PERSONAL"
        or assignment.participant_id != participant.id
    ):
        raise app_error(QUEST_NOT_FOUND, f"퀘스트를 찾을 수 없습니다: {quest_assignment_id}")

    if completed:
        assignment.status = "COMPLETED"
        assignment.completed_by_participant_id = participant.id
        assignment.completed_at = utcnow()
    else:
        assignment.status = "ASSIGNED"
        assignment.completed_by_participant_id = None
        assignment.completed_at = None

    db.add(assignment)
    db.commit()
    db.refresh(assignment)
    return assignment

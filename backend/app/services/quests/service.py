"""
퀘스트 배정/상태 전이 서비스 — SPEC_V5_CONTEST_QUEST_AGENT.md §5, §6

- build_match_context: 규칙 엔진 결과 → QuestMatchContext 어댑터 (§3)
- decide_assignment: 필터·점수·AI 선택·검증·폴백까지 이어지는 배정 결정 (§5)
- recommend_quests_for_room: 팀 성향 점수 기반 공개 후보 3개
- assign_quest_for_room: 배정 결과를 QuestAssignment로 저장, 멱등/중복 방지 (§6)
- start/complete/skip: 상태 전이 + 완료 조건 재검사 + 동시 확정 방지 (§6)
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session as DBSession
from sqlmodel import select, update

from app.errors import (
    ANALYSIS_NOT_READY,
    COMPLETION_CONDITION_NOT_MET,
    NO_ACTIVE_QUEST,
    QUEST_ALREADY_FINALIZED,
    QUEST_ASSIGNMENT_NOT_FOUND,
    QUEST_CATALOG_UNAVAILABLE,
    app_error,
)
from app.models import AnalysisResult, Participant, QuestAssignment
from app.models import Session as SessionModel
from app.services.chemistry.engine import load_team_rules
from app.services.quests import completion
from app.services.quests.ai_client import build_minimal_fallback_decision, try_agent_decision
from app.services.quests.catalog import get_active_quest_templates, get_quest_template
from app.services.quests.schemas import DEFAULT_CONTEXT_TAGS, QuestAssignmentDecision, QuestMatchContext
from ai.quest_assignment.filter import filter_candidates, matched_candidates
from ai.quest_assignment.scoring import rank_candidates

logger = logging.getLogger(__name__)

ACTIVE_STATUSES = ("ASSIGNED", "IN_PROGRESS")
TERMINAL_STATUSES = ("COMPLETED", "SKIPPED")

_TEAM_RULE_PUBLIC_LABELS = {
    "TEAM_BALANCED_AGENCY": "역할 주도성이 균형 잡힌",
    "TEAM_BALANCED_CONFLICT": "의견 조율 방식이 균형 잡힌",
    "TEAM_DIVERSE_COMMUNICATION": "소통 방식이 다양한",
    "TEAM_PLANNING_STABILITY": "계획 성향이 안정적인",
    "TEAM_ADAPTABILITY": "상황 적응력이 높은",
    "TEAM_DRIVER_ENERGY": "추진 에너지가 높은",
    "TEAM_HARMONIZER_PRESENCE": "조율 성향이 두드러지는",
    "TEAM_TACTFUL_COMMUNICATION": "배려형 소통이 강한",
    "TEAM_DIRECT_CONCENTRATION": "직접적인 소통이 강한",
    "TEAM_PLANNING_OVERLOAD": "계획 성향이 강한",
    "TEAM_CONFRONTER_MAJORITY": "의견을 분명히 표현하는",
    "TEAM_LOW_DRIVER": "신중하게 합의하는",
    "TEAM_SUPPORTER_MAJORITY": "협력과 지원을 중시하는",
    "TEAM_ADAPTER_MAJORITY": "유연하게 대응하는",
}


def _locked_participants(session_id: str, db: DBSession) -> list[Participant]:
    return list(
        db.exec(
            select(Participant).where(
                Participant.session_id == session_id,
                Participant.submission_status == "LOCKED",
            )
        ).all()
    )


def _team_rule_id_set() -> set[str]:
    return {rule.get("rule_id", "") for rule in load_team_rules().get("rules", [])}


def build_match_context(session_id: str, analysis: AnalysisResult, db: DBSession) -> QuestMatchContext:
    """SPEC §3 — 기존 엔진 결과에서 QuestMatchContext를 만든다.

    matched_rule_ids는 team_rules.yaml에 실제 존재하는 ID만 남기고(페어 규칙 제외),
    team_grade/internal_index/주의 코드는 절대 포함하지 않는다.
    """
    team_rule_ids = _team_rule_id_set()
    all_matched = json.loads(analysis.matched_rule_ids_json) if analysis.matched_rule_ids_json else []
    matched_rule_ids = [rid for rid in all_matched if rid in team_rule_ids]

    distribution = json.loads(analysis.distribution_json) if analysis.distribution_json else {}
    team_size = len(_locked_participants(session_id, db))

    completed_quest_ids = list(
        db.exec(
            select(QuestAssignment.quest_template_id).where(
                QuestAssignment.session_id == session_id,
                QuestAssignment.status == "COMPLETED",
            )
        ).all()
    )

    return QuestMatchContext(
        room_id=session_id,
        team_size=team_size,
        matched_rule_ids=matched_rule_ids,
        distribution=distribution,
        context_tags=list(DEFAULT_CONTEXT_TAGS),
        completed_quest_ids=completed_quest_ids,
    )


async def decide_assignment(context: QuestMatchContext) -> QuestAssignmentDecision:
    """SPEC §5 — 필터·점수·랭킹·Bedrock 선택은 전부 ai.quest_assignment.assign_quest의
    책임이다(SPEC §11 역할 분리). 여기서는 활성 카탈로그 전체를 넘겨 호출하고,
    그 함수가 없거나 실패/무효 응답일 때만 최소 안전망으로 넘어간다.
    """
    catalog = get_active_quest_templates()
    if not catalog:
        raise app_error(QUEST_CATALOG_UNAVAILABLE, "배정 가능한 퀘스트 후보가 카탈로그에 없습니다.")

    decision = await try_agent_decision(context, catalog)
    if decision is not None:
        return decision

    return build_minimal_fallback_decision(catalog, context)


def recommend_quests_for_room(session_id: str, db: DBSession, *, limit: int = 3) -> list[dict]:
    """팀 규칙 점수 기준 상위 퀘스트를 공개 화면용으로 반환한다.

    우선 실제 rule_id가 겹친 맞춤 후보를 점수순으로 배치하고, 3개가 안 되면
    동일한 안전·인원 필터를 통과한 보완 후보로 채운다. 내부 rule_id와 점수는
    응답에 포함하지 않는다.
    """
    session = db.get(SessionModel, session_id)
    analysis = db.exec(
        select(AnalysisResult)
        .where(AnalysisResult.session_id == session_id)
        .order_by(AnalysisResult.analysis_version.desc())
    ).first()
    if session is None or analysis is None or session.status != "COMPLETED":
        raise app_error(ANALYSIS_NOT_READY, "팀 분석이 완료된 후에만 퀘스트를 추천할 수 있습니다.")

    context = build_match_context(session_id, analysis, db)
    catalog = get_active_quest_templates()
    if not catalog:
        raise app_error(QUEST_CATALOG_UNAVAILABLE, "추천 가능한 퀘스트가 없습니다.")

    safe = filter_candidates(catalog, context)
    matched = matched_candidates(safe, context)
    ordered_matched = rank_candidates(matched, context, catalog, limit=len(matched))
    matched_ids = {q.quest_id for q in ordered_matched}
    ordered_fill = rank_candidates(
        [q for q in safe if q.quest_id not in matched_ids],
        context,
        catalog,
        limit=len(safe),
    )
    ordered = ordered_matched + ordered_fill

    # 일반 후보가 부족한 극단적인 카탈로그에서도 범용 퀘스트로 빈자리를 채운다.
    if len(ordered) < limit:
        ordered.extend(
            q
            for q in catalog
            if q.is_active
            and q.is_universal
            and q.assignment == "AUTO"
            and q.disclosure_level != "HIGH"
            and q.team_size.get("min", 99) <= context.team_size <= q.team_size.get("max", -1)
            and q.quest_id not in {item.quest_id for item in ordered}
        )

    recommendations: list[dict] = []
    rule_ids = set(context.matched_rule_ids)
    for quest in ordered[:limit]:
        used_rule_ids = sorted(rule_ids & (set(quest.best_for) | set(quest.also_for)))
        public_traits = [
            _TEAM_RULE_PUBLIC_LABELS[rule_id]
            for rule_id in used_rule_ids
            if rule_id in _TEAM_RULE_PUBLIC_LABELS
        ][:2]
        recommendations.append(
            {
                "template": quest,
                "used_rule_ids": used_rule_ids,
                "match_reason": (
                    f"{', '.join(public_traits)} 팀에 잘 맞는 퀘스트예요."
                    if public_traits
                    else "지금 팀이 부담 없이 함께 시작하기 좋은 보완 퀘스트예요."
                ),
            }
        )
    return recommendations


def find_active_assignment(session_id: str, db: DBSession) -> QuestAssignment | None:
    return db.exec(
        select(QuestAssignment).where(
            QuestAssignment.session_id == session_id,
            QuestAssignment.status.in_(ACTIVE_STATUSES),
        )
    ).first()


async def assign_quest_for_room(
    session_id: str, db: DBSession, selected_quest_id: str | None = None
) -> QuestAssignment:
    """POST /rooms/{id}/quests/assign — 멱등. 이미 활성 배정이 있으면 그대로 반환한다."""
    existing = find_active_assignment(session_id, db)
    if existing is not None:
        return existing

    session = db.get(SessionModel, session_id)
    analysis = db.exec(
        select(AnalysisResult)
        .where(AnalysisResult.session_id == session_id)
        .order_by(AnalysisResult.analysis_version.desc())
    ).first()

    if session is None or analysis is None or session.status != "COMPLETED":
        raise app_error(ANALYSIS_NOT_READY, "팀 분석이 완료된 후에만 퀘스트를 배정할 수 있습니다.")

    context = build_match_context(session_id, analysis, db)
    if selected_quest_id:
        recommendation = next(
            (
                item
                for item in recommend_quests_for_room(session_id, db)
                if item["template"].quest_id == selected_quest_id
            ),
            None,
        )
        if recommendation is None:
            from app.errors import VALIDATION_ERROR

            raise app_error(VALIDATION_ERROR, "현재 팀에 추천된 퀘스트 중에서 선택해 주세요.")
        decision = QuestAssignmentDecision(
            quest_id=selected_quest_id,
            reason=recommendation["match_reason"],
            intro_message="세 가지 추천 중 우리 팀이 고른 아이스브레이킹을 시작해볼까요?",
            used_rule_ids=recommendation["used_rule_ids"],
            assignment_source="RULE",
        )
    else:
        decision = await decide_assignment(context)
    template = get_quest_template(decision.quest_id)
    if template is None:
        raise app_error(QUEST_CATALOG_UNAVAILABLE, "배정된 퀘스트를 카탈로그에서 찾을 수 없습니다.")

    assignment = QuestAssignment(
        id=str(uuid.uuid4()),
        session_id=session_id,
        quest_template_id=template.quest_id,
        status="ASSIGNED",
        active_slot=session_id,
        assignment_source=decision.assignment_source,
        assignment_reason=decision.reason,
        intro_message=decision.intro_message,
        used_rule_ids_json=json.dumps(decision.used_rule_ids),
        result_json=completion.dump_result(completion.empty_result()),
        version=template.version,
    )
    db.add(assignment)
    try:
        db.commit()
    except IntegrityError:
        # 동시 요청 경쟁 — UNIQUE(active_slot) 위반은 곧 "이미 배정됨"을 의미한다.
        db.rollback()
        existing = find_active_assignment(session_id, db)
        if existing is not None:
            return existing
        raise
    db.refresh(assignment)
    return assignment


def get_assignment_or_404(assignment_id: str, db: DBSession) -> QuestAssignment:
    assignment = db.get(QuestAssignment, assignment_id)
    if assignment is None:
        raise app_error(QUEST_ASSIGNMENT_NOT_FOUND, f"퀘스트 배정을 찾을 수 없습니다: {assignment_id}")
    return assignment


def start_assignment(assignment_id: str, db: DBSession) -> QuestAssignment:
    assignment = get_assignment_or_404(assignment_id, db)
    if assignment.status in TERMINAL_STATUSES:
        raise app_error(QUEST_ALREADY_FINALIZED, "이미 종료된 퀘스트는 다시 시작할 수 없습니다.")
    if assignment.status == "ASSIGNED":
        assignment.status = "IN_PROGRESS"
        assignment.started_at = datetime.now(timezone.utc)
        db.add(assignment)
        db.commit()
        db.refresh(assignment)
    return assignment


def _apply_member_response(
    assignment: QuestAssignment, db: DBSession, participant_id: str, checks: list[dict]
) -> QuestAssignment:
    if assignment.status in TERMINAL_STATUSES:
        raise app_error(QUEST_ALREADY_FINALIZED, "이미 종료된 퀘스트에는 응답할 수 없습니다.")

    result = completion.load_result(assignment.result_json)
    for check in checks:
        completion.apply_member_submission(
            result,
            participant_id,
            check["type"],
            count=check.get("count", 1),
            value=check.get("value"),
        )
    assignment.result_json = completion.dump_result(result)
    db.add(assignment)
    db.commit()
    db.refresh(assignment)
    return assignment


def submit_member_response(
    assignment_id: str, db: DBSession, participant_id: str, checks: list[dict]
) -> QuestAssignment:
    assignment = get_assignment_or_404(assignment_id, db)
    return _apply_member_response(assignment, db, participant_id, checks)


def submit_team_result(assignment_id: str, db: DBSession, checks: list[dict]) -> QuestAssignment:
    assignment = get_assignment_or_404(assignment_id, db)
    if assignment.status in TERMINAL_STATUSES:
        raise app_error(QUEST_ALREADY_FINALIZED, "이미 종료된 퀘스트에는 결과를 기록할 수 없습니다.")

    result = completion.load_result(assignment.result_json)
    for check in checks:
        completion.apply_team_submission(
            result, check["type"], count=check.get("count", 1), value=check.get("value")
        )
    assignment.result_json = completion.dump_result(result)
    db.add(assignment)
    db.commit()
    db.refresh(assignment)
    return assignment


def _finalize(session_id: str, assignment_id: str, db: DBSession, *, to_status: str) -> QuestAssignment:
    """COMPLETED/SKIPPED로의 원자적 전이.

    UPDATE ... WHERE status IN (ASSIGNED, IN_PROGRESS)로 실행해 rowcount==0이면
    "이미 다른 요청이 먼저 종료 상태를 확정했다"로 판단한다 — 완료/건너뛰기 동시 요청 규칙(§6).
    """
    now = datetime.now(timezone.utc)
    stmt = (
        update(QuestAssignment)
        .where(
            QuestAssignment.id == assignment_id,
            QuestAssignment.status.in_(ACTIVE_STATUSES),
        )
        .values(status=to_status, completed_at=now, active_slot=None)
    )
    result = db.exec(stmt)
    db.commit()

    assignment = get_assignment_or_404(assignment_id, db)
    if result.rowcount == 0:
        raise app_error(
            QUEST_ALREADY_FINALIZED,
            f"이미 {assignment.status} 상태로 종료된 퀘스트입니다.",
        )
    return assignment


def complete_assignment(assignment_id: str, db: DBSession) -> QuestAssignment:
    assignment = get_assignment_or_404(assignment_id, db)
    if assignment.status in TERMINAL_STATUSES:
        raise app_error(QUEST_ALREADY_FINALIZED, f"이미 {assignment.status} 상태로 종료된 퀘스트입니다.")

    template = get_quest_template(assignment.quest_template_id)
    if template is None:
        raise app_error(QUEST_CATALOG_UNAVAILABLE, "완료 조건을 확인할 퀘스트 정의를 찾을 수 없습니다.")

    member_ids = [p.id for p in _locked_participants(assignment.session_id, db)]
    result = completion.load_result(assignment.result_json)
    checks = template.completion_condition.get("checks", [])

    if not completion.is_completion_satisfied(checks, result, member_ids):
        raise app_error(
            COMPLETION_CONDITION_NOT_MET,
            "완료 조건을 아직 충족하지 못했습니다.",
        )

    return _finalize(assignment.session_id, assignment_id, db, to_status="COMPLETED")


def skip_assignment(assignment_id: str, db: DBSession) -> QuestAssignment:
    assignment = get_assignment_or_404(assignment_id, db)
    if assignment.status in TERMINAL_STATUSES:
        raise app_error(QUEST_ALREADY_FINALIZED, f"이미 {assignment.status} 상태로 종료된 퀘스트입니다.")
    return _finalize(assignment.session_id, assignment_id, db, to_status="SKIPPED")


def get_current_assignment(session_id: str, db: DBSession) -> QuestAssignment:
    active = find_active_assignment(session_id, db)
    if active is not None:
        return active
    latest = db.exec(
        select(QuestAssignment)
        .where(QuestAssignment.session_id == session_id)
        .order_by(QuestAssignment.assigned_at.desc())
    ).first()
    if latest is None:
        raise app_error(NO_ACTIVE_QUEST, "아직 배정된 퀘스트가 없습니다.")
    return latest

"""
AI 배정 함수 호출 어댑터 — SPEC_V5_CONTEST_QUEST_AGENT.md §5, 핵심결정 #14

역할 분리(SPEC §11 "AI" 항목): 후보 필터·점수·랭킹·Bedrock 선택·검증은 전부
`ai.quest_assignment`(AI 담당자 구현)의 책임이다. 백엔드는 여기서 그 함수를
호출하고, 결과를 저장하는 일만 한다 — 백엔드가 자체적으로 필터/점수 로직을
다시 구현하지 않는다.

`ai.quest_assignment.assign_quest(context, catalog) -> QuestAssignmentDecision`이
아직 없거나(ImportError), 타임아웃/예외를 던지거나, 반환값이 검증 조건(§5.2)을
통과하지 못하면 아주 얇은 안전망(build_minimal_fallback_decision)으로 넘어간다.
이 안전망은 점수 계산 없이 "범용 퀘스트 또는 quest_id가 가장 앞선 후보"만 고른다 —
진짜 필터/점수/랭킹은 여전히 AI 모듈 몫이며, 이건 그게 완전히 불가능할 때 전체
흐름이 죽지 않도록 하는 최후 수단일 뿐이다("Bedrock 실패 시 결정론적 폴백으로
전체 흐름을 완료한다").
"""

from __future__ import annotations

import asyncio
import logging

from app.errors import QUEST_CATALOG_UNAVAILABLE, app_error
from app.services.quests.schemas import QuestAssignmentDecision, QuestMatchContext, QuestTemplate

logger = logging.getLogger(__name__)

AGENT_TIMEOUT_SECONDS = 8.0


def _team_size_matches(template: QuestTemplate, team_size: int) -> bool:
    size = template.team_size or {}
    lo, hi = size.get("min"), size.get("max")
    if lo is None or hi is None:
        return False
    return lo <= team_size <= hi


def validate_decision(
    decision: QuestAssignmentDecision,
    catalog: list[QuestTemplate],
    context: QuestMatchContext,
) -> bool:
    """SPEC §5.2 검증 조건. quest_id는 넘겨준 카탈로그 안에 있어야 한다."""
    catalog_ids = {t.quest_id for t in catalog}
    if decision.quest_id not in catalog_ids:
        return False
    if not set(decision.used_rule_ids).issubset(set(context.matched_rule_ids)):
        return False
    return True


def build_minimal_fallback_decision(
    catalog: list[QuestTemplate], context: QuestMatchContext
) -> QuestAssignmentDecision:
    """AI 모듈이 아직 없거나 실패했을 때만 쓰는 최후 안전망.

    점수 계산 없이: (1) is_universal + 활성 + AUTO + LOW/MEDIUM + 인원 일치 +
    미완료 후보 중 quest_id가 가장 앞선 것을, 없으면 (2) 활성 + AUTO + LOW/MEDIUM +
    인원 일치 + 미완료 후보 중 quest_id가 가장 앞선 것을 고른다.
    """

    def _eligible(t: QuestTemplate) -> bool:
        return (
            t.is_active
            and t.assignment == "AUTO"
            and t.disclosure_level in ("LOW", "MEDIUM")
            and _team_size_matches(t, context.team_size)
            and t.quest_id not in context.completed_quest_ids
        )

    universal = sorted(
        (t for t in catalog if t.is_universal and _eligible(t)), key=lambda t: t.quest_id
    )
    chosen_pool = universal or sorted((t for t in catalog if _eligible(t)), key=lambda t: t.quest_id)

    if not chosen_pool:
        raise app_error(QUEST_CATALOG_UNAVAILABLE, "배정 가능한 퀘스트 후보가 카탈로그에 없습니다.")

    template = chosen_pool[0]
    used_rule_ids = [rid for rid in template.best_for if rid in context.matched_rule_ids]

    return QuestAssignmentDecision(
        quest_id=template.quest_id,
        reason=f"'{template.title}'은(는) 지금 이 팀에 적합한 아이스브레이킹 활동이에요.",
        intro_message=f"오늘의 팀 퀘스트는 '{template.title}'입니다. {template.summary}",
        used_rule_ids=used_rule_ids,
        assignment_source="FALLBACK",
    )


async def try_agent_decision(
    context: QuestMatchContext,
    catalog: list[QuestTemplate],
) -> QuestAssignmentDecision | None:
    """assign_quest를 시도하고, 실패/무효/미구현이면 None을 반환한다 (호출자가 폴백 처리)."""
    try:
        from ai.quest_assignment import assign_quest  # noqa: PLC0415 — 지연 import
    except ImportError:
        logger.info("ai.quest_assignment.assign_quest 미구현 — 결정론적 폴백으로 진행")
        return None

    try:
        decision = await asyncio.wait_for(assign_quest(context, catalog), timeout=AGENT_TIMEOUT_SECONDS)
    except (asyncio.TimeoutError, Exception):  # noqa: BLE001 — Bedrock/네트워크 예외를 흡수
        logger.exception("assign_quest 호출 실패 — 결정론적 폴백으로 진행")
        return None

    if not isinstance(decision, QuestAssignmentDecision) or not validate_decision(
        decision, catalog, context
    ):
        logger.warning("assign_quest 결과가 검증 조건을 통과하지 못함 — 결정론적 폴백으로 진행")
        return None

    return decision

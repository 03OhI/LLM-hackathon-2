"""
deterministic_fallback 노드 (SPEC_V5.2 §5.2, §9 — 최종 카탈로그 정책 반영)

후보가 아예 없거나(→ is_universal 재탐색) Bedrock이 재시도 후에도 실패하면
결정론적으로 하나를 골라 QuestAssignmentDecision을 만든다.

정렬 순서: score DESC → disclosure LOW 우선 → duration_minutes ASC
→ quest_id ASC (scoring.sort_for_fallback)

후보가 전혀 없으면 카탈로그에서 is_universal=true인 배정 가능한 퀘스트를
찾는다(범용 퀘스트는 오직 이 경로에서만 쓰인다 — 일반 후보 풀에는 애초에
들어가지 않는다, filter.filter_candidates 참고). 그마저 없으면 이는 데이터
구성 오류이므로, 존재하지 않는 quest_id로 "저장 가능해 보이는" 가짜 decision을
만들어 반환하지 않고 QuestCatalogConfigurationError를 던진다. 호출자
(app/services/quests/ai_client.py 등)가 이 예외를 카탈로그 구성 오류로
처리해야 한다.
"""

from __future__ import annotations

import logging

from ..errors import QuestCatalogConfigurationError
from ..filter import team_size_matches
from ..scoring import sort_for_fallback
from ..schemas import QuestAssignmentDecision, QuestAssignmentState, QuestTemplate

logger = logging.getLogger(__name__)

_MAX_USED_RULE_IDS = 3


def _used_rule_ids_for(quest: QuestTemplate, matched_rule_ids: list[str]) -> list[str]:
    relevant = set(quest.best_for) | set(quest.also_for)
    picked = [rid for rid in matched_rule_ids if rid in relevant]
    if picked:
        return picked[:_MAX_USED_RULE_IDS]
    return matched_rule_ids[:_MAX_USED_RULE_IDS]


def _find_universal_quest(
    catalog: list[QuestTemplate], context
) -> QuestTemplate | None:
    """범용 퀘스트는 오직 이 함수에서만 후보로 취급한다 — 일반 필터/랭킹에는
    참여하지 않는다(filter.filter_candidates가 is_universal을 항상 제외함)."""
    universal_candidates = [
        quest
        for quest in catalog
        if quest.is_universal
        and quest.is_active
        and quest.assignment == "AUTO"
        and quest.disclosure_level in ("LOW", "MEDIUM")
        and team_size_matches(quest, context.team_size)
        and quest.quest_id not in context.completed_quest_ids
    ]
    if not universal_candidates:
        return None

    ordered = sort_for_fallback(universal_candidates, context, catalog)
    return ordered[0]


def _decision_for(quest: QuestTemplate, context) -> QuestAssignmentDecision:
    reason = f"'{quest.title}'은(는) 지금 이 팀 상황에 무난하게 어울리는 활동이에요."
    intro = f"오늘의 팀 퀘스트는 '{quest.title}'입니다. {quest.summary}"
    return QuestAssignmentDecision(
        quest_id=quest.quest_id,
        reason=reason[:200],
        intro_message=intro[:200],
        used_rule_ids=_used_rule_ids_for(quest, context.matched_rule_ids),
        assignment_source="FALLBACK",
    )


def deterministic_fallback(state: QuestAssignmentState) -> dict:
    """결정론적 폴백.

    맞춤 후보 pool(ranked 또는 matched_candidates)이 있으면 그중 최선을 고르고,
    없으면 카탈로그에서 is_universal 퀘스트를 재탐색한다. 안전·인원 필터만
    통과했을 뿐 rule_id가 하나도 맞지 않는 "일반 무관 퀘스트"(state["candidates"])는
    절대 폴백 pool로 쓰지 않는다 — 그런 경우는 무조건 is_universal 재탐색으로
    간다. 그마저 없으면 저장 가능해 보이는 가짜 decision을 만드는 대신
    QuestCatalogConfigurationError를 던진다 — 호출자가 이를 명시적인 카탈로그
    구성 오류로 처리하도록 한다.
    """
    context = state["context"]
    valid_catalog = state.get("valid_catalog") or []
    pool = state.get("ranked") or state.get("matched_candidates") or []

    logger.warning(
        "deterministic_fallback: room_id=%s, pool_size=%d, errors=%s",
        context.room_id,
        len(pool),
        state.get("validation_errors", []),
    )

    if pool:
        ordered = sort_for_fallback(pool, context, valid_catalog)
        decision = _decision_for(ordered[0], context)
    else:
        universal_quest = _find_universal_quest(valid_catalog, context)
        if universal_quest is None:
            logger.error(
                "CONFIG_ERROR: room_id=%s — 카탈로그에 배정 가능한 퀘스트가 전혀 없다 "
                "(일반 AUTO 후보도, is_universal 폴백도 없음). "
                "데이터 팀에 quests.json 점검을 요청할 것.",
                context.room_id,
            )
            raise QuestCatalogConfigurationError(
                f"room_id={context.room_id}: 배정 가능한 퀘스트가 카탈로그에 없다 "
                "(일반 AUTO 후보 0개, is_universal 폴백 후보 0개)."
            )
        decision = _decision_for(universal_quest, context)

    return {"final": decision, "used_fallback": True}

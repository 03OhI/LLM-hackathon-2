"""
퀘스트 배정 LangGraph (SPEC_V5.2 §5.2)

load_context → validate_catalog → filter_candidates → match_candidates → rank_top_3
  → (맞춤 후보 없음) → deterministic_fallback → END   # is_universal 폴백만 시도
  → (맞춤 후보 있음) → select_with_bedrock → validate_decision
      → (통과) → END
      → (실패, retry_count < 2) → select_with_bedrock
      → (재실패 또는 timeout) → deterministic_fallback → END

filter_candidates(안전·인원)를 통과했다고 해서 전부 Bedrock 후보가 되지는
않는다 — match_candidates가 quest.best_for/also_for와 context.matched_rule_ids가
겹치는 것만 남긴다. 겹치는 게 하나도 없으면(=일반 무관 퀘스트만 남음) rank_top_3는
빈 리스트를 만들고, 그래프는 곧장 deterministic_fallback(is_universal 전용
재탐색)으로 간다 — 일반 무관 퀘스트를 선택하지 않는다.

기존 comment_graph.py와 동일하게 최초 시도 + 1회 재시도(총 2회) 후 폴백한다.
"""

from __future__ import annotations

import logging
from typing import Literal

from langgraph.graph import END, StateGraph

from .filter import filter_candidates, matched_candidates
from .nodes.fallback import deterministic_fallback
from .nodes.load import load_context, validate_catalog_node
from .nodes.select import select_with_bedrock
from .nodes.validate import validate_decision
from .scoring import rank_candidates
from .schemas import QuestAssignmentDecision, QuestAssignmentState, QuestMatchContext, QuestTemplate

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 2  # 최초 시도 + 1회 재시도


async def _filter_candidates_node(state: QuestAssignmentState) -> dict:
    valid_catalog = state["valid_catalog"]
    candidates = filter_candidates(valid_catalog, state["context"])
    logger.info("filter_candidates: %d/%d", len(candidates), len(valid_catalog))
    return {"candidates": candidates}


async def _match_candidates_node(state: QuestAssignmentState) -> dict:
    matched = matched_candidates(state["candidates"], state["context"])
    logger.info("match_candidates: %d/%d (rule_id 매칭)", len(matched), len(state["candidates"]))
    return {"matched_candidates": matched}


async def _rank_top_3_node(state: QuestAssignmentState) -> dict:
    ranked = rank_candidates(state["matched_candidates"], state["context"], state["valid_catalog"])
    return {"ranked": ranked}


def _route_after_rank(
    state: QuestAssignmentState,
) -> Literal["select_with_bedrock", "deterministic_fallback"]:
    return "select_with_bedrock" if state["ranked"] else "deterministic_fallback"


def _route_after_validate(
    state: QuestAssignmentState,
) -> Literal["select_with_bedrock", "deterministic_fallback", "__end__"]:
    errors = state.get("validation_errors", [])
    final = state.get("final")

    if not errors and final is not None:
        return END
    if state["retry_count"] < MAX_ATTEMPTS:
        return "select_with_bedrock"
    return "deterministic_fallback"


def build_quest_assignment_graph() -> StateGraph:
    """퀘스트 배정 LangGraph를 구성하고 컴파일한다."""
    graph = StateGraph(QuestAssignmentState)

    graph.add_node("load_context", load_context)
    graph.add_node("validate_catalog", validate_catalog_node)
    graph.add_node("filter_candidates", _filter_candidates_node)
    graph.add_node("match_candidates", _match_candidates_node)
    graph.add_node("rank_top_3", _rank_top_3_node)
    graph.add_node("select_with_bedrock", select_with_bedrock)
    graph.add_node("validate_decision", validate_decision)
    graph.add_node("deterministic_fallback", deterministic_fallback)

    graph.set_entry_point("load_context")
    graph.add_edge("load_context", "validate_catalog")
    graph.add_edge("validate_catalog", "filter_candidates")
    graph.add_edge("filter_candidates", "match_candidates")
    graph.add_edge("match_candidates", "rank_top_3")

    graph.add_conditional_edges(
        "rank_top_3",
        _route_after_rank,
        {
            "select_with_bedrock": "select_with_bedrock",
            "deterministic_fallback": "deterministic_fallback",
        },
    )

    graph.add_edge("select_with_bedrock", "validate_decision")

    graph.add_conditional_edges(
        "validate_decision",
        _route_after_validate,
        {
            "select_with_bedrock": "select_with_bedrock",
            "deterministic_fallback": "deterministic_fallback",
            END: END,
        },
    )

    graph.add_edge("deterministic_fallback", END)

    return graph.compile()


quest_assignment_graph = build_quest_assignment_graph()


async def assign_quest(
    context: QuestMatchContext,
    catalog: list[QuestTemplate],
) -> QuestAssignmentDecision:
    """퀘스트 배정 공개 함수 (SPEC_V5.2 §5, §11 AI 역할 — 공개 계약).

    DB session/ORM에 의존하지 않는 순수 함수다. Bedrock 실패·timeout·검증
    재실패 등 대부분의 경우 null이 아닌 유효한 QuestAssignmentDecision을
    반환한다.

    예외: 카탈로그에 배정 가능한 퀘스트가 전혀 없는 경우(일반 AUTO 후보도,
    is_universal 폴백 후보도 없음)에는 존재하지 않는 quest_id로 가짜 decision을
    만들어 반환하지 않고 `ai.quest_assignment.errors.QuestCatalogConfigurationError`를
    던진다 — 이 상태는 카탈로그 데이터 구성 오류이지 정상적인 폴백 시나리오가
    아니다. 호출자가 이 예외를 명시적인 구성 오류로 처리해야 한다.
    """
    initial_state: QuestAssignmentState = {
        "context": context,
        "raw_catalog": catalog,
        "valid_catalog": [],
        "catalog_errors": [],
        "candidates": [],
        "matched_candidates": [],
        "ranked": [],
        "draft": None,
        "bedrock_skipped": False,
        "validation_errors": [],
        "retry_count": 0,
        "final": None,
        "used_fallback": False,
    }

    logger.info(
        "assign_quest: room_id=%s, team_size=%d, catalog_size=%d",
        context.room_id,
        context.team_size,
        len(catalog),
    )

    final_state = await quest_assignment_graph.ainvoke(initial_state)

    decision = final_state.get("final")
    if decision is None:
        # 방어적 안전망: 그래프가 어떤 이유로든 final을 못 채워도 null을 반환하지 않는다.
        logger.error("assign_quest: final이 비어 있어 방어적 폴백을 실행한다")
        fallback_result = deterministic_fallback(final_state)
        decision = fallback_result["final"]

    return decision

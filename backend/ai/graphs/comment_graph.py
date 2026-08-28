"""
LangGraph 코멘트 생성 그래프 (V2)

생성 → 검증 → (통과 → END | 최초 실패 → 재생성 | 재실패·timeout → fallback → END)

audience가 TEAM이면 TeamSnapshot, SELF_ONLY이면 PrivateCard를 처리한다.
기존 재시도 횟수(1회)와 종료 조건을 유지한다.
"""

from __future__ import annotations

import logging
from typing import Literal

from langgraph.graph import END, StateGraph

from ..nodes.fallback import render_fallback
from ..nodes.generate import generate_comment
from ..nodes.validate import validate_comment
from ..schemas import CommentGraphState

logger = logging.getLogger(__name__)


def _should_continue(state: CommentGraphState) -> Literal["generate_comment", "render_fallback", "__end__"]:
    """validate 노드 이후의 조건부 라우팅"""
    errors = state.get("validation_errors", [])
    final = state.get("final")

    # 검증 통과
    if not errors and final is not None:
        return END

    # 재시도 가능 여부
    if state["retry_count"] < 2:
        return "generate_comment"
    else:
        return "render_fallback"


def build_comment_graph() -> StateGraph:
    """코멘트 생성 LangGraph를 구성하고 컴파일한다."""
    graph = StateGraph(CommentGraphState)

    graph.add_node("generate_comment", generate_comment)
    graph.add_node("validate_comment", validate_comment)
    graph.add_node("render_fallback", render_fallback)

    graph.set_entry_point("generate_comment")
    graph.add_edge("generate_comment", "validate_comment")

    graph.add_conditional_edges(
        "validate_comment",
        _should_continue,
        {
            "generate_comment": "generate_comment",
            "render_fallback": "render_fallback",
            END: END,
        },
    )

    graph.add_edge("render_fallback", END)

    return graph.compile()


comment_graph = build_comment_graph()


def run_comment_graph(
    audience: Literal["TEAM", "SELF_ONLY"],
    analysis_result_id: str,
    participant_id: str | None,
    allowed_strength_codes: list[str],
    allowed_caution_codes: list[str],
    allowed_recommendation_codes: list[str],
    allowed_rule_ids: list[str],
    knowledge_context: dict,
) -> dict:
    """코멘트 그래프를 실행하고 최종 결과를 반환한다.

    Returns:
        {
            "insight": TeamSnapshot | PrivateCard,
            "used_fallback": bool,
            "validation_errors": list[str],
        }
    """
    initial_state: CommentGraphState = {
        "audience": audience,
        "analysis_result_id": analysis_result_id,
        "participant_id": participant_id,
        "allowed_strength_codes": allowed_strength_codes,
        "allowed_caution_codes": allowed_caution_codes,
        "allowed_recommendation_codes": allowed_recommendation_codes,
        "allowed_rule_ids": allowed_rule_ids,
        "knowledge_context": knowledge_context,
        "draft": None,
        "validation_errors": [],
        "retry_count": 0,
        "final": None,
        "used_fallback": False,
    }

    logger.info(
        "run_comment_graph: audience=%s, analysis_result_id=%s",
        audience,
        analysis_result_id,
    )

    final_state = comment_graph.invoke(initial_state)

    return {
        "insight": final_state.get("final"),
        "used_fallback": final_state.get("used_fallback", False),
        "validation_errors": final_state.get("validation_errors", []),
    }

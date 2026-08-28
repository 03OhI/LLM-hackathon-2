"""
LangGraph 코멘트 생성 그래프

생성 → 검증 → (통과 → END | 최초 실패 → 재생성 | 재실패·timeout → fallback → END)

팀 코멘트와 개인 코멘트는 같은 그래프 구조를 사용하되
서로 다른 입력 스키마·프롬프트·저장소를 사용한다.
MVP에서는 영속 체크포인트 없이 요청 단위로 그래프를 실행한다.
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
    """validate 노드 이후의 조건부 라우팅

    - validation_errors가 비어있고 final이 있으면 → END
    - retry_count < 2 (첫 시도 실패) → generate_comment (재시도)
    - retry_count >= 2 (재시도도 실패) → render_fallback
    """
    errors = state.get("validation_errors", [])
    final = state.get("final")

    # 검증 통과
    if not errors and final is not None:
        return END

    # LLM 에러 또는 검증 실패 → 재시도 가능 여부 확인
    if state["retry_count"] < 2:
        return "generate_comment"
    else:
        return "render_fallback"


def build_comment_graph() -> StateGraph:
    """코멘트 생성 LangGraph를 구성하고 컴파일한다."""

    graph = StateGraph(CommentGraphState)

    # 노드 등록
    graph.add_node("generate_comment", generate_comment)
    graph.add_node("validate_comment", validate_comment)
    graph.add_node("render_fallback", render_fallback)

    # 엣지 정의
    graph.set_entry_point("generate_comment")
    graph.add_edge("generate_comment", "validate_comment")

    # 조건부 엣지: validate 이후 분기
    graph.add_conditional_edges(
        "validate_comment",
        _should_continue,
        {
            "generate_comment": "generate_comment",
            "render_fallback": "render_fallback",
            END: END,
        },
    )

    # fallback은 항상 END
    graph.add_edge("render_fallback", END)

    return graph.compile()


# 모듈 레벨 컴파일된 그래프 인스턴스
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
            "insight": GeneratedInsight,
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

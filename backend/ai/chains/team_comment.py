"""
팀 코멘트 생성 체인 (V2)

규칙 엔진의 팀 분석 결과를 받아 LangGraph 그래프를 실행하고
TeamSnapshot을 반환한다.

team_grade는 AI에 전달하지 않는다.
"""

from __future__ import annotations

import logging

from ..config import get_ai_settings
from ..graphs.comment_graph import run_comment_graph
from ..schemas import GenerationResult, TeamCommentInput

logger = logging.getLogger(__name__)


def generate_team_comment(input_data: TeamCommentInput) -> GenerationResult:
    """팀 코멘트를 생성한다.

    Args:
        input_data: 규칙 엔진이 생성한 팀 분석 입력
                    (team_grade는 포함되지 않음)

    Returns:
        GenerationResult (insight=TeamSnapshot)
    """
    settings = get_ai_settings()

    # team_grade를 AI knowledge_context에 포함하지 않는다
    knowledge_context = {
        "team_size": input_data.team_size,
        "distribution": input_data.distribution.model_dump() if input_data.distribution else {},
    }

    result = run_comment_graph(
        audience="TEAM",
        analysis_result_id=input_data.analysis_result_id,
        participant_id=None,
        allowed_strength_codes=input_data.strength_codes,
        allowed_caution_codes=[],  # TEAM 공개에는 caution 미전달
        allowed_recommendation_codes=[],  # TEAM 공개에는 recommendation 미전달
        allowed_rule_ids=input_data.matched_rule_ids,
        knowledge_context=knowledge_context,
    )

    used_fallback = result["used_fallback"]

    logger.info(
        "generate_team_comment: analysis_result_id=%s, used_fallback=%s",
        input_data.analysis_result_id,
        used_fallback,
    )

    return GenerationResult(
        audience="TEAM",
        status="FALLBACK" if used_fallback else "COMPLETED",
        insight=result["insight"],
        used_fallback=used_fallback,
        model_id=settings.bedrock_model_id,
        prompt_version=settings.team_prompt_version,
        validation_errors=result["validation_errors"],
    )

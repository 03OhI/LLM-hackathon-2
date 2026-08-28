"""
팀 코멘트 생성 체인

규칙 엔진의 팀 분석 결과를 받아 LangGraph 그래프를 실행하고
팀 공용 코멘트를 반환한다.
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
                    (analysis_result_id, matched_rule_ids 포함)

    Returns:
        GenerationResult: 백엔드가 DB에 저장할 최종 결과
    """
    settings = get_ai_settings()

    knowledge_context = {
        "team_grade": input_data.team_grade,
        "team_size": input_data.team_size,
        "evidence_levels": input_data.evidence_levels,
        "distribution": input_data.distribution,
    }

    result = run_comment_graph(
        audience="TEAM",
        analysis_result_id=input_data.analysis_result_id,
        participant_id=None,
        allowed_strength_codes=input_data.strength_codes,
        allowed_caution_codes=input_data.caution_codes,
        allowed_recommendation_codes=input_data.recommendation_codes,
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
        status="FALLBACK" if used_fallback else "COMPLETED",
        insight=result["insight"],
        used_fallback=used_fallback,
        model_id=settings.bedrock_model_id,
        prompt_version=settings.team_prompt_version,
        validation_errors=result["validation_errors"],
    )

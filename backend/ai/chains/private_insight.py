"""
개인 인사이트 생성 체인 (V2)

참여자별로 개별 호출하며, 다른 참여자의 정보를 프롬프트에 포함하지 않는다.
PrivateCard를 반환한다.
"""

from __future__ import annotations

import logging

from ..config import get_ai_settings
from ..graphs.comment_graph import run_comment_graph
from ..schemas import GenerationResult, PrivateInsightInput

logger = logging.getLogger(__name__)


def generate_private_insight(input_data: PrivateInsightInput) -> GenerationResult:
    """개인 인사이트를 생성한다.

    Args:
        input_data: 규칙 엔진이 생성한 개인 분석 입력

    Returns:
        GenerationResult (insight=PrivateCard)
    """
    settings = get_ai_settings()

    knowledge_context = {
        "self_positions": input_data.self_positions.to_dict(),
        "team_aggregate": input_data.team_aggregate.model_dump(),
        "other_participant_names": [],
        "other_participant_ids": [],
    }

    result = run_comment_graph(
        audience="SELF_ONLY",
        analysis_result_id=input_data.analysis_result_id,
        participant_id=input_data.participant_id,
        allowed_strength_codes=input_data.strength_codes,
        allowed_caution_codes=input_data.caution_codes,
        allowed_recommendation_codes=input_data.recommendation_codes,
        allowed_rule_ids=input_data.matched_rule_ids,
        knowledge_context=knowledge_context,
    )

    used_fallback = result["used_fallback"]

    logger.info(
        "generate_private_insight: participant_id=%s, used_fallback=%s",
        input_data.participant_id,
        used_fallback,
    )

    return GenerationResult(
        audience="SELF_ONLY",
        status="FALLBACK" if used_fallback else "COMPLETED",
        insight=result["insight"],
        used_fallback=used_fallback,
        model_id=settings.bedrock_model_id,
        prompt_version=settings.private_prompt_version,
        validation_errors=result["validation_errors"],
    )

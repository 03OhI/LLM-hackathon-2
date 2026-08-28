"""
개인 인사이트 생성 체인

참여자별로 개별 호출하며, 다른 참여자의 정보를 프롬프트에 포함하지 않는다.
각 참여자가 /results/me를 처음 열 때 1회 생성 후 캐시한다.
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
                    (analysis_result_id, participant_id, matched_rule_ids 포함)

    Returns:
        GenerationResult: 백엔드가 DB에 저장할 최종 결과
    """
    settings = get_ai_settings()

    knowledge_context = {
        "self_positions": input_data.self_positions.to_dict(),
        "team_aggregate": input_data.team_aggregate.model_dump(),
        # 다른 참여자의 닉네임·개별 응답·개인 주의점은 넣지 않는다
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
        status="FALLBACK" if used_fallback else "COMPLETED",
        insight=result["insight"],
        used_fallback=used_fallback,
        model_id=settings.bedrock_model_id,
        prompt_version=settings.private_prompt_version,
        validation_errors=result["validation_errors"],
    )

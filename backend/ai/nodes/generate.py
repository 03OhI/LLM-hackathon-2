"""
generate 노드 - LangChain 구조화 출력으로 코멘트를 생성한다.

- 첫 시도: 팀/개인 프롬프트 템플릿 사용
- 재시도: revision 프롬프트 + 이전 검증 오류 포함
"""

from __future__ import annotations

import logging
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage

from ..config import get_structured_model
from ..schemas import CommentGraphState, GeneratedInsight

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent.parent / "prompts"


def _load_prompt(filename: str) -> str:
    """프롬프트 파일을 읽어 반환한다."""
    return (PROMPTS_DIR / filename).read_text(encoding="utf-8")


def _build_team_prompt(state: CommentGraphState) -> str:
    """팀 코멘트용 프롬프트를 구성한다."""
    template = _load_prompt("team_comment_v1.txt")
    ctx = state["knowledge_context"]

    return template.format(
        team_grade=ctx.get("team_grade", "MID"),
        team_size=ctx.get("team_size", 4),
        strength_codes=", ".join(state["allowed_strength_codes"]),
        caution_codes=", ".join(state["allowed_caution_codes"]),
        allowed_recommendations=", ".join(state["allowed_recommendation_codes"]),
        evidence_levels=str(ctx.get("evidence_levels", {})),
    )


def _build_private_prompt(state: CommentGraphState) -> str:
    """개인 인사이트용 프롬프트를 구성한다."""
    template = _load_prompt("private_insight_v1.txt")
    ctx = state["knowledge_context"]

    return template.format(
        self_positions=str(ctx.get("self_positions", {})),
        team_aggregate=str(ctx.get("team_aggregate", {})),
        strength_codes=", ".join(state["allowed_strength_codes"]),
        caution_codes=", ".join(state["allowed_caution_codes"]),
        allowed_recommendations=", ".join(state["allowed_recommendation_codes"]),
    )


def _build_revision_prompt(state: CommentGraphState) -> str:
    """검증 실패 후 재생성용 프롬프트를 구성한다."""
    template = _load_prompt("revision_v1.txt")

    return template.format(
        validation_errors="\n".join(
            f"- {err}" for err in state["validation_errors"]
        ),
        allowed_strength_codes=", ".join(state["allowed_strength_codes"]),
        allowed_caution_codes=", ".join(state["allowed_caution_codes"]),
        allowed_recommendation_codes=", ".join(state["allowed_recommendation_codes"]),
        allowed_rule_ids=", ".join(state["allowed_rule_ids"]),
    )


def generate_comment(state: CommentGraphState) -> dict:
    """LLM을 호출하여 구조화된 코멘트를 생성한다.

    Returns:
        상태 업데이트 dict (draft, retry_count)
    """
    is_retry = state["retry_count"] > 0

    try:
        # 프롬프트 선택
        if is_retry:
            user_prompt = _build_revision_prompt(state)
        elif state["audience"] == "TEAM":
            user_prompt = _build_team_prompt(state)
        else:
            user_prompt = _build_private_prompt(state)

        structured_model = get_structured_model()

        messages = [
            SystemMessage(content="당신은 팀 협업 성향 기반 코멘트 작성 전문가입니다."),
            HumanMessage(content=user_prompt),
        ]

        result: GeneratedInsight = structured_model.invoke(messages)

        logger.info(
            "generate_comment: audience=%s, retry=%d, codes_used=%d",
            state["audience"],
            state["retry_count"],
            len(result.used_rule_ids),
        )

        return {
            "draft": result,
            "retry_count": state["retry_count"] + 1,
        }

    except Exception as e:
        logger.error("generate_comment failed: %s", str(e))
        # timeout, parse error 등 → 검증 실패로 처리하여 fallback 경로로 이동
        return {
            "draft": None,
            "validation_errors": [f"LLM_ERROR: {type(e).__name__}: {str(e)}"],
            "retry_count": state["retry_count"] + 1,
        }

"""
generate 노드 — LangChain 구조화 출력으로 TeamSnapshot / PrivateCard를 생성한다.

- 첫 시도: audience에 따라 team_snapshot_v2 또는 private_card_v2 프롬프트
- 재시도: 원래 프롬프트 + revision_v2 (검증 오류 + 수정 지침)
  → 원래 입력 컨텍스트(distribution, self_positions 등)를 유지한다.
"""

from __future__ import annotations

import logging
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage

from ..config import get_structured_model
from ..schemas import CommentGraphState, PrivateCard, TeamSnapshot

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent.parent / "prompts"


def _load_prompt(filename: str) -> str:
    return (PROMPTS_DIR / filename).read_text(encoding="utf-8")


def _build_team_prompt(state: CommentGraphState) -> str:
    template = _load_prompt("team_snapshot_v2.txt")
    ctx = state["knowledge_context"]

    return template.format(
        team_size=ctx.get("team_size", 4),
        distribution=str(ctx.get("distribution", {})),
        strength_codes=", ".join(state["allowed_strength_codes"]),
        allowed_rule_ids=", ".join(state["allowed_rule_ids"]),
    )


def _build_private_prompt(state: CommentGraphState) -> str:
    template = _load_prompt("private_card_v2.txt")
    ctx = state["knowledge_context"]

    return template.format(
        self_positions=str(ctx.get("self_positions", {})),
        team_aggregate=str(ctx.get("team_aggregate", {})),
        strength_codes=", ".join(state["allowed_strength_codes"]),
        caution_codes=", ".join(state["allowed_caution_codes"]),
        allowed_rule_ids=", ".join(state["allowed_rule_ids"]),
    )


def _build_revision_suffix(state: CommentGraphState) -> str:
    """검증 실패 정보와 수정 지침을 반환한다."""
    template = _load_prompt("revision_v2.txt")
    return template.format(
        validation_errors="\n".join(f"- {err}" for err in state["validation_errors"]),
        allowed_rule_ids=", ".join(state["allowed_rule_ids"]),
    )


def generate_comment(state: CommentGraphState) -> dict:
    """LLM을 호출하여 TeamSnapshot 또는 PrivateCard를 생성한다."""
    is_retry = state["retry_count"] > 0
    is_team = state["audience"] == "TEAM"

    try:
        output_schema = TeamSnapshot if is_team else PrivateCard

        # 원래 프롬프트는 항상 구성 (재시도에서도 입력 컨텍스트 유지)
        if is_team:
            base_prompt = _build_team_prompt(state)
        else:
            base_prompt = _build_private_prompt(state)

        # 재시도 시 원래 프롬프트 뒤에 수정 지침 추가
        if is_retry:
            revision = _build_revision_suffix(state)
            user_prompt = f"{base_prompt}\n\n---\n\n{revision}"
        else:
            user_prompt = base_prompt

        structured_model = get_structured_model(output_schema)

        system_msg = (
            "당신은 팀 구성을 재미있고 중립적으로 표현하는 카피라이터입니다."
            if is_team
            else "당신은 개인이 팀에서 활용할 수 있는 모습을 따뜻하게 표현하는 작성자입니다."
        )

        messages = [
            SystemMessage(content=system_msg),
            HumanMessage(content=user_prompt),
        ]

        result = structured_model.invoke(messages)

        logger.info(
            "generate_comment: audience=%s, retry=%d",
            state["audience"],
            state["retry_count"],
        )

        return {
            "draft": result,
            "retry_count": state["retry_count"] + 1,
        }

    except Exception as e:
        logger.error("generate_comment failed: %s", str(e))
        return {
            "draft": None,
            "validation_errors": [f"LLM_ERROR: {type(e).__name__}: {str(e)}"],
            "retry_count": state["retry_count"] + 1,
        }

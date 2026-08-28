"""
select_with_bedrock 노드 (SPEC_V5.2 §5.1, §5.2, §7)

상위 후보(최대 3개)의 공개 메타데이터만 프롬프트에 넣고, Bedrock 구조화 출력으로
quest_id/reason/intro_message/used_rule_ids만 받는다. 참여자 식별자·개인
positions·설문 원문·team_grade·internal_index·caution 점수·다른 팀원의 개인
카드는 절대 프롬프트에 넣지 않는다.

기존 팀 코멘트 체인과 동일하게 ai.config.get_ai_settings()/get_chat_model()의
Bedrock 클라이언트·timeout 설정을 재사용한다. get_structured_model() 헬퍼는
현재 GeneratedInsight(V1) 전용으로 고정돼 있어 그대로 쓸 수 없으므로, 같은
get_chat_model()에 이 모듈만의 출력 스키마를 with_structured_output()으로
얹어 "재사용" 원칙을 지키면서도 이 모듈을 자기완결적으로 유지한다.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage

from ...config import get_ai_settings, get_chat_model
from ..schemas import QuestAssignmentState, QuestSelectionOutput, QuestTemplate

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent.parent / "prompts"


def _load_prompt(filename: str) -> str:
    return (PROMPTS_DIR / filename).read_text(encoding="utf-8")


def _format_candidates(candidates: list[QuestTemplate]) -> str:
    """후보의 공개 메타데이터만 텍스트로 만든다.

    steps/deliverable/completion_condition/materials/safety_notes/reveals_axes/
    version은 의도적으로 포함하지 않는다 — LLM이 퀘스트 본문을 언급·수정할
    소지를 프롬프트 단계에서부터 차단한다.
    """
    lines = []
    for quest in candidates:
        lines.append(
            "\n".join(
                [
                    f"- quest_id: {quest.quest_id}",
                    f"  title: {quest.title}",
                    f"  summary: {quest.summary}",
                    f"  category: {quest.category}",
                    f"  duration_minutes: {quest.duration_minutes}",
                    f"  disclosure_level: {quest.disclosure_level}",
                    f"  is_universal: {quest.is_universal}",
                    f"  best_for: {quest.best_for}",
                    f"  also_for: {quest.also_for}",
                    f"  context_tags: {quest.context_tags}",
                ]
            )
        )
    return "\n".join(lines)


def _build_prompt(state: QuestAssignmentState) -> str:
    context = state["context"]
    template = _load_prompt("quest_select_v1.txt")
    return template.format(
        room_id=context.room_id,
        team_size=context.team_size,
        matched_rule_ids=", ".join(context.matched_rule_ids),
        distribution=str(context.distribution),
        context_tags=", ".join(context.context_tags),
        candidates=_format_candidates(state["ranked"]),
    )


def _build_revision_suffix(state: QuestAssignmentState) -> str:
    template = _load_prompt("quest_select_revision_v1.txt")
    return template.format(
        validation_errors="\n".join(f"- {err}" for err in state["validation_errors"]),
    )


def _used_rule_ids_for(quest: QuestTemplate, matched_rule_ids: list[str]) -> list[str]:
    relevant = set(quest.best_for) | set(quest.also_for)
    return [rid for rid in matched_rule_ids if rid in relevant][:3]


def _skip_bedrock_draft(state: QuestAssignmentState) -> QuestSelectionOutput:
    """후보가 하나뿐이고 설정이 허용하면 결정론적으로 draft를 만든다.

    검증 노드(validate_decision)는 이 draft도 LLM 산출물과 동일하게 검사한다.
    """
    quest = state["ranked"][0]
    context = state["context"]
    reason = f"'{quest.title}'이(가) 지금 팀 상황에 맞는 단일 자동 후보예요."
    intro = f"오늘의 팀 퀘스트는 '{quest.title}'입니다."
    return QuestSelectionOutput(
        quest_id=quest.quest_id,
        reason=reason[:120],
        intro_message=intro[:120],
        used_rule_ids=_used_rule_ids_for(quest, context.matched_rule_ids),
    )


async def select_with_bedrock(state: QuestAssignmentState) -> dict:
    """LangChain 구조화 출력으로 QuestSelectionOutput을 생성한다."""
    settings = get_ai_settings()
    retry_count = state["retry_count"]
    ranked = state["ranked"]

    if (
        retry_count == 0
        and len(ranked) == 1
        and settings.quest_skip_bedrock_for_single_candidate
    ):
        logger.info("select_with_bedrock: 단일 후보 — Bedrock 생략")
        return {
            "draft": _skip_bedrock_draft(state),
            "bedrock_skipped": True,
            "retry_count": retry_count + 1,
        }

    try:
        base_prompt = _build_prompt(state)
        if retry_count > 0:
            revision = _build_revision_suffix(state)
            user_prompt = f"{base_prompt}\n\n---\n\n{revision}"
        else:
            user_prompt = base_prompt

        structured_model = get_chat_model().with_structured_output(QuestSelectionOutput)

        messages = [
            SystemMessage(
                content=(
                    "당신은 팀에게 배정할 아이스브레이킹 퀘스트를 후보 중에서 고르고 "
                    "짧은 소개 문구를 쓰는 도우미입니다."
                )
            ),
            HumanMessage(content=user_prompt),
        ]

        result = await asyncio.wait_for(
            structured_model.ainvoke(messages),
            timeout=settings.bedrock_timeout,
        )

        logger.info("select_with_bedrock: retry=%d", retry_count)

        return {
            "draft": result,
            "bedrock_skipped": False,
            "retry_count": retry_count + 1,
        }

    except Exception as e:  # noqa: BLE001 — timeout/파싱/네트워크 오류를 모두 폴백으로 흡수
        logger.error("select_with_bedrock failed: %s", str(e))
        return {
            "draft": None,
            "bedrock_skipped": False,
            "validation_errors": [f"LLM_ERROR: {type(e).__name__}: {str(e)}"],
            "retry_count": retry_count + 1,
        }

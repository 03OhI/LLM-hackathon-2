"""
퀘스트 카탈로그 오프라인 생성 스크립트

knowledge_base/quests.yaml의 team_quests / personal_quests 섹션을
Bedrock으로 생성/확장하기 위한 배치 스크립트다.

★ 런타임(API 요청 처리 중)에는 절대 이 모듈을 import하지 않는다.
  app/services/chemistry/engine.py는 quests.yaml을 읽기만 하고,
  실제 퀘스트 "생성"은 이 스크립트로 사전에(오프라인) 수행한다.
  즉 서빙 시점에는 LLM 호출이 없다 — 결정론적 매칭만 수행한다.

사용법 (AWS 자격 증명이 boto3 기본 체인에 설정되어 있어야 함):

    cd backend
    python -m ai.generate_quests --scope team --count 12 --out /tmp/team_quests_new.yaml
    python -m ai.generate_quests --scope personal --count 16 --out /tmp/personal_quests_new.yaml

생성된 조각은 사람이 검수 후 knowledge_base/quests.yaml에 수동으로 합친다
(자동 merge/overwrite는 하지 않는다 — 기존 quest_code를 실수로 지우는 사고를 방지).
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# team_rules.yaml / private_insight_rules.yaml에서 실제 쓰이는 조건 어휘.
# 생성된 퀘스트의 when 조건이 반드시 이 어휘 안에 들도록 프롬프트에 명시한다.
TEAM_AXES = ("planning", "agency", "conflict", "communication")
TEAM_CONDITIONS = (
    "balanced",
    "majority_upper",
    "majority_lower",
    "all_upper",
    "all_lower",
    "has_upper",
    "has_lower",
    "no_upper",
    "no_lower",
)
POSITION_BY_AXIS = {
    "planning": ("PLANNER", "ADAPTER"),
    "agency": ("DRIVER", "SUPPORTER"),
    "conflict": ("CONFRONTER", "HARMONIZER"),
    "communication": ("DIRECT", "TACTFUL"),
}


class GeneratedQuest(BaseModel):
    """LLM 구조화 출력 스키마 — 사람이 검수하기 쉬운 최소 형태."""

    quest_code: str = Field(description="영문 대문자 스네이크케이스 고유 식별자, 접두사 TEAM_Q_ 또는 PERSONAL_Q_")
    axis: str = Field(description="TEAM_AXES 중 하나")
    condition_or_position: str = Field(
        description="scope=team이면 TEAM_CONDITIONS 중 하나, scope=personal이면 해당 axis의 포지션 값"
    )
    title: str = Field(max_length=40)
    description: str = Field(max_length=120)
    action: str = Field(max_length=120, description="지금 바로 해볼 수 있는 구체적 행동 한 가지")
    tags: list[str] = Field(default_factory=list)


class GeneratedQuestBatch(BaseModel):
    quests: list[GeneratedQuest]


def _build_prompt(scope: Literal["team", "personal"], count: int) -> str:
    axes_desc = "\n".join(
        f"- {axis}: 상위극={pos[0]}, 하위극={pos[1]}" for axis, pos in POSITION_BY_AXIS.items()
    )

    if scope == "team":
        condition_desc = ", ".join(TEAM_CONDITIONS)
        target = (
            "세션에 참여한 팀 전체가 함께 시도하는 아이스브레이커 미션. "
            "팀원 중 누구나 완료 체크를 할 수 있다는 전제로 작성한다."
        )
    else:
        condition_desc = "해당 axis의 상위극 또는 하위극 값 (예: PLANNER, DIRECT 등)"
        target = "참여자 개인에게 배정되는, 지금 바로 해볼 수 있는 작은 행동 제안."

    return f"""당신은 팀 협업 아이스브레이커 퀘스트를 만드는 카피라이터입니다.

축(axis) 정의:
{axes_desc}

목표: {target}

요구사항:
- 정확히 {count}개의 퀘스트를 생성한다.
- 각 퀘스트는 axis 1개 + condition_or_position 값 1개에 매칭된다 ({condition_desc} 중 선택).
- 점수·등급·진단·평가 표현을 쓰지 않는다 (오락/협업 참고용 톤 유지).
- 명령형이 아니라 제안형 어투를 쓴다 ("~해보세요", "~해도 좋아요").
- title은 40자 이내, description은 120자 이내, action은 120자 이내.
- quest_code는 중복 없이 고유해야 한다.
"""


def generate_quests(scope: Literal["team", "personal"], count: int) -> GeneratedQuestBatch:
    """Bedrock을 호출해 퀘스트 배치를 생성한다.

    ai/config.py의 get_structured_model과 동일한 자격 증명 체인을 사용한다
    (boto3 기본 체인 — EC2 인스턴스 프로파일 또는 로컬 AWS_PROFILE).
    """
    from ai.config import get_chat_model

    chat_model = get_chat_model()
    structured_model = chat_model.with_structured_output(GeneratedQuestBatch)

    prompt = _build_prompt(scope, count)
    logger.info("generate_quests: scope=%s count=%d — Bedrock 호출", scope, count)

    result = structured_model.invoke(prompt)
    if not isinstance(result, GeneratedQuestBatch):
        # with_structured_output이 dict를 반환하는 버전 호환
        result = GeneratedQuestBatch.model_validate(result)
    return result


def _to_yaml_fragment(scope: Literal["team", "personal"], batch: GeneratedQuestBatch) -> dict:
    """quests.yaml에 수동으로 병합하기 쉬운 형태로 변환한다."""
    key = "team_quests" if scope == "team" else "personal_quests"
    items = []
    for q in batch.quests:
        if scope == "team":
            when = {"axis": q.axis, "condition": q.condition_or_position}
        else:
            when = {f"self.{q.axis}": q.condition_or_position}
        items.append(
            {
                "quest_code": q.quest_code,
                "when": when,
                "title": q.title,
                "description": q.description,
                "action": q.action,
                "tags": q.tags,
            }
        )
    return {key: items}


def main() -> None:
    parser = argparse.ArgumentParser(description="퀘스트 카탈로그 오프라인 생성 스크립트")
    parser.add_argument("--scope", choices=["team", "personal"], required=True)
    parser.add_argument("--count", type=int, default=10)
    parser.add_argument("--out", type=Path, default=None, help="결과를 저장할 yaml 경로 (미지정 시 stdout)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    batch = generate_quests(args.scope, args.count)
    fragment = _to_yaml_fragment(args.scope, batch)

    yaml_text = yaml.dump(fragment, allow_unicode=True, sort_keys=False)

    if args.out:
        args.out.write_text(yaml_text, encoding="utf-8")
        print(f"작성 완료: {args.out} — 검수 후 knowledge_base/quests.yaml에 수동 병합하세요.", file=sys.stderr)
    else:
        print(yaml_text)


if __name__ == "__main__":
    main()

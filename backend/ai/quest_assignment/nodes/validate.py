"""
validate_decision 노드 — 코드 기반 출력 검증기 (SPEC_V5.2 §5.2)

검증 조건:
- quest_id가 전달한 후보(ranked)에 존재한다.
- used_rule_ids가 context.matched_rule_ids의 부분집합이다.
- reason/intro_message에 점수·등급·우열·성공 가능성 표현이 없다.
- 다른 팀원이나 개인 성향(포지션 라벨)을 언급하지 않는다.
- 선택된 퀘스트의 steps/deliverable/completion_condition 원문을 그대로
  옮기거나 바꾸려는 시도가 없다.

이 파일은 ai/nodes/validate.py(팀 코멘트용)의 검증 철학을 그대로 따르되,
그 파일이 현재 진행 중인 다른 작업으로 계속 바뀌고 있어 직접 import하지 않고
같은 패턴을 이 모듈 안에 자기완결적으로 재구현한다.
"""

from __future__ import annotations

import re

from ..schemas import QuestAssignmentDecision, QuestAssignmentState, QuestSelectionOutput, QuestTemplate

GRADE_PATTERNS = [r"\bHIGH\b", r"\bMID\b", r"\bLOW\b"]

NUMERIC_SCORE_PATTERN = re.compile(
    r"(\d+\.?\d*)\s*(점|점수|score|%|퍼센트|확률|등급)", re.IGNORECASE
)

JUDGMENT_PATTERNS = [
    r"최고",
    r"최악",
    r"우수\s*[하한]",
    r"열등\s*[하한]",
    r"부적합",
    r"순위",
    r"랭킹",
    r"등급",
    r"성공\s*(확률|가능성)",
    r"실패\s*(확률|가능성)",
    r"(항상|반드시)\s*(실패|성공)",
]

# 개인 성향(포지션) 라벨 직접 언급 차단 — SPEC §5.2 "다른 팀원 또는 개인 성향 언급 차단"
POSITION_LABELS = [
    "PLANNER",
    "ADAPTER",
    "DRIVER",
    "SUPPORTER",
    "CONFRONTER",
    "HARMONIZER",
    "DIRECT",
    "TACTFUL",
]


def _check_grade_leak(text: str) -> str | None:
    for pattern in GRADE_PATTERNS:
        if re.search(pattern, text):
            return f"GRADE_LEAK: {pattern}"
    return None


def _check_numeric_score(text: str) -> str | None:
    if NUMERIC_SCORE_PATTERN.search(text):
        return "NUMERIC_SCORE_GENERATED"
    return None


def _check_judgment(text: str) -> str | None:
    for pattern in JUDGMENT_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return f"FORBIDDEN_EXPRESSION: {pattern}"
    return None


def _check_position_label_leak(text: str) -> str | None:
    # 단순 부분 문자열 검사를 쓴다: \b 기반 단어 경계는 "DRIVER인 팀원"처럼
    # 라벨 뒤에 한글 조사가 바로 붙으면 유니코드 단어문자 경계를 못 잡아 통과시킨다.
    for label in POSITION_LABELS:
        if label in text:
            return f"POSITION_LABEL_LEAK: {label}"
    return None


def _check_quest_content_leak(text: str, quest: QuestTemplate | None) -> str | None:
    if quest is None:
        return None
    for step in quest.steps:
        if step and step in text:
            return "QUEST_CONTENT_LEAK: steps"
    if quest.deliverable and quest.deliverable in text:
        return "QUEST_CONTENT_LEAK: deliverable"
    description = (quest.completion_condition or {}).get("description")
    if description and description in text:
        return "QUEST_CONTENT_LEAK: completion_condition"
    return None


def _find_quest(quest_id: str, candidates: list[QuestTemplate]) -> QuestTemplate | None:
    for quest in candidates:
        if quest.quest_id == quest_id:
            return quest
    return None


def validate_decision(state: QuestAssignmentState) -> dict:
    """생성된 QuestSelectionOutput을 검증하고, 통과하면 최종 결정을 만든다."""
    draft = state.get("draft")

    if draft is None:
        return {"validation_errors": state.get("validation_errors", ["DRAFT_IS_NONE"])}

    if not isinstance(draft, QuestSelectionOutput):
        return {"validation_errors": [f"UNEXPECTED_TYPE: {type(draft).__name__}"]}

    context = state["context"]
    candidates = state["ranked"]
    candidate_ids = {quest.quest_id for quest in candidates}

    errors: list[str] = []

    if draft.quest_id not in candidate_ids:
        errors.append(f"QUEST_ID_NOT_IN_CANDIDATES: {draft.quest_id}")

    allowed_rule_ids = set(context.matched_rule_ids)
    for i, rid in enumerate(draft.used_rule_ids):
        if rid not in allowed_rule_ids:
            errors.append(f"UNKNOWN_RULE_ID: used_rule_ids[{i}]={rid}")

    all_text = f"{draft.reason} {draft.intro_message}"

    for checker in (
        _check_grade_leak,
        _check_numeric_score,
        _check_judgment,
        _check_position_label_leak,
    ):
        err = checker(all_text)
        if err:
            errors.append(err)

    selected_quest = _find_quest(draft.quest_id, candidates)
    content_leak = _check_quest_content_leak(all_text, selected_quest)
    if content_leak:
        errors.append(content_leak)

    if errors:
        return {"validation_errors": errors}

    # 단일 맞춤 후보라 Bedrock을 생략한 경우는 LLM이 실제로 고른 게 아니므로
    # "AGENT"로 기록하지 않는다. app/services/quests/schemas.py의
    # assignment_source가 Literal["AGENT", "RULE", "FALLBACK"]로 확장되어
    # 있으므로, 결정론적 규칙으로 골랐다는 사실을 "RULE"로 정확히 기록한다.
    if state.get("bedrock_skipped"):
        source = "RULE"
    else:
        source = "AGENT"

    decision = QuestAssignmentDecision(
        quest_id=draft.quest_id,
        reason=draft.reason,
        intro_message=draft.intro_message,
        used_rule_ids=draft.used_rule_ids,
        assignment_source=source,
    )

    return {"validation_errors": [], "final": decision, "used_fallback": False}

"""
validate 노드 - 코드 기반 출력 검증기

LLM 자체 평가를 검증기로 사용하지 않는다.
다음 항목을 일반 코드로 검사한다:
1. Pydantic schema 통과 여부
2. strength/caution/recommendation code 허용 목록 포함 여부
3. used_rule_ids 허용 목록 포함 여부
4. team_grade·숫자 점수·성공확률 생성 여부
5. SELF_ONLY 출력에서 다른 참여자 이름·ID 언급 여부
6. 비하·단정·진단·채용 판단 금칙어 여부
7. caution마다 실행 가능한 action 존재 여부
8. 출력 개수 상한 준수 여부
"""

from __future__ import annotations

import re
from typing import Any

from ..schemas import CommentGraphState, GeneratedInsight, ValidationResult, ValidationError

# 금칙어 패턴 (비하·단정·진단·채용·성과 예측)
FORBIDDEN_PATTERNS = [
    r"문제\s*유형",
    r"열등\s*[하한]",
    r"무능\s*[하한]",
    r"실패\s*[할한]",
    r"채용\s*(불가|부적합|적합)",
    r"진단\s*결과",
    r"성공\s*확률",
    r"\d+\s*%\s*(성공|실패|확률)",
    r"(능력|역량)\s*부족",
    r"(항상|반드시|절대)\s*(실패|성공)",
]

# 숫자 점수 패턴
NUMERIC_SCORE_PATTERN = re.compile(
    r"(\d+\.?\d*)\s*(점|점수|score|%|퍼센트|확률)", re.IGNORECASE
)

MAX_STRENGTHS = 5
MAX_CAUTIONS = 5


def validate_comment(state: CommentGraphState) -> dict:
    """생성된 코멘트를 검증하고 결과를 상태에 반영한다.

    Returns:
        상태 업데이트 dict (validation_errors, final 또는 빈 errors)
    """
    draft = state.get("draft")

    # draft가 None이면 (LLM 오류) 바로 실패 처리
    if draft is None:
        return {
            "validation_errors": state.get("validation_errors", ["DRAFT_IS_NONE"]),
        }

    errors: list[ValidationError] = []

    # 1. Pydantic schema 검증 (이미 structured output으로 파싱되어 있으므로 타입 확인)
    if not isinstance(draft, GeneratedInsight):
        errors.append(ValidationError(code="SCHEMA_INVALID", field="root"))
        return {"validation_errors": [f"{e.code}: {e.field}" for e in errors]}

    # 2. strength code 허용 목록 검증
    allowed_strengths = set(state["allowed_strength_codes"])
    for i, item in enumerate(draft.strengths):
        if item.code not in allowed_strengths:
            errors.append(ValidationError(
                code="UNKNOWN_STRENGTH_CODE",
                field=f"strengths[{i}].code",
            ))

    # 3. caution code 허용 목록 검증
    allowed_cautions = set(state["allowed_caution_codes"])
    for i, item in enumerate(draft.cautions):
        if item.code not in allowed_cautions:
            errors.append(ValidationError(
                code="UNKNOWN_CAUTION_CODE",
                field=f"cautions[{i}].code",
            ))

    # 4. used_rule_ids 허용 목록 검증
    allowed_rules = set(state["allowed_rule_ids"])
    for i, rule_id in enumerate(draft.used_rule_ids):
        if rule_id not in allowed_rules:
            errors.append(ValidationError(
                code="UNKNOWN_RULE_ID",
                field=f"used_rule_ids[{i}]",
            ))

    # 5. 숫자 점수·성공확률 생성 여부
    all_text = draft.summary + " ".join(
        item.text + (item.action or "") for item in draft.strengths + draft.cautions
    )
    if NUMERIC_SCORE_PATTERN.search(all_text):
        errors.append(ValidationError(
            code="NUMERIC_SCORE_GENERATED",
            field="text_content",
        ))

    # 6. SELF_ONLY 출력에서 다른 참여자 언급 여부
    if state["audience"] == "SELF_ONLY":
        ctx = state.get("knowledge_context", {})
        other_names = ctx.get("other_participant_names", [])
        other_ids = ctx.get("other_participant_ids", [])

        for name in other_names:
            if name and name in all_text:
                errors.append(ValidationError(
                    code="OTHER_MEMBER_REFERENCE",
                    field="text_content",
                ))
                break

        for pid in other_ids:
            if pid and pid in all_text:
                errors.append(ValidationError(
                    code="OTHER_MEMBER_ID_REFERENCE",
                    field="text_content",
                ))
                break

    # 7. 금칙어 검사
    for pattern in FORBIDDEN_PATTERNS:
        if re.search(pattern, all_text, re.IGNORECASE):
            errors.append(ValidationError(
                code="FORBIDDEN_EXPRESSION",
                field="text_content",
            ))
            break

    # 8. caution마다 action 존재 여부
    for i, item in enumerate(draft.cautions):
        if not item.action or not item.action.strip():
            errors.append(ValidationError(
                code="MISSING_ACTION",
                field=f"cautions[{i}].action",
            ))

    # 9. 출력 개수 상한
    if len(draft.strengths) > MAX_STRENGTHS:
        errors.append(ValidationError(
            code="EXCEEDED_MAX_STRENGTHS",
            field=f"strengths (count={len(draft.strengths)})",
        ))
    if len(draft.cautions) > MAX_CAUTIONS:
        errors.append(ValidationError(
            code="EXCEEDED_MAX_CAUTIONS",
            field=f"cautions (count={len(draft.cautions)})",
        ))

    # 결과 반환
    if errors:
        return {
            "validation_errors": [f"{e.code}: {e.field}" for e in errors],
        }
    else:
        return {
            "validation_errors": [],
            "final": draft,
        }

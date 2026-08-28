"""
validate 노드 — 코드 기반 출력 검증기 (V2)

TeamSnapshot 검증:
- title/formula/scene/keywords 필수 + 길이 제한
- keywords 2~4개, 항목당 최대 15자
- used_rule_ids가 allowed_rule_ids의 부분집합
- 숫자 점수·퍼센트·HIGH/MID/LOW 차단
- 성공률·실패율·성과 예측 차단
- 최고·최악·우수·열등·부적합 표현 차단
- 특정 참여자 이름/ID 차단
- 팀 퀘스트·명령형 행동 요구 차단

PrivateCard 검증:
- card_title/contribution 필수 + 길이 제한
- used_rule_ids 허용 목록 확인
- 다른 참여자 이름/ID 차단
- 점수·등급·성과 예측 차단
- 진단·채용·능력 판단 차단
- "반드시"/"해야 한다"/"고쳐야 한다" 강제 표현 차단
"""

from __future__ import annotations

import re

from ..schemas import CommentGraphState, PrivateCard, TeamSnapshot

# ── 금칙어 패턴 (공통) ──
GRADE_PATTERNS = [
    r"\bHIGH\b",
    r"\bMID\b",
    r"\bLOW\b",
]

NUMERIC_SCORE_PATTERN = re.compile(
    r"(\d+\.?\d*)\s*(점|점수|score|%|퍼센트|확률)", re.IGNORECASE
)

JUDGMENT_PATTERNS = [
    r"최고",
    r"최악",
    r"우수\s*[하한]",
    r"열등\s*[하한]",
    r"부적합",
    r"문제\s*유형",
    r"무능\s*[하한]",
    r"실패\s*[할한]",
    r"채용\s*(불가|부적합|적합)",
    r"진단\s*결과",
    r"성공\s*확률",
    r"\d+\s*%\s*(성공|실패|확률)",
    r"(능력|역량)\s*부족",
    r"(항상|반드시)\s*(실패|성공)",
    r"성과\s*예측",
    r"위험\s*(도|지수|수준)",
]

# 팀 전용: 퀘스트·명령형 차단
QUEST_PATTERNS = [
    r"퀘스트",
    r"미션",
    r"도전\s*과제",
    r"실천\s*해\s*(주세요|보세요|야)",
    r"반드시\s*(해야|하세요|합니다)",
]

# 개인 전용: 강제 표현 차단
FORCE_PATTERNS = [
    r"반드시",
    r"해야\s*(합니다|한다|해요)",
    r"고쳐야\s*(합니다|한다|해요)",
    r"개선해야",
    r"문제점",
    r"주의점",
    r"단점",
    r"위험",
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


def _check_participant_reference(text: str, state: CommentGraphState) -> str | None:
    ctx = state.get("knowledge_context", {})
    for name in ctx.get("other_participant_names", []):
        if name and name in text:
            return f"OTHER_MEMBER_REFERENCE: {name}"
    for pid in ctx.get("other_participant_ids", []):
        if pid and pid in text:
            return f"OTHER_MEMBER_ID_REFERENCE: {pid}"
    return None


def _validate_team_snapshot(draft: TeamSnapshot, state: CommentGraphState) -> list[str]:
    errors: list[str] = []

    # 필드 존재 + 길이
    if not draft.title or not draft.title.strip():
        errors.append("MISSING_FIELD: title")
    elif len(draft.title) > 40:
        errors.append("LENGTH_EXCEEDED: title (max 40)")

    if not draft.formula or not draft.formula.strip():
        errors.append("MISSING_FIELD: formula")
    elif len(draft.formula) > 80:
        errors.append("LENGTH_EXCEEDED: formula (max 80)")

    if not draft.scene or not draft.scene.strip():
        errors.append("MISSING_FIELD: scene")
    elif len(draft.scene) > 120:
        errors.append("LENGTH_EXCEEDED: scene (max 120)")

    # keywords 2~4개, 항목당 15자
    if len(draft.keywords) < 2:
        errors.append("TOO_FEW_KEYWORDS: min 2")
    elif len(draft.keywords) > 4:
        errors.append("TOO_MANY_KEYWORDS: max 4")
    for i, kw in enumerate(draft.keywords):
        if len(kw) > 15:
            errors.append(f"KEYWORD_TOO_LONG: keywords[{i}] (max 15)")

    # used_rule_ids 부분집합 확인
    allowed = set(state["allowed_rule_ids"])
    for i, rid in enumerate(draft.used_rule_ids):
        if rid not in allowed:
            errors.append(f"UNKNOWN_RULE_ID: used_rule_ids[{i}]={rid}")

    # 전체 텍스트 검사
    all_text = f"{draft.title} {draft.formula} {draft.scene} {' '.join(draft.keywords)}"

    grade_err = _check_grade_leak(all_text)
    if grade_err:
        errors.append(grade_err)

    score_err = _check_numeric_score(all_text)
    if score_err:
        errors.append(score_err)

    judgment_err = _check_judgment(all_text)
    if judgment_err:
        errors.append(judgment_err)

    ref_err = _check_participant_reference(all_text, state)
    if ref_err:
        errors.append(ref_err)

    # 퀘스트·명령형 차단
    for pattern in QUEST_PATTERNS:
        if re.search(pattern, all_text, re.IGNORECASE):
            errors.append(f"QUEST_OR_COMMAND: {pattern}")
            break

    return errors


def _validate_private_card(draft: PrivateCard, state: CommentGraphState) -> list[str]:
    errors: list[str] = []

    # 필드 존재 + 길이
    if not draft.card_title or not draft.card_title.strip():
        errors.append("MISSING_FIELD: card_title")
    elif len(draft.card_title) > 40:
        errors.append("LENGTH_EXCEEDED: card_title (max 40)")

    if not draft.contribution or not draft.contribution.strip():
        errors.append("MISSING_FIELD: contribution")
    elif len(draft.contribution) > 160:
        errors.append("LENGTH_EXCEEDED: contribution (max 160)")

    if draft.optional_try and len(draft.optional_try) > 160:
        errors.append("LENGTH_EXCEEDED: optional_try (max 160)")

    # used_rule_ids 부분집합 확인
    allowed = set(state["allowed_rule_ids"])
    for i, rid in enumerate(draft.used_rule_ids):
        if rid not in allowed:
            errors.append(f"UNKNOWN_RULE_ID: used_rule_ids[{i}]={rid}")

    # 전체 텍스트 검사
    all_text = f"{draft.card_title} {draft.contribution} {draft.optional_try or ''}"

    grade_err = _check_grade_leak(all_text)
    if grade_err:
        errors.append(grade_err)

    score_err = _check_numeric_score(all_text)
    if score_err:
        errors.append(score_err)

    judgment_err = _check_judgment(all_text)
    if judgment_err:
        errors.append(judgment_err)

    ref_err = _check_participant_reference(all_text, state)
    if ref_err:
        errors.append(ref_err)

    # 강제 표현 차단
    for pattern in FORCE_PATTERNS:
        if re.search(pattern, all_text, re.IGNORECASE):
            errors.append(f"FORCE_EXPRESSION: {pattern}")
            break

    return errors


def validate_comment(state: CommentGraphState) -> dict:
    """생성된 출력을 검증한다."""
    draft = state.get("draft")

    if draft is None:
        return {
            "validation_errors": state.get("validation_errors", ["DRAFT_IS_NONE"]),
        }

    if isinstance(draft, TeamSnapshot):
        errors = _validate_team_snapshot(draft, state)
    elif isinstance(draft, PrivateCard):
        errors = _validate_private_card(draft, state)
    else:
        errors = [f"UNEXPECTED_TYPE: {type(draft).__name__}"]

    if errors:
        return {"validation_errors": errors}
    else:
        return {"validation_errors": [], "final": draft}

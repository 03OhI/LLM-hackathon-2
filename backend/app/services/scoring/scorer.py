"""
채점 서비스

24문항 5점 리커트 설문 채점과 CanonicalProfile 생성을 담당한다.

채점 규칙:
- 각 축 6문항 (정방향 3 + 역방향 3)
- 역문항 점수 = 6 - 응답
- 축 평균 = 해당 축 6문항 평균
- 축 비율 = (평균 - 1) / 4
- 비율 > 0.60 → 상위 극
- 비율 < 0.40 → 하위 극
- 0.40~0.60 → 중립

LLM, LangChain, LangGraph를 사용하지 않는다.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass

from ai.schemas import (
    AXIS_KEYS,
    NEUTRAL,
    POSITION_ENUM,
    CanonicalProfile,
)

# ──────────────────────────────────────────────
# 문항 매핑 (survey24-v2)
# ──────────────────────────────────────────────

# 각 축의 문항 인덱스 (0-based) 와 방향
# forward: 정방향, reverse: 역방향

QUESTION_MAP: dict[str, dict[str, list[int]]] = {
    "planning": {
        "forward": [0, 1, 2],     # Q1~Q3
        "reverse": [3, 4, 5],     # Q4~Q6
    },
    "agency": {
        "forward": [6, 7, 8],     # Q7~Q9
        "reverse": [9, 10, 11],   # Q10~Q12
    },
    "conflict": {
        "forward": [12, 13, 14],  # Q13~Q15
        "reverse": [15, 16, 17],  # Q16~Q18
    },
    "communication": {
        "forward": [18, 19, 20],  # Q19~Q21
        "reverse": [21, 22, 23],  # Q22~Q24
    },
}

QUESTION_SET_VERSION = "survey24-v2"
TOTAL_QUESTIONS = 24
MIN_SCORE = 1
MAX_SCORE = 5

# 유형 판정 임계치
UPPER_THRESHOLD = 0.60
LOWER_THRESHOLD = 0.40

# 비일관 응답 플래그 기준
INCONSISTENCY_THRESHOLD = 1.2


# ──────────────────────────────────────────────
# 채점 결과 데이터 클래스
# ──────────────────────────────────────────────


@dataclass
class AxisScore:
    """단일 축의 채점 결과"""
    axis: str
    mean: float
    ratio: float
    position: str
    raw_scores: list[float]
    is_inconsistent: bool


# ──────────────────────────────────────────────
# 채점 로직
# ──────────────────────────────────────────────


def validate_answers(answers: list[int]) -> list[str]:
    """응답 유효성을 검사한다.

    Args:
        answers: 24개의 1~5 정수 응답

    Returns:
        오류 메시지 리스트 (비어있으면 유효)
    """
    errors: list[str] = []

    if len(answers) != TOTAL_QUESTIONS:
        errors.append(f"응답 수가 {TOTAL_QUESTIONS}개여야 합니다. 현재: {len(answers)}개")
        return errors

    for i, answer in enumerate(answers):
        if not isinstance(answer, int) or answer < MIN_SCORE or answer > MAX_SCORE:
            errors.append(f"Q{i+1}: 응답은 {MIN_SCORE}~{MAX_SCORE} 사이 정수여야 합니다. 현재: {answer}")

    return errors


def _reverse_score(value: int) -> float:
    """역문항 점수 계산: 6 - 응답"""
    return 6.0 - value


def score_axis(axis: str, answers: list[int]) -> AxisScore:
    """단일 축의 점수를 계산한다.

    Args:
        axis: 축 키 (planning, agency, conflict, communication)
        answers: 전체 24개 응답

    Returns:
        AxisScore: 해당 축의 채점 결과
    """
    mapping = QUESTION_MAP[axis]
    forward_indices = mapping["forward"]
    reverse_indices = mapping["reverse"]

    # 정방향 점수
    forward_scores = [float(answers[i]) for i in forward_indices]
    # 역방향 점수 (6 - 응답)
    reverse_scores = [_reverse_score(answers[i]) for i in reverse_indices]

    all_scores = forward_scores + reverse_scores

    # 축 평균
    mean = statistics.mean(all_scores)

    # 축 비율 = (평균 - 1) / 4
    ratio = (mean - 1) / 4

    # 유형 판정
    upper, lower = POSITION_ENUM[axis]
    if ratio > UPPER_THRESHOLD:
        position = upper
    elif ratio < LOWER_THRESHOLD:
        position = lower
    else:
        position = NEUTRAL

    # 비일관 응답 검사 (표준편차 >= 1.2)
    stdev = statistics.stdev(all_scores) if len(all_scores) > 1 else 0.0
    is_inconsistent = stdev >= INCONSISTENCY_THRESHOLD

    return AxisScore(
        axis=axis,
        mean=round(mean, 2),
        ratio=round(ratio, 4),
        position=position,
        raw_scores=all_scores,
        is_inconsistent=is_inconsistent,
    )


def score_survey(answers: list[int]) -> list[AxisScore]:
    """24문항 전체를 채점한다.

    Args:
        answers: 24개의 1~5 정수 응답

    Returns:
        4개 축의 AxisScore 리스트
    """
    return [score_axis(axis, answers) for axis in AXIS_KEYS]


# ──────────────────────────────────────────────
# CanonicalProfile 생성
# ──────────────────────────────────────────────


def create_profile_from_survey(
    participant_id: str,
    answers: list[int],
) -> CanonicalProfile:
    """설문 응답으로부터 CanonicalProfile을 생성한다.

    Args:
        participant_id: 참여자 ID
        answers: 24개의 1~5 정수 응답

    Returns:
        CanonicalProfile

    Raises:
        ValueError: 응답 유효성 검사 실패 시
    """
    errors = validate_answers(answers)
    if errors:
        raise ValueError(f"설문 응답 유효성 검사 실패: {'; '.join(errors)}")

    axis_scores = score_survey(answers)

    positions = {s.axis: s.position for s in axis_scores}
    ratios = {s.axis: s.ratio for s in axis_scores}
    means = {s.axis: s.mean for s in axis_scores}

    # 비일관 플래그 수집
    axis_flags = [
        f"INCONSISTENT_AXIS_RESPONSE:{s.axis}"
        for s in axis_scores
        if s.is_inconsistent
    ]

    return CanonicalProfile(
        participant_id=participant_id,
        source="SURVEY",
        question_set_version=QUESTION_SET_VERSION,
        positions=positions,
        ratios=ratios,
        means=means,
        axis_flags=axis_flags,
    )


def create_profile_from_declared_type(
    participant_id: str,
    positions: dict[str, str],
) -> CanonicalProfile:
    """직접 입력으로부터 CanonicalProfile을 생성한다.

    직접 입력에는 문항 평균·표준편차가 없으므로 임의로 생성하지 않는다.
    가짜 비율(예: 0.75)을 부여하지 않는다.

    Args:
        participant_id: 참여자 ID
        positions: 4축 포지션 딕셔너리

    Returns:
        CanonicalProfile

    Raises:
        ValueError: 포지션 유효성 검사 실패 시
    """
    errors: list[str] = []

    for axis in AXIS_KEYS:
        if axis not in positions:
            errors.append(f"축 '{axis}'가 누락되었습니다.")
            continue

        pos = positions[axis]
        upper, lower = POSITION_ENUM[axis]
        valid_values = {upper, lower, NEUTRAL}
        if pos not in valid_values:
            errors.append(
                f"축 '{axis}'의 값 '{pos}'이 유효하지 않습니다. "
                f"허용값: {valid_values}"
            )

    if errors:
        raise ValueError(f"유형 입력 유효성 검사 실패: {'; '.join(errors)}")

    return CanonicalProfile(
        participant_id=participant_id,
        source="DECLARED_TYPE",
        question_set_version=None,
        positions=positions,
        ratios=None,
        means=None,
        axis_flags=[],
    )

"""
AI 구조화 출력 스키마 정의

LangChain structured output과 LangGraph 상태에서 사용하는 모든 Pydantic 모델을 정의한다.
- InsightItem: 개별 강점/주의점 항목
- GeneratedInsight: LLM이 반환하는 구조화된 코멘트
- CommentGraphState: LangGraph 그래프 상태
- ValidationResult: 검증기 출력
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field
from typing_extensions import TypedDict


# ──────────────────────────────────────────────
# LLM 구조화 출력 스키마
# ──────────────────────────────────────────────


class InsightItem(BaseModel):
    """개별 인사이트 항목 (강점 또는 주의점)"""

    code: str = Field(description="규칙 지식베이스의 strength/caution 코드")
    text: str = Field(description="사용자에게 보여줄 자연어 설명")
    action: str | None = Field(
        default=None,
        description="주의점에 대응하는 구체적 실천 행동 (caution일 때 필수)",
    )


class GeneratedInsight(BaseModel):
    """LLM이 생성하는 구조화된 코멘트 출력"""

    summary: str = Field(description="전체 요약 한 줄")
    strengths: list[InsightItem] = Field(description="강점 항목 리스트")
    cautions: list[InsightItem] = Field(description="주의점 항목 리스트")
    used_rule_ids: list[str] = Field(description="코멘트 작성에 사용된 rule_id 목록")


# ──────────────────────────────────────────────
# LangGraph 상태 스키마
# ──────────────────────────────────────────────


class CommentGraphState(TypedDict):
    """LangGraph 코멘트 생성 그래프의 상태"""

    # 대상 구분
    audience: Literal["TEAM", "SELF_ONLY"]
    analysis_result_id: str
    participant_id: str | None

    # 규칙 엔진이 허용한 코드 목록
    allowed_strength_codes: list[str]
    allowed_caution_codes: list[str]
    allowed_recommendation_codes: list[str]
    allowed_rule_ids: list[str]

    # 규칙 지식베이스에서 가져온 컨텍스트
    knowledge_context: dict

    # 생성 결과
    draft: GeneratedInsight | None
    validation_errors: list[str]
    retry_count: int
    final: GeneratedInsight | None
    used_fallback: bool


# ──────────────────────────────────────────────
# 검증기 출력
# ──────────────────────────────────────────────


class ValidationError(BaseModel):
    """검증 실패 항목"""

    code: str = Field(description="오류 코드 (예: UNKNOWN_CAUTION_CODE)")
    field: str = Field(description="문제가 된 필드 경로 (예: cautions[1].code)")


class ValidationResult(BaseModel):
    """출력 검증 결과"""

    passed: bool
    errors: list[ValidationError] = Field(default_factory=list)


# ──────────────────────────────────────────────
# 팀 코멘트 입력 DTO
# ──────────────────────────────────────────────


class TeamCommentInput(BaseModel):
    """팀 코멘트 생성을 위한 입력 데이터"""

    audience: Literal["TEAM"] = "TEAM"
    team_grade: Literal["HIGH", "MID", "LOW"]
    strength_codes: list[str]
    caution_codes: list[str]
    allowed_recommendations: list[str]
    evidence_levels: dict[str, Literal["direct", "indirect", "limited", "team_judgment"]]
    team_size: int = Field(ge=3, le=10)
    distribution: dict[str, dict[str, int]] | None = None


class PrivateCommentInput(BaseModel):
    """개인 인사이트 생성을 위한 입력 데이터"""

    audience: Literal["SELF_ONLY"] = "SELF_ONLY"
    self_participant_id: str
    self_positions: dict[str, str]
    team_aggregate: dict[str, dict[str, int]]
    strength_codes: list[str]
    caution_codes: list[str]
    allowed_recommendations: list[str]


# ──────────────────────────────────────────────
# CanonicalProfile 관련
# ──────────────────────────────────────────────

AXIS_KEYS = ("planning", "agency", "conflict", "communication")

POSITION_ENUM = {
    "planning": ("PLANNER", "ADAPTER"),
    "agency": ("DRIVER", "SUPPORTER"),
    "conflict": ("CONFRONTER", "HARMONIZER"),
    "communication": ("DIRECT", "TACTFUL"),
}

NEUTRAL = "NEUTRAL"


class CanonicalProfile(BaseModel):
    """두 입력 방식(설문/직접 입력)을 정규화한 프로필"""

    participant_id: str
    source: Literal["SURVEY", "DECLARED_TYPE"]
    question_set_version: str | None = None
    positions: dict[str, str] = Field(
        description="각 축의 판정 결과 (상위극/하위극/NEUTRAL)"
    )
    ratios: dict[str, float] | None = Field(
        default=None,
        description="축별 비율 (0~1). 설문 기반에서만 존재",
    )
    means: dict[str, float] | None = Field(
        default=None,
        description="축별 문항 평균. 설문 기반에서만 존재",
    )
    axis_flags: list[str] = Field(default_factory=list)

"""
AI 구조화 출력 스키마 정의

LangChain structured output과 LangGraph 상태에서 사용하는 모든 Pydantic 모델을 정의한다.
- InsightItem: 개별 강점/주의점 항목
- GeneratedInsight: LLM이 반환하는 구조화된 코멘트
- CommentGraphState: LangGraph 그래프 상태
- ValidationResult: 검증기 출력
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field
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


class GenerationResult(BaseModel):
    """백엔드가 저장하는 AI 생성 최종 결과"""

    model_config = ConfigDict(extra="forbid")

    status: Literal["COMPLETED", "FALLBACK"]
    insight: GeneratedInsight
    used_fallback: bool
    model_id: str
    prompt_version: str
    validation_errors: list[str] = Field(default_factory=list)


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


EvidenceLevel = Literal["direct", "indirect", "limited", "team_judgment"]
NonNegativeCount = Annotated[int, Field(ge=0)]


class AxisPositions(BaseModel):
    """자체 4축의 정확한 위치 값

    딕셔너리 호환 인터페이스를 제공하여 규칙 엔진에서
    positions.get(axis), positions[axis], positions.values() 등을
    AxisPositions 객체에 대해 그대로 사용할 수 있다.
    """

    model_config = ConfigDict(extra="forbid")

    planning: Literal["PLANNER", "ADAPTER", "NEUTRAL"]
    agency: Literal["DRIVER", "SUPPORTER", "NEUTRAL"]
    conflict: Literal["CONFRONTER", "HARMONIZER", "NEUTRAL"]
    communication: Literal["DIRECT", "TACTFUL", "NEUTRAL"]

    # ── 딕셔너리 호환 메서드 ──

    def get(self, key: str, default: str | None = None) -> str | None:
        """dict.get() 호환"""
        return getattr(self, key, default)

    def __getitem__(self, key: str) -> str:
        """dict[key] 호환"""
        try:
            return getattr(self, key)
        except AttributeError:
            raise KeyError(key)

    def __contains__(self, key: str) -> bool:
        """'key' in positions 호환"""
        return key in ("planning", "agency", "conflict", "communication")

    def keys(self):
        """dict.keys() 호환"""
        return ("planning", "agency", "conflict", "communication")

    def values(self):
        """dict.values() 호환"""
        return (self.planning, self.agency, self.conflict, self.communication)

    def items(self):
        """dict.items() 호환"""
        return (
            ("planning", self.planning),
            ("agency", self.agency),
            ("conflict", self.conflict),
            ("communication", self.communication),
        )

    def to_dict(self) -> dict[str, str]:
        """명시적 딕셔너리 변환"""
        return {
            "planning": self.planning,
            "agency": self.agency,
            "conflict": self.conflict,
            "communication": self.communication,
        }


class TeamDistribution(BaseModel):
    """축별 팀 인원 분포"""

    model_config = ConfigDict(extra="forbid")

    planning: dict[Literal["PLANNER", "ADAPTER", "NEUTRAL"], NonNegativeCount]
    agency: dict[Literal["DRIVER", "SUPPORTER", "NEUTRAL"], NonNegativeCount]
    conflict: dict[Literal["CONFRONTER", "HARMONIZER", "NEUTRAL"], NonNegativeCount]
    communication: dict[Literal["DIRECT", "TACTFUL", "NEUTRAL"], NonNegativeCount]


class TeamCommentInput(BaseModel):
    """팀 코멘트 생성을 위한 입력 데이터"""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    analysis_result_id: str
    audience: Literal["TEAM"] = "TEAM"
    team_grade: Literal["HIGH", "MID", "LOW"]
    strength_codes: list[str]
    caution_codes: list[str]
    recommendation_codes: list[str] = Field(
        validation_alias=AliasChoices("recommendation_codes", "allowed_recommendations")
    )
    matched_rule_ids: list[str]
    evidence_levels: dict[str, EvidenceLevel]
    team_size: int = Field(ge=3, le=10)
    distribution: TeamDistribution | None = None

    @property
    def allowed_recommendations(self) -> list[str]:
        """기존 AI 구현과의 임시 호환 프로퍼티."""

        return self.recommendation_codes


class PrivateInsightInput(BaseModel):
    """개인 인사이트 생성을 위한 입력 데이터"""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    analysis_result_id: str
    audience: Literal["SELF_ONLY"] = "SELF_ONLY"
    participant_id: str = Field(
        validation_alias=AliasChoices("participant_id", "self_participant_id")
    )
    self_positions: AxisPositions
    team_aggregate: TeamDistribution
    strength_codes: list[str]
    caution_codes: list[str]
    recommendation_codes: list[str] = Field(
        validation_alias=AliasChoices("recommendation_codes", "allowed_recommendations")
    )
    matched_rule_ids: list[str]

    @property
    def self_participant_id(self) -> str:
        """기존 AI 구현과의 임시 호환 프로퍼티."""

        return self.participant_id

    @property
    def allowed_recommendations(self) -> list[str]:
        """기존 AI 구현과의 임시 호환 프로퍼티."""

        return self.recommendation_codes


# 기존 AI 모듈 import와의 임시 호환 별칭. 신규 백엔드는 PrivateInsightInput을 사용한다.
PrivateCommentInput = PrivateInsightInput


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
    positions: AxisPositions = Field(
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

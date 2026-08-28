"""
퀘스트 배정 AI 모듈 — DTO 재노출 + AI 내부 전용 타입 (SPEC_V5.2 §3~§5)

QuestMatchContext / QuestTemplate / QuestAssignmentDecision은
`app/services/quests/schemas.py`가 "백엔드↔AI 통합 계약의 단일 정본"이라고
명시하고 있으므로 이 모듈에서 재정의하지 않고 그대로 가져와 재노출한다.
이 파일은 pydantic만 의존하는 순수 모듈이며(DB session/ORM 없음),
아래 계약 파일 역시 pydantic 전용이라 import해도 순수성이 깨지지 않는다.

이 파일에서 새로 정의하는 것은 AI 모듈 내부에서만 쓰이는 타입뿐이다:
- QuestSelectionOutput: Bedrock 구조화 출력 스키마
- CatalogIssue / CatalogValidationResult: 카탈로그 검증 결과
- QuestAssignmentState: LangGraph 상태
"""

from __future__ import annotations

from typing_extensions import TypedDict
from pydantic import BaseModel, ConfigDict, Field

from app.services.quests.schemas import (  # noqa: F401 — 재노출
    ALLOWED_CONTEXT_TAGS,
    COMPLETION_CHECK_TYPES,
    COMPLETION_SCOPES,
    DEFAULT_CONTEXT_TAGS,
    QuestAssignmentDecision,
    QuestMatchContext,
    QuestTemplate,
)

# ──────────────────────────────────────────────
# Bedrock 구조화 출력 스키마 — 후보 선택 + 소개 문구만
# ──────────────────────────────────────────────


class QuestSelectionOutput(BaseModel):
    """LLM이 채우는 필드. 퀘스트 본문(steps/deliverable/completion_condition)은
    이 스키마에 존재하지 않으므로 구조적으로 생성·수정할 수 없다."""

    model_config = ConfigDict(extra="forbid")

    quest_id: str
    reason: str = Field(max_length=120)
    intro_message: str = Field(max_length=120)
    used_rule_ids: list[str] = Field(default_factory=list)


# ──────────────────────────────────────────────
# 카탈로그 검증 결과
# ──────────────────────────────────────────────


class CatalogIssue(BaseModel):
    """카탈로그 검증 실패 항목 (개별 퀘스트 또는 카탈로그 전체 단위)."""

    model_config = ConfigDict(extra="forbid")

    quest_id: str | None = None
    code: str
    message: str


class CatalogValidationResult(BaseModel):
    """validate_catalog()의 반환값. valid_templates만 이후 단계에 전달된다."""

    model_config = ConfigDict(extra="forbid")

    valid_templates: list[QuestTemplate]
    errors: list[CatalogIssue] = Field(default_factory=list)
    warnings: list[CatalogIssue] = Field(default_factory=list)


# ──────────────────────────────────────────────
# LangGraph 상태
# ──────────────────────────────────────────────


class QuestAssignmentState(TypedDict):
    context: QuestMatchContext
    raw_catalog: list[QuestTemplate]

    valid_catalog: list[QuestTemplate]
    catalog_errors: list[str]

    candidates: list[QuestTemplate]  # 안전·인원 필터 통과 (filter.filter_candidates)
    matched_candidates: list[QuestTemplate]  # + rule_id 매칭 (filter.matched_candidates)
    ranked: list[QuestTemplate]  # matched_candidates 중 상위 3개

    draft: QuestSelectionOutput | None
    bedrock_skipped: bool
    validation_errors: list[str]
    retry_count: int

    final: QuestAssignmentDecision | None
    used_fallback: bool

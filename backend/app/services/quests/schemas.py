"""
퀘스트 배정 공통 계약 — SPEC_V5_CONTEST_QUEST_AGENT.md §3, §4.1, §5.2

이 파일이 백엔드↔AI 통합 계약의 단일 정본이다. AI 모듈(backend/ai/quest_assignment/)이
`assign_quest(context: QuestMatchContext, catalog: list[QuestTemplate]) -> QuestAssignmentDecision`을
구현할 때 이 파일의 클래스를 그대로 import해서 재노출한다(자체 재정의 금지) —
실제로 ai/quest_assignment/schemas.py가 이 파일에서 재노출하는 방식으로 맞춰져 있다.

team_size/completion_condition은 의도적으로 plain dict로 둔다 — quest.schema.json(JSON
Schema)과 1:1로 대응시키기 쉽고, ai/quest_assignment/filter.py가 이미 dict 스타일
(`quest.team_size.get("min")`)로 접근하기 때문이다.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# SPEC_V5 §3 — P0 허용 상황 태그 전체 집합
ALLOWED_CONTEXT_TAGS = frozenset(
    {
        "FIRST_MEETING",
        "REMOTE_TEAM",
        "IN_PERSON",
        "HACKATHON",
        "LONG_TERM_PROJECT",
        "BEFORE_ROLE_ASSIGNMENT",
        "WORKSPACE_NOT_READY",
    }
)

# P0 기본값 (SPEC_V5 §3 마지막 문단)
DEFAULT_CONTEXT_TAGS: list[str] = ["FIRST_MEETING", "HACKATHON"]

# SPEC_V5 §4.3, §6 — P0 scope/type
COMPLETION_SCOPES = frozenset({"PER_MEMBER", "TEAM"})
COMPLETION_CHECK_TYPES = frozenset(
    {"VOTE", "COMMENT", "TEXT_SUBMIT", "REACTION", "APPROVE", "NODE_CREATE", "LINK_VISIT", "QUESTION"}
)


class QuestMatchContext(BaseModel):
    """SPEC_V5 §3 — 퀘스트 배정 입력. AI 함수와 폴백 로직이 공유하는 유일한 입력 형태."""

    room_id: str
    team_size: int
    matched_rule_ids: list[str] = Field(default_factory=list)  # team_rules.yaml ID만, pair rule 제외
    distribution: dict[str, dict[str, int]] = Field(default_factory=dict)
    context_tags: list[str] = Field(default_factory=lambda: list(DEFAULT_CONTEXT_TAGS))
    completed_quest_ids: list[str] = Field(default_factory=list)


class QuestTemplate(BaseModel):
    """SPEC_V5 §4.1 — quest.schema.json/quests.json 정본과 1:1 대응하는 파싱 결과."""

    quest_id: str
    title: str
    summary: str
    category: str
    primary_goal: str
    duration_minutes: int
    team_size: dict  # {"min": 3, "max": 10}
    interaction_mode: str
    energy_level: Literal["LOW", "MEDIUM", "HIGH"]
    disclosure_level: Literal["LOW", "MEDIUM", "HIGH"]
    assignment: Literal["AUTO", "MANUAL"]
    reveals_axes: list[dict] = Field(default_factory=list)
    is_universal: bool
    best_for: list[str] = Field(default_factory=list)
    also_for: list[str] = Field(default_factory=list)
    avoid_for: list[str] = Field(default_factory=list)
    context_tags: list[str] = Field(default_factory=list)
    materials: list[str] = Field(default_factory=list)
    steps: list[str] = Field(default_factory=list)
    deliverable: str
    completion_condition: dict  # {"description": str, "checks": [{"type","scope","min_count"}]}
    safety_notes: list[str] = Field(default_factory=list)
    is_active: bool = True
    version: str


class QuestAssignmentDecision(BaseModel):
    """SPEC_V5 §5.2 — assign_quest()의 출력. 퀘스트 본문/단계/완료조건을 포함하지 않는다.

    assignment_source 세 값의 의미:
    - AGENT: Bedrock이 실제로 후보 중 하나를 선택했다.
    - RULE: 맞춤 후보(rule_id 매칭)가 정확히 1개라 Bedrock 호출을 생략하고
      결정론적 규칙으로 그 후보를 그대로 선택했다.
    - FALLBACK: Bedrock 호출 실패/timeout/검증 재실패, 또는 맞춤 후보가 아예
      없어 is_universal 범용 퀘스트로 대체했다.

    DB(app/models.py QuestAssignment.assignment_source)는 plain string 컬럼이라
    이 값 추가에 마이그레이션이 필요 없다.
    """

    quest_id: str
    reason: str
    intro_message: str
    used_rule_ids: list[str] = Field(default_factory=list)
    assignment_source: Literal["AGENT", "RULE", "FALLBACK"]

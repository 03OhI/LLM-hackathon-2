"""
DB 모델 정의 (SQLModel)

design.md §4 스키마 그대로. 5개 테이블만 MVP에서 사용한다:
Session, Participant, ParticipantProfile, AnalysisResult, PrivateInsight

- JSON 컬럼은 텍스트로 직렬화해 저장한다 (SQLite 호환).
- internal_index는 여기에는 저장하되, API 응답 직렬화 시에는
  allow-list 방식의 별도 Pydantic 응답 모델(app/api/results.py)만 사용해 절대 노출하지 않는다.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlmodel import Field, SQLModel, UniqueConstraint


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ──────────────────────────────────────────────
# Session
# ──────────────────────────────────────────────


class Session(SQLModel, table=True):
    """세션 — 주최자가 만든 팀 케미 분석 모임."""

    id: str = Field(primary_key=True)
    name: str
    meeting_type: str = Field(default="team_project")
    expected_member_count: int  # 3..10 (애플리케이션 계층에서 검증)
    status: str = Field(default="OPEN")  # OPEN|LOCKED|ANALYZING|COMPLETED|CLOSED
    invite_token_hash: str
    share_token_hash: str
    host_secret_hash: str
    retention_expires_at: datetime
    created_at: datetime = Field(default_factory=utcnow)


# ──────────────────────────────────────────────
# Participant
# ──────────────────────────────────────────────


class Participant(SQLModel, table=True):
    """참여자 — 세션에 초대되어 닉네임으로 등록한 사람."""

    id: str = Field(primary_key=True)
    session_id: str = Field(foreign_key="session.id", index=True)
    nickname: str
    participant_secret_hash: str
    submission_status: str = Field(default="PENDING")  # PENDING|SUBMITTED|LOCKED
    input_method: str | None = Field(default=None)  # SURVEY|DECLARED_TYPE
    created_at: datetime = Field(default_factory=utcnow)
    submitted_at: datetime | None = Field(default=None)


# ──────────────────────────────────────────────
# ParticipantProfile
# ──────────────────────────────────────────────


class ParticipantProfile(SQLModel, table=True):
    """참여자의 정규화된 성향 프로필 (CanonicalProfile의 DB 표현).

    설문 응답과 정규화 프로필을 한 테이블에 저장한다.
    DECLARED_TYPE이면 answers_json/ratios_json/means_json은 None이다.
    """

    participant_id: str = Field(foreign_key="participant.id", primary_key=True)
    source: str  # SURVEY|DECLARED_TYPE
    question_set_version: str | None = Field(default=None)
    answers_json: str | None = Field(default=None)
    positions_json: str  # 항상 존재 — AxisPositions dict 직렬화
    ratios_json: str | None = Field(default=None)
    means_json: str | None = Field(default=None)
    axis_flags_json: str = Field(default="[]")
    analysis_version: int = Field(default=0)
    created_at: datetime = Field(default_factory=utcnow)


# ──────────────────────────────────────────────
# AnalysisResult
# ──────────────────────────────────────────────


class AnalysisResult(SQLModel, table=True):
    """팀 단위 분석 결과. 세션당 analysis_version별로 여러 개 존재할 수 있다."""

    id: str = Field(primary_key=True)
    session_id: str = Field(foreign_key="session.id", index=True)
    team_grade: str | None = Field(default=None)  # HIGH|MID|LOW
    internal_index: float | None = Field(default=None)  # ★ HTTP 응답에 절대 노출 금지
    distribution_json: str | None = Field(default=None)
    pair_results_json: str | None = Field(default=None)  # top_complement/top_caution만
    team_strength_codes_json: str = Field(default="[]")
    team_caution_codes_json: str = Field(default="[]")
    matched_rule_ids_json: str = Field(default="[]")
    analysis_version: int
    status: str = Field(default="PROCESSING")  # PROCESSING|COMPLETED|FALLBACK
    public_report_json: str | None = Field(default=None)  # AI 팀 코멘트 (GeneratedInsight)
    prompt_version: str | None = Field(default=None)
    model_id: str | None = Field(default=None)
    validation_status: str | None = Field(default=None)
    used_fallback: bool = Field(default=False)
    created_at: datetime = Field(default_factory=utcnow)


# ──────────────────────────────────────────────
# PrivateInsight
# ──────────────────────────────────────────────


class PrivateInsight(SQLModel, table=True):
    """참여자 본인만 열람 가능한 개인 인사이트.

    (participant_id, analysis_result_id) 유니크 — 캐시 키 역할.
    조회는 항상 participant_id 단일 조건이어야 하며, 팀 결과 쿼리와 join하지 않는다.
    """

    __table_args__ = (
        UniqueConstraint("participant_id", "analysis_result_id", name="uq_private_insight_participant_analysis"),
    )

    id: str = Field(primary_key=True)
    participant_id: str = Field(foreign_key="participant.id", index=True)
    analysis_result_id: str = Field(foreign_key="analysisresult.id", index=True)
    status: str = Field(default="NOT_REQUESTED")  # NOT_REQUESTED|PROCESSING|COMPLETED|FALLBACK
    insight_json: str | None = Field(default=None)
    prompt_version: str | None = Field(default=None)
    model_id: str | None = Field(default=None)
    validation_status: str | None = Field(default=None)
    used_fallback: bool = Field(default=False)
    created_at: datetime = Field(default_factory=utcnow)


# ──────────────────────────────────────────────
# QuestAssignment
# ──────────────────────────────────────────────


class QuestAssignment(SQLModel, table=True):
    """세션에 배정된 퀘스트 (팀 공유 또는 개인 전용).

    카탈로그(knowledge_base/quests.yaml)의 quest_code를 참조한다.
    문구(title/description/action)는 여기에 저장하지 않고 응답 시점에
    카탈로그에서 조회한다 — 카탈로그가 갱신되면 최신 문구가 자동 반영된다.

    scope=TEAM이면 participant_id는 None (세션 전체 공유).
    scope=PERSONAL이면 participant_id가 배정 대상 본인이다.

    팀 퀘스트는 참여자 누구나 완료 처리할 수 있다 (완료자만 completed_by_participant_id에 기록).
    """

    __table_args__ = (
        UniqueConstraint(
            "session_id", "participant_id", "quest_code", "analysis_version",
            name="uq_quest_assignment_target",
        ),
    )

    id: str = Field(primary_key=True)
    session_id: str = Field(foreign_key="session.id", index=True)
    participant_id: str | None = Field(default=None, foreign_key="participant.id", index=True)
    scope: str  # TEAM|PERSONAL
    quest_code: str
    analysis_version: int  # 분석이 재실행되면 새 버전으로 재배정 (design 일관성)
    status: str = Field(default="ASSIGNED")  # ASSIGNED|COMPLETED
    completed_by_participant_id: str | None = Field(default=None, foreign_key="participant.id")
    assigned_at: datetime = Field(default_factory=utcnow)
    completed_at: datetime | None = Field(default=None)

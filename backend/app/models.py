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
    """세션 — 주최자가 만든 팀 케미 분석 모임.

    SPEC_V5 §8.1의 TeamRoom과 동일 엔터티다. 초대 코드 하나가 한 팀이므로
    별도의 CompetitionRoom/Team을 새로 만들지 않고 이 모델을 재사용한다.
    - expected_team_size(SPEC) ↔ expected_member_count(기존) — 동일 개념, 이름 유지.
    - analysis_status(SPEC) ↔ status(기존) — status가 OPEN→ANALYZING→COMPLETED로
      분석 상태를 그대로 담고 있어 중복 컬럼을 추가하지 않는다.
    - host_participant_id/workspace_status는 SPEC이 요구하는 신규 상태라 필드만 추가한다.
    """

    id: str = Field(primary_key=True)
    name: str
    meeting_type: str = Field(default="team_project")
    expected_member_count: int  # 3..10 (애플리케이션 계층에서 검증) — SPEC expected_team_size
    status: str = Field(default="OPEN")  # OPEN|LOCKED|ANALYZING|COMPLETED|CLOSED — SPEC analysis_status
    invite_token_hash: str
    share_token_hash: str
    host_secret_hash: str
    host_participant_id: str | None = Field(default=None)  # 방장도 참여자로 합류한 경우에만 채워짐 (P0 미사용, 권한은 host_secret 기준)
    workspace_status: str = Field(default="LOCKED")  # LOCKED|ACTIVE
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
    public_report_json: str | None = Field(default=None)  # AI 팀 코멘트 (TeamSnapshot)
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
# QuestTemplateRecord — SPEC_V5 §4.1/§8.1 QuestTemplate 엔터티
# ──────────────────────────────────────────────


class QuestTemplateRecord(SQLModel, table=True):
    """퀘스트 카탈로그의 DB 미러.

    payload_json에 quest.schema.json 계약(QuestTemplate pydantic 모델)의 전체 payload를
    손실 없이 저장한다. 정본은 knowledge_base/quests.json이며, 서버 시작 시
    app.services.quests.catalog.sync_catalog_to_db()가 이 테이블을 덮어써 동기화한다.
    (Pydantic 계약 클래스는 app/services/quests/schemas.py의 QuestTemplate이며 이름이 겹치므로
    DB 행은 QuestTemplateRecord로 구분한다.)
    """

    quest_id: str = Field(primary_key=True)
    payload_json: str
    version: str
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


# ──────────────────────────────────────────────
# QuestAssignment — SPEC_V5 §6/§8.1
# ──────────────────────────────────────────────


class QuestAssignment(SQLModel, table=True):
    """방(세션) 단위 퀘스트 배정.

    active_slot: 활성 배정(ASSIGNED|IN_PROGRESS) 동안에는 session_id와 동일한 값을 채우고
    종료 상태(COMPLETED|SKIPPED)가 되면 None으로 되돌린다. 이 컬럼에 UNIQUE 제약을 걸어
    "팀당 활성 배정 최대 1개"를 DB 레벨에서 강제한다 (NULL은 유니크 제약에서 중복 허용되므로
    종료된 배정은 여러 개 쌓여도 충돌하지 않는다).
    """

    __table_args__ = (UniqueConstraint("active_slot", name="uq_quest_assignment_active_slot"),)

    id: str = Field(primary_key=True)
    session_id: str = Field(foreign_key="session.id", index=True)  # SPEC room_id
    quest_template_id: str = Field(foreign_key="questtemplaterecord.quest_id")
    status: str = Field(default="ASSIGNED")  # ASSIGNED|IN_PROGRESS|COMPLETED|SKIPPED
    active_slot: str | None = Field(default=None)
    assignment_source: str  # AGENT|RULE|FALLBACK — plain string, 마이그레이션 불필요
    assignment_reason: str
    intro_message: str
    used_rule_ids_json: str = Field(default="[]")
    result_json: str | None = Field(default=None)  # {"member_submissions": {...}, "team_submissions": {...}}
    version: str  # 배정 시점의 QuestTemplateRecord.version 스냅샷
    assigned_at: datetime = Field(default_factory=utcnow)
    started_at: datetime | None = Field(default=None)
    completed_at: datetime | None = Field(default=None)  # COMPLETED/SKIPPED 공통 종료 시각


# ──────────────────────────────────────────────
# Workspace / WorkspaceTask / ResourceLink — SPEC_V5 §7/§8.1 (P0)
# ──────────────────────────────────────────────


class Workspace(SQLModel, table=True):
    """방(세션)당 하나만 존재 — session_id UNIQUE로 협업 시작 멱등성을 보장한다."""

    id: str = Field(primary_key=True)
    session_id: str = Field(foreign_key="session.id", unique=True, index=True)
    status: str = Field(default="ACTIVE")  # P0에서는 ACTIVE만 사용
    started_at: datetime = Field(default_factory=utcnow)


class WorkspaceTask(SQLModel, table=True):
    """공동 할 일. created_by는 participant_id 또는 방장이면 'HOST' 리터럴."""

    id: str = Field(primary_key=True)
    workspace_id: str = Field(foreign_key="workspace.id", index=True)
    title: str
    status: str = Field(default="TODO")  # TODO|IN_PROGRESS|DONE
    assignee_participant_id: str | None = Field(default=None)
    due_at: datetime | None = Field(default=None)
    created_by: str  # participant_id 또는 "HOST"
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class ResourceLink(SQLModel, table=True):
    """공유 링크. created_by는 participant_id 또는 방장이면 'HOST' 리터럴."""

    id: str = Field(primary_key=True)
    workspace_id: str = Field(foreign_key="workspace.id", index=True)
    title: str
    url: str
    provider: str  # GITHUB|FIGMA|NOTION|GOOGLE_DRIVE|DEPLOYMENT|OTHER
    created_by: str
    created_at: datetime = Field(default_factory=utcnow)

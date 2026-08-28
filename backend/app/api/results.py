"""
결과 API — design.md §7.3, §7.5

GET /api/sessions/{id}/results/team
GET /api/sessions/{id}/results/me
GET /api/shared/{share_token}

응답은 allow-list 방식의 Pydantic 모델만 사용한다.
internal_index, metrics, matched_rule_ids(원본), PrivateInsight 필드는
어떤 응답에도 포함하지 않는다 (design.md §7.5, 하드 제약).
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlmodel import Session as DBSession
from sqlmodel import select

from app.auth import resolve_participant_by_secret, verify_secret
from app.db import get_session
from app.errors import ANALYSIS_NOT_FOUND, FORBIDDEN, INVALID_INVITE_TOKEN, SESSION_NOT_FOUND, app_error
from app.models import AnalysisResult, Participant, Session as SessionModel
from app.services.analysis.orchestrator import get_private_insight, render_rule_text

router = APIRouter(tags=["results"])


# ──────────────────────────────────────────────
# 응답 스키마 (allow-list)
# ──────────────────────────────────────────────


class TeamResultResponse(BaseModel):
    # 최신 기획: team_grade / team_caution_codes / top_caution_pairs /
    # team_strength_codes / top_complement_pairs 는 공개 API에서 제외한다.
    # used_rule_ids(내부 rule_id) 도 공개 응답에 노출하지 않는다.
    # (DB(AnalysisResult)에는 계속 저장·계산하되 응답 스키마에만 노출하지 않는다.)
    session_id: str
    status: str  # PROCESSING|COMPLETED|FALLBACK
    distribution: dict | None
    team_comment: dict | None  # TeamSnapshot(title/formula/scene/keywords) 또는 None
    rule_text_fallback: dict[str, str] | None = None  # AI 코멘트가 전혀 없을 때만


class PrivateResultResponse(BaseModel):
    participant_id: str
    status: str  # NOT_REQUESTED|PROCESSING|COMPLETED|FALLBACK
    self_positions: dict | None
    insight: dict | None  # PrivateCard(card_title/contribution/optional_try)


# ──────────────────────────────────────────────
# 내부 헬퍼
# ──────────────────────────────────────────────


def _latest_analysis(session_id: str, db: DBSession) -> AnalysisResult | None:
    return db.exec(
        select(AnalysisResult)
        .where(AnalysisResult.session_id == session_id)
        .order_by(AnalysisResult.analysis_version.desc())
    ).first()


def _strip_internal(payload: dict | None) -> dict | None:
    """AI 산출물 dict에서 내부 전용 필드(used_rule_ids)를 제거한다."""
    if payload is None:
        return None
    return {k: v for k, v in payload.items() if k != "used_rule_ids"}


def _build_team_result(session_id: str, analysis: AnalysisResult | None) -> TeamResultResponse:
    if analysis is None:
        return TeamResultResponse(
            session_id=session_id,
            status="PROCESSING",
            distribution=None,
            team_comment=None,
        )

    distribution = json.loads(analysis.distribution_json) if analysis.distribution_json else None
    team_comment = (
        _strip_internal(json.loads(analysis.public_report_json))
        if analysis.public_report_json
        else None
    )

    rule_text_fallback = None
    if team_comment is None and analysis.status in ("FALLBACK", "PROCESSING"):
        matched_rule_ids = json.loads(analysis.matched_rule_ids_json) if analysis.matched_rule_ids_json else []
        rule_text_fallback = render_rule_text(matched_rule_ids) or None

    return TeamResultResponse(
        session_id=session_id,
        status=analysis.status,
        distribution=distribution,
        team_comment=team_comment,
        rule_text_fallback=rule_text_fallback,
    )


# ──────────────────────────────────────────────
# 엔드포인트
# ──────────────────────────────────────────────


@router.get("/sessions/{session_id}/results/team", response_model=TeamResultResponse)
def get_team_result(
    session_id: str,
    db: DBSession = Depends(get_session),
) -> TeamResultResponse:
    session = db.get(SessionModel, session_id)
    if session is None:
        raise app_error(SESSION_NOT_FOUND, f"세션을 찾을 수 없습니다: {session_id}")

    analysis = _latest_analysis(session_id, db)
    return _build_team_result(session_id, analysis)


@router.get("/sessions/{session_id}/results/me", response_model=PrivateResultResponse)
def get_my_result(
    session_id: str,
    db: DBSession = Depends(get_session),
    participant: Participant = Depends(resolve_participant_by_secret),
) -> PrivateResultResponse:
    if participant.session_id != session_id:
        raise app_error(FORBIDDEN, "본인의 세션 결과만 조회할 수 있습니다.")

    analysis = _latest_analysis(session_id, db)
    if analysis is None:
        raise app_error(ANALYSIS_NOT_FOUND, "아직 분석이 시작되지 않았습니다.")

    private_insight = get_private_insight(participant.id, analysis.id, db)

    from app.services.profile.profile_helpers import canonical_profile_for_participant

    profile = canonical_profile_for_participant(participant.id, db)

    insight = (
        _strip_internal(json.loads(private_insight.insight_json))
        if private_insight.insight_json
        else None
    )

    return PrivateResultResponse(
        participant_id=participant.id,
        status=private_insight.status,
        self_positions=dict(profile.positions.items()),
        insight=insight,
    )


@router.get("/shared/{share_token}", response_model=TeamResultResponse)
def get_shared_result(
    share_token: str,
    db: DBSession = Depends(get_session),
) -> TeamResultResponse:
    """토큰 자체가 인증. 개인 데이터는 절대 포함하지 않는다 (팀 결과와 동일 스키마)."""
    sessions = db.exec(select(SessionModel)).all()
    session = next((s for s in sessions if verify_secret(share_token, s.share_token_hash)), None)
    if session is None:
        raise app_error(INVALID_INVITE_TOKEN, "유효하지 않은 공유 링크입니다.")

    analysis = _latest_analysis(session.id, db)
    return _build_team_result(session.id, analysis)

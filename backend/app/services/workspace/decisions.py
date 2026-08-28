"""
빠른 의사결정 보드 — SPEC_V5.3 §4

- 참가자 1명당 안건 1표. 재투표 시 기존 표의 option_id를 갱신한다(DecisionVote UNIQUE로 보장).
- FINALIZED 안건은 투표를 받지 않는다.
- 최종 확정은 방장만 가능하다(호출부 require_host_actor로 검증).
- 다른 팀원의 투표 내역은 공개하지 않는다 — 집계된 vote_count와 요청자 본인의 표만 노출한다.
"""

from __future__ import annotations

import uuid
from collections import Counter

from sqlmodel import Session as DBSession
from sqlmodel import select

from app.errors import (
    DECISION_ALREADY_FINALIZED,
    DECISION_NOT_FOUND,
    DECISION_OPTION_NOT_FOUND,
    VALIDATION_ERROR,
    app_error,
)
from app.models import Decision, DecisionOption, DecisionVote, utcnow


def list_decisions(workspace_id: str, db: DBSession) -> list[Decision]:
    return list(db.exec(select(Decision).where(Decision.workspace_id == workspace_id)).all())


def create_decision(
    workspace_id: str,
    db: DBSession,
    *,
    title: str,
    options: list[str],
    created_by: str,
    description: str | None = None,
) -> Decision:
    if len(options) < 1:
        raise app_error(VALIDATION_ERROR, "선택지가 최소 1개 이상 필요합니다.")

    decision = Decision(
        id=str(uuid.uuid4()),
        workspace_id=workspace_id,
        title=title,
        description=description,
        created_by=created_by,
    )
    db.add(decision)
    db.add_all(
        [DecisionOption(id=str(uuid.uuid4()), decision_id=decision.id, label=label) for label in options]
    )
    db.commit()
    db.refresh(decision)
    return decision


def get_decision_or_404(decision_id: str, db: DBSession) -> Decision:
    decision = db.get(Decision, decision_id)
    if decision is None:
        raise app_error(DECISION_NOT_FOUND, f"안건을 찾을 수 없습니다: {decision_id}")
    return decision


def list_options(decision_id: str, db: DBSession) -> list[DecisionOption]:
    return list(db.exec(select(DecisionOption).where(DecisionOption.decision_id == decision_id)).all())


def vote_counts(decision_id: str, db: DBSession) -> Counter[str]:
    votes = db.exec(select(DecisionVote).where(DecisionVote.decision_id == decision_id)).all()
    return Counter(v.option_id for v in votes)


def my_vote_option_id(decision_id: str, participant_id: str | None, db: DBSession) -> str | None:
    """방장(participant_id=None)은 투표 대상이 아니므로 항상 None."""
    if participant_id is None:
        return None
    vote = db.exec(
        select(DecisionVote).where(
            DecisionVote.decision_id == decision_id, DecisionVote.participant_id == participant_id
        )
    ).first()
    return vote.option_id if vote else None


def cast_vote(decision_id: str, db: DBSession, *, participant_id: str, option_id: str) -> Decision:
    decision = get_decision_or_404(decision_id, db)
    if decision.status == "FINALIZED":
        raise app_error(DECISION_ALREADY_FINALIZED, "이미 확정된 안건에는 투표할 수 없습니다.")

    option = db.get(DecisionOption, option_id)
    if option is None or option.decision_id != decision_id:
        raise app_error(DECISION_OPTION_NOT_FOUND, f"선택지를 찾을 수 없습니다: {option_id}")

    existing = db.exec(
        select(DecisionVote).where(
            DecisionVote.decision_id == decision_id, DecisionVote.participant_id == participant_id
        )
    ).first()
    if existing is not None:
        existing.option_id = option_id
        existing.created_at = utcnow()
        db.add(existing)
    else:
        db.add(
            DecisionVote(
                id=str(uuid.uuid4()),
                decision_id=decision_id,
                option_id=option_id,
                participant_id=participant_id,
            )
        )
    db.commit()
    db.refresh(decision)
    return decision


def finalize_decision(decision_id: str, db: DBSession, *, final_result: str) -> Decision:
    decision = get_decision_or_404(decision_id, db)
    if decision.status == "FINALIZED":
        raise app_error(DECISION_ALREADY_FINALIZED, "이미 확정된 안건입니다.")
    decision.status = "FINALIZED"
    decision.final_result = final_result
    decision.finalized_at = utcnow()
    db.add(decision)
    db.commit()
    db.refresh(decision)
    return decision

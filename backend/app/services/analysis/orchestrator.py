"""
분석 오케스트레이션 — design.md §6.2

세 진입점:
- start_analysis: 게이트 확인 → 잠금 → 엔진 동기 실행 → 결과 저장 → 백그라운드 AI 코멘트
- get_private_insight: lazy 생성 + 캐시
- render_rule_text: matched_rule_ids → knowledge_base 텍스트 (AI 폴백용 최후 수단)

app/services/chemistry, app/services/scoring은 여기서 import되는 방향으로만 사용되고
반대로 이 모듈을 import하지 않는다 (의존 방향 준수).
"""

from __future__ import annotations

import json
import logging
import uuid

from sqlmodel import Session as DBSession
from sqlmodel import select

from ai.chains.private_insight import generate_private_insight as ai_generate_private_insight
from ai.chains.team_comment import generate_team_comment as ai_generate_team_comment
from app.services.chemistry import engine

from app.errors import (
    ANALYSIS_ALREADY_RUNNING,
    ANALYSIS_NOT_READY,
    SESSION_NOT_FOUND,
    app_error,
)
from app.models import AnalysisResult, Participant, Session as SessionModel
from app.services.profile.profile_helpers import canonical_profiles_for_session

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# start_analysis
# ──────────────────────────────────────────────


def start_analysis(session_id: str, db: DBSession) -> AnalysisResult:
    """규칙 분석을 동기 실행하고, AI 팀 코멘트는 호출자가 백그라운드로 이어 붙인다.

    Returns:
        방금 만든 AnalysisResult (status=PROCESSING). AI 코멘트 완료 후
        run_team_comment_generation(analysis_result.id, db)를 호출해 상태를 갱신한다.
    """
    session = db.get(SessionModel, session_id)
    if session is None:
        raise app_error(SESSION_NOT_FOUND, f"세션을 찾을 수 없습니다: {session_id}")

    submitted = db.exec(
        select(Participant).where(
            Participant.session_id == session_id,
            Participant.submission_status == "SUBMITTED",
        )
    ).all()

    if len(submitted) != session.expected_member_count:
        raise app_error(
            ANALYSIS_NOT_READY,
            f"제출 인원({len(submitted)})이 목표 인원({session.expected_member_count})과 다릅니다.",
        )

    existing_running = db.exec(
        select(AnalysisResult).where(
            AnalysisResult.session_id == session_id,
            AnalysisResult.status == "PROCESSING",
        )
    ).first()
    if existing_running is not None:
        raise app_error(ANALYSIS_ALREADY_RUNNING, "이미 진행 중인 분석이 있습니다.")

    # 잠금
    session.status = "ANALYZING"
    for p in submitted:
        p.submission_status = "LOCKED"
    db.add(session)
    for p in submitted:
        db.add(p)
    db.commit()

    profiles = canonical_profiles_for_session(session_id, db)

    engine_result = engine.run_team_analysis(profiles)

    prev_max = db.exec(
        select(AnalysisResult.analysis_version).where(AnalysisResult.session_id == session_id)
    ).all()
    next_version = (max(prev_max) + 1) if prev_max else 1

    analysis_result = AnalysisResult(
        id=str(uuid.uuid4()),
        session_id=session_id,
        team_grade=engine_result.team_grade,
        internal_index=engine_result.internal_index,
        distribution_json=json.dumps(engine_result.distribution),
        pair_results_json=json.dumps(
            {
                "top_complement": [_pair_to_dict(p) for p in engine_result.top_complement_pairs],
                "top_caution": [_pair_to_dict(p) for p in engine_result.top_caution_pairs],
            }
        ),
        team_strength_codes_json=json.dumps(engine_result.team_strength_codes),
        team_caution_codes_json=json.dumps(engine_result.team_caution_codes),
        matched_rule_ids_json=json.dumps(engine_result.matched_rule_ids),
        analysis_version=next_version,
        status="PROCESSING",
    )
    db.add(analysis_result)

    session.status = "COMPLETED"
    db.add(session)
    db.commit()
    db.refresh(analysis_result)

    return analysis_result


def _pair_to_dict(pair: engine.PairResult) -> dict:
    return {
        "participant_a_id": pair.participant_a_id,
        "participant_b_id": pair.participant_b_id,
        "category": pair.category,
        "rule_id": pair.rule_id,
        "code": pair.code,
        "axis": pair.axis,
    }


def run_team_comment_generation(analysis_result_id: str, db: DBSession) -> None:
    """백그라운드 태스크 — AI 팀 코멘트를 생성하고 AnalysisResult를 갱신한다.

    Bedrock 실패(timeout/throttle/parse)는 여기서 흡수하고 전체 분석을
    실패시키지 않는다. ai.chains.team_comment.generate_team_comment 내부의
    LangGraph가 이미 fallback으로 귀결시키므로, 이 함수에서는 예외가 나더라도
    FALLBACK 상태로 마감한다.
    """
    analysis_result = db.get(AnalysisResult, analysis_result_id)
    if analysis_result is None:
        logger.error("run_team_comment_generation: analysis_result not found (id omitted)")
        return

    team_size = db.exec(
        select(Participant).where(
            Participant.session_id == analysis_result.session_id,
            Participant.submission_status == "LOCKED",
        )
    ).all()

    engine_result_like = _analysis_result_to_engine_like(analysis_result)

    try:
        team_input = engine.build_team_comment_input(
            engine_result_like, analysis_result_id, team_size=len(team_size)
        )
        generation = ai_generate_team_comment(team_input)
        analysis_result.status = generation.status
        analysis_result.public_report_json = generation.insight.model_dump_json()
        analysis_result.prompt_version = generation.prompt_version
        analysis_result.model_id = generation.model_id
        analysis_result.used_fallback = generation.used_fallback
        analysis_result.validation_status = (
            "PASSED" if not generation.validation_errors else "FAILED_THEN_FALLBACK"
        )
    except Exception:  # noqa: BLE001 — Bedrock/네트워크 예외를 흡수해 분석 실패로 전파하지 않는다
        logger.exception("run_team_comment_generation: AI 코멘트 생성 실패, FALLBACK 처리")
        analysis_result.status = "FALLBACK"
        analysis_result.used_fallback = True

    db.add(analysis_result)
    db.commit()


def _analysis_result_to_engine_like(analysis_result: AnalysisResult):
    """AnalysisResult row를 engine.TeamAnalysisResult 호환 형태로 감싼다.

    build_team_comment_input은 team_grade/strength_codes/caution_codes/
    matched_rule_ids/evidence_levels/distribution 속성만 읽으므로 최소 형태로 재구성한다.
    """
    from types import SimpleNamespace

    distribution = json.loads(analysis_result.distribution_json) if analysis_result.distribution_json else {}
    strength_codes = json.loads(analysis_result.team_strength_codes_json)
    caution_codes = json.loads(analysis_result.team_caution_codes_json)
    matched_rule_ids = json.loads(analysis_result.matched_rule_ids_json)

    # evidence_levels는 저장하지 않으므로 team_rules.yaml에서 재조회한다.
    evidence_levels = _evidence_levels_for_codes(strength_codes + caution_codes)

    return SimpleNamespace(
        team_grade=analysis_result.team_grade,
        team_strength_codes=strength_codes,
        team_caution_codes=caution_codes,
        matched_rule_ids=matched_rule_ids,
        evidence_levels=evidence_levels,
        distribution=distribution,
    )


def _evidence_levels_for_codes(codes: list[str]) -> dict[str, str]:
    rules = engine.load_team_rules().get("rules", [])
    levels: dict[str, str] = {}
    for rule in rules:
        produces = rule.get("produces", {})
        evidence = rule.get("evidence_level", "limited")
        for key in ("strength_code", "caution_code"):
            code = produces.get(key)
            if code and code in codes:
                levels[code] = evidence
    return levels


# ──────────────────────────────────────────────
# get_private_insight
# ──────────────────────────────────────────────


def get_private_insight(participant_id: str, analysis_result_id: str, db: DBSession):
    """개인 인사이트를 lazy 생성하고 캐시한다 (design.md §6.2)."""
    from app.models import PrivateInsight

    existing = db.exec(
        select(PrivateInsight).where(
            PrivateInsight.participant_id == participant_id,
            PrivateInsight.analysis_result_id == analysis_result_id,
        )
    ).first()

    if existing is not None:
        return existing

    placeholder = PrivateInsight(
        id=str(uuid.uuid4()),
        participant_id=participant_id,
        analysis_result_id=analysis_result_id,
        status="PROCESSING",
    )
    db.add(placeholder)
    db.commit()
    db.refresh(placeholder)

    try:
        _generate_private_insight_now(placeholder, db)
    except Exception:  # noqa: BLE001
        logger.exception("get_private_insight: 개인 인사이트 생성 실패, FALLBACK 처리")
        placeholder.status = "FALLBACK"
        db.add(placeholder)
        db.commit()

    db.refresh(placeholder)
    return placeholder


def _generate_private_insight_now(private_insight, db: DBSession) -> None:
    from app.services.profile.profile_helpers import canonical_profile_for_participant

    analysis_result = db.get(AnalysisResult, private_insight.analysis_result_id)
    if analysis_result is None:
        from app.errors import ANALYSIS_NOT_FOUND, app_error

        raise app_error(ANALYSIS_NOT_FOUND, "분석 결과를 찾을 수 없습니다.")

    distribution = json.loads(analysis_result.distribution_json) if analysis_result.distribution_json else {}
    profile = canonical_profile_for_participant(private_insight.participant_id, db)

    team_size = db.exec(
        select(Participant).where(
            Participant.session_id == analysis_result.session_id,
            Participant.submission_status == "LOCKED",
        )
    ).all()

    private_result = engine.match_private_rules(profile, distribution, team_size=len(team_size))
    private_input = engine.build_private_comment_input(
        private_result, private_insight.analysis_result_id, distribution, profile
    )

    generation = ai_generate_private_insight(private_input)

    private_insight.status = generation.status
    private_insight.insight_json = generation.insight.model_dump_json()
    private_insight.prompt_version = generation.prompt_version
    private_insight.model_id = generation.model_id
    private_insight.used_fallback = generation.used_fallback
    private_insight.validation_status = (
        "PASSED" if not generation.validation_errors else "FAILED_THEN_FALLBACK"
    )
    db.add(private_insight)
    db.commit()


# ──────────────────────────────────────────────
# render_rule_text
# ──────────────────────────────────────────────


def render_rule_text(rule_ids: list[str]) -> dict[str, str]:
    """matched_rule_ids → knowledge_base의 produces.description 매핑.

    AI 코멘트가 전혀 없는 극단적 상황(둘 다 실패)의 최후 폴백 문장으로만 쓴다.
    평소에는 ai/nodes/fallback.py의 결정론적 템플릿이 우선한다.
    """
    text_by_rule: dict[str, str] = {}

    for loader in (engine.load_team_rules, engine.load_pair_rules, engine.load_private_rules):
        rules = loader().get("rules", [])
        for rule in rules:
            rid = rule.get("rule_id")
            if rid in rule_ids:
                desc = rule.get("produces", {}).get("description")
                if desc:
                    text_by_rule[rid] = desc

    return text_by_rule

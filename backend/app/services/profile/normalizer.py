"""
프로필 정규화 — DB row(ParticipantProfile) ↔ CanonicalProfile(ai.schemas)

design.md §6.1. ratios/means가 없으면(DECLARED_TYPE) None을 그대로 유지한다
(가짜 비율을 부여하지 않는다, SPEC §3.5).
"""

from __future__ import annotations

import json

from ai.schemas import AXIS_KEYS, CanonicalProfile

from app.models import ParticipantProfile as ParticipantProfileRow


def profile_row_to_canonical(row: ParticipantProfileRow) -> CanonicalProfile:
    """DB row를 ai.schemas.CanonicalProfile로 변환한다."""
    positions = json.loads(row.positions_json)
    ratios = json.loads(row.ratios_json) if row.ratios_json else None
    means = json.loads(row.means_json) if row.means_json else None
    axis_flags = json.loads(row.axis_flags_json) if row.axis_flags_json else []

    return CanonicalProfile(
        participant_id=row.participant_id,
        source=row.source,
        question_set_version=row.question_set_version,
        positions=positions,
        ratios=ratios,
        means=means,
        axis_flags=axis_flags,
    )


def canonical_to_profile_row(
    canonical: CanonicalProfile,
    *,
    analysis_version: int = 0,
    answers: list[int] | None = None,
) -> ParticipantProfileRow:
    """CanonicalProfile을 DB row로 변환한다.

    Args:
        canonical: 정규화된 프로필 (스코어러 또는 직접입력 생성 결과)
        analysis_version: 이 프로필이 속한 분석 버전
        answers: SURVEY인 경우 원본 24개 응답 (선택 저장)
    """
    positions_dict = dict(canonical.positions.items())

    return ParticipantProfileRow(
        participant_id=canonical.participant_id,
        source=canonical.source,
        question_set_version=canonical.question_set_version,
        answers_json=json.dumps(answers) if answers is not None else None,
        positions_json=json.dumps(positions_dict),
        ratios_json=json.dumps(canonical.ratios) if canonical.ratios is not None else None,
        means_json=json.dumps(canonical.means) if canonical.means is not None else None,
        axis_flags_json=json.dumps(canonical.axis_flags),
        analysis_version=analysis_version,
    )


def distribution_from_json(distribution_json: str) -> dict[str, dict[str, int]]:
    """AnalysisResult.distribution_json → dict. 4축 키가 모두 있는지 방어적으로 확인."""
    data = json.loads(distribution_json)
    for axis in AXIS_KEYS:
        data.setdefault(axis, {})
    return data

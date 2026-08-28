"""
규칙 엔진 서비스

YAML 규칙 지식베이스를 로드하고, CanonicalProfile 집합을 기반으로
팀·페어·개인 분석을 결정론적으로 수행한다.

- LLM, LangChain, LangGraph를 import하지 않는다.
- 동일 입력에 대해 항상 동일한 결과를 보장한다.
- 중립 축은 충돌 규칙에서 제외한다.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from ai.schemas import (
    AXIS_KEYS,
    NEUTRAL,
    POSITION_ENUM,
    CanonicalProfile,
    TeamCommentInput,
    PrivateCommentInput,
)

KNOWLEDGE_BASE_DIR = Path(__file__).parent.parent.parent.parent / "knowledge_base"


# ──────────────────────────────────────────────
# 규칙 로더
# ──────────────────────────────────────────────


def _load_yaml(filename: str) -> dict | list:
    path = KNOWLEDGE_BASE_DIR / filename
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_team_rules() -> dict:
    return _load_yaml("team_rules.yaml")


def load_pair_rules() -> dict:
    return _load_yaml("pair_rules.yaml")


def load_private_rules() -> dict:
    return _load_yaml("private_insight_rules.yaml")


def load_recommendations() -> dict:
    return _load_yaml("recommendations.yaml")


# ──────────────────────────────────────────────
# 분석 결과 데이터 클래스
# ──────────────────────────────────────────────


@dataclass
class PairResult:
    participant_a_id: str
    participant_b_id: str
    category: str  # complement, friction, alignment
    rule_id: str
    code: str
    axis: str


@dataclass
class TeamAnalysisResult:
    """규칙 엔진의 팀 분석 결과"""

    team_grade: str  # HIGH, MID, LOW
    internal_index: float
    distribution: dict[str, dict[str, int]]
    pair_results: list[PairResult]
    team_strength_codes: list[str]
    team_caution_codes: list[str]
    matched_rule_ids: list[str]
    evidence_levels: dict[str, str]

    # 대표 페어 조합 (화면 노출용, 각 최대 3개)
    top_complement_pairs: list[PairResult] = field(default_factory=list)
    top_caution_pairs: list[PairResult] = field(default_factory=list)


@dataclass
class PrivateAnalysisResult:
    """규칙 엔진의 개인 분석 결과"""

    participant_id: str
    strength_codes: list[str]
    caution_codes: list[str]
    recommendation_codes: list[str]
    matched_rule_ids: list[str]


# ──────────────────────────────────────────────
# 팀 분포 계산
# ──────────────────────────────────────────────


def compute_distribution(profiles: list[CanonicalProfile]) -> dict[str, dict[str, int]]:
    """4축 각각의 포지션 분포를 계산한다."""
    distribution: dict[str, dict[str, int]] = {}

    for axis in AXIS_KEYS:
        upper, lower = POSITION_ENUM[axis]
        counts = {upper: 0, lower: 0, NEUTRAL: 0}
        for p in profiles:
            pos = p.positions.get(axis, NEUTRAL)
            if pos in counts:
                counts[pos] += 1
            else:
                counts[NEUTRAL] += 1
        distribution[axis] = counts

    return distribution


def _get_majority(counts: dict[str, int], axis: str) -> str | None:
    """해당 축에서 과반을 차지하는 포지션을 반환한다. 없으면 None."""
    upper, lower = POSITION_ENUM[axis]
    total = sum(counts.values())
    if total == 0:
        return None
    if counts[upper] > total / 2:
        return upper
    if counts[lower] > total / 2:
        return lower
    return None


# ──────────────────────────────────────────────
# 팀 규칙 매칭
# ──────────────────────────────────────────────


def _match_team_condition(condition: str, counts: dict[str, int], axis: str) -> bool:
    """팀 규칙의 when.condition을 평가한다."""
    upper, lower = POSITION_ENUM[axis]
    total = sum(counts.values())

    if condition == "balanced":
        return counts[upper] >= 1 and counts[lower] >= 1
    elif condition == "majority_upper":
        return counts[upper] > total / 2
    elif condition == "majority_lower":
        return counts[lower] > total / 2
    elif condition == "all_upper":
        return counts[upper] == total and total > 0
    elif condition == "all_lower":
        return counts[lower] == total and total > 0
    elif condition == "has_upper":
        return counts[upper] >= 1
    elif condition == "has_lower":
        return counts[lower] >= 1
    elif condition == "no_upper":
        return counts[upper] == 0
    elif condition == "no_lower":
        return counts[lower] == 0
    return False


def match_team_rules(
    distribution: dict[str, dict[str, int]],
) -> tuple[list[str], list[str], list[str], dict[str, str]]:
    """팀 규칙을 매칭하여 강점·주의 코드와 rule_id를 반환한다.

    Returns:
        (strength_codes, caution_codes, matched_rule_ids, evidence_levels)
    """
    rules_data = load_team_rules()
    rules = rules_data.get("rules", [])

    strength_codes: list[str] = []
    caution_codes: list[str] = []
    matched_rule_ids: list[str] = []
    evidence_levels: dict[str, str] = {}

    for rule in rules:
        when = rule.get("when", {})
        axis = when.get("axis")
        condition = when.get("condition")

        if not axis or not condition:
            continue
        if axis not in distribution:
            continue

        counts = distribution[axis]
        if _match_team_condition(condition, counts, axis):
            produces = rule.get("produces", {})
            rule_id = rule.get("rule_id", "")
            matched_rule_ids.append(rule_id)

            if "strength_code" in produces:
                code = produces["strength_code"]
                strength_codes.append(code)
                evidence_levels[code] = rule.get("evidence_level", "limited")
            if "caution_code" in produces:
                code = produces["caution_code"]
                caution_codes.append(code)
                evidence_levels[code] = rule.get("evidence_level", "limited")

    return strength_codes, caution_codes, matched_rule_ids, evidence_levels


# ──────────────────────────────────────────────
# 페어 규칙 매칭
# ──────────────────────────────────────────────


def match_pair_rules(profiles: list[CanonicalProfile]) -> list[PairResult]:
    """n*(n-1)/2 페어에 대해 규칙을 매칭한다."""
    rules_data = load_pair_rules()
    rules = rules_data.get("rules", [])
    results: list[PairResult] = []

    for p_a, p_b in itertools.combinations(profiles, 2):
        for rule in rules:
            when = rule.get("when", {})
            axis = when.get("axis")
            positions_required = set(when.get("positions", []))

            if not axis or not positions_required:
                continue

            pos_a = p_a.positions.get(axis, NEUTRAL)
            pos_b = p_b.positions.get(axis, NEUTRAL)

            # 중립 축은 충돌 규칙에서 제외
            if pos_a == NEUTRAL or pos_b == NEUTRAL:
                continue

            pair_positions = {pos_a, pos_b}

            # 같은 포지션 쌍 규칙 (예: [DRIVER, DRIVER])
            if len(positions_required) == 1:
                required_pos = list(positions_required)[0]
                if pos_a == required_pos and pos_b == required_pos:
                    produces = rule.get("produces", {})
                    code = produces.get("strength_code") or produces.get("caution_code", "")
                    results.append(PairResult(
                        participant_a_id=p_a.participant_id,
                        participant_b_id=p_b.participant_id,
                        category=rule.get("category", ""),
                        rule_id=rule.get("rule_id", ""),
                        code=code,
                        axis=axis,
                    ))
            # 다른 포지션 쌍 규칙 (예: [DRIVER, SUPPORTER])
            elif pair_positions == positions_required:
                produces = rule.get("produces", {})
                code = produces.get("strength_code") or produces.get("caution_code", "")
                results.append(PairResult(
                    participant_a_id=p_a.participant_id,
                    participant_b_id=p_b.participant_id,
                    category=rule.get("category", ""),
                    rule_id=rule.get("rule_id", ""),
                    code=code,
                    axis=axis,
                ))

    return results


# ──────────────────────────────────────────────
# 팀 index & 등급 계산
# ──────────────────────────────────────────────


def compute_team_index(
    distribution: dict[str, dict[str, int]],
    pair_results: list[PairResult],
    profiles: list[CanonicalProfile],
) -> float:
    """수정된 팀 index를 계산한다.

    team_index = 0.30*balance + 0.30*complement + 0.25*task_fit + 0.15*(1-conflict_risk)
    """
    team_size = len(profiles)
    if team_size < 2:
        return 0.5

    total_pairs = team_size * (team_size - 1) / 2

    # balance: 4축 각각에서 상위·하위가 모두 존재하는 비율
    balanced_axes = 0
    for axis in AXIS_KEYS:
        counts = distribution.get(axis, {})
        upper, lower = POSITION_ENUM[axis]
        if counts.get(upper, 0) >= 1 and counts.get(lower, 0) >= 1:
            balanced_axes += 1
    balance = balanced_axes / len(AXIS_KEYS)

    # complement: 보완 페어 수 / 전체 페어 수
    complement_count = sum(1 for pr in pair_results if pr.category == "complement")
    complement = min(complement_count / max(total_pairs, 1), 1.0)

    # task_fit: planning 축에서 PLANNER가 1명 이상이고 ADAPTER도 1명 이상인지
    planning_counts = distribution.get("planning", {})
    has_planner = planning_counts.get("PLANNER", 0) >= 1
    has_adapter = planning_counts.get("ADAPTER", 0) >= 1
    task_fit = 1.0 if (has_planner and has_adapter) else 0.5

    # conflict_risk: 마찰 페어 수 / 전체 페어 수
    friction_count = sum(1 for pr in pair_results if pr.category == "friction")
    conflict_risk = min(friction_count / max(total_pairs, 1), 1.0)

    index = (
        0.30 * balance
        + 0.30 * complement
        + 0.25 * task_fit
        + 0.15 * (1 - conflict_risk)
    )

    return round(index, 4)


def determine_grade(index: float) -> str:
    """팀 index를 3단계 등급으로 변환한다."""
    rules_data = load_team_rules()
    thresholds = rules_data.get("grade_thresholds", {"HIGH": 0.65, "MID": 0.40})

    if index >= thresholds["HIGH"]:
        return "HIGH"
    elif index >= thresholds["MID"]:
        return "MID"
    else:
        return "LOW"


# ──────────────────────────────────────────────
# 개인 규칙 매칭
# ──────────────────────────────────────────────


def match_private_rules(
    profile: CanonicalProfile,
    distribution: dict[str, dict[str, int]],
    team_size: int,
) -> PrivateAnalysisResult:
    """개인 강점·주의점 규칙을 매칭한다."""
    rules_data = load_private_rules()
    rules = rules_data.get("rules", [])
    recommendations_data = load_recommendations()
    recommendations = {r["code"]: r for r in recommendations_data.get("recommendations", [])}

    strength_codes: list[str] = []
    caution_codes: list[str] = []
    recommendation_codes: list[str] = []
    matched_rule_ids: list[str] = []

    for rule in rules:
        when = rule.get("when", {})
        matched = True

        # self 조건 확인
        for key, expected_value in when.items():
            if key.startswith("self."):
                axis = key.replace("self.", "")
                actual = profile.positions.get(axis, NEUTRAL)
                if actual != expected_value:
                    matched = False
                    break
            elif key.startswith("team."):
                # team.{axis}.majority 형식
                parts = key.replace("team.", "").split(".")
                if len(parts) == 2:
                    axis, check_type = parts
                    if check_type == "majority":
                        counts = distribution.get(axis, {})
                        majority = _get_majority(counts, axis)
                        if majority != expected_value:
                            matched = False
                            break

        if not matched:
            continue

        produces = rule.get("produces", {})
        rule_id = rule.get("rule_id", "")
        matched_rule_ids.append(rule_id)

        if "strength_code" in produces:
            strength_codes.append(produces["strength_code"])
        if "caution_code" in produces:
            caution_codes.append(produces["caution_code"])
        if "recommendation_code" in produces:
            recommendation_codes.append(produces["recommendation_code"])

    return PrivateAnalysisResult(
        participant_id=profile.participant_id,
        strength_codes=strength_codes,
        caution_codes=caution_codes,
        recommendation_codes=recommendation_codes,
        matched_rule_ids=matched_rule_ids,
    )


# ──────────────────────────────────────────────
# 통합 분석 실행
# ──────────────────────────────────────────────


def run_team_analysis(profiles: list[CanonicalProfile]) -> TeamAnalysisResult:
    """전체 팀 분석을 실행한다.

    Args:
        profiles: 목표 인원 수만큼의 CanonicalProfile 리스트

    Returns:
        TeamAnalysisResult: 팀·페어 분석 결과
    """
    # 1. 분포 계산
    distribution = compute_distribution(profiles)

    # 2. 팀 규칙 매칭
    strength_codes, caution_codes, team_rule_ids, evidence_levels = match_team_rules(
        distribution
    )

    # 3. 페어 규칙 매칭
    pair_results = match_pair_rules(profiles)
    pair_rule_ids = [pr.rule_id for pr in pair_results]

    # 4. 팀 index 및 등급 계산
    team_index = compute_team_index(distribution, pair_results, profiles)
    team_grade = determine_grade(team_index)

    # 5. 대표 페어 조합 선택 (각 최대 3개)
    complement_pairs = sorted(
        [pr for pr in pair_results if pr.category == "complement"],
        key=lambda x: x.rule_id,
    )[:3]
    caution_pairs = sorted(
        [pr for pr in pair_results if pr.category in ("friction", "alignment")],
        key=lambda x: x.rule_id,
    )[:3]

    # 6. 모든 rule_id 통합
    all_rule_ids = list(dict.fromkeys(team_rule_ids + pair_rule_ids))

    return TeamAnalysisResult(
        team_grade=team_grade,
        internal_index=team_index,
        distribution=distribution,
        pair_results=pair_results,
        team_strength_codes=list(dict.fromkeys(strength_codes)),
        team_caution_codes=list(dict.fromkeys(caution_codes)),
        matched_rule_ids=all_rule_ids,
        evidence_levels=evidence_levels,
        top_complement_pairs=complement_pairs,
        top_caution_pairs=caution_pairs,
    )


def build_team_comment_input(
    analysis: TeamAnalysisResult,
    analysis_result_id: str,
    team_size: int,
) -> TeamCommentInput:
    """팀 분석 결과에서 AI 팀 코멘트 입력을 구성한다.

    matched_rule_ids는 strength 코드를 생성하는 규칙만 포함한다.
    caution/recommendation/evidence/team_grade는 AI에 전달하지 않는다.
    """
    # strength 규칙만 필터: 해당 rule이 strength_code를 생성하고
    # 그 code가 analysis.team_strength_codes에 포함되는 것만 남긴다.
    rules_data = load_team_rules()
    rules = rules_data.get("rules", [])
    strength_rule_ids: list[str] = []
    for rule in rules:
        produces = rule.get("produces", {})
        if "strength_code" in produces:
            code = produces["strength_code"]
            if code in analysis.team_strength_codes:
                rid = rule.get("rule_id", "")
                if rid in analysis.matched_rule_ids:
                    strength_rule_ids.append(rid)

    return TeamCommentInput(
        analysis_result_id=analysis_result_id,
        strength_codes=analysis.team_strength_codes,
        matched_rule_ids=list(dict.fromkeys(strength_rule_ids)),
        team_size=team_size,
        distribution=analysis.distribution,
    )


def build_private_comment_input(
    private_result: PrivateAnalysisResult,
    analysis_result_id: str,
    distribution: dict[str, dict[str, int]],
    profile: CanonicalProfile,
) -> PrivateCommentInput:
    """개인 분석 결과에서 AI 개인 코멘트 입력을 구성한다."""
    return PrivateCommentInput(
        analysis_result_id=analysis_result_id,
        participant_id=private_result.participant_id,
        self_positions=profile.positions,
        team_aggregate=distribution,
        strength_codes=private_result.strength_codes,
        caution_codes=private_result.caution_codes,
        recommendation_codes=private_result.recommendation_codes,
        matched_rule_ids=private_result.matched_rule_ids,
    )

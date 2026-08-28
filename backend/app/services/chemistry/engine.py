"""
규칙 엔진 서비스

YAML 규칙 지식베이스를 로드하고, CanonicalProfile 집합을 기반으로
팀·페어·개인 분석을 결정론적으로 수행한다.

- LLM, LangChain, LangGraph를 import하지 않는다.
- 동일 입력에 대해 항상 동일한 결과를 보장한다 (진입 시 participant_id 정렬).
- 중립(NEUTRAL) 축은 majority/all/충돌 판정에서 decided(중립 제외) 기준으로 다룬다.

설계 기준: app/services/chemistry/DESIGN.md
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from ai.schemas import (
    AXIS_KEYS,
    NEUTRAL,
    POSITION_ENUM,
    CanonicalProfile,
    PrivateCommentInput,
    TeamCommentInput,
)

KNOWLEDGE_BASE_DIR = Path(__file__).parent.parent.parent.parent / "knowledge_base"

# ──────────────────────────────────────────────
# team_index 상수 (DESIGN.md §4 — lib/analysis/team.ts 포팅)
# ──────────────────────────────────────────────

P_TARGET = 0.65
W_BALANCE = 0.30
W_COMPLEMENT = 0.30
W_TASK_FIT = 0.25
W_CONFLICT_INV = 0.15

# 축별 상위 극(PLANNER/DRIVER/CONFRONTER/DIRECT) 목표 비율 (SPEC 부록 D, 방향 반영)
TASKFIT_UPPER_TARGET = {
    "planning": 0.65,       # PLANNER 다수
    "agency": 0.50,         # DRIVER·SUPPORTER 공존
    "conflict": 0.35,       # HARMONIZER 우세 + CONFRONTER 일부
    "communication": 0.50,  # DIRECT·TACTFUL 혼재
}

# 역할 보완을 보는 축 (conflict 제외)
COMPLEMENT_AXES = ("agency", "planning", "communication")

# 극단 편중 위험을 보는 축과 그 "강성" 극
HARD_AXES = ("conflict", "communication")
HARD_POLE = {"conflict": "CONFRONTER", "communication": "DIRECT"}

DEFAULT_GRADE_THRESHOLDS = {"HIGH": 0.90, "MID": 0.70}


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


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


def load_quests() -> dict:
    return _load_yaml("quests.yaml")


# ──────────────────────────────────────────────
# 분석 결과 데이터 클래스
# ──────────────────────────────────────────────


@dataclass
class PairResult:
    participant_a_id: str
    participant_b_id: str
    category: str  # complement | friction | alignment
    rule_id: str
    code: str
    axis: str
    priority: int = 50


@dataclass
class TeamAnalysisResult:
    """규칙 엔진의 팀 분석 결과"""

    team_grade: str  # HIGH | MID | LOW
    internal_index: float  # ★ HTTP 응답에 절대 노출 금지 (DESIGN.md §10)
    distribution: dict[str, dict[str, int]]
    pair_results: list[PairResult]  # n*(n-1)/2 전부
    team_strength_codes: list[str]
    team_caution_codes: list[str]
    matched_rule_ids: list[str]
    evidence_levels: dict[str, str]
    metrics: dict[str, float] = field(default_factory=dict)  # balance/complement/... 튜닝용

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


@dataclass
class QuestCandidate:
    """카탈로그(quests.yaml)에서 매칭된 퀘스트 후보.

    quest_code는 QuestAssignment DB row가 참조하는 안정적 식별자다.
    title/description/action은 카탈로그에 미리 작성/생성된 문구를 그대로 담는다
    (서빙 시점에는 LLM을 호출하지 않는다).
    """

    quest_code: str
    scope: str  # TEAM | PERSONAL
    title: str
    description: str
    action: str
    tags: list[str] = field(default_factory=list)


# ──────────────────────────────────────────────
# Fact 계산 (DESIGN.md §3)
# ──────────────────────────────────────────────


def compute_distribution(profiles: list[CanonicalProfile]) -> dict[str, dict[str, int]]:
    """4축 각각의 포지션 분포 {UPPER: n, LOWER: n, NEUTRAL: n}."""
    distribution: dict[str, dict[str, int]] = {}
    for axis in AXIS_KEYS:
        upper, lower = POSITION_ENUM[axis]
        counts = {upper: 0, lower: 0, NEUTRAL: 0}
        for p in profiles:
            pos = p.positions.get(axis, NEUTRAL)
            if pos in (upper, lower, NEUTRAL):
                counts[pos] += 1
            else:  # 방어: 알 수 없는 값 → NEUTRAL
                counts[NEUTRAL] += 1
        distribution[axis] = counts
    return distribution


def _decided(counts: dict[str, int], axis: str) -> int:
    """중립 제외 인원 수."""
    upper, lower = POSITION_ENUM[axis]
    return counts.get(upper, 0) + counts.get(lower, 0)


def _major_ratio(counts: dict[str, int], axis: str) -> float:
    upper, lower = POSITION_ENUM[axis]
    dec = _decided(counts, axis)
    if dec == 0:
        return 0.5
    return max(counts.get(upper, 0), counts.get(lower, 0)) / dec


def _upper_ratio(counts: dict[str, int], axis: str) -> float:
    upper, _ = POSITION_ENUM[axis]
    dec = _decided(counts, axis)
    if dec == 0:
        return 0.5
    return counts.get(upper, 0) / dec


def dominant_pole(counts: dict[str, int], axis: str) -> str | None:
    """decided 중 반대 극보다 많은 극. 동수/전원중립이면 None.

    (스켈레톤의 `_get_majority`가 전체 인원 대비 >50%를 봐서
     중립이 한 명이라도 있으면 개인 caution 규칙이 안 타던 버그 수정)
    """
    upper, lower = POSITION_ENUM[axis]
    u, l = counts.get(upper, 0), counts.get(lower, 0)
    if u > l:
        return upper
    if l > u:
        return lower
    return None


def _has_both(counts: dict[str, int], axis: str) -> bool:
    upper, lower = POSITION_ENUM[axis]
    return counts.get(upper, 0) >= 1 and counts.get(lower, 0) >= 1


# ──────────────────────────────────────────────
# 팀 index & 등급 (DESIGN.md §4, §5)
# ──────────────────────────────────────────────


def compute_team_metrics(
    distribution: dict[str, dict[str, int]],
    profiles: list[CanonicalProfile],
) -> dict[str, float]:
    """balance / complement / task_fit / conflict_risk / team_index.

    분포만의 순수 함수 — 규칙 개수에 종속되지 않는다.
    """
    # balance — 적정 다양성. 뚜렷한 인원이 있는 축만.
    bal_axes = [a for a in AXIS_KEYS if _decided(distribution[a], a) > 0]
    if bal_axes:
        balance = _mean(
            [_clamp(1 - abs(_major_ratio(distribution[a], a) - P_TARGET)) for a in bal_axes]
        )
    else:
        balance = 0.5

    # complement — 역할 보완 (agency/planning/communication)
    complement = _mean(
        [1.0 if _has_both(distribution[a], a) else 0.5 for a in COMPLEMENT_AXES]
    )

    # task_fit — 이상 분포 근접도, 방향 반영 (4축 전부)
    task_fit = _clamp(
        1
        - _mean(
            [abs(_upper_ratio(distribution[a], a) - TASKFIT_UPPER_TARGET[a]) for a in AXIS_KEYS]
        )
    )

    # conflict_risk — 강성 극(CONFRONTER/DIRECT)이 80% 초과로 쏠린 축
    risk_parts: list[float] = []
    for a in HARD_AXES:
        counts = distribution[a]
        dec = _decided(counts, a)
        if dec == 0:
            risk_parts.append(0.0)
        else:
            hard = counts.get(HARD_POLE[a], 0)
            risk_parts.append(_clamp((hard / dec - 0.8) / 0.2))
    conflict_risk = _clamp(_mean(risk_parts))

    team_index = _clamp(
        W_BALANCE * balance
        + W_COMPLEMENT * complement
        + W_TASK_FIT * task_fit
        + W_CONFLICT_INV * (1 - conflict_risk)
    )

    return {
        "balance": round(balance, 4),
        "complement": round(complement, 4),
        "task_fit": round(task_fit, 4),
        "conflict_risk": round(conflict_risk, 4),
        "team_index": round(team_index, 4),
    }


def determine_grade(index: float) -> str:
    """team_index → 3단계 등급."""
    rules_data = load_team_rules()
    thresholds = rules_data.get("grade_thresholds", DEFAULT_GRADE_THRESHOLDS)
    if index >= thresholds["HIGH"]:
        return "HIGH"
    if index >= thresholds["MID"]:
        return "MID"
    return "LOW"


# ──────────────────────────────────────────────
# 팀 규칙 매칭 (DESIGN.md §6.1)
# ──────────────────────────────────────────────


def _match_team_condition(condition: str, counts: dict[str, int], axis: str) -> bool:
    upper, lower = POSITION_ENUM[axis]
    dec = _decided(counts, axis)
    u, l = counts.get(upper, 0), counts.get(lower, 0)

    if condition == "balanced":
        return u >= 1 and l >= 1
    if condition == "majority_upper":
        return dominant_pole(counts, axis) == upper
    if condition == "majority_lower":
        return dominant_pole(counts, axis) == lower
    if condition == "all_upper":
        return dec >= 1 and l == 0
    if condition == "all_lower":
        return dec >= 1 and u == 0
    if condition == "has_upper":
        return u >= 1
    if condition == "has_lower":
        return l >= 1
    if condition == "no_upper":
        return u == 0
    if condition == "no_lower":
        return l == 0
    return False


def match_team_rules(
    distribution: dict[str, dict[str, int]],
) -> tuple[list[str], list[str], list[str], dict[str, str]]:
    """(strength_codes, caution_codes, matched_rule_ids, evidence_levels)."""
    rules = load_team_rules().get("rules", [])

    strength_codes: list[str] = []
    caution_codes: list[str] = []
    matched_rule_ids: list[str] = []
    evidence_levels: dict[str, str] = {}

    for rule in rules:
        when = rule.get("when", {})
        axis = when.get("axis")
        condition = when.get("condition")
        if not axis or not condition or axis not in distribution:
            continue
        if not _match_team_condition(condition, distribution[axis], axis):
            continue

        produces = rule.get("produces", {})
        rule_id = rule.get("rule_id", "")
        evidence = rule.get("evidence_level", "limited")
        matched_rule_ids.append(rule_id)

        if "strength_code" in produces:
            code = produces["strength_code"]
            strength_codes.append(code)
            evidence_levels[code] = evidence
        if "caution_code" in produces:
            code = produces["caution_code"]
            caution_codes.append(code)
            evidence_levels[code] = evidence

    return strength_codes, caution_codes, matched_rule_ids, evidence_levels


# ──────────────────────────────────────────────
# 페어 규칙 매칭 (DESIGN.md §6.2)
# ──────────────────────────────────────────────


def match_pair_rules(profiles: list[CanonicalProfile]) -> list[PairResult]:
    """정렬된 profiles의 모든 n*(n-1)/2 페어에 규칙 매칭."""
    rules = load_pair_rules().get("rules", [])
    results: list[PairResult] = []

    for p_a, p_b in itertools.combinations(profiles, 2):
        for rule in rules:
            when = rule.get("when", {})
            axis = when.get("axis")
            positions_required = list(when.get("positions", []))
            if not axis or not positions_required:
                continue

            pos_a = p_a.positions.get(axis, NEUTRAL)
            pos_b = p_b.positions.get(axis, NEUTRAL)
            if pos_a == NEUTRAL or pos_b == NEUTRAL:
                continue  # 중립 축은 페어 규칙 제외

            required_set = set(positions_required)
            hit = False
            if len(required_set) == 1:
                target = next(iter(required_set))
                hit = pos_a == target and pos_b == target
            elif len(required_set) == 2:
                hit = {pos_a, pos_b} == required_set

            if not hit:
                continue

            produces = rule.get("produces", {})
            code = produces.get("strength_code") or produces.get("caution_code", "")
            results.append(
                PairResult(
                    participant_a_id=p_a.participant_id,
                    participant_b_id=p_b.participant_id,
                    category=rule.get("category", ""),
                    rule_id=rule.get("rule_id", ""),
                    code=code,
                    axis=axis,
                    priority=int(rule.get("priority", 50)),
                )
            )

    return results


def _rank_pairs(pairs: list[PairResult]) -> list[PairResult]:
    return sorted(
        pairs,
        key=lambda x: (x.priority, x.rule_id, x.participant_a_id, x.participant_b_id),
    )


# ──────────────────────────────────────────────
# 개인 규칙 매칭 (DESIGN.md §6.3)
# ──────────────────────────────────────────────


def _match_private_when(
    when: dict,
    profile: CanonicalProfile,
    distribution: dict[str, dict[str, int]],
    team_size: int,
) -> bool:
    for key, expected in when.items():
        if key.startswith("self."):
            axis = key[len("self."):]
            if profile.positions.get(axis, NEUTRAL) != expected:
                return False
        elif key.startswith("team."):
            parts = key[len("team."):].split(".")
            if len(parts) != 2:
                return False
            axis, check = parts
            counts = distribution.get(axis, {})
            if check == "majority":
                if dominant_pole(counts, axis) != expected:
                    return False
            elif check == "has":
                if counts.get(expected, 0) < 1:
                    return False
            elif check == "neutral_ratio_gt":
                nr = counts.get(NEUTRAL, 0) / team_size if team_size else 0.0
                if not nr > float(expected):
                    return False
            else:
                return False
        else:
            return False
    return True


def match_private_rules(
    profile: CanonicalProfile,
    distribution: dict[str, dict[str, int]],
    team_size: int,
) -> PrivateAnalysisResult:
    rules = load_private_rules().get("rules", [])

    strength_codes: list[str] = []
    caution_codes: list[str] = []
    recommendation_codes: list[str] = []
    matched_rule_ids: list[str] = []

    for rule in rules:
        if not _match_private_when(rule.get("when", {}), profile, distribution, team_size):
            continue
        produces = rule.get("produces", {})
        matched_rule_ids.append(rule.get("rule_id", ""))
        if "strength_code" in produces:
            strength_codes.append(produces["strength_code"])
        if "caution_code" in produces:
            caution_codes.append(produces["caution_code"])
        if "recommendation_code" in produces:
            recommendation_codes.append(produces["recommendation_code"])

    return PrivateAnalysisResult(
        participant_id=profile.participant_id,
        strength_codes=list(dict.fromkeys(strength_codes)),
        caution_codes=list(dict.fromkeys(caution_codes)),
        recommendation_codes=list(dict.fromkeys(recommendation_codes)),
        matched_rule_ids=list(dict.fromkeys(matched_rule_ids)),
    )


# ──────────────────────────────────────────────
# 퀘스트 매칭 — knowledge_base/quests.yaml
#
# team_rules/private_insight_rules와 동일한 결정론적 매칭 방식을 그대로 재사용한다.
# 카탈로그 문구는 사전에(오프라인) 작성/생성되어 있으므로 여기서는 LLM을 호출하지 않는다.
# ──────────────────────────────────────────────


def _quest_item_to_candidate(scope: str, item: dict) -> QuestCandidate:
    return QuestCandidate(
        quest_code=item.get("quest_code", ""),
        scope=scope,
        title=item.get("title", ""),
        description=item.get("description", ""),
        action=item.get("action", ""),
        tags=list(item.get("tags", [])),
    )


def match_team_quests(
    distribution: dict[str, dict[str, int]],
) -> list[QuestCandidate]:
    """팀 분포에 매칭되는 팀 공유 퀘스트 후보 전체를 반환한다 (결정론적, 순서 안정).

    호출부(quests 서비스 레이어)가 이 중 N개를 골라 배정한다.
    """
    items = load_quests().get("team_quests", [])
    candidates: list[QuestCandidate] = []

    for item in items:
        when = item.get("when", {})
        axis = when.get("axis")
        condition = when.get("condition")
        if not axis or not condition or axis not in distribution:
            continue
        if not _match_team_condition(condition, distribution[axis], axis):
            continue
        candidates.append(_quest_item_to_candidate("TEAM", item))

    return candidates


def match_private_quests(
    profile: CanonicalProfile,
    distribution: dict[str, dict[str, int]],
    team_size: int,
) -> list[QuestCandidate]:
    """개인 프로필 + 팀 분포에 매칭되는 개인 퀘스트 후보 전체를 반환한다 (결정론적, 순서 안정)."""
    items = load_quests().get("personal_quests", [])
    candidates: list[QuestCandidate] = []

    for item in items:
        if not _match_private_when(item.get("when", {}), profile, distribution, team_size):
            continue
        candidates.append(_quest_item_to_candidate("PERSONAL", item))

    return candidates


def get_quest_by_code(scope: str, quest_code: str) -> QuestCandidate | None:
    """카탈로그에서 quest_code로 단건 조회한다 (API 응답 렌더링용).

    카탈로그가 갱신되면 이미 배정된 QuestAssignment도 최신 문구를 그대로 보여준다
    (문구를 DB에 복제 저장하지 않기 때문).
    """
    key = "team_quests" if scope == "TEAM" else "personal_quests"
    items = load_quests().get(key, [])
    for item in items:
        if item.get("quest_code") == quest_code:
            return _quest_item_to_candidate(scope, item)
    return None


# ──────────────────────────────────────────────
# 통합 분석 실행
# ──────────────────────────────────────────────


def run_team_analysis(profiles: list[CanonicalProfile]) -> TeamAnalysisResult:
    """전체 팀 분석. 입력 순서와 무관하게 결정론적."""
    profiles = sorted(profiles, key=lambda p: p.participant_id)

    distribution = compute_distribution(profiles)
    strength_codes, caution_codes, team_rule_ids, evidence_levels = match_team_rules(distribution)

    pair_results = match_pair_rules(profiles)
    pair_rule_ids = [pr.rule_id for pr in pair_results]

    metrics = compute_team_metrics(distribution, profiles)
    team_index = metrics["team_index"]
    team_grade = determine_grade(team_index)

    complement_pairs = _rank_pairs([pr for pr in pair_results if pr.category == "complement"])[:3]
    caution_pairs = _rank_pairs(
        [pr for pr in pair_results if pr.category in ("friction", "alignment")]
    )[:3]

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
        metrics=metrics,
        top_complement_pairs=complement_pairs,
        top_caution_pairs=caution_pairs,
    )


def run_private_analysis(
    profile: CanonicalProfile,
    distribution: dict[str, dict[str, int]],
    team_size: int,
) -> PrivateAnalysisResult:
    return match_private_rules(profile, distribution, team_size)


# ──────────────────────────────────────────────
# AI 입력 DTO 구성 (allow-list = 코드 payload 그 자체)
# ──────────────────────────────────────────────


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
    # ★ analysis.internal_index 는 절대 넣지 않는다 (DESIGN.md §10)


def build_private_comment_input(
    private_result: PrivateAnalysisResult,
    analysis_result_id: str,
    distribution: dict[str, dict[str, int]],
    profile: CanonicalProfile,
) -> PrivateCommentInput:
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

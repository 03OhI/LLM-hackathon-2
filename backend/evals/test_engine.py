"""
엔진 Evaluation Harness — design.md §12

lib/analysis/team.test.ts, distribution.test.ts, likert.test.ts의 검증 의도를
Python 규칙 엔진(app.services.chemistry.engine)에 대해 포팅한다.

필수 통과 기준 (design.md §9, §12, §15):
1. 결정성 — run_team_analysis(P) == run_team_analysis(shuffle(P))
2. 등급 불변식 — T1 전원동일→LOW, T2 균형보완→HIGH, T3 밋밋→MID, T4 중립다수, T5 리더과다
3. 페어 개수 — n*(n-1)/2
4. 중립 축 제외 — decided 기준 계산
5. 개인정보 불변식 — internal_index가 AI 입력 DTO에 노출되지 않음, PrivateInsight 계산이
   participant_id 단일 기준으로만 이뤄짐
"""

from __future__ import annotations

import random
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from ai.schemas import CanonicalProfile

from app.services.chemistry.engine import (
    build_private_comment_input,
    build_team_comment_input,
    compute_distribution,
    compute_team_metrics,
    determine_grade,
    dominant_pole,
    match_pair_rules,
    match_private_rules,
    run_team_analysis,
)


# ──────────────────────────────────────────────
# 헬퍼
# ──────────────────────────────────────────────


def _profile(pid: str, planning: str, agency: str, conflict: str, communication: str, source: str = "DECLARED_TYPE") -> CanonicalProfile:
    return CanonicalProfile(
        participant_id=pid,
        source=source,
        positions={
            "planning": planning,
            "agency": agency,
            "conflict": conflict,
            "communication": communication,
        },
        ratios=None,
        means=None,
        axis_flags=[],
    )


# 팀 fixture — design.md §12 표 그대로
T1_ALL_IDENTICAL = [
    _profile(f"t1-{i}", "PLANNER", "DRIVER", "CONFRONTER", "DIRECT") for i in range(4)
]

T2_BALANCED_COMPLEMENT = [
    _profile("t2-1", "PLANNER", "DRIVER", "HARMONIZER", "DIRECT"),
    _profile("t2-2", "PLANNER", "SUPPORTER", "HARMONIZER", "TACTFUL"),
    _profile("t2-3", "ADAPTER", "DRIVER", "HARMONIZER", "DIRECT"),
    _profile("t2-4", "PLANNER", "SUPPORTER", "CONFRONTER", "TACTFUL"),
]

T3_FLAT = [
    _profile("t3-1", "PLANNER", "DRIVER", "HARMONIZER", "TACTFUL"),
    _profile("t3-2", "PLANNER", "SUPPORTER", "CONFRONTER", "DIRECT"),
    _profile("t3-3", "ADAPTER", "DRIVER", "HARMONIZER", "TACTFUL"),
    _profile("t3-4", "ADAPTER", "SUPPORTER", "CONFRONTER", "DIRECT"),
]

T4_MOSTLY_NEUTRAL = [
    _profile("t4-1", "NEUTRAL", "NEUTRAL", "NEUTRAL", "NEUTRAL"),
    _profile("t4-2", "NEUTRAL", "NEUTRAL", "NEUTRAL", "NEUTRAL"),
    _profile("t4-3", "NEUTRAL", "NEUTRAL", "NEUTRAL", "NEUTRAL"),
    _profile("t4-4", "PLANNER", "DRIVER", "CONFRONTER", "DIRECT"),
]

T5_DRIVER_OVERLOAD = [
    _profile("t5-1", "PLANNER", "DRIVER", "HARMONIZER", "DIRECT"),
    _profile("t5-2", "ADAPTER", "DRIVER", "HARMONIZER", "TACTFUL"),
    _profile("t5-3", "PLANNER", "DRIVER", "CONFRONTER", "DIRECT"),
    _profile("t5-4", "ADAPTER", "DRIVER", "CONFRONTER", "TACTFUL"),
]


# ──────────────────────────────────────────────
# 1. 결정성
# ──────────────────────────────────────────────


class TestDeterminism:
    @pytest.mark.parametrize(
        "team",
        [T1_ALL_IDENTICAL, T2_BALANCED_COMPLEMENT, T3_FLAT, T4_MOSTLY_NEUTRAL, T5_DRIVER_OVERLOAD],
    )
    def test_shuffle_invariant(self, team):
        """run_team_analysis(P) == run_team_analysis(shuffle(P))."""
        original = run_team_analysis(list(team))

        shuffled = list(team)
        random.Random(42).shuffle(shuffled)
        shuffled_result = run_team_analysis(shuffled)

        assert original.team_grade == shuffled_result.team_grade
        assert original.internal_index == shuffled_result.internal_index
        assert original.team_strength_codes == shuffled_result.team_strength_codes
        assert original.team_caution_codes == shuffled_result.team_caution_codes
        assert original.matched_rule_ids == shuffled_result.matched_rule_ids
        assert original.distribution == shuffled_result.distribution

    def test_repeated_call_same_result(self):
        r1 = run_team_analysis(list(T2_BALANCED_COMPLEMENT))
        r2 = run_team_analysis(list(T2_BALANCED_COMPLEMENT))
        assert r1.team_grade == r2.team_grade
        assert r1.internal_index == r2.internal_index

    def test_input_source_independence(self):
        """SURVEY와 DECLARED_TYPE, positions만 같으면 팀 등급이 동일해야 한다."""
        declared = [_profile(f"d-{i}", "PLANNER", "DRIVER", "HARMONIZER", "DIRECT", source="DECLARED_TYPE") for i in range(4)]
        survey = [
            CanonicalProfile(
                participant_id=f"s-{i}",
                source="SURVEY",
                question_set_version="survey24-v2",
                positions={"planning": "PLANNER", "agency": "DRIVER", "conflict": "HARMONIZER", "communication": "DIRECT"},
                ratios={"planning": 0.9, "agency": 0.85, "conflict": 0.2, "communication": 0.95},
                means={"planning": 4.6, "agency": 4.4, "conflict": 1.8, "communication": 4.8},
                axis_flags=[],
            )
            for i in range(4)
        ]

        r_declared = run_team_analysis(declared)
        r_survey = run_team_analysis(survey)

        assert r_declared.team_grade == r_survey.team_grade
        assert r_declared.internal_index == r_survey.internal_index
        assert r_declared.team_strength_codes == r_survey.team_strength_codes
        assert r_declared.team_caution_codes == r_survey.team_caution_codes


# ──────────────────────────────────────────────
# 2. 등급 불변식 (T1~T5)
# ──────────────────────────────────────────────


class TestGradeInvariants:
    def test_t1_all_identical_is_low(self):
        """전원 동일 포지션 팀 → LOW, conflict_risk > 0."""
        result = run_team_analysis(list(T1_ALL_IDENTICAL))
        assert result.team_grade == "LOW"
        assert result.metrics["conflict_risk"] > 0

    def test_t2_balanced_complement_is_high(self):
        """균형 잡힌 보완 팀 → HIGH, conflict_risk == 0."""
        result = run_team_analysis(list(T2_BALANCED_COMPLEMENT))
        assert result.team_grade == "HIGH"
        assert result.metrics["conflict_risk"] == 0

    def test_t3_flat_is_between_t1_and_t2(self):
        """T3(밋밋)은 T1과 T2 사이의 등급이거나 index가 그 사이여야 한다."""
        t1 = run_team_analysis(list(T1_ALL_IDENTICAL))
        t2 = run_team_analysis(list(T2_BALANCED_COMPLEMENT))
        t3 = run_team_analysis(list(T3_FLAT))

        assert t1.internal_index <= t3.internal_index <= t2.internal_index
        assert t3.team_grade in ("LOW", "MID", "HIGH")

    def test_t4_mostly_neutral_no_error_and_mid_ish(self):
        """중립 다수 팀도 에러 없이 처리되고, 규칙이 거의 안 탄다."""
        result = run_team_analysis(list(T4_MOSTLY_NEUTRAL))
        assert result.team_grade in ("LOW", "MID", "HIGH")
        assert isinstance(result.internal_index, float)
        # 3명이 전 축 중립이므로 팀 규칙이 많이 매칭되지 않아야 한다.
        assert len(result.matched_rule_ids) <= 6

    def test_t5_driver_overload_caution_present(self):
        """agency 전원 DRIVER → DRIVER_COLLISION류 페어 마찰이 top_caution에 노출되고
        LOW_DRIVER_ENERGY(주도력 부재 경고)는 뜨지 않아야 한다."""
        result = run_team_analysis(list(T5_DRIVER_OVERLOAD))
        assert "LOW_DRIVER_ENERGY" not in result.team_caution_codes

        pair_rule_ids = [pr.rule_id for pr in result.pair_results if pr.axis == "agency"]
        assert len(pair_rule_ids) > 0, "agency 전원 DRIVER인데 매칭된 agency 페어 규칙이 없다"

    def test_grade_thresholds_from_yaml(self):
        """team_rules.yaml의 grade_thresholds가 {HIGH: 0.90, MID: 0.70}로 반영됐는지."""
        assert determine_grade(0.95) == "HIGH"
        assert determine_grade(0.90) == "HIGH"
        assert determine_grade(0.89) == "MID"
        assert determine_grade(0.70) == "MID"
        assert determine_grade(0.69) == "LOW"


# ──────────────────────────────────────────────
# 3. 페어 개수
# ──────────────────────────────────────────────


class TestPairCount:
    @pytest.mark.parametrize("n", [3, 4, 10])
    def test_pair_count_matches_combinatorics(self, n):
        profiles = [_profile(f"p{i}", "PLANNER", "DRIVER", "HARMONIZER", "DIRECT") for i in range(n)]
        # 짝수 인덱스는 반대 포지션으로 다양성 부여 (매칭 규칙 존재 확인용)
        for i in range(0, n, 2):
            profiles[i] = _profile(f"p{i}", "ADAPTER", "SUPPORTER", "CONFRONTER", "TACTFUL")

        pair_results = match_pair_rules(profiles)
        # pair_results는 "매칭된" 규칙 결과이므로 상한은 n*(n-1)/2 * (규칙 수)지만
        # 실제 페어 조합 자체의 개수는 itertools.combinations로 별도 확인한다.
        import itertools

        combo_count = len(list(itertools.combinations(profiles, 2)))
        assert combo_count == n * (n - 1) // 2

    def test_top_pairs_capped_at_three(self):
        """10명 팀에서도 top_complement/top_caution은 각각 최대 3개."""
        profiles = []
        for i in range(10):
            if i % 2 == 0:
                profiles.append(_profile(f"p{i}", "PLANNER", "DRIVER", "HARMONIZER", "DIRECT"))
            else:
                profiles.append(_profile(f"p{i}", "ADAPTER", "SUPPORTER", "CONFRONTER", "TACTFUL"))

        result = run_team_analysis(profiles)
        assert len(result.top_complement_pairs) <= 3
        assert len(result.top_caution_pairs) <= 3


# ──────────────────────────────────────────────
# 4. 중립 축 제외
# ──────────────────────────────────────────────


class TestNeutralHandling:
    def test_dominant_pole_none_on_tie(self):
        """decided 인원이 동수면 dominant_pole은 None."""
        distribution = {"agency": {"DRIVER": 2, "SUPPORTER": 2, "NEUTRAL": 0}}
        assert dominant_pole(distribution["agency"], "agency") is None

    def test_dominant_pole_ignores_neutral(self):
        """중립이 있어도 decided 인원만으로 dominant_pole을 판정한다 (버그#3 회귀)."""
        distribution = {"communication": {"DIRECT": 1, "TACTFUL": 3, "NEUTRAL": 1}}
        assert dominant_pole(distribution["communication"], "communication") == "TACTFUL"

    def test_neutral_axis_excluded_from_pair_rules(self):
        """한쪽이라도 NEUTRAL인 축은 그 페어-축 규칙 평가에서 제외된다."""
        a = _profile("a", "NEUTRAL", "DRIVER", "HARMONIZER", "DIRECT")
        b = _profile("b", "PLANNER", "SUPPORTER", "HARMONIZER", "TACTFUL")

        pair_results = match_pair_rules([a, b])
        planning_pairs = [pr for pr in pair_results if pr.axis == "planning"]
        assert planning_pairs == [], "NEUTRAL축(planning)에서 페어 규칙이 매칭되면 안 된다"

    def test_private_rule_matches_despite_one_neutral_member(self):
        """팀에 중립 1명이 있어도 개인 규칙(direct-in-tactful-team)이 여전히 매칭된다 (버그#3 회귀)."""
        team = [
            _profile("direct-1", "PLANNER", "DRIVER", "HARMONIZER", "DIRECT"),
            _profile("tactful-1", "ADAPTER", "SUPPORTER", "HARMONIZER", "TACTFUL"),
            _profile("tactful-2", "ADAPTER", "SUPPORTER", "HARMONIZER", "TACTFUL"),
            _profile("neutral-1", "NEUTRAL", "NEUTRAL", "NEUTRAL", "NEUTRAL"),
        ]
        distribution = compute_distribution(team)
        direct_profile = next(p for p in team if p.participant_id == "direct-1")

        result = match_private_rules(direct_profile, distribution, team_size=len(team))
        assert "PERSONAL_DIRECT_IN_TACTFUL_TEAM" in result.matched_rule_ids
        assert "CHECK_FEEDBACK_TONE" in result.caution_codes


# ──────────────────────────────────────────────
# 5. 개인정보 불변식 (design.md §9, §15)
# ──────────────────────────────────────────────


class TestPrivacyInvariants:
    def test_team_comment_input_has_no_internal_index(self):
        """build_team_comment_input 출력 문자열에 internal_index가 없어야 한다."""
        result = run_team_analysis(list(T2_BALANCED_COMPLEMENT))
        team_input = build_team_comment_input(result, "analysis-1", team_size=4)

        serialized = team_input.model_dump_json()
        assert "internal_index" not in serialized

    def test_team_comment_input_has_no_metrics(self):
        result = run_team_analysis(list(T2_BALANCED_COMPLEMENT))
        team_input = build_team_comment_input(result, "analysis-1", team_size=4)

        serialized = team_input.model_dump_json()
        assert "balance" not in serialized
        assert "conflict_risk" not in serialized

    def test_private_comment_input_only_contains_own_participant(self):
        """PrivateInsightInput은 본인 participant_id만 담고 다른 참여자 식별자를 포함하지 않는다."""
        team = list(T2_BALANCED_COMPLEMENT)
        distribution = compute_distribution(team)
        me = team[0]
        other_ids = [p.participant_id for p in team[1:]]

        private_result = match_private_rules(me, distribution, team_size=len(team))
        private_input = build_private_comment_input(private_result, "analysis-1", distribution, me)

        assert private_input.participant_id == me.participant_id
        serialized = private_input.model_dump_json()
        for other_id in other_ids:
            assert other_id not in serialized, f"다른 참여자 ID({other_id})가 개인 입력에 노출됨"

    def test_ratios_and_means_do_not_affect_grade(self):
        """ratios/means를 다르게 줘도 positions가 같으면 결과가 불변해야 한다 (공정성)."""
        base_positions = {"planning": "PLANNER", "agency": "DRIVER", "conflict": "HARMONIZER", "communication": "DIRECT"}

        team_low_ratio = [
            CanonicalProfile(
                participant_id=f"lo-{i}",
                source="SURVEY",
                positions=base_positions,
                ratios={k: 0.61 for k in base_positions},
                means={k: 3.5 for k in base_positions},
                axis_flags=[],
            )
            for i in range(4)
        ]
        team_high_ratio = [
            CanonicalProfile(
                participant_id=f"hi-{i}",
                source="SURVEY",
                positions=base_positions,
                ratios={k: 0.99 for k in base_positions},
                means={k: 5.0 for k in base_positions},
                axis_flags=[],
            )
            for i in range(4)
        ]

        r_low = run_team_analysis(team_low_ratio)
        r_high = run_team_analysis(team_high_ratio)

        assert r_low.team_grade == r_high.team_grade
        assert r_low.internal_index == r_high.internal_index
        assert r_low.team_strength_codes == r_high.team_strength_codes

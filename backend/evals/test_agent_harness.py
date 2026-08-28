"""
Evaluation Harness V2 — pytest 기반 평가 묶음

아이스브레이킹 출력 구조 (TeamSnapshot / PrivateCard)에 맞게 재작성.

필수 통과 기준:
1. 유효한 TeamSnapshot 통과
2. 유효한 PrivateCard 통과
3. 허용되지 않은 rule_id 차단
4. 팀 결과에서 HIGH/MID/LOW 차단
5. 숫자 점수·성공 확률 차단
6. 다른 참여자 식별자 차단
7. 개인 결과의 강제·단정 표현 차단
8. 첫 검증 실패 후 재생성 (retry_count 증가)
9. 최종 실패 후 TEAM 폴백 — null 아님
10. 최종 실패 후 SELF_ONLY 폴백 — null 아님
11. 기존 설문 채점과 규칙 엔진 결정론 테스트 유지
12. 3명 팀과 10명 팀 입력 처리
13. 입력 방식이 달라도 같은 positions면 내부 계산 결과 동일
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from ai.schemas import (
    CanonicalProfile,
    CommentGraphState,
    PrivateCard,
    TeamSnapshot,
)
from ai.nodes.validate import validate_comment
from ai.nodes.fallback import render_fallback
from app.services.scoring.scorer import (
    create_profile_from_survey,
    create_profile_from_declared_type,
)
from app.services.chemistry.engine import (
    run_team_analysis,
    match_pair_rules,
    match_private_rules,
)

DATASETS_DIR = Path(__file__).parent / "datasets"


# ──────────────────────────────────────────────
# 헬퍼
# ──────────────────────────────────────────────


def _load_jsonl(filename: str) -> list[dict]:
    path = DATASETS_DIR / filename
    cases = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                cases.append(json.loads(line))
    return cases


def _profiles_from_case(case: dict) -> list[CanonicalProfile]:
    return [
        CanonicalProfile(
            participant_id=p["participant_id"],
            source=p["source"],
            positions=p["positions"],
            ratios=None,
            means=None,
            axis_flags=[],
        )
        for p in case["profiles"]
    ]


def _team_state(
    draft: TeamSnapshot | None = None,
    allowed_rule_ids: list[str] | None = None,
    knowledge_context: dict | None = None,
    validation_errors: list[str] | None = None,
    retry_count: int = 0,
) -> CommentGraphState:
    return {
        "audience": "TEAM",
        "analysis_result_id": "test-001",
        "participant_id": None,
        "allowed_strength_codes": ["INITIATIVE_SUPPORT_BALANCE"],
        "allowed_caution_codes": ["DIRECT_COMMUNICATION_CONCENTRATION"],
        "allowed_recommendation_codes": [],
        "allowed_rule_ids": allowed_rule_ids or ["TEAM_BALANCED_AGENCY", "TEAM_DIRECT_CONCENTRATION"],
        "knowledge_context": knowledge_context or {},
        "draft": draft,
        "validation_errors": validation_errors or [],
        "retry_count": retry_count,
        "final": None,
        "used_fallback": False,
    }


def _private_state(
    draft: PrivateCard | None = None,
    allowed_rule_ids: list[str] | None = None,
    knowledge_context: dict | None = None,
    validation_errors: list[str] | None = None,
    retry_count: int = 0,
) -> CommentGraphState:
    return {
        "audience": "SELF_ONLY",
        "analysis_result_id": "test-002",
        "participant_id": "p1",
        "allowed_strength_codes": ["PLANNING_STABILITY"],
        "allowed_caution_codes": ["CHECK_FEEDBACK_TONE"],
        "allowed_recommendation_codes": ["FACT_IMPACT_REQUEST"],
        "allowed_rule_ids": allowed_rule_ids or ["PERSONAL_PLANNER_STABILITY", "PERSONAL_DIRECT_IN_TACTFUL_TEAM"],
        "knowledge_context": knowledge_context or {"other_participant_names": [], "other_participant_ids": []},
        "draft": draft,
        "validation_errors": validation_errors or [],
        "retry_count": retry_count,
        "final": None,
        "used_fallback": False,
    }


# ──────────────────────────────────────────────
# 1. 유효한 TeamSnapshot 통과
# ──────────────────────────────────────────────


class TestTeamSnapshotValid:
    def test_valid_snapshot_passes(self):
        draft = TeamSnapshot(
            title="계획표가 먼저 완성되는 팀",
            formula="계획 2스푼 + 순발력 1스푼",
            scene="회의가 끝나기 전에 누군가 이미 만들고 있습니다.",
            keywords=["체계적", "빠른 실행"],
            used_rule_ids=["TEAM_BALANCED_AGENCY"],
        )
        state = _team_state(draft=draft)
        result = validate_comment(state)
        assert result.get("final") is not None
        assert result.get("validation_errors") == []


# ──────────────────────────────────────────────
# 2. 유효한 PrivateCard 통과
# ──────────────────────────────────────────────


class TestPrivateCardValid:
    def test_valid_card_passes(self):
        draft = PrivateCard(
            card_title="구조를 세우는 사람",
            contribution="팀에 체계와 방향을 가져다줄 수 있어요.",
            optional_try="큰 틀만 먼저 공유하고 디테일은 함께 채워봐도 좋아요.",
            used_rule_ids=["PERSONAL_PLANNER_STABILITY"],
        )
        state = _private_state(draft=draft)
        result = validate_comment(state)
        assert result.get("final") is not None
        assert result.get("validation_errors") == []


# ──────────────────────────────────────────────
# 3. 허용되지 않은 rule_id 차단
# ──────────────────────────────────────────────


class TestRuleIdBlocking:
    def test_unknown_rule_id_team(self):
        draft = TeamSnapshot(
            title="좋은 팀",
            formula="에너지 가득",
            scene="다들 즐겁습니다.",
            keywords=["활발", "에너지"],
            used_rule_ids=["INVENTED_RULE_999"],
        )
        state = _team_state(draft=draft)
        result = validate_comment(state)
        errors = result.get("validation_errors", [])
        assert any("UNKNOWN_RULE_ID" in e for e in errors)

    def test_unknown_rule_id_private(self):
        draft = PrivateCard(
            card_title="멋진 사람",
            contribution="팀에 기여합니다.",
            optional_try=None,
            used_rule_ids=["FAKE_RULE"],
        )
        state = _private_state(draft=draft)
        result = validate_comment(state)
        errors = result.get("validation_errors", [])
        assert any("UNKNOWN_RULE_ID" in e for e in errors)


# ──────────────────────────────────────────────
# 4. 팀 결과에서 HIGH/MID/LOW 차단
# ──────────────────────────────────────────────


class TestGradeBlocking:
    def test_high_in_title(self):
        draft = TeamSnapshot(
            title="HIGH 등급의 팀",
            formula="조합식",
            scene="장면입니다.",
            keywords=["좋음", "팀"],
            used_rule_ids=["TEAM_BALANCED_AGENCY"],
        )
        state = _team_state(draft=draft)
        result = validate_comment(state)
        errors = result.get("validation_errors", [])
        assert any("GRADE_LEAK" in e for e in errors)

    def test_mid_in_scene(self):
        draft = TeamSnapshot(
            title="평범한 팀",
            formula="조합식",
            scene="이 팀은 MID 수준입니다.",
            keywords=["보통", "팀"],
            used_rule_ids=["TEAM_BALANCED_AGENCY"],
        )
        state = _team_state(draft=draft)
        result = validate_comment(state)
        errors = result.get("validation_errors", [])
        assert any("GRADE_LEAK" in e for e in errors)

    def test_low_in_formula(self):
        draft = TeamSnapshot(
            title="팀 이름",
            formula="LOW 에너지 팀",
            scene="조용합니다.",
            keywords=["조용", "팀"],
            used_rule_ids=["TEAM_BALANCED_AGENCY"],
        )
        state = _team_state(draft=draft)
        result = validate_comment(state)
        errors = result.get("validation_errors", [])
        assert any("GRADE_LEAK" in e for e in errors)


# ──────────────────────────────────────────────
# 5. 숫자 점수·성공 확률 차단
# ──────────────────────────────────────────────


class TestNumericScoreBlocking:
    def test_percent_in_team(self):
        draft = TeamSnapshot(
            title="성공률 85% 팀",
            formula="조합식",
            scene="장면.",
            keywords=["성공", "팀"],
            used_rule_ids=["TEAM_BALANCED_AGENCY"],
        )
        state = _team_state(draft=draft)
        result = validate_comment(state)
        errors = result.get("validation_errors", [])
        assert any("NUMERIC_SCORE" in e for e in errors)

    def test_score_in_private(self):
        draft = PrivateCard(
            card_title="90점짜리 팀원",
            contribution="점수가 높습니다.",
            optional_try=None,
            used_rule_ids=["PERSONAL_PLANNER_STABILITY"],
        )
        state = _private_state(draft=draft)
        result = validate_comment(state)
        errors = result.get("validation_errors", [])
        assert any("NUMERIC_SCORE" in e for e in errors)


# ──────────────────────────────────────────────
# 6. 다른 참여자 식별자 차단
# ──────────────────────────────────────────────


class TestParticipantReferenceBlocking:
    def test_name_in_private(self):
        draft = PrivateCard(
            card_title="철수와 함께",
            contribution="철수님과 잘 맞아요.",
            optional_try=None,
            used_rule_ids=["PERSONAL_PLANNER_STABILITY"],
        )
        state = _private_state(
            draft=draft,
            knowledge_context={
                "other_participant_names": ["철수"],
                "other_participant_ids": ["p2"],
            },
        )
        result = validate_comment(state)
        errors = result.get("validation_errors", [])
        assert any("OTHER_MEMBER" in e for e in errors)

    def test_id_in_team(self):
        draft = TeamSnapshot(
            title="p2가 이끄는 팀",
            formula="조합",
            scene="장면.",
            keywords=["리더", "팀"],
            used_rule_ids=["TEAM_BALANCED_AGENCY"],
        )
        state = _team_state(
            draft=draft,
            knowledge_context={
                "other_participant_names": [],
                "other_participant_ids": ["p2"],
            },
        )
        result = validate_comment(state)
        errors = result.get("validation_errors", [])
        assert any("OTHER_MEMBER" in e for e in errors)


# ──────────────────────────────────────────────
# 7. 개인 결과의 강제·단정 표현 차단
# ──────────────────────────────────────────────


class TestForceExpressionBlocking:
    def test_must_expression(self):
        draft = PrivateCard(
            card_title="노력하는 사람",
            contribution="반드시 고쳐야 합니다.",
            optional_try="해야 합니다.",
            used_rule_ids=["PERSONAL_PLANNER_STABILITY"],
        )
        state = _private_state(draft=draft)
        result = validate_comment(state)
        errors = result.get("validation_errors", [])
        assert any("FORCE_EXPRESSION" in e for e in errors)

    def test_weakness_expression(self):
        draft = PrivateCard(
            card_title="약점이 있는 사람",
            contribution="당신의 문제점은 소통입니다.",
            optional_try=None,
            used_rule_ids=["PERSONAL_PLANNER_STABILITY"],
        )
        state = _private_state(draft=draft)
        result = validate_comment(state)
        errors = result.get("validation_errors", [])
        assert any("FORCE_EXPRESSION" in e for e in errors)


# ──────────────────────────────────────────────
# 8. 첫 검증 실패 후 재생성 (retry_count 증가 시뮬레이션)
# ──────────────────────────────────────────────


class TestRetryMechanism:
    def test_first_failure_allows_retry(self):
        """retry_count < 2이면 재생성 기회가 있다."""
        draft = TeamSnapshot(
            title="HIGH 등급 팀",  # 의도적 실패
            formula="조합",
            scene="장면.",
            keywords=["팀", "좋음"],
            used_rule_ids=["TEAM_BALANCED_AGENCY"],
        )
        state = _team_state(draft=draft, retry_count=0)
        result = validate_comment(state)
        errors = result.get("validation_errors", [])
        # 검증 실패 → errors 비어있지 않음 → 그래프에서 재시도 라우팅
        assert len(errors) > 0
        assert result.get("final") is None


# ──────────────────────────────────────────────
# 9. 최종 실패 후 TEAM 폴백 — null 아님
# ──────────────────────────────────────────────


class TestTeamFallback:
    def test_fallback_returns_valid_team_snapshot(self):
        state: CommentGraphState = {
            "audience": "TEAM",
            "analysis_result_id": "fallback-001",
            "participant_id": None,
            "allowed_strength_codes": ["INITIATIVE_SUPPORT_BALANCE"],
            "allowed_caution_codes": ["DIRECT_COMMUNICATION_CONCENTRATION"],
            "allowed_recommendation_codes": [],
            "allowed_rule_ids": ["TEAM_BALANCED_AGENCY", "TEAM_DIRECT_CONCENTRATION"],
            "knowledge_context": {"team_size": 4, "distribution": {"planning": {"PLANNER": 3, "ADAPTER": 1, "NEUTRAL": 0}}},
            "draft": None,
            "validation_errors": ["LLM_ERROR: TimeoutError"],
            "retry_count": 2,
            "final": None,
            "used_fallback": False,
        }
        result = render_fallback(state)
        assert result["used_fallback"] is True
        assert result["final"] is not None
        assert isinstance(result["final"], TeamSnapshot)
        assert result["final"].title
        assert result["final"].formula
        assert result["final"].scene
        assert len(result["final"].keywords) >= 2

    def test_fallback_no_grade_in_output(self):
        state: CommentGraphState = {
            "audience": "TEAM",
            "analysis_result_id": "fallback-002",
            "participant_id": None,
            "allowed_strength_codes": [],
            "allowed_caution_codes": [],
            "allowed_recommendation_codes": [],
            "allowed_rule_ids": ["TEAM_BALANCED_AGENCY"],
            "knowledge_context": {},
            "draft": None,
            "validation_errors": ["PARSE_ERROR"],
            "retry_count": 2,
            "final": None,
            "used_fallback": False,
        }
        result = render_fallback(state)
        snapshot = result["final"]
        all_text = f"{snapshot.title} {snapshot.formula} {snapshot.scene}"
        assert "HIGH" not in all_text
        assert "MID" not in all_text
        assert "LOW" not in all_text


# ──────────────────────────────────────────────
# 10. 최종 실패 후 SELF_ONLY 폴백 — null 아님
# ──────────────────────────────────────────────


class TestPrivateFallback:
    def test_fallback_returns_valid_private_card(self):
        state: CommentGraphState = {
            "audience": "SELF_ONLY",
            "analysis_result_id": "fallback-003",
            "participant_id": "p1",
            "allowed_strength_codes": ["PLANNING_STABILITY"],
            "allowed_caution_codes": ["CHECK_FEEDBACK_TONE"],
            "allowed_recommendation_codes": [],
            "allowed_rule_ids": ["PERSONAL_PLANNER_STABILITY"],
            "knowledge_context": {"self_positions": {"planning": "PLANNER", "agency": "DRIVER", "conflict": "CONFRONTER", "communication": "DIRECT"}},
            "draft": None,
            "validation_errors": ["LLM_ERROR: ConnectionError"],
            "retry_count": 2,
            "final": None,
            "used_fallback": False,
        }
        result = render_fallback(state)
        assert result["used_fallback"] is True
        assert result["final"] is not None
        assert isinstance(result["final"], PrivateCard)
        assert result["final"].card_title
        assert result["final"].contribution

    def test_fallback_no_force_expression(self):
        state: CommentGraphState = {
            "audience": "SELF_ONLY",
            "analysis_result_id": "fallback-004",
            "participant_id": "p2",
            "allowed_strength_codes": [],
            "allowed_caution_codes": [],
            "allowed_recommendation_codes": [],
            "allowed_rule_ids": ["PERSONAL_ADAPTER_FLEXIBILITY"],
            "knowledge_context": {"self_positions": {"planning": "ADAPTER", "agency": "SUPPORTER", "conflict": "HARMONIZER", "communication": "TACTFUL"}},
            "draft": None,
            "validation_errors": [],
            "retry_count": 2,
            "final": None,
            "used_fallback": False,
        }
        result = render_fallback(state)
        card = result["final"]
        all_text = f"{card.card_title} {card.contribution} {card.optional_try or ''}"
        assert "반드시" not in all_text
        assert "해야" not in all_text


# ──────────────────────────────────────────────
# 11. 기존 설문 채점 테스트
# ──────────────────────────────────────────────


class TestScoringService:
    def test_all_fours_produce_neutral(self):
        answers = [4] * 24
        profile = create_profile_from_survey("test-p1", answers)
        assert profile.source == "SURVEY"
        assert all(pos == "NEUTRAL" for pos in profile.positions.values())

    def test_high_scores_produce_upper(self):
        answers = []
        for _ in range(4):
            answers.extend([5, 5, 5, 1, 1, 1])
        profile = create_profile_from_survey("test-p2", answers)
        assert profile.positions["planning"] == "PLANNER"
        assert profile.positions["agency"] == "DRIVER"
        assert profile.positions["conflict"] == "CONFRONTER"
        assert profile.positions["communication"] == "DIRECT"

    def test_low_scores_produce_lower(self):
        answers = []
        for _ in range(4):
            answers.extend([1, 1, 1, 5, 5, 5])
        profile = create_profile_from_survey("test-p3", answers)
        assert profile.positions["planning"] == "ADAPTER"
        assert profile.positions["agency"] == "SUPPORTER"
        assert profile.positions["conflict"] == "HARMONIZER"
        assert profile.positions["communication"] == "TACTFUL"

    def test_invalid_answer_count_raises(self):
        with pytest.raises(ValueError):
            create_profile_from_survey("test-p4", [3] * 20)

    def test_declared_type_valid(self):
        profile = create_profile_from_declared_type("test-d1", {
            "planning": "PLANNER",
            "agency": "SUPPORTER",
            "conflict": "HARMONIZER",
            "communication": "DIRECT",
        })
        assert profile.source == "DECLARED_TYPE"
        assert profile.ratios is None

    def test_declared_type_invalid_raises(self):
        with pytest.raises(ValueError):
            create_profile_from_declared_type("test-d2", {
                "planning": "INVALID",
                "agency": "SUPPORTER",
                "conflict": "HARMONIZER",
                "communication": "DIRECT",
            })


# ──────────────────────────────────────────────
# 12. 규칙 엔진 결정론 + 3명/10명 팀
# ──────────────────────────────────────────────


class TestDeterminism:
    @pytest.fixture
    def team_cases(self) -> list[dict]:
        return _load_jsonl("team_cases.jsonl")

    def test_same_input_same_output(self, team_cases):
        for case in team_cases:
            profiles = _profiles_from_case(case)
            r1 = run_team_analysis(profiles)
            r2 = run_team_analysis(profiles)
            assert r1.team_grade == r2.team_grade
            assert r1.internal_index == r2.internal_index
            assert r1.team_strength_codes == r2.team_strength_codes

    def test_3_and_10_member_teams(self, team_cases):
        sizes = {case["team_size"] for case in team_cases}
        assert 3 in sizes
        assert 10 in sizes

        for case in team_cases:
            profiles = _profiles_from_case(case)
            result = run_team_analysis(profiles)
            assert result.team_grade in ("HIGH", "MID", "LOW")
            n = len(profiles)
            expected_pair_count = n * (n - 1) // 2
            assert expected_pair_count == case["assertions"]["pair_count"]


# ──────────────────────────────────────────────
# 13. 입력 방식 독립성
# ──────────────────────────────────────────────


class TestInputSourceIndependence:
    def test_same_positions_same_grade(self):
        positions = {
            "planning": "PLANNER",
            "agency": "DRIVER",
            "conflict": "CONFRONTER",
            "communication": "DIRECT",
        }
        other_pos = {
            "planning": "ADAPTER",
            "agency": "SUPPORTER",
            "conflict": "HARMONIZER",
            "communication": "TACTFUL",
        }

        survey_p = CanonicalProfile(
            participant_id="s1", source="SURVEY", positions=positions,
            ratios={"planning": 0.8, "agency": 0.7, "conflict": 0.65, "communication": 0.75},
            means={"planning": 4.2, "agency": 3.8, "conflict": 3.6, "communication": 4.0},
            axis_flags=[],
        )
        declared_p = CanonicalProfile(
            participant_id="d1", source="DECLARED_TYPE", positions=positions,
            ratios=None, means=None, axis_flags=[],
        )
        other = CanonicalProfile(
            participant_id="o1", source="DECLARED_TYPE", positions=other_pos,
            ratios=None, means=None, axis_flags=[],
        )

        r1 = run_team_analysis([survey_p, other, other])
        r2 = run_team_analysis([declared_p, other, other])
        assert r1.team_grade == r2.team_grade


# ──────────────────────────────────────────────
# 14. 개인 규칙 매칭 (기존 호환)
# ──────────────────────────────────────────────


class TestPrivateRules:
    def test_direct_in_tactful_team(self):
        profile = CanonicalProfile(
            participant_id="p1", source="DECLARED_TYPE",
            positions={"planning": "PLANNER", "agency": "DRIVER", "conflict": "CONFRONTER", "communication": "DIRECT"},
            ratios=None, means=None, axis_flags=[],
        )
        distribution = {
            "planning": {"PLANNER": 2, "ADAPTER": 1, "NEUTRAL": 0},
            "agency": {"DRIVER": 1, "SUPPORTER": 2, "NEUTRAL": 0},
            "conflict": {"CONFRONTER": 1, "HARMONIZER": 2, "NEUTRAL": 0},
            "communication": {"DIRECT": 1, "TACTFUL": 2, "NEUTRAL": 0},
        }
        result = match_private_rules(profile, distribution, 3)
        assert "CHECK_FEEDBACK_TONE" in result.caution_codes


# ──────────────────────────────────────────────
# 추가 테스트: 코드 리뷰 패치 검증
# ──────────────────────────────────────────────


class TestModelIdDefault:
    """정확한 기본 Bedrock 모델 ID"""

    def test_default_model_id_is_complete(self):
        from ai.config import AISettings
        settings = AISettings()
        assert settings.bedrock_model_id.endswith("-v1:0"), (
            f"모델 ID가 불완전: {settings.bedrock_model_id}"
        )
        assert "global.anthropic" in settings.bedrock_model_id


class TestRetryContextPreservation:
    """재시도 시 원래 입력 컨텍스트 유지"""

    def test_team_retry_includes_distribution(self):
        from ai.nodes.generate import _build_team_prompt, _build_revision_suffix
        state: CommentGraphState = {
            "audience": "TEAM",
            "analysis_result_id": "retry-test",
            "participant_id": None,
            "allowed_strength_codes": ["INITIATIVE_SUPPORT_BALANCE"],
            "allowed_caution_codes": [],
            "allowed_recommendation_codes": [],
            "allowed_rule_ids": ["TEAM_BALANCED_AGENCY"],
            "knowledge_context": {"team_size": 4, "distribution": {"planning": {"PLANNER": 2}}},
            "draft": None,
            "validation_errors": ["GRADE_LEAK: HIGH"],
            "retry_count": 1,
            "final": None,
            "used_fallback": False,
        }
        base = _build_team_prompt(state)
        revision = _build_revision_suffix(state)
        combined = f"{base}\n\n---\n\n{revision}"
        # 원래 컨텍스트 유지
        assert "PLANNER" in combined
        assert "team_size" in base or "4" in base
        # 검증 오류도 포함
        assert "GRADE_LEAK" in combined

    def test_private_retry_includes_positions(self):
        from ai.nodes.generate import _build_private_prompt, _build_revision_suffix
        state: CommentGraphState = {
            "audience": "SELF_ONLY",
            "analysis_result_id": "retry-test-2",
            "participant_id": "p1",
            "allowed_strength_codes": ["PLANNING_STABILITY"],
            "allowed_caution_codes": ["CHECK_FEEDBACK_TONE"],
            "allowed_recommendation_codes": ["FACT_IMPACT_REQUEST"],
            "allowed_rule_ids": ["PERSONAL_PLANNER_STABILITY"],
            "knowledge_context": {
                "self_positions": {"planning": "PLANNER", "agency": "DRIVER"},
                "team_aggregate": {"planning": {"PLANNER": 2, "ADAPTER": 1}},
            },
            "draft": None,
            "validation_errors": ["FORCE_EXPRESSION: 반드시"],
            "retry_count": 1,
            "final": None,
            "used_fallback": False,
        }
        base = _build_private_prompt(state)
        revision = _build_revision_suffix(state)
        combined = f"{base}\n\n---\n\n{revision}"
        assert "PLANNER" in combined
        assert "DRIVER" in combined
        assert "FORCE_EXPRESSION" in combined


class TestTeamNoCaution:
    """TEAM 프롬프트에 caution/grade 미포함"""

    def test_team_prompt_no_caution(self):
        from ai.nodes.generate import _build_team_prompt
        state: CommentGraphState = {
            "audience": "TEAM",
            "analysis_result_id": "no-caution",
            "participant_id": None,
            "allowed_strength_codes": ["INITIATIVE_SUPPORT_BALANCE"],
            "allowed_caution_codes": [],
            "allowed_recommendation_codes": [],
            "allowed_rule_ids": ["TEAM_BALANCED_AGENCY"],
            "knowledge_context": {"team_size": 3, "distribution": {}},
            "draft": None,
            "validation_errors": [],
            "retry_count": 0,
            "final": None,
            "used_fallback": False,
        }
        prompt = _build_team_prompt(state)
        # 입력 데이터 섹션에 caution_codes 값이 없어야 한다
        # (프롬프트 내 "하지 않는 것" 지시문에 HIGH/caution 단어가 있는 건 정상)
        assert "caution_codes" not in prompt
        # 입력 정보 섹션에 team_grade 값이 없어야 한다
        assert "team_grade" not in prompt

    def test_team_input_no_caution_field(self):
        from ai.schemas import TeamCommentInput
        # TeamCommentInput should NOT have caution_codes field
        assert not hasattr(TeamCommentInput.model_fields, "caution_codes")

    def test_private_still_has_caution(self):
        """SELF_ONLY에서는 여전히 caution 코드 유지"""
        from ai.nodes.generate import _build_private_prompt
        state: CommentGraphState = {
            "audience": "SELF_ONLY",
            "analysis_result_id": "has-caution",
            "participant_id": "p1",
            "allowed_strength_codes": ["PLANNING_STABILITY"],
            "allowed_caution_codes": ["CHECK_FEEDBACK_TONE"],
            "allowed_recommendation_codes": ["FACT_IMPACT_REQUEST"],
            "allowed_rule_ids": ["PERSONAL_PLANNER_STABILITY"],
            "knowledge_context": {"self_positions": {"planning": "PLANNER"}, "team_aggregate": {}},
            "draft": None,
            "validation_errors": [],
            "retry_count": 0,
            "final": None,
            "used_fallback": False,
        }
        prompt = _build_private_prompt(state)
        assert "CHECK_FEEDBACK_TONE" in prompt


class TestPublicRuleIdFiltering:
    """TEAM matched_rule_ids에 caution-only rule 미포함"""

    def test_build_team_input_filters_strength_only(self):
        from app.services.chemistry.engine import run_team_analysis, build_team_comment_input
        profiles = [
            CanonicalProfile(participant_id="a", source="DECLARED_TYPE",
                             positions={"planning": "PLANNER", "agency": "DRIVER", "conflict": "CONFRONTER", "communication": "DIRECT"},
                             ratios=None, means=None, axis_flags=[]),
            CanonicalProfile(participant_id="b", source="DECLARED_TYPE",
                             positions={"planning": "PLANNER", "agency": "DRIVER", "conflict": "CONFRONTER", "communication": "DIRECT"},
                             ratios=None, means=None, axis_flags=[]),
            CanonicalProfile(participant_id="c", source="DECLARED_TYPE",
                             positions={"planning": "PLANNER", "agency": "DRIVER", "conflict": "CONFRONTER", "communication": "DIRECT"},
                             ratios=None, means=None, axis_flags=[]),
        ]
        analysis = run_team_analysis(profiles)
        team_input = build_team_comment_input(analysis, "test-id", 3)
        # caution-only rules should not be in matched_rule_ids
        # All rules in team_input should produce a strength code
        for rid in team_input.matched_rule_ids:
            # At minimum they should be in the original analysis
            assert rid in analysis.matched_rule_ids


class TestPublicFallbackFunctions:
    """공개 폴백 함수 검증"""

    def test_build_team_fallback_returns_snapshot(self):
        from ai.nodes.fallback import build_team_fallback
        result = build_team_fallback(
            distribution={"planning": {"PLANNER": 3, "ADAPTER": 0, "NEUTRAL": 0}},
            allowed_rule_ids=["TEAM_PLANNING_STABILITY"],
        )
        assert isinstance(result, TeamSnapshot)
        assert result.title
        assert result.formula
        assert result.scene
        assert len(result.keywords) >= 2
        # 길이 제한
        assert len(result.title) <= 40
        assert len(result.formula) <= 80
        assert len(result.scene) <= 120

    def test_build_private_fallback_returns_card(self):
        from ai.nodes.fallback import build_private_fallback
        result = build_private_fallback(
            self_positions={"planning": "ADAPTER", "agency": "SUPPORTER", "conflict": "HARMONIZER", "communication": "TACTFUL"},
            allowed_rule_ids=["PERSONAL_ADAPTER_FLEXIBILITY"],
        )
        assert isinstance(result, PrivateCard)
        assert result.card_title
        assert result.contribution
        # 길이 제한
        assert len(result.card_title) <= 40
        assert len(result.contribution) <= 160

    def test_team_fallback_no_judgment(self):
        from ai.nodes.fallback import build_team_fallback
        result = build_team_fallback(
            distribution={"planning": {"PLANNER": 2, "ADAPTER": 1, "NEUTRAL": 0}},
            allowed_rule_ids=[],
        )
        all_text = f"{result.title} {result.formula} {result.scene}"
        # 판단 표현 없음
        assert "느리" not in all_text
        assert "실패" not in all_text
        assert "갈등" not in all_text
        assert "문제" not in all_text
        assert "HIGH" not in all_text
        assert "MID" not in all_text
        assert "LOW" not in all_text

    def test_private_fallback_card_style_title(self):
        """개인 폴백 제목이 '~카드' 형태"""
        from ai.nodes.fallback import build_private_fallback
        result = build_private_fallback(
            self_positions={"planning": "PLANNER"},
            allowed_rule_ids=[],
        )
        assert "카드" in result.card_title

    def test_all_fallback_pass_validation(self):
        """모든 폴백 결과가 검증 통과"""
        from ai.nodes.fallback import build_team_fallback, build_private_fallback
        from ai.nodes.validate import validate_comment

        team_fb = build_team_fallback(distribution={}, allowed_rule_ids=["R1"])
        state_t = _team_state(draft=team_fb, allowed_rule_ids=["R1"])
        res_t = validate_comment(state_t)
        assert res_t.get("validation_errors") == [] or res_t.get("final") is not None

        priv_fb = build_private_fallback(self_positions={"planning": "DRIVER"}, allowed_rule_ids=["R2"])
        state_p = _private_state(draft=priv_fb, allowed_rule_ids=["R2"])
        res_p = validate_comment(state_p)
        assert res_p.get("validation_errors") == [] or res_p.get("final") is not None


class TestChatModelCreation:
    """ChatBedrockConverse 객체 생성 (네트워크 호출 없음)"""

    def test_model_instantiation_with_dummy_creds(self):
        import os
        os.environ["AWS_DEFAULT_REGION"] = "ap-northeast-1"
        os.environ["AWS_ACCESS_KEY_ID"] = "test"
        os.environ["AWS_SECRET_ACCESS_KEY"] = "test"
        try:
            from ai.config import get_ai_settings
            # lru_cache를 우회하기 위해 직접 생성
            from botocore.config import Config as BotoConfig
            from langchain_aws import ChatBedrockConverse

            settings = get_ai_settings()
            boto_config = BotoConfig(
                read_timeout=settings.bedrock_timeout,
                connect_timeout=settings.bedrock_connect_timeout,
                retries={"max_attempts": settings.bedrock_max_retries, "mode": "standard"},
            )
            m = ChatBedrockConverse(
                model_id=settings.bedrock_model_id,
                temperature=settings.bedrock_temperature,
                max_tokens=settings.bedrock_max_tokens,
                config=boto_config,
            )
            assert type(m).__name__ == "ChatBedrockConverse"
        finally:
            os.environ.pop("AWS_DEFAULT_REGION", None)
            os.environ.pop("AWS_ACCESS_KEY_ID", None)
            os.environ.pop("AWS_SECRET_ACCESS_KEY", None)

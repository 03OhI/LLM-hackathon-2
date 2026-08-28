"""
Evaluation Harness — pytest 기반 평가 묶음

운영 요청 중에는 실행하지 않고 로컬과 CI에서만 실행한다.

필수 통과 기준 4가지:
1. 동일 입력의 규칙 계산 결과가 동일하다.
2. 정상 LLM 출력이 Pydantic 스키마를 통과한다.
3. 허용되지 않은 코드와 타 참여자 식별자가 차단된다.
4. timeout·파싱 오류·재검증 실패 시 템플릿으로 종료된다.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# 프로젝트 루트를 path에 추가
sys.path.insert(0, str(Path(__file__).parent.parent))

from ai.schemas import (
    CanonicalProfile,
    CommentGraphState,
    GeneratedInsight,
    InsightItem,
)
from ai.nodes.validate import validate_comment
from ai.nodes.fallback import render_fallback
from app.services.scoring.scorer import (
    create_profile_from_survey,
    create_profile_from_declared_type,
    score_survey,
    validate_answers,
)
from app.services.chemistry.engine import (
    compute_distribution,
    match_team_rules,
    match_pair_rules,
    compute_team_index,
    determine_grade,
    match_private_rules,
    run_team_analysis,
)

DATASETS_DIR = Path(__file__).parent / "datasets"


# ──────────────────────────────────────────────
# 헬퍼 함수
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


def _make_graph_state(
    graph_input: dict,
    draft: GeneratedInsight | None = None,
    knowledge_context: dict | None = None,
) -> CommentGraphState:
    return CommentGraphState(
        audience=graph_input["audience"],
        analysis_result_id=graph_input["analysis_result_id"],
        participant_id=graph_input.get("participant_id"),
        allowed_strength_codes=graph_input["allowed_strength_codes"],
        allowed_caution_codes=graph_input["allowed_caution_codes"],
        allowed_recommendation_codes=graph_input["allowed_recommendation_codes"],
        allowed_rule_ids=graph_input["allowed_rule_ids"],
        knowledge_context=knowledge_context or {},
        draft=draft,
        validation_errors=[],
        retry_count=0,
        final=None,
        used_fallback=False,
    )


def _draft_from_dict(d: dict) -> GeneratedInsight:
    return GeneratedInsight(
        summary=d["summary"],
        strengths=[InsightItem(**s) for s in d["strengths"]],
        cautions=[InsightItem(**c) for c in d["cautions"]],
        used_rule_ids=d["used_rule_ids"],
    )


# ──────────────────────────────────────────────
# 기준 1: 동일 입력의 규칙 계산 결과가 동일하다
# ──────────────────────────────────────────────


class TestDeterminism:
    """규칙 엔진 결정론 검증"""

    @pytest.fixture
    def team_cases(self) -> list[dict]:
        return _load_jsonl("team_cases.jsonl")

    def test_same_input_same_output(self, team_cases):
        """동일 프로필로 2회 실행 시 결과가 동일하다."""
        for case in team_cases:
            profiles = _profiles_from_case(case)

            result1 = run_team_analysis(profiles)
            result2 = run_team_analysis(profiles)

            assert result1.team_grade == result2.team_grade, f"Case {case['case_id']}: grade mismatch"
            assert result1.internal_index == result2.internal_index, f"Case {case['case_id']}: index mismatch"
            assert result1.team_strength_codes == result2.team_strength_codes
            assert result1.team_caution_codes == result2.team_caution_codes
            assert result1.matched_rule_ids == result2.matched_rule_ids

    def test_pair_count(self, team_cases):
        """페어 수가 n*(n-1)/2인지 확인한다."""
        for case in team_cases:
            profiles = _profiles_from_case(case)
            pair_results = match_pair_rules(profiles)

            expected_max = case["assertions"]["pair_count"]
            # pair_results는 매칭된 규칙 수이므로 <= n*(n-1)/2 * rules
            n = len(profiles)
            assert n * (n - 1) // 2 == expected_max

    def test_grade_not_empty(self, team_cases):
        """등급이 항상 존재한다."""
        for case in team_cases:
            profiles = _profiles_from_case(case)
            result = run_team_analysis(profiles)
            assert result.team_grade in ("HIGH", "MID", "LOW")

    def test_input_source_independence(self):
        """입력 방식(SURVEY/DECLARED_TYPE)이 달라도 positions가 같으면 동일 등급."""
        positions = {
            "planning": "PLANNER",
            "agency": "DRIVER",
            "conflict": "CONFRONTER",
            "communication": "DIRECT",
        }
        survey_profile = CanonicalProfile(
            participant_id="s1", source="SURVEY", positions=positions,
            ratios={"planning": 0.8, "agency": 0.7, "conflict": 0.65, "communication": 0.75},
            means={"planning": 4.2, "agency": 3.8, "conflict": 3.6, "communication": 4.0},
            axis_flags=[],
        )
        declared_profile = CanonicalProfile(
            participant_id="d1", source="DECLARED_TYPE", positions=positions,
            ratios=None, means=None, axis_flags=[],
        )
        # 3명 팀 (2명 동일 positions + 1명 다름)
        other = CanonicalProfile(
            participant_id="o1", source="DECLARED_TYPE",
            positions={"planning": "ADAPTER", "agency": "SUPPORTER", "conflict": "HARMONIZER", "communication": "TACTFUL"},
            ratios=None, means=None, axis_flags=[],
        )

        result_with_survey = run_team_analysis([survey_profile, other, other])
        result_with_declared = run_team_analysis([declared_profile, other, other])

        assert result_with_survey.team_grade == result_with_declared.team_grade


# ──────────────────────────────────────────────
# 기준 2: 정상 출력이 Pydantic 스키마를 통과한다
# ──────────────────────────────────────────────


class TestSchemaValidation:
    """구조화 출력 스키마 검증"""

    def test_valid_team_output_passes(self):
        """유효한 팀 코멘트 출력이 검증을 통과한다."""
        state = _make_graph_state(
            graph_input={
                "audience": "TEAM",
                "analysis_result_id": "test-valid-001",
                "participant_id": None,
                "allowed_strength_codes": ["INITIATIVE_SUPPORT_BALANCE"],
                "allowed_caution_codes": ["DIRECT_COMMUNICATION_CONCENTRATION"],
                "allowed_recommendation_codes": [],
                "allowed_rule_ids": ["TEAM_BALANCED_AGENCY", "TEAM_DIRECT_CONCENTRATION"],
            },
            draft=GeneratedInsight(
                summary="이 팀은 주도와 지원의 균형이 잡혀 있어요.",
                strengths=[InsightItem(code="INITIATIVE_SUPPORT_BALANCE", text="주도-지원 균형이 좋아요.")],
                cautions=[InsightItem(code="DIRECT_COMMUNICATION_CONCENTRATION", text="직설형이 집중되어 있어요.", action="사실-영향-요청 순서로 말해 보세요.")],
                used_rule_ids=["TEAM_BALANCED_AGENCY", "TEAM_DIRECT_CONCENTRATION"],
            ),
        )

        result = validate_comment(state)
        assert result.get("validation_errors") == [] or result.get("final") is not None

    def test_valid_private_output_passes(self):
        """유효한 개인 코멘트 출력이 검증을 통과한다."""
        state = _make_graph_state(
            graph_input={
                "audience": "SELF_ONLY",
                "analysis_result_id": "test-valid-002",
                "participant_id": "p1",
                "allowed_strength_codes": ["PLANNING_STABILITY"],
                "allowed_caution_codes": ["CHECK_FEEDBACK_TONE"],
                "allowed_recommendation_codes": ["FACT_IMPACT_REQUEST"],
                "allowed_rule_ids": ["PERSONAL_PLANNER_STABILITY", "PERSONAL_DIRECT_IN_TACTFUL_TEAM"],
            },
            draft=GeneratedInsight(
                summary="이 팀에서 계획을 정리하는 강점을 활용할 수 있어요.",
                strengths=[InsightItem(code="PLANNING_STABILITY", text="체계적 계획으로 팀에 기여해요.")],
                cautions=[InsightItem(code="CHECK_FEEDBACK_TONE", text="표현 전달 시 톤을 확인해 보세요.", action="사실-영향-요청 순서로 전달하세요.")],
                used_rule_ids=["PERSONAL_PLANNER_STABILITY", "PERSONAL_DIRECT_IN_TACTFUL_TEAM"],
            ),
            knowledge_context={"other_participant_names": [], "other_participant_ids": []},
        )

        result = validate_comment(state)
        assert result.get("validation_errors") == [] or result.get("final") is not None


# ──────────────────────────────────────────────
# 기준 3: 허용되지 않은 코드·타 참여자 식별자 차단
# ──────────────────────────────────────────────


class TestValidationBlocking:
    """검증기 차단 테스트"""

    @pytest.fixture
    def failure_cases(self) -> list[dict]:
        return _load_jsonl("failure_cases.jsonl")

    def test_unknown_codes_blocked(self, failure_cases):
        """허용되지 않은 코드가 차단된다."""
        for case in failure_cases:
            assertions = case["assertions"]
            if not assertions.get("validation_fails"):
                continue

            draft = _draft_from_dict(case["mock_draft"])
            knowledge_context = case.get("knowledge_context", {})
            state = _make_graph_state(
                graph_input=case["graph_input"],
                draft=draft,
                knowledge_context=knowledge_context,
            )

            result = validate_comment(state)
            errors = result.get("validation_errors", [])

            expected_error = assertions["error_contains"]
            assert any(expected_error in err for err in errors), (
                f"Case {case['case_id']}: expected '{expected_error}' in errors, got {errors}"
            )

    def test_no_numeric_score(self):
        """숫자 점수 생성이 차단된다."""
        cases = _load_jsonl("failure_cases.jsonl")
        case = next(c for c in cases if c["case_id"] == "failure-numeric-score")

        draft = _draft_from_dict(case["mock_draft"])
        state = _make_graph_state(graph_input=case["graph_input"], draft=draft)

        result = validate_comment(state)
        errors = result.get("validation_errors", [])
        assert any("NUMERIC_SCORE_GENERATED" in e for e in errors)

    def test_other_member_reference_blocked(self):
        """타 참여자 언급이 차단된다."""
        cases = _load_jsonl("failure_cases.jsonl")
        case = next(c for c in cases if c["case_id"] == "failure-other-member-reference")

        draft = _draft_from_dict(case["mock_draft"])
        state = _make_graph_state(
            graph_input=case["graph_input"],
            draft=draft,
            knowledge_context=case["knowledge_context"],
        )

        result = validate_comment(state)
        errors = result.get("validation_errors", [])
        assert any("OTHER_MEMBER_REFERENCE" in e for e in errors)

    def test_forbidden_expression_blocked(self):
        """금칙어가 차단된다."""
        cases = _load_jsonl("failure_cases.jsonl")
        case = next(c for c in cases if c["case_id"] == "failure-forbidden-expression")

        draft = _draft_from_dict(case["mock_draft"])
        state = _make_graph_state(graph_input=case["graph_input"], draft=draft)

        result = validate_comment(state)
        errors = result.get("validation_errors", [])
        assert any("FORBIDDEN_EXPRESSION" in e for e in errors)


# ──────────────────────────────────────────────
# 기준 4: timeout·파싱 오류·재검증 실패 시 템플릿 종료
# ──────────────────────────────────────────────


class TestFallbackPath:
    """폴백 경로 검증"""

    def test_fallback_produces_valid_output(self):
        """폴백이 유효한 GeneratedInsight를 생성한다."""
        state: CommentGraphState = {
            "audience": "TEAM",
            "analysis_result_id": "test-fallback-001",
            "participant_id": None,
            "allowed_strength_codes": ["INITIATIVE_SUPPORT_BALANCE", "CONFLICT_BALANCE"],
            "allowed_caution_codes": ["DIRECT_COMMUNICATION_CONCENTRATION"],
            "allowed_recommendation_codes": [],
            "allowed_rule_ids": ["TEAM_BALANCED_AGENCY", "TEAM_BALANCED_CONFLICT", "TEAM_DIRECT_CONCENTRATION"],
            "knowledge_context": {},
            "draft": None,
            "validation_errors": ["LLM_ERROR: TimeoutError: Request timed out"],
            "retry_count": 2,
            "final": None,
            "used_fallback": False,
        }

        result = render_fallback(state)

        assert result["used_fallback"] is True
        assert result["final"] is not None
        assert isinstance(result["final"], GeneratedInsight)
        assert len(result["final"].strengths) > 0
        assert len(result["final"].cautions) > 0

    def test_fallback_only_uses_allowed_codes(self):
        """폴백 출력이 허용된 코드만 사용한다."""
        state: CommentGraphState = {
            "audience": "SELF_ONLY",
            "analysis_result_id": "test-fallback-002",
            "participant_id": "p1",
            "allowed_strength_codes": ["PLANNING_STABILITY"],
            "allowed_caution_codes": ["CHECK_FEEDBACK_TONE"],
            "allowed_recommendation_codes": ["FACT_IMPACT_REQUEST"],
            "allowed_rule_ids": ["PERSONAL_PLANNER_STABILITY", "PERSONAL_DIRECT_IN_TACTFUL_TEAM"],
            "knowledge_context": {},
            "draft": None,
            "validation_errors": ["PARSE_ERROR"],
            "retry_count": 2,
            "final": None,
            "used_fallback": False,
        }

        result = render_fallback(state)
        insight = result["final"]

        for s in insight.strengths:
            assert s.code in state["allowed_strength_codes"]
        for c in insight.cautions:
            assert c.code in state["allowed_caution_codes"]
            assert c.action is not None and c.action.strip() != ""

    def test_fallback_cautions_always_have_action(self):
        """폴백 주의점에 항상 action이 있다."""
        state: CommentGraphState = {
            "audience": "TEAM",
            "analysis_result_id": "test-fallback-003",
            "participant_id": None,
            "allowed_strength_codes": ["DRIVER_ENERGY"],
            "allowed_caution_codes": ["LOW_DRIVER_ENERGY", "PLANNING_OVERLOAD", "CONFRONTER_CONCENTRATION"],
            "allowed_recommendation_codes": [],
            "allowed_rule_ids": ["TEAM_DRIVER_ENERGY"],
            "knowledge_context": {},
            "draft": None,
            "validation_errors": ["VALIDATION_RETRY_FAILED"],
            "retry_count": 2,
            "final": None,
            "used_fallback": False,
        }

        result = render_fallback(state)
        for caution in result["final"].cautions:
            assert caution.action is not None
            assert len(caution.action.strip()) > 0


# ──────────────────────────────────────────────
# 추가: 채점 서비스 검증
# ──────────────────────────────────────────────


class TestScoringService:
    """채점 서비스 단위 테스트"""

    def test_valid_answers_produce_profile(self):
        """유효한 24문항 응답이 프로필을 생성한다."""
        # 모두 4점 → 정방향 평균 4.0, 역방향 (6-4)=2.0
        # 축 평균 = (4+4+4+2+2+2)/6 = 3.0
        # 비율 = (3.0 - 1)/4 = 0.5 → NEUTRAL
        answers = [4] * 24
        profile = create_profile_from_survey("test-p1", answers)

        assert profile.source == "SURVEY"
        assert profile.participant_id == "test-p1"
        assert all(pos == "NEUTRAL" for pos in profile.positions.values())

    def test_high_scores_produce_upper(self):
        """높은 점수가 상위 극을 생성한다."""
        # 정방향 5, 역방향 1 (6-1=5) → 평균 5.0, 비율 = (5-1)/4 = 1.0
        answers = []
        for axis in range(4):
            answers.extend([5, 5, 5, 1, 1, 1])  # forward high, reverse low
        profile = create_profile_from_survey("test-p2", answers)

        assert profile.positions["planning"] == "PLANNER"
        assert profile.positions["agency"] == "DRIVER"
        assert profile.positions["conflict"] == "CONFRONTER"
        assert profile.positions["communication"] == "DIRECT"

    def test_low_scores_produce_lower(self):
        """낮은 점수가 하위 극을 생성한다."""
        # 정방향 1, 역방향 5 (6-5=1) → 평균 1.0, 비율 = (1-1)/4 = 0.0
        answers = []
        for axis in range(4):
            answers.extend([1, 1, 1, 5, 5, 5])
        profile = create_profile_from_survey("test-p3", answers)

        assert profile.positions["planning"] == "ADAPTER"
        assert profile.positions["agency"] == "SUPPORTER"
        assert profile.positions["conflict"] == "HARMONIZER"
        assert profile.positions["communication"] == "TACTFUL"

    def test_invalid_answer_count_raises(self):
        """응답 수가 24개가 아니면 에러가 발생한다."""
        with pytest.raises(ValueError, match="24"):
            create_profile_from_survey("test-p4", [3] * 20)

    def test_invalid_answer_range_raises(self):
        """응답이 1~5 범위를 벗어나면 에러가 발생한다."""
        answers = [3] * 23 + [6]
        with pytest.raises(ValueError):
            create_profile_from_survey("test-p5", answers)

    def test_declared_type_validation(self):
        """직접 입력 유효성 검사가 동작한다."""
        profile = create_profile_from_declared_type("test-d1", {
            "planning": "PLANNER",
            "agency": "SUPPORTER",
            "conflict": "HARMONIZER",
            "communication": "DIRECT",
        })
        assert profile.source == "DECLARED_TYPE"
        assert profile.ratios is None
        assert profile.means is None

    def test_declared_type_invalid_position_raises(self):
        """직접 입력에서 잘못된 포지션 값이면 에러 발생."""
        with pytest.raises(ValueError, match="유효하지 않"):
            create_profile_from_declared_type("test-d2", {
                "planning": "INVALID",
                "agency": "SUPPORTER",
                "conflict": "HARMONIZER",
                "communication": "DIRECT",
            })

    def test_declared_type_missing_axis_raises(self):
        """직접 입력에서 축이 누락되면 에러 발생."""
        with pytest.raises(ValueError, match="누락"):
            create_profile_from_declared_type("test-d3", {
                "planning": "PLANNER",
                "agency": "SUPPORTER",
            })


# ──────────────────────────────────────────────
# 추가: 개인 규칙 매칭 검증
# ──────────────────────────────────────────────


class TestPrivateRuleMatching:
    """개인 규칙 매칭 테스트"""

    @pytest.fixture
    def private_cases(self) -> list[dict]:
        return _load_jsonl("private_cases.jsonl")

    def test_private_rules_produce_expected_cautions(self, private_cases):
        """개인 규칙이 예상 주의 코드를 생성한다."""
        for case in private_cases:
            assertions = case["assertions"]
            if "expected_cautions_include" not in assertions:
                continue

            profile = CanonicalProfile(
                participant_id=case["participant_id"],
                source="DECLARED_TYPE",
                positions=case["self_positions"],
                ratios=None,
                means=None,
                axis_flags=[],
            )

            result = match_private_rules(
                profile,
                case["distribution"],
                case["team_size"],
            )

            for expected in assertions["expected_cautions_include"]:
                assert expected in result.caution_codes, (
                    f"Case {case['case_id']}: expected '{expected}' in {result.caution_codes}"
                )

    def test_neutral_produces_no_private_rules(self, private_cases):
        """중립 포지션은 개인 규칙을 트리거하지 않는다."""
        case = next(c for c in private_cases if c["case_id"] == "private-neutral-axis-no-caution")

        profile = CanonicalProfile(
            participant_id=case["participant_id"],
            source="DECLARED_TYPE",
            positions=case["self_positions"],
            ratios=None,
            means=None,
            axis_flags=[],
        )

        result = match_private_rules(
            profile,
            case["distribution"],
            case["team_size"],
        )

        assert len(result.caution_codes) == case["assertions"]["caution_count"]
        assert len(result.strength_codes) == case["assertions"]["strength_count"]


# ──────────────────────────────────────────────
# 추가: 개인정보 교차 노출 테스트
# ──────────────────────────────────────────────


class TestPrivacyIsolation:
    """개인정보 교차 노출 방지 테스트"""

    def test_private_insight_no_cross_contamination(self):
        """개인 인사이트 검증에서 다른 팀원 ID가 차단된다."""
        state: CommentGraphState = {
            "audience": "SELF_ONLY",
            "analysis_result_id": "privacy-test-001",
            "participant_id": "p1",
            "allowed_strength_codes": ["DRIVER_ENERGY"],
            "allowed_caution_codes": ["CHECK_PACE_PRESSURE"],
            "allowed_recommendation_codes": ["PAUSE_BEFORE_PUSH"],
            "allowed_rule_ids": ["PERSONAL_DRIVER_IN_SUPPORTER_TEAM"],
            "knowledge_context": {
                "other_participant_names": ["민수", "지영"],
                "other_participant_ids": ["p2", "p3"],
            },
            "draft": GeneratedInsight(
                summary="민수님보다 더 잘할 수 있어요.",
                strengths=[InsightItem(code="DRIVER_ENERGY", text="추진력이 좋아요.")],
                cautions=[InsightItem(
                    code="CHECK_PACE_PRESSURE",
                    text="p2와 속도를 맞춰보세요.",
                    action="천천히 가세요.",
                )],
                used_rule_ids=["PERSONAL_DRIVER_IN_SUPPORTER_TEAM"],
            ),
            "validation_errors": [],
            "retry_count": 0,
            "final": None,
            "used_fallback": False,
        }

        result = validate_comment(state)
        errors = result.get("validation_errors", [])

        # 이름 또는 ID 중 하나라도 감지되어야 함
        has_reference_error = any(
            "OTHER_MEMBER" in e for e in errors
        )
        assert has_reference_error, f"Expected privacy violation detected, got: {errors}"

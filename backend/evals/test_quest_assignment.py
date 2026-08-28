"""
퀘스트 배정 AI 모듈 평가 하니스 — SPEC_V5_CONTEST_QUEST_AGENT.md §5, §10

실제 Bedrock을 호출하지 않는다. LLM 호출부(ai.quest_assignment.nodes.select의
get_chat_model)를 mock으로 대체해 AGENT 경로/timeout/파싱 실패/폴백을 검증한다.
실호출 검증은 EC2에서 별도로 수행한다.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from ai.quest_assignment import QuestCatalogConfigurationError, assign_quest
from ai.quest_assignment.catalog import validate_catalog
from ai.quest_assignment.filter import filter_candidates, matched_candidates
from ai.quest_assignment.nodes import select as select_module
from ai.quest_assignment.nodes.fallback import deterministic_fallback
from ai.quest_assignment.nodes.validate import validate_decision
from ai.quest_assignment.schemas import (
    QuestAssignmentState,
    QuestMatchContext,
    QuestSelectionOutput,
    QuestTemplate,
)
from ai.quest_assignment.scoring import (
    ALSO_FOR_MATCH_WEIGHT,
    BEST_FOR_MATCH_WEIGHT,
    CONTEXT_TAG_MATCH_WEIGHT,
    REPEATED_CATEGORY_PENALTY,
    completed_categories,
    rank_candidates,
    score_candidate,
    sort_for_fallback,
)

KNOWLEDGE_BASE_DIR = Path(__file__).parent.parent / "knowledge_base"


# ──────────────────────────────────────────────
# 헬퍼 / fixture 빌더 (V5.2 최종 계약)
# ──────────────────────────────────────────────


def make_quest(**overrides) -> QuestTemplate:
    base = dict(
        quest_id="Q_TEST_DEFAULT",
        title="테스트 퀘스트",
        summary="테스트용 요약입니다.",
        category="ICEBREAKER",
        primary_goal="테스트 목적",
        duration_minutes=10,
        team_size={"min": 3, "max": 10},
        interaction_mode="HYBRID",
        energy_level="LOW",
        disclosure_level="LOW",
        assignment="AUTO",
        reveals_axes=[],
        is_universal=False,
        best_for=[],
        also_for=[],
        avoid_for=[],
        context_tags=[],
        materials=[],
        steps=["1단계 설명", "2단계 설명"],
        deliverable="테스트 결과물",
        completion_condition={
            "description": "팀원 각자가 반응을 남긴다.",
            "checks": [{"type": "REACTION", "scope": "PER_MEMBER", "min_count": 1}],
        },
        safety_notes=["개인 신상 정보를 요구하지 않는다."],
        is_active=True,
        version="1.0",
    )
    base.update(overrides)
    return QuestTemplate(**base)


def make_universal_fallback_quest(**overrides) -> QuestTemplate:
    """카탈로그 전체 검증(item 3: NO_UNIVERSAL_FALLBACK_AVAILABLE)을 통과시키기 위한
    최소 조건을 만족하는 범용 폴백 퀘스트. 다른 항목만 테스트하고 싶을 때
    카탈로그에 함께 넣어 쓴다."""
    base = dict(quest_id="UNIVERSAL_FALLBACK", is_universal=True, avoid_for=[])
    base.update(overrides)
    return make_quest(**base)


def make_context(**overrides) -> QuestMatchContext:
    base = dict(
        room_id="room-test",
        team_size=4,
        matched_rule_ids=["TEAM_BALANCED_AGENCY"],
        distribution={"agency": {"DRIVER": 1, "SUPPORTER": 1, "NEUTRAL": 2}},
        context_tags=["FIRST_MEETING"],
        completed_quest_ids=[],
    )
    base.update(overrides)
    return QuestMatchContext(**base)


def load_real_catalog() -> list[QuestTemplate]:
    data = json.loads((KNOWLEDGE_BASE_DIR / "quests.json").read_text(encoding="utf-8"))
    return [QuestTemplate(**q) for q in data]


class _FakeStructuredModel:
    def __init__(self, behavior):
        self.behavior = behavior

    async def ainvoke(self, messages):
        if isinstance(self.behavior, BaseException):
            raise self.behavior
        if callable(self.behavior):
            return self.behavior(messages)
        return self.behavior


class _FakeChatModel:
    def __init__(self, behavior):
        self.behavior = behavior

    def with_structured_output(self, schema):
        return _FakeStructuredModel(self.behavior)


def patch_bedrock(monkeypatch, behavior):
    """select 노드의 get_chat_model()을 mock으로 바꾼다."""
    monkeypatch.setattr(select_module, "get_chat_model", lambda: _FakeChatModel(behavior))


def run(coro):
    return asyncio.run(coro)


# ──────────────────────────────────────────────
# 1. 카탈로그 검증
# ──────────────────────────────────────────────


class TestCatalogValidation:
    def test_valid_quest_passes(self):
        result = validate_catalog(
            [make_quest(best_for=["TEAM_BALANCED_AGENCY"]), make_universal_fallback_quest()]
        )
        assert result.errors == []
        assert len(result.valid_templates) == 2

    def test_natural_language_best_for_blocked(self):
        quest = make_quest(best_for=["처음 만나 작업 방식을 모르는 팀"])
        result = validate_catalog([quest])
        assert result.valid_templates == []
        assert any(e.code == "NATURAL_LANGUAGE_VALUE" for e in result.errors)

    def test_unknown_rule_id_blocked(self):
        quest = make_quest(best_for=["TEAM_DOES_NOT_EXIST"])
        result = validate_catalog([quest])
        assert result.valid_templates == []
        assert any(e.code == "UNKNOWN_RULE_ID" for e in result.errors)

    def test_also_for_and_avoid_for_checked_too(self):
        quest = make_quest(also_for=["자연어"], avoid_for=["TEAM_FAKE_ID"])
        result = validate_catalog([quest])
        codes = {e.code for e in result.errors}
        assert "NATURAL_LANGUAGE_VALUE" in codes
        assert "UNKNOWN_RULE_ID" in codes

    def test_unknown_context_tag_blocked(self):
        quest = make_quest(context_tags=["NOT_A_REAL_TAG"])
        result = validate_catalog([quest])
        assert result.valid_templates == []
        assert any(e.code == "UNKNOWN_CONTEXT_TAG" for e in result.errors)

    def test_universal_with_nonempty_avoid_for_blocked(self):
        quest = make_quest(is_universal=True, avoid_for=["TEAM_LOW_DRIVER"])
        result = validate_catalog([quest])
        assert any(e.code == "UNIVERSAL_WITH_AVOID_FOR" for e in result.errors)

    def test_high_disclosure_must_be_manual(self):
        quest = make_quest(disclosure_level="HIGH", assignment="AUTO")
        result = validate_catalog([quest])
        assert any(e.code == "HIGH_DISCLOSURE_MUST_BE_MANUAL" for e in result.errors)

    def test_high_disclosure_manual_is_fine(self):
        quest = make_quest(disclosure_level="HIGH", assignment="MANUAL")
        result = validate_catalog([quest, make_universal_fallback_quest()])
        assert result.errors == []

    def test_duplicate_quest_id_blocked(self):
        q1 = make_quest(quest_id="DUP")
        q2 = make_quest(quest_id="DUP")
        result = validate_catalog([q1, q2])
        assert result.valid_templates == []
        assert any(e.code == "DUPLICATE_QUEST_ID" for e in result.errors)

    def test_missing_per_member_check_blocked(self):
        quest = make_quest(
            completion_condition={
                "description": "팀 전체가 제출한다.",
                "checks": [{"type": "TEXT_SUBMIT", "scope": "TEAM", "min_count": 1}],
            }
        )
        result = validate_catalog([quest])
        assert any(e.code == "MISSING_PER_MEMBER_CHECK" for e in result.errors)

    def test_invalid_team_size_range_blocked(self):
        quest = make_quest(team_size={"min": 5, "max": 2})
        result = validate_catalog([quest])
        assert any(e.code == "INVALID_TEAM_SIZE_RANGE" for e in result.errors)

    def test_large_team_coverage_warning(self):
        quests = [
            make_quest(quest_id=f"Q_{i}", team_size={"min": 3, "max": 5})
            for i in range(3)
        ]
        result = validate_catalog(quests)
        assert any(w.code == "LARGE_TEAM_AUTO_COVERAGE_LOW" for w in result.warnings)

    def test_real_catalog_passes_validation(self):
        catalog = load_real_catalog()
        result = validate_catalog(catalog)
        assert result.errors == [], result.errors
        assert len(result.valid_templates) == len(catalog)

    def test_no_universal_fallback_is_a_hard_error_not_warning(self):
        """범용 폴백 퀘스트가 하나도 없으면 warning이 아니라 error다."""
        quests = [make_quest(quest_id=f"Q_{i}") for i in range(3)]  # is_universal=False
        result = validate_catalog(quests)
        assert any(e.code == "NO_UNIVERSAL_FALLBACK_AVAILABLE" for e in result.errors)
        assert not any(w.code == "NO_UNIVERSAL_FALLBACK_AVAILABLE" for w in result.warnings)

    def test_universal_fallback_with_full_range_coverage_satisfies_check(self):
        quests = [make_quest(quest_id="Q1"), make_universal_fallback_quest()]
        result = validate_catalog(quests)
        assert not any(e.code == "NO_UNIVERSAL_FALLBACK_AVAILABLE" for e in result.errors)

    def test_universal_fallback_with_partial_range_does_not_satisfy_check(self):
        """3~10명 전체 범위를 지원하지 못하는 범용 퀘스트는 커버리지 조건을 못 채운다."""
        partial_universal = make_universal_fallback_quest(team_size={"min": 3, "max": 6})
        quests = [make_quest(quest_id="Q1"), partial_universal]
        result = validate_catalog(quests)
        assert any(e.code == "NO_UNIVERSAL_FALLBACK_AVAILABLE" for e in result.errors)

    def test_manual_universal_does_not_satisfy_check(self):
        """assignment=MANUAL인 범용 퀘스트는 자동 폴백으로 쓸 수 없으니 인정하지 않는다."""
        manual_universal = make_universal_fallback_quest(assignment="MANUAL")
        quests = [make_quest(quest_id="Q1"), manual_universal]
        result = validate_catalog(quests)
        assert any(e.code == "NO_UNIVERSAL_FALLBACK_AVAILABLE" for e in result.errors)


# ──────────────────────────────────────────────
# 2. 결정론적 필터
# ──────────────────────────────────────────────


class TestFilterCandidates:
    def test_team_size_mismatch_excluded(self):
        quest = make_quest(team_size={"min": 5, "max": 6})
        candidates = filter_candidates([quest], make_context(team_size=4))
        assert candidates == []

    def test_manual_excluded(self):
        quest = make_quest(assignment="MANUAL")
        candidates = filter_candidates([quest], make_context())
        assert candidates == []

    def test_high_disclosure_excluded(self):
        quest = make_quest(disclosure_level="HIGH", assignment="MANUAL")
        candidates = filter_candidates([quest], make_context())
        assert candidates == []

    def test_inactive_excluded(self):
        quest = make_quest(is_active=False)
        candidates = filter_candidates([quest], make_context())
        assert candidates == []

    def test_avoid_for_overlap_excluded(self):
        quest = make_quest(avoid_for=["TEAM_BALANCED_AGENCY"])
        ctx = make_context(matched_rule_ids=["TEAM_BALANCED_AGENCY"])
        candidates = filter_candidates([quest], ctx)
        assert candidates == []

    def test_completed_quest_excluded(self):
        quest = make_quest(quest_id="Q_DONE")
        ctx = make_context(completed_quest_ids=["Q_DONE"])
        candidates = filter_candidates([quest], ctx)
        assert candidates == []

    def test_eligible_quest_kept(self):
        quest = make_quest(quest_id="Q_OK")
        candidates = filter_candidates([quest], make_context())
        assert [c.quest_id for c in candidates] == ["Q_OK"]

    def test_universal_quest_excluded_from_normal_candidates(self):
        """범용 퀘스트는 일반 후보 풀에 들어가지 않는다 — 적합한 일반 AUTO
        후보가 전혀 없을 때만 nodes/fallback.py가 폴백으로 쓴다."""
        universal = make_quest(quest_id="UNIVERSAL", is_universal=True)
        regular = make_quest(quest_id="REGULAR", is_universal=False)
        candidates = filter_candidates([universal, regular], make_context())
        assert [c.quest_id for c in candidates] == ["REGULAR"]

    @pytest.mark.parametrize("team_size", [3, 4, 10])
    def test_team_sizes_3_4_10(self, team_size):
        quest = make_quest(team_size={"min": 3, "max": 10})
        candidates = filter_candidates([quest], make_context(team_size=team_size))
        assert len(candidates) == 1


# ──────────────────────────────────────────────
# 2b. 맞춤 후보 판정 (matched_candidates)
# ──────────────────────────────────────────────


class TestMatchedCandidates:
    """안전·인원 필터를 통과했다고 해서 전부 Bedrock 후보가 되는 건 아니다.
    best_for 또는 also_for가 matched_rule_ids와 겹쳐야만 "맞춤 후보"다."""

    def test_best_for_match_is_matched_candidate(self):
        quest = make_quest(quest_id="Q1", best_for=["TEAM_BALANCED_AGENCY"])
        ctx = make_context(matched_rule_ids=["TEAM_BALANCED_AGENCY"])
        result = matched_candidates([quest], ctx)
        assert [q.quest_id for q in result] == ["Q1"]

    def test_also_for_only_match_is_matched_candidate(self):
        """also_for만 일치해도 맞춤 후보로 인정된다."""
        quest = make_quest(quest_id="Q1", best_for=[], also_for=["TEAM_BALANCED_AGENCY"])
        ctx = make_context(matched_rule_ids=["TEAM_BALANCED_AGENCY"])
        result = matched_candidates([quest], ctx)
        assert [q.quest_id for q in result] == ["Q1"]

    def test_context_tag_only_match_is_not_matched_candidate(self):
        """context_tags만 겹치는 것은 맞춤 후보가 아니다 — rule_id 매칭이 전혀 없다."""
        quest = make_quest(
            quest_id="Q1", best_for=[], also_for=[], context_tags=["FIRST_MEETING"]
        )
        ctx = make_context(matched_rule_ids=["TEAM_BALANCED_AGENCY"], context_tags=["FIRST_MEETING"])
        result = matched_candidates([quest], ctx)
        assert result == []

    def test_no_rule_id_overlap_at_all_is_not_matched(self):
        quest = make_quest(quest_id="Q1", best_for=["TEAM_LOW_DRIVER"])
        ctx = make_context(matched_rule_ids=["TEAM_BALANCED_AGENCY"])
        result = matched_candidates([quest], ctx)
        assert result == []

    def test_mixed_pool_keeps_only_rule_matched(self):
        matched = make_quest(quest_id="MATCHED", best_for=["TEAM_BALANCED_AGENCY"])
        unmatched = make_quest(quest_id="UNMATCHED", best_for=[], context_tags=["FIRST_MEETING"])
        ctx = make_context(matched_rule_ids=["TEAM_BALANCED_AGENCY"], context_tags=["FIRST_MEETING"])
        result = matched_candidates([matched, unmatched], ctx)
        assert [q.quest_id for q in result] == ["MATCHED"]


# ──────────────────────────────────────────────
# 3. 점수 계산
# ──────────────────────────────────────────────


class TestScoring:
    """점수 공식은 "일치한 항목 개수" 기준이다 — 존재 여부(불리언)가 아니다.
    가중치 상수(BEST_FOR_MATCH_WEIGHT 등)를 직접 참조해 그 사실을 명시적으로
    검증한다."""

    def test_best_for_weight_is_3(self):
        assert BEST_FOR_MATCH_WEIGHT == 3

    def test_also_for_weight_is_1(self):
        assert ALSO_FOR_MATCH_WEIGHT == 1

    def test_context_tag_weight_is_1(self):
        assert CONTEXT_TAG_MATCH_WEIGHT == 1

    def test_best_for_score_scales_with_match_count_not_boolean(self):
        """일치 개수 1개짜리와 2개짜리는 점수가 달라야 한다 — 존재 여부만
        보는 불리언 채점이었다면 둘 다 같은 점수였을 것이다."""
        one_match = make_quest(best_for=["TEAM_BALANCED_AGENCY"])
        two_matches = make_quest(best_for=["TEAM_BALANCED_AGENCY", "TEAM_ADAPTABILITY"])
        ctx = make_context(matched_rule_ids=["TEAM_BALANCED_AGENCY", "TEAM_ADAPTABILITY"])

        score_one = score_candidate(one_match, ctx, set())
        score_two = score_candidate(two_matches, ctx, set())

        assert score_one == BEST_FOR_MATCH_WEIGHT * 1
        assert score_two == BEST_FOR_MATCH_WEIGHT * 2
        assert score_two > score_one

    def test_best_for_match_scores_3_times_count(self):
        quest = make_quest(best_for=["TEAM_BALANCED_AGENCY", "TEAM_ADAPTABILITY"])
        ctx = make_context(matched_rule_ids=["TEAM_BALANCED_AGENCY", "TEAM_ADAPTABILITY"])
        assert score_candidate(quest, ctx, set()) == 6

    def test_also_for_match_scores_1_times_count(self):
        quest = make_quest(also_for=["TEAM_BALANCED_AGENCY", "TEAM_ADAPTABILITY"])
        ctx = make_context(matched_rule_ids=["TEAM_BALANCED_AGENCY", "TEAM_ADAPTABILITY"])
        assert score_candidate(quest, ctx, set()) == 2

    def test_context_tag_match_scores_1_per_tag(self):
        quest = make_quest(context_tags=["FIRST_MEETING", "HACKATHON"])
        ctx = make_context(context_tags=["FIRST_MEETING", "HACKATHON"])
        assert score_candidate(quest, ctx, set()) == 2

    def test_is_universal_does_not_add_score(self):
        """is_universal은 더 이상 가점을 주지 않는다 — 범용 퀘스트는
        filter_candidates에서 애초에 제외되고, 폴백 경로에서만 쓰인다."""
        universal = make_quest(is_universal=True)
        regular = make_quest(is_universal=False)
        ctx = make_context(matched_rule_ids=[], context_tags=[])
        assert score_candidate(universal, ctx, set()) == 0
        assert score_candidate(universal, ctx, set()) == score_candidate(regular, ctx, set())

    def test_repeated_category_penalizes_2(self):
        quest = make_quest(category="ICEBREAKER")
        ctx = make_context(matched_rule_ids=[], context_tags=[])
        assert score_candidate(quest, ctx, {"ICEBREAKER"}) == -REPEATED_CATEGORY_PENALTY

    def test_completed_categories_empty_on_first_assignment(self):
        """completed_quest_ids가 비어 있으면(첫 배정) 반복 카테고리 집합도
        항상 비어 있다 — category 반복 감점이 적용될 수 없다."""
        catalog = [make_quest(quest_id="Q1", category="ICEBREAKER")]
        ctx = make_context(completed_quest_ids=[])
        assert completed_categories(ctx, catalog) == set()

    def test_no_category_penalty_on_first_assignment(self):
        """완료 퀘스트가 없는 첫 배정에서는 같은 category라도 감점되지 않는다."""
        quest = make_quest(category="ICEBREAKER")
        ctx = make_context(matched_rule_ids=[], context_tags=[], completed_quest_ids=[])
        completed_cats = completed_categories(ctx, [quest])
        assert score_candidate(quest, ctx, completed_cats) == 0

    def test_category_penalty_applies_only_when_completed_quest_exists(self):
        done = make_quest(quest_id="DONE", category="ICEBREAKER")
        next_quest = make_quest(quest_id="NEXT", category="ICEBREAKER")
        catalog = [done, next_quest]

        ctx_first_time = make_context(matched_rule_ids=[], context_tags=[], completed_quest_ids=[])
        ctx_after_completion = make_context(
            matched_rule_ids=[], context_tags=[], completed_quest_ids=["DONE"]
        )

        score_first = score_candidate(
            next_quest, ctx_first_time, completed_categories(ctx_first_time, catalog)
        )
        score_after = score_candidate(
            next_quest, ctx_after_completion, completed_categories(ctx_after_completion, catalog)
        )

        assert score_first == 0
        assert score_after == -REPEATED_CATEGORY_PENALTY

    def test_rank_candidates_orders_by_score_desc(self):
        low = make_quest(quest_id="LOW", best_for=[])
        high = make_quest(quest_id="HIGH", best_for=["TEAM_BALANCED_AGENCY"])
        ctx = make_context(matched_rule_ids=["TEAM_BALANCED_AGENCY"])
        ranked = rank_candidates([low, high], ctx, [low, high])
        assert [q.quest_id for q in ranked] == ["HIGH", "LOW"]

    def test_rank_candidates_limits_to_top_3(self):
        quests = [make_quest(quest_id=f"Q{i}") for i in range(5)]
        ctx = make_context()
        ranked = rank_candidates(quests, ctx, quests)
        assert len(ranked) == 3

    def test_tiebreak_disclosure_then_duration_then_id(self):
        a = make_quest(quest_id="B", disclosure_level="MEDIUM", duration_minutes=5)
        b = make_quest(quest_id="A", disclosure_level="LOW", duration_minutes=20)
        ctx = make_context(matched_rule_ids=[], context_tags=[])
        ranked = rank_candidates([a, b], ctx, [a, b])
        assert ranked[0].quest_id == "A"  # LOW disclosure wins despite longer duration

    def test_fallback_sort_matches_rank_sort_now_that_universal_has_no_bonus(self):
        """is_universal 가점이 빠지면서 rank/fallback 정렬 공식이 현재는 동일하다."""
        a = make_quest(quest_id="B", disclosure_level="MEDIUM", duration_minutes=5)
        b = make_quest(quest_id="A", disclosure_level="LOW", duration_minutes=20)
        ctx = make_context(matched_rule_ids=[], context_tags=[])
        ranked = rank_candidates([a, b], ctx, [a, b])
        fell_back = sort_for_fallback([a, b], ctx, [a, b])
        assert [q.quest_id for q in ranked] == [q.quest_id for q in fell_back]


# ──────────────────────────────────────────────
# 4. Bedrock 산출물 검증 (validate_decision)
# ──────────────────────────────────────────────


def _base_state(candidates: list[QuestTemplate], ctx: QuestMatchContext) -> QuestAssignmentState:
    return {
        "context": ctx,
        "raw_catalog": candidates,
        "valid_catalog": candidates,
        "catalog_errors": [],
        "candidates": candidates,
        "ranked": candidates,
        "draft": None,
        "bedrock_skipped": False,
        "validation_errors": [],
        "retry_count": 0,
        "final": None,
        "used_fallback": False,
    }


class TestValidateDecision:
    def test_valid_draft_passes(self):
        quest = make_quest(quest_id="Q1", best_for=["TEAM_BALANCED_AGENCY"])
        ctx = make_context(matched_rule_ids=["TEAM_BALANCED_AGENCY"])
        state = _base_state([quest], ctx)
        state["draft"] = QuestSelectionOutput(
            quest_id="Q1", reason="이유", intro_message="소개", used_rule_ids=["TEAM_BALANCED_AGENCY"]
        )
        result = validate_decision(state)
        assert result["validation_errors"] == []
        assert result["final"].quest_id == "Q1"
        assert result["final"].assignment_source == "AGENT"

    def test_quest_id_outside_candidates_blocked(self):
        quest = make_quest(quest_id="Q1")
        ctx = make_context()
        state = _base_state([quest], ctx)
        state["draft"] = QuestSelectionOutput(
            quest_id="NOT_A_CANDIDATE", reason="이유", intro_message="소개", used_rule_ids=[]
        )
        result = validate_decision(state)
        assert any("QUEST_ID_NOT_IN_CANDIDATES" in e for e in result["validation_errors"])
        assert "final" not in result

    def test_disallowed_used_rule_id_blocked(self):
        quest = make_quest(quest_id="Q1")
        ctx = make_context(matched_rule_ids=["TEAM_BALANCED_AGENCY"])
        state = _base_state([quest], ctx)
        state["draft"] = QuestSelectionOutput(
            quest_id="Q1", reason="이유", intro_message="소개", used_rule_ids=["TEAM_NOT_MATCHED"]
        )
        result = validate_decision(state)
        assert any("UNKNOWN_RULE_ID" in e for e in result["validation_errors"])

    def test_grade_leak_blocked(self):
        quest = make_quest(quest_id="Q1")
        ctx = make_context()
        state = _base_state([quest], ctx)
        state["draft"] = QuestSelectionOutput(
            quest_id="Q1", reason="이 팀은 HIGH 등급이에요", intro_message="소개", used_rule_ids=[]
        )
        result = validate_decision(state)
        assert any("GRADE_LEAK" in e for e in result["validation_errors"])

    def test_success_probability_language_blocked(self):
        quest = make_quest(quest_id="Q1")
        state = _base_state([quest], make_context())
        state["draft"] = QuestSelectionOutput(
            quest_id="Q1", reason="이 팀은 성공 확률이 높아요", intro_message="소개", used_rule_ids=[]
        )
        result = validate_decision(state)
        assert any("FORBIDDEN_EXPRESSION" in e for e in result["validation_errors"])

    def test_position_label_leak_blocked(self):
        quest = make_quest(quest_id="Q1")
        state = _base_state([quest], make_context())
        state["draft"] = QuestSelectionOutput(
            quest_id="Q1", reason="DRIVER인 팀원에게 잘 맞아요", intro_message="소개", used_rule_ids=[]
        )
        result = validate_decision(state)
        assert any("POSITION_LABEL_LEAK" in e for e in result["validation_errors"])

    def test_quest_content_leak_blocked(self):
        quest = make_quest(quest_id="Q1", steps=["팀원 각자 좋아하는 색을 말한다"])
        state = _base_state([quest], make_context())
        state["draft"] = QuestSelectionOutput(
            quest_id="Q1",
            reason="이유",
            intro_message="팀원 각자 좋아하는 색을 말한다",
            used_rule_ids=[],
        )
        result = validate_decision(state)
        assert any("QUEST_CONTENT_LEAK" in e for e in result["validation_errors"])

    def test_bedrock_skipped_is_labeled_rule_not_agent(self):
        """단일 맞춤 후보라 Bedrock을 생략한 draft는 LLM이 고른 게 아니므로
        assignment_source가 AGENT로 기록되면 안 된다. app/services/quests/schemas.py의
        assignment_source가 Literal["AGENT","RULE","FALLBACK"]으로 확장되어
        "RULE"로 정확히 기록한다."""
        quest = make_quest(quest_id="Q1", best_for=["TEAM_BALANCED_AGENCY"])
        ctx = make_context(matched_rule_ids=["TEAM_BALANCED_AGENCY"])
        state = _base_state([quest], ctx)
        state["bedrock_skipped"] = True
        state["draft"] = QuestSelectionOutput(
            quest_id="Q1", reason="이유", intro_message="소개", used_rule_ids=["TEAM_BALANCED_AGENCY"]
        )
        result = validate_decision(state)
        assert result["final"].assignment_source == "RULE"

    def test_draft_none_reports_error(self):
        quest = make_quest(quest_id="Q1")
        state = _base_state([quest], make_context())
        state["draft"] = None
        state["validation_errors"] = ["LLM_ERROR: boom"]
        result = validate_decision(state)
        assert result["validation_errors"] == ["LLM_ERROR: boom"]


# ──────────────────────────────────────────────
# 5. 결정론적 폴백
# ──────────────────────────────────────────────


class TestDeterministicFallback:
    def test_picks_best_of_remaining_candidates(self):
        low = make_quest(quest_id="LOW", best_for=[])
        high = make_quest(quest_id="HIGH", best_for=["TEAM_BALANCED_AGENCY"])
        ctx = make_context(matched_rule_ids=["TEAM_BALANCED_AGENCY"])
        state = _base_state([low, high], ctx)
        state["ranked"] = [low, high]
        result = deterministic_fallback(state)
        assert result["final"].quest_id == "HIGH"
        assert result["final"].assignment_source == "FALLBACK"
        assert result["used_fallback"] is True

    def test_universal_fallback_when_no_candidates(self):
        universal = make_quest(quest_id="UNIVERSAL", is_universal=True)
        ctx = make_context()
        state = _base_state([], ctx)
        state["valid_catalog"] = [universal]
        state["ranked"] = []
        state["candidates"] = []
        result = deterministic_fallback(state)
        assert result["final"].quest_id == "UNIVERSAL"

    def test_raises_configuration_error_when_catalog_has_no_universal(self):
        """일반 후보도 is_universal 폴백도 없으면, 존재하지 않는 quest_id로
        가짜 decision을 만들지 않고 명시적인 구성 오류를 던진다."""
        ctx = make_context()
        state = _base_state([], ctx)
        state["valid_catalog"] = []
        state["ranked"] = []
        state["candidates"] = []
        with pytest.raises(QuestCatalogConfigurationError):
            deterministic_fallback(state)

    def test_real_catalog_universal_default_is_team_signature_reaction(self):
        catalog = load_real_catalog()
        ctx = make_context(team_size=4)
        state = _base_state([], ctx)
        state["valid_catalog"] = catalog
        state["ranked"] = []
        state["candidates"] = []
        result = deterministic_fallback(state)
        assert result["final"].quest_id == "TEAM_SIGNATURE_REACTION"

    def test_never_returns_null_when_regular_pool_exists(self):
        """일반 후보(ranked/candidates)가 있으면 카탈로그 구성과 무관하게
        절대 null을 반환하지 않는다 (완전히 배정 가능한 퀘스트가 없는 구성
        오류 상황만 예외 — test_raises_configuration_error_when_catalog_has_no_universal 참고)."""
        quest = make_quest(quest_id="Q1")
        ctx = make_context()
        state = _base_state([quest], ctx)
        state["valid_catalog"] = []  # 폴백 검색용 전체 카탈로그가 비어 있어도
        state["ranked"] = [quest]  # pool이 있으면 그걸로 충분하다
        result = deterministic_fallback(state)
        assert result["final"] is not None
        assert result["final"].quest_id == "Q1"


# ──────────────────────────────────────────────
# 6. assign_quest 통합 — mock Bedrock
# ──────────────────────────────────────────────


class TestAssignQuestIntegration:
    @pytest.mark.asyncio
    async def test_agent_path_returns_selected_candidate(self, monkeypatch):
        catalog = load_real_catalog()
        ctx = make_context(
            team_size=4,
            matched_rule_ids=["TEAM_DIVERSE_COMMUNICATION", "TEAM_BALANCED_AGENCY"],
            context_tags=["FIRST_MEETING"],
        )

        def fake_output(_messages):
            return QuestSelectionOutput(
                quest_id="FIND_FIVE_COMMONALITIES",
                reason="첫 만남에 어울리는 가벼운 활동이에요.",
                intro_message="공통점 다섯 개 찾기부터 시작해봐요.",
                used_rule_ids=["TEAM_DIVERSE_COMMUNICATION"],
            )

        patch_bedrock(monkeypatch, fake_output)

        decision = await assign_quest(ctx, catalog)
        assert decision.quest_id == "FIND_FIVE_COMMONALITIES"
        assert decision.assignment_source == "AGENT"

    @pytest.mark.asyncio
    async def test_no_rule_id_match_at_all_returns_universal_fallback(self, monkeypatch):
        """일반 AUTO 퀘스트는 있지만 어떤 rule_id도 일치하지 않으면, 그중 아무거나
        고르지 않고 범용 퀘스트로 폴백한다 (실제 카탈로그 사용)."""
        catalog = load_real_catalog()
        # 실제 카탈로그의 어떤 best_for/also_for와도 겹치지 않는 matched_rule_ids
        ctx = make_context(matched_rule_ids=[], context_tags=[])

        def boom(_messages):
            raise AssertionError("맞춤 후보가 없으면 Bedrock을 호출하지 않아야 한다")

        patch_bedrock(monkeypatch, boom)
        decision = await assign_quest(ctx, catalog)
        assert decision.quest_id == "TEAM_SIGNATURE_REACTION"
        assert decision.assignment_source == "FALLBACK"

    @pytest.mark.asyncio
    async def test_universal_does_not_compete_when_a_matched_candidate_exists(self, monkeypatch):
        """best_for가 일치하는 맞춤 후보가 있으면, is_universal 퀘스트가 카탈로그에
        같이 있어도 절대 선택되지 않는다(경쟁하지 않는다)."""
        matched = make_quest(quest_id="MATCHED", best_for=["TEAM_BALANCED_AGENCY"])
        universal = make_universal_fallback_quest()
        ctx = make_context(matched_rule_ids=["TEAM_BALANCED_AGENCY"], team_size=4)

        def boom(_messages):
            raise AssertionError("단일 맞춤 후보면 Bedrock을 생략해야 한다")

        patch_bedrock(monkeypatch, boom)
        decision = await assign_quest(ctx, [matched, universal])
        assert decision.quest_id == "MATCHED"
        assert decision.assignment_source == "RULE"

    @pytest.mark.asyncio
    async def test_timeout_falls_back(self, monkeypatch):
        catalog = load_real_catalog()
        ctx = make_context(matched_rule_ids=["TEAM_DIVERSE_COMMUNICATION"])
        patch_bedrock(monkeypatch, TimeoutError("simulated bedrock timeout"))

        decision = await assign_quest(ctx, catalog)
        assert decision is not None
        assert decision.assignment_source == "FALLBACK"

    @pytest.mark.asyncio
    async def test_parsing_failure_falls_back(self, monkeypatch):
        catalog = load_real_catalog()
        ctx = make_context(matched_rule_ids=["TEAM_DIVERSE_COMMUNICATION"])
        patch_bedrock(monkeypatch, ValueError("simulated structured-output parse failure"))

        decision = await assign_quest(ctx, catalog)
        assert decision is not None
        assert decision.assignment_source == "FALLBACK"

    @pytest.mark.asyncio
    async def test_candidate_outside_list_triggers_retry_then_fallback(self, monkeypatch):
        catalog = load_real_catalog()
        ctx = make_context(matched_rule_ids=["TEAM_DIVERSE_COMMUNICATION"])

        def bad_output(_messages):
            return QuestSelectionOutput(
                quest_id="THIS_QUEST_DOES_NOT_EXIST",
                reason="이유",
                intro_message="소개",
                used_rule_ids=[],
            )

        patch_bedrock(monkeypatch, bad_output)
        decision = await assign_quest(ctx, catalog)
        assert decision.assignment_source == "FALLBACK"
        # 폴백이 고른 quest_id는 실제 카탈로그에 존재해야 한다.
        assert decision.quest_id in {q.quest_id for q in catalog}

    @pytest.mark.asyncio
    async def test_deterministic_across_repeated_calls_when_falling_back(self, monkeypatch):
        catalog = load_real_catalog()
        ctx = make_context(matched_rule_ids=["TEAM_DIVERSE_COMMUNICATION"], team_size=4)
        patch_bedrock(monkeypatch, TimeoutError("simulated timeout"))

        d1 = await assign_quest(ctx, catalog)
        d2 = await assign_quest(ctx, catalog)
        assert d1.quest_id == d2.quest_id
        assert d1.reason == d2.reason
        assert d1.used_rule_ids == d2.used_rule_ids

    @pytest.mark.asyncio
    async def test_no_eligible_candidates_returns_universal_default(self, monkeypatch):
        """일반 AUTO 후보가 하나도 없으면(모두 완료 처리) is_universal 퀘스트는
        애초에 filter_candidates 단계에서 제외되므로 ranked가 완전히 비고,
        deterministic_fallback이 카탈로그를 다시 뒤져 범용 퀘스트로 수렴한다."""
        catalog = load_real_catalog()
        all_ids = [q.quest_id for q in catalog if not q.is_universal]
        ctx = make_context(matched_rule_ids=[], completed_quest_ids=all_ids)
        patch_bedrock(monkeypatch, TimeoutError("should not be called"))

        decision = await assign_quest(ctx, catalog)
        assert decision.quest_id == "TEAM_SIGNATURE_REACTION"
        assert decision.assignment_source == "FALLBACK"

    @pytest.mark.asyncio
    async def test_single_matched_candidate_skips_bedrock_and_is_labeled_rule(self, monkeypatch):
        quest = make_quest(quest_id="ONLY_ONE", best_for=["TEAM_BALANCED_AGENCY"])
        ctx = make_context(matched_rule_ids=["TEAM_BALANCED_AGENCY"], team_size=4)

        def boom(_messages):
            raise AssertionError("Bedrock should have been skipped for a single candidate")

        patch_bedrock(monkeypatch, boom)
        decision = await assign_quest(ctx, [quest])
        assert decision.quest_id == "ONLY_ONE"
        # 단일 맞춤 후보 skip은 LLM이 고른 게 아니므로 AGENT로 기록하지 않고 RULE로 기록한다.
        assert decision.assignment_source == "RULE"

    @pytest.mark.asyncio
    async def test_raises_configuration_error_when_no_quest_assignable_at_all(self, monkeypatch):
        """일반 AUTO 후보도, is_universal 폴백도 전혀 없으면 존재하지 않는
        quest_id로 가짜 decision을 만들지 않고 예외를 던진다."""
        manual_only = make_quest(quest_id="MANUAL_ONLY", assignment="MANUAL")
        ctx = make_context()
        patch_bedrock(monkeypatch, TimeoutError("should not be called"))

        with pytest.raises(QuestCatalogConfigurationError):
            await assign_quest(ctx, [manual_only])

    @pytest.mark.asyncio
    @pytest.mark.parametrize("team_size", [3, 4, 10])
    async def test_team_sizes_3_4_10_produce_valid_decision(self, monkeypatch, team_size):
        catalog = load_real_catalog()
        ctx = make_context(team_size=team_size, matched_rule_ids=["TEAM_DIVERSE_COMMUNICATION"])
        patch_bedrock(monkeypatch, TimeoutError("force fallback for determinism"))

        decision = await assign_quest(ctx, catalog)
        assert decision is not None
        assert decision.quest_id in {q.quest_id for q in catalog}


# ──────────────────────────────────────────────
# 7. 프롬프트에 개인정보가 없는지
# ──────────────────────────────────────────────


class TestPromptPrivacy:
    def test_prompt_excludes_internal_and_personal_fields(self):
        catalog = load_real_catalog()
        candidates = catalog[:3]
        ctx = make_context(
            room_id="room-anonymous",
            matched_rule_ids=["TEAM_DIVERSE_COMMUNICATION"],
        )
        state: QuestAssignmentState = _base_state(candidates, ctx)
        state["ranked"] = candidates

        prompt = select_module._build_prompt(state)

        # 집계 distribution/matched_rule_ids/context_tags는 명세상 전달이 허용되므로
        # (SPEC §7) 포지션 라벨 자체가 아니라 "개인 단위" 필드 이름이 없는지 검사한다.
        forbidden_substrings = [
            "participant_id",
            "nickname",
            "self_positions",
            "team_grade",
            "internal_index",
            "caution",
            "survey",
        ]
        for token in forbidden_substrings:
            assert token not in prompt, f"프롬프트에 금지된 토큰이 포함됨: {token}"

        # 퀘스트 본문(steps/deliverable/completion_condition/materials/safety_notes)도 전달 금지
        for quest in candidates:
            for step in quest.steps:
                assert step not in prompt
            assert quest.deliverable not in prompt
            assert quest.completion_condition["description"] not in prompt

    def test_context_has_no_participant_level_fields(self):
        assert "participant_id" not in QuestMatchContext.model_fields
        assert "nickname" not in QuestMatchContext.model_fields
        assert "self_positions" not in QuestMatchContext.model_fields


# ──────────────────────────────────────────────
# 8. 기존 41개 AI Harness 회귀 (동일 프로세스 내 재확인용 스모크)
# ──────────────────────────────────────────────


class TestExistingHarnessImportsStillWork:
    def test_ai_schemas_and_engine_imports_untouched(self):
        from ai.schemas import CanonicalProfile, CommentGraphState  # noqa: F401
        from ai.nodes.validate import validate_comment  # noqa: F401
        from ai.nodes.fallback import render_fallback  # noqa: F401
        from app.services.chemistry.engine import (  # noqa: F401
            run_team_analysis,
            match_pair_rules,
            match_private_rules,
        )

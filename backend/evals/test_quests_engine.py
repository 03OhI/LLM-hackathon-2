"""
퀘스트 매칭 엔진 테스트 — knowledge_base/quests.yaml + engine.match_team_quests /
match_private_quests / get_quest_by_code에 대한 순수 함수 테스트.

test_engine.py와 동일한 스타일을 따른다 (결정성, 카탈로그 무결성, 매칭 조건 검증).
LLM/DB는 사용하지 않는다 — 카탈로그 문구는 이미 생성/작성되어 있고, 여기서는
"이 팀/이 사람에게 어떤 퀘스트가 매칭되는가"만 검증한다.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from ai.schemas import CanonicalProfile

from app.services.chemistry.engine import (
    compute_distribution,
    get_quest_by_code,
    load_quests,
    match_private_quests,
    match_team_quests,
)


def _profile(pid: str, planning: str, agency: str, conflict: str, communication: str) -> CanonicalProfile:
    return CanonicalProfile(
        participant_id=pid,
        source="DECLARED_TYPE",
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


# ──────────────────────────────────────────────
# 카탈로그 무결성
# ──────────────────────────────────────────────


def test_catalog_loads_with_expected_keys():
    catalog = load_quests()
    assert "team_quests" in catalog
    assert "personal_quests" in catalog
    assert len(catalog["team_quests"]) > 0
    assert len(catalog["personal_quests"]) > 0


def test_catalog_items_have_required_fields():
    catalog = load_quests()
    for scope_key in ("team_quests", "personal_quests"):
        for item in catalog[scope_key]:
            assert item.get("quest_code"), f"missing quest_code in {scope_key}"
            assert item.get("when"), f"missing when-condition for {item.get('quest_code')}"
            assert item.get("title"), f"missing title for {item.get('quest_code')}"
            assert item.get("description"), f"missing description for {item.get('quest_code')}"
            assert item.get("action"), f"missing action for {item.get('quest_code')}"


def test_quest_codes_are_unique_within_each_scope():
    catalog = load_quests()
    for scope_key in ("team_quests", "personal_quests"):
        codes = [item["quest_code"] for item in catalog[scope_key]]
        assert len(codes) == len(set(codes)), f"duplicate quest_code found in {scope_key}"


def test_team_quest_conditions_use_known_vocabulary():
    """team_rules.yaml과 동일한 axis/condition 어휘만 사용해야 한다 (오타 방지)."""
    known_axes = {"planning", "agency", "conflict", "communication"}
    known_conditions = {
        "balanced", "majority_upper", "majority_lower",
        "all_upper", "all_lower", "has_upper", "has_lower", "no_upper", "no_lower",
    }
    catalog = load_quests()
    for item in catalog["team_quests"]:
        when = item["when"]
        assert when.get("axis") in known_axes, item["quest_code"]
        assert when.get("condition") in known_conditions, item["quest_code"]


# ──────────────────────────────────────────────
# 팀 퀘스트 매칭
# ──────────────────────────────────────────────


def test_match_team_quests_balanced_agency_matches():
    profiles = [
        _profile("p1", "PLANNER", "DRIVER", "HARMONIZER", "DIRECT"),
        _profile("p2", "PLANNER", "SUPPORTER", "HARMONIZER", "TACTFUL"),
    ]
    distribution = compute_distribution(profiles)
    candidates = match_team_quests(distribution)
    codes = [c.quest_code for c in candidates]
    assert "TEAM_Q_BALANCED_AGENCY" in codes


def test_match_team_quests_all_planner_matches_overload_quest():
    profiles = [
        _profile(f"p{i}", "PLANNER", "DRIVER", "HARMONIZER", "DIRECT") for i in range(4)
    ]
    distribution = compute_distribution(profiles)
    candidates = match_team_quests(distribution)
    codes = [c.quest_code for c in candidates]
    assert "TEAM_Q_PLANNING_OVERLOAD" in codes


def test_match_team_quests_no_driver_matches_low_driver_quest():
    profiles = [
        _profile("p1", "PLANNER", "SUPPORTER", "HARMONIZER", "TACTFUL"),
        _profile("p2", "ADAPTER", "SUPPORTER", "CONFRONTER", "DIRECT"),
    ]
    distribution = compute_distribution(profiles)
    candidates = match_team_quests(distribution)
    codes = [c.quest_code for c in candidates]
    assert "TEAM_Q_LOW_DRIVER" in codes


def test_match_team_quests_is_deterministic():
    profiles = [
        _profile("p1", "PLANNER", "DRIVER", "HARMONIZER", "DIRECT"),
        _profile("p2", "ADAPTER", "SUPPORTER", "CONFRONTER", "TACTFUL"),
        _profile("p3", "PLANNER", "SUPPORTER", "HARMONIZER", "DIRECT"),
    ]
    distribution = compute_distribution(profiles)
    first = [c.quest_code for c in match_team_quests(distribution)]
    second = [c.quest_code for c in match_team_quests(distribution)]
    assert first == second


def test_match_team_quests_candidates_carry_content():
    profiles = [
        _profile("p1", "PLANNER", "DRIVER", "HARMONIZER", "DIRECT"),
        _profile("p2", "ADAPTER", "SUPPORTER", "CONFRONTER", "TACTFUL"),
    ]
    distribution = compute_distribution(profiles)
    candidates = match_team_quests(distribution)
    assert len(candidates) > 0
    for c in candidates:
        assert c.scope == "TEAM"
        assert c.title
        assert c.description
        assert c.action


# ──────────────────────────────────────────────
# 개인 퀘스트 매칭
# ──────────────────────────────────────────────


def test_match_private_quests_planner_self_only():
    profile = _profile("p1", "PLANNER", "DRIVER", "HARMONIZER", "DIRECT")
    distribution = compute_distribution([profile])
    candidates = match_private_quests(profile, distribution, team_size=1)
    codes = [c.quest_code for c in candidates]
    assert "PERSONAL_Q_PLANNER_SHARE_PLAN" in codes
    assert "PERSONAL_Q_ADAPTER_TRY_DETOUR" not in codes


def test_match_private_quests_direct_in_tactful_team_context():
    self_profile = _profile("self", "PLANNER", "DRIVER", "HARMONIZER", "DIRECT")
    team_profiles = [
        self_profile,
        _profile("p2", "PLANNER", "SUPPORTER", "HARMONIZER", "TACTFUL"),
        _profile("p3", "ADAPTER", "SUPPORTER", "HARMONIZER", "TACTFUL"),
    ]
    distribution = compute_distribution(team_profiles)
    candidates = match_private_quests(self_profile, distribution, team_size=3)
    codes = [c.quest_code for c in candidates]
    assert "PERSONAL_Q_DIRECT_IN_TACTFUL_TEAM" in codes


def test_match_private_quests_candidates_carry_content():
    profile = _profile("p1", "PLANNER", "DRIVER", "HARMONIZER", "DIRECT")
    distribution = compute_distribution([profile])
    candidates = match_private_quests(profile, distribution, team_size=1)
    assert len(candidates) > 0
    for c in candidates:
        assert c.scope == "PERSONAL"
        assert c.title
        assert c.description
        assert c.action


# ──────────────────────────────────────────────
# 카탈로그 단건 조회
# ──────────────────────────────────────────────


def test_get_quest_by_code_team_found():
    quest = get_quest_by_code("TEAM", "TEAM_Q_BALANCED_AGENCY")
    assert quest is not None
    assert quest.quest_code == "TEAM_Q_BALANCED_AGENCY"
    assert quest.scope == "TEAM"


def test_get_quest_by_code_personal_found():
    quest = get_quest_by_code("PERSONAL", "PERSONAL_Q_PLANNER_SHARE_PLAN")
    assert quest is not None
    assert quest.scope == "PERSONAL"


def test_get_quest_by_code_unknown_returns_none():
    assert get_quest_by_code("TEAM", "NOT_A_REAL_CODE") is None
    assert get_quest_by_code("PERSONAL", "NOT_A_REAL_CODE") is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

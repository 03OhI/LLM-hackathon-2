"""
V5.2 퀘스트 카탈로그 검수 — knowledge_base/quests.json 데이터 전용 테스트

이 파일은 데이터 작업자가 quests.json/quest.schema.json만 고치면서 회귀를
잡을 수 있도록 만든 것이다. app/services, app/api, ai/** 코드는 import하지
않는다(카탈로그 JSON과 team_rules.yaml만 읽는다).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

BACKEND_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(BACKEND_ROOT))

KNOWLEDGE_BASE_DIR = BACKEND_ROOT / "knowledge_base"

DEFAULT_CONTEXT_TAGS = {"FIRST_MEETING", "HACKATHON"}


def _load_quests() -> list[dict]:
    return json.loads((KNOWLEDGE_BASE_DIR / "quests.json").read_text(encoding="utf-8"))


def _load_team_rule_ids() -> set[str]:
    data = yaml.safe_load((KNOWLEDGE_BASE_DIR / "team_rules.yaml").read_text(encoding="utf-8"))
    return {r["rule_id"] for r in data["rules"]}


def _by_id(quests: list[dict], quest_id: str) -> dict:
    return next(q for q in quests if q["quest_id"] == quest_id)


def _eligible_auto(quests: list[dict], rule_id: str, team_size: int = 3) -> list[dict]:
    out = []
    for q in quests:
        if not q.get("is_active", True):
            continue
        if q["assignment"] != "AUTO":
            continue
        if q["disclosure_level"] not in ("LOW", "MEDIUM"):
            continue
        lo, hi = q["team_size"]["min"], q["team_size"]["max"]
        if not (lo <= team_size <= hi):
            continue
        if rule_id in q.get("avoid_for", []):
            continue
        out.append(q)
    return out


def _tailored(candidates: list[dict], rule_id: str) -> list[dict]:
    return [q for q in candidates if rule_id in q.get("best_for", []) or rule_id in q.get("also_for", [])]


# ──────────────────────────────────────────────
# 신규 퀘스트: CONFLICT_FIRST_SENTENCE
# ──────────────────────────────────────────────


def test_conflict_first_sentence_quest_added_correctly():
    quests = _load_quests()
    quest_ids = [q["quest_id"] for q in quests]
    assert quest_ids.count("CONFLICT_FIRST_SENTENCE") == 1

    q = _by_id(quests, "CONFLICT_FIRST_SENTENCE")
    assert q["category"] == "TEAM_SAFETY"
    assert q["assignment"] == "AUTO"
    assert q["disclosure_level"] == "LOW"
    assert q["is_universal"] is False
    assert q["is_active"] is True
    assert q["team_size"] == {"min": 3, "max": 10}
    assert set(q["best_for"]) == {"TEAM_CONFRONTER_MAJORITY", "TEAM_BALANCED_CONFLICT"}
    assert set(q["also_for"]) == {"TEAM_HARMONIZER_PRESENCE"}
    assert q["avoid_for"] == []
    assert set(q["context_tags"]) == {"FIRST_MEETING", "HACKATHON"}

    check_shapes = {(c["type"], c["scope"]) for c in q["completion_condition"]["checks"]}
    assert ("VOTE", "PER_MEMBER") in check_shapes
    assert ("TEXT_SUBMIT", "TEAM") in check_shapes
    assert any(c["scope"] == "PER_MEMBER" for c in q["completion_condition"]["checks"])


# ──────────────────────────────────────────────
# 전체 카탈로그 검수 (요청 §2 체크리스트)
# ──────────────────────────────────────────────


def test_all_quests_support_three_to_ten():
    for q in _load_quests():
        lo, hi = q["team_size"]["min"], q["team_size"]["max"]
        assert 3 <= lo <= hi <= 10, q["quest_id"]


def test_high_disclosure_never_auto():
    for q in _load_quests():
        if q["disclosure_level"] == "HIGH":
            assert q["assignment"] == "MANUAL", q["quest_id"]


def test_rule_id_fields_reference_real_team_rules_only():
    team_rule_ids = _load_team_rule_ids()
    for q in _load_quests():
        for field in ("best_for", "also_for", "avoid_for"):
            for rid in q.get(field, []):
                assert rid in team_rule_ids, f"{q['quest_id']}.{field} has unknown rule_id: {rid}"
                assert rid.isupper() and " " not in rid, f"{q['quest_id']}.{field} looks like natural language: {rid}"


def test_universal_quests_have_empty_avoid_for():
    for q in _load_quests():
        if q["is_universal"]:
            assert q["avoid_for"] == [], q["quest_id"]


def test_every_quest_has_per_member_check():
    for q in _load_quests():
        checks = q["completion_condition"]["checks"]
        assert any(c["scope"] == "PER_MEMBER" for c in checks), q["quest_id"]


def test_no_duplicate_quest_ids():
    quests = _load_quests()
    ids = [q["quest_id"] for q in quests]
    assert len(ids) == len(set(ids))


def test_large_team_auto_coverage_at_least_four():
    quests = _load_quests()
    for size in (9, 10):
        count = sum(
            1
            for q in quests
            if q.get("is_active", True)
            and q["assignment"] == "AUTO"
            and q["disclosure_level"] in ("LOW", "MEDIUM")
            and q["team_size"]["min"] <= size <= q["team_size"]["max"]
        )
        assert count >= 4, f"{size}명 AUTO 후보가 {count}개뿐"


# ──────────────────────────────────────────────
# rule_id 커버리지 회귀 고정
# ──────────────────────────────────────────────


def test_conflict_rule_ids_now_have_tailored_auto_coverage():
    """CONFLICT_FIRST_SENTENCE 추가 전에는 TEAM_CONFRONTER_MAJORITY가
    맞춤 AUTO 후보 0개였다 — 이 테스트로 그 회귀를 고정한다."""
    quests = _load_quests()
    for rule_id in ("TEAM_CONFRONTER_MAJORITY", "TEAM_BALANCED_CONFLICT"):
        candidates = _eligible_auto(quests, rule_id)
        tailored = _tailored(candidates, rule_id)
        assert tailored, f"{rule_id}에 맞춤 AUTO 후보가 없음"


def test_known_universal_fallback_only_rule_ids():
    """맞춤 AUTO 후보가 없어 범용 퀘스트로만 커버되는 rule_id 목록을 고정한다.

    이 집합이 바뀌면(늘거나 줄면) 의도한 데이터 변경인지 확인해야 하므로
    실패하도록 둔다 — 조용히 커버리지가 나빠지는 것을 막기 위함이다.
    """
    quests = _load_quests()
    team_rule_ids = sorted(_load_team_rule_ids())

    universal_only = set()
    for rule_id in team_rule_ids:
        candidates = _eligible_auto(quests, rule_id)
        tailored = _tailored(candidates, rule_id)
        if not tailored:
            universal_only.add(rule_id)

    assert universal_only == {"TEAM_LOW_DRIVER", "TEAM_SUPPORTER_MAJORITY", "TEAM_ADAPTER_MAJORITY"}

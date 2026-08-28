"""
퀘스트 카탈로그 검증 (SPEC_V5.2 §4, §10 "카탈로그" 인수 기준)

AI 그래프에 전달하기 전에 카탈로그를 검증해 다음을 배제한다:
- 알 수 없는/자연어 rule_id, 알 수 없는 context tag, 중복 quest_id,
  is_universal 규칙 위반, HIGH+AUTO 조합, PER_MEMBER 체크 누락.
- (카탈로그 전체 단위, quest_id=None) 3~10명 전체 범위를 지원하는
  is_universal/is_active/AUTO/disclosure LOW|MEDIUM 폴백 퀘스트가 하나도 없으면
  errors에 추가한다(warning이 아니다) — 이게 없으면 맞춤 후보가 없는 요청은
  배정 자체가 불가능해질 수 있는 심각한 데이터 결함이기 때문이다.

`app/services/quests/validate_quests.py`는 quests.json 원본(dict)을
JSON Schema로 검증하는 별도 계층이다. 이 모듈은 이미 QuestTemplate으로
파싱되어 assign_quest()에 들어오는 객체에 대한 마지막 방어선이며,
DB나 ORM에 의존하지 않고 team_rules.yaml만 파일로 읽는다.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

import yaml

from .schemas import ALLOWED_CONTEXT_TAGS, CatalogIssue, CatalogValidationResult, QuestTemplate

TEAM_RULES_PATH = (
    Path(__file__).resolve().parents[2] / "knowledge_base" / "team_rules.yaml"
)

# rule_id는 항상 대문자 스네이크케이스 식별자다. 공백/조사/한글이 섞인 값은
# team_rules.yaml에 존재할 수 없으므로 이 패턴만으로도 자연어 값을 걸러낸다.
_RULE_ID_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]*$")

_PER_MEMBER_SCOPE = "PER_MEMBER"

# 9~10명 팀을 지원해야 하는 자동 퀘스트 최소 개수 (SPEC §4.4)
_LARGE_TEAM_MIN_AUTO_QUESTS = 4

# 범용 폴백에 필요한 팀 인원 커버리지 — 이 범위 전체를 지원하는 is_universal
# 퀘스트가 최소 하나 없으면 배정 불가능한 team_size가 생길 수 있다.
_UNIVERSAL_FALLBACK_MIN_TEAM_SIZE = 3
_UNIVERSAL_FALLBACK_MAX_TEAM_SIZE = 10


@lru_cache()
def load_team_rule_ids(path: Path | None = None) -> frozenset[str]:
    """team_rules.yaml에서 rule_id 전체 집합을 로드해 allow-list로 사용한다."""
    target = path or TEAM_RULES_PATH
    with open(target, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    rule_ids = {
        rule.get("rule_id", "")
        for rule in data.get("rules", [])
        if rule.get("rule_id")
    }
    return frozenset(rule_ids)


def _team_size_range(quest: QuestTemplate) -> tuple[int | None, int | None]:
    size = quest.team_size or {}
    return size.get("min"), size.get("max")


def _completion_checks(quest: QuestTemplate) -> list[dict]:
    condition = quest.completion_condition or {}
    return condition.get("checks", []) or []


def _check_rule_id_field(
    field_name: str,
    values: list[str],
    allowed_rule_ids: frozenset[str],
    quest_id: str,
) -> list[CatalogIssue]:
    issues: list[CatalogIssue] = []
    for value in values:
        if not _RULE_ID_PATTERN.match(value):
            issues.append(
                CatalogIssue(
                    quest_id=quest_id,
                    code="NATURAL_LANGUAGE_VALUE",
                    message=f"{field_name}에 자연어/비정형 값이 있다: {value!r}",
                )
            )
        elif value not in allowed_rule_ids:
            issues.append(
                CatalogIssue(
                    quest_id=quest_id,
                    code="UNKNOWN_RULE_ID",
                    message=f"{field_name}의 rule_id가 team_rules.yaml에 없다: {value!r}",
                )
            )
    return issues


def _check_context_tags(quest: QuestTemplate) -> list[CatalogIssue]:
    issues: list[CatalogIssue] = []
    for tag in quest.context_tags:
        if tag not in ALLOWED_CONTEXT_TAGS:
            issues.append(
                CatalogIssue(
                    quest_id=quest.quest_id,
                    code="UNKNOWN_CONTEXT_TAG",
                    message=f"허용되지 않은 context tag: {tag!r}",
                )
            )
    return issues


def _validate_single(
    quest: QuestTemplate, allowed_rule_ids: frozenset[str]
) -> list[CatalogIssue]:
    issues: list[CatalogIssue] = []

    for field_name in ("best_for", "also_for", "avoid_for"):
        issues.extend(
            _check_rule_id_field(
                field_name, getattr(quest, field_name), allowed_rule_ids, quest.quest_id
            )
        )

    issues.extend(_check_context_tags(quest))

    if quest.is_universal and quest.avoid_for:
        issues.append(
            CatalogIssue(
                quest_id=quest.quest_id,
                code="UNIVERSAL_WITH_AVOID_FOR",
                message="is_universal=true인 퀘스트는 avoid_for가 비어 있어야 한다",
            )
        )

    if quest.disclosure_level == "HIGH" and quest.assignment != "MANUAL":
        issues.append(
            CatalogIssue(
                quest_id=quest.quest_id,
                code="HIGH_DISCLOSURE_MUST_BE_MANUAL",
                message="disclosure_level=HIGH인 퀘스트는 assignment=MANUAL이어야 한다",
            )
        )

    lo, hi = _team_size_range(quest)
    if not isinstance(lo, int) or not isinstance(hi, int) or lo > hi or lo < 3 or hi > 10:
        issues.append(
            CatalogIssue(
                quest_id=quest.quest_id,
                code="INVALID_TEAM_SIZE_RANGE",
                message=f"team_size 범위가 3~10을 벗어나거나 형식이 잘못됨: {quest.team_size!r}",
            )
        )

    checks = _completion_checks(quest)
    has_per_member_check = any(
        isinstance(c, dict) and c.get("scope") == _PER_MEMBER_SCOPE for c in checks
    )
    if not has_per_member_check:
        issues.append(
            CatalogIssue(
                quest_id=quest.quest_id,
                code="MISSING_PER_MEMBER_CHECK",
                message="completion_condition.checks에 PER_MEMBER 체크가 최소 하나 필요하다",
            )
        )

    return issues


def validate_catalog(
    catalog: list[QuestTemplate],
    allowed_rule_ids: frozenset[str] | None = None,
) -> CatalogValidationResult:
    """카탈로그를 검증하고, 구조적으로 유효한 항목만 valid_templates로 반환한다.

    개별 퀘스트의 무효 항목은 배제되며(제외), errors에 사유가 남는다.
    카탈로그 전체 단위 이슈는 심각도에 따라 나뉜다:
    - errors (하드 실패): 범용 폴백 퀘스트가 하나도 없음(NO_UNIVERSAL_FALLBACK_AVAILABLE).
    - warnings (품질 경고, 배정 흐름은 막지 않음): 9~10명 지원 자동 퀘스트 커버리지 부족.
    """
    allow_list = allowed_rule_ids if allowed_rule_ids is not None else load_team_rule_ids()

    errors: list[CatalogIssue] = []
    warnings: list[CatalogIssue] = []

    seen_ids: dict[str, int] = {}
    for quest in catalog:
        seen_ids[quest.quest_id] = seen_ids.get(quest.quest_id, 0) + 1

    duplicate_ids = {qid for qid, count in seen_ids.items() if count > 1}
    for qid in duplicate_ids:
        errors.append(
            CatalogIssue(
                quest_id=qid,
                code="DUPLICATE_QUEST_ID",
                message=f"quest_id가 카탈로그에 중복 존재한다: {qid!r}",
            )
        )

    valid_templates: list[QuestTemplate] = []
    already_admitted: set[str] = set()

    for quest in catalog:
        if quest.quest_id in duplicate_ids:
            continue

        quest_issues = _validate_single(quest, allow_list)
        if quest_issues:
            errors.extend(quest_issues)
            continue

        if quest.quest_id in already_admitted:
            continue
        already_admitted.add(quest.quest_id)
        valid_templates.append(quest)

    has_universal_fallback = any(
        quest.is_universal
        and quest.is_active
        and quest.assignment == "AUTO"
        and quest.disclosure_level in ("LOW", "MEDIUM")
        and (quest.team_size or {}).get("min", 99) <= _UNIVERSAL_FALLBACK_MIN_TEAM_SIZE
        and (quest.team_size or {}).get("max", 0) >= _UNIVERSAL_FALLBACK_MAX_TEAM_SIZE
        for quest in valid_templates
    )
    if not has_universal_fallback:
        errors.append(
            CatalogIssue(
                code="NO_UNIVERSAL_FALLBACK_AVAILABLE",
                message=(
                    "is_universal=true이고 is_active/AUTO/disclosure LOW|MEDIUM이며 "
                    f"{_UNIVERSAL_FALLBACK_MIN_TEAM_SIZE}~{_UNIVERSAL_FALLBACK_MAX_TEAM_SIZE}명 "
                    "전체 범위를 지원하는 범용 폴백 퀘스트가 카탈로그에 하나도 없다. "
                    "일반 맞춤 후보가 없는 요청은 배정에 실패할 수 있다."
                ),
            )
        )

    large_team_auto_count = sum(
        1
        for quest in valid_templates
        if quest.is_active
        and quest.assignment == "AUTO"
        and (quest.team_size or {}).get("max", 0) >= 9
    )
    if large_team_auto_count < _LARGE_TEAM_MIN_AUTO_QUESTS:
        warnings.append(
            CatalogIssue(
                code="LARGE_TEAM_AUTO_COVERAGE_LOW",
                message=(
                    f"9~10명 지원 자동 퀘스트가 {large_team_auto_count}개로 "
                    f"최소 {_LARGE_TEAM_MIN_AUTO_QUESTS}개 기준에 못 미친다"
                ),
            )
        )

    return CatalogValidationResult(
        valid_templates=valid_templates,
        errors=errors,
        warnings=warnings,
    )

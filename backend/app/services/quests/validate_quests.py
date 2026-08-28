"""
퀘스트 카탈로그 검증 — SPEC_V5_CONTEST_QUEST_AGENT.md §4.3, §4.4, §10

두 단계로 검증한다.
1. quest.schema.json(JSON Schema)으로 raw dict 구조를 검증한다 — 데이터 작업자가
   quests.json을 고칠 때 JSON Schema 하나만 보고도 검증할 수 있게 하기 위함이다.
2. 스키마를 통과한 항목만 ai.quest_assignment.schemas.QuestTemplate으로 파싱하고,
   ai.quest_assignment.catalog.validate_catalog()(AI 담당자가 구현한 §4.3/§4.4
   비즈니스 규칙 검증)에 그대로 위임한다 — team_rules.yaml rule_id, is_universal/
   avoid_for, HIGH+MANUAL, PER_MEMBER 체크 존재 여부 등을 백엔드가 다시 구현하지 않는다.

개별 퀘스트 오류 → 그 퀘스트만 배정 후보에서 제외한다 (카탈로그 전체를 막지 않는다).

CLI로도 실행 가능하다:
    python -m app.services.quests.validate_quests
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

import jsonschema

from ai.quest_assignment.catalog import validate_catalog as ai_validate_catalog
from ai.quest_assignment.schemas import QuestTemplate

KNOWLEDGE_BASE_DIR = Path(__file__).parent.parent.parent.parent / "knowledge_base"
QUEST_SCHEMA_PATH = KNOWLEDGE_BASE_DIR / "quest.schema.json"
QUESTS_JSON_PATH = KNOWLEDGE_BASE_DIR / "quests.json"


@dataclass
class QuestValidationResult:
    schema_errors: dict[str, list[str]] = field(default_factory=dict)  # quest_id -> errors
    business_errors: dict[str, list[str]] = field(default_factory=dict)  # quest_id -> errors
    catalog_warnings: list[str] = field(default_factory=list)  # 카탈로그 전체 품질 경고
    valid_templates: list[QuestTemplate] = field(default_factory=list)

    @property
    def invalid_quest_ids(self) -> set[str]:
        return set(self.schema_errors) | set(self.business_errors)

    def all_errors(self) -> list[str]:
        errors = []
        for qid, errs in {**self.schema_errors, **self.business_errors}.items():
            for e in errs:
                errors.append(f"{qid}: {e}")
        errors.extend(self.catalog_warnings)
        return errors


def validate_catalog(quests: list[dict]) -> QuestValidationResult:
    with open(QUEST_SCHEMA_PATH, "r", encoding="utf-8") as f:
        schema = json.load(f)

    result = QuestValidationResult()

    structurally_valid: list[QuestTemplate] = []
    for quest in quests:
        quest_id = quest.get("quest_id", f"<no-id-{len(structurally_valid) + len(result.schema_errors)}>")

        schema_errors = [e.message for e in jsonschema.Draft7Validator(schema).iter_errors(quest)]
        if schema_errors:
            result.schema_errors[quest_id] = schema_errors
            continue

        try:
            structurally_valid.append(QuestTemplate(**quest))
        except Exception as e:  # noqa: BLE001 — pydantic 파싱 실패도 스키마 오류로 취급
            result.schema_errors[quest_id] = [str(e)]

    ai_result = ai_validate_catalog(structurally_valid)

    errors_by_quest: dict[str, list[str]] = {}
    for issue in ai_result.errors:
        errors_by_quest.setdefault(issue.quest_id or "<catalog>", []).append(
            f"{issue.code}: {issue.message}"
        )
    result.business_errors = errors_by_quest
    result.catalog_warnings = [f"{issue.code}: {issue.message}" for issue in ai_result.warnings]
    result.valid_templates = ai_result.valid_templates

    return result


def load_and_validate() -> QuestValidationResult:
    with open(QUESTS_JSON_PATH, "r", encoding="utf-8") as f:
        quests = json.load(f)
    return validate_catalog(quests)


def main() -> int:
    result = load_and_validate()
    errors = result.all_errors()
    if errors:
        print(f"퀘스트 카탈로그 검증 실패 ({len(result.invalid_quest_ids)}개 항목 오류):")
        for e in errors:
            print(f"  - {e}")
        return 1
    print(f"퀘스트 카탈로그 검증 통과 ({len(result.valid_templates)}개).")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""
load_context / validate_catalog 노드 (SPEC_V5.2 §5.2 mermaid A→B)

load_context: 그래프 상태 초기 정규화.
validate_catalog: team_rules.yaml allow-list 기준으로 카탈로그를 검증하고
                   구조적으로 유효한 항목만 이후 단계로 넘긴다.
"""

from __future__ import annotations

import logging

from ..catalog import validate_catalog as run_catalog_validation
from ..schemas import QuestAssignmentState

logger = logging.getLogger(__name__)


async def load_context(state: QuestAssignmentState) -> dict:
    """입력 컨텍스트를 정규화한다. matched_rule_ids 중복만 제거한다."""
    context = state["context"]
    deduped_rule_ids = list(dict.fromkeys(context.matched_rule_ids))

    logger.info(
        "load_context: room_id=%s, team_size=%d, catalog_size=%d",
        context.room_id,
        context.team_size,
        len(state["raw_catalog"]),
    )

    if deduped_rule_ids != context.matched_rule_ids:
        context = context.model_copy(update={"matched_rule_ids": deduped_rule_ids})

    return {"context": context}


async def validate_catalog_node(state: QuestAssignmentState) -> dict:
    """카탈로그를 검증해 valid_catalog / catalog_errors를 채운다."""
    result = run_catalog_validation(state["raw_catalog"])

    if result.errors:
        logger.warning(
            "validate_catalog: %d개 항목 배제됨: %s",
            len({issue.quest_id for issue in result.errors if issue.quest_id}),
            [f"{issue.quest_id}:{issue.code}" for issue in result.errors],
        )
    if result.warnings:
        logger.warning(
            "validate_catalog: 카탈로그 품질 경고: %s",
            [issue.message for issue in result.warnings],
        )

    return {
        "valid_catalog": result.valid_templates,
        "catalog_errors": [f"{issue.code}: {issue.message}" for issue in result.errors],
    }

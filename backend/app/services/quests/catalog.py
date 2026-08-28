"""
퀘스트 카탈로그 로더 — SPEC_V5 §2, §4

knowledge_base/quests.json(정본)을 읽어 검증하고, 유효한 퀘스트만
app.services.quests.schemas.QuestTemplate 목록으로 노출한다.

카탈로그 오류가 있는 개별 퀘스트는 자동 배정 후보에서 제외한다 — 서버 전체를
죽이지 않는다("카탈로그 오류가 있으면 잘못된 퀘스트를 자동 배정하지 마").
"""

from __future__ import annotations

import logging

from sqlmodel import Session as DBSession
from sqlmodel import select

from app.models import QuestTemplateRecord
from app.services.quests.schemas import QuestTemplate
from app.services.quests.validate_quests import load_and_validate

logger = logging.getLogger(__name__)

_cache: list[QuestTemplate] | None = None


def _build_catalog() -> list[QuestTemplate]:
    result = load_and_validate()

    if result.invalid_quest_ids:
        logger.error(
            "퀘스트 카탈로그에 오류가 있는 항목을 제외합니다: %s", sorted(result.invalid_quest_ids)
        )
    if result.catalog_warnings:
        for w in result.catalog_warnings:
            logger.warning("퀘스트 카탈로그 품질 경고: %s", w)

    return result.valid_templates


def load_quest_catalog(*, force_reload: bool = False) -> list[QuestTemplate]:
    """검증을 통과한 QuestTemplate 전체 목록 (is_active 무관, 배정 후보 필터는 ai.quest_assignment 책임)."""
    global _cache
    if _cache is None or force_reload:
        _cache = _build_catalog()
    return _cache


def get_active_quest_templates() -> list[QuestTemplate]:
    return [q for q in load_quest_catalog() if q.is_active]


def get_quest_template(quest_id: str) -> QuestTemplate | None:
    for q in load_quest_catalog():
        if q.quest_id == quest_id:
            return q
    return None


def sync_catalog_to_db(db: DBSession) -> None:
    """검증 통과한 퀘스트를 QuestTemplateRecord(DB 미러)에 upsert한다.

    서버 시작 시 호출되며, quests.json에서 사라진 quest_id는 is_active=False로
    내려 배정 후보에서 자연스럽게 제외한다(기존 QuestAssignment의 FK는 유지).
    """
    templates = load_quest_catalog(force_reload=True)
    seen_ids = set()

    for template in templates:
        seen_ids.add(template.quest_id)
        record = db.get(QuestTemplateRecord, template.quest_id)
        payload_json = template.model_dump_json()
        if record is None:
            record = QuestTemplateRecord(
                quest_id=template.quest_id,
                payload_json=payload_json,
                version=template.version,
                is_active=template.is_active,
            )
        else:
            record.payload_json = payload_json
            record.version = template.version
            record.is_active = template.is_active
        db.add(record)

    existing = db.exec(select(QuestTemplateRecord)).all()
    for record in existing:
        if record.quest_id not in seen_ids and record.is_active:
            record.is_active = False
            db.add(record)

    db.commit()

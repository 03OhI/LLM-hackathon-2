"""
퀘스트 배정 AI 모듈 (SPEC_V5.2 §5)

공개 계약 (canonical import 경로):
    from ai.quest_assignment import assign_quest
    from ai.quest_assignment.schemas import (
        QuestMatchContext, QuestTemplate, QuestAssignmentDecision,
    )
    from ai.quest_assignment.errors import QuestCatalogConfigurationError

DB session/ORM에 의존하지 않는 순수 AI 모듈이다.
"""

from __future__ import annotations

from .errors import QuestCatalogConfigurationError
from .graph import assign_quest
from .schemas import QuestAssignmentDecision, QuestMatchContext, QuestTemplate

__all__ = [
    "assign_quest",
    "QuestMatchContext",
    "QuestTemplate",
    "QuestAssignmentDecision",
    "QuestCatalogConfigurationError",
]

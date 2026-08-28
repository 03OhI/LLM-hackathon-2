"""
퀘스트 배정 AI 모듈 전용 예외.

DTO(app/services/quests/schemas.py)는 건드리지 않는다 — 이 예외는 그 계약의
일부가 아니라, assign_quest()가 정상적으로 반환할 수 없는(=유효한
QuestAssignmentDecision을 만들 수 없는) 카탈로그 구성 오류를 호출자에게
명확히 알리기 위한 내부 신호다.
"""

from __future__ import annotations


class QuestCatalogConfigurationError(RuntimeError):
    """카탈로그에 배정 가능한 퀘스트가 하나도 없을 때 발생한다.

    일반 AUTO 후보도 없고 is_universal 폴백 후보도 없는 경우에만 발생한다 —
    이 상태에서는 존재하지 않는 quest_id로 "저장 가능해 보이는" 가짜
    QuestAssignmentDecision을 만들어 반환하지 않는다. 호출자는 이 예외를
    데이터/카탈로그 구성 오류로 처리해야 한다(예: 데이터팀에 quests.json
    점검 요청, 서비스 레이어에서 명시적 오류 응답으로 변환).
    """

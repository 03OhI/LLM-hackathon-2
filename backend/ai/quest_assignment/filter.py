"""
결정론적 후보 필터 (SPEC_V5.2 §5.1 — 최종 카탈로그 정책 반영)

두 단계로 나뉜다.

1. filter_candidates: 안전·인원 필터. 비활성, MANUAL, 인원 범위 불일치,
   disclosure_level=HIGH, avoid_for 겹침, 완료 처리된 퀘스트를 제외한다.
   is_universal=true인 퀘스트도 이 단계에서 제외한다 — 범용 퀘스트는 일반
   AUTO 후보와 경쟁하지 않으며, 적합한 일반 후보가 하나도 없을 때만
   nodes/fallback.py가 카탈로그를 다시 뒤져 폴백으로만 사용한다.

2. matched_candidates: "안전·인원 조건을 통과했다"만으로는 Bedrock 후보가
   되지 않는다. quest.best_for 또는 quest.also_for가 context.matched_rule_ids와
   하나라도 겹쳐야만 "맞춤 후보"로 인정한다. context_tags만 겹치는 것은
   맞춤 후보로 인정하지 않는다 — context_tags는 이미 규칙이 일치한 후보들
   사이의 보조 정렬(scoring.score_candidate)에만 쓰인다. 맞춤 후보가 0개면
   일반 무관 퀘스트를 선택하지 않고 is_universal 폴백으로 넘어간다
   (graph.py의 라우팅이 candidates=[]를 그대로 처리한다).

순수 함수이며 LLM을 호출하지 않는다.
"""

from __future__ import annotations

from .schemas import QuestMatchContext, QuestTemplate


def team_size_matches(quest: QuestTemplate, team_size: int) -> bool:
    size = quest.team_size or {}
    lo, hi = size.get("min"), size.get("max")
    if lo is None or hi is None:
        return False
    return lo <= team_size <= hi


def filter_candidates(
    catalog: list[QuestTemplate],
    context: QuestMatchContext,
) -> list[QuestTemplate]:
    """결정론적 규칙만으로 후보 목록을 만든다."""
    matched_rule_ids = set(context.matched_rule_ids)
    completed_quest_ids = set(context.completed_quest_ids)

    candidates: list[QuestTemplate] = []
    for quest in catalog:
        if not quest.is_active:
            continue
        if quest.assignment != "AUTO":
            continue
        if quest.is_universal:
            continue  # 범용 퀘스트는 폴백 전용 — 일반 후보 풀에 넣지 않는다
        if not team_size_matches(quest, context.team_size):
            continue
        if quest.disclosure_level == "HIGH":
            continue
        if matched_rule_ids & set(quest.avoid_for):
            continue
        if quest.quest_id in completed_quest_ids:
            continue

        candidates.append(quest)

    return candidates


def matched_candidates(
    candidates: list[QuestTemplate],
    context: QuestMatchContext,
) -> list[QuestTemplate]:
    """규칙(rule_id) 기준으로 실제 "맞춤" 후보만 남긴다.

    best_for 또는 also_for가 matched_rule_ids와 하나라도 겹쳐야 한다.
    context_tags만 겹치는 것은 맞춤 후보로 인정하지 않는다.
    """
    matched_rule_ids = set(context.matched_rule_ids)

    return [
        quest
        for quest in candidates
        if matched_rule_ids & (set(quest.best_for) | set(quest.also_for))
    ]

"""
점수 계산 및 정렬 (SPEC_V5.2 §5.1, §9 — 최종 카탈로그 정책 반영)

점수 공식은 "일치 개수" 기준이다 (일치 여부에 대한 고정 가산점이 아니다):
    best_for 일치 개수 × BEST_FOR_MATCH_WEIGHT(3)
  + also_for 일치 개수 × ALSO_FOR_MATCH_WEIGHT(1)
  + context_tags 일치 개수 × CONTEXT_TAG_MATCH_WEIGHT(1)
  - REPEATED_CATEGORY_PENALTY(2)  # 완료 퀘스트와 category가 같을 때만

예: context.matched_rule_ids와 quest.best_for가 2개 겹치면 3×2=6점이 가산된다.
1개만 겹치는 다른 후보와는 점수가 달라진다 — 존재 여부(불리언)가 아니라
정말로 "개수"에 비례한다.

is_universal은 점수에 가산하지 않는다. 범용 퀘스트는 filter.filter_candidates()
단계에서 이미 일반 후보 풀에서 제외되며, 적합한 일반 AUTO 후보가 전혀 없을 때만
nodes/fallback.py가 카탈로그를 다시 뒤져 폴백으로 사용한다 — 즉 is_universal은
"동점일 때 유리한 속성"이 아니라 "다른 후보가 하나도 없을 때만 쓰는 최후 후보"다.

랭킹(top 3 선정)과 폴백 선택은 별도 함수로 분리해 두되(SPEC §5 vs §9의 문맥이
다르므로), is_universal 가산이 빠지면서 두 정렬 공식은 현재 동일하다.
"""

from __future__ import annotations

from .schemas import QuestMatchContext, QuestTemplate

_DISCLOSURE_RANK = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}

TOP_CANDIDATE_LIMIT = 3

# 점수 가중치 — "일치한 항목 개수"에 곱해지는 값이다 (일치 여부 불리언이 아님).
BEST_FOR_MATCH_WEIGHT = 3
ALSO_FOR_MATCH_WEIGHT = 1
CONTEXT_TAG_MATCH_WEIGHT = 1
REPEATED_CATEGORY_PENALTY = 2  # 완료 퀘스트와 category가 겹칠 때만 감점(빼는 값)


def completed_categories(
    context: QuestMatchContext, catalog: list[QuestTemplate]
) -> set[str]:
    """완료 처리된 퀘스트들의 category 집합을 전체 카탈로그에서 조회한다.

    completed_quest_ids가 비어 있으면(첫 배정) 빈 집합을 반환하므로,
    score_candidate()의 category 반복 감점은 완료 퀘스트가 있을 때만 걸린다.
    """
    completed_ids = set(context.completed_quest_ids)
    if not completed_ids:
        return set()
    return {quest.category for quest in catalog if quest.quest_id in completed_ids}


def score_candidate(
    quest: QuestTemplate,
    context: QuestMatchContext,
    completed_category_set: set[str],
) -> int:
    """best_for/also_for/context_tags는 "일치한 개수" 기준으로 계산한다."""
    matched_rule_ids = set(context.matched_rule_ids)
    context_tags = set(context.context_tags)

    score = 0
    score += BEST_FOR_MATCH_WEIGHT * len(matched_rule_ids & set(quest.best_for))
    score += ALSO_FOR_MATCH_WEIGHT * len(matched_rule_ids & set(quest.also_for))
    score += CONTEXT_TAG_MATCH_WEIGHT * len(context_tags & set(quest.context_tags))

    # completed_category_set은 completed_quest_ids가 있을 때만 채워지므로,
    # 첫 배정(완료 퀘스트 없음)에서는 이 조건이 항상 False다.
    if quest.category in completed_category_set:
        score -= REPEATED_CATEGORY_PENALTY

    return score


def _sort_key(quest: QuestTemplate, score: int) -> tuple:
    """score DESC → disclosure LOW 우선 → duration ASC → quest_id ASC."""
    return (
        -score,
        _DISCLOSURE_RANK.get(quest.disclosure_level, 99),
        quest.duration_minutes,
        quest.quest_id,
    )


def rank_candidates(
    candidates: list[QuestTemplate],
    context: QuestMatchContext,
    full_catalog: list[QuestTemplate],
    limit: int = TOP_CANDIDATE_LIMIT,
) -> list[QuestTemplate]:
    """점수 계산 후 상위 limit개만 반환한다 (Bedrock에 전달할 후보)."""
    completed_cats = completed_categories(context, full_catalog)
    scored = [(quest, score_candidate(quest, context, completed_cats)) for quest in candidates]
    scored.sort(key=lambda pair: _sort_key(pair[0], pair[1]))
    return [quest for quest, _score in scored[:limit]]


def sort_for_fallback(
    candidates: list[QuestTemplate],
    context: QuestMatchContext,
    full_catalog: list[QuestTemplate],
) -> list[QuestTemplate]:
    """폴백 후보 정렬: score DESC → disclosure LOW 우선 → duration ASC → quest_id ASC.

    이 함수가 받는 candidates는 두 가지 경우뿐이다:
    1) filter.filter_candidates()를 통과한 일반 AUTO 후보 목록 (is_universal 없음)
    2) nodes/fallback.py가 카탈로그에서 찾은 is_universal 후보만 모은 목록
    두 경우 모두 목록 내에서 is_universal 값이 섞이지 않으므로 별도의
    is_universal 우선순위를 둘 필요가 없다.
    """
    completed_cats = completed_categories(context, full_catalog)
    scored = [(quest, score_candidate(quest, context, completed_cats)) for quest in candidates]
    scored.sort(key=lambda pair: _sort_key(pair[0], pair[1]))
    return [quest for quest, _score in scored]

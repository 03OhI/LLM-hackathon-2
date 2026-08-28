"""
fallback 노드 — 결정론적 안전 기본값 생성 (V2)

LLM 생성이 실패했을 때:
- TEAM → TeamSnapshot 안전 기본값
- SELF_ONLY → PrivateCard 안전 기본값

항상 null이 아닌 유효한 결과를 반환한다.
점수·등급·판정·퀘스트를 포함하지 않는다.
"""

from __future__ import annotations

import logging

from ..schemas import CommentGraphState, PrivateCard, TeamSnapshot

logger = logging.getLogger(__name__)

# ── 팀 폴백 매핑 (분포 기반) ──

TEAM_FALLBACK_TEMPLATES: dict[str, dict] = {
    "balanced": {
        "title": "여러 색이 섞인 팀",
        "formula": "다양함 한 바가지 + 호기심 두 스푼",
        "scene": "회의 시작 5분 만에 세 가지 방향이 나옵니다.",
        "keywords": ["다채로움", "활발한 논의"],
    },
    "planner_heavy": {
        "title": "일정이 먼저 나오는 팀",
        "formula": "계획 3스푼 + 실행력 1스푼",
        "scene": "회의가 시작되자 일정표와 첫 아이디어가 나란히 등장합니다.",
        "keywords": ["체계적", "준비형"],
    },
    "driver_heavy": {
        "title": "출발이 빠른 팀",
        "formula": "추진력 3방울 + 속도감 2방울",
        "scene": "아이디어가 나오자마자 누군가 이미 만들고 있습니다.",
        "keywords": ["빠른 실행", "에너지"],
    },
    "default": {
        "title": "함께 모인 팀",
        "formula": "각자의 방식 한 숟갈씩",
        "scene": "서로 다른 리듬이 하나의 프로젝트에서 만납니다.",
        "keywords": ["조합", "시작"],
    },
}

# ── 개인 폴백 매핑 ──

PRIVATE_FALLBACK_TEMPLATES: dict[str, dict] = {
    "PLANNER": {
        "card_title": "이번 팀에서 꺼내볼 구조화 카드",
        "contribution": "팀에 체계와 방향을 가져다줄 수 있어요.",
        "optional_try": "큰 틀만 먼저 공유하고 디테일은 함께 채워봐도 좋아요.",
    },
    "ADAPTER": {
        "card_title": "이번 팀에서 꺼내볼 유연함 카드",
        "contribution": "상황이 바뀔 때 자연스럽게 대응하는 모습이 팀에 여유를 줘요.",
        "optional_try": "진행 상황을 짧게 공유하면 팀이 더 안심할 수 있어요.",
    },
    "DRIVER": {
        "card_title": "이번 팀에서 꺼내볼 추진력 카드",
        "contribution": "팀이 멈춰 있을 때 첫 걸음을 만들어줄 수 있어요.",
        "optional_try": "출발 전에 한 번 팀 반응을 확인해봐도 좋아요.",
    },
    "SUPPORTER": {
        "card_title": "이번 팀에서 꺼내볼 안정감 카드",
        "contribution": "팀원들이 편하게 움직일 수 있는 안정감을 줘요.",
        "optional_try": "내 아이디어도 짧게 한마디 던져봐도 괜찮아요.",
    },
    "CONFRONTER": {
        "card_title": "이번 팀에서 꺼내볼 직면 카드",
        "contribution": "모두가 피하는 주제를 테이블 위에 올려놓을 수 있어요.",
        "optional_try": "'나는 이렇게 느꼈어'로 시작해봐도 좋아요.",
    },
    "HARMONIZER": {
        "card_title": "이번 팀에서 꺼내볼 조화 카드",
        "contribution": "팀의 온도를 조절하고 다리를 놓아줄 수 있어요.",
        "optional_try": "내 의견도 하나 꺼내보면 팀에 새로운 관점이 돼요.",
    },
    "DIRECT": {
        "card_title": "이번 팀에서 꺼내볼 간결함 카드",
        "contribution": "복잡한 논의를 짧은 한마디로 정리해줄 수 있어요.",
        "optional_try": "전달 전에 한 호흡 넣어보면 더 잘 닿을 수 있어요.",
    },
    "TACTFUL": {
        "card_title": "이번 팀에서 꺼내볼 배려 카드",
        "contribution": "팀원들이 안전하게 의견을 꺼낼 수 있는 분위기를 만들어요.",
        "optional_try": "내 생각을 먼저 짧게 말해봐도 괜찮아요.",
    },
    "NEUTRAL": {
        "card_title": "이번 팀에서 꺼내볼 적응 카드",
        "contribution": "상황에 따라 다양한 역할을 자연스럽게 맡을 수 있어요.",
        "optional_try": "이번에 해보고 싶은 역할 하나를 정해봐도 좋아요.",
    },
}


def _pick_team_template_key(state: CommentGraphState) -> str:
    """분포를 보고 가장 적합한 팀 폴백 키를 선택한다."""
    ctx = state.get("knowledge_context", {})
    dist = ctx.get("distribution", {})

    if not dist:
        return "default"

    # 간단한 휴리스틱: planning 축 PLANNER 과반이면 planner_heavy
    planning = dist.get("planning", {})
    if isinstance(planning, dict):
        total = sum(planning.values()) if planning else 0
        if total > 0 and planning.get("PLANNER", 0) > total / 2:
            return "planner_heavy"

    agency = dist.get("agency", {})
    if isinstance(agency, dict):
        total = sum(agency.values()) if agency else 0
        if total > 0 and agency.get("DRIVER", 0) > total / 2:
            return "driver_heavy"

    # 2축 이상에서 양극 모두 존재하면 balanced
    balanced_count = 0
    for axis_dist in dist.values():
        if isinstance(axis_dist, dict):
            vals = list(axis_dist.values())
            non_zero = [v for v in vals if v > 0]
            if len(non_zero) >= 2:
                balanced_count += 1
    if balanced_count >= 2:
        return "balanced"

    return "default"


def _pick_private_template_key(state: CommentGraphState) -> str:
    """개인 포지션에서 가장 대표적인 포지션을 선택한다."""
    ctx = state.get("knowledge_context", {})
    positions = ctx.get("self_positions", {})

    # planning 축 우선, 그 다음 agency
    for axis in ("planning", "agency", "conflict", "communication"):
        pos = positions.get(axis)
        if pos and pos != "NEUTRAL" and pos in PRIVATE_FALLBACK_TEMPLATES:
            return pos

    return "NEUTRAL"


def build_team_fallback(
    distribution: dict,
    allowed_rule_ids: list[str],
) -> TeamSnapshot:
    """백엔드가 직접 호출할 수 있는 팀 폴백 함수.

    항상 null이 아닌 유효한 TeamSnapshot을 반환한다.
    점수·등급·판정·퀘스트를 포함하지 않는다.
    """
    # 간단한 CommentGraphState 구성하여 기존 로직 재사용
    state: CommentGraphState = {
        "audience": "TEAM",
        "analysis_result_id": "",
        "participant_id": None,
        "allowed_strength_codes": [],
        "allowed_caution_codes": [],
        "allowed_recommendation_codes": [],
        "allowed_rule_ids": allowed_rule_ids,
        "knowledge_context": {"distribution": distribution},
        "draft": None,
        "validation_errors": [],
        "retry_count": 2,
        "final": None,
        "used_fallback": False,
    }
    result = render_fallback(state)
    return result["final"]


def build_private_fallback(
    self_positions: dict,
    allowed_rule_ids: list[str],
) -> PrivateCard:
    """백엔드가 직접 호출할 수 있는 개인 폴백 함수.

    항상 null이 아닌 유효한 PrivateCard를 반환한다.
    다른 참여자 정보 없이도 생성 가능하다.
    """
    state: CommentGraphState = {
        "audience": "SELF_ONLY",
        "analysis_result_id": "",
        "participant_id": None,
        "allowed_strength_codes": [],
        "allowed_caution_codes": [],
        "allowed_recommendation_codes": [],
        "allowed_rule_ids": allowed_rule_ids,
        "knowledge_context": {"self_positions": self_positions},
        "draft": None,
        "validation_errors": [],
        "retry_count": 2,
        "final": None,
        "used_fallback": False,
    }
    result = render_fallback(state)
    return result["final"]


def render_fallback(state: CommentGraphState) -> dict:
    """안전한 기본 결과를 항상 생성한다."""
    logger.warning(
        "render_fallback: audience=%s, errors=%s",
        state["audience"],
        state.get("validation_errors", []),
    )

    allowed_rule_ids = state["allowed_rule_ids"][:3]

    if state["audience"] == "TEAM":
        key = _pick_team_template_key(state)
        tmpl = TEAM_FALLBACK_TEMPLATES.get(key, TEAM_FALLBACK_TEMPLATES["default"])
        result = TeamSnapshot(
            title=tmpl["title"],
            formula=tmpl["formula"],
            scene=tmpl["scene"],
            keywords=tmpl["keywords"],
            used_rule_ids=allowed_rule_ids,
        )
    else:
        key = _pick_private_template_key(state)
        tmpl = PRIVATE_FALLBACK_TEMPLATES.get(key, PRIVATE_FALLBACK_TEMPLATES["NEUTRAL"])
        result = PrivateCard(
            card_title=tmpl["card_title"],
            contribution=tmpl["contribution"],
            optional_try=tmpl["optional_try"],
            used_rule_ids=allowed_rule_ids,
        )

    return {
        "final": result,
        "used_fallback": True,
    }

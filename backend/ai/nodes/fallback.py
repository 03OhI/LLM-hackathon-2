"""
fallback 노드 - 결정론적 템플릿 기반 코멘트 생성

LLM 생성이 실패(timeout, 파싱 오류, 검증 재실패)했을 때
규칙 엔진이 제공한 코드를 기반으로 안전한 템플릿 코멘트를 반환한다.
"""

from __future__ import annotations

import logging

from ..schemas import CommentGraphState, GeneratedInsight, InsightItem

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# 코드별 기본 텍스트 매핑
# ──────────────────────────────────────────────

STRENGTH_TEMPLATES: dict[str, str] = {
    "INITIATIVE_SUPPORT_BALANCE": "주도와 지원의 균형이 잡혀 있어 과제 추진에 안정감을 줄 수 있어요.",
    "PLANNING_STABILITY": "계획을 체계적으로 정리하는 성향이 팀에 안정감을 더할 수 있어요.",
    "DIVERSE_COMMUNICATION": "다양한 커뮤니케이션 스타일이 공존하여 논의가 풍성해질 수 있어요.",
    "CONFLICT_BALANCE": "갈등 대응 방식이 골고루 분포되어 건설적 토론이 가능할 수 있어요.",
    "ADAPTABILITY_PRESENT": "유연하게 대처하는 구성원이 있어 변화 상황에서 강점을 발휘할 수 있어요.",
    "DRIVER_ENERGY": "추진력 있는 구성원이 팀의 실행 속도를 높여줄 수 있어요.",
    "HARMONIZER_PRESENCE": "조화를 중시하는 구성원이 팀 분위기를 안정시켜 줄 수 있어요.",
    "TACTFUL_COMMUNICATION": "배려하는 소통 방식이 팀의 심리적 안전감을 높여줄 수 있어요.",
}

CAUTION_TEMPLATES: dict[str, tuple[str, str]] = {
    "DIRECT_COMMUNICATION_CONCENTRATION": (
        "직접적 소통 성향이 집중되어 있어 의견 충돌 시 톤 조절이 필요할 수 있어요.",
        "중요한 피드백 전에 '사실-영향-요청' 순서로 전달해 보세요.",
    ),
    "CHECK_FEEDBACK_TONE": (
        "직접적인 표현이 빠른 해결에는 도움이 되지만, 전달 전에 상대가 받아들일 여지를 확인해 보세요.",
        "사실-영향-요청 순서로 말해 보세요.",
    ),
    "PLANNING_OVERLOAD": (
        "계획 성향이 강한 구성원이 많아 유연한 대응이 늦어질 수 있어요.",
        "주간 회고에서 '계획 외 성과'도 함께 인정해 보세요.",
    ),
    "LOW_DRIVER_ENERGY": (
        "추진력을 맡는 구성원이 부족하면 의사결정이 느려질 수 있어요.",
        "논의 시간을 미리 정하고, 시간 내에 결론을 내는 연습을 해 보세요.",
    ),
    "CONFRONTER_CONCENTRATION": (
        "갈등 직면 성향이 집중되어 토론이 과열될 수 있어요.",
        "의견 대립 시 3분 발언 규칙을 정해 보세요.",
    ),
    "SUPPORTER_MAJORITY": (
        "지원 성향이 다수여서 누군가 먼저 나서기 어려울 수 있어요.",
        "미팅마다 돌아가며 진행 역할을 맡아 보세요.",
    ),
    "ADAPTER_MAJORITY": (
        "유연한 성향이 다수이면 방향 설정이 늦어질 수 있어요.",
        "프로젝트 초기에 마일스톤 3개를 먼저 합의해 보세요.",
    ),
}

DEFAULT_STRENGTH_TEXT = "이 팀 조합에서 긍정적으로 작용할 수 있는 요소가 있어요."
DEFAULT_CAUTION_TEXT = "이 팀 조합에서 주의하면 좋을 부분이 있어요."
DEFAULT_ACTION = "팀원들과 짧은 체크인을 정기적으로 가져 보세요."


def render_fallback(state: CommentGraphState) -> dict:
    """규칙 코드 기반 결정론적 템플릿 코멘트를 생성한다.

    Returns:
        상태 업데이트 dict (final, used_fallback)
    """
    logger.warning(
        "render_fallback: audience=%s, errors=%s",
        state["audience"],
        state.get("validation_errors", []),
    )

    # 강점 항목 생성
    strengths: list[InsightItem] = []
    for code in state["allowed_strength_codes"]:
        text = STRENGTH_TEMPLATES.get(code, DEFAULT_STRENGTH_TEXT)
        strengths.append(InsightItem(code=code, text=text))

    # 주의점 항목 생성
    cautions: list[InsightItem] = []
    for code in state["allowed_caution_codes"]:
        if code in CAUTION_TEMPLATES:
            text, action = CAUTION_TEMPLATES[code]
        else:
            text = DEFAULT_CAUTION_TEXT
            action = DEFAULT_ACTION
        cautions.append(InsightItem(code=code, text=text, action=action))

    # summary 생성
    if state["audience"] == "TEAM":
        summary = "이 팀은 서로 다른 성향이 모여 다양한 관점을 제공할 수 있는 조합이에요."
    else:
        summary = "이 팀에서 나의 성향을 잘 활용하면 팀에 기여할 수 있어요."

    result = GeneratedInsight(
        summary=summary,
        strengths=strengths[:5],
        cautions=cautions[:5],
        used_rule_ids=state["allowed_rule_ids"][:5],
    )

    return {
        "final": result,
        "used_fallback": True,
    }

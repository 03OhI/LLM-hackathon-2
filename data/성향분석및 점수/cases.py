"""
RAG 코퍼스 정본 — 팀 패턴 케이스 11 + 개인 유형 카드 16.

두 묶음의 쓰임이 다르다. 이걸 섞으면 검색이 무너진다.

  TEAM_CASES  (11)  → 벡터 인덱스에 넣는다.  조건 조합이 무한하므로 '검색'이 맞다.
  TYPE_CARDS  (16)  → 딕셔너리로 조회한다.   키가 유한하고 코드가 정확히 계산해내므로 '조회'가 맞다.

근거는 RETRIEVAL.md §1·§2. 이 파일은 외부 의존성이 없다(표준 라이브러리만).
"""

# ══════════════════════════════════════════════════════════════
# 1. 팀 패턴 케이스 — 벡터 인덱스 대상
# ══════════════════════════════════════════════════════════════
# priority: 낮을수록 먼저. 기준은 "등급을 실제로 바꾸는 순서"다.
#   0 = 등급을 강등시킨다 (compute_chemistry에서 total에 계수를 곱한다)
#   1 = 게이트로 등급을 C로 고정시킨다
#   2 = 축 점수를 0.5 아래로 떨어뜨린다
#   4~6 = 마찰로만 뜬다 (축 가중치 순: comms .25 > conflict .20 = plan .20)
#   7~8 = 등급을 안 바꾸는 진단. 헤드라인이 될 수 없다 (RETRIEVAL.md §3)
#   9 = 문제가 하나도 없을 때만 나온다 (폴백)
#
# evidence_finding 은 원문을 열어야만 채운다. 비어 있으면 화면에 출처를 띄우지 않는다.
# (환각 방지 장치 — RAG_CORPUS.md의 카드 규칙과 같다)

TEAM_CASES = [
    {
        "id": "TEAM_SPLIT",
        "priority": 0,
        "axes": ["plan", "drive", "conflict", "comms"],
        "severity": "high",
        "trigger": "faultline_kind == '두 편으로 갈라진 조합'",
        "query": "팀이 두 편으로 갈라진 조합",
        "text": (
            "구성원들이 두 덩어리로 나뉘고, 네 가지 성향이 그 경계를 따라 같이 움직이는 조합. "
            "한쪽 덩어리 안에서는 말이 잘 통하는데 경계를 넘으면 같은 말이 다르게 들린다. "
            "첫 주에는 각자 편한 사람끼리 붙어서 진도가 나가는 것처럼 보인다. "
            "문제는 두 덩어리가 만든 결과물을 합칠 때 드러나고, 그때는 이미 되돌리기 비싸다. "
            "먼저 할 일 — 역할을 두 덩어리에서 교차로 배치한다. 같은 덩어리끼리 묶으면 사흘째에 벌어진다."
        ),
        "action": "역할을 두 편에서 교차로 배치하세요. 같은 편끼리 묶으면 사흘째에 벌어집니다",
        "evidence_ref": "Thatcher, S. M. B., Jehn, K. A., & Zanutto, E. (2003). Cracks in Diversity Research: The Effects of Diversity Faultlines on Conflict and Performance. Group Decision and Negotiation, 12(3), 217-241",
        "evidence_finding": "Groups with either virtually no faultlines (very diverse members) or strong faultlines (split into 2 fairly homogeneous subgroups) had higher levels of conflict and lower levels of morale and performance than groups with medium faultlines (79개 집단)",
        "evidence_status": "원문 대조 (2026-08-28, 초록) · ⚠️ 곡선 관계다. '두 편으로 갈라지면 나쁘다'는 절반만 우리 설계와 맞고, 나머지 절반은 TEAM_MIXED 로 간다",
    },
    {
        "id": "TEAM_ISOLATED",
        "priority": 0,
        "axes": ["plan", "drive", "conflict", "comms"],
        "severity": "high",
        "trigger": "faultline_kind == '한 사람이 겉도는 조합'",
        "query": "한 구성원만 나머지와 성향이 다른 조합",
        "text": (
            "한 명을 뺀 나머지가 서로 비슷하고, 그 한 명만 여러 성향에서 반대편에 서 있는 조합. "
            "이건 분열이 아니라 소외다. 다수가 편해서 갈등이 안 보이는데, 안 보이는 게 문제다. "
            "그 한 명의 의견은 반박당하는 게 아니라 그냥 흘러간다. 회의록에 남지 않는다. "
            "다수결로 정하면 매번 같은 사람이 밀리고, 보통 그 사람이 가장 먼저 팀에서 마음을 뗀다. "
            "먼저 할 일 — 그 한 명에게 먼저 말할 자리를 준다. 표결이 아니라 순서로 푼다."
        ),
        "action": "그 한 명에게 먼저 말할 자리를 주세요. 다수결로 가면 계속 밀립니다",
        "evidence_ref": "Meyer, B., & Glenz, A. (2013). Team Faultline Measures: A Computational Comparison and a New Approach to Multiple Subgroups. Organizational Research Methods, 16(3), 393-424",
        "evidence_finding": None,
        "evidence_status": "원문 대조 (2026-08-28, 초록) · ⚠️ ASW 는 측정 방법 문헌이지 '겉도는 것이 나쁘다'의 근거가 아니다. diagnose() 도 ASW 를 판정에 안 쓴다. 다만 두 방법이 어긋나지는 않는다 — 현행이 이 조합으로 판정한 3,414건이 100% ASW 최적 분할에서도 크기 1인 하위집단을 갖는다 (2026-08-28 전수). 화면 출처로는 쓰지 않는다",
    },
    {
        "id": "DRIVE_NONE",
        "priority": 1,
        "axes": ["drive"],
        "severity": "high",
        "trigger": "captain_ratio == 0",
        "query": "먼저 나서서 정하는 사람이 없는 조합",
        "text": (
            "먼저 나서서 방향을 정하는 사람이 아무도 없는 조합. 전원이 요청을 기다린다. "
            "분위기는 좋다. 서로 배려하고 부딪히는 일이 거의 없다. 그래서 문제로 안 느껴진다. "
            "대신 아무 결정도 안 난 채로 시간이 지나간다. 마감이 다가와야 누군가 억지로 떠맡는다. "
            "떠맡은 사람은 준비 없이 끌게 되므로 결정의 질이 나쁘고, 나중에 그 사람만 원망을 듣는다. "
            "먼저 할 일 — 첫 회의 진행자를 지금 한 명 지목한다. 성향이 아니라 순번으로 정해도 된다."
        ),
        "action": "첫 회의 진행자를 지금 한 명 지목하세요",
        "evidence_ref": "노연희, 손영우 (2012). 팀의 구성이 팀 수행에 미치는 영향. 한국심리학회지: 산업 및 조직, 25(4), 861-887 · Flores Ureba, S., Simon de Blas, C., Borras-Gene, O., & Macias-Guillen, A. (2022). Analyzing the Influence of Belbin's Roles on the Quality of Collaborative Learning. Education Sciences, 12(9), 594",
        "evidence_finding": "67개 팀 315명. 우호성 최솟값과 과제의 연구논리 점수가 부적 상관(r=-.26, p<.05). Steiner(1972)의 합동과제에서는 팀의 가장 약한 부분이 치명적이므로 최솟값이 팀 수준의 적절한 조작적 정의다(Bell, 2007). 다양성과 성과의 관계는 선형이 아니며 적정한 수준의 범위가 존재한다 / balanced groups facilitate greater homogeneity in group grades, improving the performance of the group overall (149명 21개 그룹, 학부 팀 과제)",
        "evidence_status": "원문 대조 (2026-08-28, 초록·결과·논의) · ⚠️ Halfhill et al.(2005)에서 교체함 — 원문이 '최솟값이 평균 만큼 예측한다'여서 우리 주장을 지지하지 않는다. 보고서 §5.4 와 cases.py 는 2026-08-28 반영 완료",
    },
    {
        "id": "DRIVE_ALL",
        "priority": 2,
        "axes": ["drive"],
        "severity": "mid",
        "trigger": "captain_ratio == 1.0",
        "query": "전원이 주도하려는 조합",
        "text": (
            "구성원 전부가 자기가 끌고 가려는 조합. 회의가 제안으로 가득 차고 아무것도 채택되지 않는다. "
            "각자 상대의 안을 반박이 아니라 개선으로 다듬으려 하기 때문에 논의가 끝나지 않는다. "
            "겉보기 활력은 가장 높지만 산출물 수는 가장 적다. "
            "누가 양보하느냐로 풀려고 하면 인간관계 문제가 되어 더 나빠진다. "
            "먼저 할 일 — 결정권을 사람이 아니라 영역으로 나눈다. 이 영역은 누가 최종 결정, 저 영역은 누가."
        ),
        "action": "결정권을 사람이 아니라 영역으로 나누세요",
        "evidence_ref": "Flores Ureba, S., Simon de Blas, C., Borras-Gene, O., & Macias-Guillen, A. (2022). Analyzing the Influence of Belbin's Roles on the Quality of Collaborative Learning. Education Sciences, 12(9), 594",
        "evidence_finding": "balanced groups facilitate greater homogeneity in group grades, improving the performance of the group overall (149명 21개 그룹, 학부 팀 과제)",
        "evidence_status": "원문 대조 (2026-08-28, 초록)",
    },
    {
        "id": "DRIVE_EXCESS",
        "priority": 2,
        "axes": ["drive"],
        "severity": "mid",
        "trigger": "0.6 <= captain_ratio < 1.0",
        "query": "주도적인 구성원이 다수인 조합",
        "text": (
            "끌고 가려는 사람이 절반을 넘는 조합. 제안은 빠르게 나오는데 채택이 늦다. "
            "초반 사흘은 속도가 잘 나와서 아무도 이상하게 여기지 않는다. "
            "그러다 \"그래서 누가 정하나요\"라는 말이 처음 나오는 지점이 온다. 대개 사흘째다. "
            "따라가는 쪽에 선 소수는 이 시기에 말수가 줄고, 줄어든 걸 아무도 알아채지 못한다. "
            "먼저 할 일 — 결정 마감 시각을 안건마다 먼저 못박는다. 그 시각에 안 정해지면 자동으로 한 안을 택한다."
        ),
        "action": "제안은 빨리 나오지만 결정이 늦습니다. 마감 시각을 먼저 정하세요",
        "evidence_ref": "노연희, 손영우 (2012). 팀의 구성이 팀 수행에 미치는 영향. 한국심리학회지: 산업 및 조직, 25(4), 861-887",
        "evidence_finding": "67개 팀 315명. 우호성 최솟값과 과제의 연구논리 점수가 부적 상관(r=-.26, p<.05). Steiner(1972)의 합동과제에서는 팀의 가장 약한 부분이 치명적이므로 최솟값이 팀 수준의 적절한 조작적 정의다(Bell, 2007). 다양성과 성과의 관계는 선형이 아니며 적정한 수준의 범위가 존재한다",
        "evidence_status": "원문 대조 (2026-08-28, 초록·결과·논의) · ⚠️ 원 결과는 인구통계·인지 다양성이지 성향 다양성이 아니다. '성향에도 적정 구간이 있다'고 말하면 안 된다",
    },
    {
        "id": "PARTIAL_TWO_AXIS",
        "priority": 7,
        "axes": ["plan", "drive", "conflict", "comms"],
        "severity": "low",
        "trigger": "faultline breadth == 0.50 (차이가 두 축에만)",
        "query": "차이가 두 가지 성향에서만 나타나는 조합",
        "text": (
            "네 가지 중 두 가지에서만 사람들이 갈리고 나머지 둘은 거의 같은 조합. 공통 기반이 넓어서 대화는 대체로 통한다. "
            "갈리는 두 가지가 어디인지 서로 이미 눈치채고 있는 경우가 많다. 그래서 이 차이는 다투는 지점이 아니라 나눠 맡는 지점으로 쓸 수 있다. "
            "위험은 좁은 차이일수록 말 안 하고 덮기 쉽다는 것이다. 덮은 채로 사흘이 지나면 마지막 날에 한꺼번에 나온다. "
            "먼저 할 일 — 갈리는 두 가지를 골라 각각 누가 맡을지 이름을 붙인다."
        ),
        "action": "갈리는 두 가지를 골라 각각 누가 맡을지 이름을 붙이세요",
        "evidence_ref": None,
        "evidence_finding": None,
        "evidence_status": "[규칙] 팀이 정한 기준 — 논문 근거 없음 · ⚠️ breadth 로 나눈 우리 기준. 논문 수식이 아니다",
    },
    {
        "id": "PARTIAL_THREE_AXIS",
        "priority": 7,
        "axes": ["plan", "drive", "conflict", "comms"],
        "severity": "mid",
        "trigger": "faultline breadth == 0.75 (차이가 세 축에)",
        "query": "세 가지 성향에서 차이가 나는 조합",
        "text": (
            "네 가지 중 세 가지에서 차이가 나는 조합. 겹치는 면이 하나로 줄어서 무엇을 하든 어딘가는 맞춰야 한다. "
            "개별 사안은 대체로 풀리는데 풀 때마다 시간이 든다는 게 특징이다. 합의를 못 하는 팀이 아니라 합의가 비싼 팀이다. "
            "사흘짜리 일정에서는 이 비용이 그대로 지연으로 나타나고, 보통 이틀째 오후에 처음 체감된다. "
            "먼저 할 일 — 자주 부딪힐 결정 세 가지를 골라 처리 규칙을 문장으로 적어둔다."
        ),
        "action": "자주 부딪힐 결정 세 가지의 처리 규칙을 문장으로 적어두세요",
        "evidence_ref": None,
        "evidence_finding": None,
        "evidence_status": "[규칙] 팀이 정한 기준 — 논문 근거 없음 · ⚠️ breadth 로 나눈 우리 기준. 논문 수식이 아니다",
    },
    {
        "id": "PARTIAL_SHIFTING",
        "priority": 7,
        "axes": ["plan", "drive", "conflict", "comms"],
        "severity": "mid",
        "trigger": "faultline breadth == 1.00 and fau < 0.50 (네 축 다르나 경계가 안 겹침)",
        "query": "매번 다른 사람끼리 같은 편이 되는 조합",
        "text": (
            "네 가지 전부에서 차이가 있는데 그 차이들이 서로 다른 방향을 향하는 조합. 어떤 주제에서는 A와 B가 한편이고 "
            "다른 주제에서는 A와 C가 한편이 된다. 고정된 무리가 안 생기므로 감정이 쌓이지는 않는다. "
            "대신 편이 매번 바뀌어 다음 회의가 어떻게 흘러갈지 예측이 안 된다. 회의 길이가 들쭉날쭉해지는 것이 첫 신호다. "
            "먼저 할 일 — 안건 종류별로 결정 방식을 미리 정해둔다."
        ),
        "action": "안건 종류별로 결정 방식을 미리 정해두세요",
        "evidence_ref": None,
        "evidence_finding": None,
        "evidence_status": "[규칙] 팀이 정한 기준 — 논문 근거 없음 · ⚠️ Fau 0.5 는 '최적 2분할이 분산의 절반을 설명한다'는 선. 우리가 정했다",
    },
    {
        "id": "PARTIAL_HARDENING",
        "priority": 6,
        "axes": ["plan", "drive", "conflict", "comms"],
        "severity": "mid",
        "trigger": "faultline breadth == 1.00 and fau >= 0.50 (네 축 다르고 경계가 겹치기 시작)",
        "query": "같은 두 무리가 반복해서 생기는 조합",
        "text": (
            "네 가지 전부에서 차이가 있고 그 차이들이 대체로 같은 선을 따라 놓이는 조합. 아직 굳지는 않았지만 굳는 쪽으로 가는 중이다. "
            "회의를 몇 번 하면 늘 비슷한 사람끼리 비슷한 의견을 낸다는 게 눈에 띄기 시작한다. "
            "지금 손대는 비용이 굳은 다음보다 훨씬 싸다는 것이 이 상태의 유일한 좋은 점이다. "
            "먼저 할 일 — 짝을 섞어 배치한다. 자연스럽게 뭉치는 조합을 한 번 끊어준다."
        ),
        "action": "짝을 섞어 배치하세요. 자연스럽게 뭉치는 조합을 한 번 끊습니다",
        "evidence_ref": None,
        "evidence_finding": None,
        "evidence_status": "[규칙] 팀이 정한 기준 — 논문 근거 없음 · ⚠️ Thatcher(2003)의 strong faultline 전 단계로 읽히지만 논문은 '굳어가는 중'을 다루지 않았다. 붙이지 않는다",
    },
    {
        "id": "TEAM_ONE_AXIS",
        "priority": 8,          # 본문 스스로 "가장 풀기 쉬운 형태"라고 말한다. 헤드라인 자격 없음
        "axes": ["plan", "drive", "conflict", "comms"],
        "severity": "low",
        "trigger": "faultline_kind == '한 가지만 다른 조합'",
        "query": "성향 한 가지에서만 갈리는 조합",
        "text": (
            "나머지는 거의 같은데 딱 한 가지 성향에서만 갈리는 조합. 가장 풀기 쉬운 형태다. "
            "겹치는 부분이 넓어서 서로를 이미 이해하고 있고, 차이가 어디인지도 대체로 알고 있다. "
            "그래서 이 차이는 갈등이 아니라 역할 분담의 재료가 된다. "
            "위험은 반대편이다 — 너무 비슷해서 아무도 다른 안을 내지 않는 쪽으로 흐를 수 있다. "
            "먼저 할 일 — 갈리는 그 한 가지를 역할 경계로 삼는다. 나머지는 굳이 맞추지 않아도 된다."
        ),
        "action": "갈리는 그 한 가지를 역할 경계로 삼으세요",
        "evidence_ref": None,
        "evidence_finding": None,
        "evidence_status": "[규칙] 팀이 정한 기준 — 논문 근거 없음 · ⚠️ breadth 보정은 우리가 만든 것이지 논문 수식이 아니다",
    },
    {
        "id": "COMMS_SPLIT",
        "priority": 4,
        "axes": ["comms"],
        "severity": "mid",
        "trigger": "comms mismatch >= 0.45",
        "query": "직설과 완곡이 섞인 조합",
        "text": (
            "결론을 먼저 던지는 사람과 배경부터 깔고 들어가는 사람이 반반 섞인 조합. "
            "결론부터 듣는 쪽에는 배경 설명이 변명처럼 들리고, 배경부터 말하는 쪽에는 결론만 던지는 게 무례하게 들린다. "
            "둘 다 상대에게 악의가 없어서 오해를 오해로 인식하지 못한다. 그래서 초기 갈등 1순위가 여기서 난다. "
            "특히 피드백을 주고받을 때 터진다. 내용이 아니라 형식 때문에 감정이 상한다. "
            "먼저 할 일 — 피드백 형식을 먼저 합의한다. 예를 들어 \"결론 한 줄 → 이유 세 줄\" 같은 틀 하나면 충분하다."
        ),
        "action": "피드백을 줄 때 형식을 먼저 합의하세요. 초기 오해 1순위입니다",
        "evidence_ref": None,
        "evidence_finding": None,
        "evidence_status": "[규칙] 팀이 정한 기준 — 논문 근거 없음 · ⚠️ 소통 직접성 축은 [팀 판단]. 논문을 붙이면 '네 축 전부 논문 근거'라는 금지 문장이 된다",
    },
    {
        "id": "CONFLICT_SPLIT",
        "priority": 5,
        "axes": ["conflict"],
        "severity": "mid",
        "trigger": "conflict mismatch >= 0.45",
        "query": "갈등을 다루는 방식이 갈린 조합",
        "text": (
            "문제가 보이면 그 자리에서 짚는 사람과, 일단 넘기고 나중에 따로 말하는 사람이 섞인 조합. "
            "그 자리에서 짚는 쪽은 뒤에서 말하는 걸 신뢰가 없다고 느낀다. "
            "따로 말하는 쪽은 공개 지적을 망신으로 느낀다. 같은 지적이 한쪽에는 성실이고 한쪽에는 공격이다. "
            "결과적으로 문제가 두 경로로 흐른다 — 회의에서 다뤄지는 문제와, 개인 대화에서만 도는 문제. "
            "먼저 할 일 — 어떤 문제를 그 자리에서 말하고 어떤 문제를 따로 말할지 경계를 한 번 정한다."
        ),
        "action": "문제를 그 자리에서 말할지 따로 말할지 규칙을 정하세요",
        "evidence_ref": "Triana, M. C., Kim, K., Byun, S.-Y., Delgado, D. M., & Arthur, W. (2021). Journal of Management Studies, 58(8), 2137-2179",
        "evidence_finding": "team deep-level diversity is associated with fewer positive emergent states and positive team processes and more team conflict",
        "evidence_status": "원문 대조 (2026-08-28, 초록)",
    },
    {
        "id": "PLAN_ONESIDED",
        "priority": 6,
        "axes": ["plan"],
        "severity": "low",
        "trigger": "plan 축에 한쪽 극만 존재",
        "query": "계획 성향이 한쪽에만 몰린 조합",
        "text": (
            "순서를 먼저 그리는 사람만 있거나, 일단 시작하는 사람만 있는 조합. 양극 중 하나가 비어 있다. "
            "전원이 순서를 먼저 그리면 착수가 늦고 문서가 실제보다 앞서간다. "
            "전원이 일단 시작하면 초반 속도는 좋은데 중간에 겹치는 작업과 빠진 작업이 동시에 생긴다. "
            "이건 갈등이 아니라 공백이다. 팀 안에서 아무도 불편해하지 않기 때문에 끝까지 안 드러난다. "
            "먼저 할 일 — 비어 있는 쪽 역할을 한 사람이 겸한다. 성향이 아니라 담당으로 지정한다."
        ),
        "action": "누가 순서를 잡고 누가 밀어붙일지 먼저 정하세요",
        "evidence_ref": "Flores Ureba, S., Simon de Blas, C., Borras-Gene, O., & Macias-Guillen, A. (2022). Analyzing the Influence of Belbin's Roles on the Quality of Collaborative Learning. Education Sciences, 12(9), 594 · Adamis, D., Krompa, G. M., Rauf, A., Mulligan, O., & O'Mahony, E. (2023). Merits, 3(3), 604-614 (CC BY)",
        "evidence_finding": "balanced groups facilitate greater homogeneity in group grades, improving the performance of the group overall (149명 21개 그룹, 학부 팀 과제) / The more diverse roles the members of a team have, the better the effectiveness of the team. 다중수준 분석에서 역할 다양성이 팀 효과성의 유의한 독립 예측변인 (n=106, 8팀)",
        "evidence_status": "원문 대조 (2026-08-28, 초록)",
    },
    {
        "id": "PLAN_TILTED",
        "priority": 6,
        "axes": ["plan"],
        "severity": "low",
        "trigger": "계획성 축 점수 < 0.7 이고 양극이 모두 존재 (spread > 0)",
        "query": "계획 성향이 한쪽으로 기운 조합",
        "text": (
            "양극이 다 있긴 한데 폭이 좁은 조합. 판을 먼저 그리는 쪽과 일단 손대는 쪽이 둘 다 있지만 "
            "둘 사이 거리가 좁아 서로를 보완하지 못한다. 착수와 마무리를 나눠 맡을 만큼 갈리지 않아서 결국 둘 다 어중간하게 한다. "
            "공백이 생기는 것은 아니라서 아무도 문제를 느끼지 못하고, 그래서 분업이 안 되고 있다는 사실이 늦게 드러난다. "
            "먼저 할 일 — 성향이 아니라 시간으로 자른다. 며칠까지 판을 짜고 언제부터 밀어붙일지 날짜로 정한다."
        ),
        "action": "성향이 아니라 시간으로 나누세요. 언제까지 판을 짜고 언제부터 밀어붙일지 날짜로 정합니다",
        "evidence_ref": None,
        "evidence_finding": None,
        "evidence_status": "[규칙] 팀이 정한 기준 — 논문 근거 없음 · ⚠️ 축 점수 0.7 임계는 우리 기준. 논문 수식이 아니다",
    },
    {
        "id": "AXIS_UNJUDGED",
        "priority": 1,
        "axes": ["plan", "drive", "conflict", "comms"],
        "severity": "high",
        "trigger": "축 점수가 None — 판정할 인원 또는 쌍이 부족 (MIN_JUDGED / MIN_PAIRS 미만)",
        "query": "응답이 부족해 판정하지 않은 축이 있는 조합",
        "text": (
            "어떤 축을 판정하지 않고 비워 둔 조합. 그 축의 여섯 문항에 대한 답이 중간값 근처로 모이면 "
            "그 사람의 성향을 뚜렷하다고 말할 수 없고, 그런 사람이 많으면 견줘 볼 짝 자체가 없어진다. "
            "이때 점수를 매기면 판정하지 않은 것이 문제 없는 것으로 둔갑한다. 그래서 비워 둔다. "
            "화면에서 비어 있는 축은 팀이 좋다는 뜻이 아니라 아직 모른다는 뜻이다. "
            "먼저 할 일 — 비운 축은 진단 대신 첫 회의에서 직접 물어본다."
        ),
        "action": "비어 있는 축은 진단 대신 첫 회의에서 직접 물어보세요",
        "evidence_ref": None,
        "evidence_finding": None,
        "evidence_status": "[규칙] 팀이 정한 기준 — 논문 근거 없음 · ⚠️ MIN_JUDGED/MIN_PAIRS = 3 은 [팀 판단]. 판정 불가를 만점으로 처리하던 결함의 대응이다",
    },
    {
        "id": "TEAM_MIXED",
        "priority": 9,
        "axes": ["plan", "drive", "conflict", "comms"],
        "severity": "none",
        "trigger": "다른 조건이 하나도 걸리지 않을 때만",
        "query": "성향이 고르게 섞여 경계가 생기지 않는 조합",
        "text": (
            "성향이 고르게 흩어져 어느 방향으로도 뚜렷한 경계가 생기지 않는 조합. "
            "특정 두 사람이 늘 같은 편이 되는 일이 없고 주제마다 짝이 바뀐다. 파벌이 안 생기는 것은 분명한 장점이다. "
            "다만 경계가 없다는 것이 마찰이 없다는 뜻은 아니다 — 79개 집단을 본 연구에서 갈라짐이 거의 없는 팀은 "
            "중간 정도로 갈린 팀보다 오히려 갈등이 많고 사기와 성과가 낮았다. 겹치는 기반이 좁아 사안마다 처음부터 맞춰야 하기 때문이다. "
            "먼저 할 일 — 사흘째에 한 번, 말수가 가장 적은 사람에게 직접 묻는다."
        ),
        "action": "사흘째에 말수가 가장 적은 구성원에게 직접 물어보세요",
        "evidence_ref": "Thatcher, S. M. B., Jehn, K. A., & Zanutto, E. (2003). Cracks in Diversity Research: The Effects of Diversity Faultlines on Conflict and Performance. Group Decision and Negotiation, 12(3), 217-241",
        "evidence_finding": "Groups with either virtually no faultlines (very diverse members) or strong faultlines (split into 2 fairly homogeneous subgroups) had higher levels of conflict and lower levels of morale and performance than groups with medium faultlines (79개 집단)",
        "evidence_status": "원문 대조 (2026-08-28, 초록) · ⚠️ 같은 논문의 반대쪽 절반. 폴백 문단이라 '문제 없음'으로 읽히기 쉬웠다 — 2026-08-28 곡선 관계를 문단 안에 넣어 '주의 구간'으로 고쳐 씀",
    },
]

CASES_BY_ID = {c["id"]: c for c in TEAM_CASES}

# 판정 불가 마찰은 축마다 라벨이 다르지만 케이스는 하나가 공통으로 받는다.
# (chemistry_v2 가 축 이름을 붙여 내보내고, 화면 문단은 AXIS_UNJUDGED 하나를 쓴다)
UNJUDGED_LABELS = {
    "계획성을 판정할 응답이 부족한 조합": "AXIS_UNJUDGED",
    "주도성을 판정할 응답이 부족한 조합": "AXIS_UNJUDGED",
    "갈등대응을 판정할 응답이 부족한 조합": "AXIS_UNJUDGED",
    "소통을 판정할 응답이 부족한 조합": "AXIS_UNJUDGED",
}


def case_for_friction(label):
    """마찰 label → 케이스 id. 못 찾으면 None."""
    if label in UNJUDGED_LABELS:
        return UNJUDGED_LABELS[label]
    for c in TEAM_CASES:
        if c["query"] == label:
            return c["id"]
    return None


# ══════════════════════════════════════════════════════════════
# 2. 개인 유형 — 딕셔너리 조회 대상 (인덱스에 넣지 않는다)
# ══════════════════════════════════════════════════════════════
WORK_STYLE = {
    ("P", "L"): ("판 짜는 형", "순서를 먼저 그리고 자기가 끌고 간다"),
    ("P", "S"): ("길 닦는 형", "순서를 그려서 남이 쓰게 한다"),
    ("A", "L"): ("먼저 뛰는 형", "일단 시작하고 남들을 끌어당긴다"),
    ("A", "S"): ("바로 붙는 형", "일단 붙어서 필요한 걸 채운다"),
}
TALK_STYLE = {
    ("C", "D"): ("바로 말하는 형", "그 자리에서 짚고 결론부터"),
    ("C", "I"): ("돌려 짚는 형", "반드시 짚되 말투는 부드럽게"),
    ("H", "D"): ("짧게 고르는 형", "각을 안 세우되 말은 간결하게"),
    ("H", "I"): ("감싸는 형", "부드럽게, 배경부터"),
}

# 별칭 · 한 줄 · 강점 · 보완 · 팀에서 좋은 자리  (TYPES16.md §2 정본)
TYPE_CARDS = {
    "PLCD": ("선봉 설계자", "판 짜고 바로 말하는 사람",
             "시작이 빠르고 문제가 오래 묵지 않는다",
             "속도에 못 따라오는 사람이 말할 틈을 잃는다", "전체 일정·결정 주도"),
    "PLCI": ("조심스러운 지휘자", "판 짜고 돌려 짚는 사람",
             "방향을 잡으면서 사람을 안 다치게 한다",
             "급할 때 지적이 늦어 문제가 커진다", "이해관계가 얽힌 협의"),
    "PLHD": ("실무 조정자", "판 짜고 짧게 고르는 사람",
             "회의가 짧고 결론이 남는다",
             "갈등을 덮고 넘어가 나중에 되돌아온다", "일정 관리·회의 진행"),
    "PLHI": ("배려하는 기획자", "판 짜고 감싸는 사람",
             "계획이 있으면서 팀 분위기가 안정된다",
             "말해야 할 때 타이밍을 놓친다", "장기 계획·팀 안정"),
    "PSCD": ("냉정한 참모", "길 닦고 바로 말하는 사람",
             "남의 계획의 구멍을 정확히 짚는다",
             "대안 없이 지적만 하면 팀이 지친다", "검토·품질 확인"),
    "PSCI": ("신중한 참모", "길 닦고 돌려 짚는 사람",
             "준비가 꼼꼼하고 관계를 안 깬다",
             "의견이 이미 결정된 뒤에 도착한다", "문서·자료 정리"),
    "PSHD": ("효율 지원자", "길 닦고 짧게 고르는 사람",
             "필요한 걸 말없이 준비해둔다",
             "자기 몫이 안 보여 기여가 저평가된다", "운영·반복 작업"),
    "PSHI": ("묵묵한 준비자", "길 닦고 감싸는 사람",
             "팀이 흔들려도 자리를 지킨다",
             "힘든 걸 말 안 해서 혼자 떠안는다", "지속적 관리"),
    "ALCD": ("돌파형 리더", "먼저 뛰고 바로 말하는 사람",
             "막힌 걸 뚫는다. 결정이 빠르다",
             "되돌아가는 비용이 크다", "초기 프로토타입·위기 대응"),
    "ALCI": ("설득하는 개척자", "먼저 뛰고 돌려 짚는 사람",
             "새 시도를 하면서 사람을 데려간다",
             "방향이 자주 바뀌어 팀이 혼란스럽다", "새 영역 탐색"),
    "ALHD": ("실행 조율자", "먼저 뛰고 짧게 고르는 사람",
             "말보다 결과로 정리한다",
             "왜 그렇게 했는지 공유가 빠진다", "빠른 실행·데모"),
    "ALHI": ("분위기 메이커", "먼저 뛰고 감싸는 사람",
             "팀을 움직이게 만든다",
             "계획이 없어 막판에 몰린다", "초반 동력·팀 결속"),
    "ASCD": ("현장 감시자", "바로 붙고 바로 말하는 사람",
             "실제로 안 되는 걸 제일 먼저 발견한다",
             "전체 그림 없이 지엽적인 걸 짚는다", "테스트·검증"),
    "ASCI": ("조용한 관찰자", "바로 붙고 돌려 짚는 사람",
             "문제를 알아채고 상처 없이 전한다",
             "신호가 약해 아무도 못 알아듣는다", "사용자 관점 점검"),
    "ASHD": ("군말 없는 실행자", "바로 붙고 짧게 고르는 사람",
             "시키면 바로 되고 뒤탈이 없다",
             "방향을 안 물어서 헛일이 생긴다", "정해진 작업 처리"),
    "ASHI": ("팀의 완충재", "바로 붙고 감싸는 사람",
             "누구와도 붙어서 일한다",
             "자기 의견이 안 남아 소진된다", "여러 파트 연결"),
}

_POLES = {                       # 축 → (1일 때 글자, 0일 때 글자)
    "plan": ("P", "A"), "drive": ("L", "S"),
    "conflict": ("C", "H"), "comms": ("D", "I"),
}
AXES = ["plan", "drive", "conflict", "comms"]


def type_code(member, team=None):
    """
    유형 코드 4글자. 결정론.

    중립(None)인 축은 팀 다수 쪽으로 배정한다(TYPES16.md §7).
    팀이 없거나 다수가 동수면 0쪽 극(A/S/H/I)으로 고정한다 — 임의 선택이지만
    같은 입력이면 항상 같은 결과가 나오게 하기 위한 결정이다.

    반환: (code, unclear_axes)  — unclear_axes는 화면에 "뚜렷하지 않음"으로 표시할 축
    """
    code, unclear = "", []
    for ax in AXES:
        v = member.get(ax)
        if v is None:
            unclear.append(ax)
            if team:
                known = [m[ax] for m in team if m.get(ax) is not None]
                v = 1 if known and sum(known) * 2 > len(known) else 0
            else:
                v = 0
        code += _POLES[ax][0] if v else _POLES[ax][1]
    return code, unclear


def type_name(code):
    """조합 이름 자동 생성. 예: '판 짜는 형 · 바로 말하는 형'"""
    return f"{WORK_STYLE[(code[0], code[1])][0]} · {TALK_STYLE[(code[2], code[3])][0]}"


def lookup_type(code):
    """유형 카드 조회. 벡터 검색을 쓰지 않는다 — 정확한 키가 이미 있다."""
    alias, oneline, strength, caution, seat = TYPE_CARDS[code]
    return {
        "code": code, "alias": alias, "name": type_name(code),
        "oneline": oneline, "strength": strength,
        "caution": caution, "seat": seat,
        "work_style": WORK_STYLE[(code[0], code[1])],
        "talk_style": TALK_STYLE[(code[2], code[3])],
    }


# ══════════════════════════════════════════════════════════════
# 3. 팀 상태 → 검색 조건 목록
# ══════════════════════════════════════════════════════════════
# ⚠️ 조건들을 한 문장으로 이어붙이지 않는다. VECTORDB.md §3의 방식은 틀렸다.
#    이유와 재현은 RETRIEVAL.md §1.

_DRIVE_COND = {           # compute_chemistry의 drive 축 점수 → 조건 id
    0.0: "DRIVE_NONE",
    0.25: "DRIVE_ALL",
    0.45: "DRIVE_EXCESS",
}
_FAULT_COND = {
    "두 편으로 갈라진 조합": "TEAM_SPLIT",
    "한 사람이 겉도는 조합": "TEAM_ISOLATED",
    "차이가 두 가지 성향에서만 나타나는 조합": "PARTIAL_TWO_AXIS",
    "세 가지 성향에서 차이가 나는 조합": "PARTIAL_THREE_AXIS",
    "매번 다른 사람끼리 같은 편이 되는 조합": "PARTIAL_SHIFTING",
    "같은 두 무리가 반복해서 생기는 조합": "PARTIAL_HARDENING",
    "한 가지만 다른 조합": "TEAM_ONE_AXIS",
}


def build_query(chem):
    """
    compute_chemistry() 결과 → 검색 조건 목록. 결정론.

    반환: [(priority, case_id, query_text), ...]  — priority 오름차순 정렬됨
    조건이 하나도 없으면 TEAM_MIXED 하나만 돌려준다.
    """
    ids = []
    kind = chem.get("faultline_kind")
    if kind in _FAULT_COND:
        ids.append(_FAULT_COND[kind])

    ax = chem["axes"]
    if ax["drive"] in _DRIVE_COND:
        ids.append(_DRIVE_COND[ax["drive"]])
    if ax["comms"] <= 0.55:            # mismatch >= 0.45
        ids.append("COMMS_SPLIT")
    if ax["conflict"] <= 0.55:
        ids.append("CONFLICT_SPLIT")
    if ax["plan"] < 1.0:
        ids.append("PLAN_ONESIDED")

    if not ids:
        ids = ["TEAM_MIXED"]
    out = [(CASES_BY_ID[i]["priority"], i, CASES_BY_ID[i]["query"]) for i in ids]
    return sorted(out, key=lambda t: (t[0], t[1]))


if __name__ == "__main__":
    print(f"팀 패턴 케이스 {len(TEAM_CASES)}건 · 유형 카드 {len(TYPE_CARDS)}건")
    for c in sorted(TEAM_CASES, key=lambda x: x["priority"]):
        print(f"  p{c['priority']}  {c['id']:<16} {c['severity']:<5} {c['query']}")

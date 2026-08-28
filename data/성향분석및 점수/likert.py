"""
5점 리커트 채점 — SURVEY24.md v2 정본.

  1) 역채점(−) 문항:  점수 = 6 − 응답
  2) 축 원점수      = 6문항 평균 (1.00 ~ 5.00)
  3) 축 비율 r      = (평균 − 1) / 4   → 0.00 ~ 1.00   ← chemistry_v2 가 그대로 받는다
  4) 이진 변환      r > 0.60 → 상위 극 / r < 0.40 → 하위 극 / 사이 → 중립(None)

역채점이 왜 필수인가: 리커트에서 모든 문항이 같은 방향이면 무조건 '그렇다'로 답하는
사람(묵종, acquiescence)을 못 걸러낸다. 축마다 정방향 3 · 역방향 3으로 배치했다.
"""
from statistics import mean, pstdev

SCALE_MIN, SCALE_MAX = 1, 5
HI, LO = 0.60, 0.40          # 이진 변환 경계 (평균 3.4 / 2.6)

# item: (축, 방향, facet)   방향 +1 = 상위 극(P·L·C·D) 쪽, -1 = 역채점
ITEMS = {
    "P1": ("plan", +1, "order-착수"),        "P2": ("plan", +1, "self-discipline-마감"),
    "P3": ("plan", +1, "order-산출물"),       "P4": ("plan", -1, "deliberation-변경"),
    "P5": ("plan", -1, "deliberation-사전검토"), "P6": ("plan", -1, "order-협업절차"),

    "L1": ("drive", +1, "발의"),   "L2": ("drive", +1, "역할선점"), "L3": ("drive", +1, "관철"),
    "L4": ("drive", -1, "결정주도"), "L5": ("drive", -1, "자원요구"), "L6": ("drive", -1, "책임귀속"),

    "C1": ("conflict", +1, "제기시점"), "C2": ("conflict", +1, "실수대응"),
    "C3": ("conflict", +1, "반복문제"), "C4": ("conflict", -1, "이견조율"),
    "C5": ("conflict", -1, "제3자충돌"), "C6": ("conflict", -1, "양보"),

    "D1": ("comms", +1, "전달순서"), "D2": ("comms", +1, "거절"), "D3": ("comms", +1, "표현강도"),
    "D4": ("comms", -1, "이견표명"), "D5": ("comms", -1, "문체"), "D6": ("comms", -1, "요청방식"),
}
AXES = ["plan", "drive", "conflict", "comms"]
POLES = {"plan": ("P", "A"), "drive": ("L", "S"),
         "conflict": ("C", "H"), "comms": ("D", "I")}
AXIS_ITEMS = {ax: [i for i, (a, _, _) in ITEMS.items() if a == ax] for ax in AXES}


def keyed(item, value):
    """역채점 적용. 정방향은 그대로, 역방향은 6 − v."""
    v = int(value)
    if not SCALE_MIN <= v <= SCALE_MAX:
        raise ValueError(f"{item}: 응답 {v} 는 1~5 범위 밖입니다")
    return v if ITEMS[item][1] > 0 else (SCALE_MIN + SCALE_MAX) - v


def score_member(name, responses):
    """
    responses: {"P1": 5, "P2": 4, ...} 24문항.
    반환: chemistry_v2 에 그대로 넣을 수 있는 멤버 dict.
    """
    missing = [i for i in ITEMS if i not in responses]
    if missing:
        raise ValueError(f"{name}: 미응답 {len(missing)}문항 — {', '.join(missing[:6])}"
                         + (" …" if len(missing) > 6 else ""))

    out = {"name": name, "ratios": {}, "means": {}, "sd": {}, "unclear": []}
    for ax in AXES:
        vals = [keyed(i, responses[i]) for i in AXIS_ITEMS[ax]]
        m = mean(vals)
        r = (m - SCALE_MIN) / (SCALE_MAX - SCALE_MIN)
        out["means"][ax] = round(m, 2)
        out["sd"][ax] = round(pstdev(vals), 2)
        out["ratios"][ax] = round(r, 3)
        out[ax] = 1 if r > HI else (0 if r < LO else None)
        if out[ax] is None:
            out["unclear"].append(ax)
    return out


def label(member, ax):
    """화면 한 줄. 확신의 정도를 그대로 보인다."""
    m, sd, v = member["means"][ax], member["sd"][ax], member[ax]
    ko = {"plan": "계획성", "drive": "주도성", "conflict": "갈등대응", "comms": "소통"}[ax]
    side = {"plan": ("먼저 그리는 쪽", "먼저 움직이는 쪽"),
            "drive": ("먼저 정하는 쪽", "받쳐주는 쪽"),
            "conflict": ("바로 말하는 쪽", "고르게 만드는 쪽"),
            "comms": ("결론부터 쪽", "배경부터 쪽")}[ax]
    if v is None:
        s = f"{ko}은 뚜렷하지 않습니다 (평균 {m})"
    elif m >= 4.0 or m <= 2.0:
        s = f"{ko}은 {side[0] if v else side[1]}입니다"
    else:
        s = f"{ko}은 {side[0] if v else side[1]}입니다 (평균 {m} / 5점)"
    if sd >= 1.2:
        s += " — 응답이 문항마다 갈렸습니다"
    return s


def acquiescence(responses):
    """
    묵종 지수 — 역채점 전 원응답의 평균. 3.0이 중앙.
    정방향 3 · 역방향 3이 균형이므로, 성향과 무관하게 3.0 근처여야 정상이다.
    3.8 이상이면 '무조건 그렇다', 2.2 이하면 '무조건 아니다' 경향.
    """
    return round(mean(int(responses[i]) for i in ITEMS if i in responses), 2)


def type_code(member, team=None):
    """유형 4글자. 중립은 팀 다수 쪽, 팀이 없거나 동수면 하위 극으로 고정(결정론)."""
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
        code += POLES[ax][0] if v else POLES[ax][1]
    return code, unclear


if __name__ == "__main__":
    demo = {
        # 계획형·주도형·직설형이면서 갈등축은 애매한 사람
        "P1": 5, "P2": 4, "P3": 5, "P4": 2, "P5": 2, "P6": 1,
        "L1": 4, "L2": 5, "L3": 4, "L4": 2, "L5": 3, "L6": 2,
        "C1": 4, "C2": 3, "C3": 3, "C4": 3, "C5": 4, "C6": 3,
        "D1": 5, "D2": 4, "D3": 4, "D4": 2, "D5": 2, "D6": 2,
    }
    m = score_member("예찬", demo)
    print(f"묵종 지수 {acquiescence(demo)}  (3.0 중앙 · 3.8↑ 또는 2.2↓ 면 경고)\n")
    print(f"{'축':<10}{'평균':>6}{'표준편차':>9}{'비율':>7}{'이진':>6}   화면 문구")
    print("─" * 84)
    for ax in AXES:
        b = m[ax]
        print(f"{ax:<10}{m['means'][ax]:>6.2f}{m['sd'][ax]:>9.2f}{m['ratios'][ax]:>7.2f}"
              f"{('중립' if b is None else POLES[ax][0] if b else POLES[ax][1]):>6}   {label(m, ax)}")
    code, unclear = type_code(m)
    print(f"\n유형 {code}   뚜렷하지 않은 축 {unclear or '없음'}")

    print("\n── chemistry_v2 로 넘길 형태 ──")
    print({k: m[k] for k in ["name"] + AXES})
    print("ratios:", m["ratios"])

    print("\n── 역채점 검증 ──")
    for i in ("P1", "P4"):
        d = ITEMS[i][1]
        print(f"  {i} ({'정방향' if d > 0 else '역채점'}): 응답 5 → {keyed(i, 5)} · 응답 1 → {keyed(i, 1)}")

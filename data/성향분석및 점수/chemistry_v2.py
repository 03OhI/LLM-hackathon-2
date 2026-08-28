"""
chemistry.py 연속 확장판 — 24문항의 정보를 안 버린다.

무엇이 달라지나
  현행: 축당 6문항 → 4:2 / 5:1 / 6:0 을 전부 `1`로 뭉갠다. 3:3은 `None`.
        → "6:0 D 3명 vs 6:0 I 2명"과 "4:2 D 3명 vs 4:2 I 2명"이 **같은 점수**가 나온다.
           실제 응답 격차는 1.00 대 0.33인데.
  이 파일: `confidence`("5:1")를 비율(0~1)로 바꿔 그대로 계산에 넣는다.

무엇이 그대로인가
  축별 유사/보완 방향 · 가중치 · 등급 경계 · 게이트 · faultline 규칙 — **전부 그대로**다.
  이건 새 모델이 아니라 **같은 규칙을 연속값 위에서 돌린 것**이다.

  ⚠️ 벡터 유사도로 바꾸지 않는다. 코사인은 모든 축을 "닮을수록 좋다"로 취급하는데
     우리는 계획성은 달라야 좋고 주도성은 비선형이다. 한 숫자로 표현이 안 된다.
     (측정: 유사도 1위가 '전원 캡틴'(B), 2위가 '캡틴 0명'(C)이었다 — RETRIEVAL.md §11)

호환성
  `confidence`가 없으면 1.0 / 0.0 / 0.5로 떨어져 **현행 chemistry.py와 같은 값**을 낸다.
  회귀 테스트가 이 파일 맨 아래에 있다.
"""
from itertools import combinations
import numpy as np
from faultline import diagnose

AXES = ["plan", "drive", "conflict", "comms"]
WEIGHTS = {"drive": 0.35, "comms": 0.25, "conflict": 0.20, "plan": 0.20}
N_ITEMS = 6                      # 축당 문항 수 (SURVEY24.md)

# 등급은 총점 경계가 아니라 "0.5 미만인 축이 몇 개인가"로 정한다 (GRADE_V2.md)
#   경계를 내려도 A 는 7.8% 에서 막혔고, 실제 응답에서는 총점이 0.6~0.9 에 몰려
#   0.45 미만이 0.1% 였다 — 3등급 중 하나가 안 쓰인다.
GRADES = {
    0: "바로 시작해도 되는 조합",
    1: "한 가지만 맞추면 되는 조합",
    2: "두 가지를 맞추고 시작하는 조합",
    3: "먼저 맞출 게 세 가지 이상인 조합",
    None: "응답이 부족해 진단하지 않았습니다",
}

# 판정에 필요한 최소 인원 [팀 판단]
#   축 점수를 낼 사람이 부족한데도 만점을 주던 것이 결함이었다 (DEFENSE.md)
MIN_PAIRS = 3        # 유사축(갈등·소통): 중립 아닌 쌍이 이보다 적으면 판정하지 않는다
MIN_JUDGED = 3       # 주도성: 캡틴/서포터로 판정된 인원
UNJUDGED_ACTION = "비어 있는 축은 진단 대신 첫 회의에서 직접 물어보세요"


# ── 입력 정규화 ────────────────────────────────────────────
def ratio(member, ax):
    """
    축 응답을 0~1 비율로. 1.0 = 6문항 전부 pole-1 쪽.

    confidence["plan"] == "5:1" 은 '고른 쪽이 5개'라는 뜻이므로
    이진값과 합쳐야 방향이 정해진다.  plan==1 → 5/6,  plan==0 → 1/6.
    confidence가 없으면 1.0 / 0.0 / 0.5 (= 현행과 동일).
    """
    # ① 리커트 경로 — likert.score_member() 가 넣어준 ratios 가 있으면 그게 정본이다
    r = (member.get("ratios") or {}).get(ax)
    if r is not None:
        return float(r)

    # ② 양자택일 경로 (v1 하위 호환)
    v = member.get(ax)
    conf = (member.get("confidence") or {}).get(ax)
    if v is None:
        return 0.5                                   # 3:3 중립
    if not conf:
        return float(v)
    hi = int(str(conf).split(":")[0])
    return hi / N_ITEMS if v else 1.0 - hi / N_ITEMS


def is_neutral(member, ax):
    return member.get(ax) is None


# ── 축별 점수 — 방향은 현행과 동일, 값만 연속 ──────────────
def score_plan(rs, neutral):
    """보완: 양극이 벌어질수록 좋다. 중립은 판정에서 제외."""
    d = [r for r, n in zip(rs, neutral) if not n]
    if len(d) < 2:
        return None, ("계획성을 판정할 응답이 부족한 조합", UNJUDGED_ACTION)
    spread = max(d) - min(d)
    if spread == 0.0:                       # 전원이 같은 쪽 — cases.PLAN_ONESIDED
        return 0.40, ("계획 성향이 한쪽에만 몰린 조합",
                      "누가 순서를 잡고 누가 밀어붙일지 먼저 정하세요")
    # 이진에서 '양극 존재'는 spread >= 2/3 에 해당한다. 거기서 1.0이 되도록 맞춘다.
    s = 0.40 + 0.60 * min(1.0, spread / (2 / 3))
    if s < 0.7:
        return round(s, 3), ("계획 성향이 한쪽으로 기운 조합",
                             "누가 순서를 잡고 누가 밀어붙일지 먼저 정하세요")
    return round(s, 3), None


def score_drive(rs, neutral):
    """
    비선형: 캡틴 0명도 전원 캡틴도 나쁘다.

    평균이 아니라 **인원수**로 센다 (SCORE_DRIVE.md).
      평균을 쓰면 '캡틴 2·서포터 3'과 '전원 중립'이 둘 다 r̄ 0.40 이라 같은 만점을 받고,
      '캡틴 0명'은 r̄ == 0 조건이라 리커트에서 사실상 발동하지 않는다.
    경계는 정수 규칙이다 (GRADE_V2.md §9) — 0.95/0.50/0.20 과 값이 완전히 같으면서
    [팀 판단] 파라미터가 사라진다. (0.20 은 5명 팀에서 도달 불가한 죽은 경계였다)
    """
    cap = sum(1 for r, n in zip(rs, neutral) if not n and r > 0.60)
    sup = sum(1 for r, n in zip(rs, neutral) if not n and r < 0.40)
    eff = cap + sup
    if eff < MIN_JUDGED:
        return None, ("주도성을 판정할 응답이 부족한 조합", UNJUDGED_ACTION)
    if cap == 0:
        return 0.0, ("먼저 나서서 정하는 사람이 없는 조합",
                     "첫 회의 진행자를 지금 한 명 지목하세요")
    if cap == eff:                                  # 전원이 캡틴
        return 0.25, ("전원이 주도하려는 조합",
                      "결정권을 사람이 아니라 영역으로 나누세요")
    if cap > eff / 2:                               # 캡틴이 과반
        return 0.45, ("주도적인 구성원이 다수인 조합",
                      "제안은 빨리 나오지만 결정이 늦습니다. 마감 시각을 먼저 정하세요")
    return 1.0, None                                # 1명 이상 과반 이하 — 이상적


def _similarity(rs, neutral):
    """유사가 좋은 축: 쌍 단위 '거리'의 평균. 이진이면 불일치 비율과 정확히 같다."""
    pairs = [(i, j) for i, j in combinations(range(len(rs)), 2)
             if not neutral[i] and not neutral[j]]
    if len(pairs) < MIN_PAIRS:
        return None, None          # 판정 불가. 예전에는 여기서 만점 1.0 을 줬다
    gap = sum(abs(rs[i] - rs[j]) for i, j in pairs) / len(pairs)
    return 1.0 - gap, gap


def score_conflict(rs, neutral):
    s, g = _similarity(rs, neutral)
    if s is None:
        return None, ("갈등대응을 판정할 응답이 부족한 조합", UNJUDGED_ACTION)
    fr = ("갈등을 다루는 방식이 갈린 조합",
          "문제를 그 자리에서 말할지 따로 말할지 규칙을 정하세요") if g >= 0.45 else None
    return round(s, 3), fr


def score_comms(rs, neutral):
    s, g = _similarity(rs, neutral)
    if s is None:
        return None, ("소통을 판정할 응답이 부족한 조합", UNJUDGED_ACTION)
    fr = ("직설과 완곡이 섞인 조합",
          "피드백을 줄 때 형식을 먼저 합의하세요. 초기 오해 1순위입니다") if g >= 0.45 else None
    return round(s, 3), fr


SCORERS = {"plan": score_plan, "drive": score_drive,
           "conflict": score_conflict, "comms": score_comms}

# 쌍 단위 궁합에서 축이 향하는 방향. 팀 단위 규칙과 같다.
#   +1 = 벌어질수록 좋다(보완)   −1 = 가까울수록 좋다(유사)
PAIR_DIRECTION = {"plan": +1, "drive": +1, "conflict": -1, "comms": -1}


def pair_fit(members):
    """
    쌍 단위 궁합 — 예찬 요청('개인간의 조합').

    근거: Andrés et al.(2011) 쌍 단위 지수가 평균보다 우수.
    벡터 유사도가 아니라 **축별 방향을 적용한 가중 합**이다.
    주도성은 쌍 수준에서는 보완(한 명이 끌고 한 명이 받친다)으로 본다.
    n명이면 n(n−1)/2쌍 — 10명이어도 45쌍이라 전수 계산이 즉시 끝난다.
    """
    R = {ax: [ratio(m, ax) for m in members] for ax in AXES}
    NU = {ax: [is_neutral(m, ax) for m in members] for ax in AXES}
    out = []
    for i, j in combinations(range(len(members)), 2):
        per, total = {}, 0.0
        for ax in AXES:
            if NU[ax][i] or NU[ax][j]:
                per[ax] = None                       # 중립이 끼면 판정하지 않는다
                continue
            gap = abs(R[ax][i] - R[ax][j])
            per[ax] = round(gap if PAIR_DIRECTION[ax] > 0 else 1.0 - gap, 3)
            total += per[ax] * WEIGHTS[ax]
        w = sum(WEIGHTS[ax] for ax in AXES if per[ax] is not None) or 1.0
        out.append({
            "a": members[i]["name"], "b": members[j]["name"],
            "fit": round(total / w, 3), "axes": per,
        })
    return sorted(out, key=lambda p: -p["fit"])


# ── 팀 종합 ────────────────────────────────────────────────
def compute_chemistry(members, with_pairs=True):
    axis_scores, frictions = {}, []
    R = {ax: [ratio(m, ax) for m in members] for ax in AXES}
    NU = {ax: [is_neutral(m, ax) for m in members] for ax in AXES}

    for ax in AXES:
        s, fr = SCORERS[ax](R[ax], NU[ax])
        axis_scores[ax] = None if s is None else round(s, 3)   # None = 판정하지 않음
        if fr:
            frictions.append({"axis": ax, "label": fr[0], "action": fr[1]})

    unjudged = [ax for ax in AXES if axis_scores[ax] is None]

    # 총점은 화면 표시용이다. 등급을 정하지 않는다 (GRADE_V2.md).
    # 판정된 축만으로 가중 평균하고 가중치를 재정규화한다.
    known = {a: v for a, v in axis_scores.items() if v is not None}
    wsum = sum(WEIGHTS[a] for a in known)
    total = (sum(known[a] * WEIGHTS[a] for a in known) / wsum) if wsum else None

    X = [[R[ax][i] for ax in AXES] for i in range(len(members))]
    diag = diagnose(X)

    demoted = diag["kind"] == "두 편으로 갈라진 조합"
    if demoted:
        if total is not None:
            total *= 0.75
        frictions.insert(0, {
            "axis": "team", "label": "팀이 두 편으로 갈라진 조합",
            "action": "역할을 두 편에서 교차로 배치하세요. 같은 편끼리 묶으면 사흘째에 벌어집니다"})
    elif diag["kind"] == "한 사람이 겉도는 조합":
        if total is not None:
            total *= 0.85
        frictions.insert(0, {
            "axis": "team", "label": "한 구성원만 나머지와 성향이 다른 조합",
            "action": "그 한 명에게 먼저 말할 자리를 주세요. 다수결로 가면 계속 밀립니다"})

    gates = []
    if axis_scores["drive"] == 0.0:
        gates.append("drive_zero")
    if len(unjudged) >= 2:
        gates.append("too_many_unjudged")

    # ── 등급 = 0.5 미만인 축의 개수 (GRADE_V2.md)
    #    axis_below_half 게이트는 이 규칙이 흡수해 사라졌다.
    if len(unjudged) >= 2:
        grade = None                                  # 진단하지 않는다
    elif "drive_zero" in gates:
        grade = 3
    else:
        weak = sum(1 for v in axis_scores.values() if v is not None and v < 0.5)
        if demoted:
            weak += 1
        grade = min(weak, 3)

    out = {
        "grade": grade, "grade_label": GRADES[grade],
        "total": None if total is None else round(total, 3),
        "axes": axis_scores, "unjudged_axes": unjudged,
        "ratios": {ax: [round(v, 3) for v in R[ax]] for ax in AXES},
        "faultline": {k: round(v, 3) for k, v in diag.items()
                      if k in ("fau", "asw", "breadth", "balance", "adjusted")},
        "faultline_kind": diag["kind"], "demoted_by_faultline": demoted,
        "gates": gates, "frictions": frictions[:2],
    }
    if with_pairs:
        p = pair_fit(members)
        out["pairs"] = p
        out["pair_best"] = p[0] if p else None
        out["pair_worst"] = p[-1] if p else None
    return out


# ── 회귀 테스트 — confidence가 없으면 현행과 같은 값이어야 한다 ──
if __name__ == "__main__":
    import chemistry as v1

    print("── v1 대비 변경분 (2026-08-28 이후 등급 체계가 다르므로 '같음'이 목표가 아니다)")
    print("   v1: 총점 경계 A/B/C · v2: 0.5 미만인 축의 개수 0~3, 판정 불가면 None")
    for name, ms in v1.CASES.items():
        a, b = v1.compute_chemistry(ms), compute_chemistry(ms, with_pairs=False)
        bt = "—" if b["total"] is None else f"{b['total']:.3f}"
        uj = f" · 판정불가 {b['unjudged_axes']}" if b["unjudged_axes"] else ""
        print(f"  {name:<26} v1 {a['grade']} {a['total']:.3f}   →   v2 {str(b['grade']):<4} {bt}{uj}")
    print()

    print("── 연속: 같은 이진 코드인데 응답 분포가 다른 두 팀")
    def team(conf_hi):
        return [{"name": f"M{i+1}", "plan": 1, "drive": 1, "conflict": 1,
                 "comms": 1 if i < 3 else 0,
                 "confidence": {"plan": "5:1", "drive": "4:2",
                                "conflict": "5:1", "comms": conf_hi}} for i in range(5)]
    for label, c in [("완전 대립 (6:0)", "6:0"), ("약한 기울기 (4:2)", "4:2")]:
        r = compute_chemistry(team(c))
        print(f"  {label:<18} 소통 {r['axes']['comms']:.2f} · 등급 {r['grade']} · 총점 {r['total']:.3f}"
              f"  | 최고쌍 {r['pair_best']['a']}–{r['pair_best']['b']} {r['pair_best']['fit']}"
              f"  최저쌍 {r['pair_worst']['a']}–{r['pair_worst']['b']} {r['pair_worst']['fit']}")

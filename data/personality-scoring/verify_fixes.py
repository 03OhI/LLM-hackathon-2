# -*- coding: utf-8 -*-
"""
수정 4건 수용 테스트 — 고치고 나서 이걸 돌린다. 전부 ✅ 면 끝.

    python verify_fixes.py

무엇을 확인하는가
  ① chemistry_v2._similarity()   유효 쌍이 부족하면 만점 대신 None 을 주는가   (DEFENSE.md)
  ② chemistry_v2.score_drive()   평균이 아니라 인원수로 세는가 · 정수 규칙인가  (SCORE_DRIVE.md · GRADE_V2.md §9)
  ③ faultline.diagnose()         '부분적으로 갈린 조합' 이 4개로 쪼개졌는가      (PARTIAL_SPLIT.md)
  ④ cases.TEAM_CASES             16건인가 · 문단 구별도가 0.75 미만인가          (PARTIAL_SPLIT.md §4)
  ⑤ 실제 응답 22건               등급 분포가 예상대로 나오는가                    (ALPHA_RESULT.md)

수정 전에 돌리면 ①②③④ 가 🔴 로 뜬다. 그게 정상이다.
"""
import sys, json, math, re, os
from itertools import combinations, combinations_with_replacement
from collections import Counter

OK, NG, SKIP = "✅", "🔴", "⚪"
results = []
def check(name, cond, detail=""):
    results.append(cond)
    print(f"  {OK if cond else NG} {name}" + (f"\n      {detail}" if detail else ""))

print("=" * 74)
print("수정 4건 수용 테스트")
print("=" * 74)

# ──────────────────────────────────────────── ① _similarity
print("\n① _similarity() — 판정할 쌍이 없으면 만점 대신 None")
try:
    from chemistry_v2 import _similarity
    # 5명 중 4명이 중립 → 유효 쌍 0개
    rs = [0.9, 0.5, 0.5, 0.5, 0.5]
    nu = [False, True, True, True, True]
    s, _ = _similarity(rs, nu)
    check("유효 쌍 0개 → None", s is None,
          f"현재 반환 {s!r} — 1.0 이면 '판정 불가'가 '만점'이 된다")
    # 유효 쌍 1개
    nu2 = [False, False, True, True, True]
    s2, _ = _similarity(rs, nu2)
    check("유효 쌍 1개 → None (MIN_PAIRS=3 미만)", s2 is None, f"현재 반환 {s2!r}")
    # 유효 쌍 충분
    s3, _ = _similarity([0.9, 0.8, 0.7, 0.2, 0.1], [False] * 5)
    check("유효 쌍 10개 → 숫자", isinstance(s3, float), f"반환 {s3!r}")
except Exception as e:
    check("_similarity 로드", False, f"{type(e).__name__}: {e}")

# ──────────────────────────────────────────── ② score_drive
print("\n② score_drive() — 평균이 아니라 인원수. 정수 규칙")
try:
    from chemistry_v2 import score_drive
    def sd(rs):
        nu = [0.40 <= r <= 0.60 for r in rs]
        v = score_drive(rs, nu)
        return v[0] if isinstance(v, tuple) else v

    check("전원 중립 → None (만점 아님)", sd([0.5] * 5) is None,
          f"현재 {sd([0.5]*5)!r} — 1.0 이면 중립이 만점을 만든다")
    check("캡틴 0 · 약한 서포터(r=.15) → 0.00 게이트", sd([0.15] * 5) == 0.00,
          f"현재 {sd([0.15]*5)!r} — r̄==0 조건이면 실전에서 안 걸린다")
    a, b = sd([0.9, 0.85, 0.8, 0.75, 0.2]), sd([0.65, 0.65, 0.65, 0.65, 0.10])
    check("캡틴 4명은 뚜렷하든 약하든 같은 값", a == b == 0.45,
          f"뚜렷 {a!r} · 약함 {b!r} — 달라지면 평균을 보고 있는 것")
    check("캡틴 2 · 서포터 3 → 1.00 (이상적)", sd([1.0, 1.0, 0.0, 0.0, 0.0]) == 1.00)
    check("전원 캡틴 → 0.25", sd([1.0] * 5) == 0.25)
except Exception as e:
    check("score_drive 로드", False, f"{type(e).__name__}: {e}")

# ──────────────────────────────────────────── ③ diagnose
print("\n③ faultline.diagnose() — '부분적으로 갈린 조합' 4분할")
NEW_KINDS = {"차이가 두 가지 성향에서만 나타나는 조합",
             "세 가지 성향에서 차이가 나는 조합",
             "매번 다른 사람끼리 같은 편이 되는 조합",
             "같은 두 무리가 반복해서 생기는 조합"}
try:
    from faultline import diagnose
    TYPES = [p + l + c + d for p in "PA" for l in "LS" for c in "CH" for d in "DI"]
    vec = lambda c: [int(c[0] == "P"), int(c[1] == "L"), int(c[2] == "C"), int(c[3] == "D")]
    kinds = Counter()
    # combinations_with_replacement 여야 한다. 같은 유형이 겹치는 팀을 빼면
    # '차이가 두 축에만' 같은 진단이 아예 안 나온다 (축 두 개의 분산이 0이어야 하므로)
    for k, t in enumerate(combinations_with_replacement(TYPES, 5)):   # 7팀 중 1팀
        if k % 7: continue
        kinds[diagnose([vec(c) for c in t])["kind"]] += 1
    check("'부분적으로 갈린 조합' 이 사라졌는가", "부분적으로 갈린 조합" not in kinds,
          f"남아 있으면 미수정. 현재 진단 {len(kinds)}종")
    check("새 진단 4종이 모두 나오는가", NEW_KINDS <= set(kinds),
          f"빠진 것: {NEW_KINDS - set(kinds) or '없음'}")
except Exception as e:
    check("diagnose 로드", False, f"{type(e).__name__}: {e}")

# ──────────────────────────────────────────── ④ cases
print("\n④ cases.TEAM_CASES — 16건 · 문단 구별도")
try:
    from cases import TEAM_CASES
    ids = {c["id"] for c in TEAM_CASES}
    check("16건인가", len(TEAM_CASES) == 16, f"현재 {len(TEAM_CASES)}건")
    check("TEAM_PARTIAL 이 제거됐는가", "TEAM_PARTIAL" not in ids)
    want = {"PARTIAL_TWO_AXIS", "PARTIAL_THREE_AXIS", "PARTIAL_SHIFTING", "PARTIAL_HARDENING"}
    check("분할 4건이 들어갔는가", want <= ids, f"빠진 것: {want - ids or '없음'}")
    want2 = {"PLAN_TILTED", "AXIS_UNJUDGED"}
    check("케이스 없던 마찰 2건이 채워졌는가", want2 <= ids, f"빠진 것: {want2 - ids or '없음'}")

    def ng(t, lo=2, hi=3):
        s = re.sub(r"\s+", " ", t.strip()); o = []
        for n in range(lo, hi + 1):
            o += [s[i:i+n] for i in range(len(s)-n+1) if s[i:i+n].strip()]
        return o
    docs = [(c["id"], c["query"] + " " + c["text"]) for c in TEAM_CASES]
    tfs = {d: Counter(ng(t)) for d, t in docs}
    df = Counter()
    for tf in tfs.values(): df.update(tf.keys())
    idf = {g: math.log((1+len(docs))/(1+c)) + 1.0 for g, c in df.items()}
    V = {}
    for d, tf in tfs.items():
        v = {g: (1+math.log(c))*idf[g] for g, c in tf.items()}
        nm = math.sqrt(sum(x*x for x in v.values())) or 1.0
        V[d] = {g: x/nm for g, x in v.items()}
    idl = [d for d, _ in docs]
    pairs = sorted(((sum(x*V[idl[j]].get(g, 0.0) for g, x in V[idl[i]].items()), idl[i], idl[j])
                    for i in range(len(idl)) for j in range(i+1, len(idl))), reverse=True)
    check(f"문단 구별도 최대 {pairs[0][0]:.3f} < 0.75", pairs[0][0] < 0.75,
          f"가장 닮은 쌍: {pairs[0][1]} ↔ {pairs[0][2]}")
except Exception as e:
    check("cases 로드", False, f"{type(e).__name__}: {e}")

# ──────────────────────────────────────────── ⑤ 실제 응답
print("\n⑤ 실제 응답 22건 — 끝단까지 돌아가는가")
if not os.path.exists("responses22.jsonl"):
    print(f"  {SKIP} responses22.jsonl 이 없어 건너뜀")
else:
    try:
        from likert import score_member
        from chemistry_v2 import compute_chemistry
        rows = [json.loads(l) for l in open("responses22.jsonl", encoding="utf-8")]
        mem = [score_member(r["name"], r["likert"]) for r in rows]
        g = Counter(); unk = 0
        for t in list(combinations(range(len(mem)), 5))[:3000]:
            r = compute_chemistry([mem[i] for i in t], with_pairs=False)
            g[r["grade"]] += 1
            unk += sum(1 for v in r["axes"].values() if v is None)
        check("에러 없이 3,000팀 계산", True, f"등급 분포 {dict(g)}")
        check("판정 불가 축(None)이 실제로 발생하는가", unk > 0,
              f"None 축 {unk}건 — 0 이면 아직 만점을 주고 있다")
    except Exception as e:
        check("끝단 실행", False, f"{type(e).__name__}: {e}")

# ──────────────────────────────────────────── 요약
print("\n" + "=" * 74)
n_ok, n = sum(results), len(results)
print(f"{n_ok} / {n} 통과")
if n_ok == n:
    print("✅ 수정 완료. GRADE_V2.md · ALPHA_RESULT.md 의 분포와 대조해 보세요.")
else:
    print("🔴 남은 항목이 있습니다. 각 항목 옆 문서를 보세요:")
    print("   ① DEFENSE.md   ② SCORE_DRIVE.md · GRADE_V2.md §9")
    print("   ③④ PARTIAL_SPLIT.md (붙여넣기용 리터럴은 cases_partial_split.py)")
sys.exit(0 if n_ok == n else 1)

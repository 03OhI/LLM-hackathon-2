"""
Faultline 계산 — 두 방식 모두 구현하고 교차 검증한다.

  Fau  : Thatcher, Jehn & Zanutto (2003) — 집단 간 제곱합 / 전체 제곱합, 최적 2분할 기준
  ASW  : Meyer & Glenz (2013)            — Rousseeuw(1987) 실루엣 폭 기반, 다중 하위집단 지원

팀이 10명 이하이므로 두 방식 모두 **전수 탐색**한다. 근사가 아니라 정확한 최댓값이다.
"""
from itertools import combinations
import numpy as np


# ─────────────────────────────────────────────────────────────
# Fau — Thatcher, Jehn & Zanutto (2003)
# ─────────────────────────────────────────────────────────────
def fau(X):
    """
    X : (n, p) 행렬. n=멤버 수, p=축 수. 이진(0/1)이어도 되고 연속이어도 된다.
    반환 : (Fau 값 0~1, 최적 분할 인덱스 튜플)

    Fau = max over all 2-splits g of  SSB(g) / SST
      SST = Σ_j Σ_i (x_ij - x̄_j)²                     전체 제곱합
      SSB = Σ_j Σ_{k=1,2} n_k (x̄_jk - x̄_j)²          집단 간 제곱합
    """
    X = np.asarray(X, dtype=float)
    n = len(X)
    grand = X.mean(axis=0)                       # 축별 전체 평균 x̄_j
    sst = ((X - grand) ** 2).sum()               # 전체 제곱합
    if sst == 0:
        return 0.0, None                         # 전원 동일 → 갈라질 게 없다

    best, best_split = 0.0, None
    # 2^(n-1) - 1 개의 분할. n=10이면 511개 — 전수 탐색이 즉시 끝난다.
    for size in range(1, n // 2 + 1):
        for idx in combinations(range(n), size):
            g1 = np.array(idx)
            g2 = np.array([i for i in range(n) if i not in idx])
            if len(g2) == 0:
                continue
            ssb = (len(g1) * (X[g1].mean(axis=0) - grand) ** 2).sum() \
                + (len(g2) * (X[g2].mean(axis=0) - grand) ** 2).sum()
            if ssb / sst > best:
                best, best_split = ssb / sst, (tuple(g1), tuple(g2))
    return best, best_split


# ─────────────────────────────────────────────────────────────
# ASW — Meyer & Glenz (2013) / 실루엣: Rousseeuw (1987)
# ─────────────────────────────────────────────────────────────
def _silhouette(X, labels):
    """
    s(i) = (b(i) - a(i)) / max{a(i), b(i)}
      a(i) = 자기 클러스터 내 다른 점들과의 평균 거리
      b(i) = 가장 가까운 다른 클러스터와의 평균 거리
      |C_i| = 1 이면 s(i) = 0
    ASW = mean_i s(i)
    """
    n = len(X)
    D = np.abs(X[:, None, :] - X[None, :, :]).sum(axis=2)   # 맨해튼(이진이면 해밍)
    s = np.zeros(n)
    for i in range(n):
        own = labels == labels[i]
        own[i] = False
        if own.sum() == 0:
            s[i] = 0.0                                       # 혼자인 클러스터
            continue
        a = D[i, own].mean()
        b = min(D[i, labels == c].mean()
                for c in set(labels) if c != labels[i])
        s[i] = (b - a) / max(a, b) if max(a, b) > 0 else 0.0
    return s.mean()


def asw_faultline(X, max_k=None):
    """
    가능한 모든 분할(2개 이상 하위집단)을 전수 탐색해 ASW 최댓값을 찾는다.
    반환 : (ASW 0~1, 최적 라벨 배열)
    """
    X = np.asarray(X, dtype=float)
    n = len(X)
    max_k = max_k or n - 1
    best, best_labels = -1.0, None

    def partitions(elems):
        """집합의 모든 분할을 생성한다 (벨 수). n<=10이면 115975개 이하."""
        if len(elems) == 1:
            yield [elems]
            return
        first, rest = elems[0], elems[1:]
        for p in partitions(rest):
            for i in range(len(p)):
                yield p[:i] + [[first] + p[i]] + p[i + 1:]
            yield [[first]] + p

    for part in partitions(list(range(n))):
        if not (2 <= len(part) <= max_k):
            continue
        labels = np.empty(n, dtype=int)
        for c, grp in enumerate(part):
            labels[grp] = c
        val = _silhouette(X, labels)
        if val > best:
            best, best_labels = val, labels.copy()
    return max(best, 0.0), best_labels


# ─────────────────────────────────────────────────────────────
# 보정 2개 — 논문 수식을 그대로 쓰면 오판하는 두 케이스를 잡는다
# ─────────────────────────────────────────────────────────────
def breadth(X):
    """몇 개 축이 실제로 갈렸는가 (분산이 0이 아닌 축의 비율).

    Fau는 분산이 0인 축을 무시한다. 3축이 전원 동일하고 1축만 갈리면
    SSB/SST = 1.0 이 되어 '완전 분열'로 나온다 — 실제로는 한 축만 다르다.
    """
    X = np.asarray(X, dtype=float)
    return float((X.var(axis=0) > 1e-12).mean())


def balance(split):
    """하위집단 크기 비 (0~1). 4:1이면 분열이 아니라 소외다."""
    if split is None:
        return 0.0
    a, b = len(split[0]), len(split[1])
    return min(a, b) / max(a, b)


def diagnose(X):
    """
    세 지표를 합쳐 진단명을 낸다. 이게 '마찰 예상 지점'의 최상위 규칙이다.

    ⚠️ ASW 는 계산해서 결과에 넣지만 판정에는 쓰지 않는다. 분기는 전부 Fau·balance·breadth 다.
       Meyer & Glenz(2013)를 인용할 때는 이 사실을 함께 말해야 한다.
       다만 두 방법이 어긋나지는 않는다 — 5명 팀 15,504개 전수에서 이 함수가
       '한 사람이 겉도는 조합'으로 판정한 3,414건은 100% ASW 최적 분할에서도
       크기 1인 하위집단을 갖는다 (2026-08-28 측정). 반대로 ASW 가 잡고 현행이
       놓치는 경우는 4,266건(27.5%) 있다 — ASW 쪽이 더 민감하다.
    """
    f, split = fau(X)
    a, _ = asw_faultline(X)
    br, bal = breadth(X), balance(split)
    adjusted = f * br                      # 갈라짐의 선명도 × 폭

    if f < 0.35:
        kind = "고르게 섞인 조합"
    elif bal <= 0.34:
        kind = "한 사람이 겉도는 조합"      # 4:1, 5:1 — 분열이 아니라 소외
    elif br <= 0.35:
        kind = "한 가지만 다른 조합"        # 축 하나만 갈림 — 가장 쉽게 풀린다
    elif adjusted >= 0.6:
        kind = "두 편으로 갈라진 조합"      # 가장 위험
    # ── 이하 4분기: 옛 "부분적으로 갈린 조합"(전수의 59.0%)을 쪼갠 것 (PARTIAL_SPLIT.md)
    #    balance 는 이 구간에서 상수(2:3 = 0.667)라 쓸 수 없다. breadth 와 Fau 로 가른다.
    elif br <= 0.50:
        kind = "차이가 두 가지 성향에서만 나타나는 조합"
    elif br <= 0.75:
        kind = "세 가지 성향에서 차이가 나는 조합"
    elif f < 0.50:                          # 최적 2분할이 분산의 절반도 설명 못 한다
        kind = "매번 다른 사람끼리 같은 편이 되는 조합"
    else:
        kind = "같은 두 무리가 반복해서 생기는 조합"
    return dict(fau=f, asw=a, breadth=br, balance=bal,
                adjusted=adjusted, kind=kind, split=split)


# ─────────────────────────────────────────────────────────────
# 검증 — 축 순서: [계획성 P=1, 주도성 L=1, 갈등 C=1, 소통 D=1]
# ─────────────────────────────────────────────────────────────
CASES = {
    "완전 분열 (3명 vs 2명, 4축 전부 반대)": [
        [1, 1, 1, 1], [1, 1, 1, 1], [1, 1, 1, 1],
        [0, 0, 0, 0], [0, 0, 0, 0],
    ],
    "한 축만 갈림 (나머지 3축은 동일)": [
        [1, 1, 1, 1], [1, 1, 1, 1], [1, 1, 1, 1],
        [1, 1, 1, 0], [1, 1, 1, 0],
    ],
    "잘 섞임 (축마다 다르게 갈림)": [
        [1, 1, 0, 0], [1, 0, 1, 0], [0, 1, 0, 1],
        [0, 0, 1, 1], [1, 1, 1, 0],
    ],
    "전원 동일": [
        [1, 1, 1, 1], [1, 1, 1, 1], [1, 1, 1, 1],
        [1, 1, 1, 1], [1, 1, 1, 1],
    ],
    "1명만 이질 (외톨이 패턴)": [
        [1, 1, 1, 1], [1, 1, 1, 1], [1, 1, 1, 1],
        [1, 1, 1, 1], [0, 0, 0, 0],
    ],
}

if __name__ == "__main__":
    hdr = f"{'케이스':<34}{'Fau':>6}{'ASW':>7}{'폭':>7}{'균형':>7}{'보정':>7}   진단"
    print(hdr)
    print("─" * 104)
    for name, X in CASES.items():
        r = diagnose(X)
        print(f"{name:<34}{r['fau']:>6.2f}{r['asw']:>7.2f}{r['breadth']:>7.2f}"
              f"{r['balance']:>7.2f}{r['adjusted']:>7.2f}   {r['kind']}")

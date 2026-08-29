# 케이스 ↔ 논문 손매핑 표

> 2026-08-28 작성 · 기계용 정본은 `evidence_map.json` · 대상은 `cases.py` TEAM_CASES 11건 + 케이스 없는 마찰 2건
> 검색을 뺐으므로(보고서 6장) **이 표가 근거 표시의 유일한 경로다.**

---

## 0. 이 표를 만든 원칙 — 억지로 붙이지 않는다

2026-08-28에 `DRIVE_NONE`의 근거였던 Halfhill et al.(2005)을 열어보니 **원문이 우리 주장을 지지하지 않았다.** 우리는 "평균이 낮은 값을 가려버린다"고 썼는데, 초록은 *"minimum scores predict **as well as** mean scores"* 였다. 인용을 안 열고 붙였다가 발표에서 그대로 말할 뻔했다.

그래서 이 표의 규칙은 셋이다.

1. **초록 이상을 직접 읽은 것만 붙인다.** 읽지 않은 것은 칸을 비운다.
2. **지지 강도를 나눠 적는다.** 직접 / 간접 / 방법론. 간접을 직접인 것처럼 말하지 않는다.
3. **논문이 없는 자리는 `[규칙]`으로 남긴다.** 팀이 정한 규칙임을 밝히는 것이 억지 인용보다 강하다.

`evidence_finding`이 비면 화면에 출처를 띄우지 않는 게이트가 이미 코드에 있다. 이 표는 그 게이트를 채우는 문서다.

---

## 1. 매핑 표

| # | 케이스 | 논문 | 지지 강도 | 상태 |
|---|---|---|---|---|
| 1 | **TEAM_SPLIT** 팀이 두 편으로 갈라진 조합 | Thatcher, Jehn & Zanutto (2003) | 직접 ⚠️ | 원문 대조 |
| 2 | **TEAM_ISOLATED** 한 구성원만 성향이 다른 조합 | Meyer & Glenz (2013) | 방법론 ⚠️ | 원문 대조 |
| 3 | **DRIVE_NONE** 먼저 나서서 정하는 사람이 없는 조합 | 노연희·손영우 (2012) · Flores Ureba et al. (2022) | 직접 | 원문 대조 · **Halfhill에서 교체** |
| 4 | **DRIVE_ALL** 전원이 주도하려는 조합 | Flores Ureba et al. (2022) | 간접 | 원문 대조 |
| 5 | **DRIVE_EXCESS** 주도적인 구성원이 다수인 조합 | 노연희·손영우 (2012) | 간접 | 원문 대조 |
| 6 | **CONFLICT_SPLIT** 갈등을 다루는 방식이 갈린 조합 | Triana et al. (2021) | 직접 | 원문 대조 |
| 7 | **COMMS_SPLIT** 직설과 완곡이 섞인 조합 | — | — | **`[규칙]`** |
| 8 | **PLAN_ONESIDED** 계획 성향이 한쪽에만 몰린 조합 | Flores Ureba et al. (2022) · Adamis et al. (2023) | 직접 | 원문 대조 |
| 9 | **TEAM_PARTIAL** 일부 성향에서만 경계가 생기는 조합 | — | — | **`[규칙]`** |
| 10 | **TEAM_ONE_AXIS** 성향 한 가지에서만 갈리는 조합 | — | — | **`[규칙]`** |
| 11 | **TEAM_MIXED** 성향이 고르게 섞인 조합 (폴백) | Thatcher, Jehn & Zanutto (2003) ⭐ | 직접 | 원문 대조 |
| 12 | *(케이스 없음)* 계획 성향이 한쪽으로 기운 조합 | Flores Ureba et al. (2022) | 직접 | **케이스부터 써야 함** |
| 13 | *(케이스 없음)* 주도하는 사람이 한쪽으로 기운 조합 | 노연희·손영우 (2012) | 간접 | **케이스부터 써야 함** |

**논문이 붙는 자리 8 / `[규칙]` 3 / 케이스 자체가 없는 자리 2.**

---

## 2. 붙인 문장 (화면에 그대로 나갈 것)

**1 · TEAM_SPLIT — Thatcher, Jehn & Zanutto (2003), 79개 집단**
> "Groups with either virtually no faultlines (very diverse members) or strong faultlines (split into 2 fairly homogeneous subgroups) had higher levels of conflict and lower levels of morale and performance than groups with medium faultlines."

⚠️ **곡선 관계다.** "두 편으로 갈라지면 나쁘다"는 절반만 우리 설계와 맞는다. 나머지 절반은 11번으로 간다.

**2 · TEAM_ISOLATED — Meyer & Glenz (2013)**
> "the ASW measure had the most favorable attributes and was the only measure that accurately determined subgroup membership in the presence of more than two subgroups"

⚠️ `faultline.py`는 ASW를 계산하지만 `diagnose()`가 판정에 쓰지 않는다. 판정은 `balance ≤ 0.34`(Fau 기반)로 나온다. **근거와 판정 경로가 다르므로, 고칠 때까지 화면 출처로 쓰지 말 것.**

**3 · DRIVE_NONE — 노연희·손영우 (2012), 67개 팀 315명**
> 우호성 최솟값이 과제의 연구논리 점수와 부적 상관(r = −.26, p<.05). Steiner(1972)의 합동과제에서는 팀의 가장 약한 부분이 치명적이므로 최솟값이 팀 수준의 적절한 조작적 정의다(Bell, 2007).

🔴 **Halfhill et al.(2005)에서 교체했다.** 원문이 "최솟값이 평균 **만큼** 예측한다"여서 우리 주장을 지지하지 않는다. 보고서 §5.4의 문장도 같이 고쳐야 한다.

**4 · DRIVE_ALL / 8 · PLAN_ONESIDED — Flores Ureba et al. (2022), 149명 21개 그룹**
> "balanced groups facilitate greater homogeneity in group grades, improving the performance of the group overall"

Belbin 역할 균형 그룹 vs 비균형 그룹 비교. **학부생 팀 과제**라 우리 사용자 맥락과 정확히 겹친다.

**5 · DRIVE_EXCESS — 노연희·손영우 (2012)**
> 다양성과 성과의 관계가 선형이 아니며 적정한 수준의 다양성 범위가 존재한다.

간접이다. 원 결과는 인구통계·인지 다양성이고 성향 다양성이 아니다 — "성향에도 적정 구간이 있다"고 말하면 안 된다.

**6 · CONFLICT_SPLIT — Triana et al. (2021)**
> "team deep-level diversity is associated with fewer positive emergent states and positive team processes and more team conflict"

**8 · PLAN_ONESIDED 보강 — Adamis et al. (2023), 106명 8팀**
> 역할 다양성이 팀 효과성의 유의한 독립 예측변인. "The more diverse roles the members of a team have, the better the effectiveness of the team."

**11 · TEAM_MIXED — Thatcher, Jehn & Zanutto (2003)** ⭐
같은 논문의 **반대쪽 절반**이다. faultline이 거의 없는 집단(매우 다양한 구성원)도 중간 집단보다 갈등이 많고 성과가 낮았다.

→ **폴백 문단이 "문제 없음"으로 읽히면 안 된다.** 현재 코드는 `Fau < 0.35`를 "고르게 섞인 조합"으로 두고 보정을 안 한다. 논문에 따르면 그것도 주의 구간이다. 문단을 그렇게 다시 써야 한다.

---

## 3. `[규칙]`으로 남기는 자리 3곳과 그 이유

| 케이스 | 왜 논문을 안 붙이는가 |
|---|---|
| **COMMS_SPLIT** | 소통 직접성 축은 확립된 척도에 대응하지 않는다. 팀이 현장 관찰로 추가한 축이다(`SURVEY24.md` §5). **이 자리에 논문을 붙이면 "네 축 전부 논문 근거"라는 금지 문장이 된다.** |
| **TEAM_PARTIAL** | faultline 판정의 `else` 분기다. "앞 조건에 안 걸린 나머지"라서 대응하는 구성개념이 없다. 전수의 59%가 여기 떨어지므로 **분할이 먼저고 논문은 그 다음이다.** |
| **TEAM_ONE_AXIS** | 축 하나만 갈리는 경우. `breadth` 보정은 우리가 만든 것이지 논문 수식이 아니다. |

**발표에서는 이게 약점이 아니라 강점이다.** *"근거가 있는 것만 출처를 답니다. 나머지는 저희가 정한 규칙이라고 화면에 씁니다."*

---

## 4. 케이스가 아니라 문제 정의에 쓰는 문헌 (섞지 말 것)

| 문헌 | 확인된 사실 | 자리 |
|---|---|---|
| Harrison et al. (2003) *Personnel Psychology* 56(3) 633–669 | 단회 팀은 일관되게 느리고 품질 낮음. 계속 만난 팀은 따라잡음 | 문제 정의 |
| 이혜주·이정현 (2024) *APJCRI* 10(1) 561–570 | MBTI 기질별 팀 만족도 차이 유의하지 않음. 최고점/최저점 팀의 구성에는 차이 | 문제 정의 · 주제 선정 |
| 최신혜·양석준 (2012) *상업교육연구* 26(4) | 사전 이해 + 역할 부여 → 과정·결과·개인 성과 모두 향상 | 문제 정의 |
| 박준기·이세윤 (2017) *산업혁신연구* 33(1) 1–26 | 스타트업 실무자 21명 Q방법론. **팀워크 인식 유형이 4가지**(커뮤니케이션 지향·목적 지향·감성 중심·지식 공유) | 문제 정의 — *"좋은 팀워크가 뭔지부터 사람마다 다르다"* |
| 윤종훈 외 (한국원자력연구원) | *"인적성과 같은 개인의 성향만으로는 부서배치, 직무할당 등에 필요한 정보가 불충분하다"* | 주제 선정 — 단, **`[서지 미확정]`** (학술대회 발표문으로 보이며 연도·게재지 확인 안 됨). 화면 출처로 쓰지 말 것 |

---

## 5. 화면 표기 규칙

```
evidence_finding 이 있고  강도 = 직접   → 출처를 화면에 표시한다
evidence_finding 이 있고  강도 = 간접   → 표시하되 "관련 연구" 로 적는다
강도 = 방법론 이거나 caveat 이 있음     → 고칠 때까지 표시하지 않는다
evidence_ref 가 없음                    → "[규칙] 저희가 정한 기준입니다" 로 적는다
```

**절대 하지 말 것**: 원문을 열지 않은 논문을 `evidence_finding`에 요약으로 채우는 것. 그게 Halfhill 사고의 원인이었다.

---

## 6. 다음 할 일

1. **`TEAM_PARTIAL` 분할(할 일 1번)이 끝나면 이 표에 3~4행이 추가된다.** 새 케이스에도 논문을 붙일지 `[규칙]`으로 둘지 그때 정한다 — 지금 예상으로는 전부 `[규칙]`이다.
2. **케이스 없는 마찰 2건**(12·13번)을 `cases.py`에 추가한다. 12번은 전수의 10.2%에 발화 중인데 설명 문단이 없다.
3. **`TEAM_MIXED` 문단을 다시 쓴다.** Thatcher의 반대쪽 절반을 반영해 "문제 없음"이 아니라 "주의 구간"으로.
4. **보고서 §5.4의 Halfhill 문장을 고친다.** 발표 대사에 들어가 있으면 같이.
5. `diagnose()`가 ASW를 판정에 쓰게 하거나, `TEAM_ISOLATED`의 인용 범위를 좁힌다.

---

## 7. 발표 문장

> "저희는 마찰 규칙마다 논문을 손으로 매핑했습니다. 검색으로 근거를 찾지 않은 이유는, 21건 규모에서는 손매핑이 더 정확하기 때문입니다. 그리고 **모든 규칙에 논문을 붙이지는 않았습니다** — 열한 개 중 여덟 개만 붙였고, 세 개는 화면에 '저희가 정한 규칙'이라고 씁니다. 실제로 근거를 확인하는 과정에서 인용 하나가 원문과 맞지 않는 걸 발견해서 교체했습니다."

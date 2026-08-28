# 규칙 엔진 설계 — `app/services/chemistry/engine.py`

- 담당: 백엔드 (규칙 엔진만)
- 기준: `new_spec/SPEC_V4.2.md`, `ai/schemas.py`, `app/services/scoring/scorer.py`
- 이 문서를 Kiro에 먹여 `engine.py` + `knowledge_base/*.yaml` 스키마를 리파인한다.

이 엔진은 **결정론적**이다. LLM·LangChain·LangGraph를 import하지 않는다. 동일한 `CanonicalProfile` 집합은 항상 동일한 등급·코드·rule_id를 낸다.

---

## 0. 범위

| 포함 | 제외 (다른 담당) |
| --- | --- |
| `CanonicalProfile[]` → 팀/페어/개인 **코드** payload | 규칙 **내용** 25개 작성 (`knowledge_base/*.yaml`의 when/produces) |
| `team_index` 성분·공식·등급 컷오프 | AI 그래프 (`ai/graphs`, `ai/nodes`) |
| 페어 top-3 랭킹, 중립 처리, 결정성 | API 라우팅·인증·DB (`app/api`, `app/auth`) |
| YAML `when` 술어 평가기 | 채점 (`scorer.py` — 이미 완료) |

**현재 `engine.py`는 동작하는 스켈레톤이다.** 아래 §5·§7·§11이 교체·수정 대상이고 나머지 구조는 유지한다.

---

## 1. 고정 계약 — Kiro는 이 타입들을 바꾸지 않는다

`ai/schemas.py`에서 온다. 엔진은 이걸 **소비·생산**만 한다.

### 입력: `CanonicalProfile`

```
participant_id: str
source: "SURVEY" | "DECLARED_TYPE"
question_set_version: str | None            # "survey24-v2" | None
positions: AxisPositions                     # 아래
ratios:  dict[str,float] | None              # SURVEY만. 엔진은 등급 계산에 쓰지 않는다 (§9)
means:   dict[str,float] | None              # SURVEY만. 엔진은 쓰지 않는다
axis_flags: list[str]                        # 예: ["INCONSISTENT_AXIS_RESPONSE:planning"]
```

### `AxisPositions` (4축, dict 호환)

| 축 키 | 상위 극 (`upper`) | 하위 극 (`lower`) | 중립 |
| --- | --- | --- | --- |
| `planning` | `PLANNER` | `ADAPTER` | `NEUTRAL` |
| `agency` | `DRIVER` | `SUPPORTER` | `NEUTRAL` |
| `conflict` | `CONFRONTER` | `HARMONIZER` | `NEUTRAL` |
| `communication` | `DIRECT` | `TACTFUL` | `NEUTRAL` |

축 순서 상수: `AXIS_KEYS = ("planning","agency","conflict","communication")`. `POSITION_ENUM[axis] = (upper, lower)`.

### 출력: AI 입력 DTO (엔진이 채워서 넘김)

```
TeamCommentInput:
  analysis_result_id, audience="TEAM",
  team_grade: "HIGH" | "MID" | "LOW",
  strength_codes: list[str], caution_codes: list[str],
  recommendation_codes: list[str],          # 팀은 [] (팀 코멘트는 실행행동 없음)
  matched_rule_ids: list[str],
  evidence_levels: dict[code -> "direct"|"indirect"|"limited"|"team_judgment"],
  team_size: int(3..10),
  distribution: TeamDistribution | None

PrivateInsightInput:                          # 참여자 1명당 1개
  analysis_result_id, audience="SELF_ONLY",
  participant_id,
  self_positions: AxisPositions,
  team_aggregate: TeamDistribution,
  strength_codes, caution_codes, recommendation_codes,
  matched_rule_ids
```

`TeamDistribution` = 축별 `dict[POLE|NEUTRAL -> count>=0]`.

### 규칙 엔진 → 그래프 allow-list

`CommentGraphState`의 `allowed_strength_codes / allowed_caution_codes / allowed_recommendation_codes / allowed_rule_ids`는 **각 코멘트 대상의 코드 payload 그 자체**다. 팀 그래프는 `TeamCommentInput`의 코드들, 개인 그래프는 그 참여자 `PrivateInsightInput`의 코드들. 엔진이 allow-list의 유일한 출처다.

---

## 2. 입력 정규화 + 결정성

1. `run_team_analysis(profiles)` **진입 즉시 `profiles`를 `participant_id` 오름차순 정렬**한다. 호출자 순서와 무관하게 결과가 같아야 한다.
2. 페어는 `itertools.combinations(sorted_profiles, 2)` — 순서 보존.
3. 규칙 iteration은 YAML 파일 순서. 코드 dedup은 `list(dict.fromkeys(...))` (삽입 순서 보존).
4. 부동소수 결과는 `round(x, 4)`.
5. 랜덤·시각·해시 순서 의존 금지.

**인수 기준:** `run_team_analysis(profiles)` == `run_team_analysis(shuffle(profiles))` (완전 일치).

---

## 3. Fact 모델 — 규칙 평가 전에 계산

### `TeamFacts`

```
distribution[axis] = {upper: n, lower: n, NEUTRAL: n}
decided(axis)      = upper + lower                       # 중립 제외
upper_ratio(axis)  = upper / decided   (decided==0 → 0.5)
major_ratio(axis)  = max(upper,lower) / decided  (decided==0 → 0.5)
dominant_pole(axis):                                     # ★ majority 재정의 (§7)
    decided==0                       → None
    upper > lower                    → upper
    lower > upper                    → lower
    upper == lower (동수)            → None
has_both(axis)     = upper>=1 and lower>=1
all_decided_upper(axis) = decided>=1 and lower==0
all_decided_lower(axis) = decided>=1 and upper==0
neutral_ratio(axis)= NEUTRAL / team_size
```

### `PairFacts` (각 페어)

```
pos_a[axis], pos_b[axis]
same(axis)   = pos_a==pos_b != NEUTRAL
differ(axis)  = pos_a!=pos_b and pos_a!=NEUTRAL and pos_b!=NEUTRAL
both(axis, POLE) = pos_a==POLE and pos_b==POLE
```
한쪽이라도 `NEUTRAL`인 축은 그 페어-축 규칙 평가에서 제외.

### `SelfFacts` (각 참여자)

```
self.positions            # AxisPositions
team = TeamFacts 참조       # self vs team 규칙용
```

---

## 4. `compute_team_index` — **스켈레톤 내부를 아래로 교체**

현재 스켈레톤의 `balance/complement/task_fit/conflict_risk`는 페어 규칙 개수에 의존해서 **규칙 내용이 바뀌면 등급이 흔들린다**. 아래는 `分포만의 순수 함수` (검증된 TS 55 테스트에서 포팅). 시그니처를 `compute_team_index(distribution, profiles)`로 바꾸고 `pair_results` 파라미터 제거.

```text
상수:
  P_TARGET = 0.65
  W = { balance: 0.30, complement: 0.30, task_fit: 0.25, conflict_inv: 0.15 }
  TASKFIT_UPPER_TARGET = {planning: 0.65, agency: 0.50, conflict: 0.35, communication: 0.50}
  COMPLEMENT_AXES = [agency, planning, communication]     # conflict 제외
  HARD_AXES       = [conflict, communication]             # 극단 편중 위험 체크 축
  HARD_POLE       = {conflict: CONFRONTER, communication: DIRECT}
  clamp(x) = min(1, max(0, x));  mean([]) = 0

balance:
  bal_axes = [axis for axis in AXIS_KEYS if decided(axis) > 0]
  balance  = mean( clamp(1 - abs(major_ratio(axis) - P_TARGET)) for axis in bal_axes )
             (bal_axes 비면 0.5)

complement:
  complement = mean( 1.0 if has_both(axis) else 0.5  for axis in COMPLEMENT_AXES )

task_fit:
  task_fit = clamp( 1 - mean( abs(upper_ratio(axis) - TASKFIT_UPPER_TARGET[axis]) for axis in AXIS_KEYS ) )

conflict_risk:
  per axis in HARD_AXES:
      d = decided(axis)
      if d == 0: 0
      else: clamp( ( count(HARD_POLE[axis]) / d - 0.8 ) / 0.2 )     # 80% 초과 쏠림부터 선형
  conflict_risk = clamp( mean(위 값들) )

team_index = clamp( 0.30*balance + 0.30*complement + 0.25*task_fit + 0.15*(1 - conflict_risk) )
```

> `+ 0.15*(1 - conflict_risk)`는 대수적으로 `기존 - 0.15*conflict_risk` **+ 상수 0.15**다. 따라서 등급 컷오프도 0.15 올린다 (§6). 상대 순서·테스트 결과는 기존과 동일.

`count(POLE)` = 그 축에서 해당 극인 참여자 수. `distribution[axis][POLE]`.

---

## 5. 등급 컷오프 — `team_rules.yaml`

```yaml
grade_thresholds:
  HIGH: 0.90    # team_index >= 0.90
  MID:  0.70    # 0.70 <= team_index < 0.90
  # LOW: < 0.70
```

스켈레톤의 `{HIGH: 0.65, MID: 0.40}`은 잘못된 성분 기준값이므로 위로 교체. 이 값은 §4 공식 + §12 예시 팀으로 검증한다. 규칙 불변식:

- 전원 동일 포지션 팀 → `LOW`
- 균형 잡힌 보완 팀 → `HIGH`
- 위 두 팀 사이 → `MID`

`determine_grade`는 `internal_index`만 받는 순수 함수. `team_rules.yaml`의 `grade_thresholds`를 읽되 기본값을 `{HIGH: 0.90, MID: 0.70}`로.

---

## 6. YAML 규칙 평가

### 6.1 팀 규칙 (`team_rules.yaml`, scope: team)

```yaml
- rule_id: TEAM_BALANCED_AGENCY
  scope: team
  category: strength | caution
  when:
    axis: agency
    condition: <아래 목록>
  produces:
    strength_code | caution_code: <CODE>
    description: "..."          # 사람용 메모, AI엔 안 감
  evidence_level: direct | indirect | limited | team_judgment
```

`condition` 어휘 (**중립 제외 = decided 기준**):

| condition | 참 조건 |
| --- | --- |
| `balanced` | `has_both(axis)` |
| `majority_upper` | `dominant_pole(axis) == upper` |
| `majority_lower` | `dominant_pole(axis) == lower` |
| `all_upper` | `all_decided_upper(axis)` |
| `all_lower` | `all_decided_lower(axis)` |
| `has_upper` | `distribution[axis][upper] >= 1` |
| `has_lower` | `distribution[axis][lower] >= 1` |
| `no_upper` | `distribution[axis][upper] == 0` |
| `no_lower` | `distribution[axis][lower] == 0` |

매칭 시 `produces`의 코드를 `team_strength_codes` / `team_caution_codes`에, `rule_id`를 `matched_rule_ids`에, `evidence_levels[code] = rule.evidence_level`.

> 다축 복합 팀 규칙이 필요하면 `when`을 `conditions: [{axis, condition}, ...]` (AND) 리스트로 확장. MVP 현재 규칙은 전부 단일 축이므로 스켈레톤 유지.

### 6.2 페어 규칙 (`pair_rules.yaml`, scope: pair)

```yaml
- rule_id: AGENCY_COMPLEMENT
  scope: pair
  category: complement | friction | alignment
  when:
    axis: agency
    positions: [DRIVER, SUPPORTER]     # 같은 극 2개면 [DRIVER, DRIVER]
  produces:
    strength_code | caution_code: <CODE>
  evidence_level: ...
  priority: 1                          # 낮을수록 우선 (§8)
```

매칭 (해당 축 둘 다 non-NEUTRAL 일 때만):

- `positions` 원소 1종 (`[DRIVER, DRIVER]`) → `pos_a == pos_b == that`
- `positions` 원소 2종 (`[DRIVER, SUPPORTER]`) → `{pos_a, pos_b} == set(positions)`

결과: `PairResult(a_id, b_id, category, rule_id, code, axis, priority)`.
`PairResult` dataclass에 **`priority: int` 필드 추가**, `match_pair_rules`에서 `rule.get("priority", 50)`로 채움.

### 6.3 개인 규칙 (`private_insight_rules.yaml`, scope: private, audience: SELF_ONLY)

```yaml
- rule_id: PERSONAL_DIRECT_IN_TACTFUL_TEAM
  scope: private
  category: strength | caution
  when:
    self.communication: DIRECT
    team.communication.majority: TACTFUL     # → dominant_pole(communication) == TACTFUL
  produces:
    strength_code | caution_code: <CODE>
    recommendation_code: <CODE>              # caution일 때
  audience: SELF_ONLY
```

`when` 키 (모두 AND):

| 키 형태 | 평가 |
| --- | --- |
| `self.<axis>: <POLE>` | `self.positions[axis] == POLE` |
| `team.<axis>.majority: <POLE>` | `dominant_pole(axis) == POLE`  (**§3 재정의 사용**) |
| `team.<axis>.has: <POLE>` | `distribution[axis][POLE] >= 1` |
| `team.<axis>.neutral_ratio_gt: <float>` | `neutral_ratio(axis) > float` |

매칭 시 참여자의 `strength_codes / caution_codes / recommendation_codes / matched_rule_ids`에 append. `recommendations.yaml`에서 `recommendation_code` → text/detail 조회는 **AI 그래프 몫** (엔진은 코드만).

---

## 7. 페어 top-3 랭킹 — `run_team_analysis` step 5 교체

```
complement_pairs = [pr for pr in pair_results if pr.category == "complement"]
caution_pairs    = [pr for pr in pair_results if pr.category in ("friction", "alignment")]

sort key = (pr.priority, pr.rule_id, pr.participant_a_id, pr.participant_b_id)   # 전부 결정론적
top_complement_pairs = sorted(complement_pairs, key=...)[:3]
top_caution_pairs    = sorted(caution_pairs,    key=...)[:3]
```

내부 `pair_results`는 `n*(n-1)/2` 전부 유지 (인수 기준). 화면엔 top 3+3만.

---

## 8. 중립(NEUTRAL) 처리 — 한 곳에 모음

| 위치 | 규칙 |
| --- | --- |
| `team_index` 성분 | `decided` = 중립 제외. 전 축 중립이면 `balance=0.5` |
| 팀 규칙 `condition` | `majority_*` / `all_*` 는 decided 기준. `has_*` / `no_*` 는 전체 카운트 |
| 페어 규칙 | 그 축이 한쪽이라도 NEUTRAL → 그 페어-축 규칙 스킵 |
| 개인 규칙 `self.<axis>` | `NEUTRAL == POLE` 은 항상 거짓 → 규칙 안 탐 |
| `dominant_pole` | 동수(upper==lower)면 `None` → majority 규칙 안 탐 |

---

## 9. 공정성 — `ratios` / `means` 미사용

`source == "DECLARED_TYPE"` 참여자는 `ratios=None`. **엔진은 등급·코드 계산에서 `ratios`/`means`를 절대 쓰지 않는다.** 동일 `positions` → 입력 방식 무관하게 동일 결과 (SPEC §3.5, 인수 기준).

`ratios` 기반 "설명 강도 조절"은 MVP 제외. 강도 신호는 규칙별 `evidence_level` 하나뿐.

`axis_flags`(비일관 응답)는 `scorer.py`가 이미 `CanonicalProfile`에 담음. 엔진은 **게이트하지 않고**, MVP에서는 AI로도 넘기지 않는다 (`PrivateInsightInput`에 필드 없음). 저장만.

---

## 10. `internal_index` 유출 금지

`TeamAnalysisResult.internal_index`는 엔진 내부 + 튜닝 로그용. **어떤 HTTP 응답(`/results/team`, `/results/pairs`, 공유, 내보내기)에도 넣지 않는다** (SPEC §7.4). `build_team_comment_input`은 이미 미포함 — 유지.

---

## 11. 반드시 고칠 것 (스켈레톤 버그)

1. **`compute_team_index`** — §4로 내부 교체. `pair_results` 파라미터 제거. (지금은 규칙 개수에 등급이 종속됨)
2. **`grade_thresholds`** — `team_rules.yaml`을 `{HIGH: 0.90, MID: 0.70}`으로. (`0.65/0.40`은 근거 없음)
3. **`_get_majority`** — `counts[upper] > total/2` (전체 대비) → `dominant_pole` (decided 대비, 반대 극보다 많음). 지금은 4인 팀에 중립 1명만 있어도 개인 caution 규칙이 거의 안 탐 → **private 기능 전체가 죽음**.
4. **`match_pair_rules`** — `PairResult`에 `priority` 추가, `rule` 에서 읽기.
5. **`run_team_analysis` step 5** — `key=lambda x: x.rule_id` (알파벳순) → §7 `priority` 우선 정렬.
6. **`run_team_analysis` 진입** — `profiles.sort(key=participant_id)` 추가 (결정성).
7. **팀 `condition` 평가** — `all_upper`/`majority_*`를 decided 기준으로 (§6.1 표). 지금은 `== total`이라 중립 있으면 안 맞음.
8. **개인 규칙 `team.*` 파서** — `team.{axis}.majority` 외 `.has` / `.neutral_ratio_gt` 도 지원 (§6.3).

---

## 12. 인수 기준 (`evals/` + `pytest`)

### 결정성 / 공정성

- `run_team_analysis(P)` == `run_team_analysis(shuffle(P))`
- 설문 4명 vs 직접입력 4명 (동일 positions) → `team_grade`, `team_strength_codes`, `team_caution_codes`, 각 `PrivateAnalysisResult` 완전 일치
- `ratios`를 다르게 줘도 (positions 동일) 결과 불변

### 페어 개수

- 3명 → 3, 4명 → 6, 10명 → 45 (`len(pair_results)`)
- `top_complement_pairs`, `top_caution_pairs` 각 ≤ 3

### 등급 불변식 (예시 팀 — `team_index` 컷오프 튜닝용 fixture)

| 팀 | positions | 기대 |
| --- | --- | --- |
| T1 전원동일 | 4명 모두 `PLANNER/DRIVER/CONFRONTER/DIRECT` | `LOW`, `conflict_risk > 0` |
| T2 균형보완 | `P/L/H/D`, `P/S/H/I`, `A/L/H/D`, `A/S/C/I` (풀네임 매핑) | `HIGH`, `conflict_risk == 0` |
| T3 밋밋 | 전 축 2:2 이면서 conflict/comm 강성 없음 | `MID` |
| T4 중립다수 | 3명이 모든 축 `NEUTRAL`, 1명만 뚜렷 | `MID` 근처, 규칙 거의 안 탐, 에러 없음 |
| T5 리더과다 | agency 전원 `DRIVER` | `LOW_DRIVER_ENERGY` 안 뜨고 `DRIVER_COLLISION` 페어 다수, top_caution에 노출 |

`team.ts` 55 테스트 케이스를 그대로 포팅해 대조 (`lib/analysis/*.test.ts`).

### 개인 규칙 (private)

- `self.communication=DIRECT` + 팀 communication `dominant_pole == TACTFUL` → `PERSONAL_DIRECT_IN_TACTFUL_TEAM` 매칭, `caution_code=CHECK_FEEDBACK_TONE`, `recommendation_code=FACT_IMPACT_REQUEST`
- 팀에 중립 1명 있어도 위가 여전히 매칭 (버그 #3 회귀 테스트)
- `dominant_pole`가 동수면 majority 규칙 안 탐

### 유출

- `TeamAnalysisResult`를 dict로 직렬화 시 `internal_index` 키 존재 여부는 API 레이어 책임 — 엔진 테스트에서는 `build_team_comment_input` 출력에 `internal_index` 없음만 확인

---

## 13. 파일 맵

```
app/services/chemistry/
  engine.py         ← 이 문서 대상. §11 고침 + §4 교체
  DESIGN.md         ← 이 문서
knowledge_base/
  team_rules.yaml           ← grade_thresholds 수정(§5). rules 내용은 다른 담당
  pair_rules.yaml           ← priority 필드 스키마 확정(§6.2)
  private_insight_rules.yaml← when 어휘 확장(§6.3)
  recommendations.yaml      ← 코드↔행동 매핑. AI가 조회
  positions.yaml / evidence.yaml ← 참조 데이터, 변경 없음
```

의존 방향: `engine.py` → `ai/schemas.py` (타입만) + `pyyaml`. **`ai/graphs`·`ai/nodes`·`langchain*` import 금지.**

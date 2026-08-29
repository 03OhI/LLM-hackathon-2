# 퀘스트 카탈로그 V5.1 → V5.2 마이그레이션 노트

기준: `SPEC_V5_CONTEST_QUEST_AGENT.md` v5.2
검증: `python validate_quests.py quest.schema.json quests.json patterns.enum.json` → 오류 0건 / 경고 0건

---

## 0. 현재 상태 — 안정본 고정 (읽는 순서 여기부터)

카탈로그 29개 중 **9개만 `is_active: true`**다. 나머지 20개는 제작 완료 후 대기 상태다.

| 구분 | 개수 | quest_id |
| --- | --- | --- |
| **통합·시연 안정본** | 9 | `Q_CSB_001` `Q_WSD_001` `Q_COM_001` `Q_COM_002` `Q_TSF_001` `Q_TSF_002` `Q_TID_001` `Q_SAR_001` `Q_SAR_002` |
| 대기 — 16유형 질문 | 16 | `Q_CSB_010` ~ `Q_CSB_025` |
| 대기 — 추가 협업 퀘스트 | 4 | `Q_TSF_003` SOS · `Q_TSF_004` 컨디션 게이지 · `Q_TSF_005` 데스 룰 · `Q_TID_002` 노동요 |

대기 퀘스트는 스키마·안전성 검증을 이미 통과했고 `is_active`만 `false`다. E2E 통합이 끝난 뒤 배정 분포를 확인하며 하나씩 올리면 된다. 파일 구조나 계약 변경은 필요 없다.

**런타임 계약 (고정)**

1. 백엔드·AI는 `quests.json`만 읽는다. `topics.json`은 제작·검수 전용.
2. 배정: `matched_rule_ids` → `best_for`/`also_for` 매칭 → 상위 3개 Bedrock → 팀 공용 퀘스트 1개.
3. 카드 선택·개인 유형 선택·상위/하위 그룹 선택 기능 없음. 개인 유형과 NEUTRAL은 배정 입력이 아니다.
4. 질문 A/B는 `materials`에 본문 그대로. 무엇을 할지는 팀이 고른다.
5. 완료는 `completion_condition.checks`로만 확인한다.
6. 사용자 노출 필드에 내부 유형 코드·명칭 금지. 검증기가 강제한다.

점수: `best_for` 일치 1건당 +3 / `also_for` +1 / `context_tags` +1 / `avoid_for` 일치 시 제외 / 인원·HIGH·MANUAL·비활성 제외 / `is_universal`은 경쟁 제외 후 폴백 전용.

---

## 1. 어휘 교체 (SPEC §13.1)

V5.1의 `TeamQuestProfile.patterns` 코드 체계를 폐기하고 `team_rules.yaml`의 기존 `rule_id` 14종을 그대로 쓴다.
`patterns.enum.json`은 이제 rule_id 어휘집이다. 파일명은 `rules.enum.json`이 정확하지만 커맨드라인 변경을 피하려 유지했다.

### 1.1 폐기 코드 → rule_id 매핑

| V5.1 잠정 코드 | V5.2 대체 | 비고 |
| --- | --- | --- |
| `PLANNING_MIXED` | `TEAM_PLANNING_STABILITY` / `TEAM_ADAPTABILITY` | 계획 성향이 갈린 상태를 직접 표현하는 rule이 없어 두 rule로 분해 |
| `AGENCY_MIXED` | `TEAM_BALANCED_AGENCY` | 1:1 대응 |
| `DRIVER_MAJORITY` | `TEAM_DRIVER_ENERGY` | 1:1 대응 |
| `DRIVER_BALANCED` | `TEAM_BALANCED_AGENCY` | `AGENCY_MIXED`와 동일 rule로 수렴 |
| `SUPPORTER_MAJORITY` | `TEAM_SUPPORTER_MAJORITY` | 1:1 대응 |
| `ADAPTER_MAJORITY` | `TEAM_ADAPTER_MAJORITY` | 1:1 대응 |
| `CONFLICT_MIXED` | `TEAM_BALANCED_CONFLICT` | 1:1 대응 |
| `CONFLICT_DIRECT_MAJORITY` | `TEAM_CONFRONTER_MAJORITY` | 1:1 대응 |
| `CONFLICT_AVOIDANT_MAJORITY` | `TEAM_HARMONIZER_PRESENCE` | 회피 다수 → 조율자 존재로 의미 이동 |
| `COMM_MIXED` | `TEAM_DIVERSE_COMMUNICATION` | 1:1 대응 |
| `COMM_DIRECT_SIMILAR` | `TEAM_DIRECT_CONCENTRATION` | 1:1 대응 |
| `COMM_INDIRECT_SIMILAR` | `TEAM_TACTFUL_COMMUNICATION` | 1:1 대응 |
| `COMM_ASYNC_MAJORITY` | `TEAM_TACTFUL_COMMUNICATION` | 동기/비동기 축이 rule에 없어 흡수 |
| `TEAM_LOW_RESPONSE` | `TEAM_LOW_DRIVER` | 1:1 대응 |
| `TEAM_ISOLATED_MEMBER` | `TEAM_LOW_DRIVER` / `TEAM_SUPPORTER_MAJORITY` | 고립 팀원을 직접 표현하는 rule 없음 |
| `TEAM_ALREADY_ALIGNED` | (대체 없음) | 모든 `avoid_for`에서 제거 |
| `TEAM_HIGH_VARIANCE` | (미사용) | — |

### 1.2 상황 태그 교체 (SPEC §3)

| V5.1 태그 | V5.2 대체 |
| --- | --- |
| `ONLINE_ONLY` | `REMOTE_TEAM` |
| `ASYNC_HEAVY` | `REMOTE_TEAM` |
| `TOOL_SETUP_NEEDED` | `WORKSPACE_NOT_READY` |
| `SHORT_DEADLINE` | `HACKATHON` |
| `NEW_MEMBER_JOINED` | (삭제) |
| `PARTS_MERGE_ONLY` | (삭제) |

미사용 태그: `IN_PERSON`. 현재 8개 퀘스트는 전부 온라인·혼합에서 돌아가 굳이 대면 전용으로 묶을 것이 없다.

---

## 2. 스키마 변경 (SPEC §4.1 완전 일치)

**제거된 필드 5종**

| 필드 | 제거 사유 | 잃은 것 |
| --- | --- | --- |
| `stage` | §4.1 모델에 없음 | 첫 배정 우선순위. `WORKSPACE_NOT_READY` 태그로 부분 대체 |
| `observed_dimensions` | `reveals_axes`로 병합 | 없음. 축 선언과 설명이 한 필드가 되어 불일치 자체가 불가능해짐 |
| `fit_note` | §4.1 모델에 없음 | 사용자용 적합 설명 한 줄. 프론트는 `summary`를 쓴다 |
| `duration_per_extra_member` | §4.1 모델에 없음 | 인원별 시간 보정. **3명 팀도 최대 인원 기준 시간을 보게 된다** |
| `avoid_context_tags` | §4.1 모델·§5.1 필터 모두에 없음 | 상황 기반 제외. 아래 3.2 참고 |

**추가된 필드 2종**: `is_active`(bool), `version`(semver 문자열). 둘 다 §4.1 모델에 있으나 기존 스키마에 없었다.

**변경**: `reveals_axes`가 `list[str]` → `list[dict]`. SPEC §4.1이 `list[dict]`로 적고 있어 `observed_dimensions`를 그대로 흡수했다. §4.3에 따라 배정 점수 계산에는 쓰지 않는다는 설명을 스키마에 명시했다.

**완화**: `is_universal`은 이제 단방향 제약이다. `is_universal == true → avoid_for == []`만 강제하고(SPEC §4.3), 역방향(`avoid_for`가 비면 반드시 universal)은 강제하지 않는다. 제외 조건이 없는 퀘스트와 폴백으로 쓸 퀘스트는 다른 판단이다.

---

## 3. 데이터 변경 (SPEC §4.5 보정)

| 퀘스트 | 조치 |
| --- | --- |
| Q_CSB_001 공통점 다섯 개 | 3~10명 유지, rule/context 재태깅 |
| Q_WSD_001 밸런스 게임 | rule_id 재태깅, `HACKATHON` 추가 |
| Q_COM_001 설명 전달 릴레이 | 설명자 회고 제출 유지(§4.5), 3~6명 유지 |
| Q_TSF_001 세이브포인트 | **해커톤 문구 반영** — "여러 주 일정이면 요일·시간대, 하루 일정이면 시간 단위"로 단계 수정, `HACKATHON` 태그 추가, 밤샘 금지 안전 문구 추가 |
| Q_TSF_002 그라운드 룰 | **`assignment: MANUAL`로 강등**(§4.5 "낮은 우선순위"). 자동 후보에서 빠지되 방장이 직접 고를 수는 있다 |
| Q_TID_001 팀 공식 리액션 | `is_universal: true` 유지, 6분으로 최단 → 폴백 정렬에서 항상 1위 |
| Q_SAR_001 가상 타임라인 | 22분으로 조정(10명 기준), `avoid_for: TEAM_PLANNING_OVERLOAD` |
| Q_SAR_002 워크스페이스 세팅 | **3~8 → 3~10명 확장**, 링크 확인 문구 단순화, `WORKSPACE_NOT_READY` 태그로 배정 시점 표현 |

`duration_minutes`는 전부 최대 인원 기준 단일값으로 재산정했다. 보정 계수가 사라졌으므로 3명 팀에도 같은 숫자가 표시된다.

---

## 4. 인수 기준 대조 (SPEC §10 카탈로그)

| 기준 | 결과 |
| --- | --- |
| 모든 퀘스트가 JSON Schema 통과 | ✅ 오류 0건 |
| 세 적합 필드가 실제 rule_id 또는 빈 배열 | ✅ `[VOCAB]` 검사, 14종 대조 |
| 자연어 적합 조건·미허용 context tag 차단 | ✅ 패턴 `^TEAM_[A-Z_]+$` + 어휘 대조 |
| 9~10명 자동 퀘스트 최소 4개 | ✅ 6개 |
| HIGH + AUTO 차단 | ✅ 스키마 `allOf` + `[DISCLOSURE]` 이중 검사 |
| 범용 퀘스트의 비어 있지 않은 `avoid_for` 차단 | ✅ 스키마 `allOf` + `[UNIVERSAL]` |
| (추가) 3~10명 전 구간 범용 폴백 존재 | ✅ Q_TID_001 (SPEC §5.2) |

---

## 5. 배정 점수식 확정 (백엔드 통합 후)

SPEC §5.1의 미정 사항이 백엔드 구현으로 확정됐다. 검증기도 여기에 맞췄다.

```text
best_for 일치      rule_id 1건당 +3   (per-match)
also_for 일치      rule_id 1건당 +1   (per-match)
context_tags 일치  태그 1건당   +1   (per-match)
같은 category 반복             -2
is_universal                 가산 없음   <- 제거됨
```

**범용 퀘스트는 점수 경쟁에서 완전히 빠진다.** `is_universal == true`인 퀘스트는 AUTO 후보 목록에 아예 들어가지 않고, 적합한 rule_id 후보가 없거나 Bedrock이 실패했을 때만 폴백으로 쓴다. 검증기의 `score()`가 `is_universal`이면 `None`을 반환하는 이유다.

또한 상황 태그만으로 점수가 붙은 퀘스트는 "rule 적합 후보"로 세지 않는다. `best_for`나 `also_for`에 해당 rule_id가 실제로 들어 있어야 후보다. 이 구분이 없으면 모든 퀘스트가 `FIRST_MEETING` 하나로 후보가 되어 폴백이 영원히 발동하지 않는다.

---

## 6. CONFLICT 축 퀘스트 추가

`TEAM_CONFRONTER_MAJORITY`에 맞는 AUTO 퀘스트가 없고 `VIRTUAL_TIMELINE` 계열에서는 `avoid_for`로 제외되던 문제를 해결하기 위해 `Q_COM_002`를 추가했다.

| 항목 | 값 |
| --- | --- |
| 제목 | 의견 갈릴 때 첫 문장 정하기 |
| category | `COMMUNICATION` (TEAM_SAFETY가 이미 2개라 category 중복 감점 -2를 피함) |
| 인원 / 시간 | 3~10명 / 8분 |
| interaction_mode | `HYBRID` (개인 선택 → 팀 합의). 스키마 enum에 신규 추가 |
| disclosure / assignment | `LOW` / `AUTO` |
| best_for | `TEAM_CONFRONTER_MAJORITY`, `TEAM_BALANCED_CONFLICT` |
| also_for | `TEAM_HARMONIZER_PRESENCE`, `TEAM_DIRECT_CONCENTRATION` |
| 완료 조건 | `VOTE PER_MEMBER 1` + `TEXT_SUBMIT TEAM 1` |

개인 경험 대신 가상 상황 카드(마감 이틀 전 기능 추가 vs 현상 마감)를 쓰고, 보기 네 개 중 하나를 고른 뒤 팀 공용 조율 문장 한 줄을 저장한다. 안전 문구로 실제 갈등·과거 팀 이야기 금지, 소수 선택자에게 이유 되묻기 금지, 선택 결과의 개인 성향 규정 금지를 명시했다.

`also_for`에 `TEAM_DIRECT_CONCENTRATION`을 넣어, `avoid_for`에만 등장하던 rule 하나가 자동 후보를 갖게 됐다.

---

## 7. 아이디어 반영 라운드 (퀘스트 6개 추가, 15개)

### 7.1 협동 퀘스트 아이디어 7건 판정

| 아이디어 | 판정 | 처리 |
| --- | --- | --- |
| 파티원 디버프 게이지 오픈 | **채택 (재설계)** | `Q_TSF_004` 파티 컨디션 게이지. 아래 7.2 참고 |
| 안전지대(세이프 존) 시간 | 중복 | `Q_TSF_001` 세이브포인트와 동일 |
| 초기 장비(툴) 튜토리얼 | 병합 | `Q_SAR_002`에 툴 투표 + 1분 시연 단계 추가. 특정 팀원 독박 방지 요소가 새로웠다 |
| 퀘스트 완료 공식 리액션 | 중복 | `Q_TID_001`과 동일 |
| 팀 공식 SOS 구조신호 | **채택** | `Q_TSF_003` 팀 구조신호 정하기 |
| 파티 공식 노동요 플리 | 보류 | 안전하고 재밌지만 배정 신호가 거의 없어 카탈로그만 늘린다. 원하면 1분이면 추가 |
| 최악의 팀플 썰 배틀 | **반려** | SPEC §4.4 "과거 팀원 비난을 요구하지 않는다" 정면 위반. 같은 산출물(하지 말 것 규칙)은 `Q_TSF_002` 그라운드 룰이 안전하게 달성한다 |

### 7.2 디버프 게이지에서 덜어낸 것

원안은 "전공 과제 3개 겹쳐서 체력 2", "어제 과음해서 지능 디버프"처럼 사유까지 공유하는 형태였다. 건강 상태·음주·수면은 민감정보이고 SPEC §4.4의 개인 경험 요구 금지에도 걸린다.

**1에서 5까지 숫자 하나만 받고 사유 칸을 두지 않는 형태로 바꿨다.** 분포만 익명으로 보여주고 개인 점수는 저장하지 않는다. 낮은 점수에 설명이나 만회를 요구하지 않고, 밤샘으로 여력을 메우는 방안을 제안하지 않는다는 안전 문구를 넣었다. 원안의 효과("무리한 일정 방지", "완벽한 모습을 보여야 한다는 압박 완화")는 그대로 남는다.

`best_for`에 `TEAM_PLANNING_OVERLOAD`를 걸었다. 계획은 잔뜩인데 실제 가용 여력을 모르는 팀에 맞는다는 판단이다. **[가정]** — 이 rule의 실제 발동 조건을 team_rules.yaml에서 확인하지 않았다. 아니면 이 한 줄만 빼면 된다.

### 7.3 16유형 질문 카드 → 유형 퀘스트 16개 + topics.json

> **최종 결정: 유형당 퀘스트 1개.** 아래 그룹 4개 안은 중간 단계였고, "다 넣어달라"는 결정에 따라 16개로 펼쳤다. `topics.json`의 `types[].quest_id`가 유형과 퀘스트를 1:1로 잇는다. `groups`·`sub_groups`는 축과 rule_id를 설명하는 계층 정보로 남는다.
>
> 각 유형 퀘스트의 `best_for`는 하위 2 + 상위 2 = 최대 4개 rule_id를 전부 싣는다. 그 결과 `best_for` 커버리지가 **14/14**가 됐다. 비용은 아래 8.2에 적었다.

> **런타임 계약 (백엔드 확인 반영): 신규 기능 없음.**
>
> - 백엔드는 **`quests.json`만 읽는다.** `topics.json`은 카탈로그 제작·검수용 참조 파일이며 런타임에 로드하지 않는다.
> - 배정 흐름은 기존 그대로다. `rule_id` → `best_for` 매칭 → 팀 공용 퀘스트 1개.
> - **카드 선택 API도, 개인별 유형 노출도 없다.** 유형은 질문을 묶는 제작상의 축일 뿐 배정 입력이 아니다. 따라서 개인 유형 판정 로직이나 NEUTRAL 처리도 백엔드에 필요 없다.
> - 질문 2개는 각 퀘스트의 `materials`에 본문 그대로 들어가 있고, "둘 중 하나를 팀이 골라 시작한다"는 `steps`의 진행 안내다. 서버가 고르는 동작이 아니다.
> - 완료 조건은 유형 퀘스트 16개 전부 `TEXT_SUBMIT / PER_MEMBER / 1` 하나뿐이다. 질문 A·B 중 무엇을 골랐는지는 완료 판정에 들어가지 않는다.
> - 검증기가 이 계약을 강제한다. `types[].topics`의 두 문장이 연결된 퀘스트 `materials`에 **본문 그대로** 있어야 하고, 퀘스트 본문이 `topics.json`을 문자열로 참조하면 오류다.
>
> 이전 초안에 있던 "시스템이 카드를 꺼냅니다" 문구가 신규 기능처럼 읽혔던 부분은 전부 걷어냈다.

> **내부 제작 개념은 사용자 화면에 나오지 않는다.**
>
> 유형 코드(`PLCD`)와 명칭(`선봉 설계자`, `판 짜는 형`, `직진 지적형`)은 `topics.json`에만 있다. 퀘스트의 `title`·`summary`·`primary_goal`·`materials`·`steps`·`deliverable` 어디에도 넣지 않는다.
>
> - `materials`에 있던 `"겨냥하는 결: ..."` 메모를 16개 전부에서 제거했다. 남은 것은 질문 A·B 두 줄뿐이다.
> - 제목도 유형 명칭 대신 **질문 주제**로 바꿨다. `선봉 설계자 질문 카드` → `초능력 밸런스 게임`. 원안 문서에 있던 질문 제목을 그대로 썼다.
> - `summary`도 같은 이유로 다시 썼다. `판 짜는 형·직진 지적형 결이 있는 팀에...` → `통제와 효율을 두고 고르는 가정 질문 하나에 전원이 한 줄씩 답합니다.`
> - 검증기가 유형 코드·명칭·상위/하위 그룹 라벨이 사용자 노출 필드에 나타나면 오류로 잡는다. 되돌아오면 바로 걸린다.

16유형(PLCD~ASHI)은 기존 4축과 정확히 맞물린다. `P/A`=planning, `L/S`=agency, `C/H`=conflict, `D/I`=communication.

문제는 **4축 조합 하나를 지목하는 rule_id가 없다는 것**이다. 기존 14종은 대부분 팀 분포 기반이고, "PLCD인 팀원이 한 명 있으면"은 표현할 수 없다. 그래서 계획 축 × 주도 축까지만 쓰는 **성향 그룹 4개**로 묶었다.

| 그룹 | 퀘스트 | best_for |
| --- | --- | --- |
| PL 판 짜는 형 | `Q_CSB_002` | `TEAM_PLANNING_STABILITY`, `TEAM_DRIVER_ENERGY` |
| PS 길 닦는 형 | `Q_CSB_003` | `TEAM_SUPPORTER_MAJORITY`, `TEAM_TACTFUL_COMMUNICATION` |
| AL 먼저 뛰는 형 | `Q_CSB_004` | `TEAM_DRIVER_ENERGY`, `TEAM_ADAPTABILITY` |
| AS 바로 붙는 형 | `Q_CSB_005` | `TEAM_ADAPTER_MAJORITY`, `TEAM_ADAPTABILITY` |

질문 32개는 `topics.json`에 유형별로 분리했다. 퀘스트가 열리면 그 안에서 해당 팀원의 세부 유형에 맞는 질문 한 장을 꺼낸다. 퀘스트는 팀 단위로 뜨고, 질문만 유형별로 갈린다.

**하위 체계(CD/CI/HD/HI)도 rule_id를 갖는다.** 처음에는 상위 2축(planning × agency)만 쓰고 하위 2축(conflict × communication)을 버렸는데, 그 탓에 `TEAM_DIRECT_CONCENTRATION`이 어디에도 걸리지 않았다. `topics.json`에 `sub_groups`를 추가해 하위 4종에도 축과 rule_id를 명시했다.

| 하위 | 이름 | 축 | rule_ids |
| --- | --- | --- | --- |
| CD | 직진 지적형 | CONFRONTER × DIRECT | `TEAM_CONFRONTER_MAJORITY`, `TEAM_DIRECT_CONCENTRATION` |
| CI | 신중 설득형 | CONFRONTER × TACTFUL | `TEAM_BALANCED_CONFLICT`, `TEAM_TACTFUL_COMMUNICATION` |
| HD | 담백 실행형 | HARMONIZER × DIRECT | `TEAM_HARMONIZER_PRESENCE`, `TEAM_DIRECT_CONCENTRATION` |
| HI | 분위기 조율형 | HARMONIZER × TACTFUL | `TEAM_HARMONIZER_PRESENCE`, `TEAM_TACTFUL_COMMUNICATION` |

상위 그룹 하나는 하위 4종을 전부 포함하므로, 하위 rule_id를 그룹 퀘스트의 `best_for`에 올릴 수는 없다(어느 하위가 걸릴지 배정 시점에야 정해진다). 대신 **카드를 꺼낼 때 쓴다** — 팀원의 하위 축까지 맞춰 4장 중 한 장을 고른다. 퀘스트 태깅은 상위 2축, 카드 선택은 하위 2축이라는 2단 구조다.

**NEUTRAL 처리가 필요하다.** SPEC §2.1은 축별 `NEUTRAL`(비율 0.40~0.60)을 허용하므로, 4축 모두 극값인 팀원만 16유형에 들어간다. 중립이 하나라도 있으면 유형 미부여다. 실제 설문에서 흔한 구간이라 **전원이 유형 미부여인 팀이 나올 수 있다.** `topics.json`의 `_neutral_policy`에 "유형이 확정된 팀원이 한 명이라도 있을 때만 그룹 퀘스트를 연다"로 적어뒀고, 배정 코드도 같은 조건을 걸어야 한다.

안전장치로 세 퀘스트 모두 "카드가 열린 이유로 특정 팀원의 유형 코드를 화면에 표시하거나 지목하지 않습니다"를 넣었다. SPEC §9의 개인 카드 비공개 원칙과 충돌하지 않게 하기 위해서다.

### 7.4 검증기 확장

`topics.json`이 `quests.json` 옆에 있으면 자동으로 함께 검증한다.

- 16유형 전부 존재 / 정의되지 않은 코드 없음, 하위 4종 전부 존재
- 유형 코드 앞 두 글자와 `group`, 뒤 두 글자와 `sub_group` 일치
- 상위·하위 그룹의 **코드 글자와 `axes` 선언 일치** (예: `AL`의 `A`는 반드시 `planning: ADAPTER`)
- `groups`·`sub_groups`의 `rule_ids`가 실제 team_rules.yaml rule_id인지
- 유형당 질문 정확히 2개, 중복 없음, 10자 이상
- `groups[].quest_id`가 실제 존재하고 자동 후보인지
- `topics.json`을 참조하는 퀘스트가 `groups`에 등록됐는지

의도적으로 깨뜨려 두 차례 확인했다. 1차 5건 주입 → 6건 검출, 2차 하위 체계 5건 주입 → 9건 검출(연쇄 오류 포함).

---

## 8. 남은 갭

### 8.1 rule_id 커버리지는 해결됨

유형 퀘스트 16개가 하위 축 rule을 `best_for`에 싣게 되면서 **`best_for` 커버리지 14/14, 범용 폴백으로 떨어지는 rule_id 0종**이 됐다. `TEAM_DIRECT_CONCENTRATION`은 CD·HD 계열 8개 퀘스트가 들고 있다.

### 8.2 카탈로그가 질문 카드로 기울었다 — 감수한 비용

29개 중 17개가 `CASUAL_BONDING`이고 그중 16개가 질문 카드다. 측정값:

| | 4그룹 안 (15개) | **현행 16유형 (29개)** |
| --- | --- | --- |
| 질문 카드 비중 | 4/15 (27%) | 16/29 (55%) |
| 14 rule × 3연속 배정 중 질문 카드 | 13/42 (31%) | **18/42 (43%)** |
| `best_for` 커버리지 | 13/14 | **14/14** |

**일치 개수 기반 점수와 겹치면 편중이 커진다.** 유형 퀘스트는 `best_for`에 rule_id를 4개 싣고 있어 최대 12점(+상황 태그 2점 = 14점)까지 오른다. 일반 퀘스트는 `best_for`가 2~3개라 상한이 9~11점이다. `matched_rule_ids` 개수별로 전 조합을 돌린 결과:

| matched_rule_ids | 조합 수 | 1위가 유형 퀘스트 |
| --- | --- | --- |
| 2개 | 91 | 52건 (57%) |
| 3개 | 364 | 242건 (66%) |
| 4개 | 1001 | 708건 (71%) |

매칭되는 rule이 많은 팀일수록 유형 퀘스트가 1위를 가져간다. 다만 rule이 특정 일반 퀘스트에 집중되면 뒤집힌다 — SPEC §3 샘플(`BALANCED_AGENCY` + `DIVERSE_COMMUNICATION` + `ADAPTABILITY`)에서는 `Q_WSD_001` 업무 스타일 밸런스 게임이 9점으로 1위, 유형 퀘스트는 5점으로 3위부터다.

3연속 배정의 43%가 질문 카드다. 팀 입장에서는 "질문에 한 줄 답하기"가 반복되고, 세이브포인트·그라운드 룰·워크스페이스 세팅 같은 실무 정렬 퀘스트가 뒤로 밀린다. 매칭 정확도(14/14)와 맞바꾼 값이며, 되돌리려면 다음 중 하나를 쓰면 된다.

- 배정 코드에서 유형 퀘스트를 팀당 1회로 제한한다 — 데이터 변경 없음, **가장 싸다**
- 유형 퀘스트의 `best_for`를 하위 2개로 줄이고 상위 2개를 `also_for`로 내린다 — 상한이 6+2=8점으로 떨어져 일반 퀘스트와 대등해진다. 데이터만 고치면 되고 검증기가 커버리지 변화를 바로 보여준다
- 유형 퀘스트를 별도 category(예: `TYPE_CARD`)로 분리해 `같은 category 반복 -2`가 카드끼리만 걸리게 한다 — 스키마 enum과 quest_id 접두사 추가 필요

### 8.3 fixture 전체 배정 분포 (`simulate_assignment.py`)

`python simulate_assignment.py quests.json patterns.enum.json topics.json`

fixture는 rule 조합 1~4개(같은 축 반대편끼리는 배타로 제외 **[가정]**) 634종 × 인원 3~10명 8종 × 상황 태그 3종 = **15,216건**. 정상 경로가 상위 3개를 Bedrock에 넘기므로 1위와 상위 3개 포함을 함께 집계한다. `Q_TSF_002`(그라운드 룰)는 MANUAL이라 자동 순위에서 제외된 것을 리포트 상단에 표시한다.

**요청한 다섯 가지**

| 항목 | 결과 |
| --- | --- |
| 퀘스트별 1위 횟수 | 아래 표 (최다 `Q_CSB_010` 1,664건) |
| 퀘스트별 상위 3개 포함 | 아래 표 (최다 `Q_CSB_010` 3,632건) |
| 맞춤 후보 0개 | **0건 (0.0%)** |
| 범용 폴백 배정 | **0건 (0.0%)** |
| 한 퀘스트가 1위의 40% 이상 | **아니오.** 최다가 `Q_CSB_010` 10.9% |

**집계 요약**

| 구분 | 1위 | 비율 |
| --- | --- | --- |
| 유형 질문 카드 16개 | 10,744 | 70.6% |
| 일반 퀘스트 12개 | 4,472 | 29.4% |
| 범용 폴백 | 0 | 0.0% |

개별 집중은 상한 안이지만 **카드 계열이 합쳐서 1위의 70.6%**를 가져간다. 의도한 동작이라면 그대로 두면 되고, 조정이 필요하면 8.2의 선택지 중 배정 코드에서 팀당 1회 제한이 데이터를 건드리지 않는다.

**주의해서 볼 두 퀘스트**

- `Q_COM_001` 설명 전달 릴레이 — 1위 8건(0.1%), 상위 3개 80건(0.5%). 인원이 3~6명으로 좁고 `best_for`가 `TEAM_DIVERSE_COMMUNICATION` 하나뿐이라 사실상 뜨지 않는다. 인원 상한을 올리거나 `best_for`를 보강하지 않으면 사문화된다.
- `Q_SAR_002` 공동 작업 공간 세팅 — 1위 8건(0.1%). 다만 이건 정상이다. 이 퀘스트는 `WORKSPACE_NOT_READY` 상황에 걸려 있고 협업 시작 직전에 쓰는 것이라, 아이스브레이킹 첫 배정을 재는 이 fixture에서 낮게 나오는 게 맞다.
- `Q_TID_001` 팀 공식 리액션 — 1위·상위 3개 모두 0건. `is_universal`이라 점수 경쟁에서 제외되는 설계대로다. 맞춤 후보 0개가 한 번도 없었으므로 폴백이 발동할 일도 없었다.

### 8.4 안정본 9개만 활성화한 상태의 분포

`python simulate_assignment.py quests.json patterns.enum.json topics.json`

합성 fixture 15,216건 기준. 대기 20개는 `is_active: false`라 자동 후보에서 빠진다.

| quest_id | 1위 | 1위% | 상위 3개 | 상위3% |
| --- | ---: | ---: | ---: | ---: |
| `Q_CSB_001` 공통점 다섯 개 | 4,128 | 27.1% | 8,860 | 58.2% |
| `Q_COM_002` 의견 갈릴 때 첫 문장 | 3,192 | 21.0% | 8,580 | 56.4% |
| `Q_WSD_001` 업무 스타일 밸런스 | 2,608 | 17.1% | 8,188 | 53.8% |
| `Q_TSF_001` 세이브포인트 | 2,328 | 15.3% | 6,940 | 45.6% |
| `Q_SAR_001` 가상 타임라인 | 2,016 | 13.2% | 6,684 | 43.9% |
| `Q_SAR_002` 워크스페이스 세팅 | 888 | 5.8% | 4,528 | 29.8% |
| `Q_COM_001` 설명 전달 릴레이 | 32 | 0.2% | 872 | 5.7% |
| `Q_TID_001` 팀 공식 리액션 (폴백) | 24 | 0.2% | 24 | 0.2% |

- **맞춤 후보 0개: 24건 (0.2%)** — 전부 `TEAM_PLANNING_OVERLOAD` 단독 매칭이다. 이 rule을 `best_for`로 가진 `Q_TSF_004` 컨디션 게이지가 대기 상태라 안정본에는 주인이 없다. 폴백으로 덮이므로 시연은 막히지 않는다.
- **범용 폴백 배정: 24건 (0.2%)** — 위와 같은 건이다.
- **한 퀘스트가 1위의 40% 이상: 아니오.** 최다는 `Q_CSB_001` 27.1%.
- `Q_COM_001`은 안정본에서도 0.2%다. 8.3에 적은 이유가 그대로다.

`Q_TSF_002` 그라운드 룰은 MANUAL이라 자동 순위에서 빠진 것을 리포트 상단에 표시한다.

### 8.5 fixture 정본은 실제 엔진이다

`simulate_assignment.py`가 `--fixtures` 를 받는다.

```bash
python simulate_assignment.py quests.json patterns.enum.json topics.json --fixtures fixtures.json
```

`fixtures.json`은 `QuestMatchContext`와 같은 모양의 배열이다.

```json
[{"team_size": 4,
  "matched_rule_ids": ["TEAM_BALANCED_AGENCY", "TEAM_ADAPTABILITY"],
  "context_tags": ["FIRST_MEETING", "HACKATHON"]}]
```

저장소에서는 `team_rules.yaml` + `match_team_rules()`로 fixture를 뽑아 넘긴다. `--fixtures` 없이 돌리면 스크립트 상단 `MUTUALLY_EXCLUSIVE` 표로 조합을 합성하는데, 이 표는 `team_rules.yaml`을 확인하지 못한 **[가정]**이라 정본이 아니다. 합성 모드로 돌면 리포트 상단에 경고가 찍힌다. 위 8.3·8.4 수치는 전부 합성 모드 결과이므로 실제 엔진 fixture로 다시 뽑아야 한다.

### 8.6 데스 룰은 사례 카드 방식으로 바꿔 넣었다

`Q_TSF_005`. 원안의 "최악의 조원 썰 풀기"는 SPEC §4.4의 과거 팀원 비난 금지에 걸려서, **흔한 사고 사례 5장 중 고르는 투표 방식**으로 바꿨다. 읽씹·잠수·전날 일정 파기·마감 직전 전면 수정·파트 떠넘기기 다섯 장이다. 규칙 두 개를 정한다는 산출물과 "서로 가장 싫어하는 행동을 확인한다"는 효과는 그대로 남고, 실명이나 실제 경험을 꺼낼 자리는 없앴다. 원안 그대로가 필요하면 사례 카드를 자유 서술로 바꾸면 되지만 §4.4 위반은 남는다.

### 8.3 SPEC 개정 제안

- **§4.1 `reveals_axes: list[dict]`의 dict 구조 미정의** — 현재 스키마는 `{axis, dimension, pole_a, pole_b}`로 확정했다. SPEC에 명시 필요.
- **§4.4 "인원 범위는 3~10명"의 의미 모호** — 제품 범위인지 퀘스트별 필수 범위인지. Q_COM_001은 3~6명이라 후자면 위반이다. 현재는 전자로 해석했다.
- **§2.2 "주의 코드는 퀘스트 에이전트에서 제외"** — `TEAM_PLANNING_OVERLOAD`, `TEAM_LOW_DRIVER` 등이 주의 코드에 해당하는지 불명확하다. §4.2 예시가 `avoid_for: ["TEAM_LOW_DRIVER"]`를 쓰고 있어 **사용 가능으로 해석했다.** 아니라면 `best_for`/`avoid_for`에서 5종을 빼야 하고, 7.1의 폴백 문제가 더 커진다.
- **§5.1 점수식** — `is_universal +1` 제거와 범용 퀘스트의 후보 제외를 SPEC 본문에 반영해야 한다. 현재 문서는 여전히 `is_universal +1`을 적고 있다.
- **§4.1 `interaction_mode`** — `HYBRID`를 enum에 추가해야 한다.

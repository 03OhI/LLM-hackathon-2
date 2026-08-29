# GitHub 공개 정리 — 올릴 것 / 뺄 것 / docs 구조

> 2026-08-28 · 실제 파일을 열어 확인한 결과입니다. 추정 아님.
> 커밋은 하지 않았습니다.

---

## 0. 먼저 — 스캔 결과

| 점검 | 결과 |
|---|---|
| 하드코딩된 AWS 키·토큰·비밀번호 | **없음** (`AKIA`, `secret_key`, `arn:aws`, 12자리 계정번호 전부 0건) |
| 응답 데이터의 실명 | **없음** — `R01`~`R22` 로 이미 익명화돼 있음 |
| 이메일·전화번호·아이디 | **없음** |
| `papers.py` 에 복사된 논문 초록 | **없음** (7편 전부 `abstract: None`) |
| `survey.html` 의 전송 엔드포인트 | **없음** — 정적 폼이라 유출 경로 없음 |

**보안 사고 위험은 없습니다.** 남은 판단은 개인정보 동의 하나입니다(§1-A).

---

## 1. 올리면 안 되는 것

### A. 🔴 판단이 필요한 것 — `responses*.jsonl`

`responses.jsonl` · `responses22.jsonl` (22명 24문항 응답)

익명화는 돼 있습니다. 그런데 **22명이 서로 아는 같은 집단**입니다. 이 규모에서는 몇 문항 답만 알면 누구인지 좁혀집니다. 그래서 기술적 익명화와 별개로 **동의를 받았는지**가 기준입니다.

> **[미확인] 설문할 때 "결과를 공개 저장소에 올린다"고 알렸습니까?**
>
> - 알렸다 → 올려도 됩니다.
> - 안 알렸다 → **빼세요.** 대신 집계값만 공개합니다. `ALPHA_RESULT.md` 의 표(α · MIC · 균형 합)는 개인을 복원할 수 없어 그대로 올려도 됩니다.

빼도 코드는 돕니다. `verify_fixes.py` ⑤ 와 `frictions.py` ② 는 파일이 없으면 건너뛰도록 이미 짜여 있습니다. README 에 한 줄만 적으면 됩니다 — "원자료는 응답자 보호를 위해 공개하지 않습니다. 집계 결과는 docs/ALPHA_RESULT.md."

**애매하면 빼세요.** 올린 걸 나중에 지워도 git 히스토리에 남습니다.

### B. 🔴 무조건 빼는 것

| 대상 | 이유 |
|---|---|
| `~$_확정_보고서.docx` · `~$ 흐름 정리.docx` | Word 락 파일. 내용 없는 쓰레기 |
| `__pycache__/` | 빌드 산물 |
| `설계_확정_보고서.docx` (구본) | `_최종` 만 남기고 지우세요. 두 개 다 올리면 어느 게 맞는지 아무도 모릅니다 |
| `cases_partial_split.py` | 붙여넣기용 임시 파일. 내용은 이미 `cases.py` 안에 들어갔습니다 |
| `resp23.xlsx` · `협업 스타일 설문 v2응답*.xlsx` | **RAG/ 밖에 있지만 실수로 넣지 마세요.** `타임스탬프` 열에 응답 시각이 초 단위로 있어 §1-A 보다 위험합니다 |

### C. 🟡 한 번 보고 결정할 것

**`upload_s3vectors.py`** — 자격증명은 없지만 버킷명 `team-chemistry-vectors` 와 리전 `ap-northeast-1` 이 그대로 있습니다. 대회에서 받은 계정이면 상수만 `os.environ.get("BUCKET", "...")` 로 빼는 걸 권합니다. 5분이면 됩니다. 위험은 낮습니다.

**`HANDOFF.md`** — 팀 내부 인수인계 문서입니다. "Word 닫고 압축하세요" 같은 문장이 공개 저장소에 있으면 어색합니다. `docs/` 에 넣되 §"⚠️ 보내기 전에 한 번" 문단은 지우세요.

---

## 2. 제안하는 구조

```
repo/
├─ README.md                  ← 진입점. 이것만 읽어도 파악되게 (§4 참고)
├─ requirements.txt
├─ .gitignore
│
├─ src/                       ← 돌아가는 코드
│   ├─ likert.py                 24문항 → 축 점수 · 역채점 · 묵종 지수
│   ├─ chemistry_v2.py           축 점수 · 등급 · 마찰 판정 (핵심)
│   ├─ faultline.py              갈라짐 진단 (Fau · breadth · ASW)
│   ├─ cases.py                  케이스 16건 문단 · 조치 · 논문 근거
│   ├─ papers.py                 논문 서지 인덱스
│   └─ survey.html               설문 폼
│
├─ evidence/                  ← 근거 파이프라인. 여기가 이 프로젝트의 차별점입니다
│   ├─ evidence_map.json         **논문 근거 정본**
│   ├─ mkmap.py                  정본 생성
│   ├─ sync_evidence.py          정본 → cases.py 자동 반영
│   ├─ frictions.py              마찰 규칙 추출 + 케이스 대조
│   └─ frictions.json            추출 결과 13종
│
├─ tests/
│   ├─ verify_fixes.py           **수용 테스트 17건. 여기부터 돌리게 하세요**
│   ├─ continuous_test.py
│   ├─ gate_counterexample.py
│   └─ space_test.py · space_test2.py
│
├─ analysis/                  ← 일회성 분석. 결론은 docs 에 있습니다
│   ├─ alpha_check.py            Cronbach's α · MIC
│   ├─ desirability_check.py     사회적 바람직성
│   ├─ reverse_factor_analysis.py
│   ├─ grade_sweep.py · decide.py · gimpact.py · split59.py
│   ├─ convert.py · make_jsonl.py · make_pair_matrix.py · trace.py
│   └─ pair_matrix.csv · cases.jsonl
│
├─ rejected/                  ← 구현하고 뺀 경로. 지우지 마세요 (§3)
│   ├─ vector_store.py · upload_s3vectors.py
│   ├─ test_vector_store.py · mock_s3_test.py
│   ├─ probe_retrieval.py · kure_bench.py · search_test.py
│   ├─ cosine_variant.py · voice_test.py
│   └─ chemistry.py              v1. v2 회귀 비교의 기준
│
└─ docs/                      ← §3
```

`src/` 로 옮기면 import 가 깨집니다. 옮기기 싫으면 **폴더를 나누지 말고 루트에 그대로 두고 `docs/` 만 만드세요.** 대회 일정에는 그게 안전합니다.

---

## 3. `docs/` 에 넣을 것

우선순위 순입니다. 위 5개가 이 프로젝트를 설명합니다.

| 파일 | 왜 여기 있는가 |
|---|---|
| **`설계_확정_보고서_최종.docx`** | 본 보고서 |
| **`DEFENSE.md`** | 판정 불가를 만점으로 주던 결함과 조치. **가장 강한 문서입니다** — 자기 코드의 결함을 스스로 찾아 고친 기록이라 |
| **`ALPHA_RESULT.md`** | 설문 신뢰도 측정 n=22. 결과가 나빴고 그걸 그대로 적었습니다 |
| **`FACTOR_ANALYSIS_SUMMARY.md`** | 시뮬레이션이 결론을 내장해 실패할 수 없는 테스트였다는 기록 |
| **`EVIDENCE_MAP.md`** | 케이스 16 ↔ 논문 8 대응표. 어느 것이 근거이고 어느 것이 팀 판단인지 갈라놨습니다 |
| `GRADE_V2.md` | 등급 규칙 (총점 경계 → 0.5 미만 축 개수) |
| `SCORE_DRIVE.md` | 주도성 인원수 집계 규칙 |
| `PARTIAL_SPLIT.md` | 59% 쏠림을 4개로 쪼갠 근거 |
| `SURVEY24.md` | 설문 24문항 설계 |
| `REVERSE_SCORING_ANALYSIS.md` | 역채점 설계와 한계 |
| `AXIS_GROUNDING.md` | 네 축의 학술 근거 |
| `TYPES16.md` | 16유형 정의 |
| `SCORING.md` · `COMBINATION_SPACE.md` · `PAIR_MATRIX.md` | 점수 체계 상세 |
| `ITEM_BIAS.md` | 문항 편향 점검 |
| `설문_학술근거_기준표.md` | 문항별 근거표 |
| `SPEC (1).md` | **이름 바꾸세요** → `SPEC.md`. 괄호와 공백이 든 파일명은 URL·스크립트에서 깨집니다 |
| `HANDOFF.md` | 인수인계 (§1-C 대로 손보고) |

### `docs/rejected/` 로 따로 묶을 것

미채택 경로의 기록입니다. **지우지 마세요.** 심사에서 "왜 RAG 를 안 썼나요"가 나왔을 때 답이 "안 해봤다"가 아니라 "구현하고 검증한 뒤 뺐다"가 되는 근거입니다.

`RETRIEVAL.md` · `COSINE_OPTION.md` · `VECTOR_UPLOAD.md` · `전체 흐름 정리.docx`

---

## 4. `.gitignore`

```gitignore
# 빌드 산물
__pycache__/
*.py[cod]
.venv/
venv/

# Office 락 파일 · 임시본
~$*
*.bak
*.bak[0-9]
*.log
*.tmp

# 🔴 응답 원자료 — 동의 확인 전까지 올리지 않는다 (docs/ALPHA_RESULT.md 에 집계값)
responses*.jsonl
*.xlsx

# 로컬 자격증명
.env
.aws/
```

`*.xlsx` 를 통째로 막아둔 것은 실수 방지용입니다. 올릴 xlsx 가 생기면 그때 예외를 넣으세요.

---

## 5. 올리기 전 README 손볼 곳 🔴

**README 가 저장소 첫 화면인데 지금 틀린 숫자가 있습니다.**

| 현재 | 고칠 것 |
|---|---|
| `팀 패턴 11 · 유형 카드 16 조회` | **케이스는 16건입니다.** 11 → 16 |

그리고 세 줄을 추가하시길 권합니다. 지금 README 에는 이 저장소가 뭘 검증했는지가 없습니다.

```markdown
## 검증 상태

python verify_fixes.py     # 수용 테스트 17건 — 17/17

- 마찰 13종 전부 케이스 문단에 연결 (미연결 0)
- 케이스 16건 중 논문 근거 8건 · 팀이 정한 규칙 8건 — `evidence_map.json` 에서 갈라 표시
- 설문 신뢰도는 미달입니다 (α .35~.56). 숨기지 않았고 원인과 처방은 docs/ALPHA_RESULT.md
```

마지막 줄이 중요합니다. **미달을 README 에 먼저 적는 저장소는 거의 없습니다.** 그게 이 프로젝트가 다른 팀과 구분되는 지점입니다.

---

## 6. 순서

1. Word 전부 닫기 → `설계_확정_보고서.docx` 지우고 `_최종` 을 그 이름으로 rename
2. `.gitignore` 먼저 만들기 (**`git init` 이나 `git add` 보다 먼저**. 한 번 커밋되면 히스토리에 남습니다)
3. `docs/` 만들고 §3 대로 옮기기
4. `SPEC (1).md` → `SPEC.md`
5. README 숫자 고치기 (§5)
6. §1-A 동의 여부 확인 → `responses*.jsonl` 결정
7. `git add` 전에 `git status` 로 **`__pycache__` 와 `~$` 파일이 안 잡히는지 눈으로 확인**

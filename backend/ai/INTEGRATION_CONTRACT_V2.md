# AI 모듈 통합 계약 V2

백엔드 담당자가 AI 모듈을 호출할 때 필요한 모든 정보.

---

## 1. 호출 함수

```python
from ai.chains.team_comment import generate_team_comment
from ai.chains.private_insight import generate_private_insight
from ai.schemas import TeamCommentInput, PrivateInsightInput, GenerationResult
from ai.nodes.fallback import build_team_fallback, build_private_fallback
```

### 팀 코멘트

```python
result: GenerationResult = generate_team_comment(input_data: TeamCommentInput)
```

### 개인 인사이트

```python
result: GenerationResult = generate_private_insight(input_data: PrivateInsightInput)
```

---

## 2. 입력 DTO

### TeamCommentInput (팀 — V2 단순화)

```json
{
  "analysis_result_id": "uuid-string",
  "strength_codes": ["INITIATIVE_SUPPORT_BALANCE", "CONFLICT_BALANCE"],
  "matched_rule_ids": ["TEAM_BALANCED_AGENCY", "TEAM_BALANCED_CONFLICT"],
  "team_size": 4,
  "distribution": {
    "planning": {"PLANNER": 2, "ADAPTER": 1, "NEUTRAL": 1},
    "agency": {"DRIVER": 1, "SUPPORTER": 2, "NEUTRAL": 1},
    "conflict": {"CONFRONTER": 1, "HARMONIZER": 2, "NEUTRAL": 1},
    "communication": {"DIRECT": 2, "TACTFUL": 1, "NEUTRAL": 1}
  }
}
```

**제거된 필드** (AI에 전달하지 않음):
- `team_grade` — 내부 전용
- `caution_codes` — 공개 결과에 부정적 코드 미포함
- `recommendation_codes` — 행동 지시 미생성
- `evidence_levels` — V2에서 미사용

**matched_rule_ids 필터 규칙**:
strength_code를 생성하는 규칙 중 해당 code가 실제 team_strength_codes에 포함된 것만.

### PrivateInsightInput (개인)

```json
{
  "analysis_result_id": "uuid-string",
  "participant_id": "participant-uuid",
  "self_positions": {
    "planning": "PLANNER",
    "agency": "DRIVER",
    "conflict": "CONFRONTER",
    "communication": "DIRECT"
  },
  "team_aggregate": {
    "planning": {"PLANNER": 2, "ADAPTER": 1, "NEUTRAL": 1},
    "agency": {"DRIVER": 1, "SUPPORTER": 2, "NEUTRAL": 1},
    "conflict": {"CONFRONTER": 1, "HARMONIZER": 2, "NEUTRAL": 1},
    "communication": {"DIRECT": 1, "TACTFUL": 2, "NEUTRAL": 1}
  },
  "strength_codes": ["PLANNING_STABILITY"],
  "caution_codes": ["CHECK_FEEDBACK_TONE"],
  "recommendation_codes": ["FACT_IMPACT_REQUEST"],
  "matched_rule_ids": ["PERSONAL_PLANNER_STABILITY", "PERSONAL_DIRECT_IN_TACTFUL_TEAM"]
}
```

---

## 3. 출력: GenerationResult

```python
class GenerationResult(BaseModel):
    audience: Literal["TEAM", "SELF_ONLY"]
    status: Literal["COMPLETED", "FALLBACK"]
    insight: TeamSnapshot | PrivateCard
    used_fallback: bool
    model_id: str
    prompt_version: str
    validation_errors: list[str]
```

### TeamSnapshot 정상 출력 예시

```json
{
  "audience": "TEAM",
  "status": "COMPLETED",
  "insight": {
    "title": "계획서는 꼼꼼한데 첫 커밋은 더 빠른 팀",
    "formula": "계획 2스푼 + 순발력 1스푼 + 솔직함 2방울",
    "scene": "회의가 끝나기 전에 누군가 브랜치를 만들고 있습니다.",
    "keywords": ["체계적", "빠른 실행", "솔직"],
    "used_rule_ids": ["TEAM_BALANCED_AGENCY"]
  },
  "used_fallback": false,
  "model_id": "global.anthropic.claude-sonnet-4-20250514-v1:0",
  "prompt_version": "team_snapshot_v2",
  "validation_errors": []
}
```

### PrivateCard 정상 출력 예시

```json
{
  "audience": "SELF_ONLY",
  "status": "COMPLETED",
  "insight": {
    "card_title": "이번 팀에서 꺼내볼 구조화 카드",
    "contribution": "팀에 체계와 방향을 가져다줄 수 있어요.",
    "optional_try": "큰 틀만 먼저 공유하고 디테일은 함께 채워봐도 좋아요.",
    "used_rule_ids": ["PERSONAL_PLANNER_STABILITY"]
  },
  "used_fallback": false,
  "model_id": "global.anthropic.claude-sonnet-4-20250514-v1:0",
  "prompt_version": "private_card_v2",
  "validation_errors": []
}
```

### TEAM 폴백 출력 예시

```json
{
  "audience": "TEAM",
  "status": "FALLBACK",
  "insight": {
    "title": "일정이 먼저 나오는 팀",
    "formula": "계획 3스푼 + 실행력 1스푼",
    "scene": "회의가 시작되자 일정표와 첫 아이디어가 나란히 등장합니다.",
    "keywords": ["체계적", "준비형"],
    "used_rule_ids": ["TEAM_BALANCED_AGENCY"]
  },
  "used_fallback": true,
  "model_id": "global.anthropic.claude-sonnet-4-20250514-v1:0",
  "prompt_version": "team_snapshot_v2",
  "validation_errors": ["LLM_ERROR: TimeoutError: Request timed out"]
}
```

---

## 4. 상태 의미

| status | 의미 |
|--------|------|
| `COMPLETED` | LLM 생성 → 검증 통과 |
| `FALLBACK` | LLM 실패 또는 검증 재실패 → 결정론적 템플릿 반환 |

두 상태 모두 `insight`는 **절대 null이 아니다**. 안전하게 저장·노출 가능.

---

## 5. 공개 폴백 함수 (백엔드 직접 호출용)

```python
from ai.nodes.fallback import build_team_fallback, build_private_fallback

# 팀 폴백
fallback = build_team_fallback(
    distribution={"planning": {"PLANNER": 3, "ADAPTER": 1, "NEUTRAL": 0}, ...},
    allowed_rule_ids=["TEAM_BALANCED_AGENCY"],
)
analysis_result.public_report_json = fallback.model_dump_json()

# 개인 폴백
fallback = build_private_fallback(
    self_positions={"planning": "PLANNER", "agency": "DRIVER", ...},
    allowed_rule_ids=["PERSONAL_PLANNER_STABILITY"],
)
private_insight.insight_json = fallback.model_dump_json()
```

---

## 6. DB 저장 가이드

```python
# 팀 코멘트
analysis_result.status = generation.status
analysis_result.public_report_json = generation.insight.model_dump_json()
analysis_result.used_fallback = generation.used_fallback
analysis_result.prompt_version = generation.prompt_version
analysis_result.model_id = generation.model_id
analysis_result.validation_status = (
    "PASSED" if not generation.validation_errors else "FAILED_THEN_FALLBACK"
)

# 개인 인사이트 — 동일 패턴
private_insight.status = generation.status
private_insight.insight_json = generation.insight.model_dump_json()
private_insight.used_fallback = generation.used_fallback
```

---

## 7. 프론트에 노출하면 안 되는 내부 필드

| 필드 | 이유 |
|------|------|
| `internal_index` | 내부 점수 |
| `team_grade` | 내부 등급 |
| `validation_errors` | 디버깅용 |
| `matched_rule_ids` | 내부 규칙 ID |
| `model_id` | 운영 정보 |
| `prompt_version` | 운영 정보 |
| `team_strength_codes` | 내부 코드 |
| `team_caution_codes` | 내부 코드 |
| `top_complement_pairs` | 공개 불필요 |

**프론트에 전달할 필드 (insight 내부만)**:
- TEAM: `title`, `formula`, `scene`, `keywords`
- SELF_ONLY: `card_title`, `contribution`, `optional_try`

---

## 8. AWS 자격 증명

- EC2: 인스턴스 프로파일 IAM Role (Bedrock 호출 권한)
- 로컬 개발: AWS named profile (`AWS_PROFILE` 환경변수) 또는 `aws sso login`
- 장기 Access Key 생성·저장 금지
- `BEDROCK_MODEL_ID` 환경변수로 모델 교체 가능
  - 기본값: `global.anthropic.claude-sonnet-4-20250514-v1:0`
  - 팀 계정 권한에 따라 다른 모델 ID 사용 가능

---

## 9. 백엔드 마이그레이션 (backend 75240c8 이후)

### 이미 완료된 항목 (75240c8)
- TeamResultResponse에서 team_grade 제거
- team_caution_codes 제거
- top_caution_pairs 제거
- BackgroundTasks 내부에서 새 DB session 생성
- 외부 예외 시 null 결과 방지

### 아직 수행해야 할 항목
1. V1 `_build_fallback_insight_json()` → V2 `build_team_fallback()` / `build_private_fallback()` 호출로 교체
2. 공개 API에서 `top_complement_pairs` 제거
3. 공개 API에서 `team_strength_codes` 제거
4. `dto` 브랜치 AI V2 커밋 병합
5. `public_report_json`에 TeamSnapshot JSON 저장 확인
6. `insight_json`에 PrivateCard JSON 저장 확인
7. V1 `GeneratedInsight`/`InsightItem` 직접 import 제거

---

## 10. 빌더 함수 (규칙 엔진 → AI 입력)

```python
from app.services.chemistry.engine import (
    build_team_comment_input,
    build_private_comment_input,
    run_team_analysis,
    match_private_rules,
)

# 팀 분석 후 AI 입력 구성
analysis = run_team_analysis(profiles)
team_input = build_team_comment_input(analysis, analysis_result_id, team_size)

# 개인 분석 후 AI 입력 구성
private_result = match_private_rules(profile, analysis.distribution, team_size)
private_input = build_private_comment_input(
    private_result, analysis_result_id, analysis.distribution, profile
)
```

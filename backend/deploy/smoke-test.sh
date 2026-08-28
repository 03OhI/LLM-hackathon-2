#!/usr/bin/env bash
#
# team-chemistry-analyzer 백엔드 smoke test
#
# 배포 후 최소 흐름(health → 세션 생성 → 초대 참여 → 제출 → 분석 → 팀 결과)이
# 실제로 동작하는지 확인한다. 실패 시 non-zero exit code.
#
# 사용법:
#   BASE_URL=http://localhost/api ./smoke-test.sh
#   (기본값: http://localhost/api)

set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost/api}"

fail() {
    echo "SMOKE TEST FAILED: $1" >&2
    exit 1
}

require_json_field() {
    local json="$1" field="$2"
    python3 -c "
import json, sys
d = json.loads(sys.argv[1])
if sys.argv[2] not in d:
    sys.exit(1)
print(d[sys.argv[2]])
" "$json" "$field" || fail "필드 '$field'를 응답에서 찾을 수 없습니다: $json"
}

echo "== 1. GET /api/health =="
HEALTH_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/health")
[ "$HEALTH_STATUS" = "200" ] || fail "health check가 200이 아닙니다 (got $HEALTH_STATUS)"
echo "OK ($HEALTH_STATUS)"

echo "== 2. POST /api/sessions =="
CREATE_RESP=$(curl -s -X POST "$BASE_URL/sessions" \
    -H "Content-Type: application/json" \
    -d '{"name":"smoke-test-session","expected_member_count":3}')
SESSION_ID=$(require_json_field "$CREATE_RESP" session_id)
INVITE_TOKEN=$(require_json_field "$CREATE_RESP" invite_token)
HOST_SECRET=$(require_json_field "$CREATE_RESP" host_secret)
echo "OK (session_id=$SESSION_ID)"

echo "== 3. POST /api/invites/{token}/participants x3 =="
declare -a PARTICIPANT_IDS
declare -a PARTICIPANT_SECRETS
for i in 1 2 3; do
    JOIN_RESP=$(curl -s -X POST "$BASE_URL/invites/$INVITE_TOKEN/participants" \
        -H "Content-Type: application/json" \
        -d "{\"nickname\":\"smoke-user-$i\"}")
    PARTICIPANT_IDS[$i]=$(require_json_field "$JOIN_RESP" participant_id)
    PARTICIPANT_SECRETS[$i]=$(require_json_field "$JOIN_RESP" participant_secret)
done
echo "OK (3 participants joined)"

echo "== 4. POST submissions/type x3 =="
POSITIONS=(
  '{"positions":{"planning":"PLANNER","agency":"DRIVER","conflict":"CONFRONTER","communication":"DIRECT"}}'
  '{"positions":{"planning":"ADAPTER","agency":"SUPPORTER","conflict":"HARMONIZER","communication":"TACTFUL"}}'
  '{"positions":{"planning":"PLANNER","agency":"SUPPORTER","conflict":"HARMONIZER","communication":"DIRECT"}}'
)
for i in 1 2 3; do
    STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST \
        "$BASE_URL/participants/${PARTICIPANT_IDS[$i]}/submissions/type" \
        -H "Content-Type: application/json" \
        -H "Authorization: Bearer ${PARTICIPANT_SECRETS[$i]}" \
        -d "${POSITIONS[$((i-1))]}")
    [ "$STATUS" = "200" ] || fail "참여자 $i 제출이 200이 아닙니다 (got $STATUS)"
done
echo "OK (3 submissions)"

echo "== 5. POST /api/sessions/{id}/analysis =="
ANALYSIS_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST \
    "$BASE_URL/sessions/$SESSION_ID/analysis" \
    -H "Authorization: Bearer $HOST_SECRET")
[ "$ANALYSIS_STATUS" = "200" ] || fail "분석 시작이 200이 아닙니다 (got $ANALYSIS_STATUS)"
echo "OK ($ANALYSIS_STATUS)"

echo "== 6. GET /api/sessions/{id}/results/team =="
TEAM_RESULT=$(curl -s "$BASE_URL/sessions/$SESSION_ID/results/team")
TEAM_GRADE=$(require_json_field "$TEAM_RESULT" team_grade)
echo "$TEAM_RESULT" | grep -q "internal_index" && fail "team 결과에 internal_index가 유출됐습니다"
echo "OK (team_grade=$TEAM_GRADE, internal_index 미노출 확인)"

echo "== 7. GET /api/sessions/{id}/results/me (participant 1) =="
ME_STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
    "$BASE_URL/sessions/$SESSION_ID/results/me" \
    -H "Authorization: Bearer ${PARTICIPANT_SECRETS[1]}")
[ "$ME_STATUS" = "200" ] || fail "개인 결과 조회가 200이 아닙니다 (got $ME_STATUS)"
echo "OK ($ME_STATUS)"

echo ""
echo "ALL SMOKE TESTS PASSED"

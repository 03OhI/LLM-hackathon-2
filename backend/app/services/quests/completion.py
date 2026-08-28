"""
완료 조건 검사 — SPEC_V5_CONTEST_QUEST_AGENT.md §4.3, §6

completion_condition.checks를 일반 코드로 검사한다. LLM은 관여하지 않는다.

result_json 저장 형식:
{
  "member_submissions": {"<participant_id>": {"<TYPE>": {"count": int, "value": Any}}},
  "team_submissions": {"<TYPE>": {"count": int, "value": Any}}
}

PUT 요청은 상태를 "설정"한다(REST PUT 의미론) — 팀원이 같은 타입을 다시 제출하면
그 타입의 count/value가 교체된다. NODE_CREATE처럼 누적 개수를 의미하는 체크는
클라이언트가 현재까지의 총 개수를 count로 보내는 것을 전제로 한다.
"""

from __future__ import annotations

import json

from app.services.quests.schemas import COMPLETION_CHECK_TYPES, COMPLETION_SCOPES


def empty_result() -> dict:
    return {"member_submissions": {}, "team_submissions": {}}


def load_result(result_json: str | None) -> dict:
    if not result_json:
        return empty_result()
    data = json.loads(result_json)
    data.setdefault("member_submissions", {})
    data.setdefault("team_submissions", {})
    return data


def dump_result(result: dict) -> str:
    return json.dumps(result)


def apply_member_submission(
    result: dict, participant_id: str, check_type: str, *, count: int, value=None
) -> dict:
    if check_type not in COMPLETION_CHECK_TYPES:
        raise ValueError(f"허용되지 않은 체크 타입: {check_type}")
    member = result["member_submissions"].setdefault(participant_id, {})
    member[check_type] = {"count": count, "value": value}
    return result


def apply_team_submission(result: dict, check_type: str, *, count: int, value=None) -> dict:
    if check_type not in COMPLETION_CHECK_TYPES:
        raise ValueError(f"허용되지 않은 체크 타입: {check_type}")
    result["team_submissions"][check_type] = {"count": count, "value": value}
    return result


def _check_satisfied(check: dict, result: dict, member_ids: list[str]) -> bool:
    check_type = check.get("type")
    scope = check.get("scope")
    min_count = check.get("min_count", 1)

    if scope not in COMPLETION_SCOPES or check_type not in COMPLETION_CHECK_TYPES:
        return False

    if scope == "TEAM":
        entry = result["team_submissions"].get(check_type)
        return bool(entry) and entry.get("count", 0) >= min_count

    if scope == "PER_MEMBER":
        if not member_ids:
            return False
        for pid in member_ids:
            entry = result["member_submissions"].get(pid, {}).get(check_type)
            if not entry or entry.get("count", 0) < min_count:
                return False
        return True

    return False


def unmet_checks(checks: list[dict], result: dict, member_ids: list[str]) -> list[dict]:
    """충족되지 않은 체크 목록. 빈 리스트면 완료 조건을 모두 만족한 것."""
    return [c for c in checks if not _check_satisfied(c, result, member_ids)]


def is_completion_satisfied(checks: list[dict], result: dict, member_ids: list[str]) -> bool:
    return not unmet_checks(checks, result, member_ids)

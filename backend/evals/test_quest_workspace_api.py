"""
퀘스트/워크스페이스 백엔드 API 통합 테스트 — SPEC_V5_CONTEST_QUEST_AGENT.md §9

FastAPI TestClient + 임시 SQLite 파일. DATABASE_URL을 app.* 최초 import 이전에
설정해야 app.config.get_settings()(lru_cache 싱글톤)가 임시 DB를 가리키게 된다.

ai.quest_assignment.assign_quest는 이 테스트 환경(AWS 자격 증명 없음)에서는
내부적으로 결정론적 경로(RULE 또는 FALLBACK)로 귀결되지만, 백엔드 입장에서는
AGENT/RULE/FALLBACK 중 무엇이 오든 유효한 QuestAssignmentDecision이면 동일하게
처리해야 하므로 assignment_source 값 자체는 세밀하게 검증하지 않고 "카탈로그에
실제로 있는 퀘스트인지"만 검증한다.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

BACKEND_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(BACKEND_ROOT))

_TMP_DB_FD, _TMP_DB_PATH = tempfile.mkstemp(prefix="test_quest_workspace_api_", suffix=".db")
os.close(_TMP_DB_FD)
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP_DB_PATH}"

import pytest
from sqlmodel import Session as DBSession
from sqlmodel import select
from fastapi.testclient import TestClient

from app.db import engine, init_db
from app.main import app
from app.models import QuestAssignment

client = TestClient(app)


@pytest.fixture(scope="module", autouse=True)
def _setup_and_teardown_db():
    init_db()
    yield
    # 삭제하지 않는다 — app.db의 engine/settings는 프로세스 전체 lru_cache 싱글톤이라
    # 이 세션에서 가장 먼저 app.db를 import한 evals/test_*.py 모듈의 DATABASE_URL만 실제로
    # 쓰이고, 나머지 모듈은 이 파일을 공유해서 쓴다. 그 상태에서 먼저 끝난 모듈이 파일을
    # 지우면 나중에 도는 다른 테스트 모듈이 "unable to open database file"로 깨진다.


# ──────────────────────────────────────────────
# 헬퍼
# ──────────────────────────────────────────────

_TYPE_CYCLE = [
    {"planning": "PLANNER", "agency": "DRIVER", "conflict": "HARMONIZER", "communication": "DIRECT"},
    {"planning": "PLANNER", "agency": "SUPPORTER", "conflict": "HARMONIZER", "communication": "TACTFUL"},
    {"planning": "ADAPTER", "agency": "SUPPORTER", "conflict": "CONFRONTER", "communication": "DIRECT"},
    {"planning": "ADAPTER", "agency": "DRIVER", "conflict": "CONFRONTER", "communication": "TACTFUL"},
]


def _auth(secret: str) -> dict:
    return {"Authorization": f"Bearer {secret}"}


def _create_session(expected_member_count: int) -> dict:
    resp = client.post(
        "/api/sessions", json={"name": "퀘스트 테스트팀", "expected_member_count": expected_member_count}
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _join(invite_token: str, nickname: str) -> tuple[str, str]:
    resp = client.post(f"/api/invites/{invite_token}/participants", json={"nickname": nickname})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    return data["participant_id"], data["participant_secret"]


def _submit_type(participant_id: str, secret: str, positions: dict) -> None:
    resp = client.post(
        f"/api/participants/{participant_id}/submissions/type",
        json={"positions": positions},
        headers=_auth(secret),
    )
    assert resp.status_code == 200, resp.text


def _trigger_analysis(session_id: str, host_secret: str) -> None:
    resp = client.post(f"/api/sessions/{session_id}/analysis", headers=_auth(host_secret))
    assert resp.status_code == 200, resp.text


def build_team(team_size: int) -> dict:
    """team_size명 팀을 만들고 전원 유형 제출 + 분석까지 끝낸 상태로 반환한다."""
    session = _create_session(expected_member_count=team_size)
    session_id = session["session_id"]
    host_secret = session["host_secret"]
    invite_token = session["invite_token"]

    members = []
    for i in range(team_size):
        pid, psecret = _join(invite_token, f"member{i}")
        positions = _TYPE_CYCLE[i % len(_TYPE_CYCLE)]
        _submit_type(pid, psecret, positions)
        members.append((pid, psecret))

    _trigger_analysis(session_id, host_secret)

    return {"session_id": session_id, "host_secret": host_secret, "members": members}


def assign_quest(session_id: str, host_secret: str) -> dict:
    resp = client.post(f"/api/rooms/{session_id}/quests/assign", headers=_auth(host_secret))
    assert resp.status_code == 200, resp.text
    return resp.json()


def complete_quest_generically(session_id: str, host_secret: str, members: list[tuple[str, str]]) -> dict:
    """어떤 퀘스트가 배정되든 team_completion_status.unmet_check_types를 보고
    필요한 체크를 전부 채운 뒤 완료를 확정한다."""
    current = client.get(f"/api/rooms/{session_id}/quests/current", headers=_auth(host_secret)).json()
    assignment_id = current["assignment"]["id"]

    my_status = client.get(
        f"/api/rooms/{session_id}/quests/current", headers=_auth(members[0][1])
    ).json()["my_response_status"]
    per_member_types = set(my_status.keys()) if my_status else set()
    unmet = set(current["team_completion_status"]["unmet_check_types"])
    team_only_types = unmet - per_member_types

    for pid, psecret in members:
        if per_member_types:
            resp = client.put(
                f"/api/quest-assignments/{assignment_id}/responses/me",
                json={"checks": [{"type": t, "count": 1} for t in per_member_types]},
                headers=_auth(psecret),
            )
            assert resp.status_code == 200, resp.text

    if team_only_types:
        resp = client.put(
            f"/api/quest-assignments/{assignment_id}/result",
            json={"checks": [{"type": t, "count": 1} for t in team_only_types]},
            headers=_auth(host_secret),
        )
        assert resp.status_code == 200, resp.text

    resp = client.post(f"/api/quest-assignments/{assignment_id}/complete", headers=_auth(host_secret))
    assert resp.status_code == 200, resp.text
    return resp.json()


# ──────────────────────────────────────────────
# 카탈로그
# ──────────────────────────────────────────────


def test_quest_catalog_validates_cleanly():
    from app.services.quests.validate_quests import load_and_validate

    result = load_and_validate()
    assert result.schema_errors == {}
    assert result.business_errors == {}
    assert len(result.valid_templates) >= 8


# ──────────────────────────────────────────────
# 3명 / 10명 팀 배정
# ──────────────────────────────────────────────


@pytest.mark.parametrize("team_size", [3, 10])
def test_assign_quest_for_team_size(team_size):
    team = build_team(team_size)
    result = assign_quest(team["session_id"], team["host_secret"])

    from app.services.quests.catalog import get_quest_template

    assert get_quest_template(result["quest_id"]) is not None
    assert result["assignment"]["status"] == "ASSIGNED"
    assert result["assignment"]["assignment_source"] in ("AGENT", "RULE", "FALLBACK")


def test_assign_quest_is_idempotent():
    team = build_team(4)
    first = assign_quest(team["session_id"], team["host_secret"])
    second = assign_quest(team["session_id"], team["host_secret"])
    assert first["assignment"]["id"] == second["assignment"]["id"]


def test_recommendations_return_three_distinct_public_quests():
    team = build_team(4)
    resp = client.get(
        f"/api/rooms/{team['session_id']}/quests/recommendations",
        headers=_auth(team["host_secret"]),
    )
    assert resp.status_code == 200, resp.text
    items = resp.json()["recommendations"]
    assert len(items) == 3
    assert len({item["quest_id"] for item in items}) == 3
    assert all(
        set(item)
        == {"quest_id", "title", "summary", "duration_minutes", "category", "match_reason"}
        for item in items
    )
    assert all("rule_id" not in json.dumps(item) for item in items)


def test_host_can_select_one_of_three_recommendations():
    team = build_team(4)
    recommendations = client.get(
        f"/api/rooms/{team['session_id']}/quests/recommendations",
        headers=_auth(team["host_secret"]),
    ).json()["recommendations"]
    selected = recommendations[1]

    resp = client.post(
        f"/api/rooms/{team['session_id']}/quests/assign",
        json={"quest_id": selected["quest_id"]},
        headers=_auth(team["host_secret"]),
    )
    assert resp.status_code == 200, resp.text
    result = resp.json()
    assert result["quest_id"] == selected["quest_id"]
    assert result["assignment"]["assignment_source"] == "RULE"


def test_unrecommended_quest_cannot_be_forced_by_request_body():
    team = build_team(4)
    resp = client.post(
        f"/api/rooms/{team['session_id']}/quests/assign",
        json={"quest_id": "NOT_A_REAL_RECOMMENDATION"},
        headers=_auth(team["host_secret"]),
    )
    assert resp.status_code == 422


def test_only_one_active_assignment_enforced_by_db_constraint():
    team = build_team(4)
    active = assign_quest(team["session_id"], team["host_secret"])

    with DBSession(engine) as db:
        existing = db.exec(
            select(QuestAssignment).where(QuestAssignment.id == active["assignment"]["id"])
        ).one()
        duplicate = QuestAssignment(
            id="duplicate-active-assignment",
            session_id=team["session_id"],
            quest_template_id=existing.quest_template_id,
            status="ASSIGNED",
            active_slot=team["session_id"],  # 같은 방의 두 번째 활성 슬롯 — UNIQUE 위반
            assignment_source="FALLBACK",
            assignment_reason="test",
            intro_message="test",
            version=existing.version,
        )
        db.add(duplicate)
        with pytest.raises(Exception):
            db.commit()
        db.rollback()


# ──────────────────────────────────────────────
# 권한 / 접근 제어
# ──────────────────────────────────────────────


def test_member_cannot_call_host_only_assign():
    team = build_team(3)
    member_secret = team["members"][0][1]
    resp = client.post(f"/api/rooms/{team['session_id']}/quests/assign", headers=_auth(member_secret))
    assert resp.status_code in (401, 403)


def test_cross_room_access_blocked():
    team_a = build_team(3)
    team_b = build_team(3)
    assign_quest(team_a["session_id"], team_a["host_secret"])

    # B팀 참여자로 A팀 방의 현재 퀘스트를 조회할 수 없다.
    b_member_secret = team_b["members"][0][1]
    resp = client.get(
        f"/api/rooms/{team_a['session_id']}/quests/current", headers=_auth(b_member_secret)
    )
    assert resp.status_code == 401

    # B팀 방장 secret으로 A팀 방을 배정할 수 없다.
    resp = client.post(
        f"/api/rooms/{team_a['session_id']}/quests/assign", headers=_auth(team_b["host_secret"])
    )
    assert resp.status_code == 401


def test_cross_room_workspace_access_blocked():
    team_a = _started_workspace()
    team_b = build_team(3)

    b_member_secret = team_b["members"][0][1]
    resp = client.get(f"/api/workspaces/{team_a['workspace_id']}", headers=_auth(b_member_secret))
    assert resp.status_code == 401

    resp = client.post(
        f"/api/workspaces/{team_a['workspace_id']}/tasks",
        json={"title": "무단 생성 시도"},
        headers=_auth(b_member_secret),
    )
    assert resp.status_code == 401


# ──────────────────────────────────────────────
# 완료 조건 / 상태 전이
# ──────────────────────────────────────────────


def test_complete_allowed_even_when_condition_not_met():
    """완료 조건 충족 여부와 무관하게 방장이 바로 완료할 수 있다(의도적 정책)."""
    team = build_team(3)
    assigned = assign_quest(team["session_id"], team["host_secret"])
    assignment_id = assigned["assignment"]["id"]

    resp = client.post(f"/api/quest-assignments/{assignment_id}/complete", headers=_auth(team["host_secret"]))
    assert resp.status_code == 200, resp.text
    assert resp.json()["assignment"]["status"] == "COMPLETED"


def test_no_state_change_after_completion():
    team = build_team(3)
    assign_quest(team["session_id"], team["host_secret"])
    completed = complete_quest_generically(team["session_id"], team["host_secret"], team["members"])
    assignment_id = completed["assignment"]["id"]
    assert completed["assignment"]["status"] == "COMPLETED"

    again = client.post(f"/api/quest-assignments/{assignment_id}/complete", headers=_auth(team["host_secret"]))
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "QUEST_ALREADY_FINALIZED"

    skip_resp = client.post(f"/api/quest-assignments/{assignment_id}/skip", headers=_auth(team["host_secret"]))
    assert skip_resp.status_code == 409
    assert skip_resp.json()["error"]["code"] == "QUEST_ALREADY_FINALIZED"


def test_skip_has_no_penalty_data():
    team = build_team(3)
    assigned = assign_quest(team["session_id"], team["host_secret"])
    assignment_id = assigned["assignment"]["id"]

    resp = client.post(f"/api/quest-assignments/{assignment_id}/skip", headers=_auth(team["host_secret"]))
    assert resp.status_code == 200
    body = resp.json()
    assert body["assignment"]["status"] == "SKIPPED"

    serialized = json.dumps(body)
    for forbidden in ("penalty", "grade", "coin", "leaderboard", "점수", "등급", "불이익"):
        assert forbidden not in serialized


# ──────────────────────────────────────────────
# 협업 시작
# ──────────────────────────────────────────────


def test_workspace_start_auto_skips_unfinished_quest():
    """방장은 퀘스트를 끝내지 않아도 바로 협업을 시작할 수 있다(의도적 정책).
    진행 중이던 퀘스트는 시작하면서 자동으로 SKIPPED 처리된다."""
    team = build_team(3)
    assigned = assign_quest(team["session_id"], team["host_secret"])
    assignment_id = assigned["assignment"]["id"]

    resp = client.post(f"/api/rooms/{team['session_id']}/workspace/start", headers=_auth(team["host_secret"]))
    assert resp.status_code == 200, resp.text

    current = client.get(
        f"/api/rooms/{team['session_id']}/quests/current", headers=_auth(team["host_secret"])
    ).json()
    assert current["assignment"]["id"] == assignment_id
    assert current["assignment"]["status"] == "SKIPPED"


def test_workspace_start_works_with_no_quest_assigned_at_all():
    """퀘스트를 한 번도 고르지 않았어도 협업을 시작할 수 있다."""
    team = build_team(3)

    resp = client.post(f"/api/rooms/{team['session_id']}/workspace/start", headers=_auth(team["host_secret"]))
    assert resp.status_code == 200, resp.text


def test_workspace_start_idempotent_after_quest_completed():
    team = build_team(3)
    assign_quest(team["session_id"], team["host_secret"])
    complete_quest_generically(team["session_id"], team["host_secret"], team["members"])

    first = client.post(f"/api/rooms/{team['session_id']}/workspace/start", headers=_auth(team["host_secret"]))
    assert first.status_code == 200
    second = client.post(f"/api/rooms/{team['session_id']}/workspace/start", headers=_auth(team["host_secret"]))
    assert second.status_code == 200
    assert first.json()["id"] == second.json()["id"]


def test_workspace_start_works_after_skip_too():
    team = build_team(3)
    assigned = assign_quest(team["session_id"], team["host_secret"])
    client.post(f"/api/quest-assignments/{assigned['assignment']['id']}/skip", headers=_auth(team["host_secret"]))

    resp = client.post(f"/api/rooms/{team['session_id']}/workspace/start", headers=_auth(team["host_secret"]))
    assert resp.status_code == 200


# ──────────────────────────────────────────────
# 공동 할 일 / 공유 링크
# ──────────────────────────────────────────────


def _started_workspace(team_size: int = 3) -> dict:
    team = build_team(team_size)
    assigned = assign_quest(team["session_id"], team["host_secret"])
    client.post(f"/api/quest-assignments/{assigned['assignment']['id']}/skip", headers=_auth(team["host_secret"]))
    ws = client.post(
        f"/api/rooms/{team['session_id']}/workspace/start", headers=_auth(team["host_secret"])
    ).json()
    team["workspace_id"] = ws["id"]
    return team


def test_task_status_transitions():
    team = _started_workspace()
    member_secret = team["members"][0][1]

    created = client.post(
        f"/api/workspaces/{team['workspace_id']}/tasks",
        json={"title": "발표자료 초안 작성"},
        headers=_auth(member_secret),
    )
    assert created.status_code == 200, created.text
    task_id = created.json()["id"]
    assert created.json()["status"] == "TODO"

    to_progress = client.patch(
        f"/api/tasks/{task_id}", json={"status": "IN_PROGRESS"}, headers=_auth(member_secret)
    )
    assert to_progress.status_code == 200
    assert to_progress.json()["status"] == "IN_PROGRESS"

    to_done = client.patch(f"/api/tasks/{task_id}", json={"status": "DONE"}, headers=_auth(member_secret))
    assert to_done.status_code == 200
    assert to_done.json()["status"] == "DONE"

    invalid = client.patch(f"/api/tasks/{task_id}", json={"status": "BOGUS"}, headers=_auth(member_secret))
    assert invalid.status_code == 422


def test_task_delete_permission_author_or_host():
    team = _started_workspace()
    author_secret = team["members"][0][1]
    other_secret = team["members"][1][1]
    host_secret = team["host_secret"]

    created = client.post(
        f"/api/workspaces/{team['workspace_id']}/tasks",
        json={"title": "테스트 케이스 작성"},
        headers=_auth(author_secret),
    ).json()
    task_id = created["id"]

    forbidden = client.delete(f"/api/tasks/{task_id}", headers=_auth(other_secret))
    assert forbidden.status_code == 403

    ok = client.delete(f"/api/tasks/{task_id}", headers=_auth(author_secret))
    assert ok.status_code == 200

    created2 = client.post(
        f"/api/workspaces/{team['workspace_id']}/tasks",
        json={"title": "다시 작성"},
        headers=_auth(author_secret),
    ).json()
    host_delete = client.delete(f"/api/tasks/{created2['id']}", headers=_auth(host_secret))
    assert host_delete.status_code == 200


def test_resource_link_permission_author_or_host():
    team = _started_workspace()
    author_secret = team["members"][0][1]
    other_secret = team["members"][1][1]
    host_secret = team["host_secret"]

    created = client.post(
        f"/api/workspaces/{team['workspace_id']}/resources",
        json={"title": "레포", "url": "https://github.com/example/repo", "provider": "GITHUB"},
        headers=_auth(author_secret),
    )
    assert created.status_code == 200, created.text
    resource_id = created.json()["id"]

    forbidden = client.delete(f"/api/resources/{resource_id}", headers=_auth(other_secret))
    assert forbidden.status_code == 403

    ok = client.delete(f"/api/resources/{resource_id}", headers=_auth(author_secret))
    assert ok.status_code == 200

    created2 = client.post(
        f"/api/workspaces/{team['workspace_id']}/resources",
        json={"title": "레포2", "url": "https://github.com/example/repo2", "provider": "GITHUB"},
        headers=_auth(author_secret),
    ).json()
    host_delete = client.delete(f"/api/resources/{created2['id']}", headers=_auth(host_secret))
    assert host_delete.status_code == 200


def test_invalid_resource_provider_rejected():
    team = _started_workspace()
    resp = client.post(
        f"/api/workspaces/{team['workspace_id']}/resources",
        json={"title": "x", "url": "https://example.com", "provider": "NOT_A_PROVIDER"},
        headers=_auth(team["members"][0][1]),
    )
    assert resp.status_code == 422

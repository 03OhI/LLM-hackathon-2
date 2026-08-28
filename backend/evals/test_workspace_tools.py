"""
워크스페이스 도구 확장 백엔드 통합 테스트 — SPEC_V5.3
(상단 공지 / 회의 메모 / 발표 준비 체크리스트 / 빠른 의사결정 보드)

FastAPI TestClient + 임시 SQLite 파일. 패턴은 evals/test_quest_workspace_api.py와 동일하다.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

BACKEND_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(BACKEND_ROOT))

_TMP_DB_FD, _TMP_DB_PATH = tempfile.mkstemp(prefix="test_workspace_tools_", suffix=".db")
os.close(_TMP_DB_FD)
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP_DB_PATH}"

import pytest
from fastapi.testclient import TestClient

from app.db import init_db
from app.main import app

client = TestClient(app)


@pytest.fixture(scope="module", autouse=True)
def _setup_db():
    init_db()
    yield
    # 파일을 지우지 않는다 — 다른 테스트 모듈과 동일 이유(test_quest_workspace_api.py 주석 참고).


# ──────────────────────────────────────────────
# 헬퍼
# ──────────────────────────────────────────────

_TYPE_CYCLE = [
    {"planning": "PLANNER", "agency": "DRIVER", "conflict": "HARMONIZER", "communication": "DIRECT"},
    {"planning": "PLANNER", "agency": "SUPPORTER", "conflict": "HARMONIZER", "communication": "TACTFUL"},
    {"planning": "ADAPTER", "agency": "SUPPORTER", "conflict": "CONFRONTER", "communication": "DIRECT"},
]


def _auth(secret: str) -> dict:
    return {"Authorization": f"Bearer {secret}"}


def _started_workspace(team_size: int = 3) -> dict:
    """team_size명 팀을 만들고 퀘스트를 건너뛴 뒤 워크스페이스를 시작한 상태로 반환한다."""
    resp = client.post("/api/sessions", json={"name": "도구 테스트팀", "expected_member_count": team_size})
    assert resp.status_code == 200, resp.text
    session = resp.json()
    session_id = session["session_id"]
    host_secret = session["host_secret"]
    invite_token = session["invite_token"]

    members = []
    for i in range(team_size):
        joined = client.post(f"/api/invites/{invite_token}/participants", json={"nickname": f"member{i}"}).json()
        pid, psecret = joined["participant_id"], joined["participant_secret"]
        client.post(
            f"/api/participants/{pid}/submissions/type",
            json={"positions": _TYPE_CYCLE[i % len(_TYPE_CYCLE)]},
            headers=_auth(psecret),
        )
        members.append((pid, psecret))

    assert client.post(f"/api/sessions/{session_id}/analysis", headers=_auth(host_secret)).status_code == 200

    assigned = client.post(f"/api/rooms/{session_id}/quests/assign", headers=_auth(host_secret))
    assert assigned.status_code == 200, assigned.text
    assignment_id = assigned.json()["assignment"]["id"]
    client.post(f"/api/quest-assignments/{assignment_id}/skip", headers=_auth(host_secret))

    ws = client.post(f"/api/rooms/{session_id}/workspace/start", headers=_auth(host_secret))
    assert ws.status_code == 200, ws.text
    workspace = ws.json()

    return {
        "session_id": session_id,
        "host_secret": host_secret,
        "members": members,
        "workspace_id": workspace["id"],
        "workspace": workspace,
    }


# ──────────────────────────────────────────────
# 1) 상단 고정 공지
# ──────────────────────────────────────────────


def test_host_can_update_notice_and_member_can_read_it():
    team = _started_workspace()
    resp = client.patch(
        f"/api/workspaces/{team['workspace_id']}/notice",
        json={"notice": "오늘 17시까지 통합 완료", "deadline_at": "2026-08-29T17:00:00+09:00", "presentation_order": "3번째 발표"},
        headers=_auth(team["host_secret"]),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["notice"] == "오늘 17시까지 통합 완료"
    assert body["presentation_order"] == "3번째 발표"

    member_secret = team["members"][0][1]
    ws = client.get(f"/api/workspaces/{team['workspace_id']}", headers=_auth(member_secret))
    assert ws.status_code == 200
    assert ws.json()["notice"] == "오늘 17시까지 통합 완료"
    assert ws.json()["presentation_order"] == "3번째 발표"


def test_member_cannot_update_notice():
    team = _started_workspace()
    member_secret = team["members"][0][1]
    resp = client.patch(
        f"/api/workspaces/{team['workspace_id']}/notice",
        json={"notice": "무단 수정", "deadline_at": None, "presentation_order": None},
        headers=_auth(member_secret),
    )
    assert resp.status_code in (401, 403)


def test_notice_cross_room_access_blocked():
    team_a = _started_workspace()
    team_b = _started_workspace()
    resp = client.patch(
        f"/api/workspaces/{team_a['workspace_id']}/notice",
        json={"notice": "다른 방 공격", "deadline_at": None, "presentation_order": None},
        headers=_auth(team_b["host_secret"]),
    )
    assert resp.status_code in (401, 403)


# ──────────────────────────────────────────────
# 2) 회의 메모
# ──────────────────────────────────────────────


def test_meeting_note_crud_and_author_permission():
    team = _started_workspace()
    author_secret = team["members"][0][1]
    other_secret = team["members"][1][1]
    host_secret = team["host_secret"]

    created = client.post(
        f"/api/workspaces/{team['workspace_id']}/meeting-notes",
        json={
            "title": "1차 기획 회의",
            "content": "결과 화면과 퀘스트 흐름을 먼저 완성하기로 결정",
            "next_action": "민지는 결과 UI, 지훈은 API 연결",
        },
        headers=_auth(author_secret),
    )
    assert created.status_code == 200, created.text
    note_id = created.json()["id"]

    listed = client.get(f"/api/workspaces/{team['workspace_id']}/meeting-notes", headers=_auth(host_secret))
    assert listed.status_code == 200
    assert any(n["id"] == note_id for n in listed.json())

    forbidden = client.patch(
        f"/api/meeting-notes/{note_id}", json={"title": "무단 수정"}, headers=_auth(other_secret)
    )
    assert forbidden.status_code == 403

    ok = client.patch(f"/api/meeting-notes/{note_id}", json={"title": "수정됨"}, headers=_auth(author_secret))
    assert ok.status_code == 200
    assert ok.json()["title"] == "수정됨"

    host_ok = client.patch(
        f"/api/meeting-notes/{note_id}", json={"content": "방장이 수정"}, headers=_auth(host_secret)
    )
    assert host_ok.status_code == 200

    forbidden_delete = client.delete(f"/api/meeting-notes/{note_id}", headers=_auth(other_secret))
    assert forbidden_delete.status_code == 403

    ok_delete = client.delete(f"/api/meeting-notes/{note_id}", headers=_auth(author_secret))
    assert ok_delete.status_code == 200


def test_meeting_note_cross_room_access_blocked():
    team_a = _started_workspace()
    team_b = _started_workspace()
    resp = client.post(
        f"/api/workspaces/{team_a['workspace_id']}/meeting-notes",
        json={"title": "무단 생성", "content": "x"},
        headers=_auth(team_b["members"][0][1]),
    )
    assert resp.status_code in (401, 403)


# ──────────────────────────────────────────────
# 3) 발표 준비 체크리스트
# ──────────────────────────────────────────────


def test_default_checklist_items_created_on_workspace_start():
    team = _started_workspace()
    items = team["workspace"]["presentation_checklist"]
    assert len(items) == 4
    assert {i["item_type"] for i in items} == {"DEMO_URL", "SLIDES", "SCRIPT", "BACKUP"}
    assert {i["label"] for i in items} == {"시연 URL 확인", "발표 자료 확인", "발표 대본 확인", "백업 화면 확인"}
    assert all(i["completed"] is False for i in items)


def test_pre_existing_workspace_without_checklist_gets_backfilled_exactly_once():
    """배포 DB에 기능 추가 전 생성된 Workspace(체크리스트 0개)를 흉내낸다."""
    from sqlmodel import Session as DBSession
    from sqlmodel import select

    from app.db import engine
    from app.models import PresentationChecklistItem
    from app.services.workspace import checklist as checklist_service

    team = _started_workspace()
    workspace_id = team["workspace_id"]
    member_secret = team["members"][0][1]

    # start_workspace가 만든 기본 4개를 지워 "기능 추가 전 생성된 워크스페이스" 상태로 되돌린다.
    with DBSession(engine) as db:
        for item in checklist_service.list_items(workspace_id, db):
            db.delete(item)
        db.commit()
        assert checklist_service.list_items(workspace_id, db) == []

    first = client.get(f"/api/workspaces/{workspace_id}", headers=_auth(member_secret))
    assert first.status_code == 200
    first_items = first.json()["presentation_checklist"]
    assert len(first_items) == 4
    assert {i["item_type"] for i in first_items} == {"DEMO_URL", "SLIDES", "SCRIPT", "BACKUP"}

    # 다시 조회해도 중복 생성되지 않고 정확히 4개만 유지된다.
    second = client.get(f"/api/workspaces/{workspace_id}", headers=_auth(member_secret))
    assert second.status_code == 200
    second_items = second.json()["presentation_checklist"]
    assert len(second_items) == 4
    assert {i["id"] for i in second_items} == {i["id"] for i in first_items}

    with DBSession(engine) as db:
        rows = db.exec(
            select(PresentationChecklistItem).where(PresentationChecklistItem.workspace_id == workspace_id)
        ).all()
        assert len(rows) == 4


def test_member_can_toggle_checklist_completion():
    team = _started_workspace()
    member_secret = team["members"][0][1]
    item_id = team["workspace"]["presentation_checklist"][0]["id"]

    resp = client.patch(
        f"/api/presentation-checklist/{item_id}",
        json={"completed": True, "url": "http://54.64.89.202"},
        headers=_auth(member_secret),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["completed"] is True
    assert body["url"] == "http://54.64.89.202"
    assert body["completed_by"] == team["members"][0][0]

    back = client.patch(f"/api/presentation-checklist/{item_id}", json={"completed": False}, headers=_auth(member_secret))
    assert back.status_code == 200
    assert back.json()["completed_by"] is None


def test_checklist_item_delete_permission_author_or_host():
    team = _started_workspace()
    author_secret = team["members"][0][1]
    other_secret = team["members"][1][1]
    host_secret = team["host_secret"]

    created = client.post(
        f"/api/workspaces/{team['workspace_id']}/presentation-checklist",
        json={"item_type": "CUSTOM", "label": "리허설 완료"},
        headers=_auth(author_secret),
    )
    assert created.status_code == 200, created.text
    item_id = created.json()["id"]

    forbidden = client.delete(f"/api/presentation-checklist/{item_id}", headers=_auth(other_secret))
    assert forbidden.status_code == 403

    # 기본 항목(HOST 소유)은 팀원이 지울 수 없고 방장만 지울 수 있다.
    default_item_id = team["workspace"]["presentation_checklist"][0]["id"]
    member_delete_default = client.delete(f"/api/presentation-checklist/{default_item_id}", headers=_auth(other_secret))
    assert member_delete_default.status_code == 403
    host_delete_default = client.delete(f"/api/presentation-checklist/{default_item_id}", headers=_auth(host_secret))
    assert host_delete_default.status_code == 200

    ok = client.delete(f"/api/presentation-checklist/{item_id}", headers=_auth(author_secret))
    assert ok.status_code == 200


def test_checklist_invalid_item_type_rejected():
    team = _started_workspace()
    resp = client.post(
        f"/api/workspaces/{team['workspace_id']}/presentation-checklist",
        json={"item_type": "NOT_A_TYPE", "label": "x"},
        headers=_auth(team["host_secret"]),
    )
    assert resp.status_code == 422


# ──────────────────────────────────────────────
# 4) 빠른 의사결정 보드
# ──────────────────────────────────────────────


def test_decision_create_and_list_options():
    team = _started_workspace()
    resp = client.post(
        f"/api/workspaces/{team['workspace_id']}/decisions",
        json={
            "title": "최종 서비스명",
            "description": "발표 자료에 사용할 이름을 정합니다.",
            "options": ["TMTI", "Team Chemistry", "Team Mate"],
        },
        headers=_auth(team["members"][0][1]),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "OPEN"
    assert [o["label"] for o in body["options"]] == ["TMTI", "Team Chemistry", "Team Mate"]
    assert all(o["vote_count"] == 0 for o in body["options"])
    assert body["my_vote_option_id"] is None


def test_revote_changes_existing_vote_not_duplicates():
    team = _started_workspace()
    member_secret = team["members"][0][1]
    created = client.post(
        f"/api/workspaces/{team['workspace_id']}/decisions",
        json={"title": "안건", "options": ["A", "B"]},
        headers=_auth(member_secret),
    ).json()
    decision_id = created["id"]
    option_a, option_b = created["options"][0]["id"], created["options"][1]["id"]

    first = client.post(f"/api/decisions/{decision_id}/vote", json={"option_id": option_a}, headers=_auth(member_secret))
    assert first.status_code == 200
    assert first.json()["my_vote_option_id"] == option_a
    counts_after_first = {o["id"]: o["vote_count"] for o in first.json()["options"]}
    assert counts_after_first[option_a] == 1
    assert counts_after_first[option_b] == 0

    second = client.post(f"/api/decisions/{decision_id}/vote", json={"option_id": option_b}, headers=_auth(member_secret))
    assert second.status_code == 200
    assert second.json()["my_vote_option_id"] == option_b
    counts_after_second = {o["id"]: o["vote_count"] for o in second.json()["options"]}
    assert counts_after_second[option_a] == 0  # 재투표로 기존 표가 대체된다 (중복 아님)
    assert counts_after_second[option_b] == 1


def test_other_members_votes_not_exposed():
    team = _started_workspace()
    member_a, member_b = team["members"][0][1], team["members"][1][1]
    created = client.post(
        f"/api/workspaces/{team['workspace_id']}/decisions",
        json={"title": "안건", "options": ["A", "B"]},
        headers=_auth(member_a),
    ).json()
    decision_id, option_a = created["id"], created["options"][0]["id"]

    client.post(f"/api/decisions/{decision_id}/vote", json={"option_id": option_a}, headers=_auth(member_a))

    # member_b 시점에서는 자신의 my_vote_option_id만 보이고(None), 집계 수치만 공개된다.
    view_as_b = client.get(f"/api/workspaces/{team['workspace_id']}/decisions", headers=_auth(member_b)).json()
    decision_view = next(d for d in view_as_b if d["id"] == decision_id)
    assert decision_view["my_vote_option_id"] is None
    assert next(o for o in decision_view["options"] if o["id"] == option_a)["vote_count"] == 1
    assert "participant_id" not in str(decision_view)  # 개별 투표자 식별자가 응답에 없다


def test_host_cannot_vote():
    team = _started_workspace()
    created = client.post(
        f"/api/workspaces/{team['workspace_id']}/decisions",
        json={"title": "안건", "options": ["A", "B"]},
        headers=_auth(team["host_secret"]),
    ).json()
    resp = client.post(
        f"/api/decisions/{created['id']}/vote",
        json={"option_id": created["options"][0]["id"]},
        headers=_auth(team["host_secret"]),
    )
    assert resp.status_code == 403


def test_only_host_can_finalize_and_vote_rejected_after():
    team = _started_workspace()
    member_secret = team["members"][0][1]
    created = client.post(
        f"/api/workspaces/{team['workspace_id']}/decisions",
        json={"title": "안건", "options": ["A", "B"]},
        headers=_auth(member_secret),
    ).json()
    decision_id, option_a = created["id"], created["options"][0]["id"]

    forbidden = client.post(
        f"/api/decisions/{decision_id}/finalize", json={"final_result": "A"}, headers=_auth(member_secret)
    )
    assert forbidden.status_code == 403

    finalized = client.post(
        f"/api/decisions/{decision_id}/finalize", json={"final_result": "A"}, headers=_auth(team["host_secret"])
    )
    assert finalized.status_code == 200
    assert finalized.json()["status"] == "FINALIZED"
    assert finalized.json()["final_result"] == "A"

    rejected_vote = client.post(
        f"/api/decisions/{decision_id}/vote", json={"option_id": option_a}, headers=_auth(member_secret)
    )
    assert rejected_vote.status_code == 409
    assert rejected_vote.json()["error"]["code"] == "DECISION_ALREADY_FINALIZED"

    double_finalize = client.post(
        f"/api/decisions/{decision_id}/finalize", json={"final_result": "B"}, headers=_auth(team["host_secret"])
    )
    assert double_finalize.status_code == 409


def test_decision_cross_room_access_blocked():
    team_a = _started_workspace()
    team_b = _started_workspace()
    resp = client.post(
        f"/api/workspaces/{team_a['workspace_id']}/decisions",
        json={"title": "무단 생성", "options": ["A", "B"]},
        headers=_auth(team_b["members"][0][1]),
    )
    assert resp.status_code in (401, 403)


# ──────────────────────────────────────────────
# 5) 기존 Task/Resource API 회귀 없음 (새 응답 필드와 공존 확인)
# ──────────────────────────────────────────────


def test_workspace_response_keeps_existing_fields_alongside_new_ones():
    team = _started_workspace()
    member_secret = team["members"][0][1]

    client.post(
        f"/api/workspaces/{team['workspace_id']}/tasks",
        json={"title": "발표자료 초안 작성"},
        headers=_auth(member_secret),
    )
    client.post(
        f"/api/workspaces/{team['workspace_id']}/resources",
        json={"title": "레포", "url": "https://github.com/example/repo", "provider": "GITHUB"},
        headers=_auth(member_secret),
    )

    resp = client.get(f"/api/workspaces/{team['workspace_id']}", headers=_auth(member_secret))
    assert resp.status_code == 200
    body = resp.json()
    for field in ("id", "session_id", "status", "started_at", "tasks", "resources"):
        assert field in body
    assert len(body["tasks"]) == 1
    assert len(body["resources"]) == 1
    for field in ("notice", "deadline_at", "presentation_order", "meeting_notes", "presentation_checklist", "decisions"):
        assert field in body
    assert len(body["presentation_checklist"]) == 4


def test_resource_link_github_figma_notion_providers_roundtrip():
    team = _started_workspace()
    member_secret = team["members"][0][1]
    for provider, url in (
        ("GITHUB", "https://github.com/example/repo"),
        ("FIGMA", "https://figma.com/file/example"),
        ("NOTION", "https://notion.so/example"),
    ):
        created = client.post(
            f"/api/workspaces/{team['workspace_id']}/resources",
            json={"title": provider.title(), "url": url, "provider": provider},
            headers=_auth(member_secret),
        )
        assert created.status_code == 200, created.text
        assert created.json()["provider"] == provider

    listed = client.get(f"/api/workspaces/{team['workspace_id']}", headers=_auth(member_secret)).json()
    providers = {r["provider"] for r in listed["resources"]}
    assert {"GITHUB", "FIGMA", "NOTION"} <= providers

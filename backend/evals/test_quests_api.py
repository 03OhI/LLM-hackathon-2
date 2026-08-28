"""
퀘스트 API 통합 테스트 — FastAPI TestClient + 임시 SQLite 파일

세션 생성 → 참여자 3명 참여/유형 제출 → 분석 실행 → 팀 퀘스트 조회/완료(누구나),
개인 퀘스트 조회/완료(본인만) 흐름을 검증한다.

DATABASE_URL을 app.* 최초 import 이전에 설정해야 app.config.get_settings()
(lru_cache 싱글톤)가 임시 DB를 가리키게 된다. 테스트 종료 후 파일을 정리한다.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

BACKEND_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(BACKEND_ROOT))

_TMP_DB_FD, _TMP_DB_PATH = tempfile.mkstemp(prefix="test_quests_api_", suffix=".db")
os.close(_TMP_DB_FD)
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP_DB_PATH}"

import pytest
from fastapi.testclient import TestClient

from app.db import init_db
from app.main import app

client = TestClient(app)


@pytest.fixture(scope="module", autouse=True)
def _setup_and_teardown_db():
    init_db()
    yield
    try:
        os.remove(_TMP_DB_PATH)
    except OSError:
        pass


# ──────────────────────────────────────────────
# 헬퍼
# ──────────────────────────────────────────────


def _create_session(expected_member_count: int = 3) -> dict:
    resp = client.post(
        "/api/sessions",
        json={"name": "퀘스트 테스트팀", "expected_member_count": expected_member_count},
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
        headers={"Authorization": f"Bearer {secret}"},
    )
    assert resp.status_code == 200, resp.text


def _trigger_analysis(session_id: str, host_secret: str) -> None:
    resp = client.post(
        f"/api/sessions/{session_id}/analysis",
        headers={"Authorization": f"Bearer {host_secret}"},
    )
    assert resp.status_code == 200, resp.text


def _build_team() -> dict:
    """3인 팀: agency 균형(DRIVER+SUPPORTER), planning 다수 PLANNER 등 다양한 조합."""
    session = _create_session(expected_member_count=3)
    session_id = session["session_id"]
    host_secret = session["host_secret"]
    invite_token = session["invite_token"]

    p1_id, p1_secret = _join(invite_token, "지훈")
    p2_id, p2_secret = _join(invite_token, "서연")
    p3_id, p3_secret = _join(invite_token, "민준")

    _submit_type(
        p1_id, p1_secret,
        {"planning": "PLANNER", "agency": "DRIVER", "conflict": "HARMONIZER", "communication": "DIRECT"},
    )
    _submit_type(
        p2_id, p2_secret,
        {"planning": "PLANNER", "agency": "SUPPORTER", "conflict": "HARMONIZER", "communication": "TACTFUL"},
    )
    _submit_type(
        p3_id, p3_secret,
        {"planning": "ADAPTER", "agency": "SUPPORTER", "conflict": "CONFRONTER", "communication": "TACTFUL"},
    )

    _trigger_analysis(session_id, host_secret)

    return {
        "session_id": session_id,
        "host_secret": host_secret,
        "participants": [
            {"id": p1_id, "secret": p1_secret, "nickname": "지훈"},
            {"id": p2_id, "secret": p2_secret, "nickname": "서연"},
            {"id": p3_id, "secret": p3_secret, "nickname": "민준"},
        ],
    }


# ──────────────────────────────────────────────
# 팀 퀘스트
# ──────────────────────────────────────────────


def test_quests_before_analysis_returns_empty_not_error():
    session = _create_session(expected_member_count=3)
    resp = client.get(f"/api/sessions/{session['session_id']}/quests/team")
    assert resp.status_code == 200
    data = resp.json()
    assert data["quests"] == []
    assert data["total_count"] == 0


def test_team_quests_lazy_assignment_and_listing():
    team = _build_team()
    resp = client.get(f"/api/sessions/{team['session_id']}/quests/team")
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data["session_id"] == team["session_id"]
    assert 0 < data["total_count"] <= 3  # config 기본값 team_quest_count=3
    assert data["completed_count"] == 0
    for q in data["quests"]:
        assert q["scope"] == "TEAM"
        assert q["status"] == "ASSIGNED"
        assert q["title"]
        assert q["description"]
        assert q["action"]


def test_team_quest_assignment_is_cached_not_reassigned():
    team = _build_team()
    first = client.get(f"/api/sessions/{team['session_id']}/quests/team").json()
    second = client.get(f"/api/sessions/{team['session_id']}/quests/team").json()

    first_ids = sorted(q["quest_assignment_id"] for q in first["quests"])
    second_ids = sorted(q["quest_assignment_id"] for q in second["quests"])
    assert first_ids == second_ids


def test_any_participant_can_complete_team_quest():
    team = _build_team()
    listing = client.get(f"/api/sessions/{team['session_id']}/quests/team").json()
    quest_id = listing["quests"][0]["quest_assignment_id"]

    completer = team["participants"][1]  # 서연 — host도, 개인 배정 대상도 아닌 팀원
    resp = client.patch(
        f"/api/sessions/{team['session_id']}/quests/{quest_id}",
        json={"completed": True},
        headers={"Authorization": f"Bearer {completer['secret']}"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "COMPLETED"
    assert body["completed_by_nickname"] == "서연"

    listing_after = client.get(f"/api/sessions/{team['session_id']}/quests/team").json()
    assert listing_after["completed_count"] == 1


def test_completing_team_quest_without_auth_fails():
    team = _build_team()
    listing = client.get(f"/api/sessions/{team['session_id']}/quests/team").json()
    quest_id = listing["quests"][0]["quest_assignment_id"]

    resp = client.patch(f"/api/sessions/{team['session_id']}/quests/{quest_id}", json={"completed": True})
    assert resp.status_code == 401


def test_outsider_cannot_complete_team_quest_of_other_session():
    team_a = _build_team()
    team_b = _build_team()

    listing = client.get(f"/api/sessions/{team_a['session_id']}/quests/team").json()
    quest_id = listing["quests"][0]["quest_assignment_id"]

    outsider = team_b["participants"][0]
    resp = client.patch(
        f"/api/sessions/{team_a['session_id']}/quests/{quest_id}",
        json={"completed": True},
        headers={"Authorization": f"Bearer {outsider['secret']}"},
    )
    assert resp.status_code == 403


def test_team_quest_can_be_uncompleted():
    team = _build_team()
    listing = client.get(f"/api/sessions/{team['session_id']}/quests/team").json()
    quest_id = listing["quests"][0]["quest_assignment_id"]
    p1 = team["participants"][0]

    client.patch(
        f"/api/sessions/{team['session_id']}/quests/{quest_id}",
        json={"completed": True},
        headers={"Authorization": f"Bearer {p1['secret']}"},
    )
    resp = client.patch(
        f"/api/sessions/{team['session_id']}/quests/{quest_id}",
        json={"completed": False},
        headers={"Authorization": f"Bearer {p1['secret']}"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "ASSIGNED"
    assert body["completed_by_nickname"] is None


def test_completing_unknown_quest_id_returns_404():
    team = _build_team()
    p1 = team["participants"][0]
    resp = client.patch(
        f"/api/sessions/{team['session_id']}/quests/not-a-real-id",
        json={"completed": True},
        headers={"Authorization": f"Bearer {p1['secret']}"},
    )
    assert resp.status_code == 404


# ──────────────────────────────────────────────
# 개인 퀘스트
# ──────────────────────────────────────────────


def test_personal_quests_lazy_assignment_and_listing():
    team = _build_team()
    p1 = team["participants"][0]
    resp = client.get(
        f"/api/participants/{p1['id']}/quests",
        headers={"Authorization": f"Bearer {p1['secret']}"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data["participant_id"] == p1["id"]
    assert 0 < data["total_count"] <= 2  # config 기본값 personal_quest_count=2
    for q in data["quests"]:
        assert q["scope"] == "PERSONAL"


def test_personal_quest_completion_requires_self():
    team = _build_team()
    p1, p2 = team["participants"][0], team["participants"][1]

    listing = client.get(
        f"/api/participants/{p1['id']}/quests",
        headers={"Authorization": f"Bearer {p1['secret']}"},
    ).json()
    quest_id = listing["quests"][0]["quest_assignment_id"]

    # 다른 참여자가 p1의 개인 퀘스트를 완료 시도 -> 403
    resp = client.patch(
        f"/api/participants/{p1['id']}/quests/{quest_id}",
        json={"completed": True},
        headers={"Authorization": f"Bearer {p2['secret']}"},
    )
    assert resp.status_code == 403

    # 본인은 완료 가능
    resp = client.patch(
        f"/api/participants/{p1['id']}/quests/{quest_id}",
        json={"completed": True},
        headers={"Authorization": f"Bearer {p1['secret']}"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "COMPLETED"


def test_personal_quests_are_isolated_per_participant():
    team = _build_team()
    p1, p2 = team["participants"][0], team["participants"][1]

    p1_quests = client.get(
        f"/api/participants/{p1['id']}/quests",
        headers={"Authorization": f"Bearer {p1['secret']}"},
    ).json()["quests"]
    p2_quests = client.get(
        f"/api/participants/{p2['id']}/quests",
        headers={"Authorization": f"Bearer {p2['secret']}"},
    ).json()["quests"]

    p1_ids = {q["quest_assignment_id"] for q in p1_quests}
    p2_ids = {q["quest_assignment_id"] for q in p2_quests}
    assert p1_ids.isdisjoint(p2_ids)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

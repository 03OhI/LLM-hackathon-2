"""
프론트 통합 API/쿠키/CORS 테스트 — SPEC_V5 프론트 통합 보완

FastAPI TestClient + 임시 SQLite 파일. DATABASE_URL을 app.* 최초 import 이전에
설정해야 app.config.get_settings()(lru_cache 싱글톤)가 임시 DB를 가리키게 된다.

FRONTEND_ORIGINS도 app.config import 이전에 설정해야 CORSMiddleware가 이 값을
읽는다(main.py가 모듈 최초 import 시 settings를 한 번만 읽어 add_middleware에 넘긴다).
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

BACKEND_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(BACKEND_ROOT))

_TMP_DB_FD, _TMP_DB_PATH = tempfile.mkstemp(prefix="test_frontend_integration_v52_", suffix=".db")
os.close(_TMP_DB_FD)
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP_DB_PATH}"
os.environ["FRONTEND_ORIGINS"] = "https://app.example.com,https://admin.example.com"

import pytest
from fastapi.testclient import TestClient

from app.db import init_db
from app.main import app

client = TestClient(app)


@pytest.fixture(scope="module", autouse=True)
def _setup_and_teardown_db():
    init_db()
    yield
    # 의도적으로 파일을 삭제하지 않는다: app.db의 engine/settings는 프로세스 전체에서
    # lru_cache로 공유되는 싱글톤이라, pytest가 여러 evals/test_*.py 모듈을 한 세션에서
    # 함께 실행하면 "가장 먼저 app.db를 import한 모듈"의 DATABASE_URL만 실제로 적용되고
    # 이후 모듈들은 각자 만든 시크릿 파일 경로를 무시한 채 그 엔진을 공유해서 쓴다.
    # 그 상태에서 먼저 끝난 모듈이 파일을 지우면, 나중에 도는 다른 테스트 모듈까지
    # "unable to open database file"로 깨진다 — 그래서 여기서는 지우지 않는다
    # (OS 임시 디렉터리에 남는 파일 하나는 이 회귀보다 훨씬 싼 대가다).


# ──────────────────────────────────────────────
# 헬퍼 (test_quest_workspace_api.py와 동일 패턴)
# ──────────────────────────────────────────────

_TYPE_CYCLE = [
    {"planning": "PLANNER", "agency": "DRIVER", "conflict": "HARMONIZER", "communication": "DIRECT"},
    {"planning": "PLANNER", "agency": "SUPPORTER", "conflict": "HARMONIZER", "communication": "TACTFUL"},
    {"planning": "ADAPTER", "agency": "SUPPORTER", "conflict": "CONFRONTER", "communication": "DIRECT"},
]


def _auth(secret: str) -> dict:
    return {"Authorization": f"Bearer {secret}"}


def _create_session(expected_member_count: int = 3) -> dict:
    resp = client.post(
        "/api/sessions", json={"name": "프론트 통합 테스트팀", "expected_member_count": expected_member_count}
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


def build_team(team_size: int = 3) -> dict:
    session = _create_session(expected_member_count=team_size)
    session_id = session["session_id"]
    host_secret = session["host_secret"]
    invite_token = session["invite_token"]

    members = []
    for i in range(team_size):
        pid, psecret = _join(invite_token, f"멤버{i}")
        _submit_type(pid, psecret, _TYPE_CYCLE[i % len(_TYPE_CYCLE)])
        members.append((pid, psecret))

    return {"session_id": session_id, "host_secret": host_secret, "members": members}


def analyze(session_id: str, host_secret: str) -> None:
    resp = client.post(f"/api/sessions/{session_id}/analysis", headers=_auth(host_secret))
    assert resp.status_code == 200, resp.text


def assign_quest(session_id: str, host_secret: str) -> dict:
    resp = client.post(f"/api/rooms/{session_id}/quests/assign", headers=_auth(host_secret))
    assert resp.status_code == 200, resp.text
    return resp.json()


# ──────────────────────────────────────────────
# 1. 팀원 목록 API
# ──────────────────────────────────────────────


def test_list_participants_as_room_member():
    team = build_team(3)
    resp = client.get(
        f"/api/rooms/{team['session_id']}/participants", headers=_auth(team["members"][0][1])
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body) == 3
    assert {"participant_id", "nickname"} == set(body[0].keys())


def test_list_participants_as_host():
    team = build_team(3)
    resp = client.get(f"/api/rooms/{team['session_id']}/participants", headers=_auth(team["host_secret"]))
    assert resp.status_code == 200, resp.text
    assert len(resp.json()) == 3


def test_list_participants_cross_room_forbidden():
    team_a = build_team(3)
    team_b = build_team(3)

    resp = client.get(
        f"/api/rooms/{team_a['session_id']}/participants", headers=_auth(team_b["members"][0][1])
    )
    assert resp.status_code == 403

    resp = client.get(
        f"/api/rooms/{team_a['session_id']}/participants", headers=_auth(team_b["host_secret"])
    )
    assert resp.status_code == 403


def test_list_participants_no_credentials_unauthorized():
    team = build_team(3)
    # build_team()이 방금 호출한 POST /invites/{token}/participants의 Set-Cookie 응답이
    # 모듈 전역 client의 쿠키 저장소에 그대로 남아 있어(TestClient는 세션형 클라이언트다),
    # 그냥 client.get()을 호출하면 "자격 증명 없음"이 아니라 이 팀 참여자 본인의
    # participant_secret 쿠키를 자동으로 실어 보낸다 — 그러면 401이 아니라 200이 나와
    # 이 테스트가 실제로는 아무것도 검증하지 못한다. 이 요청에서만 쿠키를 비운다.
    client.cookies.clear()
    resp = client.get(f"/api/rooms/{team['session_id']}/participants")
    assert resp.status_code == 401


def test_list_participants_excludes_private_fields():
    team = build_team(3)
    resp = client.get(f"/api/rooms/{team['session_id']}/participants", headers=_auth(team["host_secret"]))
    body_text = resp.text
    forbidden = [
        "participant_secret",
        "secret_hash",
        "answers",
        "positions",
        "planning",
        "agency",
        "conflict",
        "communication",
        "internal_index",
        "team_grade",
        "insight",
    ]
    for token in forbidden:
        assert token not in body_text, f"참여자 목록 응답에 금지된 필드가 포함됨: {token}"


# ──────────────────────────────────────────────
# 2. 방 기준 워크스페이스 조회
# ──────────────────────────────────────────────


def test_room_workspace_locked_before_start():
    team = build_team(3)
    resp = client.get(f"/api/rooms/{team['session_id']}/workspace", headers=_auth(team["members"][0][1]))
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"workspace_id": None, "status": "LOCKED"}


def test_room_workspace_active_after_start():
    team = build_team(3)
    analyze(team["session_id"], team["host_secret"])
    assigned = assign_quest(team["session_id"], team["host_secret"])
    client.post(
        f"/api/quest-assignments/{assigned['assignment']['id']}/skip", headers=_auth(team["host_secret"])
    )
    started = client.post(
        f"/api/rooms/{team['session_id']}/workspace/start", headers=_auth(team["host_secret"])
    )
    assert started.status_code == 200

    resp = client.get(f"/api/rooms/{team['session_id']}/workspace", headers=_auth(team["members"][0][1]))
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ACTIVE"
    assert body["workspace_id"] == started.json()["id"]


def test_room_workspace_viewable_by_non_host_member():
    team = build_team(3)
    resp = client.get(f"/api/rooms/{team['session_id']}/workspace", headers=_auth(team["members"][1][1]))
    assert resp.status_code == 200


def test_room_workspace_cross_room_forbidden():
    team_a = build_team(3)
    team_b = build_team(3)
    resp = client.get(
        f"/api/rooms/{team_a['session_id']}/workspace", headers=_auth(team_b["members"][0][1])
    )
    assert resp.status_code == 403


def test_workspace_start_idempotent_via_room_endpoint():
    team = build_team(3)
    analyze(team["session_id"], team["host_secret"])
    assigned = assign_quest(team["session_id"], team["host_secret"])
    client.post(
        f"/api/quest-assignments/{assigned['assignment']['id']}/skip", headers=_auth(team["host_secret"])
    )

    first = client.post(f"/api/rooms/{team['session_id']}/workspace/start", headers=_auth(team["host_secret"]))
    second = client.post(f"/api/rooms/{team['session_id']}/workspace/start", headers=_auth(team["host_secret"]))
    assert first.status_code == 200 and second.status_code == 200
    assert first.json()["id"] == second.json()["id"]

    status_after = client.get(
        f"/api/rooms/{team['session_id']}/workspace", headers=_auth(team["host_secret"])
    ).json()
    assert status_after["workspace_id"] == first.json()["id"]
    assert status_after["status"] == "ACTIVE"


# ──────────────────────────────────────────────
# 3. 퀘스트 완료 요구사항 공개
# ──────────────────────────────────────────────


def test_current_quest_exposes_completion_requirements_split_by_scope():
    team = build_team(3)
    analyze(team["session_id"], team["host_secret"])
    assign_quest(team["session_id"], team["host_secret"])

    resp = client.get(f"/api/rooms/{team['session_id']}/quests/current", headers=_auth(team["host_secret"]))
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert "completion_requirements" in body
    reqs = body["completion_requirements"]
    assert set(reqs.keys()) == {"member_checks", "team_checks"}
    for check in reqs["member_checks"] + reqs["team_checks"]:
        assert set(check.keys()) == {"type", "min_count"}

    # 규칙 엔진 카탈로그 어떤 퀘스트가 배정되든, completion_condition.checks에 있던
    # 모든 체크가 scope에 맞게 정확히 한 번씩 분류되어 있어야 한다.
    from app.services.quests.catalog import get_quest_template

    template = get_quest_template(body["quest_id"])
    raw_checks = template.completion_condition["checks"]
    expected_member = {c["type"] for c in raw_checks if c.get("scope") == "PER_MEMBER"}
    expected_team = {c["type"] for c in raw_checks if c.get("scope") == "TEAM"}
    assert {c["type"] for c in reqs["member_checks"]} == expected_member
    assert {c["type"] for c in reqs["team_checks"]} == expected_team


def test_current_quest_response_regression_existing_fields_still_present():
    """기존 §9 회귀 — completion_requirements 추가가 기존 필드를 건드리지 않아야 한다."""
    team = build_team(3)
    analyze(team["session_id"], team["host_secret"])
    assign_quest(team["session_id"], team["host_secret"])

    resp = client.get(f"/api/rooms/{team['session_id']}/quests/current", headers=_auth(team["host_secret"]))
    body = resp.json()
    for field in (
        "quest_id",
        "title",
        "summary",
        "duration_minutes",
        "steps",
        "materials",
        "deliverable",
        "assignment",
        "my_response_status",
        "team_completion_status",
    ):
        assert field in body, f"기존 필드 {field}가 사라짐"
    assert set(body["assignment"].keys()) == {
        "id",
        "status",
        "assignment_source",
        "reason",
        "intro_message",
        "assigned_at",
        "started_at",
        "completed_at",
    }
    assert set(body["team_completion_status"].keys()) == {"satisfied", "unmet_check_types"}


# ──────────────────────────────────────────────
# 4. 쿠키 / CORS
# ──────────────────────────────────────────────


def _cors_test_client() -> TestClient:
    """app.main.app(프로세스 전역 싱글톤)의 CORS 설정은 pytest가 evals/의 어떤 모듈을
    먼저 import하느냐(FRONTEND_ORIGINS를 누가 먼저 읽어 lru_cache에 고정하느냐)에 따라
    달라질 수 있다. CORS 동작 자체는 main.py와 동일한 배선(allow_origins=명시적 목록,
    allow_credentials=True)을 쓰는 격리된 앱으로 검증해 실행 순서와 무관하게 만든다.
    """
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware

    isolated_app = FastAPI()
    isolated_app.add_middleware(
        CORSMiddleware,
        allow_origins=["https://app.example.com", "https://admin.example.com"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @isolated_app.post("/api/sessions")
    def _dummy() -> dict:
        return {"ok": True}

    return TestClient(isolated_app)


def test_allowed_origin_gets_cors_headers():
    resp = _cors_test_client().options(
        "/api/sessions",
        headers={
            "Origin": "https://app.example.com",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert resp.status_code in (200, 204)
    assert resp.headers.get("access-control-allow-origin") == "https://app.example.com"
    assert resp.headers.get("access-control-allow-credentials") == "true"


def test_disallowed_origin_blocked_by_cors():
    resp = _cors_test_client().options(
        "/api/sessions",
        headers={
            "Origin": "https://evil.example.com",
            "Access-Control-Request-Method": "POST",
        },
    )
    # starlette CORSMiddleware는 허용되지 않은 origin에 대해 별도 오류 상태 없이
    # 단순히 Access-Control-Allow-Origin 헤더를 붙이지 않는다 — 브라우저가 이 헤더
    # 부재를 보고 응답을 차단한다. 여기서는 헤더 부재로 "차단됨"을 검증한다.
    assert resp.headers.get("access-control-allow-origin") is None


def test_configured_app_uses_frontend_origins_setting():
    """app.main.app이 실제로 settings.frontend_origins를 CORSMiddleware에 넘기는지는
    (프로세스 전역 상태와 무관하게) 미들웨어 스택 구성 자체를 검사해 확인한다."""
    from starlette.middleware.cors import CORSMiddleware as StarletteCORSMiddleware

    from app.config import get_settings
    from app.main import app as configured_app

    cors_entry = next(
        m for m in configured_app.user_middleware if m.cls is StarletteCORSMiddleware
    )
    assert cors_entry.kwargs["allow_origins"] == get_settings().frontend_origins
    assert cors_entry.kwargs["allow_credentials"] is True
    assert "*" not in cors_entry.kwargs["allow_origins"]


def test_wildcard_origin_rejected_at_config_load():
    from pydantic import ValidationError

    from app.config import Settings

    with pytest.raises(ValidationError):
        Settings(frontend_origins=["*"])


def test_samesite_none_requires_secure():
    from pydantic import ValidationError

    from app.config import Settings

    with pytest.raises(ValidationError):
        Settings(cookie_samesite="none", cookie_secure=False)

    # secure=True와 함께면 허용된다.
    settings = Settings(cookie_samesite="none", cookie_secure=True)
    assert settings.cookie_samesite == "none"


def test_secret_cookies_are_httponly():
    resp = client.post("/api/sessions", json={"name": "쿠키 확인", "expected_member_count": 3})
    assert resp.status_code == 200
    set_cookie_headers = resp.headers.get_list("set-cookie")
    host_cookie = next(h for h in set_cookie_headers if h.startswith("host_secret="))
    assert "HttpOnly" in host_cookie

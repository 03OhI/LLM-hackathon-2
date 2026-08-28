"""
협업 워크스페이스 API — SPEC_V5_CONTEST_QUEST_AGENT.md §7, §8, §9 (P0)

POST   /api/rooms/{id}/workspace/start           — 방장, 멱등
GET    /api/workspaces/{id}                      — 같은 방 팀원/방장
POST   /api/workspaces/{id}/tasks                — 같은 방 팀원/방장
PATCH  /api/tasks/{id}                           — 같은 방 팀원/방장
DELETE /api/tasks/{id}                           — 작성자 또는 방장
POST   /api/workspaces/{id}/resources            — 같은 방 팀원/방장
DELETE /api/resources/{id}                       — 작성자 또는 방장
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlmodel import Session as DBSession

from app.auth import RoomActor, assert_host, identify_room_actor
from app.db import get_session
from app.errors import SESSION_NOT_FOUND, WORKSPACE_NOT_FOUND, app_error
from app.models import ResourceLink, Session as SessionModel, Workspace, WorkspaceTask
from app.services.workspace import service

router = APIRouter(tags=["workspace"])


# ──────────────────────────────────────────────
# 요청/응답 스키마
# ──────────────────────────────────────────────


class TaskCreateRequest(BaseModel):
    title: str
    assignee_participant_id: str | None = None
    due_at: datetime | None = None


class TaskUpdateRequest(BaseModel):
    title: str | None = None
    status: str | None = None
    assignee_participant_id: str | None = None
    clear_assignee: bool = False
    due_at: datetime | None = None
    clear_due_at: bool = False


class ResourceCreateRequest(BaseModel):
    title: str
    url: str
    provider: str


class TaskResponse(BaseModel):
    id: str
    title: str
    status: str
    assignee_participant_id: str | None
    due_at: datetime | None
    created_by: str
    created_at: datetime
    updated_at: datetime

    @staticmethod
    def from_model(t: WorkspaceTask) -> "TaskResponse":
        return TaskResponse(
            id=t.id,
            title=t.title,
            status=t.status,
            assignee_participant_id=t.assignee_participant_id,
            due_at=t.due_at,
            created_by=t.created_by,
            created_at=t.created_at,
            updated_at=t.updated_at,
        )


class ResourceResponse(BaseModel):
    id: str
    title: str
    url: str
    provider: str
    created_by: str
    created_at: datetime

    @staticmethod
    def from_model(r: ResourceLink) -> "ResourceResponse":
        return ResourceResponse(
            id=r.id, title=r.title, url=r.url, provider=r.provider, created_by=r.created_by, created_at=r.created_at
        )


class WorkspaceResponse(BaseModel):
    id: str
    session_id: str
    status: str
    started_at: datetime
    tasks: list[TaskResponse]
    resources: list[ResourceResponse]


# ──────────────────────────────────────────────
# 헬퍼
# ──────────────────────────────────────────────


def _actor_created_by(actor: RoomActor) -> str:
    return service.HOST_SENTINEL if actor.role == "HOST" else actor.participant.id


def _build_workspace_response(workspace: Workspace, db: DBSession) -> WorkspaceResponse:
    tasks = service.list_tasks(workspace.id, db)
    resources = service.list_resources(workspace.id, db)
    return WorkspaceResponse(
        id=workspace.id,
        session_id=workspace.session_id,
        status=workspace.status,
        started_at=workspace.started_at,
        tasks=[TaskResponse.from_model(t) for t in tasks],
        resources=[ResourceResponse.from_model(r) for r in resources],
    )


def _resolve_actor_for_workspace(workspace: Workspace, request: Request, db: DBSession) -> RoomActor:
    session = db.get(SessionModel, workspace.session_id)
    if session is None:
        raise app_error(SESSION_NOT_FOUND, "세션을 찾을 수 없습니다.")
    return identify_room_actor(session, request, db)


def _resolve_actor_for_task(task: WorkspaceTask, request: Request, db: DBSession) -> RoomActor:
    workspace = db.get(Workspace, task.workspace_id)
    if workspace is None:
        raise app_error(WORKSPACE_NOT_FOUND, "워크스페이스를 찾을 수 없습니다.")
    return _resolve_actor_for_workspace(workspace, request, db)


def _resolve_actor_for_resource(resource: ResourceLink, request: Request, db: DBSession) -> RoomActor:
    workspace = db.get(Workspace, resource.workspace_id)
    if workspace is None:
        raise app_error(WORKSPACE_NOT_FOUND, "워크스페이스를 찾을 수 없습니다.")
    return _resolve_actor_for_workspace(workspace, request, db)


# ──────────────────────────────────────────────
# 엔드포인트
# ──────────────────────────────────────────────


@router.post("/rooms/{session_id}/workspace/start", response_model=WorkspaceResponse)
def start_workspace(
    session_id: str,
    db: DBSession = Depends(get_session),
    session: SessionModel = Depends(assert_host),
) -> WorkspaceResponse:
    workspace = service.start_workspace(session_id, db)
    return _build_workspace_response(workspace, db)


@router.get("/workspaces/{workspace_id}", response_model=WorkspaceResponse)
def get_workspace(
    workspace_id: str,
    request: Request,
    db: DBSession = Depends(get_session),
) -> WorkspaceResponse:
    workspace = service.get_workspace_or_404(workspace_id, db)
    _resolve_actor_for_workspace(workspace, request, db)  # 같은 방 소속만 통과
    return _build_workspace_response(workspace, db)


@router.post("/workspaces/{workspace_id}/tasks", response_model=TaskResponse)
def create_task(
    workspace_id: str,
    body: TaskCreateRequest,
    request: Request,
    db: DBSession = Depends(get_session),
) -> TaskResponse:
    workspace = service.get_workspace_or_404(workspace_id, db)
    actor = _resolve_actor_for_workspace(workspace, request, db)
    task = service.create_task(
        workspace_id,
        db,
        title=body.title,
        created_by=_actor_created_by(actor),
        assignee_participant_id=body.assignee_participant_id,
        due_at=body.due_at,
    )
    return TaskResponse.from_model(task)


@router.patch("/tasks/{task_id}", response_model=TaskResponse)
def update_task(
    task_id: str,
    body: TaskUpdateRequest,
    request: Request,
    db: DBSession = Depends(get_session),
) -> TaskResponse:
    task = service.get_task_or_404(task_id, db)
    _resolve_actor_for_task(task, request, db)  # 같은 방 소속만 통과

    assignee = ... if not body.clear_assignee else None
    if body.assignee_participant_id is not None:
        assignee = body.assignee_participant_id
    due_at = ... if not body.clear_due_at else None
    if body.due_at is not None:
        due_at = body.due_at

    task = service.update_task(
        task_id, db, title=body.title, status=body.status, assignee_participant_id=assignee, due_at=due_at
    )
    return TaskResponse.from_model(task)


@router.delete("/tasks/{task_id}")
def delete_task(
    task_id: str,
    request: Request,
    db: DBSession = Depends(get_session),
) -> dict:
    task = service.get_task_or_404(task_id, db)
    actor = _resolve_actor_for_task(task, request, db)
    service.delete_task(
        task_id,
        db,
        actor_is_host=actor.role == "HOST",
        actor_participant_id=actor.participant.id if actor.participant else None,
    )
    return {"deleted": True}


@router.post("/workspaces/{workspace_id}/resources", response_model=ResourceResponse)
def create_resource(
    workspace_id: str,
    body: ResourceCreateRequest,
    request: Request,
    db: DBSession = Depends(get_session),
) -> ResourceResponse:
    workspace = service.get_workspace_or_404(workspace_id, db)
    actor = _resolve_actor_for_workspace(workspace, request, db)
    resource = service.create_resource(
        workspace_id,
        db,
        title=body.title,
        url=body.url,
        provider=body.provider,
        created_by=_actor_created_by(actor),
    )
    return ResourceResponse.from_model(resource)


@router.delete("/resources/{resource_id}")
def delete_resource(
    resource_id: str,
    request: Request,
    db: DBSession = Depends(get_session),
) -> dict:
    resource = service.get_resource_or_404(resource_id, db)
    actor = _resolve_actor_for_resource(resource, request, db)
    service.delete_resource(
        resource_id,
        db,
        actor_is_host=actor.role == "HOST",
        actor_participant_id=actor.participant.id if actor.participant else None,
    )
    return {"deleted": True}

"""
협업 워크스페이스 서비스 — SPEC_V5_CONTEST_QUEST_AGENT.md §6, §7, §8 (P0)

- start_workspace: 분석 완료 + 활성 퀘스트 종료 + 방장 요청일 때만 워크스페이스 생성, 멱등.
- 공동 할 일(WorkspaceTask): 생성/조회/수정/삭제, 삭제는 작성자 또는 방장.
- 공유 링크(ResourceLink): 등록/조회/삭제, 삭제는 작성자 또는 방장.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session as DBSession
from sqlmodel import select

from app.errors import (
    FORBIDDEN,
    RESOURCE_NOT_FOUND,
    TASK_NOT_FOUND,
    VALIDATION_ERROR,
    WORKSPACE_NOT_FOUND,
    WORKSPACE_NOT_READY,
    app_error,
)
from app.models import QuestAssignment, ResourceLink, Session as SessionModel, Workspace, WorkspaceTask, utcnow

HOST_SENTINEL = "HOST"

TASK_STATUSES = ("TODO", "IN_PROGRESS", "DONE")
RESOURCE_PROVIDERS = ("GITHUB", "FIGMA", "NOTION", "GOOGLE_DRIVE", "DEPLOYMENT", "OTHER")


def get_workspace_by_session(session_id: str, db: DBSession) -> Workspace | None:
    return db.exec(select(Workspace).where(Workspace.session_id == session_id)).first()


def start_workspace(session_id: str, db: DBSession) -> Workspace:
    """POST /rooms/{id}/workspace/start — 멱등.

    조건(§6): 팀 분석 완료 + 활성 퀘스트가 COMPLETED/SKIPPED로 종료.
    """
    existing = get_workspace_by_session(session_id, db)
    if existing is not None:
        return existing

    session = db.get(SessionModel, session_id)
    if session is None or session.status != "COMPLETED":
        raise app_error(WORKSPACE_NOT_READY, "팀 분석이 완료되어야 협업을 시작할 수 있습니다.")

    active_quest = db.exec(
        select(QuestAssignment).where(
            QuestAssignment.session_id == session_id,
            QuestAssignment.status.in_(("ASSIGNED", "IN_PROGRESS")),
        )
    ).first()
    if active_quest is not None:
        raise app_error(WORKSPACE_NOT_READY, "퀘스트를 완료하거나 건너뛴 후에 협업을 시작할 수 있습니다.")

    any_quest = db.exec(
        select(QuestAssignment).where(QuestAssignment.session_id == session_id)
    ).first()
    if any_quest is None:
        raise app_error(WORKSPACE_NOT_READY, "퀘스트가 배정된 적이 없습니다.")

    workspace = Workspace(id=str(uuid.uuid4()), session_id=session_id, status="ACTIVE")
    db.add(workspace)
    session.workspace_status = "ACTIVE"
    db.add(session)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = get_workspace_by_session(session_id, db)
        if existing is not None:
            return existing
        raise
    db.refresh(workspace)
    return workspace


def get_workspace_or_404(workspace_id: str, db: DBSession) -> Workspace:
    workspace = db.get(Workspace, workspace_id)
    if workspace is None:
        raise app_error(WORKSPACE_NOT_FOUND, f"워크스페이스를 찾을 수 없습니다: {workspace_id}")
    return workspace


def list_tasks(workspace_id: str, db: DBSession) -> list[WorkspaceTask]:
    return list(
        db.exec(select(WorkspaceTask).where(WorkspaceTask.workspace_id == workspace_id)).all()
    )


def list_resources(workspace_id: str, db: DBSession) -> list[ResourceLink]:
    return list(
        db.exec(select(ResourceLink).where(ResourceLink.workspace_id == workspace_id)).all()
    )


def create_task(
    workspace_id: str,
    db: DBSession,
    *,
    title: str,
    created_by: str,
    assignee_participant_id: str | None = None,
    due_at: datetime | None = None,
) -> WorkspaceTask:
    task = WorkspaceTask(
        id=str(uuid.uuid4()),
        workspace_id=workspace_id,
        title=title,
        status="TODO",
        assignee_participant_id=assignee_participant_id,
        due_at=due_at,
        created_by=created_by,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def get_task_or_404(task_id: str, db: DBSession) -> WorkspaceTask:
    task = db.get(WorkspaceTask, task_id)
    if task is None:
        raise app_error(TASK_NOT_FOUND, f"할 일을 찾을 수 없습니다: {task_id}")
    return task


def update_task(
    task_id: str,
    db: DBSession,
    *,
    title: str | None = None,
    status: str | None = None,
    assignee_participant_id: str | None = ...,
    due_at: datetime | None = ...,
) -> WorkspaceTask:
    task = get_task_or_404(task_id, db)
    if status is not None:
        if status not in TASK_STATUSES:
            raise app_error(VALIDATION_ERROR, f"허용되지 않은 상태: {status}")
        task.status = status
    if title is not None:
        task.title = title
    if assignee_participant_id is not ...:
        task.assignee_participant_id = assignee_participant_id
    if due_at is not ...:
        task.due_at = due_at
    task.updated_at = utcnow()
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def delete_task(task_id: str, db: DBSession, *, actor_is_host: bool, actor_participant_id: str | None) -> None:
    task = get_task_or_404(task_id, db)
    if not (actor_is_host or task.created_by == actor_participant_id):
        raise app_error(FORBIDDEN, "작성자 또는 방장만 삭제할 수 있습니다.")
    db.delete(task)
    db.commit()


def create_resource(
    workspace_id: str,
    db: DBSession,
    *,
    title: str,
    url: str,
    provider: str,
    created_by: str,
) -> ResourceLink:
    if provider not in RESOURCE_PROVIDERS:
        raise app_error(VALIDATION_ERROR, f"허용되지 않은 provider: {provider}")
    resource = ResourceLink(
        id=str(uuid.uuid4()),
        workspace_id=workspace_id,
        title=title,
        url=url,
        provider=provider,
        created_by=created_by,
    )
    db.add(resource)
    db.commit()
    db.refresh(resource)
    return resource


def get_resource_or_404(resource_id: str, db: DBSession) -> ResourceLink:
    resource = db.get(ResourceLink, resource_id)
    if resource is None:
        raise app_error(RESOURCE_NOT_FOUND, f"공유 링크를 찾을 수 없습니다: {resource_id}")
    return resource


def delete_resource(
    resource_id: str, db: DBSession, *, actor_is_host: bool, actor_participant_id: str | None
) -> None:
    resource = get_resource_or_404(resource_id, db)
    if not (actor_is_host or resource.created_by == actor_participant_id):
        raise app_error(FORBIDDEN, "작성자 또는 방장만 삭제할 수 있습니다.")
    db.delete(resource)
    db.commit()

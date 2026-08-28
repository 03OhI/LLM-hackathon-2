"""
협업 워크스페이스 API — SPEC_V5_CONTEST_QUEST_AGENT.md §7, §8, §9 (P0)
+ SPEC_V5.3 워크스페이스 도구 확장(공지/회의 메모/발표 체크리스트/의사결정 보드)

GET    /api/rooms/{id}/workspace                          — 같은 방 팀원/방장, polling용 경량 조회
POST   /api/rooms/{id}/workspace/start                    — 방장, 멱등
GET    /api/workspaces/{id}                                — 같은 방 팀원/방장
PATCH  /api/workspaces/{id}/notice                          — 방장만
POST   /api/workspaces/{id}/tasks                          — 같은 방 팀원/방장
PATCH  /api/tasks/{id}                                      — 같은 방 팀원/방장
DELETE /api/tasks/{id}                                      — 작성자 또는 방장
POST   /api/workspaces/{id}/resources                      — 같은 방 팀원/방장
DELETE /api/resources/{id}                                  — 작성자 또는 방장
GET    /api/workspaces/{id}/meeting-notes                   — 같은 방 팀원/방장
POST   /api/workspaces/{id}/meeting-notes                   — 같은 방 팀원/방장
PATCH  /api/meeting-notes/{id}                               — 작성자 또는 방장
DELETE /api/meeting-notes/{id}                               — 작성자 또는 방장
GET    /api/workspaces/{id}/presentation-checklist           — 같은 방 팀원/방장
POST   /api/workspaces/{id}/presentation-checklist           — 같은 방 팀원/방장
PATCH  /api/presentation-checklist/{id}                       — 같은 방 팀원/방장(완료 상태 포함)
DELETE /api/presentation-checklist/{id}                       — 작성자 또는 방장
GET    /api/workspaces/{id}/decisions                        — 같은 방 팀원/방장
POST   /api/workspaces/{id}/decisions                        — 같은 방 팀원/방장
POST   /api/decisions/{id}/vote                              — 같은 방 팀원만(방장은 투표 불가)
POST   /api/decisions/{id}/finalize                           — 방장만
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlmodel import Session as DBSession

from app.auth import RoomActor, assert_host, assert_room_member_strict, identify_room_actor, require_host_actor
from app.db import get_session
from app.errors import FORBIDDEN, SESSION_NOT_FOUND, WORKSPACE_NOT_FOUND, app_error
from app.models import (
    Decision,
    DecisionOption,
    MeetingNote,
    PresentationChecklistItem,
    ResourceLink,
    Session as SessionModel,
    Workspace,
    WorkspaceTask,
)
from app.services.workspace import checklist, decisions, meeting_notes, service

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


class NoticeUpdateRequest(BaseModel):
    notice: str | None
    deadline_at: datetime | None
    presentation_order: str | None


class NoticeResponse(BaseModel):
    notice: str | None
    deadline_at: datetime | None
    presentation_order: str | None


class MeetingNoteCreateRequest(BaseModel):
    title: str
    content: str
    next_action: str | None = None


class MeetingNoteUpdateRequest(BaseModel):
    title: str | None = None
    content: str | None = None
    next_action: str | None = None
    clear_next_action: bool = False


class ChecklistItemCreateRequest(BaseModel):
    item_type: str
    label: str
    url: str | None = None


class ChecklistItemUpdateRequest(BaseModel):
    label: str | None = None
    url: str | None = None
    clear_url: bool = False
    completed: bool | None = None


class DecisionCreateRequest(BaseModel):
    title: str
    description: str | None = None
    options: list[str]


class DecisionVoteRequest(BaseModel):
    option_id: str


class DecisionFinalizeRequest(BaseModel):
    final_result: str


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


class MeetingNoteResponse(BaseModel):
    id: str
    title: str
    content: str
    next_action: str | None
    created_by: str
    created_at: datetime
    updated_at: datetime

    @staticmethod
    def from_model(n: MeetingNote) -> "MeetingNoteResponse":
        return MeetingNoteResponse(
            id=n.id,
            title=n.title,
            content=n.content,
            next_action=n.next_action,
            created_by=n.created_by,
            created_at=n.created_at,
            updated_at=n.updated_at,
        )


class ChecklistItemResponse(BaseModel):
    id: str
    item_type: str
    label: str
    completed: bool
    url: str | None
    completed_by: str | None
    created_by: str
    created_at: datetime
    updated_at: datetime

    @staticmethod
    def from_model(i: PresentationChecklistItem) -> "ChecklistItemResponse":
        return ChecklistItemResponse(
            id=i.id,
            item_type=i.item_type,
            label=i.label,
            completed=i.completed,
            url=i.url,
            completed_by=i.completed_by,
            created_by=i.created_by,
            created_at=i.created_at,
            updated_at=i.updated_at,
        )


class DecisionOptionResponse(BaseModel):
    id: str
    label: str
    vote_count: int


class DecisionResponse(BaseModel):
    id: str
    title: str
    description: str | None
    status: str
    final_result: str | None
    created_by: str
    created_at: datetime
    finalized_at: datetime | None
    options: list[DecisionOptionResponse]
    my_vote_option_id: str | None

    @staticmethod
    def from_model(
        d: Decision, options: list[DecisionOption], counts: dict, my_vote: str | None
    ) -> "DecisionResponse":
        return DecisionResponse(
            id=d.id,
            title=d.title,
            description=d.description,
            status=d.status,
            final_result=d.final_result,
            created_by=d.created_by,
            created_at=d.created_at,
            finalized_at=d.finalized_at,
            options=[
                DecisionOptionResponse(id=o.id, label=o.label, vote_count=counts.get(o.id, 0)) for o in options
            ],
            my_vote_option_id=my_vote,
        )


class WorkspaceResponse(BaseModel):
    id: str
    session_id: str
    status: str
    started_at: datetime
    notice: str | None
    deadline_at: datetime | None
    presentation_order: str | None
    tasks: list[TaskResponse]
    resources: list[ResourceResponse]
    meeting_notes: list[MeetingNoteResponse]
    presentation_checklist: list[ChecklistItemResponse]
    decisions: list[DecisionResponse]


class RoomWorkspaceStatusResponse(BaseModel):
    """GET /rooms/{id}/workspace — polling 전용 경량 응답 (tasks/resources 미포함)."""

    workspace_id: str | None
    status: str  # LOCKED | ACTIVE


# ──────────────────────────────────────────────
# 헬퍼
# ──────────────────────────────────────────────


def _actor_created_by(actor: RoomActor) -> str:
    return service.HOST_SENTINEL if actor.role == "HOST" else actor.participant.id


def _actor_participant_id(actor: RoomActor) -> str | None:
    """방장은 participant 레코드가 없을 수 있어 None — 의사결정 투표 조회 등에 쓴다."""
    return actor.participant.id if actor.participant else None


def _build_decision_response(decision: Decision, db: DBSession, actor: RoomActor) -> DecisionResponse:
    options = decisions.list_options(decision.id, db)
    counts = decisions.vote_counts(decision.id, db)
    my_vote = decisions.my_vote_option_id(decision.id, _actor_participant_id(actor), db)
    return DecisionResponse.from_model(decision, options, counts, my_vote)


def _build_workspace_response(workspace: Workspace, db: DBSession, actor: RoomActor) -> WorkspaceResponse:
    tasks = service.list_tasks(workspace.id, db)
    resources = service.list_resources(workspace.id, db)
    notes = meeting_notes.list_notes(workspace.id, db)
    checklist_items = checklist.list_items(workspace.id, db)
    decision_rows = decisions.list_decisions(workspace.id, db)
    return WorkspaceResponse(
        id=workspace.id,
        session_id=workspace.session_id,
        status=workspace.status,
        started_at=workspace.started_at,
        notice=workspace.notice,
        deadline_at=workspace.deadline_at,
        presentation_order=workspace.presentation_order,
        tasks=[TaskResponse.from_model(t) for t in tasks],
        resources=[ResourceResponse.from_model(r) for r in resources],
        meeting_notes=[MeetingNoteResponse.from_model(n) for n in notes],
        presentation_checklist=[ChecklistItemResponse.from_model(i) for i in checklist_items],
        decisions=[_build_decision_response(d, db, actor) for d in decision_rows],
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


def _resolve_actor_for_note(note: MeetingNote, request: Request, db: DBSession) -> RoomActor:
    workspace = db.get(Workspace, note.workspace_id)
    if workspace is None:
        raise app_error(WORKSPACE_NOT_FOUND, "워크스페이스를 찾을 수 없습니다.")
    return _resolve_actor_for_workspace(workspace, request, db)


def _resolve_actor_for_checklist_item(item: PresentationChecklistItem, request: Request, db: DBSession) -> RoomActor:
    workspace = db.get(Workspace, item.workspace_id)
    if workspace is None:
        raise app_error(WORKSPACE_NOT_FOUND, "워크스페이스를 찾을 수 없습니다.")
    return _resolve_actor_for_workspace(workspace, request, db)


def _resolve_actor_for_decision(decision: Decision, request: Request, db: DBSession) -> RoomActor:
    workspace = db.get(Workspace, decision.workspace_id)
    if workspace is None:
        raise app_error(WORKSPACE_NOT_FOUND, "워크스페이스를 찾을 수 없습니다.")
    return _resolve_actor_for_workspace(workspace, request, db)


def _require_host_for_workspace(workspace: Workspace, request: Request, db: DBSession) -> None:
    session = db.get(SessionModel, workspace.session_id)
    if session is None:
        raise app_error(SESSION_NOT_FOUND, "세션을 찾을 수 없습니다.")
    require_host_actor(session, request)


# ──────────────────────────────────────────────
# 엔드포인트
# ──────────────────────────────────────────────


@router.get("/rooms/{session_id}/workspace", response_model=RoomWorkspaceStatusResponse)
def get_room_workspace_status(
    session_id: str,
    db: DBSession = Depends(get_session),
    _actor: RoomActor = Depends(assert_room_member_strict),
) -> RoomWorkspaceStatusResponse:
    """팀원이 3~5초 polling으로 협업 시작 여부만 가볍게 확인하는 용도.

    방장이 아니어도 같은 방 팀원이면 조회할 수 있다. 다른 방 사용자는 403(assert_room_member_strict).
    """
    workspace = service.get_workspace_by_session(session_id, db)
    if workspace is None:
        return RoomWorkspaceStatusResponse(workspace_id=None, status="LOCKED")
    return RoomWorkspaceStatusResponse(workspace_id=workspace.id, status=workspace.status)


@router.post("/rooms/{session_id}/workspace/start", response_model=WorkspaceResponse)
def start_workspace(
    session_id: str,
    db: DBSession = Depends(get_session),
    session: SessionModel = Depends(assert_host),
) -> WorkspaceResponse:
    workspace = service.start_workspace(session_id, db)
    host_actor = RoomActor(role="HOST", session=session, participant=None)
    return _build_workspace_response(workspace, db, host_actor)


@router.get("/workspaces/{workspace_id}", response_model=WorkspaceResponse)
def get_workspace(
    workspace_id: str,
    request: Request,
    db: DBSession = Depends(get_session),
) -> WorkspaceResponse:
    workspace = service.get_workspace_or_404(workspace_id, db)
    actor = _resolve_actor_for_workspace(workspace, request, db)  # 같은 방 소속만 통과
    return _build_workspace_response(workspace, db, actor)


@router.patch("/workspaces/{workspace_id}/notice", response_model=NoticeResponse)
def update_notice(
    workspace_id: str,
    body: NoticeUpdateRequest,
    request: Request,
    db: DBSession = Depends(get_session),
) -> NoticeResponse:
    """방장만 수정할 수 있다. 같은 방 팀원은 GET /workspaces/{id}로 조회한다."""
    workspace = service.get_workspace_or_404(workspace_id, db)
    _require_host_for_workspace(workspace, request, db)
    workspace = service.update_notice(
        workspace_id,
        db,
        notice=body.notice,
        deadline_at=body.deadline_at,
        presentation_order=body.presentation_order,
    )
    return NoticeResponse(
        notice=workspace.notice, deadline_at=workspace.deadline_at, presentation_order=workspace.presentation_order
    )


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


# ──────────────────────────────────────────────
# 회의 메모
# ──────────────────────────────────────────────


@router.get("/workspaces/{workspace_id}/meeting-notes", response_model=list[MeetingNoteResponse])
def list_meeting_notes(
    workspace_id: str,
    request: Request,
    db: DBSession = Depends(get_session),
) -> list[MeetingNoteResponse]:
    workspace = service.get_workspace_or_404(workspace_id, db)
    _resolve_actor_for_workspace(workspace, request, db)
    return [MeetingNoteResponse.from_model(n) for n in meeting_notes.list_notes(workspace_id, db)]


@router.post("/workspaces/{workspace_id}/meeting-notes", response_model=MeetingNoteResponse)
def create_meeting_note(
    workspace_id: str,
    body: MeetingNoteCreateRequest,
    request: Request,
    db: DBSession = Depends(get_session),
) -> MeetingNoteResponse:
    workspace = service.get_workspace_or_404(workspace_id, db)
    actor = _resolve_actor_for_workspace(workspace, request, db)
    note = meeting_notes.create_note(
        workspace_id,
        db,
        title=body.title,
        content=body.content,
        next_action=body.next_action,
        created_by=_actor_created_by(actor),
    )
    return MeetingNoteResponse.from_model(note)


@router.patch("/meeting-notes/{note_id}", response_model=MeetingNoteResponse)
def update_meeting_note(
    note_id: str,
    body: MeetingNoteUpdateRequest,
    request: Request,
    db: DBSession = Depends(get_session),
) -> MeetingNoteResponse:
    note = meeting_notes.get_note_or_404(note_id, db)
    actor = _resolve_actor_for_note(note, request, db)
    if body.clear_next_action:
        next_action_arg = None
    elif body.next_action is not None:
        next_action_arg = body.next_action
    else:
        next_action_arg = ...
    note = meeting_notes.update_note(
        note_id,
        db,
        actor_is_host=actor.role == "HOST",
        actor_participant_id=_actor_participant_id(actor),
        title=body.title,
        content=body.content,
        next_action=next_action_arg,
    )
    return MeetingNoteResponse.from_model(note)


@router.delete("/meeting-notes/{note_id}")
def delete_meeting_note(
    note_id: str,
    request: Request,
    db: DBSession = Depends(get_session),
) -> dict:
    note = meeting_notes.get_note_or_404(note_id, db)
    actor = _resolve_actor_for_note(note, request, db)
    meeting_notes.delete_note(
        note_id, db, actor_is_host=actor.role == "HOST", actor_participant_id=_actor_participant_id(actor)
    )
    return {"deleted": True}


# ──────────────────────────────────────────────
# 발표 준비 체크리스트
# ──────────────────────────────────────────────


@router.get("/workspaces/{workspace_id}/presentation-checklist", response_model=list[ChecklistItemResponse])
def list_checklist_items(
    workspace_id: str,
    request: Request,
    db: DBSession = Depends(get_session),
) -> list[ChecklistItemResponse]:
    workspace = service.get_workspace_or_404(workspace_id, db)
    _resolve_actor_for_workspace(workspace, request, db)
    return [ChecklistItemResponse.from_model(i) for i in checklist.list_items(workspace_id, db)]


@router.post("/workspaces/{workspace_id}/presentation-checklist", response_model=ChecklistItemResponse)
def create_checklist_item(
    workspace_id: str,
    body: ChecklistItemCreateRequest,
    request: Request,
    db: DBSession = Depends(get_session),
) -> ChecklistItemResponse:
    workspace = service.get_workspace_or_404(workspace_id, db)
    actor = _resolve_actor_for_workspace(workspace, request, db)
    item = checklist.create_item(
        workspace_id,
        db,
        item_type=body.item_type,
        label=body.label,
        url=body.url,
        created_by=_actor_created_by(actor),
    )
    return ChecklistItemResponse.from_model(item)


@router.patch("/presentation-checklist/{item_id}", response_model=ChecklistItemResponse)
def update_checklist_item(
    item_id: str,
    body: ChecklistItemUpdateRequest,
    request: Request,
    db: DBSession = Depends(get_session),
) -> ChecklistItemResponse:
    """완료 상태 변경은 같은 방 팀원 누구나 할 수 있다 — 삭제와 달리 작성자/방장으로 제한하지 않는다."""
    item = checklist.get_item_or_404(item_id, db)
    actor = _resolve_actor_for_checklist_item(item, request, db)
    url_arg = None if body.clear_url else (body.url if body.url is not None else ...)
    item = checklist.update_item(
        item_id,
        db,
        actor_created_by=_actor_created_by(actor),
        label=body.label,
        url=url_arg,
        completed=body.completed,
    )
    return ChecklistItemResponse.from_model(item)


@router.delete("/presentation-checklist/{item_id}")
def delete_checklist_item(
    item_id: str,
    request: Request,
    db: DBSession = Depends(get_session),
) -> dict:
    item = checklist.get_item_or_404(item_id, db)
    actor = _resolve_actor_for_checklist_item(item, request, db)
    checklist.delete_item(
        item_id, db, actor_is_host=actor.role == "HOST", actor_participant_id=_actor_participant_id(actor)
    )
    return {"deleted": True}


# ──────────────────────────────────────────────
# 빠른 의사결정 보드
# ──────────────────────────────────────────────


@router.get("/workspaces/{workspace_id}/decisions", response_model=list[DecisionResponse])
def list_decisions(
    workspace_id: str,
    request: Request,
    db: DBSession = Depends(get_session),
) -> list[DecisionResponse]:
    workspace = service.get_workspace_or_404(workspace_id, db)
    actor = _resolve_actor_for_workspace(workspace, request, db)
    return [_build_decision_response(d, db, actor) for d in decisions.list_decisions(workspace_id, db)]


@router.post("/workspaces/{workspace_id}/decisions", response_model=DecisionResponse)
def create_decision(
    workspace_id: str,
    body: DecisionCreateRequest,
    request: Request,
    db: DBSession = Depends(get_session),
) -> DecisionResponse:
    workspace = service.get_workspace_or_404(workspace_id, db)
    actor = _resolve_actor_for_workspace(workspace, request, db)
    decision = decisions.create_decision(
        workspace_id,
        db,
        title=body.title,
        description=body.description,
        options=body.options,
        created_by=_actor_created_by(actor),
    )
    return _build_decision_response(decision, db, actor)


@router.post("/decisions/{decision_id}/vote", response_model=DecisionResponse)
def vote_decision(
    decision_id: str,
    body: DecisionVoteRequest,
    request: Request,
    db: DBSession = Depends(get_session),
) -> DecisionResponse:
    """방장은 participant가 아니므로 투표할 수 없다(퀘스트 팀원 응답과 동일 정책)."""
    decision = decisions.get_decision_or_404(decision_id, db)
    actor = _resolve_actor_for_decision(decision, request, db)
    if actor.role != "MEMBER" or actor.participant is None:
        raise app_error(FORBIDDEN, "본인(팀원)만 투표할 수 있습니다.")
    decision = decisions.cast_vote(decision_id, db, participant_id=actor.participant.id, option_id=body.option_id)
    return _build_decision_response(decision, db, actor)


@router.post("/decisions/{decision_id}/finalize", response_model=DecisionResponse)
def finalize_decision(
    decision_id: str,
    body: DecisionFinalizeRequest,
    request: Request,
    db: DBSession = Depends(get_session),
) -> DecisionResponse:
    decision = decisions.get_decision_or_404(decision_id, db)
    actor = _resolve_actor_for_decision(decision, request, db)
    if actor.role != "HOST":
        raise app_error(FORBIDDEN, "방장만 최종 결과를 확정할 수 있습니다.")
    decision = decisions.finalize_decision(decision_id, db, final_result=body.final_result)
    return _build_decision_response(decision, db, actor)

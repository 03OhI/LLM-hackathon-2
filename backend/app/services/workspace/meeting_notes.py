"""
회의 메모 — SPEC_V5.3 §2

생성은 같은 방 팀원 누구나(호출부에서 방 소속만 검증), 수정·삭제는 작성자 또는 방장만 가능하다.
"""

from __future__ import annotations

import uuid

from sqlmodel import Session as DBSession
from sqlmodel import select

from app.errors import FORBIDDEN, MEETING_NOTE_NOT_FOUND, app_error
from app.models import MeetingNote, utcnow


def list_notes(workspace_id: str, db: DBSession) -> list[MeetingNote]:
    return list(db.exec(select(MeetingNote).where(MeetingNote.workspace_id == workspace_id)).all())


def create_note(
    workspace_id: str,
    db: DBSession,
    *,
    title: str,
    content: str,
    created_by: str,
    next_action: str | None = None,
) -> MeetingNote:
    note = MeetingNote(
        id=str(uuid.uuid4()),
        workspace_id=workspace_id,
        title=title,
        content=content,
        next_action=next_action,
        created_by=created_by,
    )
    db.add(note)
    db.commit()
    db.refresh(note)
    return note


def get_note_or_404(note_id: str, db: DBSession) -> MeetingNote:
    note = db.get(MeetingNote, note_id)
    if note is None:
        raise app_error(MEETING_NOTE_NOT_FOUND, f"회의 메모를 찾을 수 없습니다: {note_id}")
    return note


def update_note(
    note_id: str,
    db: DBSession,
    *,
    actor_is_host: bool,
    actor_participant_id: str | None,
    title: str | None = None,
    content: str | None = None,
    next_action: str | None = ...,
) -> MeetingNote:
    note = get_note_or_404(note_id, db)
    if not (actor_is_host or note.created_by == actor_participant_id):
        raise app_error(FORBIDDEN, "작성자 또는 방장만 수정할 수 있습니다.")
    if title is not None:
        note.title = title
    if content is not None:
        note.content = content
    if next_action is not ...:
        note.next_action = next_action
    note.updated_at = utcnow()
    db.add(note)
    db.commit()
    db.refresh(note)
    return note


def delete_note(note_id: str, db: DBSession, *, actor_is_host: bool, actor_participant_id: str | None) -> None:
    note = get_note_or_404(note_id, db)
    if not (actor_is_host or note.created_by == actor_participant_id):
        raise app_error(FORBIDDEN, "작성자 또는 방장만 삭제할 수 있습니다.")
    db.delete(note)
    db.commit()

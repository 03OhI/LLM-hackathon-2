"""
발표 준비 체크리스트 — SPEC_V5.3 §3

워크스페이스 생성 시 기본 4개 항목을 자동 생성한다(create_default_items).
완료 상태는 같은 방 팀원 누구나 바꿀 수 있고, 삭제는 작성자 또는 방장만 가능하다.
"""

from __future__ import annotations

import uuid

from sqlmodel import Session as DBSession
from sqlmodel import select

from app.errors import CHECKLIST_ITEM_NOT_FOUND, FORBIDDEN, VALIDATION_ERROR, app_error
from app.models import PresentationChecklistItem, utcnow

ITEM_TYPES = ("DEMO_URL", "SLIDES", "SCRIPT", "BACKUP", "CUSTOM")

_DEFAULT_ITEMS: tuple[tuple[str, str], ...] = (
    ("DEMO_URL", "시연 URL 확인"),
    ("SLIDES", "발표 자료 확인"),
    ("SCRIPT", "발표 대본 확인"),
    ("BACKUP", "백업 화면 확인"),
)


def create_default_items(workspace_id: str, db: DBSession) -> list[PresentationChecklistItem]:
    """워크스페이스가 처음 생성될 때만 호출한다(멱등 아님 — 호출부가 1회만 부르도록 보장)."""
    items = [
        PresentationChecklistItem(
            id=str(uuid.uuid4()),
            workspace_id=workspace_id,
            item_type=item_type,
            label=label,
        )
        for item_type, label in _DEFAULT_ITEMS
    ]
    db.add_all(items)
    db.commit()
    for item in items:
        db.refresh(item)
    return items


def list_items(workspace_id: str, db: DBSession) -> list[PresentationChecklistItem]:
    return list(
        db.exec(
            select(PresentationChecklistItem).where(PresentationChecklistItem.workspace_id == workspace_id)
        ).all()
    )


def ensure_default_items(workspace_id: str, db: DBSession) -> list[PresentationChecklistItem]:
    """조회 시점에 항목이 0개면 기본 4개를 채운다(배포 전 생성된 워크스페이스 보정용).

    확인 후 삽입(check-then-insert) 방식의 최소한의 방어다 — 이미 하나라도 있으면
    절대 다시 만들지 않으므로, 정상적인 순차 요청에서는 중복이 생기지 않는다.
    완전한 동시성 보장이 필요하면 DB 유니크 제약이 필요하지만(CUSTOM 항목은 여러 개
    허용해야 해서 단순 유니크 제약을 걸 수 없다), 해커톤 데모 규모에서는 이 정도로 충분하다.
    """
    existing = list_items(workspace_id, db)
    if existing:
        return existing
    return create_default_items(workspace_id, db)


def create_item(
    workspace_id: str,
    db: DBSession,
    *,
    item_type: str,
    label: str,
    created_by: str,
    url: str | None = None,
) -> PresentationChecklistItem:
    if item_type not in ITEM_TYPES:
        raise app_error(VALIDATION_ERROR, f"허용되지 않은 item_type: {item_type}")
    item = PresentationChecklistItem(
        id=str(uuid.uuid4()),
        workspace_id=workspace_id,
        item_type=item_type,
        label=label,
        url=url,
        created_by=created_by,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def get_item_or_404(item_id: str, db: DBSession) -> PresentationChecklistItem:
    item = db.get(PresentationChecklistItem, item_id)
    if item is None:
        raise app_error(CHECKLIST_ITEM_NOT_FOUND, f"체크리스트 항목을 찾을 수 없습니다: {item_id}")
    return item


def update_item(
    item_id: str,
    db: DBSession,
    *,
    actor_created_by: str,
    label: str | None = None,
    url: str | None = ...,
    completed: bool | None = None,
) -> PresentationChecklistItem:
    """label/url/completed — 완료 상태 변경은 같은 방 팀원 누구나 가능하다(호출부에서 방 소속만 검증)."""
    item = get_item_or_404(item_id, db)
    if label is not None:
        item.label = label
    if url is not ...:
        item.url = url
    if completed is not None:
        item.completed = completed
        item.completed_by = actor_created_by if completed else None
    item.updated_at = utcnow()
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def delete_item(item_id: str, db: DBSession, *, actor_is_host: bool, actor_participant_id: str | None) -> None:
    item = get_item_or_404(item_id, db)
    if not (actor_is_host or item.created_by == actor_participant_id):
        raise app_error(FORBIDDEN, "작성자 또는 방장만 삭제할 수 있습니다.")
    db.delete(item)
    db.commit()

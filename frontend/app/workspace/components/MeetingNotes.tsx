"use client";

// 회의 메모 — 최신순, 긴 내용은 접기/펼치기.

import { useState } from "react";

import type { MeetingNote } from "@/lib/workspace-tools-api";

const COLLAPSE_THRESHOLD = 120;

export function MeetingNotes({
  notes,
  pendingAction,
  canManage,
  error,
  onCreate,
  onUpdate,
  onDelete,
}: {
  notes: MeetingNote[];
  pendingAction: string | null;
  canManage: (createdBy: string) => boolean;
  error?: string | null;
  onCreate: (input: { title: string; content: string; next_action: string | null }) => void;
  onUpdate: (noteId: string, input: { title: string; content: string; next_action: string | null }) => void;
  onDelete: (noteId: string) => void;
}) {
  const [creating, setCreating] = useState(false);
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [nextAction, setNextAction] = useState("");

  const sorted = [...notes].sort((a, b) => (a.created_at < b.created_at ? 1 : -1));

  const resetForm = () => {
    setTitle("");
    setContent("");
    setNextAction("");
    setCreating(false);
  };

  return (
    <div className="workspace-panel" aria-label="회의 메모">
      <h2>회의 메모</h2>

      {creating ? (
        <form
          className="workspace-note-form"
          onSubmit={(event) => {
            event.preventDefault();
            if (!title.trim()) return;
            onCreate({
              title: title.trim(),
              content: content.trim(),
              next_action: nextAction.trim() ? nextAction.trim() : null,
            });
            resetForm();
          }}
        >
          <input value={title} onChange={(event) => setTitle(event.target.value)} placeholder="제목" aria-label="메모 제목" />
          <textarea
            value={content}
            onChange={(event) => setContent(event.target.value)}
            placeholder="논의 내용"
            aria-label="논의 내용"
            rows={3}
          />
          <textarea
            value={nextAction}
            onChange={(event) => setNextAction(event.target.value)}
            placeholder="다음 행동"
            aria-label="다음 행동"
            rows={2}
          />
          <div className="workspace-notice-form-actions">
            <button type="submit" className="button-next" disabled={pendingAction === "create-note" || !title.trim()}>
              저장
            </button>
            <button type="button" className="button-muted" onClick={resetForm}>
              취소
            </button>
          </div>
        </form>
      ) : (
        <button type="button" className="button-muted" onClick={() => setCreating(true)}>
          새 회의 메모 추가
        </button>
      )}

      {sorted.length === 0 ? (
        <p className="workspace-empty">아직 등록된 메모가 없어요.</p>
      ) : (
        <ul className="workspace-note-list">
          {sorted.map((note) => (
            <MeetingNoteItem
              key={note.id}
              note={note}
              pendingAction={pendingAction}
              canManage={canManage(note.created_by)}
              onUpdate={onUpdate}
              onDelete={onDelete}
            />
          ))}
        </ul>
      )}
      {error && <p className="workspace-section-inline-error">{error}</p>}
    </div>
  );
}

function MeetingNoteItem({
  note,
  pendingAction,
  canManage,
  onUpdate,
  onDelete,
}: {
  note: MeetingNote;
  pendingAction: string | null;
  canManage: boolean;
  onUpdate: (noteId: string, input: { title: string; content: string; next_action: string | null }) => void;
  onDelete: (noteId: string) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const [title, setTitle] = useState(note.title);
  const [content, setContent] = useState(note.content);
  const [nextAction, setNextAction] = useState(note.next_action ?? "");

  const isLong = note.content.length > COLLAPSE_THRESHOLD;
  const shownContent = isLong && !expanded ? `${note.content.slice(0, COLLAPSE_THRESHOLD)}…` : note.content;

  if (editing) {
    return (
      <li className="workspace-note-item">
        <form
          className="workspace-note-form"
          onSubmit={(event) => {
            event.preventDefault();
            onUpdate(note.id, {
              title: title.trim(),
              content: content.trim(),
              next_action: nextAction.trim() ? nextAction.trim() : null,
            });
            setEditing(false);
          }}
        >
          <input value={title} onChange={(event) => setTitle(event.target.value)} aria-label="메모 제목 수정" />
          <textarea value={content} onChange={(event) => setContent(event.target.value)} aria-label="논의 내용 수정" rows={3} />
          <textarea value={nextAction} onChange={(event) => setNextAction(event.target.value)} aria-label="다음 행동 수정" rows={2} />
          <div className="workspace-notice-form-actions">
            <button type="submit" className="button-next" disabled={pendingAction === `update-note-${note.id}`}>
              저장
            </button>
            <button type="button" className="button-muted" onClick={() => setEditing(false)}>
              취소
            </button>
          </div>
        </form>
      </li>
    );
  }

  return (
    <li className="workspace-note-item">
      <div className="workspace-note-item-header">
        <b>{note.title}</b>
        {canManage && (
          <div className="workspace-note-item-actions">
            <button type="button" className="button-muted" onClick={() => setEditing(true)}>
              수정
            </button>
            <button
              type="button"
              className="task-delete-button"
              disabled={pendingAction === `delete-note-${note.id}`}
              onClick={() => onDelete(note.id)}
              aria-label={`${note.title} 삭제`}
            >
              삭제
            </button>
          </div>
        )}
      </div>
      {note.content && (
        <p className="workspace-note-discussion">
          {shownContent}
          {isLong && (
            <button type="button" className="workspace-note-toggle" onClick={() => setExpanded((v) => !v)}>
              {expanded ? "접기" : "더보기"}
            </button>
          )}
        </p>
      )}
      {note.next_action && <p className="workspace-note-next-actions">다음 행동: {note.next_action}</p>}
    </li>
  );
}

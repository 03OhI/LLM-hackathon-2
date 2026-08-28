"use client";

// 발표 준비 체크리스트.
// 완료 상태 변경은 같은 방 팀원 누구나 할 수 있다(백엔드 정책). 삭제만 작성자/방장으로 제한한다
// (기본 4개 항목은 워크스페이스를 시작한 방장 소유로 취급된다).

import { useState } from "react";

import type { ChecklistItemType, PresentationChecklistItem } from "@/lib/workspace-tools-api";

export const DEFAULT_CHECKLIST_LABELS = ["시연 URL 확인", "발표 자료 확인", "발표 대본 확인", "백업 화면 확인"];

export function PresentationChecklist({
  items,
  pendingAction,
  canManage,
  error,
  onToggle,
  onUrlChange,
  onAdd,
  onDelete,
}: {
  items: PresentationChecklistItem[];
  pendingAction: string | null;
  canManage: (createdBy: string) => boolean;
  error?: string | null;
  onToggle: (itemId: string, completed: boolean) => void;
  onUrlChange: (itemId: string, url: string) => void;
  onAdd: (label: string, itemType: ChecklistItemType) => void;
  onDelete: (itemId: string) => void;
}) {
  const [newLabel, setNewLabel] = useState("");
  const doneCount = items.filter((item) => item.completed).length;
  const progress = items.length === 0 ? 0 : Math.round((doneCount / items.length) * 100);

  return (
    <div className="workspace-panel" aria-label="발표 준비 체크리스트">
      <h2>발표 준비 체크리스트</h2>
      <div className="workspace-checklist-progress">
        <span>
          {doneCount}/{items.length}개 완료
        </span>
        <div className="workspace-progress-bar" role="progressbar" aria-valuenow={progress} aria-valuemin={0} aria-valuemax={100}>
          <div className="workspace-progress-fill" style={{ width: `${progress}%` }} />
        </div>
      </div>

      {items.length === 0 ? (
        <p className="workspace-empty">아직 등록된 항목이 없어요.</p>
      ) : (
        <ul className="workspace-checklist-list">
          {items.map((item) => (
            <li
              key={item.id}
              data-type={item.item_type}
              className={item.completed ? "quest-check-row quest-check-done" : "quest-check-row"}
            >
              <label className="workspace-checklist-label">
                <input
                  type="checkbox"
                  checked={item.completed}
                  disabled={pendingAction === `toggle-checklist-${item.id}`}
                  onChange={(event) => onToggle(item.id, event.target.checked)}
                />
                <span className={item.completed ? "workspace-checklist-done-text" : undefined}>{item.label}</span>
              </label>
              <input
                className="workspace-checklist-url"
                placeholder="관련 URL"
                defaultValue={item.url ?? ""}
                aria-label={`${item.label} URL`}
                onBlur={(event) => {
                  const value = event.target.value.trim();
                  if (value !== (item.url ?? "")) onUrlChange(item.id, value);
                }}
              />
              {canManage(item.created_by) && (
                <button
                  type="button"
                  className="task-delete-button"
                  disabled={pendingAction === `delete-checklist-${item.id}`}
                  onClick={() => onDelete(item.id)}
                  aria-label={`${item.label} 삭제`}
                >
                  삭제
                </button>
              )}
            </li>
          ))}
        </ul>
      )}

      <form
        className="workspace-checklist-add-form"
        onSubmit={(event) => {
          event.preventDefault();
          if (!newLabel.trim()) return;
          onAdd(newLabel.trim(), "CUSTOM");
          setNewLabel("");
        }}
      >
        <input
          value={newLabel}
          onChange={(event) => setNewLabel(event.target.value)}
          placeholder="새 항목 추가"
          aria-label="새 체크리스트 항목"
        />
        <button type="submit" className="button-muted" disabled={pendingAction === "create-checklist-item" || !newLabel.trim()}>
          항목 추가
        </button>
      </form>
      {error && <p className="workspace-section-inline-error">{error}</p>}
    </div>
  );
}

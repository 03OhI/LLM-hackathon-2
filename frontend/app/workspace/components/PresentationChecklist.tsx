"use client";

// 발표 준비 체크리스트.

import { useState } from "react";

import type { PresentationChecklistItem } from "@/lib/workspace-tools-api";

export const DEFAULT_CHECKLIST_LABELS = ["시연 URL", "발표 자료", "발표 대본", "백업 화면"];

export function PresentationChecklist({
  items,
  pendingAction,
  onToggle,
  onUrlChange,
  onAdd,
  onDelete,
}: {
  items: PresentationChecklistItem[];
  pendingAction: string | null;
  onToggle: (itemId: string, checked: boolean) => void;
  onUrlChange: (itemId: string, url: string) => void;
  onAdd: (label: string) => void;
  onDelete: (itemId: string) => void;
}) {
  const [newLabel, setNewLabel] = useState("");
  const doneCount = items.filter((item) => item.is_checked).length;
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
              className={item.is_checked ? "quest-check-row quest-check-done" : "quest-check-row"}
            >
              <label className="workspace-checklist-label">
                <input
                  type="checkbox"
                  checked={item.is_checked}
                  disabled={pendingAction === `toggle-checklist-${item.id}`}
                  onChange={(event) => onToggle(item.id, event.target.checked)}
                />
                <span className={item.is_checked ? "workspace-checklist-done-text" : undefined}>{item.label}</span>
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
              <button
                type="button"
                className="task-delete-button"
                onClick={() => onDelete(item.id)}
                aria-label={`${item.label} 삭제`}
              >
                삭제
              </button>
            </li>
          ))}
        </ul>
      )}

      <form
        className="workspace-checklist-add-form"
        onSubmit={(event) => {
          event.preventDefault();
          if (!newLabel.trim()) return;
          onAdd(newLabel.trim());
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
    </div>
  );
}

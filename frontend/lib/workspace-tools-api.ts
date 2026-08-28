// 협업 대시보드 확장 기능(공지/체크리스트/의사결정/회의메모) API 클라이언트.
//
// backend/app/api/workspace.py를 정본으로 한다. 공지는 별도 GET이 없다 —
// 조회는 getWorkspace()가 돌려주는 Workspace.notice/deadline_at/presentation_order를
// 쓰고, 이 파일은 PATCH(수정, 방장 전용)만 내보낸다.

import { requestJson } from "./api";

// ──────────────────────────────────────────────
// 1. 상단 고정 공지 — 조회는 workspace-api.ts의 Workspace 타입/GET을 그대로 쓴다.
// ──────────────────────────────────────────────

export type WorkspaceNotice = {
  notice: string | null;
  deadline_at: string | null;
  presentation_order: string | null;
};

// 방장 전용.
export function updateNotice(
  workspaceId: string,
  input: { notice: string | null; deadline_at: string | null; presentation_order: string | null },
): Promise<WorkspaceNotice> {
  return requestJson(`/workspaces/${encodeURIComponent(workspaceId)}/notice`, {
    method: "PATCH",
    body: JSON.stringify(input),
  });
}

// ──────────────────────────────────────────────
// 2. 회의 메모
// ──────────────────────────────────────────────

export type MeetingNote = {
  id: string;
  title: string;
  content: string;
  next_action: string | null;
  created_by: string;
  created_at: string;
  updated_at: string;
};

export function getMeetingNotes(workspaceId: string): Promise<MeetingNote[]> {
  return requestJson(`/workspaces/${encodeURIComponent(workspaceId)}/meeting-notes`);
}

export function createMeetingNote(
  workspaceId: string,
  input: { title: string; content: string; next_action?: string | null },
): Promise<MeetingNote> {
  return requestJson(`/workspaces/${encodeURIComponent(workspaceId)}/meeting-notes`, {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function updateMeetingNote(
  noteId: string,
  input: { title?: string; content?: string; next_action?: string | null; clear_next_action?: boolean },
): Promise<MeetingNote> {
  return requestJson(`/meeting-notes/${encodeURIComponent(noteId)}`, {
    method: "PATCH",
    body: JSON.stringify(input),
  });
}

export function deleteMeetingNote(noteId: string): Promise<{ deleted: boolean }> {
  return requestJson(`/meeting-notes/${encodeURIComponent(noteId)}`, { method: "DELETE" });
}

// ──────────────────────────────────────────────
// 3. 발표 준비 체크리스트
// ──────────────────────────────────────────────

export type ChecklistItemType = "DEMO_URL" | "SLIDES" | "SCRIPT" | "BACKUP" | "CUSTOM";

export type PresentationChecklistItem = {
  id: string;
  item_type: ChecklistItemType;
  label: string;
  completed: boolean;
  url: string | null;
  completed_by: string | null;
  created_by: string;
  created_at: string;
  updated_at: string;
};

export function getPresentationChecklist(workspaceId: string): Promise<PresentationChecklistItem[]> {
  return requestJson(`/workspaces/${encodeURIComponent(workspaceId)}/presentation-checklist`);
}

export function createPresentationChecklistItem(
  workspaceId: string,
  input: { item_type: ChecklistItemType; label: string; url?: string | null },
): Promise<PresentationChecklistItem> {
  return requestJson(`/workspaces/${encodeURIComponent(workspaceId)}/presentation-checklist`, {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function updatePresentationChecklistItem(
  itemId: string,
  input: { label?: string; url?: string | null; clear_url?: boolean; completed?: boolean },
): Promise<PresentationChecklistItem> {
  return requestJson(`/presentation-checklist/${encodeURIComponent(itemId)}`, {
    method: "PATCH",
    body: JSON.stringify(input),
  });
}

export function deletePresentationChecklistItem(itemId: string): Promise<{ deleted: boolean }> {
  return requestJson(`/presentation-checklist/${encodeURIComponent(itemId)}`, { method: "DELETE" });
}

// ──────────────────────────────────────────────
// 4. 빠른 의사결정 보드
// ──────────────────────────────────────────────

export type DecisionOption = {
  id: string;
  label: string;
  vote_count: number;
};

export type Decision = {
  id: string;
  title: string;
  description: string | null;
  status: "OPEN" | "FINALIZED";
  final_result: string | null;
  created_by: string;
  created_at: string;
  finalized_at: string | null;
  options: DecisionOption[];
  my_vote_option_id: string | null;
};

export function getDecisions(workspaceId: string): Promise<Decision[]> {
  return requestJson(`/workspaces/${encodeURIComponent(workspaceId)}/decisions`);
}

export function createDecision(
  workspaceId: string,
  input: { title: string; description?: string | null; options: string[] },
): Promise<Decision> {
  return requestJson(`/workspaces/${encodeURIComponent(workspaceId)}/decisions`, {
    method: "POST",
    body: JSON.stringify(input),
  });
}

// 방장은 participant 레코드가 없어 투표할 수 없다(백엔드 정책 — 403).
export function voteDecision(decisionId: string, optionId: string): Promise<Decision> {
  return requestJson(`/decisions/${encodeURIComponent(decisionId)}/vote`, {
    method: "POST",
    body: JSON.stringify({ option_id: optionId }),
  });
}

// 방장 전용. finalResult는 확정할 선택지의 label 문자열이다(option_id가 아니다).
export function finalizeDecision(decisionId: string, finalResult: string): Promise<Decision> {
  return requestJson(`/decisions/${encodeURIComponent(decisionId)}/finalize`, {
    method: "POST",
    body: JSON.stringify({ final_result: finalResult }),
  });
}

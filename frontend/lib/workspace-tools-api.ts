// 협업 대시보드 확장 기능(공지/체크리스트/의사결정/회의메모) API 클라이언트.
//
// 백엔드가 아직 병합되지 않았으므로, 이 파일의 엔드포인트는 workspace-api.ts의
// 기존 관례(REST, workspace_id 하위 리소스 + 개별 리소스는 최상위 경로)를 그대로
// 따른 "합의(가정)" 계약이다. 요청서에 명시된 것은 PATCH /workspaces/{id}/notice
// 뿐이지만, 최초 진입 시 조회할 방법이 필요해 같은 관례로 GET을 함께 추가했다
// (workspace.tasks/resources처럼 Workspace 응답에 포함시키지 않고 별도 엔드포인트로
// 분리한 이유: 이 리소스들은 workspace 조회 폴링과 갱신 빈도가 달라 워크스페이스
// 폴링 페이로드를 불필요하게 키우지 않기 위함).
//
// 실제 백엔드 병합 시 경로/필드가 달라지면 이 파일만 맞추면 된다 — 컴포넌트는
// 이 모듈이 내보내는 타입/함수에만 의존한다.

import { requestJson } from "./api";

// ──────────────────────────────────────────────
// 1. 고정 공지
// ──────────────────────────────────────────────

export type WorkspaceNotice = {
  content: string;
  deadline_at: string | null;
  presentation_order: number | null;
  updated_at: string | null;
};

export function getNotice(workspaceId: string): Promise<WorkspaceNotice> {
  return requestJson(`/workspaces/${encodeURIComponent(workspaceId)}/notice`);
}

export function updateNotice(
  workspaceId: string,
  input: { content: string; deadline_at: string | null; presentation_order: number | null },
): Promise<WorkspaceNotice> {
  return requestJson(`/workspaces/${encodeURIComponent(workspaceId)}/notice`, {
    method: "PATCH",
    body: JSON.stringify(input),
  });
}

// ──────────────────────────────────────────────
// 3. 발표 준비 체크리스트
// ──────────────────────────────────────────────

export type PresentationChecklistItem = {
  id: string;
  label: string;
  url: string | null;
  is_checked: boolean;
  created_by: string;
  created_at: string;
};

export function getPresentationChecklist(workspaceId: string): Promise<PresentationChecklistItem[]> {
  return requestJson(`/workspaces/${encodeURIComponent(workspaceId)}/presentation-checklist`);
}

export function createPresentationChecklistItem(
  workspaceId: string,
  input: { label: string; url?: string | null },
): Promise<PresentationChecklistItem> {
  return requestJson(`/workspaces/${encodeURIComponent(workspaceId)}/presentation-checklist`, {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function updatePresentationChecklistItem(
  itemId: string,
  input: { label?: string; url?: string | null; is_checked?: boolean },
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
  description: string;
  options: DecisionOption[];
  status: "OPEN" | "FINALIZED";
  finalized_option_id: string | null;
  my_vote_option_id: string | null;
  created_by: string;
  created_at: string;
};

export function getDecisions(workspaceId: string): Promise<Decision[]> {
  return requestJson(`/workspaces/${encodeURIComponent(workspaceId)}/decisions`);
}

export function createDecision(
  workspaceId: string,
  input: { title: string; description: string; options: string[] },
): Promise<Decision> {
  return requestJson(`/workspaces/${encodeURIComponent(workspaceId)}/decisions`, {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function voteDecision(decisionId: string, optionId: string): Promise<Decision> {
  return requestJson(`/decisions/${encodeURIComponent(decisionId)}/vote`, {
    method: "POST",
    body: JSON.stringify({ option_id: optionId }),
  });
}

export function finalizeDecision(decisionId: string, optionId: string): Promise<Decision> {
  return requestJson(`/decisions/${encodeURIComponent(decisionId)}/finalize`, {
    method: "POST",
    body: JSON.stringify({ option_id: optionId }),
  });
}

// ──────────────────────────────────────────────
// 5. 회의 메모
// ──────────────────────────────────────────────

export type MeetingNote = {
  id: string;
  title: string;
  discussion: string;
  next_actions: string;
  created_by: string;
  created_at: string;
  updated_at: string;
};

export function getMeetingNotes(workspaceId: string): Promise<MeetingNote[]> {
  return requestJson(`/workspaces/${encodeURIComponent(workspaceId)}/meeting-notes`);
}

export function createMeetingNote(
  workspaceId: string,
  input: { title: string; discussion: string; next_actions: string },
): Promise<MeetingNote> {
  return requestJson(`/workspaces/${encodeURIComponent(workspaceId)}/meeting-notes`, {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function updateMeetingNote(
  noteId: string,
  input: { title?: string; discussion?: string; next_actions?: string },
): Promise<MeetingNote> {
  return requestJson(`/meeting-notes/${encodeURIComponent(noteId)}`, {
    method: "PATCH",
    body: JSON.stringify(input),
  });
}

export function deleteMeetingNote(noteId: string): Promise<{ deleted: boolean }> {
  return requestJson(`/meeting-notes/${encodeURIComponent(noteId)}`, { method: "DELETE" });
}

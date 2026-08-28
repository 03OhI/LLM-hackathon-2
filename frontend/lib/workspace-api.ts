// 협업 워크스페이스 API 클라이언트.
//
// GET /api/rooms/{room_id}/workspace는 이 작업에서 새로 합의(가정)한 계약이다 —
// workspace_id를 URL로 미리 몰라도 room_id만으로 상태를 조회할 수 있게 한다.
// LOCKED: 아직 방장이 시작하지 않음(workspace_id는 null).
// ACTIVE: 방장이 시작함(workspace_id로 상세 조회 가능).

import { requestJson } from "./api";

export type TaskStatus = "TODO" | "IN_PROGRESS" | "DONE";
export type ResourceProvider = "GITHUB" | "FIGMA" | "NOTION" | "GOOGLE_DRIVE" | "DEPLOYMENT" | "OTHER";

export type Task = {
  id: string;
  title: string;
  status: TaskStatus;
  assignee_participant_id: string | null;
  due_at: string | null;
  created_by: string;
  created_at: string;
  updated_at: string;
};

export type ResourceLink = {
  id: string;
  title: string;
  url: string;
  provider: ResourceProvider;
  created_by: string;
  created_at: string;
};

export type Workspace = {
  id: string;
  session_id: string;
  status: string;
  started_at: string;
  tasks: Task[];
  resources: ResourceLink[];
};

export type RoomWorkspaceStatus = {
  status: "LOCKED" | "ACTIVE";
  workspace_id: string | null;
};

// 방장 전용 — 퀘스트 종료 후 협업 공간을 시작한다(멱등).
export function startWorkspace(roomId: string): Promise<Workspace> {
  return requestJson(`/rooms/${encodeURIComponent(roomId)}/workspace/start`, { method: "POST" });
}

// 팀원/방장 공용 — room_id만으로 협업 공간이 시작됐는지 폴링한다.
export function getRoomWorkspace(roomId: string): Promise<RoomWorkspaceStatus> {
  return requestJson(`/rooms/${encodeURIComponent(roomId)}/workspace`);
}

export function getWorkspace(workspaceId: string): Promise<Workspace> {
  return requestJson(`/workspaces/${encodeURIComponent(workspaceId)}`);
}

export function createTask(
  workspaceId: string,
  input: { title: string; assignee_participant_id?: string | null; due_at?: string | null },
): Promise<Task> {
  return requestJson(`/workspaces/${encodeURIComponent(workspaceId)}/tasks`, {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function updateTask(
  taskId: string,
  input: {
    title?: string;
    status?: TaskStatus;
    assignee_participant_id?: string | null;
    clear_assignee?: boolean;
    due_at?: string | null;
    clear_due_at?: boolean;
  },
): Promise<Task> {
  return requestJson(`/tasks/${encodeURIComponent(taskId)}`, {
    method: "PATCH",
    body: JSON.stringify(input),
  });
}

export function deleteTask(taskId: string): Promise<{ deleted: boolean }> {
  return requestJson(`/tasks/${encodeURIComponent(taskId)}`, { method: "DELETE" });
}

export function createResource(
  workspaceId: string,
  input: { title: string; url: string; provider: ResourceProvider },
): Promise<ResourceLink> {
  return requestJson(`/workspaces/${encodeURIComponent(workspaceId)}/resources`, {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function deleteResource(resourceId: string): Promise<{ deleted: boolean }> {
  return requestJson(`/resources/${encodeURIComponent(resourceId)}`, { method: "DELETE" });
}

export const PROVIDER_LABEL: Record<ResourceProvider, string> = {
  GITHUB: "GitHub",
  FIGMA: "Figma",
  NOTION: "Notion",
  GOOGLE_DRIVE: "Google Drive",
  DEPLOYMENT: "배포 링크",
  OTHER: "기타",
};

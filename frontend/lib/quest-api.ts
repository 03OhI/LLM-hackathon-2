// 퀘스트 API 클라이언트.
//
// 실제 백엔드 계약 (backend/app/api/quests.py QuestCurrentResponse):
// - my_response_status: 팀원 본인의 PER_MEMBER 체크별 제출 여부(type -> bool).
//   방장 조회 시에는 null.
// - team_completion_status: 팀 전체 완료 조건 충족 여부(satisfied)와 아직 안 채운
//   타입 목록(unmet_check_types). "완료" 버튼 활성/비활성의 최종 기준.
// - completion_requirements.member_checks/team_checks: 체크가 어느 scope에
//   속하는지, 각 타입이 최소 몇 번(min_count) 필요한지를 서버가 이미 나눠서
//   알려준다 — 프론트가 scope를 추론하지 않는다. 여기엔 진행 카운트/충족 여부는
//   없다(그건 my_response_status/team_completion_status 몫이다).
// used_rule_ids/matched_rule_ids/internal_index/team_grade/다른 팀원의 응답
// 내용은 이 응답에 없다.

import { requestJson } from "./api";

export type QuestStatus = "ASSIGNED" | "IN_PROGRESS" | "COMPLETED" | "SKIPPED";
export type AssignmentSource = "AGENT" | "RULE" | "FALLBACK";

export type AssignmentInfo = {
  id: string;
  status: QuestStatus;
  assignment_source: AssignmentSource;
  reason: string;
  intro_message: string;
  assigned_at: string;
  started_at: string | null;
  completed_at: string | null;
};

export type CompletionCheckRequirement = {
  type: string;
  min_count: number;
};

export type CompletionRequirements = {
  member_checks: CompletionCheckRequirement[];
  team_checks: CompletionCheckRequirement[];
};

export type CompletionStatus = {
  satisfied: boolean;
  unmet_check_types: string[];
};

export type QuestCurrent = {
  quest_id: string;
  title: string;
  summary: string;
  duration_minutes: number;
  steps: string[];
  materials: string[];
  deliverable: string;
  assignment: AssignmentInfo;
  my_response_status: Record<string, boolean> | null;
  team_completion_status: CompletionStatus;
  completion_requirements: CompletionRequirements;
};

export type CheckSubmission = { type: string; count?: number; value?: string | null };

export function getCurrentQuest(roomId: string): Promise<QuestCurrent> {
  return requestJson(`/rooms/${encodeURIComponent(roomId)}/quests/current`);
}

export function assignQuest(roomId: string): Promise<QuestCurrent> {
  return requestJson(`/rooms/${encodeURIComponent(roomId)}/quests/assign`, { method: "POST" });
}

export function startQuest(assignmentId: string): Promise<QuestCurrent> {
  return requestJson(`/quest-assignments/${encodeURIComponent(assignmentId)}/start`, { method: "POST" });
}

export function submitMyResponse(assignmentId: string, checks: CheckSubmission[]): Promise<QuestCurrent> {
  return requestJson(`/quest-assignments/${encodeURIComponent(assignmentId)}/responses/me`, {
    method: "PUT",
    body: JSON.stringify({ checks }),
  });
}

export function submitTeamResult(assignmentId: string, checks: CheckSubmission[]): Promise<QuestCurrent> {
  return requestJson(`/quest-assignments/${encodeURIComponent(assignmentId)}/result`, {
    method: "PUT",
    body: JSON.stringify({ checks }),
  });
}

export function completeQuest(assignmentId: string): Promise<QuestCurrent> {
  return requestJson(`/quest-assignments/${encodeURIComponent(assignmentId)}/complete`, { method: "POST" });
}

export function skipQuest(assignmentId: string): Promise<QuestCurrent> {
  return requestJson(`/quest-assignments/${encodeURIComponent(assignmentId)}/skip`, { method: "POST" });
}

// 체크 타입 → 안내 라벨/자유 입력 필요 여부. 백엔드 COMPLETION_CHECK_TYPES와 맞춘다.
export const CHECK_TYPE_LABEL: Record<string, string> = {
  VOTE: "투표",
  COMMENT: "댓글 남기기",
  TEXT_SUBMIT: "내용 제출",
  REACTION: "반응 남기기",
  APPROVE: "승인",
  NODE_CREATE: "항목 추가",
  LINK_VISIT: "링크 확인",
  QUESTION: "질문 남기기",
};

export const CHECK_TYPE_NEEDS_TEXT = new Set(["TEXT_SUBMIT", "COMMENT", "QUESTION"]);

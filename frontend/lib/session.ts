// survey/page.tsx가 저장한 팀 세션 정보를 읽기만 한다 (저장 형식은 그대로 재사용).

export type TeamSession = {
  sessionId: string;
  inviteToken: string;
  teamName: string;
  expectedMembers: number;
  participantId: string;
  isHost: boolean;
};

const TEAM_SESSION_KEY = "tmti-active-team-session";

export function getSavedTeamSession(): TeamSession | null {
  if (typeof window === "undefined") return null;
  try {
    const raw =
      window.sessionStorage.getItem(TEAM_SESSION_KEY) ?? window.localStorage.getItem(TEAM_SESSION_KEY);
    const parsed = JSON.parse(raw ?? "null") as { team?: TeamSession } | null;
    const team = parsed?.team;
    return team?.sessionId && team?.participantId ? team : null;
  } catch {
    return null;
  }
}

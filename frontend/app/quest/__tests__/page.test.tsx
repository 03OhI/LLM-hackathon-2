import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/lib/api";
import type { QuestCurrent } from "@/lib/quest-api";
import type { TeamSession } from "@/lib/session";

vi.mock("@/lib/session", () => ({
  getSavedTeamSession: vi.fn(),
}));
vi.mock("@/lib/quest-api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/quest-api")>("@/lib/quest-api");
  return {
    ...actual,
    getCurrentQuest: vi.fn(),
    getQuestRecommendations: vi.fn(),
    assignQuest: vi.fn(),
    startQuest: vi.fn(),
    completeQuest: vi.fn(),
    skipQuest: vi.fn(),
    submitMyResponse: vi.fn(),
    submitTeamResult: vi.fn(),
  };
});
vi.mock("@/lib/workspace-api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/workspace-api")>("@/lib/workspace-api");
  return { ...actual, startWorkspace: vi.fn() };
});

import { getSavedTeamSession } from "@/lib/session";
import { assignQuest, getCurrentQuest, getQuestRecommendations } from "@/lib/quest-api";
import QuestPage from "../page";

const hostSession: TeamSession = {
  sessionId: "room-1",
  inviteToken: "tok",
  teamName: "우리팀",
  expectedMembers: 4,
  participantId: "host-participant",
  isHost: true,
};
const memberSession: TeamSession = { ...hostSession, participantId: "member-1", isHost: false };

function makeQuest(overrides: Partial<QuestCurrent> = {}): QuestCurrent {
  return {
    quest_id: "Q1",
    title: "공통점 다섯 개 찾기",
    summary: "가볍게 대화하며 공통점을 찾아봐요.",
    duration_minutes: 10,
    steps: ["대화하기", "목록 작성"],
    materials: [],
    deliverable: "공통점 목록",
    assignment: {
      id: "assign-1",
      status: "ASSIGNED",
      assignment_source: "AGENT",
      reason: "지금 팀에 잘 맞아요.",
      intro_message: "오늘의 퀘스트예요.",
      assigned_at: "2026-01-01T00:00:00Z",
      started_at: null,
      completed_at: null,
    },
    my_response_status: null,
    team_completion_status: { satisfied: true, unmet_check_types: [] },
    completion_requirements: { member_checks: [], team_checks: [] },
    ...overrides,
  };
}

afterEach(() => {
  vi.clearAllMocks();
  vi.unstubAllGlobals();
  window.history.pushState({}, "", "/quest");
});

describe("QuestPage 관리자 시연 흐름", () => {
  it("실제 세션 없이도 관리자 결과에서 퀘스트를 시작하고 완료할 수 있다", async () => {
    window.history.pushState({}, "", "/quest?mode=admin");
    vi.mocked(getSavedTeamSession).mockReturnValue(null);
    render(<QuestPage />);

    (await screen.findAllByRole("button", { name: "이 퀘스트 선택" }))[0].click();
    const startButton = await screen.findByRole("button", { name: "퀘스트 시작" });
    startButton.click();
    const input = await screen.findByLabelText("내용 제출 입력");
    expect(input).toBeInTheDocument();
  });

  it("퀘스트 시작 → 공동 결과 제출 → 완료 → 협업 시작하기 → /workspace?mode=admin까지 실제로 클릭된다", async () => {
    window.history.pushState({}, "", "/quest?mode=admin");
    vi.mocked(getSavedTeamSession).mockReturnValue(null);
    const assign = vi.fn();
    vi.stubGlobal("location", { ...window.location, assign });

    render(<QuestPage />);

    // 0) 추천 3개 중 하나 선택
    (await screen.findAllByRole("button", { name: "이 퀘스트 선택" }))[0].click();

    // 1) 퀘스트 시작
    (await screen.findByRole("button", { name: "퀘스트 시작" })).click();

    // 2) 공동 결과 제출(team_checks: TEXT_SUBMIT)
    const input = await screen.findByLabelText("내용 제출 입력");
    fireEvent.change(input, { target: { value: "우리 팀은 80% 완성 후 함께 쉬기로 했어요." } });
    const submitButtons = await screen.findAllByRole("button", { name: "제출" });
    submitButtons[submitButtons.length - 1].click();

    // 3) 완료
    const completeButton = await screen.findByRole("button", { name: "완료" });
    await waitFor(() => expect(completeButton).not.toBeDisabled());
    completeButton.click();

    // 4) 협업 시작하기
    const goWorkspace = await screen.findByRole("button", { name: "협업 시작하기" });
    goWorkspace.click();

    await waitFor(() => expect(assign).toHaveBeenCalledWith("/workspace?mode=admin"));
  });
});

describe("QuestPage 역할별 버튼", () => {
  it("아직 배정 전이면 팀 성향 추천 3개를 보여주고 선택한 퀘스트를 배정한다", async () => {
    vi.mocked(getSavedTeamSession).mockReturnValue(hostSession);
    vi.mocked(getCurrentQuest).mockRejectedValue(new ApiError("NO_ACTIVE_QUEST", "", 404));
    vi.mocked(getQuestRecommendations).mockResolvedValue({
      recommendations: [
        { quest_id: "Q1", title: "추천 하나", summary: "첫 번째", duration_minutes: 5, category: "A", match_reason: "팀 성향과 잘 맞아요." },
        { quest_id: "Q2", title: "추천 둘", summary: "두 번째", duration_minutes: 7, category: "B", match_reason: "팀 성향과 잘 맞아요." },
        { quest_id: "Q3", title: "추천 셋", summary: "세 번째", duration_minutes: 9, category: "C", match_reason: "팀 성향과 잘 맞아요." },
      ],
    });
    vi.mocked(assignQuest).mockResolvedValue(makeQuest({ quest_id: "Q2", title: "추천 둘" }));

    render(<QuestPage />);

    expect(await screen.findByText("추천 하나")).toBeInTheDocument();
    expect(screen.getByText("추천 둘")).toBeInTheDocument();
    expect(screen.getByText("추천 셋")).toBeInTheDocument();
    const selectButtons = screen.getAllByRole("button", { name: "이 퀘스트 선택" });
    selectButtons[1].click();
    await waitFor(() => expect(assignQuest).toHaveBeenCalledWith("room-1", "Q2"));
    expect(await screen.findByRole("button", { name: "퀘스트 시작" })).toBeInTheDocument();
  });

  it("ASSIGNED 상태에서 방장에게만 '퀘스트 시작' 버튼을 보여준다", async () => {
    vi.mocked(getSavedTeamSession).mockReturnValue(hostSession);
    vi.mocked(getCurrentQuest).mockResolvedValue(makeQuest());
    render(<QuestPage />);

    expect(await screen.findByRole("button", { name: "퀘스트 시작" })).toBeInTheDocument();
  });

  it("ASSIGNED 상태에서 팀원에게는 '퀘스트 시작' 버튼이 없다", async () => {
    vi.mocked(getSavedTeamSession).mockReturnValue(memberSession);
    vi.mocked(getCurrentQuest).mockResolvedValue(makeQuest());
    render(<QuestPage />);

    await screen.findByText(/방장이 곧 퀘스트를 시작할 거예요/);
    expect(screen.queryByRole("button", { name: "퀘스트 시작" })).not.toBeInTheDocument();
  });

  it("완료 조건이 부족하면 방장의 완료 버튼이 비활성 상태다", async () => {
    vi.mocked(getSavedTeamSession).mockReturnValue(hostSession);
    vi.mocked(getCurrentQuest).mockResolvedValue(
      makeQuest({
        assignment: { ...makeQuest().assignment, status: "IN_PROGRESS" },
        team_completion_status: { satisfied: false, unmet_check_types: ["REACTION"] },
        completion_requirements: {
          member_checks: [{ type: "REACTION", min_count: 3 }],
          team_checks: [],
        },
      }),
    );
    render(<QuestPage />);

    const completeButton = await screen.findByRole("button", { name: "완료" });
    expect(completeButton).toBeDisabled();
  });

  it("완료 조건이 모두 충족되면 완료 버튼이 활성화된다", async () => {
    vi.mocked(getSavedTeamSession).mockReturnValue(hostSession);
    vi.mocked(getCurrentQuest).mockResolvedValue(
      makeQuest({
        assignment: { ...makeQuest().assignment, status: "IN_PROGRESS" },
        team_completion_status: { satisfied: true, unmet_check_types: [] },
        completion_requirements: {
          member_checks: [{ type: "REACTION", min_count: 1 }],
          team_checks: [],
        },
      }),
    );
    render(<QuestPage />);

    const completeButton = await screen.findByRole("button", { name: "완료" });
    expect(completeButton).toBeEnabled();
  });

  it("완료 전(ASSIGNED/IN_PROGRESS)에는 '협업 시작하기' 버튼이 없다", async () => {
    vi.mocked(getSavedTeamSession).mockReturnValue(hostSession);
    vi.mocked(getCurrentQuest).mockResolvedValue(
      makeQuest({
        assignment: { ...makeQuest().assignment, status: "IN_PROGRESS" },
        team_completion_status: { satisfied: true, unmet_check_types: [] },
      }),
    );
    render(<QuestPage />);

    await screen.findByRole("button", { name: "완료" });
    expect(screen.queryByRole("button", { name: "협업 시작하기" })).not.toBeInTheDocument();
  });

  it("COMPLETED 이후에는 방장에게 '협업 시작하기' 버튼이 활성화된다", async () => {
    vi.mocked(getSavedTeamSession).mockReturnValue(hostSession);
    vi.mocked(getCurrentQuest).mockResolvedValue(
      makeQuest({ assignment: { ...makeQuest().assignment, status: "COMPLETED" } }),
    );
    render(<QuestPage />);

    const button = await screen.findByRole("button", { name: "협업 시작하기" });
    expect(button).toBeEnabled();
  });

  it("SKIPPED 상태도 불이익 없는 문구와 함께 팀원에게 이동 링크를 보여준다", async () => {
    vi.mocked(getSavedTeamSession).mockReturnValue(memberSession);
    vi.mocked(getCurrentQuest).mockResolvedValue(
      makeQuest({ assignment: { ...makeQuest().assignment, status: "SKIPPED" } }),
    );
    render(<QuestPage />);

    expect(await screen.findByText(/불이익은 없어요/)).toBeInTheDocument();
    expect(await screen.findByRole("link", { name: "협업 공간으로 이동" })).toBeInTheDocument();
  });
});

describe("QuestPage 체크 scope는 서버가 이미 나눈 대로만 쓴다", () => {
  it("member_checks는 팀원 화면에, team_checks는 방장 화면에 각각 노출된다", async () => {
    vi.mocked(getSavedTeamSession).mockReturnValue(memberSession);
    vi.mocked(getCurrentQuest).mockResolvedValue(
      makeQuest({
        assignment: { ...makeQuest().assignment, status: "IN_PROGRESS" },
        my_response_status: { REACTION: false },
        team_completion_status: { satisfied: false, unmet_check_types: ["REACTION", "TEXT_SUBMIT"] },
        completion_requirements: {
          member_checks: [{ type: "REACTION", min_count: 1 }],
          team_checks: [{ type: "TEXT_SUBMIT", min_count: 1 }],
        },
      }),
    );
    render(<QuestPage />);

    expect(await screen.findByText("내 응답")).toBeInTheDocument();
    expect(screen.queryByText("공동 결과 제출")).not.toBeInTheDocument();
  });

  it("completion_requirements는 min_count만 담고 있고, 충족 여부는 my_response_status로만 판단한다", async () => {
    vi.mocked(getSavedTeamSession).mockReturnValue(memberSession);
    vi.mocked(getCurrentQuest).mockResolvedValue(
      makeQuest({
        assignment: { ...makeQuest().assignment, status: "IN_PROGRESS" },
        my_response_status: { REACTION: true },
        team_completion_status: { satisfied: false, unmet_check_types: [] },
        completion_requirements: {
          member_checks: [{ type: "REACTION", min_count: 2 }],
          team_checks: [],
        },
      }),
    );
    render(<QuestPage />);

    expect(await screen.findByText("최소 2회")).toBeInTheDocument();
    expect(await screen.findByText("✓ 제출했어요")).toBeInTheDocument();
  });

  it("방장 화면의 팀원 응답 현황은 입력 폼 없이 진행 상태만 보여준다", async () => {
    vi.mocked(getSavedTeamSession).mockReturnValue(hostSession);
    vi.mocked(getCurrentQuest).mockResolvedValue(
      makeQuest({
        assignment: { ...makeQuest().assignment, status: "IN_PROGRESS" },
        team_completion_status: { satisfied: false, unmet_check_types: ["REACTION"] },
        completion_requirements: {
          member_checks: [{ type: "REACTION", min_count: 1 }],
          team_checks: [],
        },
      }),
    );
    render(<QuestPage />);

    await screen.findByText("팀원 응답 현황");
    expect(screen.queryByLabelText(/반응 남기기 입력/)).not.toBeInTheDocument();
  });
});

describe("QuestPage API 오류 표시", () => {
  it("기술적 원인을 노출하지 않고 사람이 읽을 문구를 보여준다", async () => {
    vi.mocked(getSavedTeamSession).mockReturnValue(hostSession);
    vi.mocked(getCurrentQuest).mockRejectedValue(
      new ApiError("UNKNOWN_ERROR", "LLM_ERROR: TimeoutError: Bedrock timed out", 500),
    );
    render(<QuestPage />);

    await waitFor(() => expect(screen.getByRole("button", { name: "다시 시도" })).toBeInTheDocument());
    expect(screen.queryByText(/bedrock/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/timeout/i)).not.toBeInTheDocument();
  });

  it("세션 정보가 없으면 안내 카드를 보여준다", async () => {
    vi.mocked(getSavedTeamSession).mockReturnValue(null);
    render(<QuestPage />);

    expect(await screen.findByText(/세션 정보가 없어요/)).toBeInTheDocument();
  });
});

describe("QuestPage polling 정리", () => {
  it("언마운트 후에는 더 이상 getCurrentQuest를 호출하지 않는다", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.mocked(getSavedTeamSession).mockReturnValue(hostSession);
    vi.mocked(getCurrentQuest).mockResolvedValue(makeQuest());

    const { unmount } = render(<QuestPage />);
    await vi.waitFor(() => expect(getCurrentQuest).toHaveBeenCalledTimes(1));

    unmount();
    const callsAtUnmount = vi.mocked(getCurrentQuest).mock.calls.length;

    await vi.advanceTimersByTimeAsync(20000);
    expect(vi.mocked(getCurrentQuest).mock.calls.length).toBe(callsAtUnmount);
    vi.useRealTimers();
  });
});

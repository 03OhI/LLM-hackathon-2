import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/lib/api";
import type { TeamSession } from "@/lib/session";
import type { RoomParticipant } from "@/lib/participants-api";
import type { Task, Workspace } from "@/lib/workspace-api";

vi.mock("@/lib/session", () => ({
  getSavedTeamSession: vi.fn(),
}));
vi.mock("@/lib/participants-api", () => ({
  getRoomParticipants: vi.fn(),
}));
vi.mock("@/lib/workspace-api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/workspace-api")>("@/lib/workspace-api");
  return {
    ...actual,
    getRoomWorkspace: vi.fn(),
    getWorkspace: vi.fn(),
    startWorkspace: vi.fn(),
    createTask: vi.fn(),
    updateTask: vi.fn(),
    deleteTask: vi.fn(),
    createResource: vi.fn(),
    deleteResource: vi.fn(),
  };
});
vi.mock("@/lib/workspace-tools-api", () => ({
  getNotice: vi.fn(),
  updateNotice: vi.fn(),
  getPresentationChecklist: vi.fn(),
  createPresentationChecklistItem: vi.fn(),
  updatePresentationChecklistItem: vi.fn(),
  deletePresentationChecklistItem: vi.fn(),
  getDecisions: vi.fn(),
  createDecision: vi.fn(),
  voteDecision: vi.fn(),
  finalizeDecision: vi.fn(),
  getMeetingNotes: vi.fn(),
  createMeetingNote: vi.fn(),
  updateMeetingNote: vi.fn(),
  deleteMeetingNote: vi.fn(),
}));

import { getSavedTeamSession } from "@/lib/session";
import { getRoomParticipants } from "@/lib/participants-api";
import { getRoomWorkspace, getWorkspace, startWorkspace, updateTask, createResource, deleteResource } from "@/lib/workspace-api";
import {
  getNotice,
  updateNotice,
  getPresentationChecklist,
  getDecisions,
  voteDecision,
  finalizeDecision,
  getMeetingNotes,
  createMeetingNote,
} from "@/lib/workspace-tools-api";
import type { Decision, WorkspaceNotice } from "@/lib/workspace-tools-api";
import WorkspacePage from "../page";

const hostSession: TeamSession = {
  sessionId: "room-1",
  inviteToken: "tok",
  teamName: "우리팀",
  expectedMembers: 4,
  participantId: "host-participant",
  isHost: true,
};
const memberSession: TeamSession = { ...hostSession, participantId: "member-1", isHost: false };

const participants: RoomParticipant[] = [
  { participant_id: "host-participant", nickname: "방장" },
  { participant_id: "member-1", nickname: "민지" },
  { participant_id: "member-2", nickname: "재완" },
];

function makeTask(overrides: Partial<Task> = {}): Task {
  return {
    id: "task-1",
    title: "발표 자료 초안 만들기",
    status: "TODO",
    assignee_participant_id: null,
    due_at: null,
    created_by: "host-participant",
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

function makeWorkspace(overrides: Partial<Workspace> = {}): Workspace {
  return {
    id: "ws-1",
    session_id: "room-1",
    status: "ACTIVE",
    started_at: "2026-01-01T00:00:00Z",
    tasks: [makeTask()],
    resources: [],
    ...overrides,
  };
}

function setUrl(query: string) {
  window.history.pushState({}, "", `/workspace${query}`);
}

beforeEach(() => {
  setUrl("?sessionId=room-1");
  vi.mocked(getRoomParticipants).mockResolvedValue(participants);
  // 새 확장 기능 4종은 백엔드 미병합을 기본 가정으로 둔다 — 각 테스트가 필요할 때만
  // mockResolvedValue로 덮어쓴다. 이렇게 해야 이 섹션들과 무관한 기존 테스트가
  // "엔드포인트 없음 -> 친화적 오류" 경로를 그대로 타면서 undefined로 렌더링해
  // 깨지는 일이 없다.
  const notFound = new ApiError("NOT_FOUND", "", 404);
  vi.mocked(getNotice).mockRejectedValue(notFound);
  vi.mocked(getPresentationChecklist).mockRejectedValue(notFound);
  vi.mocked(getDecisions).mockRejectedValue(notFound);
  vi.mocked(getMeetingNotes).mockRejectedValue(notFound);
});

afterEach(() => {
  vi.clearAllMocks();
});

describe("WorkspacePage room_id 기반 자동 조회", () => {
  it("관리자 시연 모드는 실제 세션 없이 협업 공간을 보여준다", async () => {
    setUrl("?mode=admin");
    vi.mocked(getSavedTeamSession).mockReturnValue(null);

    render(<WorkspacePage />);

    expect(await screen.findByText("함께 정리하고 공유해요")).toBeInTheDocument();
    expect(screen.getByText("발표 자료의 핵심 한 문장 정하기")).toBeInTheDocument();
  });

  it("LOCKED이면 대기 화면을 보여주고 getWorkspace는 호출하지 않는다", async () => {
    vi.mocked(getSavedTeamSession).mockReturnValue(memberSession);
    vi.mocked(getRoomWorkspace).mockResolvedValue({ status: "LOCKED", workspace_id: null });

    render(<WorkspacePage />);

    expect(await screen.findByText(/방장이 협업을 시작하면 자동으로 열려요/)).toBeInTheDocument();
    expect(getWorkspace).not.toHaveBeenCalled();
  });

  it("ACTIVE + workspace_id를 받으면 워크스페이스를 표시한다", async () => {
    vi.mocked(getSavedTeamSession).mockReturnValue(memberSession);
    vi.mocked(getRoomWorkspace).mockResolvedValue({ status: "ACTIVE", workspace_id: "ws-1" });
    vi.mocked(getWorkspace).mockResolvedValue(makeWorkspace());

    render(<WorkspacePage />);

    expect(await screen.findByText("함께 정리하고 공유해요")).toBeInTheDocument();
    expect(getWorkspace).toHaveBeenCalledWith("ws-1");
  });

  it("방장은 LOCKED 화면에서 바로 협업을 시작할 수 있다", async () => {
    vi.mocked(getSavedTeamSession).mockReturnValue(hostSession);
    vi.mocked(getRoomWorkspace).mockResolvedValue({ status: "LOCKED", workspace_id: null });
    vi.mocked(startWorkspace).mockResolvedValue(makeWorkspace());

    render(<WorkspacePage />);
    const startButton = await screen.findByRole("button", { name: "협업 시작하기" });
    fireEvent.click(startButton);

    await waitFor(() => expect(startWorkspace).toHaveBeenCalledWith("room-1"));
  });
});

describe("WorkspacePage 팀원 담당자 선택", () => {
  it("미지정/나/다른 팀원 중에서 고를 수 있다", async () => {
    vi.mocked(getSavedTeamSession).mockReturnValue(hostSession);
    vi.mocked(getRoomWorkspace).mockResolvedValue({ status: "ACTIVE", workspace_id: "ws-1" });
    vi.mocked(getWorkspace).mockResolvedValue(makeWorkspace());

    render(<WorkspacePage />);
    await screen.findByText("함께 정리하고 공유해요");

    const select = screen.getByLabelText("담당자") as HTMLSelectElement;
    const optionLabels = Array.from(select.options).map((o) => o.textContent);
    expect(optionLabels).toEqual(["담당자 미지정", "나에게 배정", "민지", "재완"]);
  });

  it("다른 팀원에게 배정하면 그 팀원의 닉네임이 목록에 표시된다", async () => {
    vi.mocked(getSavedTeamSession).mockReturnValue(hostSession);
    vi.mocked(getRoomWorkspace).mockResolvedValue({ status: "ACTIVE", workspace_id: "ws-1" });
    vi.mocked(getWorkspace).mockResolvedValue(
      makeWorkspace({ tasks: [makeTask({ assignee_participant_id: "member-2" })] }),
    );

    render(<WorkspacePage />);
    await screen.findByText("함께 정리하고 공유해요");

    // "재완"은 담당자 select의 옵션으로도 나오므로, task-assignee 배지 쪽만 확인한다.
    const matches = screen.getAllByText("재완");
    expect(matches.some((el) => el.className === "task-assignee")).toBe(true);
  });
});

describe("WorkspacePage task 상태 변경", () => {
  it("상태 버튼을 누르면 updateTask가 새 상태로 호출된다", async () => {
    vi.mocked(getSavedTeamSession).mockReturnValue(hostSession);
    vi.mocked(getRoomWorkspace).mockResolvedValue({ status: "ACTIVE", workspace_id: "ws-1" });
    vi.mocked(getWorkspace).mockResolvedValue(makeWorkspace());
    vi.mocked(updateTask).mockResolvedValue(makeTask({ status: "IN_PROGRESS" }));

    render(<WorkspacePage />);
    const inProgressButton = await screen.findByRole("button", { name: "진행 중" });
    fireEvent.click(inProgressButton);

    await waitFor(() => expect(updateTask).toHaveBeenCalledWith("task-1", { status: "IN_PROGRESS" }));
  });
});

describe("WorkspacePage 링크 등록·삭제", () => {
  it("링크를 등록하면 createResource가 입력값으로 호출된다", async () => {
    const user = userEvent.setup();
    vi.mocked(getSavedTeamSession).mockReturnValue(hostSession);
    vi.mocked(getRoomWorkspace).mockResolvedValue({ status: "ACTIVE", workspace_id: "ws-1" });
    vi.mocked(getWorkspace).mockResolvedValue(makeWorkspace());
    vi.mocked(createResource).mockResolvedValue({
      id: "res-1",
      title: "디자인 시안",
      url: "https://figma.com/x",
      provider: "FIGMA",
      created_by: "host-participant",
      created_at: "2026-01-01T00:00:00Z",
    });

    render(<WorkspacePage />);
    await screen.findByText("공유 링크");

    await user.type(screen.getByLabelText("링크 이름"), "디자인 시안");
    await user.type(screen.getByLabelText("링크 주소"), "https://figma.com/x");
    await user.selectOptions(screen.getByLabelText("링크 종류"), "FIGMA");
    await user.click(screen.getByRole("button", { name: "링크 추가" }));

    await waitFor(() =>
      expect(createResource).toHaveBeenCalledWith("ws-1", {
        title: "디자인 시안",
        url: "https://figma.com/x",
        provider: "FIGMA",
      }),
    );
  });

  it("삭제 버튼을 누르면 deleteResource가 호출된다 (작성자 본인)", async () => {
    vi.mocked(getSavedTeamSession).mockReturnValue(hostSession);
    vi.mocked(getRoomWorkspace).mockResolvedValue({ status: "ACTIVE", workspace_id: "ws-1" });
    vi.mocked(getWorkspace).mockResolvedValue(
      makeWorkspace({
        resources: [
          {
            id: "res-1",
            title: "우리 팀 배포 주소",
            url: "https://example.com",
            provider: "DEPLOYMENT",
            created_by: "host-participant",
            created_at: "2026-01-01T00:00:00Z",
          },
        ],
      }),
    );
    vi.mocked(deleteResource).mockResolvedValue({ deleted: true });

    render(<WorkspacePage />);
    const deleteButton = await screen.findByRole("button", { name: "우리 팀 배포 주소 삭제" });
    fireEvent.click(deleteButton);

    await waitFor(() => expect(deleteResource).toHaveBeenCalledWith("res-1"));
  });

  it("본인이 만들지 않았고 방장도 아니면 삭제 버튼이 보이지 않는다", async () => {
    vi.mocked(getSavedTeamSession).mockReturnValue(memberSession);
    vi.mocked(getRoomWorkspace).mockResolvedValue({ status: "ACTIVE", workspace_id: "ws-1" });
    vi.mocked(getWorkspace).mockResolvedValue(
      makeWorkspace({
        resources: [
          {
            id: "res-1",
            title: "우리 팀 배포 주소",
            url: "https://example.com",
            provider: "DEPLOYMENT",
            created_by: "someone-else",
            created_at: "2026-01-01T00:00:00Z",
          },
        ],
      }),
    );

    render(<WorkspacePage />);
    await screen.findByRole("link", { name: /우리 팀 배포 주소/ });
    expect(screen.queryByRole("button", { name: /삭제/ })).not.toBeInTheDocument();
  });
});

describe("WorkspacePage API 오류 표시", () => {
  it("워크스페이스 조회 실패 시 안내 문구를 보여준다", async () => {
    vi.mocked(getSavedTeamSession).mockReturnValue(hostSession);
    vi.mocked(getRoomWorkspace).mockRejectedValue(new ApiError("WORKSPACE_NOT_FOUND", "", 404));

    render(<WorkspacePage />);

    expect(await screen.findByText(/협업 공간을 불러오지 못했어요/)).toBeInTheDocument();
  });
});

// ──────────────────────────────────────────────
// 확장 기능(공지/타이머/체크리스트/의사결정/회의메모/바로가기)
// ──────────────────────────────────────────────

function makeNotice(overrides: Partial<WorkspaceNotice> = {}): WorkspaceNotice {
  return {
    content: "오늘 17시까지 기능 통합 완료",
    deadline_at: "2026-08-29T17:00:00Z",
    presentation_order: 3,
    updated_at: "2026-08-29T00:00:00Z",
    ...overrides,
  };
}

function makeDecisionRecord(overrides: Partial<Decision> = {}): Decision {
  return {
    id: "decision-1",
    title: "서비스명 정하기",
    description: "최종 이름을 정해요.",
    options: [
      { id: "opt-1", label: "TMTI", vote_count: 2 },
      { id: "opt-2", label: "ChemLink", vote_count: 1 },
    ],
    status: "OPEN",
    finalized_option_id: null,
    my_vote_option_id: null,
    created_by: "host-participant",
    created_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

describe("WorkspacePage 관리자 시연 모드 — 확장 기능은 전부 로컬 상태로 동작한다", () => {
  it("시연 기본 데이터(공지/타이머/체크리스트/의사결정/메모/할일/링크)가 전부 표시된다", async () => {
    setUrl("?mode=admin");
    vi.mocked(getSavedTeamSession).mockReturnValue(null);

    render(<WorkspacePage />);

    expect(await screen.findByText("오늘 17시까지 기능 통합 완료")).toBeInTheDocument();
    expect(screen.getByText("발표 순서 3번째")).toBeInTheDocument();
    expect(screen.getByText("25:00")).toBeInTheDocument(); // 타이머
    expect(screen.getByText("2/4개 완료")).toBeInTheDocument(); // 체크리스트
    expect(screen.getByText("서비스명 정하기")).toBeInTheDocument(); // 의사결정
    expect(screen.getByText("발표 리허설 회의")).toBeInTheDocument(); // 회의 메모
    expect(screen.getByText("발표 자료의 핵심 한 문장 정하기")).toBeInTheDocument(); // 할 일
    expect(screen.getAllByText("팀 GitHub 저장소").length).toBeGreaterThan(0); // 링크

    // 관리자 모드는 어떤 확장 기능 API도 호출하지 않는다.
    expect(getNotice).not.toHaveBeenCalled();
    expect(getPresentationChecklist).not.toHaveBeenCalled();
    expect(getDecisions).not.toHaveBeenCalled();
    expect(getMeetingNotes).not.toHaveBeenCalled();
  });

  it("공지 수정, 체크리스트 체크, 투표·확정, 메모 추가가 모두 클릭 가능하다(API 호출 없이)", async () => {
    setUrl("?mode=admin");
    vi.mocked(getSavedTeamSession).mockReturnValue(null);
    const user = userEvent.setup();

    render(<WorkspacePage />);
    await screen.findByText("오늘 17시까지 기능 통합 완료");

    // 공지 수정
    await user.click(screen.getByRole("button", { name: "공지 수정" }));
    const contentBox = screen.getByLabelText("공지 내용");
    await user.clear(contentBox);
    await user.type(contentBox, "새 공지입니다");
    await user.click(screen.getByRole("button", { name: "저장" }));
    expect(await screen.findByText("새 공지입니다")).toBeInTheDocument();

    // 체크리스트 체크 해제(2개 완료 -> 1개 완료)
    const checkboxes = screen.getAllByRole("checkbox");
    await user.click(checkboxes[0]);
    expect(await screen.findByText("1/4개 완료")).toBeInTheDocument();

    // 투표
    await user.click(screen.getAllByRole("button", { name: "투표" })[0]);
    expect(await screen.findByText("투표함")).toBeInTheDocument();

    // 방장 확정
    await user.click(screen.getAllByRole("button", { name: "이 선택지로 확정" })[0]);
    expect(await screen.findByText(/최종 결정:/)).toBeInTheDocument();

    expect(updateNotice).not.toHaveBeenCalled();
    expect(voteDecision).not.toHaveBeenCalled();
    expect(finalizeDecision).not.toHaveBeenCalled();
  });
});

describe("WorkspacePage 실제 모드 — 확장 기능 API 연동", () => {
  it("워크스페이스가 열리면 공지/체크리스트/의사결정/메모를 각각 조회한다", async () => {
    vi.mocked(getSavedTeamSession).mockReturnValue(hostSession);
    vi.mocked(getRoomWorkspace).mockResolvedValue({ status: "ACTIVE", workspace_id: "ws-1" });
    vi.mocked(getWorkspace).mockResolvedValue(makeWorkspace());
    vi.mocked(getNotice).mockResolvedValue(makeNotice());
    vi.mocked(getPresentationChecklist).mockResolvedValue([]);
    vi.mocked(getDecisions).mockResolvedValue([makeDecisionRecord()]);
    vi.mocked(getMeetingNotes).mockResolvedValue([]);

    render(<WorkspacePage />);

    await waitFor(() => {
      expect(getNotice).toHaveBeenCalledWith("ws-1");
      expect(getPresentationChecklist).toHaveBeenCalledWith("ws-1");
      expect(getDecisions).toHaveBeenCalledWith("ws-1");
      expect(getMeetingNotes).toHaveBeenCalledWith("ws-1");
    });
    expect(await screen.findByText("오늘 17시까지 기능 통합 완료")).toBeInTheDocument();
  });

  it("공지 API가 아직 없으면(404) 가짜 성공 없이 친화적 오류 문구를 보여준다", async () => {
    vi.mocked(getSavedTeamSession).mockReturnValue(hostSession);
    vi.mocked(getRoomWorkspace).mockResolvedValue({ status: "ACTIVE", workspace_id: "ws-1" });
    vi.mocked(getWorkspace).mockResolvedValue(makeWorkspace());
    // getNotice는 beforeEach 기본값(404 거부) 그대로 둔다.

    render(<WorkspacePage />);
    await screen.findByText("함께 정리하고 공유해요");

    expect(screen.queryByRole("button", { name: "공지 수정" })).not.toBeInTheDocument();
    expect((await screen.findAllByText(/정보를 찾지 못했어요|아직 준비되지 않은 기능|잠시 문제가 있었어요/)).length).toBeGreaterThan(0);
  });

  it("투표 버튼을 누르면 voteDecision이 호출된다", async () => {
    vi.mocked(getSavedTeamSession).mockReturnValue(memberSession);
    vi.mocked(getRoomWorkspace).mockResolvedValue({ status: "ACTIVE", workspace_id: "ws-1" });
    vi.mocked(getWorkspace).mockResolvedValue(makeWorkspace());
    vi.mocked(getDecisions).mockResolvedValue([makeDecisionRecord()]);
    vi.mocked(voteDecision).mockResolvedValue(makeDecisionRecord({ my_vote_option_id: "opt-1" }));

    render(<WorkspacePage />);
    const voteButton = (await screen.findAllByRole("button", { name: "투표" }))[0];
    fireEvent.click(voteButton);

    await waitFor(() => expect(voteDecision).toHaveBeenCalledWith("decision-1", "opt-1"));
  });

  it("팀원에게는 확정 버튼이 보이지 않고, 방장에게는 보인다", async () => {
    vi.mocked(getRoomWorkspace).mockResolvedValue({ status: "ACTIVE", workspace_id: "ws-1" });
    vi.mocked(getWorkspace).mockResolvedValue(makeWorkspace());
    vi.mocked(getDecisions).mockResolvedValue([makeDecisionRecord()]);

    vi.mocked(getSavedTeamSession).mockReturnValue(memberSession);
    const { unmount } = render(<WorkspacePage />);
    await screen.findByText("서비스명 정하기");
    expect(screen.queryByRole("button", { name: "이 선택지로 확정" })).not.toBeInTheDocument();
    unmount();

    vi.mocked(getSavedTeamSession).mockReturnValue(hostSession);
    render(<WorkspacePage />);
    await screen.findByText("서비스명 정하기");
    expect(screen.getAllByRole("button", { name: "이 선택지로 확정" }).length).toBeGreaterThan(0);
  });

  it("회의 메모를 추가하면 createMeetingNote가 호출된다", async () => {
    const user = userEvent.setup();
    vi.mocked(getSavedTeamSession).mockReturnValue(hostSession);
    vi.mocked(getRoomWorkspace).mockResolvedValue({ status: "ACTIVE", workspace_id: "ws-1" });
    vi.mocked(getWorkspace).mockResolvedValue(makeWorkspace());
    vi.mocked(getMeetingNotes).mockResolvedValue([]);
    vi.mocked(createMeetingNote).mockResolvedValue({
      id: "note-1",
      title: "킥오프",
      discussion: "역할 분담",
      next_actions: "각자 리서치",
      created_by: "host-participant",
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    });

    render(<WorkspacePage />);
    await screen.findByText("함께 정리하고 공유해요");

    await user.click(screen.getByRole("button", { name: "새 회의 메모 추가" }));
    await user.type(screen.getByLabelText("메모 제목"), "킥오프");
    await user.click(screen.getByRole("button", { name: "저장" }));

    await waitFor(() =>
      expect(createMeetingNote).toHaveBeenCalledWith("ws-1", { title: "킥오프", discussion: "", next_actions: "" }),
    );
  });
});

describe("WorkspacePage 모바일 레이아웃(390px)", () => {
  const originalWidth = window.innerWidth;

  afterEach(() => {
    Object.defineProperty(window, "innerWidth", { configurable: true, value: originalWidth });
  });

  it("390px 뷰포트에서도 모든 섹션이 렌더링된다(1열 CSS는 globals.css @media(max-width:700px)가 담당)", async () => {
    Object.defineProperty(window, "innerWidth", { configurable: true, value: 390 });
    window.dispatchEvent(new Event("resize"));
    setUrl("?mode=admin");
    vi.mocked(getSavedTeamSession).mockReturnValue(null);

    render(<WorkspacePage />);

    expect(await screen.findByText("함께 정리하고 공유해요")).toBeInTheDocument();
    expect(screen.getByLabelText("고정 공지")).toBeInTheDocument();
    expect(screen.getByLabelText("집중·회의 타이머")).toBeInTheDocument();
    expect(screen.getByLabelText("발표 준비 체크리스트")).toBeInTheDocument();
    expect(screen.getByLabelText("빠른 의사결정 보드")).toBeInTheDocument();
    expect(screen.getByLabelText("공동 할 일")).toBeInTheDocument();
    expect(screen.getByLabelText("회의 메모")).toBeInTheDocument();
    expect(screen.getByLabelText("GitHub/Figma/Notion 바로가기")).toBeInTheDocument();
    expect(screen.getByLabelText("공유 링크")).toBeInTheDocument();
  });
});

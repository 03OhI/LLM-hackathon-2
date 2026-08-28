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
  updateNotice: vi.fn(),
  createPresentationChecklistItem: vi.fn(),
  updatePresentationChecklistItem: vi.fn(),
  deletePresentationChecklistItem: vi.fn(),
  createDecision: vi.fn(),
  voteDecision: vi.fn(),
  finalizeDecision: vi.fn(),
  createMeetingNote: vi.fn(),
  updateMeetingNote: vi.fn(),
  deleteMeetingNote: vi.fn(),
}));

import { getSavedTeamSession } from "@/lib/session";
import { getRoomParticipants } from "@/lib/participants-api";
import { getRoomWorkspace, getWorkspace, startWorkspace, updateTask, createResource, deleteResource } from "@/lib/workspace-api";
import {
  updateNotice,
  voteDecision,
  finalizeDecision,
  createMeetingNote,
} from "@/lib/workspace-tools-api";
import type { Decision } from "@/lib/workspace-tools-api";
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
    final_result: null,
    my_vote_option_id: null,
    created_by: "host-participant",
    created_at: "2026-01-01T00:00:00Z",
    finalized_at: null,
    ...overrides,
  };
}

function makeWorkspace(overrides: Partial<Workspace> = {}): Workspace {
  return {
    id: "ws-1",
    session_id: "room-1",
    status: "ACTIVE",
    started_at: "2026-01-01T00:00:00Z",
    notice: null,
    deadline_at: null,
    presentation_order: null,
    tasks: [makeTask()],
    resources: [],
    meeting_notes: [],
    presentation_checklist: [],
    decisions: [],
    ...overrides,
  };
}

function setUrl(query: string) {
  window.history.pushState({}, "", `/workspace${query}`);
}

beforeEach(() => {
  setUrl("?sessionId=room-1");
  vi.mocked(getRoomParticipants).mockResolvedValue(participants);
});

afterEach(() => {
  vi.clearAllMocks();
});

describe("WorkspacePage room_id 기반 자동 조회", () => {
  it("관리자 시연 모드는 실제 세션 없이 협업 공간을 보여준다", async () => {
    setUrl("?mode=admin");
    vi.mocked(getSavedTeamSession).mockReturnValue(null);

    render(<WorkspacePage />);

    expect(await screen.findByText("이제 함께 만들어 볼까요?")).toBeInTheDocument();
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

    expect(await screen.findByText("이제 함께 만들어 볼까요?")).toBeInTheDocument();
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
    await screen.findByText("이제 함께 만들어 볼까요?");

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
    await screen.findByText("이제 함께 만들어 볼까요?");

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

describe("WorkspacePage 관리자 시연 모드 — 확장 기능은 전부 로컬 상태로 동작한다", () => {
  it("시연 기본 데이터(공지/타이머/체크리스트/의사결정/메모/할일/링크)가 전부 표시된다", async () => {
    setUrl("?mode=admin");
    vi.mocked(getSavedTeamSession).mockReturnValue(null);

    render(<WorkspacePage />);

    expect(await screen.findByText("오늘 17시까지 기능 통합 완료")).toBeInTheDocument();
    expect(screen.getByText("발표 순서: 3번째 발표")).toBeInTheDocument();
    expect(screen.getByText("25:00")).toBeInTheDocument(); // 타이머
    expect(screen.getByText("2/4개 완료")).toBeInTheDocument(); // 체크리스트
    expect(screen.getByText("서비스명 정하기")).toBeInTheDocument(); // 의사결정
    expect(screen.getByText("발표 리허설 회의")).toBeInTheDocument(); // 회의 메모
    expect(screen.getByText("발표 자료의 핵심 한 문장 정하기")).toBeInTheDocument(); // 할 일
    expect(screen.getAllByText("팀 GitHub 저장소").length).toBeGreaterThan(0); // 링크

    // 관리자 모드는 어떤 워크스페이스 확장 기능 API도 호출하지 않는다.
    expect(updateNotice).not.toHaveBeenCalled();
    expect(voteDecision).not.toHaveBeenCalled();
    expect(finalizeDecision).not.toHaveBeenCalled();
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

    // 관리자 모드는 방장 role이어도 투표+확정을 모두 시연할 수 있다.
    await user.click(screen.getAllByRole("button", { name: "투표" })[0]);
    expect(await screen.findByText("투표함")).toBeInTheDocument();

    await user.click(screen.getAllByRole("button", { name: "이 선택지로 확정" })[0]);
    expect(await screen.findByText(/최종 결정:/)).toBeInTheDocument();

    expect(updateNotice).not.toHaveBeenCalled();
    expect(voteDecision).not.toHaveBeenCalled();
    expect(finalizeDecision).not.toHaveBeenCalled();
  });
});

describe("WorkspacePage 실제 모드 — 확장 기능 API 연동", () => {
  it("워크스페이스가 열리면 GET /workspaces/{id} 응답 그대로 공지/체크리스트/의사결정/메모를 표시한다", async () => {
    vi.mocked(getSavedTeamSession).mockReturnValue(hostSession);
    vi.mocked(getRoomWorkspace).mockResolvedValue({ status: "ACTIVE", workspace_id: "ws-1" });
    vi.mocked(getWorkspace).mockResolvedValue(
      makeWorkspace({
        notice: "오늘 17시까지 기능 통합 완료",
        deadline_at: "2026-08-29T17:00:00Z",
        presentation_order: "3번째 발표",
        decisions: [makeDecisionRecord()],
      }),
    );

    render(<WorkspacePage />);

    expect(await screen.findByText("오늘 17시까지 기능 통합 완료")).toBeInTheDocument();
    expect(screen.getByText("서비스명 정하기")).toBeInTheDocument();
    // getWorkspace 한 번으로 전부 채워진다 — 부가 기능마다 별도 GET을 하지 않는다.
    expect(getWorkspace).toHaveBeenCalledTimes(1);
  });

  it("공지가 없으면(null) '등록된 공지가 없어요'를 보여준다 — 별도 GET 실패로 처리하지 않는다", async () => {
    vi.mocked(getSavedTeamSession).mockReturnValue(hostSession);
    vi.mocked(getRoomWorkspace).mockResolvedValue({ status: "ACTIVE", workspace_id: "ws-1" });
    vi.mocked(getWorkspace).mockResolvedValue(makeWorkspace());

    render(<WorkspacePage />);
    await screen.findByText("이제 함께 만들어 볼까요?");

    expect(screen.getByText("등록된 공지가 없어요.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "공지 수정" })).toBeInTheDocument();
  });

  it("팀원 시점에서 투표 버튼을 누르면 voteDecision이 호출되고, 방장 시점에는 투표 버튼이 없다", async () => {
    vi.mocked(getRoomWorkspace).mockResolvedValue({ status: "ACTIVE", workspace_id: "ws-1" });
    vi.mocked(getWorkspace).mockResolvedValue(makeWorkspace({ decisions: [makeDecisionRecord()] }));
    vi.mocked(voteDecision).mockResolvedValue(makeDecisionRecord({ my_vote_option_id: "opt-1" }));

    vi.mocked(getSavedTeamSession).mockReturnValue(memberSession);
    const { unmount } = render(<WorkspacePage />);
    const voteButton = (await screen.findAllByRole("button", { name: "투표" }))[0];
    fireEvent.click(voteButton);
    await waitFor(() => expect(voteDecision).toHaveBeenCalledWith("decision-1", "opt-1"));
    unmount();

    vi.mocked(getSavedTeamSession).mockReturnValue(hostSession);
    render(<WorkspacePage />);
    await screen.findByText("서비스명 정하기");
    expect(screen.queryByRole("button", { name: "투표" })).not.toBeInTheDocument();
  });

  it("팀원에게는 확정 버튼이 보이지 않고, 방장에게는 보인다", async () => {
    vi.mocked(getRoomWorkspace).mockResolvedValue({ status: "ACTIVE", workspace_id: "ws-1" });
    vi.mocked(getWorkspace).mockResolvedValue(makeWorkspace({ decisions: [makeDecisionRecord()] }));

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

  it("회의 메모를 추가하면 createMeetingNote가 content/next_action 필드로 호출된다", async () => {
    const user = userEvent.setup();
    vi.mocked(getSavedTeamSession).mockReturnValue(hostSession);
    vi.mocked(getRoomWorkspace).mockResolvedValue({ status: "ACTIVE", workspace_id: "ws-1" });
    vi.mocked(getWorkspace).mockResolvedValue(makeWorkspace());
    vi.mocked(createMeetingNote).mockResolvedValue({
      id: "note-1",
      title: "킥오프",
      content: "역할 분담",
      next_action: null,
      created_by: "host-participant",
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    });

    render(<WorkspacePage />);
    await screen.findByText("이제 함께 만들어 볼까요?");

    await user.click(screen.getByRole("button", { name: "새 회의 메모 추가" }));
    await user.type(screen.getByLabelText("메모 제목"), "킥오프");
    await user.click(screen.getByRole("button", { name: "저장" }));

    await waitFor(() =>
      expect(createMeetingNote).toHaveBeenCalledWith("ws-1", { title: "킥오프", content: "", next_action: null }),
    );
  });

  it("의사결정 액션이 실패해도 오류는 의사결정 카드 안에만 표시되고 다른 카드는 계속 쓸 수 있다", async () => {
    vi.mocked(getSavedTeamSession).mockReturnValue(memberSession);
    vi.mocked(getRoomWorkspace).mockResolvedValue({ status: "ACTIVE", workspace_id: "ws-1" });
    vi.mocked(getWorkspace).mockResolvedValue(makeWorkspace({ decisions: [makeDecisionRecord()] }));
    vi.mocked(voteDecision).mockRejectedValue(new ApiError("DECISION_ALREADY_FINALIZED", "이미 확정된 안건이에요.", 409));

    render(<WorkspacePage />);
    const voteButton = (await screen.findAllByRole("button", { name: "투표" }))[0];
    fireEvent.click(voteButton);

    expect(await screen.findByText("이미 확정된 안건이에요.")).toBeInTheDocument();
    // 다른 카드(공동 할 일)는 여전히 정상 노출된다.
    expect(screen.getByLabelText("공동 할 일")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "할 일 추가" })).toBeInTheDocument();
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

    expect(await screen.findByText("이제 함께 만들어 볼까요?")).toBeInTheDocument();
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

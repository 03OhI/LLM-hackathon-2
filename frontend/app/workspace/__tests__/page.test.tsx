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

import { getSavedTeamSession } from "@/lib/session";
import { getRoomParticipants } from "@/lib/participants-api";
import { getRoomWorkspace, getWorkspace, startWorkspace, updateTask, createResource, deleteResource } from "@/lib/workspace-api";
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
});

afterEach(() => {
  vi.clearAllMocks();
});

describe("WorkspacePage room_id 기반 자동 조회", () => {
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

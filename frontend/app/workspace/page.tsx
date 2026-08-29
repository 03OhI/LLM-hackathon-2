"use client";

import Image from "next/image";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

import { friendlyErrorMessage } from "@/lib/api";
import { RoomParticipant, getRoomParticipants } from "@/lib/participants-api";
import { getSavedTeamSession, TeamSession } from "@/lib/session";
import { usePolling } from "@/lib/use-polling";
import {
  PROVIDER_LABEL,
  ResourceLink,
  ResourceProvider,
  Task,
  TaskStatus,
  Workspace,
  createResource,
  createTask,
  deleteResource,
  deleteTask,
  getRoomWorkspace,
  getWorkspace,
  startWorkspace,
  updateTask,
} from "@/lib/workspace-api";
import {
  ChecklistItemType,
  Decision,
  DecisionOption,
  MeetingNote,
  PresentationChecklistItem,
  WorkspaceNotice,
  createDecision,
  createMeetingNote,
  createPresentationChecklistItem,
  deleteMeetingNote,
  deletePresentationChecklistItem,
  finalizeDecision,
  updateMeetingNote,
  updateNotice,
  updatePresentationChecklistItem,
  voteDecision,
} from "@/lib/workspace-tools-api";
import { DecisionBoard } from "./components/DecisionBoard";
import { FocusTimer } from "./components/FocusTimer";
import { MeetingNotes } from "./components/MeetingNotes";
import { NoticeCard } from "./components/NoticeCard";
import { DEFAULT_CHECKLIST_LABELS, PresentationChecklist } from "./components/PresentationChecklist";
import { QuickLinks } from "./components/QuickLinks";

const POLL_INTERVAL_MS = 4000;
const TASK_STATUSES: TaskStatus[] = ["TODO", "IN_PROGRESS", "DONE"];
const TASK_STATUS_LABEL: Record<TaskStatus, string> = { TODO: "할 일", IN_PROGRESS: "진행 중", DONE: "완료" };
const PROVIDERS: ResourceProvider[] = ["GITHUB", "FIGMA", "NOTION", "GOOGLE_DRIVE", "DEPLOYMENT", "OTHER"];

// 히어로의 진행률 요약 — 이미 받은 workspace 데이터에서만 계산한다(새 API 없음).
function WorkspaceHero({
  teamName,
  checklist,
  tasks,
  decisions,
}: {
  teamName: string;
  checklist: PresentationChecklistItem[];
  tasks: Task[];
  decisions: Decision[];
}) {
  const doneChecklist = checklist.filter((item) => item.completed).length;
  const inProgressTasks = tasks.filter((task) => task.status === "IN_PROGRESS").length;
  const openDecisions = decisions.filter((decision) => decision.status === "OPEN").length;

  return (
    <header className="workspace-hero">
      <div className="workspace-hero-copy">
        <p className="result-eyebrow">협업 워크스페이스</p>
        <h1>이제 함께 만들어 볼까요?</h1>
        <p className="workspace-hero-team">
          <b>{teamName}</b> 팀의 협업 공간이에요. 오늘의 흐름을 한곳에서 맞춰 봐요.
        </p>
        <div className="workspace-progress-summary" aria-label="현재 협업 현황">
          <span className="workspace-summary-chip">
            발표 준비 <b>{doneChecklist}</b> / {checklist.length}
          </span>
          <span className="workspace-summary-chip">
            진행 중 할 일 <b>{inProgressTasks}</b>개
          </span>
          <span className="workspace-summary-chip">
            열린 결정 <b>{openDecisions}</b>개
          </span>
        </div>
      </div>
      <div className="workspace-hero-visual" aria-hidden="true">
        <span className="workspace-hero-spark workspace-hero-spark-coral">+</span>
        <span className="workspace-hero-spark workspace-hero-spark-sage">+</span>
        <span className="workspace-hero-spark workspace-hero-spark-blue">+</span>
        <Image src="/duck-run-3.png" alt="" width={176} height={176} priority />
      </div>
    </header>
  );
}

export default function WorkspacePage() {
  const [session, setSession] = useState<TeamSession | null | undefined>(undefined);
  const [roomId, setRoomId] = useState<string | null>(null);
  const [administratorMode, setAdministratorMode] = useState(false);

  useEffect(() => {
    // 세션/roomId는 브라우저 storage·URL에만 있어 서버 렌더 시점엔 알 수 없다. 지연
    // 초기화 대신 마운트 후 채우는 이 관례는 서버-클라이언트 하이드레이션 불일치를
    // 피하기 위함이다(기존 survey/results 페이지와 동일).
    const saved = getSavedTeamSession();
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setSession(saved);
    const params = new URLSearchParams(window.location.search);
    setAdministratorMode(params.get("mode") === "admin");
    const fromQuery = params.get("sessionId");
    setRoomId(fromQuery ?? saved?.sessionId ?? null);
  }, []);

  return (
    <main className="survey-shell results-shell workspace-shell">
      <nav className="survey-nav result-nav">
        <Link className="survey-home" href="/" aria-label="홈으로">
          ⌂
        </Link>
        <Image
          className="tmti-header-brand"
          src="/tmti-survey-logo.png"
          alt="TMTI 오리 로고"
          width={196}
          height={110}
          priority
        />
      </nav>
      <div className="tmti-flow-header">
        <span className="tmti-flow-stage">
          <b>4 / 4</b> · 협업 시작
        </span>
      </div>
      {session === undefined ? (
        <LoadingCard />
      ) : administratorMode ? (
        <AdminDemoWorkspaceView />
      ) : session === null ? (
        <InfoCard title="세션 정보가 없어요." body="초대 링크로 다시 들어와 주세요." />
      ) : !roomId ? (
        <InfoCard title="방 정보가 없어요." body="퀘스트 화면에서 다시 이동해 주세요." />
      ) : (
        <WorkspaceView session={session} roomId={roomId} />
      )}
    </main>
  );
}

// ──────────────────────────────────────────────
// 관리자 시연 모드 — 백엔드 없이 전부 로컬 상태로 동작한다.
// ──────────────────────────────────────────────

const ADMIN_DEMO_SESSION: TeamSession = {
  sessionId: "admin-demo-room",
  inviteToken: "admin-demo",
  teamName: "TMTI 데모 팀",
  expectedMembers: 4,
  participantId: "admin-demo-host",
  isHost: true,
};

const ADMIN_DEMO_PARTICIPANTS: RoomParticipant[] = [
  { participant_id: "admin-demo-host", nickname: "나" },
  { participant_id: "admin-demo-member-1", nickname: "민지" },
  { participant_id: "admin-demo-member-2", nickname: "지훈" },
  { participant_id: "admin-demo-member-3", nickname: "서연" },
];

function adminDemoDeadline(): string {
  return new Date(Date.now() + 3 * 60 * 60 * 1000).toISOString();
}

const DEFAULT_CHECKLIST_TYPES: ChecklistItemType[] = ["DEMO_URL", "SLIDES", "SCRIPT", "BACKUP"];

function AdminDemoWorkspaceView() {
  const [notice, setNotice] = useState<WorkspaceNotice>({
    notice: "오늘 17시까지 기능 통합 완료",
    deadline_at: adminDemoDeadline(),
    presentation_order: "3번째 발표",
  });

  const [checklist, setChecklist] = useState<PresentationChecklistItem[]>(
    DEFAULT_CHECKLIST_LABELS.map((label, index) => ({
      id: `admin-demo-checklist-${index}`,
      item_type: DEFAULT_CHECKLIST_TYPES[index],
      label,
      url: null,
      completed: index < 2,
      completed_by: index < 2 ? "admin-demo-host" : null,
      created_by: "admin-demo-host",
      created_at: "2026-08-29T00:00:00Z",
      updated_at: "2026-08-29T00:00:00Z",
    })),
  );

  const [decisions, setDecisions] = useState<Decision[]>([
    {
      id: "admin-demo-decision-1",
      title: "서비스명 정하기",
      description: "발표에서 부를 최종 서비스 이름을 정해요.",
      options: [
        { id: "admin-demo-option-1", label: "TMTI", vote_count: 2 },
        { id: "admin-demo-option-2", label: "ChemLink", vote_count: 1 },
        { id: "admin-demo-option-3", label: "Vibemap", vote_count: 0 },
      ],
      status: "OPEN",
      final_result: null,
      my_vote_option_id: "admin-demo-option-1",
      created_by: "admin-demo-host",
      created_at: "2026-08-29T00:00:00Z",
      finalized_at: null,
    },
  ]);

  const [notes, setNotes] = useState<MeetingNote[]>([
    {
      id: "admin-demo-note-1",
      title: "발표 리허설 회의",
      content: "발표 순서와 역할 분담을 정하고, 시연 시나리오를 처음부터 끝까지 한 번 맞춰봤어요.",
      next_action: "각자 맡은 파트 대본 다듬기",
      created_by: "admin-demo-host",
      created_at: "2026-08-29T00:00:00Z",
      updated_at: "2026-08-29T00:00:00Z",
    },
  ]);

  const [tasks, setTasks] = useState<Task[]>([
    {
      id: "admin-demo-task-1",
      title: "발표 자료의 핵심 한 문장 정하기",
      status: "IN_PROGRESS",
      assignee_participant_id: "admin-demo-member-1",
      due_at: null,
      created_by: "admin-demo-host",
      created_at: "2026-08-29T00:00:00Z",
      updated_at: "2026-08-29T00:00:00Z",
    },
    {
      id: "admin-demo-task-2",
      title: "백업 발표 화면 녹화하기",
      status: "TODO",
      assignee_participant_id: null,
      due_at: null,
      created_by: "admin-demo-host",
      created_at: "2026-08-29T00:00:00Z",
      updated_at: "2026-08-29T00:00:00Z",
    },
  ]);

  const [resources, setResources] = useState<ResourceLink[]>([
    {
      id: "admin-demo-resource-1",
      title: "팀 GitHub 저장소",
      url: "https://github.com/03OhI/LLM-hackathon-2",
      provider: "GITHUB",
      created_by: "admin-demo-host",
      created_at: "2026-08-29T00:00:00Z",
    },
  ]);

  const [presetProvider, setPresetProvider] = useState<{ provider: ResourceProvider; token: number } | null>(null);

  return (
    <section className="result-report workspace-card-shell survey-card-enter">
      <WorkspaceHero teamName={ADMIN_DEMO_SESSION.teamName} checklist={checklist} tasks={tasks} decisions={decisions} />
      <div className="workspace-grid">
        <NoticeCard
          notice={notice}
          isHost
          pending={false}
          onSave={(input) => setNotice((current) => ({ ...current, ...input }))}
        />
        <FocusTimer />
        <PresentationChecklist
          items={checklist}
          pendingAction={null}
          canManage={() => true}
          onToggle={(itemId, completed) =>
            setChecklist((current) =>
              current.map((item) =>
                item.id === itemId
                  ? { ...item, completed, completed_by: completed ? ADMIN_DEMO_SESSION.participantId : null }
                  : item,
              ),
            )
          }
          onUrlChange={(itemId, url) =>
            setChecklist((current) => current.map((item) => (item.id === itemId ? { ...item, url } : item)))
          }
          onAdd={(label, itemType) =>
            setChecklist((current) => [
              ...current,
              {
                id: `admin-demo-checklist-${Date.now()}`,
                item_type: itemType,
                label,
                url: null,
                completed: false,
                completed_by: null,
                created_by: ADMIN_DEMO_SESSION.participantId,
                created_at: new Date().toISOString(),
                updated_at: new Date().toISOString(),
              },
            ])
          }
          onDelete={(itemId) => setChecklist((current) => current.filter((item) => item.id !== itemId))}
        />
        <DecisionBoard
          decisions={decisions}
          canVote
          canFinalize
          pendingAction={null}
          onCreate={(input) =>
            setDecisions((current) => [
              {
                id: `admin-demo-decision-${Date.now()}`,
                title: input.title,
                description: input.description,
                options: input.options.map((label, index) => ({
                  id: `admin-demo-decision-${Date.now()}-option-${index}`,
                  label,
                  vote_count: 0,
                })),
                status: "OPEN",
                final_result: null,
                my_vote_option_id: null,
                created_by: ADMIN_DEMO_SESSION.participantId,
                created_at: new Date().toISOString(),
                finalized_at: null,
              },
              ...current,
            ])
          }
          onVote={(decisionId, optionId) =>
            setDecisions((current) =>
              current.map((decision) => {
                if (decision.id !== decisionId) return decision;
                const alreadyVoted = decision.my_vote_option_id;
                const options: DecisionOption[] = decision.options.map((option) => {
                  if (option.id === optionId) return { ...option, vote_count: option.vote_count + 1 };
                  if (option.id === alreadyVoted) return { ...option, vote_count: Math.max(0, option.vote_count - 1) };
                  return option;
                });
                return { ...decision, options, my_vote_option_id: optionId };
              }),
            )
          }
          onFinalize={(decisionId, finalResult) =>
            setDecisions((current) =>
              current.map((decision) =>
                decision.id === decisionId
                  ? { ...decision, status: "FINALIZED", final_result: finalResult, finalized_at: new Date().toISOString() }
                  : decision,
              ),
            )
          }
        />
        <TaskPanel
          tasks={tasks}
          session={ADMIN_DEMO_SESSION}
          participants={ADMIN_DEMO_PARTICIPANTS}
          pendingAction={null}
          canManage={() => true}
          onCreate={(input) => {
            const now = new Date().toISOString();
            setTasks((current) => [
              ...current,
              {
                id: `admin-demo-task-${Date.now()}`,
                title: input.title,
                status: "TODO",
                assignee_participant_id: input.assignee_participant_id ?? null,
                due_at: input.due_at ?? null,
                created_by: ADMIN_DEMO_SESSION.participantId,
                created_at: now,
                updated_at: now,
              },
            ]);
          }}
          onUpdate={(taskId, input) => {
            setTasks((current) =>
              current.map((task) =>
                task.id === taskId
                  ? { ...task, ...input, updated_at: new Date().toISOString() }
                  : task,
              ),
            );
          }}
          onDelete={(taskId) => setTasks((current) => current.filter((task) => task.id !== taskId))}
        />
        <MeetingNotes
          notes={notes}
          pendingAction={null}
          canManage={() => true}
          onCreate={(input) => {
            const now = new Date().toISOString();
            setNotes((current) => [
              { id: `admin-demo-note-${Date.now()}`, ...input, created_by: ADMIN_DEMO_SESSION.participantId, created_at: now, updated_at: now },
              ...current,
            ]);
          }}
          onUpdate={(noteId, input) =>
            setNotes((current) =>
              current.map((note) => (note.id === noteId ? { ...note, ...input, updated_at: new Date().toISOString() } : note)),
            )
          }
          onDelete={(noteId) => setNotes((current) => current.filter((note) => note.id !== noteId))}
        />
        <QuickLinks resources={resources} onConnect={(provider) => setPresetProvider({ provider, token: Date.now() })} />
        <ResourcePanel
          resources={resources}
          pendingAction={null}
          canManage={() => true}
          presetProvider={presetProvider}
          onCreate={(input) => {
            setResources((current) => [
              ...current,
              {
                id: `admin-demo-resource-${Date.now()}`,
                ...input,
                created_by: ADMIN_DEMO_SESSION.participantId,
                created_at: new Date().toISOString(),
              },
            ]);
          }}
          onDelete={(resourceId) =>
            setResources((current) => current.filter((resource) => resource.id !== resourceId))
          }
        />
      </div>
    </section>
  );
}

function LoadingCard() {
  return (
    <section className="result-message">
      <span className="result-loader" aria-hidden="true" />
      <h1>불러오는 중이에요.</h1>
    </section>
  );
}

function InfoCard({ title, body }: { title: string; body: string }) {
  return (
    <section className="result-message">
      <h1>{title}</h1>
      <p>{body}</p>
      <Link href="/quest" className="button-next">
        퀘스트로 돌아가기
      </Link>
    </section>
  );
}

// ──────────────────────────────────────────────
// 실제 세션 — 백엔드 API 연동
// ──────────────────────────────────────────────

function WorkspaceView({ session, roomId }: { session: TeamSession; roomId: string }) {
  const [workspaceId, setWorkspaceId] = useState<string | null>(null);
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [participants, setParticipants] = useState<RoomParticipant[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const pendingRef = useRef<string | null>(null);
  const [pendingAction, setPendingAction] = useState<string | null>(null);

  // 카드별로 독립된 오류 상태를 둔다 — 회의 메모 저장이 실패해도 체크리스트/의사결정/
  // 할 일/링크 카드는 계속 정상 동작해야 한다(부가 기능 실패가 전체 화면을 가리지 않음).
  const [startError, setStartError] = useState<string | null>(null);
  const [noticeActionError, setNoticeActionError] = useState<string | null>(null);
  const [checklistActionError, setChecklistActionError] = useState<string | null>(null);
  const [decisionActionError, setDecisionActionError] = useState<string | null>(null);
  const [taskActionError, setTaskActionError] = useState<string | null>(null);
  const [noteActionError, setNoteActionError] = useState<string | null>(null);
  const [resourceActionError, setResourceActionError] = useState<string | null>(null);
  const [presetProvider, setPresetProvider] = useState<{ provider: ResourceProvider; token: number } | null>(null);

  // 팀원 목록은 자주 바뀌지 않으므로 최초 1회만 가져온다(4초 폴링 대상이 아니다).
  useEffect(() => {
    getRoomParticipants(roomId)
      .then(setParticipants)
      .catch(() => {
        /* 담당자 표시는 부가 기능이라 실패해도 워크스페이스 자체는 계속 보여준다 */
      });
  }, [roomId]);

  // GET /workspaces/{id}(getWorkspace) 응답 하나에 notice/tasks/resources/meeting_notes/
  // presentation_checklist/decisions가 모두 담겨 온다 — 부가 기능마다 별도로 GET하지 않는다.
  const refresh = useCallback(async () => {
    try {
      const roomWorkspace = await getRoomWorkspace(roomId);
      if (roomWorkspace.status === "LOCKED" || !roomWorkspace.workspace_id) {
        setWorkspaceId(null);
        setWorkspace(null);
        setLoadError(null);
        return;
      }
      setWorkspaceId(roomWorkspace.workspace_id);
      const full = await getWorkspace(roomWorkspace.workspace_id);
      setWorkspace(full);
      setLoadError(null);
    } catch (error) {
      setLoadError(friendlyErrorMessage(error));
    } finally {
      setLoading(false);
    }
  }, [roomId]);

  useEffect(() => {
    // 마운트 시 최초 1회 조회 — refresh 내부의 setState는 fetch 완료 후 비동기로
    // 실행되므로 렌더 중 동기 setState가 아니다(기존 results 페이지와 동일한 관례).
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void refresh();
  }, [refresh]);

  usePolling(refresh, POLL_INTERVAL_MS, true);

  // 카드마다 다른 setState로 오류를 보내는 것만 다르고, 그 외 로직(단일 진행,
  // 성공 시 getWorkspace 재조회)은 모든 액션이 동일하게 공유한다.
  const runAction = useCallback(
    async (key: string, action: () => Promise<unknown>, onError: (message: string) => void) => {
      if (pendingRef.current) return;
      pendingRef.current = key;
      setPendingAction(key);
      onError("");
      try {
        await action();
        await refresh();
      } catch (error) {
        onError(friendlyErrorMessage(error));
      } finally {
        pendingRef.current = null;
        setPendingAction(null);
      }
    },
    [refresh],
  );

  if (loading) return <LoadingCard />;
  if (loadError) return <InfoCard title="협업 공간을 불러오지 못했어요." body={loadError} />;

  if (!workspaceId || !workspace) {
    return (
      <section className="result-message">
        <p className="result-eyebrow">협업 공간 준비 중</p>
        <h1>{session.isHost ? "협업을 시작해 주세요." : "방장이 협업을 시작하면 자동으로 열려요."}</h1>
        {session.isHost && (
          <button
            type="button"
            className="button-next"
            disabled={pendingAction === "start-workspace"}
            onClick={() => runAction("start-workspace", () => startWorkspace(roomId), setStartError)}
          >
            {pendingAction === "start-workspace" ? "시작하는 중…" : "협업 시작하기"}
          </button>
        )}
        {startError && <p className="quest-action-error">{startError}</p>}
      </section>
    );
  }

  const canManage = (createdBy: string) => session.isHost || createdBy === session.participantId;
  // 방장은 participant 레코드가 없어 투표할 수 없다(백엔드 정책) — 팀원만 투표, 방장만 확정.
  const canVote = !session.isHost;
  const canFinalize = session.isHost;
  const notice: WorkspaceNotice = {
    notice: workspace.notice,
    deadline_at: workspace.deadline_at,
    presentation_order: workspace.presentation_order,
  };

  return (
    <section className="result-report workspace-card-shell survey-card-enter">
      <WorkspaceHero
        teamName={session.teamName}
        checklist={workspace.presentation_checklist}
        tasks={workspace.tasks}
        decisions={workspace.decisions}
      />
      <div className="workspace-grid">
        <NoticeCard
          notice={notice}
          isHost={session.isHost}
          pending={pendingAction === "save-notice"}
          error={noticeActionError}
          onSave={(input) => runAction("save-notice", () => updateNotice(workspace.id, input), setNoticeActionError)}
        />

        <FocusTimer />

        <PresentationChecklist
          items={workspace.presentation_checklist}
          pendingAction={pendingAction}
          canManage={canManage}
          error={checklistActionError}
          onToggle={(itemId, completed) =>
            runAction(
              `toggle-checklist-${itemId}`,
              () => updatePresentationChecklistItem(itemId, { completed }),
              setChecklistActionError,
            )
          }
          onUrlChange={(itemId, url) =>
            runAction(`url-checklist-${itemId}`, () => updatePresentationChecklistItem(itemId, { url }), setChecklistActionError)
          }
          onAdd={(label, itemType) =>
            runAction(
              "create-checklist-item",
              () => createPresentationChecklistItem(workspace.id, { item_type: itemType, label }),
              setChecklistActionError,
            )
          }
          onDelete={(itemId) =>
            runAction(`delete-checklist-${itemId}`, () => deletePresentationChecklistItem(itemId), setChecklistActionError)
          }
        />

        <DecisionBoard
          decisions={workspace.decisions}
          canVote={canVote}
          canFinalize={canFinalize}
          pendingAction={pendingAction}
          error={decisionActionError}
          onCreate={(input) => runAction("create-decision", () => createDecision(workspace.id, input), setDecisionActionError)}
          onVote={(decisionId, optionId) =>
            runAction(`vote-${decisionId}`, () => voteDecision(decisionId, optionId), setDecisionActionError)
          }
          onFinalize={(decisionId, finalResult) =>
            runAction(`finalize-${decisionId}`, () => finalizeDecision(decisionId, finalResult), setDecisionActionError)
          }
        />

        <TaskPanel
          tasks={workspace.tasks}
          session={session}
          participants={participants}
          pendingAction={pendingAction}
          canManage={canManage}
          error={taskActionError}
          onCreate={(input) => runAction("create-task", () => createTask(workspace.id, input), setTaskActionError)}
          onUpdate={(taskId, input) => runAction(`update-task-${taskId}`, () => updateTask(taskId, input), setTaskActionError)}
          onDelete={(taskId) => runAction(`delete-task-${taskId}`, () => deleteTask(taskId), setTaskActionError)}
        />

        <MeetingNotes
          notes={workspace.meeting_notes}
          pendingAction={pendingAction}
          canManage={canManage}
          error={noteActionError}
          onCreate={(input) => runAction("create-note", () => createMeetingNote(workspace.id, input), setNoteActionError)}
          onUpdate={(noteId, input) => runAction(`update-note-${noteId}`, () => updateMeetingNote(noteId, input), setNoteActionError)}
          onDelete={(noteId) => runAction(`delete-note-${noteId}`, () => deleteMeetingNote(noteId), setNoteActionError)}
        />

        <QuickLinks resources={workspace.resources} onConnect={(provider) => setPresetProvider({ provider, token: Date.now() })} />
        <ResourcePanel
          resources={workspace.resources}
          pendingAction={pendingAction}
          canManage={canManage}
          presetProvider={presetProvider}
          error={resourceActionError}
          onCreate={(input) => runAction("create-resource", () => createResource(workspace.id, input), setResourceActionError)}
          onDelete={(resourceId) => runAction(`delete-resource-${resourceId}`, () => deleteResource(resourceId), setResourceActionError)}
        />
      </div>
    </section>
  );
}

function TaskPanel({
  tasks,
  session,
  participants,
  pendingAction,
  canManage,
  error,
  onCreate,
  onUpdate,
  onDelete,
}: {
  tasks: Task[];
  session: TeamSession;
  participants: RoomParticipant[];
  pendingAction: string | null;
  canManage: (createdBy: string) => boolean;
  error?: string | null;
  onCreate: (input: { title: string; assignee_participant_id?: string | null; due_at?: string | null }) => void;
  onUpdate: (taskId: string, input: { status?: TaskStatus; due_at?: string | null; clear_due_at?: boolean }) => void;
  onDelete: (taskId: string) => void;
}) {
  const [title, setTitle] = useState("");
  const [assignee, setAssignee] = useState<string>("none"); // "none" | "me" | participant_id
  const [dueAt, setDueAt] = useState("");

  const nicknameFor = (participantId: string | null) => {
    if (!participantId) return "미지정";
    if (participantId === session.participantId) return "나";
    return participants.find((p) => p.participant_id === participantId)?.nickname ?? "팀원";
  };

  return (
    <div className="workspace-panel" aria-label="공동 할 일">
      <h2>공동 할 일</h2>
      <form
        className="task-create-form"
        onSubmit={(event) => {
          event.preventDefault();
          if (!title.trim()) return;
          onCreate({
            title: title.trim(),
            assignee_participant_id: assignee === "none" ? null : assignee === "me" ? session.participantId : assignee,
            due_at: dueAt ? new Date(dueAt).toISOString() : null,
          });
          setTitle("");
          setAssignee("none");
          setDueAt("");
        }}
      >
        <input
          value={title}
          onChange={(event) => setTitle(event.target.value)}
          placeholder="할 일을 입력해 주세요"
          aria-label="새 할 일"
        />
        <select value={assignee} onChange={(event) => setAssignee(event.target.value)} aria-label="담당자">
          <option value="none">담당자 미지정</option>
          <option value="me">나에게 배정</option>
          {participants
            .filter((p) => p.participant_id !== session.participantId)
            .map((p) => (
              <option key={p.participant_id} value={p.participant_id}>
                {p.nickname}
              </option>
            ))}
        </select>
        <input
          type="datetime-local"
          value={dueAt}
          onChange={(event) => setDueAt(event.target.value)}
          aria-label="마감 시간(선택)"
        />
        <button type="submit" className="button-muted" disabled={pendingAction === "create-task" || !title.trim()}>
          할 일 추가
        </button>
      </form>

      {tasks.length === 0 ? (
        <p className="workspace-empty">아직 등록된 할 일이 없어요.</p>
      ) : (
        <ul className="task-list">
          {tasks.map((task) => (
            <li key={task.id} className="task-item">
              <div className="task-item-main">
                <b>{task.title}</b>
                <span className={`task-status-badge task-status-badge-${task.status.toLowerCase()}`}>
                  {TASK_STATUS_LABEL[task.status]}
                </span>
                <span className="task-assignee">{nicknameFor(task.assignee_participant_id)}</span>
                {task.due_at && <span className="task-due">마감 {formatDate(task.due_at)}</span>}
              </div>
              <div className="task-item-actions">
                {TASK_STATUSES.map((status) => (
                  <button
                    key={status}
                    type="button"
                    className={
                      task.status === status
                        ? `task-status-active task-status-active-${status.toLowerCase()}`
                        : "task-status-button"
                    }
                    disabled={pendingAction === `update-task-${task.id}`}
                    onClick={() => onUpdate(task.id, { status })}
                  >
                    {TASK_STATUS_LABEL[status]}
                  </button>
                ))}
                {canManage(task.created_by) && (
                  <button
                    type="button"
                    className="task-delete-button"
                    disabled={pendingAction === `delete-task-${task.id}`}
                    onClick={() => onDelete(task.id)}
                    aria-label={`${task.title} 삭제`}
                  >
                    삭제
                  </button>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
      {error && <p className="workspace-section-inline-error">{error}</p>}
    </div>
  );
}

function ResourcePanel({
  resources,
  pendingAction,
  canManage,
  presetProvider,
  error,
  onCreate,
  onDelete,
}: {
  resources: ResourceLink[];
  pendingAction: string | null;
  canManage: (createdBy: string) => boolean;
  presetProvider?: { provider: ResourceProvider; token: number } | null;
  error?: string | null;
  onCreate: (input: { title: string; url: string; provider: ResourceProvider }) => void;
  onDelete: (resourceId: string) => void;
}) {
  const [title, setTitle] = useState("팀 노션");
  const [url, setUrl] = useState("https://app.notion.com/p/2-3cbeb06e3d72804ebe47ea4cf5e53a1c?source=copy_link");
  const [provider, setProvider] = useState<ResourceProvider>("NOTION");
  const formRef = useRef<HTMLFormElement | null>(null);
  const titleInputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    // QuickLinks의 "연결하기" 클릭(외부 커맨드)에 반응해 폼을 세팅하는 명령형
    // 동기화다 — presetProvider.token이 바뀔 때마다(같은 provider를 다시 눌러도)
    // provider를 맞추고 스크롤/포커스한다.
    if (!presetProvider) return;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setProvider(presetProvider.provider);
    formRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
    titleInputRef.current?.focus();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [presetProvider?.token]);

  return (
    <div className="workspace-panel" aria-label="공유 링크">
      <h2>공유 링크</h2>
      <form
        ref={formRef}
        className="resource-create-form"
        onSubmit={(event) => {
          event.preventDefault();
          if (!title.trim() || !url.trim()) return;
          onCreate({ title: title.trim(), url: url.trim(), provider });
          setTitle("");
          setUrl("");
          setProvider("OTHER");
        }}
      >
        <input
          ref={titleInputRef}
          value={title}
          onChange={(event) => setTitle(event.target.value)}
          placeholder="링크 이름"
          aria-label="링크 이름"
        />
        <input value={url} onChange={(event) => setUrl(event.target.value)} placeholder="https://" aria-label="링크 주소" />
        <select value={provider} onChange={(event) => setProvider(event.target.value as ResourceProvider)} aria-label="링크 종류">
          {PROVIDERS.map((item) => (
            <option key={item} value={item}>
              {PROVIDER_LABEL[item]}
            </option>
          ))}
        </select>
        <button type="submit" className="button-muted" disabled={pendingAction === "create-resource" || !title.trim() || !url.trim()}>
          링크 추가
        </button>
      </form>

      {resources.length === 0 ? (
        <p className="workspace-empty">아직 등록된 링크가 없어요.</p>
      ) : (
        <ul className="resource-list">
          {resources.map((resource) => (
            <li key={resource.id} className="resource-item">
              <a href={resource.url} target="_blank" rel="noopener noreferrer" className="resource-link">
                <span className="resource-provider">{PROVIDER_LABEL[resource.provider]}</span>
                <b>{resource.title}</b>
              </a>
              {canManage(resource.created_by) && (
                <button
                  type="button"
                  className="task-delete-button"
                  disabled={pendingAction === `delete-resource-${resource.id}`}
                  onClick={() => onDelete(resource.id)}
                  aria-label={`${resource.title} 삭제`}
                >
                  삭제
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
      {error && <p className="workspace-section-inline-error">{error}</p>}
    </div>
  );
}

function formatDate(iso: string): string {
  try {
    const date = new Date(iso);
    return `${date.getMonth() + 1}/${date.getDate()}`;
  } catch {
    return iso;
  }
}

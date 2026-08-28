"use client";

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

const POLL_INTERVAL_MS = 4000;
const TASK_STATUSES: TaskStatus[] = ["TODO", "IN_PROGRESS", "DONE"];
const TASK_STATUS_LABEL: Record<TaskStatus, string> = { TODO: "할 일", IN_PROGRESS: "진행 중", DONE: "완료" };
const PROVIDERS: ResourceProvider[] = ["GITHUB", "FIGMA", "NOTION", "GOOGLE_DRIVE", "DEPLOYMENT", "OTHER"];

export default function WorkspacePage() {
  const [session, setSession] = useState<TeamSession | null | undefined>(undefined);
  const [roomId, setRoomId] = useState<string | null>(null);

  useEffect(() => {
    // 세션/roomId는 브라우저 storage·URL에만 있어 서버 렌더 시점엔 알 수 없다. 지연
    // 초기화 대신 마운트 후 채우는 이 관례는 서버-클라이언트 하이드레이션 불일치를
    // 피하기 위함이다(기존 survey/results 페이지와 동일).
    const saved = getSavedTeamSession();
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setSession(saved);
    const fromQuery = new URLSearchParams(window.location.search).get("sessionId");
    setRoomId(fromQuery ?? saved?.sessionId ?? null);
  }, []);

  return (
    <main className="survey-shell results-shell workspace-shell">
      <nav className="survey-nav">
        <Link className="survey-home" href="/" aria-label="홈으로">
          ⌂
        </Link>
      </nav>
      {session === undefined ? (
        <LoadingCard />
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

function WorkspaceView({ session, roomId }: { session: TeamSession; roomId: string }) {
  const [workspaceId, setWorkspaceId] = useState<string | null>(null);
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [participants, setParticipants] = useState<RoomParticipant[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const pendingRef = useRef<string | null>(null);
  const [pendingAction, setPendingAction] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  // 팀원 목록은 자주 바뀌지 않으므로 최초 1회만 가져온다(4초 폴링 대상이 아니다).
  useEffect(() => {
    getRoomParticipants(roomId)
      .then(setParticipants)
      .catch(() => {
        /* 담당자 표시는 부가 기능이라 실패해도 워크스페이스 자체는 계속 보여준다 */
      });
  }, [roomId]);

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

  const runAction = useCallback(
    async (key: string, action: () => Promise<unknown>) => {
      if (pendingRef.current) return;
      pendingRef.current = key;
      setPendingAction(key);
      setActionError(null);
      try {
        await action();
        await refresh();
      } catch (error) {
        setActionError(friendlyErrorMessage(error));
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
            onClick={() => runAction("start-workspace", () => startWorkspace(roomId))}
          >
            {pendingAction === "start-workspace" ? "시작하는 중…" : "협업 시작하기"}
          </button>
        )}
        {actionError && <p className="quest-action-error">{actionError}</p>}
      </section>
    );
  }

  const canManage = (createdBy: string) => session.isHost || createdBy === session.participantId;

  return (
    <section className="result-report workspace-card-shell survey-card-enter">
      <header className="quest-header">
        <p className="result-eyebrow">협업 워크스페이스</p>
        <h1>함께 정리하고 공유해요</h1>
      </header>
      {actionError && <p className="quest-action-error">{actionError}</p>}
      <div className="workspace-grid">
        <TaskPanel
          tasks={workspace.tasks}
          session={session}
          participants={participants}
          pendingAction={pendingAction}
          canManage={canManage}
          onCreate={(input) => runAction("create-task", () => createTask(workspace.id, input))}
          onUpdate={(taskId, input) => runAction(`update-task-${taskId}`, () => updateTask(taskId, input))}
          onDelete={(taskId) => runAction(`delete-task-${taskId}`, () => deleteTask(taskId))}
        />
        <ResourcePanel
          resources={workspace.resources}
          pendingAction={pendingAction}
          canManage={canManage}
          onCreate={(input) => runAction("create-resource", () => createResource(workspace.id, input))}
          onDelete={(resourceId) => runAction(`delete-resource-${resourceId}`, () => deleteResource(resourceId))}
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
  onCreate,
  onUpdate,
  onDelete,
}: {
  tasks: Task[];
  session: TeamSession;
  participants: RoomParticipant[];
  pendingAction: string | null;
  canManage: (createdBy: string) => boolean;
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
                <span className="task-assignee">{nicknameFor(task.assignee_participant_id)}</span>
                {task.due_at && <span className="task-due">마감 {formatDate(task.due_at)}</span>}
              </div>
              <div className="task-item-actions">
                {TASK_STATUSES.map((status) => (
                  <button
                    key={status}
                    type="button"
                    className={task.status === status ? "task-status-active" : "task-status-button"}
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
    </div>
  );
}

function ResourcePanel({
  resources,
  pendingAction,
  canManage,
  onCreate,
  onDelete,
}: {
  resources: ResourceLink[];
  pendingAction: string | null;
  canManage: (createdBy: string) => boolean;
  onCreate: (input: { title: string; url: string; provider: ResourceProvider }) => void;
  onDelete: (resourceId: string) => void;
}) {
  const [title, setTitle] = useState("");
  const [url, setUrl] = useState("");
  const [provider, setProvider] = useState<ResourceProvider>("OTHER");

  return (
    <div className="workspace-panel" aria-label="공유 링크">
      <h2>공유 링크</h2>
      <form
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
        <input value={title} onChange={(event) => setTitle(event.target.value)} placeholder="링크 이름" aria-label="링크 이름" />
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

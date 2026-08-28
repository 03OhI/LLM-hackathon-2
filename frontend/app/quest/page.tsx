"use client";

import Image from "next/image";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError, friendlyErrorMessage } from "@/lib/api";
import {
  CHECK_TYPE_LABEL,
  CHECK_TYPE_NEEDS_TEXT,
  CompletionCheckRequirement,
  QuestCurrent,
  assignQuest,
  completeQuest,
  getCurrentQuest,
  skipQuest,
  startQuest,
  submitMyResponse,
  submitTeamResult,
} from "@/lib/quest-api";
import { getSavedTeamSession, TeamSession } from "@/lib/session";
import { startWorkspace } from "@/lib/workspace-api";
import { usePolling } from "@/lib/use-polling";

const POLL_INTERVAL_MS = 4000;
const QUEST_STATUS_LABEL: Record<string, string> = {
  ASSIGNED: "배정됨",
  IN_PROGRESS: "진행 중",
  COMPLETED: "완료",
  SKIPPED: "건너뜀",
};

export default function QuestPage() {
  const [session, setSession] = useState<TeamSession | null | undefined>(undefined);
  const [administratorMode, setAdministratorMode] = useState(false);

  useEffect(() => {
    // 세션은 브라우저 storage에만 있어 서버 렌더 시점엔 알 수 없다. useState 지연
    // 초기화를 쓰면 정적 프리렌더(서버)와 클라이언트 첫 렌더 결과가 달라져 하이드레이션
    // 불일치가 생기므로, 마운트 후 한 번만 채우는 이 패턴을 그대로 둔다(기존 survey/
    // results 페이지와 동일한 관례).
    const isAdmin = new URLSearchParams(window.location.search).get("mode") === "admin";
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setAdministratorMode(isAdmin);
    setSession(getSavedTeamSession());
  }, []);

  if (session === undefined) return <QuestShell><LoadingCard /></QuestShell>;
  if (administratorMode) return <QuestShell><AdminDemoQuestView /></QuestShell>;
  if (session === null) return <QuestShell><SessionMissingCard /></QuestShell>;

  return (
    <QuestShell>
      <QuestView session={session} />
    </QuestShell>
  );
}

const ADMIN_DEMO_SESSION: TeamSession = {
  sessionId: "admin-demo-room",
  inviteToken: "admin-demo",
  teamName: "TMTI 데모 팀",
  expectedMembers: 4,
  participantId: "admin-demo-host",
  isHost: true,
};

const ADMIN_DEMO_QUEST: QuestCurrent = {
  quest_id: "WORK_STYLE_BALANCE_GAME",
  title: "마감 24시간 전, 우리 팀의 선택은?",
  summary: "완성도와 휴식 사이에서 각자의 작업 스타일을 가볍게 확인해요.",
  duration_minutes: 6,
  steps: [
    "80%에서 마무리하고 다 같이 쉬기와 밤새서 100% 만들기 중 하나를 고릅니다.",
    "전원이 선택한 이유를 한 문장씩 이야기합니다.",
    "답이 가장 갈린 지점 하나만 짚고 웃으며 마무리합니다.",
  ],
  materials: ["팀 채팅방 또는 메모장", "서로의 답을 들을 열린 마음"],
  deliverable: "우리 팀의 마감 스타일 한 줄",
  assignment: {
    id: "admin-demo-assignment",
    status: "ASSIGNED",
    assignment_source: "AGENT",
    reason: "계획을 세우는 힘과 빠르게 움직이는 에너지가 함께 보여, 서로의 마감 기준을 먼저 맞춰보는 퀘스트를 골랐어요.",
    intro_message: "본격적인 협업 전에 우리 팀의 마감 본능부터 확인해볼까요?",
    assigned_at: "2026-08-29T00:00:00Z",
    started_at: null,
    completed_at: null,
  },
  my_response_status: null,
  team_completion_status: { satisfied: false, unmet_check_types: ["TEXT_SUBMIT"] },
  completion_requirements: {
    member_checks: [],
    team_checks: [{ type: "TEXT_SUBMIT", min_count: 1 }],
  },
};

function AdminDemoQuestView() {
  const [quest, setQuest] = useState<QuestCurrent>(ADMIN_DEMO_QUEST);
  const [pendingAction, setPendingAction] = useState<string | null>(null);

  const runAction = useCallback(async (key: string, action: () => Promise<QuestCurrent>) => {
    // 관리자 시연에서는 실제 API 액션 대신 아래의 로컬 상태 전이를 사용한다.
    void action;
    setPendingAction(key);
    await Promise.resolve();
    setQuest((current) => {
      if (key === "start") {
        return {
          ...current,
          assignment: {
            ...current.assignment,
            status: "IN_PROGRESS",
            started_at: new Date().toISOString(),
          },
        };
      }
      if (key.startsWith("team-")) {
        return {
          ...current,
          team_completion_status: { satisfied: true, unmet_check_types: [] },
        };
      }
      if (key === "complete" || key === "skip") {
        return {
          ...current,
          assignment: {
            ...current.assignment,
            status: key === "complete" ? "COMPLETED" : "SKIPPED",
            completed_at: new Date().toISOString(),
          },
        };
      }
      return current;
    });
    setPendingAction(null);
  }, []);

  return (
    <QuestCard
      quest={quest}
      session={ADMIN_DEMO_SESSION}
      pendingAction={pendingAction}
      actionError={null}
      runAction={runAction}
      onHostGoWorkspace={async () => {
        window.location.assign("/workspace?mode=admin");
      }}
    />
  );
}

function QuestShell({ children }: { children: React.ReactNode }) {
  return (
    <main className="survey-shell results-shell quest-shell">
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
          <b>3 / 4</b> · 아이스브레이킹
        </span>
        <p className="tmti-flow-caption">협업 전에 서로의 방식을 가볍게 알아보세요.</p>
      </div>
      {children}
    </main>
  );
}

function QuestView({ session }: { session: TeamSession }) {
  const [quest, setQuest] = useState<QuestCurrent | null>(null);
  const [notAssignedYet, setNotAssignedYet] = useState(false);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<ApiError | null>(null);
  const [pendingAction, setPendingAction] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const pendingRef = useRef<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const next = await getCurrentQuest(session.sessionId);
      setQuest(next);
      setNotAssignedYet(false);
      setLoadError(null);
    } catch (error) {
      if (error instanceof ApiError && error.code === "NO_ACTIVE_QUEST") {
        setQuest(null);
        setNotAssignedYet(true);
        setLoadError(null);
      } else {
        setLoadError(error instanceof ApiError ? error : new ApiError("UNKNOWN_ERROR", "", 0));
      }
    } finally {
      setLoading(false);
    }
  }, [session.sessionId]);

  useEffect(() => {
    // 마운트 시 최초 1회 조회 — refresh 내부의 setState는 fetch 완료 후 비동기로
    // 실행되므로 렌더 중 동기 setState가 아니다(기존 results 페이지와 동일한 관례).
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void refresh();
  }, [refresh]);

  usePolling(refresh, POLL_INTERVAL_MS, true);

  const runAction = useCallback(async (key: string, action: () => Promise<QuestCurrent>) => {
    if (pendingRef.current) return; // 이미 처리 중이면 중복 클릭 무시
    pendingRef.current = key;
    setPendingAction(key);
    setActionError(null);
    try {
      const next = await action();
      setQuest(next);
      setNotAssignedYet(false);
    } catch (error) {
      setActionError(friendlyErrorMessage(error));
    } finally {
      pendingRef.current = null;
      setPendingAction(null);
    }
  }, []);

  const handleHostGoWorkspace = useCallback(async () => {
    if (pendingRef.current) return;
    pendingRef.current = "workspace";
    setPendingAction("workspace");
    setActionError(null);
    try {
      await startWorkspace(session.sessionId);
      window.location.assign(`/workspace?sessionId=${encodeURIComponent(session.sessionId)}`);
    } catch (error) {
      setActionError(friendlyErrorMessage(error));
      pendingRef.current = null;
      setPendingAction(null);
    }
  }, [session.sessionId]);

  if (loading) return <LoadingCard />;
  if (loadError) return <ErrorCard message={friendlyErrorMessage(loadError)} onRetry={refresh} />;

  if (notAssignedYet || !quest) {
    return (
      <NotAssignedCard
        isHost={session.isHost}
        pending={pendingAction === "assign"}
        error={actionError}
        onAssign={() => runAction("assign", () => assignQuest(session.sessionId))}
      />
    );
  }

  return (
    <QuestCard
      quest={quest}
      session={session}
      pendingAction={pendingAction}
      actionError={actionError}
      runAction={runAction}
      onHostGoWorkspace={handleHostGoWorkspace}
    />
  );
}

function LoadingCard() {
  return (
    <section className="result-message">
      <span className="result-loader" aria-hidden="true" />
      <p className="result-eyebrow">불러오는 중</p>
      <h1>퀘스트 정보를 가져오고 있어요.</h1>
    </section>
  );
}

function SessionMissingCard() {
  return (
    <section className="result-message">
      <p className="result-eyebrow">세션 정보 없음</p>
      <h1>퀘스트를 확인할 세션 정보가 없어요.</h1>
      <p>초대 링크로 다시 들어오거나 테스트 방을 새로 만들어 주세요.</p>
      <Link href="/" className="button-next">
        홈으로
      </Link>
    </section>
  );
}

function ErrorCard({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <section className="result-message">
      <p className="result-eyebrow">문제가 발생했어요</p>
      <h1>{message}</h1>
      <button type="button" className="button-next" onClick={onRetry}>
        다시 시도
      </button>
    </section>
  );
}

function NotAssignedCard({
  isHost,
  pending,
  error,
  onAssign,
}: {
  isHost: boolean;
  pending: boolean;
  error: string | null;
  onAssign: () => void;
}) {
  return (
    <section className="result-report quest-card quest-not-assigned">
      <p className="result-eyebrow">아이스브레이킹 퀘스트</p>
      <h1>{isHost ? "팀에 어울리는 퀘스트를 준비해볼까요?" : "방장이 퀘스트를 준비하고 있어요."}</h1>
      {isHost ? (
        <>
          <p>팀 분석 결과를 바탕으로 지금 팀에 어울리는 퀘스트 하나를 배정해요.</p>
          <button type="button" className="button-next" disabled={pending} onClick={onAssign}>
            {pending ? "배정하는 중…" : "퀘스트 배정하기"}
          </button>
        </>
      ) : (
        <p>잠시만 기다려 주세요. 방장이 퀘스트를 배정하면 자동으로 화면이 바뀌어요.</p>
      )}
      {error && <p className="quest-action-error">{error}</p>}
    </section>
  );
}

function QuestCard({
  quest,
  session,
  pendingAction,
  actionError,
  runAction,
  onHostGoWorkspace,
}: {
  quest: QuestCurrent;
  session: TeamSession;
  pendingAction: string | null;
  actionError: string | null;
  runAction: (key: string, action: () => Promise<QuestCurrent>) => Promise<void>;
  onHostGoWorkspace: () => Promise<void>;
}) {
  const { assignment } = quest;

  return (
    <section className="result-report quest-card survey-card-enter">
      <header className="quest-header">
        <p className="result-eyebrow">
          아이스브레이킹 퀘스트
          <span className={`quest-status-pill quest-status-pill-${assignment.status.toLowerCase()}`}>
            {QUEST_STATUS_LABEL[assignment.status]}
          </span>
        </p>
        <h1>{quest.title}</h1>
        <p className="quest-summary">{quest.summary}</p>
        <span className="quest-duration-badge">⏱ 약 {quest.duration_minutes}분</span>
      </header>

      <div className="quest-intro">
        <b>{assignment.intro_message}</b>
        <p>{assignment.reason}</p>
      </div>

      <div className="quest-body-grid">
        <article className="quest-steps">
          <h2>진행 단계</h2>
          <ol>
            {quest.steps.map((step, index) => (
              <li key={index}>{step}</li>
            ))}
          </ol>
        </article>
        <aside className="quest-meta">
          {quest.materials.length > 0 && (
            <div>
              <h3>준비물</h3>
              <ul className="quest-chip-list">
                {quest.materials.map((material) => (
                  <li key={material}>{material}</li>
                ))}
              </ul>
            </div>
          )}
          <div>
            <h3>결과물</h3>
            <p>{quest.deliverable}</p>
          </div>
        </aside>
      </div>

      <StatusSection
        quest={quest}
        session={session}
        pendingAction={pendingAction}
        runAction={runAction}
        onHostGoWorkspace={onHostGoWorkspace}
      />

      {actionError && <p className="quest-action-error">{actionError}</p>}
      {session.isHost === false && <p className="quest-source-hint">퀘스트 상태는 몇 초마다 자동으로 갱신돼요.</p>}
    </section>
  );
}

function StatusSection({
  quest,
  session,
  pendingAction,
  runAction,
  onHostGoWorkspace,
}: {
  quest: QuestCurrent;
  session: TeamSession;
  pendingAction: string | null;
  runAction: (key: string, action: () => Promise<QuestCurrent>) => Promise<void>;
  onHostGoWorkspace: () => Promise<void>;
}) {
  const { assignment } = quest;
  const isHost = session.isHost;

  if (assignment.status === "ASSIGNED") {
    return (
      <div className="quest-status-panel" data-status="ASSIGNED">
        {isHost ? (
          <>
            <p>팀원들과 함께 볼 준비가 되면 퀘스트를 시작해 주세요.</p>
            <button
              type="button"
              className="button-next"
              disabled={pendingAction === "start"}
              onClick={() => runAction("start", () => startQuest(assignment.id))}
            >
              {pendingAction === "start" ? "시작하는 중…" : "퀘스트 시작"}
            </button>
          </>
        ) : (
          <p>방장이 곧 퀘스트를 시작할 거예요. 잠시만 기다려 주세요.</p>
        )}
      </div>
    );
  }

  if (assignment.status === "IN_PROGRESS") {
    return (
      <div className="quest-status-panel" data-status="IN_PROGRESS">
        {isHost ? (
          <HostInProgressPanel
            assignmentId={assignment.id}
            requirements={quest.completion_requirements}
            teamStatus={quest.team_completion_status}
            pendingAction={pendingAction}
            runAction={runAction}
          />
        ) : (
          <MemberInProgressPanel
            assignmentId={assignment.id}
            requirements={quest.completion_requirements}
            myResponseStatus={quest.my_response_status}
            pendingAction={pendingAction}
            runAction={runAction}
          />
        )}
      </div>
    );
  }

  // COMPLETED | SKIPPED
  const completed = assignment.status === "COMPLETED";
  return (
    <div className="quest-status-panel" data-status={assignment.status}>
      {completed ? (
        <div className="quest-complete-hero">
          <Image src="/duck-face-sparkle.png" alt="" width={72} height={72} />
          <p className="quest-final-badge quest-final-completed">✓ 퀘스트를 완료했어요.</p>
          <h2>우리 팀, 이제 협업 준비 완료!</h2>
        </div>
      ) : (
        <p className="quest-final-badge quest-final-skipped">이번 퀘스트는 가볍게 건너뛰었어요. 불이익은 없어요.</p>
      )}
      {isHost ? (
        <button
          type="button"
          className="button-next quest-cta-strong"
          disabled={pendingAction === "workspace"}
          onClick={() => void onHostGoWorkspace()}
        >
          {pendingAction === "workspace" ? "준비하는 중…" : "협업 시작하기"}
        </button>
      ) : (
        <Link
          href={`/workspace?sessionId=${encodeURIComponent(session.sessionId)}`}
          className="button-next quest-cta-strong"
        >
          협업 공간으로 이동
        </Link>
      )}
    </div>
  );
}

// 진행 상태 판정은 항상 서버 값(my_response_status/team_completion_status)만
// 쓴다 — completion_requirements는 "무엇이·최소 몇 번 필요한지"만 알려줄 뿐
// 진행 카운트/충족 여부를 담지 않으므로, scope별 필요 타입 목록 이상으로는
// 쓰지 않는다.
function MemberInProgressPanel({
  assignmentId,
  requirements,
  myResponseStatus,
  pendingAction,
  runAction,
}: {
  assignmentId: string;
  requirements: QuestCurrent["completion_requirements"];
  myResponseStatus: QuestCurrent["my_response_status"];
  pendingAction: string | null;
  runAction: (key: string, action: () => Promise<QuestCurrent>) => Promise<void>;
}) {
  const checks = requirements.member_checks;
  if (checks.length === 0) {
    return <p className="quest-member-note">이 퀘스트는 팀 전체 결과로만 완료돼요. 방장의 진행을 기다려 주세요.</p>;
  }

  return (
    <div className="quest-response-list">
      <h3>내 응답</h3>
      {checks.map((check) => {
        const done = myResponseStatus?.[check.type] === true;
        return (
          <div key={check.type} className="quest-check-block">
            <CheckLabel check={check} />
            {done ? (
              <div className="quest-check-row quest-check-done">
                <span>✓ 제출했어요</span>
              </div>
            ) : (
              <CheckSubmitRow
                type={check.type}
                pending={pendingAction === `me-${check.type}`}
                onSubmit={(value) =>
                  runAction(`me-${check.type}`, () =>
                    submitMyResponse(assignmentId, [{ type: check.type, count: 1, value }]),
                  )
                }
              />
            )}
          </div>
        );
      })}
    </div>
  );
}

function HostInProgressPanel({
  assignmentId,
  requirements,
  teamStatus,
  pendingAction,
  runAction,
}: {
  assignmentId: string;
  requirements: QuestCurrent["completion_requirements"];
  teamStatus: QuestCurrent["team_completion_status"];
  pendingAction: string | null;
  runAction: (key: string, action: () => Promise<QuestCurrent>) => Promise<void>;
}) {
  const [skipConfirm, setSkipConfirm] = useState(false);
  const unmet = new Set(teamStatus.unmet_check_types);

  return (
    <div className="quest-host-panel">
      {requirements.member_checks.length > 0 && (
        <div className="quest-response-list">
          <h3>팀원 응답 현황</h3>
          {requirements.member_checks.map((check) => (
            <div key={check.type} className="quest-check-block">
              <CheckLabel check={check} />
              <div
                className={
                  unmet.has(check.type) ? "quest-check-row quest-check-progress-only" : "quest-check-row quest-check-done"
                }
              >
                <span>{unmet.has(check.type) ? "진행 중이에요" : "✓ 완료"}</span>
              </div>
            </div>
          ))}
        </div>
      )}
      {requirements.team_checks.length > 0 && (
        <div className="quest-response-list">
          <h3>공동 결과 제출</h3>
          {requirements.team_checks.map((check) => (
            <div key={check.type} className="quest-check-block">
              <CheckLabel check={check} />
              {unmet.has(check.type) ? (
                <CheckSubmitRow
                  type={check.type}
                  pending={pendingAction === `team-${check.type}`}
                  onSubmit={(value) =>
                    runAction(`team-${check.type}`, () =>
                      submitTeamResult(assignmentId, [{ type: check.type, count: 1, value }]),
                    )
                  }
                />
              ) : (
                <div className="quest-check-row quest-check-done">
                  <span>✓ 완료</span>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
      <div className="quest-host-actions">
        <button
          type="button"
          className="button-next"
          disabled={!teamStatus.satisfied || pendingAction === "complete"}
          title={teamStatus.satisfied ? undefined : "아직 완료 조건을 채우지 못했어요."}
          onClick={() => runAction("complete", () => completeQuest(assignmentId))}
        >
          {pendingAction === "complete" ? "완료하는 중…" : "완료"}
        </button>
        {!skipConfirm ? (
          <button type="button" className="button-muted" onClick={() => setSkipConfirm(true)}>
            건너뛰기
          </button>
        ) : (
          <span className="quest-skip-confirm">
            정말 건너뛸까요?
            <button
              type="button"
              className="button-muted"
              disabled={pendingAction === "skip"}
              onClick={() => runAction("skip", () => skipQuest(assignmentId))}
            >
              {pendingAction === "skip" ? "처리 중…" : "네, 건너뛰기"}
            </button>
            <button type="button" className="quest-skip-cancel" onClick={() => setSkipConfirm(false)}>
              취소
            </button>
          </span>
        )}
      </div>
    </div>
  );
}

function CheckLabel({ check }: { check: CompletionCheckRequirement }) {
  return (
    <div className="quest-check-progress">
      <span>{CHECK_TYPE_LABEL[check.type] ?? check.type}</span>
      <small>최소 {check.min_count}회</small>
    </div>
  );
}

function CheckSubmitRow({
  type,
  pending,
  onSubmit,
}: {
  type: string;
  pending: boolean;
  onSubmit: (value: string | null) => void;
}) {
  const [value, setValue] = useState("");
  const needsText = CHECK_TYPE_NEEDS_TEXT.has(type);

  return (
    <form
      className="quest-check-row"
      onSubmit={(event) => {
        event.preventDefault();
        onSubmit(needsText ? value.trim() || null : null);
        setValue("");
      }}
    >
      {needsText && (
        <input
          value={value}
          onChange={(event) => setValue(event.target.value)}
          placeholder="짧게 남겨 주세요"
          aria-label={`${CHECK_TYPE_LABEL[type] ?? type} 입력`}
        />
      )}
      <button type="submit" className="button-muted" disabled={pending}>
        {pending ? "제출 중…" : "제출"}
      </button>
    </form>
  );
}

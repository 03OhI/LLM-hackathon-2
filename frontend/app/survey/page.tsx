"use client";

import Image from "next/image";
import Link from "next/link";
import QRCode from "qrcode";
import { useEffect, useMemo, useState } from "react";

const groups = [
  {
    title: "계획성",
    items: [
      ["P1", "새 일을 받으면 전체 순서를 먼저 그린 다음 착수한다."],
      ["P2", "마감이 다가오면 남은 일을 쪼개 하루치로 나눈다."],
      ["P3", "발표 자료를 만들 때 목차를 먼저 짜고 칸을 채운다."],
      [
        "P4",
        "일정이 틀어지면 지금 할 수 있는 것부터 처리하며 계획을 갱신한다.",
      ],
      ["P5", "되돌릴 수 있는 결정이면 먼저 정하고 확인은 나중에 한다."],
      ["P6", "작업 공간 규칙은 실제로 불편해진 시점에 만든다."],
    ],
  },
  {
    title: "주도성",
    items: [
      ["L1", "회의에서 방향이 안 잡히면 내가 안을 내놓는다."],
      ["L2", "역할을 나눌 때 하고 싶은 역할을 먼저 말한다."],
      ["L3", "내 안이 밀려도 한 번 더 설득해본다."],
      ["L4", "의견이 반반으로 갈리면 정해지는 대로 따르는 편이다."],
      ["L5", "일이 몰려도 일단 내 선에서 처리해본다."],
      ["L6", "팀 결과 전체보다 맡은 부분을 확실히 하는 게 편하다."],
    ],
  },
  {
    title: "갈등 대응",
    items: [
      ["C1", "팀원 결과물이 아쉬우면 그 자리에서 짚는다."],
      ["C2", "작업에서 실수가 나오면 원인을 바로 짚는다."],
      ["C3", "같은 문제가 또 생기면 규칙을 바꾸자고 공식적으로 제기한다."],
      ["C4", "의견이 갈리면 접점을 찾아 좁히는 편이다."],
      ["C5", "팀원 둘이 부딪히면 감정이 상하지 않게 사이를 조율한다."],
      [
        "C6",
        "내 방식과 팀 방식이 다르면 팀 방식을 따르고 필요하면 나중에 제안한다.",
      ],
    ],
  },
  {
    title: "소통 직접성",
    items: [
      ["D1", "문제를 알릴 때 결론부터 말한다."],
      ["D2", "요청을 못 받을 때 안 된다고 명확히 말한다."],
      ["D3", "고칠 점을 그대로 짚어 오해를 줄인다."],
      ["D4", "내 의견이 다수와 다르면 분위기를 보며 조심스럽게 꺼낸다."],
      ["D5", "메신저로 의견을 전할 때 완충 표현을 더해 부드럽게 적는다."],
      ["D6", "도움이 필요할 때 상대 상황을 살피며 에둘러 꺼낸다."],
    ],
  },
] as const;

const choices = [
  [1, "매우 아니다"],
  [2, "아니다"],
  [3, "중간"],
  [4, "그렇다"],
  [5, "매우 그렇다"],
] as const;

function SurveyNav() {
  return (
    <nav className="survey-nav" aria-label="설문 탐색">
      <Link className="survey-back" href="/" aria-label="이전 화면으로">
        ←
      </Link>
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
  );
}

function isGroupComplete(index: number, answers: Record<string, number>) {
  return groups[index].items.every(([id]) => answers[id] !== undefined);
}

function SurveySidebar({
  step,
  answers,
  onSelect,
}: {
  step: number;
  answers: Record<string, number>;
  onSelect: (index: number) => void;
}) {
  const answeredInStage = groups[step].items.filter(
    ([id]) => answers[id] !== undefined,
  ).length;
  const sidebarFace = ["smile", "open", "wink", "sparkle"][
    Math.min(3, Math.floor(answeredInStage / 2))
  ];
  return (
    <aside className="survey-sidebar" aria-label="설문 단계">
      <p>협업 스타일</p>
      <div className="sidebar-count">
        <b>
          {step + 1} / {groups.length}
        </b>
        <span>단계</span>
      </div>
      <ol>
        {groups.map((group, index) => {
          const complete = isGroupComplete(index, answers);
          const unlocked =
            index === 0 ||
            groups
              .slice(0, index)
              .every((_, previous) => isGroupComplete(previous, answers));
          const active = index === step;
          return (
            <li key={group.title}>
              <button
                type="button"
                disabled={!unlocked}
                className={`${active ? "active" : ""} ${complete ? "complete" : ""}`}
                onClick={() => onSelect(index)}
              >
                <i aria-label={complete ? "완료" : `${index + 1}단계`}>
                  {complete ? "●" : String(index + 1).padStart(2, "0")}
                </i>
                <span>
                  <b>{group.title}</b>
                  <small>
                    {complete ? "완료" : active ? "진행 중" : "예정"}
                  </small>
                </span>
              </button>
            </li>
          );
        })}
      </ol>
      <div className="sidebar-note">
        <Image
          key={sidebarFace}
          className="sidebar-face"
          src={`/duck-face-${sidebarFace}.png`}
          alt=""
          width={68}
          height={68}
        />
        <div>
          <b>천천히, 솔직하게!</b>
          <p>
            정답은 없어요.
            <br />
            당신의 평소 모습을 선택해 주세요.
          </p>
        </div>
      </div>
    </aside>
  );
}

type TeamSession = {
  sessionId: string;
  inviteToken: string;
  teamName: string;
  expectedMembers: number;
  participantId: string;
  isHost: boolean;
};
type SavedTeamSession = {
  team: TeamSession;
  phase: "lobby" | "survey" | "waiting";
};
type TeamStatus = {
  joinedMembers: number;
  completedMembers: number;
  expectedMembers: number;
  analysisStatus: string | null;
};
const teamSessionStorageKey = "tmti-active-team-session";
const apiBase = process.env.NEXT_PUBLIC_API_BASE ?? "/backend/api";

type AnalysisStatusPayload = {
  joined_member_count?: number;
  submitted_member_count?: number;
  expected_member_count?: number;
  analysis_status?: string | null;
};

function parseTeamStatus(
  next: AnalysisStatusPayload,
  fallbackExpected: number,
): TeamStatus {
  return {
    joinedMembers: next.joined_member_count ?? 0,
    completedMembers: next.submitted_member_count ?? 0,
    expectedMembers: next.expected_member_count ?? fallbackExpected,
    analysisStatus: next.analysis_status ?? null,
  };
}

// http(비보안 컨텍스트)에서는 navigator.clipboard 가 없으므로 execCommand 로 폴백한다.
async function copyText(text: string): Promise<boolean> {
  try {
    if (
      typeof navigator !== "undefined" &&
      navigator.clipboard &&
      window.isSecureContext
    ) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch {
    /* execCommand 폴백으로 진행 */
  }
  try {
    const area = document.createElement("textarea");
    area.value = text;
    area.setAttribute("readonly", "");
    area.style.position = "fixed";
    area.style.top = "0";
    area.style.opacity = "0";
    document.body.appendChild(area);
    area.focus();
    area.select();
    const ok = document.execCommand("copy");
    document.body.removeChild(area);
    return ok;
  } catch {
    return false;
  }
}

function saveTeamSession(team: TeamSession, phase: SavedTeamSession["phase"]) {
  if (typeof window !== "undefined")
    window.sessionStorage.setItem(
      teamSessionStorageKey,
      JSON.stringify({ team, phase }),
    );
}

function getSavedTeamSession(): SavedTeamSession | null {
  if (typeof window === "undefined") return null;
  try {
    const saved = JSON.parse(
      window.sessionStorage.getItem(teamSessionStorageKey) ?? "null",
    ) as SavedTeamSession | null;
    return saved?.team?.sessionId && saved.team.participantId ? saved : null;
  } catch {
    return null;
  }
}

function beginNewTest() {
  // 이전 팀 데이터는 서버에 남기고, 현재 브라우저의 참여 상태만 비운다.
  // Link의 클라이언트 전환 대신 문서를 새로 열어 대기 화면 상태가 재사용되지 않게 한다.
  window.sessionStorage.removeItem(teamSessionStorageKey);
  window.sessionStorage.removeItem("tmti-session-id");
  window.localStorage.removeItem(teamSessionStorageKey);
  window.localStorage.removeItem("tmti-session-id");
  window.location.replace("/survey?new=1");
}

function WaitingScreen({
  team,
}: {
  team: TeamSession;
}) {
  const [status, setStatus] = useState<TeamStatus>({
    joinedMembers: 1,
    completedMembers: 1,
    expectedMembers: team.expectedMembers,
    analysisStatus: null,
  });
  const [copied, setCopied] = useState(false);
  const [analysisRequested, setAnalysisRequested] = useState(false);
  const [statusError, setStatusError] = useState("");
  useEffect(() => {
    const refresh = async () => {
      try {
        const response = await fetch(`${apiBase}/sessions/${team.sessionId}/analysis/status`, {
          cache: "no-store",
          credentials: "same-origin",
        });
        if (!response.ok) {
          setStatusError("완료 현황을 다시 확인하고 있어요.");
          return;
        }
        const next = await response.json();
        // 제출 완료 직후에는 이 브라우저의 완료 상태를 우선 보존합니다.
        // 서버 응답이 도착한 뒤에는 더 큰 값으로 자연스럽게 동기화됩니다.
        const parsed = parseTeamStatus(next, team.expectedMembers);
        setStatus({
          ...parsed,
          completedMembers: Math.max(1, parsed.completedMembers),
          joinedMembers: Math.max(1, parsed.joinedMembers),
        });
        setStatusError("");
        if (next.analysis_status === "COMPLETED" || next.analysis_status === "FALLBACK") {
          window.location.assign(`/results?sessionId=${encodeURIComponent(team.sessionId)}`);
          return;
        }
        if (team.isHost && !analysisRequested && !next.analysis_status && next.submitted_member_count === next.expected_member_count) {
          setAnalysisRequested(true);
          await fetch(`${apiBase}/sessions/${team.sessionId}/analysis`, { method: "POST", credentials: "same-origin" });
        }
      } catch {
        setStatusError("완료 현황을 불러오지 못했어요. 잠시 후 자동으로 다시 확인합니다.");
      }
    };
    refresh();
    const timer = window.setInterval(refresh, 3000);
    return () => window.clearInterval(timer);
  }, [analysisRequested, team.isHost, team.sessionId]);
  const invite =
    typeof window === "undefined"
      ? ""
      : `${window.location.origin}/?invite=${team.inviteToken}`;

  return (
    <main className="survey-shell">
      <SurveyNav />
      <section className="survey-card waiting-card survey-card-enter">
        <div className="waiting-duck" aria-hidden="true">
          {[1, 2, 3, 4].map((frame) => (
            <Image
              key={frame}
              className={`waiting-frame waiting-frame-${frame}`}
              src={`/wait-duck-${frame}.png`}
              alt=""
              width={250}
              height={250}
              priority
            />
          ))}
        </div>
        <p className="eyebrow">TEAM ANALYSIS</p>
        <h1>
          {status.analysisStatus === "PROCESSING"
            ? "결과를 준비하고 있어요."
            : "팀원들의 응답을 모으고 있어요."}
        </h1>
        <p className="waiting-count">
          로딩 중{" "}
          <b>
            ({status.completedMembers} / {status.expectedMembers})
          </b>
        </p>
        <div className="waiting-progress">
          <i
            style={{
              width: `${(status.completedMembers / status.expectedMembers) * 100}%`,
            }}
          />
        </div>
        <p className="waiting-note">
          모든 팀원이 설문을 마치면 팀 분석 결과가 준비됩니다.
        </p>
        <div className="waiting-actions">
          <button
            className="invite-button"
            onClick={async () => {
              setCopied(await copyText(invite));
            }}
          >
            {copied ? "참여 링크가 복사되었어요" : "팀 참여 링크 복사"}
          </button>
          {team.isHost && <button type="button" className="admin-preview-button" onClick={() => window.location.assign("/results?mode=admin")}>관리자 · 응답 결과 보기 <span aria-hidden="true">→</span></button>}
          <Link className="button-muted" href="/">
            홈으로
          </Link>
          <button type="button" className="button-next waiting-new-test" onClick={beginNewTest}>
            <span>새로운 테스트 진행하기</span>
            <i aria-hidden="true">→</i>
          </button>
        </div>
        {statusError && <p className="waiting-demo-note" role="status">{statusError}</p>}
        {team.isHost && <p className="waiting-demo-note">모든 응답이 모이면 분석을 시작하고 결과 화면으로 이동합니다.</p>}
      </section>
    </main>
  );
}

function TeamLobby({
  team,
  onStart,
}: {
  team: TeamSession;
  onStart: () => void;
}) {
  const [status, setStatus] = useState<TeamStatus>({
    joinedMembers: 1,
    completedMembers: 0,
    expectedMembers: team.expectedMembers,
    analysisStatus: null,
  });
  const [copied, setCopied] = useState(false);
  const [qrCode, setQrCode] = useState("");
  const invite =
    typeof window === "undefined"
      ? ""
      : `${window.location.origin}/?invite=${team.inviteToken}`;
  useEffect(() => {
    const refresh = async () => {
      try {
        const response = await fetch(
          `${apiBase}/sessions/${team.sessionId}/analysis/status`,
          { cache: "no-store", credentials: "same-origin" },
        );
        if (!response.ok) return;
        const next = await response.json();
        setStatus(parseTeamStatus(next, team.expectedMembers));
      } catch {
        /* 네트워크가 잠시 끊겨도 초대 화면은 유지합니다. */
      }
    };
    refresh();
    const timer = window.setInterval(refresh, 3000);
    return () => window.clearInterval(timer);
  }, [team.expectedMembers, team.sessionId]);
  useEffect(() => {
    if (invite)
      QRCode.toDataURL(invite, {
        width: 340,
        margin: 1,
        color: { dark: "#334166", light: "#FFFFFF" },
      }).then(setQrCode);
  }, [invite]);
  return (
    <main className="survey-shell">
      <SurveyNav />
      <section className="survey-card team-lobby survey-card-enter">
        <div className="lobby-heading">
          <div>
            <div className="intro-kicker">
              <Image src="/duck-face-open.png" alt="" width={48} height={48} />
              <span>{team.teamName}</span>
            </div>
            <h1>팀원을 초대해 주세요</h1>
            <p>
              링크 또는 QR을 공유하면 팀원들이 바로 설문에 참여할 수 있어요.
            </p>
          </div>
          <Image
            className="lobby-face"
            src="/duck-face-sparkle.png"
            alt=""
            width={130}
            height={130}
            priority
          />
        </div>
        <div className="lobby-grid">
          <section className="lobby-invite">
            <p className="lobby-label">TEAM INVITE</p>
            {qrCode ? (
              <Image
                className="invite-qr"
                src={qrCode}
                alt={`${team.teamName} 설문 참여 QR 코드`}
                width={170}
                height={170}
                unoptimized
              />
            ) : (
              <div className="invite-qr loading" />
            )}
            <p className="invite-code">초대 링크를 공유해 주세요</p>
            <button
              className="invite-button lobby-copy"
              onClick={async () => {
                setCopied(await copyText(invite));
              }}
            >
              {copied ? "초대 링크가 복사되었어요" : "초대 링크 복사"}
            </button>
          </section>
          <section className="lobby-members">
            <div className="lobby-member-heading">
              <div>
                <p className="lobby-label">TEAM STATUS</p>
                <h2>
                  참여 현황{" "}
                  <b>
                    {status.joinedMembers} / {status.expectedMembers}
                  </b>
                </h2>
                <small>설문 완료 {status.completedMembers}명</small>
              </div>
              <button
                className="lobby-refresh"
                onClick={async () => {
                  const response = await fetch(
                    `${apiBase}/sessions/${team.sessionId}/analysis/status`,
                    { cache: "no-store", credentials: "same-origin" },
                  );
                  if (response.ok) {
                    const next = await response.json();
                    setStatus(parseTeamStatus(next, team.expectedMembers));
                  }
                }}
                aria-label="참여 현황 새로고침"
              >
                ↻
              </button>
            </div>
            <ul>
              {Array.from({ length: status.expectedMembers }, (_, index) => {
                const joined = index < status.joinedMembers;
                const completed = index < status.completedMembers;
                return (
                  <li className={joined ? "joined" : "waiting"} key={index}>
                    <i>{completed ? "✓" : joined ? "●" : ""}</i>
                    <span>{joined ? "참여한 팀원" : "팀원 참여 대기"}</span>
                    <small>
                      {completed ? "설문 완료" : joined ? "설문 작성 중" : "대기"}
                    </small>
                  </li>
                );
              })}
            </ul>
          </section>
        </div>
        <div className="lobby-note">
          <Image src="/duck-face-smile.png" alt="" width={56} height={56} />
          <p>
            팀원들이 링크로 참여하면 이 화면에서 참여 현황이 자동으로
            업데이트돼요.
          </p>
        </div>
        <div className="survey-actions">
          <Link className="button-muted" href="/">
            홈으로
          </Link>
          <button type="button" className="button-muted lobby-new-test" onClick={beginNewTest}>
            새로운 테스트
          </button>
          <button className="button-next intro-start-button" onClick={onStart}>
            <span>내 설문 시작하기</span>
            <i aria-hidden="true">→</i>
          </button>
        </div>
      </section>
    </main>
  );
}

export default function SurveyPage() {
  const [step, setStep] = useState(-1);
  const [answers, setAnswers] = useState<Record<string, number>>({});
  const [showValidation, setShowValidation] = useState(false);
  const [teamName, setTeamName] = useState("");
  const [teamSize, setTeamSize] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [showTeamValidation, setShowTeamValidation] = useState(false);
  const [teamSession, setTeamSession] = useState<TeamSession | null>(null);
  const [teamError, setTeamError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const inviteToken =
    typeof window === "undefined"
      ? ""
      : (new URLSearchParams(window.location.search).get("invite") ?? "");
  const freshStart =
    typeof window !== "undefined" &&
    new URLSearchParams(window.location.search).get("new") === "1";
  const [inviteInfo, setInviteInfo] = useState<{
    sessionName: string;
    expectedMembers: number;
  } | null>(null);
  const current = step >= 0 && step < groups.length ? groups[step] : null;
  const currentAnswered = current
    ? current.items.filter(([id]) => answers[id] !== undefined).length
    : 0;
  const progress = useMemo(
    () => (step < 0 ? 0 : ((step + 1) / groups.length) * 100),
    [step],
  );
  const runnerPosition = Math.min(94, Math.max(6, progress));
  const completeCurrent = current?.items.every(
    ([id]) => answers[id] !== undefined,
  ) ?? false;
  const validTeamSetup =
    teamName.trim().length > 0 &&
    displayName.trim().length > 0 &&
    Number(teamSize) >= 3 &&
    Number(teamSize) <= 10;
  useEffect(() => {
    if (freshStart) {
      // 같은 /survey 경로에서 쿼리만 바뀌면 Next.js가 기존 컴포넌트를 재사용한다.
      // 따라서 저장소만 지우지 말고 메모리 상태도 초기 팀 생성 화면으로 즉시 되돌린다.
      // 기존 팀/DB 데이터를 삭제하지 않고, 이 브라우저의 새 테스트 시작 상태만 초기화한다.
      window.sessionStorage.removeItem(teamSessionStorageKey);
      window.sessionStorage.removeItem("tmti-session-id");
      window.localStorage.removeItem(teamSessionStorageKey);
      window.localStorage.removeItem("tmti-session-id");
      setAnswers({});
      setTeamSession(null);
      setTeamError("");
      setShowValidation(false);
      setShowTeamValidation(false);
      setStep(-1);
      window.history.replaceState(null, "", "/survey");
      return;
    }
    const saved = getSavedTeamSession();
    if (!saved) return;
    setTeamSession(saved.team);
    setStep(
      saved.phase === "waiting"
        ? groups.length
        : saved.phase === "lobby"
          ? -2
          : 0,
    );
  }, [freshStart]);
  useEffect(() => {
    if (step < 0 || step >= groups.length) return;

    // 다음 축으로 넘어가도 이전 페이지의 하단 스크롤 위치가 남지 않게 한다.
    // 모든 설문 단계가 계획성 페이지와 같은 시작 위치에서 보이도록 맞춘다.
    const frame = window.requestAnimationFrame(() => {
      window.scrollTo({ top: 0, left: 0, behavior: "auto" });
    });
    return () => window.cancelAnimationFrame(frame);
  }, [step]);
  const resetSurvey = () => {
    window.sessionStorage.removeItem(teamSessionStorageKey);
    window.sessionStorage.removeItem("tmti-session-id");
    window.localStorage.removeItem(teamSessionStorageKey);
    window.localStorage.removeItem("tmti-session-id");
    setAnswers({});
    setTeamSession(null);
    setTeamError("");
    setShowValidation(false);
    setStep(-1);
  };
  // 시연용: 24문항을 즉석에서 채우고 마지막 단계로 이동한다.
  // 앞 3문항은 높게, 뒤 3문항(역채점)은 낮게 줘서 성향이 뚜렷하게 나오도록 한다.
  const autofillForDemo = () => {
    const next: Record<string, number> = {};
    groups.forEach((group) =>
      group.items.forEach(([id], index) => {
        next[id] =
          index < 3 ? 4 + Math.round(Math.random()) : 1 + Math.round(Math.random());
      }),
    );
    setAnswers(next);
    setShowValidation(false);
    setTeamError("");
    setStep(groups.length - 1);
  };
  useEffect(() => {
    if (!inviteToken) return;
    const loadInvite = async () => {
      try {
        const response = await fetch(`${apiBase}/invites/${inviteToken}`, {
          cache: "no-store",
          credentials: "same-origin",
        });
        if (!response.ok) {
          setTeamError("초대 링크를 확인하지 못했어요. 링크를 다시 확인해 주세요.");
          return;
        }
        const invite = await response.json();
        setInviteInfo({
          sessionName: invite.session_name,
          expectedMembers: invite.expected_member_count,
        });
      } catch {
        setTeamError("초대 정보를 불러오지 못했어요. 잠시 후 다시 시도해 주세요.");
      }
    };
    loadInvite();
  }, [inviteToken]);
  const startSurvey = async () => {
    if (!validTeamSetup) {
      setShowTeamValidation(true);
      return;
    }
    setShowTeamValidation(false);
    setTeamError("");
    setIsSubmitting(true);
    try {
      const response = await fetch(`${apiBase}/sessions`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        credentials: "same-origin",
        body: JSON.stringify({
          name: teamName.trim(),
          expected_member_count: Number(teamSize),
          meeting_type: "team_project",
        }),
      });
      if (!response.ok) throw new Error("create-session");
      const created = await response.json();
      const participantResponse = await fetch(
        `${apiBase}/invites/${created.invite_token}/participants`,
        {
          method: "POST",
          headers: { "content-type": "application/json" },
          credentials: "same-origin",
          body: JSON.stringify({ nickname: displayName.trim() }),
        },
      );
      if (!participantResponse.ok) throw new Error("create-host-participant");
      const participant = await participantResponse.json();
      const session: TeamSession = {
        sessionId: created.session_id,
        inviteToken: created.invite_token,
        teamName: teamName.trim(),
        expectedMembers: Number(teamSize),
        participantId: participant.participant_id,
        isHost: true,
      };
      window.sessionStorage.setItem("tmti-session-id", session.sessionId);
      // 탭을 닫아도 "결과 이어보기"가 되도록 로컬에도 남긴다.
      window.localStorage.setItem("tmti-session-id", session.sessionId);
      window.localStorage.setItem(
        teamSessionStorageKey,
        JSON.stringify({ team: session, phase: "lobby" }),
      );
      saveTeamSession(session, "lobby");
      setTeamSession(session);
      setStep(-2);
    } catch {
      setTeamError("팀을 만들지 못했어요. 잠시 후 다시 시도해 주세요.");
    } finally {
      setIsSubmitting(false);
    }
  };
  const joinSurvey = async () => {
    if (!displayName.trim()) {
      setShowTeamValidation(true);
      return;
    }
    setTeamError("");
    setIsSubmitting(true);
    try {
      const response = await fetch(`${apiBase}/invites/${inviteToken}/participants`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        credentials: "same-origin",
        body: JSON.stringify({ nickname: displayName.trim() }),
      });
      if (!response.ok) throw new Error("join-session");
      const joined = await response.json();
      const session: TeamSession = {
        sessionId: joined.session_id,
        inviteToken,
        teamName: inviteInfo?.sessionName ?? "초대받은 팀",
        expectedMembers: inviteInfo?.expectedMembers ?? 3,
        participantId: joined.participant_id,
        isHost: false,
      };
      window.sessionStorage.setItem("tmti-session-id", session.sessionId);
      // 탭을 닫아도 "결과 이어보기"가 되도록 로컬에도 남긴다.
      window.localStorage.setItem("tmti-session-id", session.sessionId);
      window.localStorage.setItem(
        teamSessionStorageKey,
        JSON.stringify({ team: session, phase: "survey" }),
      );
      saveTeamSession(session, "survey");
      setTeamSession(session);
      setStep(0);
    } catch {
      setTeamError("팀 참여 정보를 확인하지 못했어요. 이름이나 링크를 확인해 주세요.");
    } finally {
      setIsSubmitting(false);
    }
  };

  if (step === groups.length)
    return (
      <WaitingScreen
        team={
          teamSession ?? {
            sessionId: "",
            inviteToken: "",
            teamName: teamName || "우리 팀",
            expectedMembers: Number(teamSize) || 3,
            participantId: "",
            isHost: false,
          }
        }
      />
    );

  if (step === -2 && teamSession)
    return (
      <TeamLobby
        team={teamSession}
        onStart={() => {
          saveTeamSession(teamSession, "survey");
          setStep(0);
        }}
      />
    );

  if (step === -1)
    return (
      <main className="survey-shell">
        <SurveyNav />
        <section className="survey-card survey-intro survey-card-enter">
          <div className="intro-heading">
            <div>
              <div className="intro-kicker">
                <Image
                  src="/duck-face-open.png"
                  alt=""
                  width={48}
                  height={48}
                />
                <span>팀과 함께 시작해요</span>
              </div>
              <h1>협업 스타일 24문항</h1>
            </div>
            <Image
              className="intro-thinking-duck"
              src="/duck-face-wink.png"
              alt=""
              width={104}
              height={104}
              priority
            />
          </div>
          <p>
            성격 유형 검사가 아니라, 이 팀에서의 자리를 제안하기 위한
            질문지입니다. 정답은 없습니다.
          </p>
          <div className="intro-steps" aria-label="설문은 4단계로 진행됩니다.">
            <i className="active" />
            <i />
            <i />
            <i />
            <span>6문항씩 4단계</span>
          </div>
          <form
            className="team-setup"
            onSubmit={(event) => {
              event.preventDefault();
              inviteToken ? joinSurvey() : startSurvey();
            }}
          >
            <div className="team-setup-heading">
              <b>
                {inviteToken
                  ? `${inviteInfo?.sessionName ?? "팀"}에 참여하고 시작해요`
                  : "팀 정보를 먼저 알려주세요"}
              </b>
              <span>
                {inviteToken
                  ? "결과에서 사용할 표시 이름을 입력해 주세요."
                  : "팀 전체 결과를 준비하는 데 사용돼요."}
              </span>
            </div>
            <div className="team-fields">
              {!inviteToken && (
                <>
                  <label>
                    팀명
                    <input
                      value={teamName}
                      onChange={(event) => {
                        setTeamName(event.target.value);
                        setShowTeamValidation(false);
                      }}
                      placeholder="예: 캡스톤 드림팀"
                      maxLength={24}
                    />
                  </label>
                  <label>
                    참여 인원 수
                    <input
                      value={teamSize}
                      onChange={(event) => {
                        setTeamSize(event.target.value.replace(/\D/g, ""));
                        setShowTeamValidation(false);
                      }}
                      inputMode="numeric"
                      placeholder="3~10명"
                      aria-describedby="team-size-help"
                    />
                  </label>
                </>
              )}
              <label>
                내 표시 이름
                <input
                  value={displayName}
                  onChange={(event) => {
                    setDisplayName(event.target.value);
                    setShowTeamValidation(false);
                  }}
                  placeholder="결과에서 사용할 이름"
                  maxLength={12}
                />
              </label>
            </div>
            {!inviteToken && (
              <p id="team-size-help" className="team-setup-help">
                참여 인원은 모든 팀원이 설문을 마친 뒤 팀 분석을 열기 위한
                기준입니다.
              </p>
            )}
            {showTeamValidation && (
              <p className="team-setup-error" aria-live="polite">
                {inviteToken
                  ? "팀원에게 보일 이름을 입력해 주세요."
                  : "팀명과 표시 이름을 입력하고, 참여 인원은 3~10명으로 설정해 주세요."}
              </p>
            )}
            {teamError && (
              <p className="team-setup-error" aria-live="polite">
                {teamError}
              </p>
            )}
            <div className="intro-note intro-speech">
              <Image src="/duck-face-smile.png" alt="" width={68} height={68} />
              <p>
                천천히 읽고, 평소 협업할 때의 내 모습에 가까운 답을 골라주세요.
              </p>
            </div>
            <div className="survey-actions">
              <Link className="button-muted" href="/">
                나중에 하기
              </Link>
              <button className="button-next intro-start-button" type="submit">
                <span>시작하기</span>
                <i aria-hidden="true">→</i>
              </button>
            </div>
          </form>
        </section>
      </main>
    );

  if (!current)
    return (
      <main className="survey-shell">
        <SurveyNav />
        <section className="survey-card survey-intro survey-card-enter">
          <div className="intro-heading">
            <div>
              <div className="intro-kicker">
                <Image src="/duck-face-open.png" alt="" width={48} height={48} />
                <span>설문을 다시 준비할게요</span>
              </div>
              <h1>진행 정보를 다시 확인해 주세요</h1>
            </div>
          </div>
          <p>이전에 저장된 설문 단계 정보를 불러오지 못했어요. 처음 화면에서 다시 시작할 수 있어요.</p>
          <div className="survey-actions">
            <Link className="button-next intro-start-button" href="/survey" onClick={() => window.sessionStorage.removeItem(teamSessionStorageKey)}>
              <span>설문 처음으로</span>
              <i aria-hidden="true">→</i>
            </Link>
          </div>
        </section>
      </main>
    );

  return (
    <main className="survey-shell">
      <SurveyNav />
      <div className={`survey-workspace stage-${step}`}>
        <SurveySidebar
          step={step}
          answers={answers}
          onSelect={(index) => {
            setStep(index);
            setShowValidation(false);
          }}
        />
        <section className="survey-card">
          <div className="survey-topline">
            <div className="survey-stage-copy">
              <span className="survey-stage">
                <i className="stage-icon" aria-hidden="true">
                  {["✓", "↑", "↔", "→"][step]}
                </i>
                {current.title}
              </span>
              <span className="section-progress" aria-live="polite">
                현재 {currentAnswered} / 6 문항
              </span>
            </div>
            <span>
              {step + 1} / {groups.length}
            </span>
          </div>
          <div
            className="progress-runway"
            aria-label={`설문 진행률 ${Math.round(progress)}%`}
          >
            <div className="progress-track">
              <div
                className="progress-fill"
                style={{ width: `${progress}%` }}
              />
            </div>
            <div
              className="progress-runner"
              style={{ left: `${runnerPosition}%` }}
              aria-hidden="true"
            >
              <Image
                className="runner-frame frame-one"
                src="/duck-run-1.png"
                alt=""
                width={104}
                height={104}
                priority
              />
              <Image
                className="runner-frame frame-two"
                src="/duck-run-2.png"
                alt=""
                width={104}
                height={104}
                priority
              />
              <Image
                className="runner-frame frame-three"
                src="/duck-run-3.png"
                alt=""
                width={104}
                height={104}
                priority
              />
            </div>
          </div>
          <div className="question-list question-list-enter" key={step}>
            {current.items.map(([id, text], index) => (
              <article className="question" key={id}>
                <span className="question-number">
                  {id} · 문항 {index + 1} / 6
                </span>
                <h2>{text}</h2>
                <div className="scale" role="group" aria-label={`${id} 응답`}>
                  {choices.map(([value, label]) => (
                    <button
                      type="button"
                      className={answers[id] === value ? "selected" : ""}
                      key={value}
                      onClick={() => {
                        setAnswers((previous) => ({
                          ...previous,
                          [id]: value,
                        }));
                        setShowValidation(false);
                      }}
                    >
                      <span>{value}</span>
                      {label}
                    </button>
                  ))}
                </div>
              </article>
            ))}
          </div>
          {showValidation && (
            <p className="validation validation-shake" aria-live="polite">
              이 단계의 6개 문항에 모두 답해 주세요.
            </p>
          )}
          {teamError && (
            <p className="validation" aria-live="polite">
              {teamError}
            </p>
          )}
          <div className="survey-actions">
            <button
              className="button-muted"
              onClick={() => setStep((previous) => previous - 1)}
              disabled={step === 0 || isSubmitting}
            >
              이전
            </button>
            <button
              type="button"
              className="button-muted"
              onClick={autofillForDemo}
              disabled={isSubmitting}
              title="시연용: 24문항을 자동으로 채우고 마지막 단계로 이동합니다."
            >
              자동 채우기
            </button>
            <button
              className="button-next"
              disabled={isSubmitting}
              onClick={async () => {
                if (!completeCurrent) {
                  setShowValidation(true);
                  return;
                }
                if (step === groups.length - 1) {
                  if (!teamSession?.participantId) {
                    setTeamError("참여 정보를 찾지 못했어요. 처음부터 다시 시작해 주세요.");
                    return;
                  }
                  setIsSubmitting(true);
                  setTeamError("");
                  try {
                    const orderedAnswers = groups.flatMap((group) =>
                      group.items.map(([id]) => answers[id]),
                    );
                    const response = await fetch(
                      `${apiBase}/participants/${teamSession.participantId}/submissions/survey`,
                      {
                        method: "POST",
                        headers: { "content-type": "application/json" },
                        credentials: "same-origin",
                        body: JSON.stringify({ answers: orderedAnswers }),
                      },
                    );
                    if (!response.ok) throw new Error("submit-survey");
                    saveTeamSession(teamSession, "waiting");
                    setStep(groups.length);
                  } catch {
                    setTeamError("응답을 저장하지 못했어요. 네트워크를 확인한 뒤 다시 시도해 주세요.");
                  } finally {
                    setIsSubmitting(false);
                  }
                  return;
                }
                setStep((previous) => previous + 1);
              }}
            >
              {isSubmitting
                ? "응답 저장 중"
                : step === groups.length - 1
                  ? "응답 완료"
                  : "다음"}{" "}
              {!isSubmitting && "→"}
            </button>
          </div>
        </section>
      </div>
    </main>
  );
}

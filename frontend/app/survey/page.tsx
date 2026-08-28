"use client";

import Image from "next/image";
import Link from "next/link";
import QRCode from "qrcode";
import { useEffect, useMemo, useState } from "react";
import ResultsPage from "../results/page";

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
        className="survey-brand-image"
        src="/tmti-survey-logo.png"
        alt="TMTI 캐릭터 로고"
        width={220}
        height={124}
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
  code: string;
  teamName: string;
  expectedMembers: number;
  memberId: string;
};
type SavedTeamSession = {
  team: TeamSession;
  phase: "lobby" | "survey" | "waiting";
};
type DemoResultSession = {
  displayName: string;
  teamName: string;
  responses: Record<string, number>;
};
type TeamStatus = {
  completedMembers: number;
  expectedMembers: number;
  joinedMembers: number;
  members: { displayName: string; completed: boolean }[];
  ready: boolean;
};
const teamSessionStorageKey = "tmti-active-team-session";
const demoResultStorageKey = "tmti-demo-result";

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
    return saved?.team?.code && saved.team.memberId ? saved : null;
  } catch {
    return null;
  }
}

function saveDemoResult(result: DemoResultSession) {
  if (typeof window !== "undefined")
    window.sessionStorage.setItem(demoResultStorageKey, JSON.stringify(result));
}

function WaitingScreen({ team }: { team: TeamSession }) {
  const [status, setStatus] = useState<TeamStatus>({
    completedMembers: 1,
    expectedMembers: team.expectedMembers,
    joinedMembers: 1,
    members: [],
    ready: false,
  });
  const [copied, setCopied] = useState(false);
  const [showPreview, setShowPreview] = useState(false);
  useEffect(() => {
    const refresh = async () => {
      try {
        const response = await fetch(`/api/teams/${team.code}`, {
          cache: "no-store",
        });
        if (response.ok) setStatus(await response.json());
      } catch {
        /* 프론트 시연에서는 대기 UI를 계속 보여 줍니다. */
      }
    };
    refresh();
    const timer = window.setInterval(refresh, 3000);
    return () => window.clearInterval(timer);
  }, [team.code]);
  const invite =
    typeof window === "undefined"
      ? ""
      : `${window.location.origin}/?team=${team.code}`;
  if (showPreview) return <ResultsPage />;

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
          {status.ready
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
              await navigator.clipboard?.writeText(invite);
              setCopied(true);
            }}
          >
            {copied ? "참여 링크가 복사되었어요" : "팀 참여 링크 복사"}
          </button>
          <button
            type="button"
            className="admin-preview-button"
            onClick={() => {
              window.sessionStorage.setItem("tmti-inline-demo-preview", "1");
              setShowPreview(true);
            }}
          >
            관리자 · 결과 미리보기 <span aria-hidden="true">→</span>
          </button>
        </div>
        <p className="waiting-demo-note">
          시연용 버튼이며, 현재 기기에서 작성한 응답으로 결과를 보여 줍니다.
        </p>
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
    completedMembers: 0,
    expectedMembers: team.expectedMembers,
    joinedMembers: 1,
    members: [],
    ready: false,
  });
  const [copied, setCopied] = useState(false);
  const [qrCode, setQrCode] = useState("");
  const invite =
    typeof window === "undefined"
      ? ""
      : `${window.location.origin}/?team=${team.code}`;
  useEffect(() => {
    const refresh = async () => {
      const response = await fetch(`/api/teams/${team.code}`, {
        cache: "no-store",
      });
      if (response.ok) setStatus(await response.json());
    };
    refresh();
    const timer = window.setInterval(refresh, 3000);
    return () => window.clearInterval(timer);
  }, [team.code]);
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
            <p className="invite-code">{team.code}</p>
            <button
              className="invite-button lobby-copy"
              onClick={async () => {
                await navigator.clipboard?.writeText(invite);
                setCopied(true);
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
              </div>
              <button
                className="lobby-refresh"
                onClick={async () => {
                  const response = await fetch(`/api/teams/${team.code}`, {
                    cache: "no-store",
                  });
                  if (response.ok) setStatus(await response.json());
                }}
                aria-label="참여 현황 새로고침"
              >
                ↻
              </button>
            </div>
            <ul>
              {Array.from({ length: status.expectedMembers }, (_, index) => {
                const member = status.members[index];
                return (
                  <li className={member ? "joined" : "waiting"} key={index}>
                    <i>{member ? (member.completed ? "✓" : "●") : ""}</i>
                    <span>{member?.displayName ?? "팀원 참여 대기"}</span>
                    <small>
                      {member
                        ? member.completed
                          ? "설문 완료"
                          : "설문 전"
                        : "대기"}
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
            나중에 하기
          </Link>
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
  const inviteCode =
    typeof window === "undefined"
      ? ""
      : (new URLSearchParams(window.location.search).get("team") ?? "");
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
    Number(teamSize) >= 2 &&
    Number(teamSize) <= 10;
  useEffect(() => {
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
  }, []);
  const startSurvey = async () => {
    if (!validTeamSetup) {
      setShowTeamValidation(true);
      return;
    }
    setShowTeamValidation(false);
    setTeamError("");
    const response = await fetch("/api/teams", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        teamName,
        expectedMembers: Number(teamSize),
        displayName,
      }),
    });
    if (!response.ok) {
      setTeamError("팀을 만들지 못했어요. 잠시 후 다시 시도해 주세요.");
      return;
    }
    const created = await response.json();
    const session = {
      code: created.code,
      teamName: created.teamName,
      expectedMembers: created.expectedMembers,
      memberId: created.memberId,
    };
    saveTeamSession(session, "lobby");
    setTeamSession(session);
    setStep(-2);
  };
  const joinSurvey = async () => {
    if (!displayName.trim()) {
      setShowTeamValidation(true);
      return;
    }
    setTeamError("");
    const response = await fetch(`/api/teams/${inviteCode}`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ action: "join", displayName }),
    });
    if (!response.ok) {
      setTeamError(
        "팀 참여 정보를 확인하지 못했어요. 이름이나 링크를 확인해 주세요.",
      );
      return;
    }
    const joined = await response.json();
    const session = {
      code: joined.code,
      teamName: joined.teamName,
      expectedMembers: joined.expectedMembers,
      memberId: joined.memberId,
    };
    saveTeamSession(session, "survey");
    setTeamSession(session);
    setStep(0);
  };

  if (step === groups.length)
    return (
      <WaitingScreen
        team={
          teamSession ?? {
            code: "DEMO",
            teamName: teamName || "우리 팀",
            expectedMembers: Number(teamSize) || 2,
            memberId: "demo",
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
              inviteCode ? joinSurvey() : startSurvey();
            }}
          >
            <div className="team-setup-heading">
              <b>
                {inviteCode
                  ? "팀에 참여하고 시작해요"
                  : "팀 정보를 먼저 알려주세요"}
              </b>
              <span>
                {inviteCode
                  ? "결과에서 사용할 표시 이름을 입력해 주세요."
                  : "팀 전체 결과를 준비하는 데 사용돼요."}
              </span>
            </div>
            <div className="team-fields">
              {!inviteCode && (
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
                      placeholder="2~10명"
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
            {!inviteCode && (
              <p id="team-size-help" className="team-setup-help">
                참여 인원은 모든 팀원이 설문을 마친 뒤 팀 분석을 열기 위한
                기준입니다.
              </p>
            )}
            {showTeamValidation && (
              <p className="team-setup-error" aria-live="polite">
                {inviteCode
                  ? "팀원에게 보일 이름을 입력해 주세요."
                  : "팀명과 표시 이름을 입력하고, 참여 인원은 2~10명으로 설정해 주세요."}
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
              className="button-next"
              disabled={isSubmitting}
              onClick={async () => {
                if (!completeCurrent) {
                  setShowValidation(true);
                  return;
                }
                if (step === groups.length - 1) {
                  saveDemoResult({
                    displayName: displayName.trim() || "나",
                    teamName:
                      teamSession?.teamName || teamName.trim() || "우리 팀",
                    responses: answers,
                  });
                  if (teamSession) saveTeamSession(teamSession, "waiting");
                }
                setStep((previous) => previous + 1);
              }}
            >
              {isSubmitting
                ? "응답 저장 중"
                : step === groups.length - 1
                  ? "응답 확인"
                  : "다음"}{" "}
              {!isSubmitting && "→"}
            </button>
          </div>
        </section>
      </div>
    </main>
  );
}

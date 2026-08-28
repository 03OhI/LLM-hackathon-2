"use client";

import Image from "next/image";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

type ResultStatus = "PROCESSING" | "COMPLETED" | "FALLBACK" | "NOT_REQUESTED";

type TeamSnapshot = {
  title: string;
  formula: string;
  scene: string;
  keywords: string[];
  used_rule_ids: string[];
};

type PrivateCard = {
  card_title: string;
  contribution: string;
  optional_try: string | null;
  used_rule_ids: string[];
};

type TeamResult = {
  session_id: string;
  status: ResultStatus;
  team_comment: TeamSnapshot | null;
};

type PersonalResult = {
  participant_id: string;
  status: ResultStatus;
  insight: PrivateCard | null;
};

type View = "personal" | "team";

const sessionStorageKey = "tmti-session-id";
const apiBase = process.env.NEXT_PUBLIC_API_BASE ?? "/backend/api";

const administratorPreview = {
  personal: {
    participant_id: "administrator-preview",
    status: "COMPLETED" as ResultStatus,
    insight: {
      card_title: "흐름을 정리해 팀을 앞으로 움직이는 사람",
      contribution:
        "해야 할 일을 작게 나누고 다음 순서를 제안해, 팀이 막히지 않도록 안정적인 리듬을 만듭니다.",
      optional_try:
        "결정이 필요한 순간에는 우선순위를 한 문장으로 먼저 공유해 보세요.",
      used_rule_ids: [],
    },
  } satisfies PersonalResult,
  team: {
    session_id: "administrator-preview",
    status: "COMPLETED" as ResultStatus,
    team_comment: {
      title: "서로의 속도를 맞추며 완성하는 팀",
      formula: "구조를 잡는 사람 × 실행을 밀어주는 사람 × 분위기를 살피는 사람",
      scene:
        "방향을 먼저 맞춘 뒤 각자의 강점을 나누어 쓰는 팀이에요. 짧은 체크인만 꾸준히 해도 협업의 흐름이 더 단단해집니다.",
      keywords: ["역할 분담", "빠른 공유", "균형 있는 실행"],
      used_rule_ids: [],
    },
  } satisfies TeamResult,
};

export default function ResultsPage() {
  const [view, setView] = useState<View>("personal");
  const [teamResult, setTeamResult] = useState<TeamResult | null>(null);
  const [personalResult, setPersonalResult] = useState<PersonalResult | null>(null);
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const administratorMode = useMemo(() => {
    if (typeof window === "undefined") return false;
    return new URLSearchParams(window.location.search).get("mode") === "admin";
  }, []);
  const sessionId = useMemo(() => {
    if (typeof window === "undefined") return "";
    const params = new URLSearchParams(window.location.search);
    return params.get("sessionId") ?? params.get("session") ?? window.sessionStorage.getItem(sessionStorageKey) ?? "";
  }, []);

  useEffect(() => {
    if (administratorMode) {
      return;
    }
    if (!sessionId) {
      setError("결과를 확인할 세션 정보가 없어요. 초대 링크에서 다시 시작해 주세요.");
      setIsLoading(false);
      return;
    }

    let cancelled = false;
    let pollTimer: number | undefined;
    const load = async () => {
      try {
        const teamResponse = await fetch(`${apiBase}/sessions/${encodeURIComponent(sessionId)}/results/team`, { credentials: "same-origin" });
        if (!teamResponse.ok) throw new Error("TEAM_RESULT_FAILED");
        const nextTeam = (await teamResponse.json()) as TeamResult;
        if (cancelled) return;
        setTeamResult(nextTeam);
        if (nextTeam.status === "PROCESSING") {
          setIsLoading(true);
          pollTimer = window.setTimeout(load, 3000);
          return;
        }

        const personalResponse = await fetch(`${apiBase}/sessions/${encodeURIComponent(sessionId)}/results/me`, { credentials: "same-origin" });
        if (!personalResponse.ok) throw new Error("PERSONAL_RESULT_FAILED");
        const nextPersonal = (await personalResponse.json()) as PersonalResult;
        if (cancelled) return;
        setPersonalResult(nextPersonal);
        if (nextPersonal.status === "PROCESSING") {
          setIsLoading(true);
          pollTimer = window.setTimeout(load, 3000);
          return;
        }
        setIsLoading(false);
      } catch {
        if (!cancelled) {
          setError("결과를 불러오지 못했어요. 잠시 후 다시 시도해 주세요.");
          setIsLoading(false);
        }
      }
    };
    void load();
    return () => {
      cancelled = true;
      if (pollTimer) window.clearTimeout(pollTimer);
    };
  }, [administratorMode, sessionId]);

  const displayedTeam = administratorMode ? administratorPreview.team : teamResult;
  const displayedPersonal = administratorMode
    ? administratorPreview.personal
    : personalResult;

  if (!administratorMode && isLoading) return <ResultLoading />;
  if (error || !displayedTeam || !displayedPersonal)
    return <ResultError message={error} />;

  return (
    <ResultShell>
      <section className="result-tabs" aria-label="결과 보기 방식">
        <button className={view === "personal" ? "active" : ""} onClick={() => setView("personal")}>개인 결과</button>
        <button className={view === "team" ? "active" : ""} onClick={() => setView("team")}>우리 팀 분석</button>
      </section>
      {view === "personal" ? <PersonalReport insight={displayedPersonal.insight} onTeam={() => setView("team")} /> : <TeamReport snapshot={displayedTeam.team_comment} onPersonal={() => setView("personal")} />}
    </ResultShell>
  );
}

function ResultShell({ children }: { children: React.ReactNode }) {
  return <main className="survey-shell results-shell"><nav className="survey-nav"><Link className="survey-home" href="/" aria-label="홈으로">⌂</Link><Image className="survey-brand-image" src="/tmti-survey-logo.png" alt="TMTI" width={220} height={124} priority /></nav>{children}</main>;
}

function ResultLoading() {
  return <ResultShell><section className="result-message"><Image src="/duck-face-open.png" alt="결과를 준비하는 TMTI 오리" width={112} height={112} priority /><p className="result-eyebrow">결과 준비 중</p><h1>팀의 협업 이야기를 정리하고 있어요.</h1><p>완료되면 이 화면에서 개인 결과와 팀 분석을 함께 볼 수 있어요.</p></section></ResultShell>;
}

function ResultError({ message }: { message: string }) {
  return <ResultShell><section className="result-message"><Image src="/duck-face-wink.png" alt="TMTI 오리" width={108} height={108} /><h1>{message || "결과를 준비하지 못했어요."}</h1><Link href="/" className="button-next">홈으로</Link></section></ResultShell>;
}

function PersonalReport({ insight, onTeam }: { insight: PrivateCard | null; onTeam: () => void }) {
  if (!insight) return <ResultError message="개인 결과를 아직 준비하고 있어요." />;
  return <section className="result-report api-result-report survey-card-enter"><header className="api-result-hero"><div><p className="result-kicker">나의 협업 이야기</p><h1>{insight.card_title}</h1><p>평가가 아닌, 팀에서 더 편하게 함께하기 위한 제안이에요.</p></div><Image src="/duck-face-sparkle.png" alt="기쁜 표정의 TMTI 오리" width={128} height={128} priority /></header><article className="api-insight-card api-personal-card"><span>팀에 기여하는 방식</span><p>{insight.contribution}</p>{insight.optional_try && <div className="optional-try"><b>함께 시도해 볼 점</b><p>{insight.optional_try}</p></div>}</article><button className="result-team-link" onClick={onTeam}>우리 팀 분석 보기 <b>→</b></button></section>;
}

function TeamReport({ snapshot, onPersonal }: { snapshot: TeamSnapshot | null; onPersonal: () => void }) {
  if (!snapshot) return <ResultError message="팀 결과를 아직 준비하고 있어요." />;
  return <section className="result-report api-result-report survey-card-enter"><header className="api-result-hero"><div><p className="result-kicker">우리 팀의 협업 이야기</p><h1>{snapshot.title}</h1><p>서로를 줄 세우지 않고, 함께 일할 방식을 찾아봅니다.</p></div><Image src="/duck-face-smile.png" alt="웃는 표정의 TMTI 오리" width={122} height={122} /></header><article className="api-insight-card api-team-card"><span>우리 팀의 조합</span><h2>{snapshot.formula}</h2><p>{snapshot.scene}</p><div className="keyword-list" aria-label="팀 핵심 키워드">{snapshot.keywords.map((keyword) => <b key={keyword}>#{keyword}</b>)}</div></article><button className="result-team-link" onClick={onPersonal}>내 협업 스타일 보기 <b>→</b></button></section>;
}

"use client";

import Image from "next/image";
import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";

const typeCodes = ["PLCD", "PLCI", "PLHD", "PLHI", "PSCD", "PSCI", "PSHD", "PSHI", "ALCD", "ALCI", "ALHD", "ALHI", "ASCD", "ASCI", "ASHD", "ASHI"];
type Tab = "home" | "guide" | "survey" | "types" | "results";
type InvitePreview = { sessionName: string; expectedMembers: number; inviteToken: string };
const tabs: { id: Tab; icon: string; label: string }[] = [{ id: "home", icon: "⌂", label: "홈" }, { id: "guide", icon: "↝", label: "테스트 방법" }, { id: "survey", icon: "◌", label: "설문 문항" }, { id: "types", icon: "▦", label: "16유형" }, { id: "results", icon: "◷", label: "분석 결과" }];

const apiBase = process.env.NEXT_PUBLIC_API_BASE ?? "/backend/api";

// 붙여넣은 초대 링크(?invite=...) 또는 토큰 원문에서 초대 토큰을 뽑아낸다.
function inviteTokenFrom(value: string): string | null {
  const trimmed = value.trim();
  if (!trimmed) return null;
  try {
    const url = new URL(trimmed);
    const fromQuery = url.searchParams.get("invite") ?? url.searchParams.get("team");
    if (fromQuery) return fromQuery;
  } catch {
    /* URL이 아니면 토큰 원문으로 취급 */
  }
  return /^[A-Za-z0-9_-]{10,}$/.test(trimmed) ? trimmed : null;
}

// 이 브라우저에서 진행 중이던 세션 ID를 저장소에서 찾는다.
function savedSessionId(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return (
      window.sessionStorage.getItem("tmti-session-id") ??
      window.localStorage.getItem("tmti-session-id")
    );
  } catch {
    return null;
  }
}

function savedTeamName(): string {
  if (typeof window === "undefined") return "";
  try {
    const raw =
      window.sessionStorage.getItem("tmti-active-team-session") ??
      window.localStorage.getItem("tmti-active-team-session");
    if (!raw) return "";
    return JSON.parse(raw)?.team?.teamName ?? "";
  } catch {
    return "";
  }
}

export default function Home() {
  const [activeTab, setActiveTab] = useState<Tab>("home");
  const [inviteInput, setInviteInput] = useState("");
  const [token, setToken] = useState<string | null>(() =>
    typeof window === "undefined"
      ? null
      : new URLSearchParams(window.location.search).get("invite") ??
        new URLSearchParams(window.location.search).get("team"),
  );
  const [invite, setInvite] = useState<InvitePreview | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    setError("");
    fetch(`${apiBase}/invites/${encodeURIComponent(token)}`, {
      cache: "no-store",
      credentials: "same-origin",
    })
      .then((response) => (response.ok ? response.json() : Promise.reject()))
      .then((data) => {
        if (cancelled) return;
        setInvite({
          sessionName: data.session_name,
          expectedMembers: data.expected_member_count,
          inviteToken: token,
        });
      })
      .catch(() => {
        if (!cancelled) setError("초대 링크를 확인하지 못했어요. 링크를 다시 확인해 주세요.");
      });
    return () => {
      cancelled = true;
    };
  }, [token]);

  const openInvite = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const next = inviteTokenFrom(inviteInput);
    if (!next) {
      setError("초대 링크 또는 초대 코드를 입력해 주세요.");
      return;
    }
    setError("");
    setInvite(null);
    setToken(next);
    window.history.replaceState(null, "", `/?invite=${encodeURIComponent(next)}`);
  };

  if (invite) return <InviteConfirm invite={invite} />;

  return <main className="dashboard-shell"><section className="dashboard-top">
    <article className="welcome-card"><div className="welcome-brand"><span className="brand-text">TMTI+</span><span>TEAM · MATCH · TYPE · INDICATOR</span></div><div className="welcome-main"><div className="welcome-logo"><Image src="/tmti-hero.png" alt="TMTI 캐릭터 로고" width={620} height={620} priority /></div><div className="welcome-copy"><p>당신의 성장과 팀의 변화를 위한<br />따뜻한 협업 스타일 테스트.</p><h1>팀프로젝트 전<br /><strong>확인해보세요!</strong></h1><div className="entry-actions"><Link href="/survey" className="start-button home-action-primary"><PeopleIcon /><span className="action-copy"><b>테스트 방 만들기</b><small>새로운 팀 프로젝트를 시작해보세요.</small></span><em>→</em></Link><form className="invite-entry home-action-secondary" onSubmit={openInvite}><LinkIcon /><div className="invite-fields"><label htmlFor="invite-link">팀원 · 초대 링크 접속하기</label><div><input id="invite-link" value={inviteInput} onChange={(event) => setInviteInput(event.target.value)} placeholder="초대 링크 붙여넣기" /><button type="submit">확인</button></div></div></form><button className="result-button home-action-result" onClick={() => setActiveTab("results")}><ReportIcon /><span>기존 팀 분석 결과 불러오기</span><em>→</em></button></div>{error && <p className="invite-entry-error">{error}</p>}<div className="welcome-links"><button onClick={() => setActiveTab("survey")}>▣ 설문 문항 미리보기</button><i /><button onClick={() => setActiveTab("types")}>▦ 16유형 미리보기</button></div></div></div></article>
    <article className="workspace-card" aria-label="TMTI 미리보기"><aside className="workspace-nav"><b>TMTI+</b>{tabs.map((tab) => <button key={tab.id} className={activeTab === tab.id ? "nav-active" : ""} onClick={() => setActiveTab(tab.id)}><span aria-hidden="true">{tab.icon}</span>{tab.label}</button>)}</aside><div className="workspace-content">{activeTab === "home" && <HomePanel />}{activeTab === "guide" && <GuidePanel />}{activeTab === "survey" && <SurveyPanel />}{activeTab === "types" && <TypesPanel />}{activeTab === "results" && <ResultsPanel />}</div></article>
  </section></main>;
}

function InviteConfirm({ invite }: { invite: InvitePreview }) {
  return <main className="dashboard-shell"><section className="invite-confirm welcome-card"><Image src="/duck-face-open.png" alt="" width={84} height={84} /><p>팀 초대가 도착했어요</p><h1><strong>{invite.sessionName}</strong> 테스트 방에<br />초대되었어요.</h1><span>참여 인원 {invite.expectedMembers}명으로 준비된 팀이에요.</span><Link href={`/survey?invite=${encodeURIComponent(invite.inviteToken)}`} className="start-button">테스트 하러 가기 <b>→</b></Link><Link href="/" className="invite-change">다른 초대 링크 입력하기</Link></section></main>;
}
function PeopleIcon() { return <svg className="home-action-icon" viewBox="0 0 48 48" aria-hidden="true"><circle cx="18" cy="17" r="5" /><circle cx="31" cy="17" r="5" /><path d="M8 34c0-5 4-9 10-9s10 4 10 9M22 34c0-5 4-9 10-9s10 4 10 9" /></svg>; }
function LinkIcon() { return <svg className="home-action-icon" viewBox="0 0 48 48" aria-hidden="true"><path d="M19 29l-3 3a7 7 0 01-10-10l7-7a7 7 0 0110 0" /><path d="M29 19l3-3a7 7 0 0110 10l-7 7a7 7 0 01-10 0" /><path d="M16 32l16-16" /></svg>; }
function ReportIcon() { return <svg className="home-action-icon" viewBox="0 0 48 48" aria-hidden="true"><path d="M14 6h14l8 8v26H14z" /><path d="M28 6v9h8M20 23h10M20 30h4M29 29v6M33 26v9" /></svg>; }
function HomePanel() { return <><p className="workspace-greeting">새로운 팀 분석을 시작해볼까요?</p><div className="workspace-start"><span className="clipboard">✓</span><div><h2>새로운 팀 분석 시작</h2><p>팀프로젝트 전, 서로의 협업 방식을 살펴보세요.</p></div><Link href="/survey">테스트 방 만들기 <span>→</span></Link></div><div className="workspace-steps"><p>테스트는 이렇게 진행돼요</p><ol><li><b>1</b> 테스트 방 만들기</li><li><b>2</b> 초대 링크 공유</li><li><b>3</b> 팀 결과 확인</li></ol></div></>; }
function GuidePanel() { return <section className="tab-panel guide-panel" aria-labelledby="guide-heading"><header className="tab-heading"><div><p>테스트 방법</p><h2 id="guide-heading">이렇게 진행돼요</h2></div></header><ol><li><b>1</b><div><strong>테스트 방 만들기</strong><span>팀장이 팀명과 참여 인원을 입력해요.</span></div></li><li><b>2</b><div><strong>링크 또는 QR 공유</strong><span>팀원은 초대 링크를 확인한 뒤 참여해요.</span></div></li><li><b>3</b><div><strong>각자 24문항 응답</strong><span>평소 협업할 때의 모습에 가깝게 골라요.</span></div></li><li><b>4</b><div><strong>팀 결과 함께 보기</strong><span>모두 완료되면 개인·팀 결과가 준비돼요.</span></div></li></ol></section>; }
function SurveyPanel() { return <section className="tab-panel" aria-labelledby="survey-heading"><header className="tab-heading"><div><p>설문 문항 미리보기</p><h2 id="survey-heading">01 <span>/ 24</span></h2></div><Link href="/survey">전체 문항 보기 →</Link></header><div className="tab-question"><p className="quote-mark">“</p><h3>새로운 과제를 받았을 때,<br />나는 어떻게 시작하는 편인가?</h3><p>본인의 평소 모습에 가장 가까운 답을 골라주세요.</p><div className="tab-scale">{["매우 아니다", "아니다", "보통이다", "그렇다", "매우 그렇다"].map((label, index) => <span key={label}><b>{index + 1}</b>{label}</span>)}</div></div></section>; }
function TypesPanel() { return <section className="tab-panel" aria-labelledby="types-heading"><header className="tab-heading"><div><p>16유형 미리보기</p><h2 id="types-heading">협업 스타일 16가지</h2></div></header><p className="type-description">계획성·주도성·갈등 대응·소통 직접성의 조합으로 팀 안에서의 협업 방식을 살펴봅니다.</p><div className="type-grid">{typeCodes.map((type, index) => <span key={type} className={`type-chip chip-${index % 4}`}>{type}</span>)}</div></section>; }
function ResultsPanel() {
  // 결과 탭은 사용자가 클릭해야 마운트되므로(클라이언트 전용) 지연 초기화로 저장소를 읽는다.
  const [sessionId] = useState<string | null>(() => savedSessionId());
  const [teamName] = useState(() => savedTeamName());
  if (sessionId) {
    return <section className="tab-panel result-empty" aria-labelledby="results-heading"><div className="result-empty-mark">◷</div><p>분석 결과</p><h2 id="results-heading">{teamName ? `${teamName} 결과 이어보기` : "저장된 팀 결과 이어보기"}</h2><span>이 브라우저에서 참여한 팀의 결과를 바로 다시 볼 수 있어요.</span><Link href={`/results?sessionId=${encodeURIComponent(sessionId)}`} className="start-button" style={{ marginTop: 14 }}>결과 보기 <b>→</b></Link></section>;
  }
  return <section className="tab-panel result-empty" aria-labelledby="results-heading"><div className="result-empty-mark">◷</div><p>분석 결과</p><h2 id="results-heading">불러올 결과가 없어요</h2><span>이 브라우저에서 진행한 팀 테스트가 없어요. 새로 시작하거나 초대 링크로 참여해 주세요.</span><Link href="/survey" style={{ marginTop: 12 }}>테스트 방 만들기 →</Link></section>;
}

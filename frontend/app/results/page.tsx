"use client";

import Image from "next/image";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

type Personal = {
  displayName: string;
  result: {
    code: string | null;
    type: { alias: string; strength: string; caution: string; role: string } | null;
    axes: Record<string, { label: string; ratio: number; state: string; pole: string | null }>;
  };
};
type Team = { total: number; grade: string; faultline: string; frictions: string[]; axisScores: Record<string, number> };

const axisOrder = ["plan", "drive", "conflict", "communication"];

export default function ResultsPage() {
  const [personal, setPersonal] = useState<Personal | null>(null);
  const [team, setTeam] = useState<Team | null>(null);
  const [view, setView] = useState<"choose" | "personal" | "team">("choose");
  const [error, setError] = useState("");
  const { teamCode, memberId } = useMemo(() => {
    if (typeof window === "undefined") return { teamCode: "", memberId: "" };
    const params = new URLSearchParams(window.location.search);
    return { teamCode: params.get("team") ?? "", memberId: params.get("member") ?? "" };
  }, []);

  useEffect(() => {
    if (!teamCode || !memberId) return;
    Promise.all([
      fetch(`/api/teams/${teamCode}?view=personal&memberId=${memberId}`).then(async (response) => response.ok ? response.json() : Promise.reject()),
      fetch(`/api/teams/${teamCode}?view=team`).then(async (response) => response.ok ? response.json() : Promise.reject()),
    ]).then(([personalData, teamData]) => { setPersonal(personalData); setTeam(teamData); }).catch(() => setError("아직 팀 결과를 준비하고 있어요. 잠시 후 다시 확인해 주세요."));
  }, [memberId, teamCode]);

  if (!teamCode || !memberId || error) return <ResultShell><section className="result-message"><Image src="/duck-face-wink.png" alt="" width={110} height={110} /><h1>{error || "결과를 확인할 정보를 찾지 못했어요."}</h1><Link href="/" className="button-next">홈으로</Link></section></ResultShell>;
  if (!personal || !team) return <ResultShell><section className="result-message"><div className="result-loader" /><p>팀의 협업 결과를 정리하고 있어요.</p></section></ResultShell>;

  return <ResultShell>
    {view === "choose" && <section className="result-choose survey-card-enter"><Image src="/duck-face-sparkle.png" alt="" width={120} height={120} /><p>TEAM RESULT READY</p><h1>{personal.displayName}님, 결과가 준비됐어요.</h1><span>나의 협업 경향과 우리 팀의 조합을 각각 살펴볼 수 있어요.</span><div><button onClick={() => setView("personal")}>내 협업 스타일 보기 <b>→</b></button><button onClick={() => setView("team")}>우리 팀 분석 보기 <b>→</b></button></div></section>}
    {view === "personal" && <PersonalResult personal={personal} onBack={() => setView("choose")} />}
    {view === "team" && <TeamResult team={team} onBack={() => setView("choose")} />}
  </ResultShell>;
}

function ResultShell({ children }: { children: React.ReactNode }) { return <main className="survey-shell results-shell"><nav className="survey-nav"><Link className="survey-home" href="/" aria-label="홈으로">⌂</Link><Image className="survey-brand-image" src="/tmti-survey-logo.png" alt="TMTI" width={220} height={124} priority /></nav>{children}</main>; }

function PersonalResult({ personal, onBack }: { personal: Personal; onBack: () => void }) {
  const type = personal.result.type;
  return <section className="result-report survey-card-enter"><button className="result-back" onClick={onBack}>← 결과 선택</button><div className="result-title"><div><p>MY COLLABORATION STYLE</p><h1>{type ? type.alias : "균형을 살피는 협업자"}</h1><span>{type ? `${personal.result.code} · ${personal.displayName}님의 협업 경향` : "아직 한쪽으로 뚜렷하지 않은 축이 있어요."}</span></div><Image src="/duck-face-open.png" alt="" width={104} height={104} /></div><section className="axis-grid">{axisOrder.map((axis) => { const score = personal.result.axes[axis]; return <article key={axis}><b>{score.label}</b><div><i style={{ width: `${score.ratio * 100}%` }} /></div><span>{score.pole ? `${score.pole} 성향` : "뚜렷하지 않음"}</span></article>; })}</section>{type && <section className="insight-grid"><article><b>강점</b><p>{type.strength}</p></article><article><b>협업할 때 유의할 점</b><p>{type.caution}</p></article><article><b>팀에서 잘 맞는 자리</b><p>{type.role}</p></article></section>}</section>;
}

function TeamResult({ team, onBack }: { team: Team; onBack: () => void }) {
  return <section className="result-report survey-card-enter"><button className="result-back" onClick={onBack}>← 결과 선택</button><div className="result-title"><div><p>OUR TEAM ANALYSIS</p><h1>우리 팀의 협업 지도</h1><span>팀 상태 <b className="team-grade">{team.grade}</b> · {team.faultline}</span></div><Image src="/duck-face-smile.png" alt="" width={104} height={104} /></div><section className="team-score"><b>협업 균형도</b><strong>{Math.round(team.total * 100)}점</strong><div><i style={{ width: `${team.total * 100}%` }} /></div></section><section className="axis-grid">{axisOrder.map((axis) => <article key={axis}><b>{{ plan: "계획성", drive: "주도성", conflict: "갈등 대응", communication: "소통 직접성" }[axis]}</b><div><i style={{ width: `${team.axisScores[axis] * 100}%` }} /></div><span>{Math.round(team.axisScores[axis] * 100)} / 100</span></article>)}</section><section className="insight-grid"><article><b>먼저 합의할 지점</b><p>{team.frictions.length ? team.frictions.join(" ") : "현재는 큰 방식 차이가 보이지 않아요. 맡을 일과 의사결정 기준부터 정해보세요."}</p></article><article><b>첫 회의에서 물어볼 질문</b><p>누가 최종 결정을 정리할까요?<br />일정이 바뀌면 어디에 먼저 공유할까요?<br />의견이 다를 때 어떤 방식으로 말할까요?</p></article></section></section>;
}

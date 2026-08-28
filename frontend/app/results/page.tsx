"use client";

import Image from "next/image";
import Link from "next/link";
import { useEffect, useMemo, useState, type CSSProperties, type ReactNode } from "react";

type ResultStatus = "PROCESSING" | "COMPLETED" | "FALLBACK" | "NOT_REQUESTED";
type AxisKey = "planning" | "agency" | "conflict" | "communication";
type Positions = Partial<Record<AxisKey, string>>;
type Distribution = Partial<Record<AxisKey, Record<string, number>>>;
type TeamSnapshot = { title: string; formula: string; scene: string; keywords: string[]; used_rule_ids: string[] };
type PrivateCard = { card_title: string; contribution: string; optional_try: string | null; used_rule_ids: string[] };
type MemberPosition = { participant_id: string; display_name: string; self_positions: Positions };
type TeamResult = { session_id: string; status: ResultStatus; distribution: Distribution | null; member_positions: MemberPosition[]; team_comment: TeamSnapshot | null };
type PersonalResult = { participant_id: string; status: ResultStatus; self_positions: Positions | null; insight: PrivateCard | null };
type View = "personal" | "team";

const sessionStorageKey = "tmti-session-id";
const apiBase = process.env.NEXT_PUBLIC_API_BASE ?? "/backend/api";
const axes: Array<{ key: AxisKey; label: string; left: string; right: string; leftValue: string; rightValue: string; leftCode: string; rightCode: string; color: string; soft: string }> = [
  { key: "planning", label: "계획성", left: "계획형", right: "적응형", leftValue: "PLANNER", rightValue: "ADAPTER", leftCode: "P", rightCode: "A", color: "#e9826b", soft: "#fff1ec" },
  { key: "agency", label: "주도성", left: "주도형", right: "지원형", leftValue: "DRIVER", rightValue: "SUPPORTER", leftCode: "D", rightCode: "S", color: "#e6ae3e", soft: "#fff8e8" },
  { key: "conflict", label: "갈등 대응", left: "직면형", right: "조율형", leftValue: "CONFRONTER", rightValue: "HARMONIZER", leftCode: "C", rightCode: "H", color: "#88a281", soft: "#f2f8f0" },
  { key: "communication", label: "소통 직접성", left: "직설형", right: "완곡형", leftValue: "DIRECT", rightValue: "TACTFUL", leftCode: "D", rightCode: "T", color: "#7e9fbe", soft: "#f0f6fb" },
];

const administratorPreview = {
  personal: { participant_id: "administrator-preview", status: "COMPLETED" as ResultStatus, self_positions: { planning: "PLANNER", agency: "DRIVER", conflict: "HARMONIZER", communication: "TACTFUL" }, insight: { card_title: "흐름을 정리해 팀을 앞으로 움직이는 사람", contribution: "해야 할 일을 작게 나누고 다음 순서를 제안해, 팀이 막히지 않도록 안정적인 리듬을 만듭니다.", optional_try: "결정이 필요한 순간에는 우선순위를 한 문장으로 먼저 공유해 보세요.", used_rule_ids: [] } } satisfies PersonalResult,
  team: { session_id: "administrator-preview", status: "COMPLETED" as ResultStatus, distribution: { planning: { PLANNER: 3, ADAPTER: 1, NEUTRAL: 0 }, agency: { DRIVER: 2, SUPPORTER: 1, NEUTRAL: 1 }, conflict: { CONFRONTER: 1, HARMONIZER: 2, NEUTRAL: 1 }, communication: { DIRECT: 2, TACTFUL: 2, NEUTRAL: 0 } }, member_positions: [{ participant_id: "a", display_name: "서연", self_positions: { planning: "PLANNER", agency: "DRIVER", conflict: "HARMONIZER", communication: "TACTFUL" } }, { participant_id: "b", display_name: "민준", self_positions: { planning: "PLANNER", agency: "SUPPORTER", conflict: "CONFRONTER", communication: "DIRECT" } }, { participant_id: "c", display_name: "지우", self_positions: { planning: "ADAPTER", agency: "DRIVER", conflict: "HARMONIZER", communication: "DIRECT" } }, { participant_id: "d", display_name: "하늘", self_positions: { planning: "PLANNER", agency: "NEUTRAL", conflict: "HARMONIZER", communication: "TACTFUL" } }], team_comment: { title: "서로의 속도를 맞추며 완성하는 팀", formula: "구조를 잡는 사람 × 실행을 밀어주는 사람 × 분위기를 살피는 사람", scene: "방향을 먼저 맞춘 뒤 각자의 강점을 나누어 쓰는 팀이에요. 짧은 체크인만 꾸준히 해도 협업의 흐름이 더 단단해집니다.", keywords: ["역할 분담", "빠른 공유", "균형 있는 실행"], used_rule_ids: [] } } satisfies TeamResult,
};

function positionLabel(axis: (typeof axes)[number], value: string | undefined) { return value === axis.leftValue ? axis.left : value === axis.rightValue ? axis.right : "균형형"; }
function positionCode(axis: (typeof axes)[number], value: string | undefined) { return value === axis.leftValue ? axis.leftCode : value === axis.rightValue ? axis.rightCode : "N"; }
function positionPoint(axis: (typeof axes)[number], value: string | undefined) { return value === axis.leftValue ? 82 : value === axis.rightValue ? 18 : 50; }
function resultCode(positions: Positions | null) { return axes.map((axis) => positionCode(axis, positions?.[axis.key])).join("-"); }

export default function ResultsPage() {
  const [view, setView] = useState<View>("personal");
  const [teamResult, setTeamResult] = useState<TeamResult | null>(null);
  const [personalResult, setPersonalResult] = useState<PersonalResult | null>(null);
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const administratorMode = useMemo(() => typeof window !== "undefined" && new URLSearchParams(window.location.search).get("mode") === "admin", []);
  const sessionId = useMemo(() => {
    if (typeof window === "undefined") return "";
    const params = new URLSearchParams(window.location.search);
    return params.get("sessionId") ?? params.get("session") ?? window.sessionStorage.getItem(sessionStorageKey) ?? "";
  }, []);

  useEffect(() => {
    if (administratorMode) return;
    if (!sessionId) { setError("결과를 확인할 세션 정보가 없어요. 초대 링크에서 다시 시작해 주세요."); setIsLoading(false); return; }
    let cancelled = false;
    let pollTimer: number | undefined;
    const load = async () => {
      try {
        const teamResponse = await fetch(`${apiBase}/sessions/${encodeURIComponent(sessionId)}/results/team`, { credentials: "same-origin" });
        if (!teamResponse.ok) throw new Error("TEAM_RESULT_FAILED");
        const nextTeam = (await teamResponse.json()) as TeamResult;
        if (cancelled) return;
        setTeamResult(nextTeam);
        if (nextTeam.status === "PROCESSING") { pollTimer = window.setTimeout(load, 3000); return; }
        const personalResponse = await fetch(`${apiBase}/sessions/${encodeURIComponent(sessionId)}/results/me`, { credentials: "same-origin" });
        if (!personalResponse.ok) throw new Error("PERSONAL_RESULT_FAILED");
        const nextPersonal = (await personalResponse.json()) as PersonalResult;
        if (cancelled) return;
        setPersonalResult(nextPersonal);
        if (nextPersonal.status === "PROCESSING") { pollTimer = window.setTimeout(load, 3000); return; }
        setIsLoading(false);
      } catch {
        if (!cancelled) { setError("결과를 불러오지 못했어요. 잠시 후 다시 시도해 주세요."); setIsLoading(false); }
      }
    };
    void load();
    return () => { cancelled = true; if (pollTimer) window.clearTimeout(pollTimer); };
  }, [administratorMode, sessionId]);

  const displayedTeam = administratorMode ? administratorPreview.team : teamResult;
  const displayedPersonal = administratorMode ? administratorPreview.personal : personalResult;
  if (!administratorMode && isLoading) return <ResultLoading />;
  if (error || !displayedTeam || !displayedPersonal) return <ResultError message={error} />;
  return <ResultShell><section className="result-tabs" aria-label="결과 보기 방식"><button className={view === "personal" ? "active" : ""} onClick={() => setView("personal")}>개인 결과</button><button className={view === "team" ? "active" : ""} onClick={() => setView("team")}>우리 팀 분석</button></section>{view === "personal" ? <PersonalReport insight={displayedPersonal.insight} positions={displayedPersonal.self_positions} onTeam={() => setView("team")} /> : <TeamReport snapshot={displayedTeam.team_comment} distribution={displayedTeam.distribution} memberPositions={displayedTeam.member_positions ?? []} onPersonal={() => setView("personal")} />}</ResultShell>;
}

function ResultShell({ children }: { children: ReactNode }) { return <main className="survey-shell results-shell"><nav className="survey-nav result-nav"><Link className="survey-home" href="/" aria-label="홈으로">⌂</Link><Image className="tmti-header-brand" src="/tmti-survey-logo.png" alt="TMTI 오리 로고" width={196} height={110} priority /></nav>{children}</main>; }
function ResultLoading() { return <ResultShell><section className="result-message"><Image src="/duck-face-open.png" alt="결과를 준비하는 TMTI 오리" width={112} height={112} priority /><p className="result-eyebrow">결과 준비 중</p><h1>팀의 협업 이야기를 정리하고 있어요.</h1><p>완료되면 이 화면에서 개인 결과와 팀 분석을 함께 볼 수 있어요.</p></section></ResultShell>; }
function ResultError({ message }: { message: string }) { return <ResultShell><section className="result-message"><Image src="/duck-face-wink.png" alt="TMTI 오리" width={108} height={108} /><h1>{message || "결과를 준비하지 못했어요."}</h1><Link href="/" className="button-next">홈으로</Link></section></ResultShell>; }

function RadarChart({ positions }: { positions: Positions | null }) {
  const center = 137; const radius = 91;
  const points = axes.map((axis, index) => { const ratio = positionPoint(axis, positions?.[axis.key]) / 100; return ([[center, center - radius * ratio], [center + radius * ratio, center], [center, center + radius * ratio], [center - radius * ratio, center]][index]).join(","); }).join(" ");
  return <div className="radar-chart" aria-label="네 가지 협업 성향 위치 지도"><svg viewBox="0 0 274 274" role="img"><polygon className="radar-grid" points="137,15 259,137 137,259 15,137" /><polygon className="radar-grid-inner" points="137,45 229,137 137,229 45,137" /><line x1="137" y1="15" x2="137" y2="259" /><line x1="15" y1="137" x2="259" y2="137" /><polygon className="radar-shape" points={points} /></svg>{axes.map((axis, index) => <span key={axis.key} className={`radar-label label-${index}`}>{axis.label}</span>)}</div>;
}

const axisDescriptions = ["목표 설정과 체계적인 실행", "주도적인 행동과 리딩", "갈등 상황에서의 유연한 대처", "의사 전달과 정보 공유"];
function RadarCallouts() { return <div className="radar-axis-callouts" aria-hidden="true">{axes.map((axis, index) => <div key={axis.key} className={`radar-axis-callout radar-callout-${index}`} style={{ "--axis": axis.color, "--axis-soft": axis.soft } as CSSProperties}><i>{["⚑", "◎", "♧", "☷"][index]}</i><div><b>{axis.label}</b><span>{axisDescriptions[index]}</span></div></div>)}</div>; }

function PersonalReport({ insight, positions, onTeam }: { insight: PrivateCard | null; positions: Positions | null; onTeam: () => void }) {
  if (!insight) return <ResultError message="개인 결과를 아직 준비하고 있어요." />;
  return <section className="result-report personal-report result-dashboard survey-card-enter">
    <header className="result-dashboard-hero">
      <div className="dashboard-copy"><div className="type-line"><span>나의 협업 유형</span><b>{resultCode(positions)}</b></div><h1>{insight.card_title}</h1><p>점수로 평가하지 않고, 팀에서 편하게 함께하는 방식을 보여주는 성향 지도예요.</p></div>
      <div className="dashboard-mascot" aria-hidden="true"><i className="plus plus-sage">+</i><i className="plus plus-coral">+</i><i className="plus plus-yellow">+</i><Image src="/duck-run-2.png" alt="" width={178} height={178} priority /></div>
    </header>
    <section className="quick-traits" aria-label="한눈에 보는 나의 협업 성향"><article className="quick-intro"><b>✦</b><span>한눈에 보는<br />나의 협업 성향</span></article>{axes.map((axis, index) => <article key={axis.key} style={{ "--axis": axis.color, "--axis-soft": axis.soft } as CSSProperties}><i>{["◎", "⚑", "♧", "☷"][index]}</i><span>{axis.label}</span><b>{positionLabel(axis, positions?.[axis.key])}</b></article>)}</section>
    <section className="dashboard-analysis"><article className="radar-panel radar-panel-feature"><div className="radar-spotlight"><div className="radar-copy"><p>COLLABORATION MAP</p><h2>네 가지 협업 성향</h2><span>각 축의 양끝과 현재 성향 위치를 한눈에 볼 수 있어요. 가운데는 한쪽으로 기울지 않은 균형 상태입니다.</span></div><div className="radar-duck" aria-hidden="true"><i>+</i><i>+</i><i>+</i><Image src="/duck-run-2.png" alt="" width={150} height={150} /></div></div><div className="radar-stage"><RadarChart positions={positions} /><RadarCallouts /></div><div className="radar-legend">{axes.map((axis) => <span key={axis.key}><i style={{ background: axis.color }} />{axis.label}</span>)}<em>— 기준선(균형)</em></div></article><section className="axis-map"><header><div><p>나의 협업 위치</p><h2>상황에 따라 더 자연스러운 방식</h2></div><span aria-label="안내">ⓘ</span></header>{axes.map((axis, index) => { const value = positions?.[axis.key]; return <article className="axis-position" key={axis.key} style={{ "--axis": axis.color, "--axis-light": axis.soft, "--point": `${positionPoint(axis, value)}%` } as CSSProperties}><div className="axis-position-title"><i>{["▣", "⚑", "♧", "☷"][index]}</i><div><b>{axis.label}</b><span>{positionLabel(axis, value)}</span></div></div><div className="axis-poles"><span>{axis.left}</span><span>{axis.right}</span></div><div className="axis-line"><i style={{ left: "var(--point)" }} /></div></article>; })}</section></section>
    <section className="personal-actions"><article className="insight-strength"><span>팀에 기여하는 방식</span><p>{insight.contribution}</p></article>{insight.optional_try && <article className="insight-caution"><span>함께 시도해 볼 점</span><p>{insight.optional_try}</p></article>}<article className="insight-role"><span>유형 조합</span><p>{axes.map((axis) => `${axis.label} ${positionLabel(axis, positions?.[axis.key])}`).join(" · ")}</p></article></section><button className="result-team-link" onClick={onTeam}>우리 팀 분석 보기 <b>→</b></button><ResultFooter />
  </section>;
}

function distributionNote(axis: (typeof axes)[number], counts: Record<string, number>) { const left = counts[axis.leftValue] ?? 0; const right = counts[axis.rightValue] ?? 0; const neutral = counts.NEUTRAL ?? 0; if (left === right) return "두 방식이 고르게 있어 서로의 관점을 나눠 보기 좋아요."; if (neutral >= Math.max(left, right)) return "한쪽으로 서두르기보다 상황을 함께 살피는 팀이에요."; return `${left > right ? axis.left : axis.right} 성향이 조금 더 많아요. 반대 방식의 의견도 회의에서 한 번 확인해 보세요.`; }
function TeamDistribution({ distribution }: { distribution: Distribution | null }) { return <section className="team-distribution"><header><div><p>TEAM BALANCE MAP</p><h2>네 가지 축의 팀원 분포</h2></div><span>인원 분포를 보여주며, 우열이나 점수는 표시하지 않습니다.</span></header><div className="team-distribution-grid">{axes.map((axis) => { const counts = distribution?.[axis.key] ?? {}; const left = counts[axis.leftValue] ?? 0; const neutral = counts.NEUTRAL ?? 0; const right = counts[axis.rightValue] ?? 0; const total = Math.max(1, left + neutral + right); return <article key={axis.key} style={{ "--axis": axis.color, "--axis-soft": axis.soft } as CSSProperties}><div className="distribution-title"><b>{axis.label}</b><span>{left + neutral + right}명 응답</span></div><div className="distribution-poles"><span>{axis.left}</span><span>{axis.right}</span></div><div className="distribution-bar" aria-label={`${axis.label}: ${axis.left} ${left}명, 균형형 ${neutral}명, ${axis.right} ${right}명`}><i style={{ width: `${(left / total) * 100}%` }} /><i style={{ width: `${(neutral / total) * 100}%` }} /><i style={{ width: `${(right / total) * 100}%` }} /></div><div className="distribution-counts"><span>{axis.left} {left}</span><span>균형형 {neutral}</span><span>{axis.right} {right}</span></div><p>{distributionNote(axis, counts)}</p></article>; })}</div></section>; }
function ResultFooter() { return <footer className="result-footer-actions"><Link href="/">홈으로</Link><Link href="/survey">새로운 테스트하기 <b>→</b></Link></footer>; }
function memberAlias(member: MemberPosition) { return axes.map((axis) => positionLabel(axis, member.self_positions[axis.key])).join(" · "); }
function TeamMemberMap({ title, xAxis, yAxis, members }: { title: string; xAxis: (typeof axes)[number]; yAxis: (typeof axes)[number]; members: MemberPosition[] }) {
  const [selected, setSelected] = useState<MemberPosition | null>(null);
  const placed = members.map((member, index) => {
    const x = positionPoint(xAxis, member.self_positions[xAxis.key]); const y = 100 - positionPoint(yAxis, member.self_positions[yAxis.key]);
    const same = members.slice(0, index).filter((item) => positionPoint(xAxis, item.self_positions[xAxis.key]) === x && 100 - positionPoint(yAxis, item.self_positions[yAxis.key]) === y).length;
    const offsets = [[0, 0], [-8, -7], [8, -7], [-8, 8], [8, 8], [0, -13]]; const [dx, dy] = offsets[same % offsets.length];
    return { member, x: x + dx, y: y + dy, hidden: same >= 5 };
  });
  return <article className="member-map"><header><p>TEAM MEMBER MAP</p><h3>{title}</h3><span>점을 누르면 팀원의 협업 성향을 볼 수 있어요.</span></header><div className="member-map-board" aria-label={`${title} 팀원 성향 지도`}><b className="map-axis map-left">{xAxis.left}</b><b className="map-axis map-right">{xAxis.right}</b><b className="map-axis map-top">{yAxis.left}</b><b className="map-axis map-bottom">{yAxis.right}</b><i className="map-cross map-horizontal" /><i className="map-cross map-vertical" />{placed.filter((item) => !item.hidden).map(({ member, x, y }) => <button key={member.participant_id} className="member-dot" style={{ left: `${x}%`, top: `${y}%` }} onClick={() => setSelected(member)} aria-label={`${member.display_name} 성향 보기`}>{member.display_name.slice(0, 2)}</button>)}{placed.filter((item) => item.hidden).length > 0 && <button className="member-dot member-more" style={{ left: "50%", top: "50%" }} onClick={() => setSelected(placed.find((item) => item.hidden)?.member ?? null)}>+{placed.filter((item) => item.hidden).length}</button>}</div>{selected && <aside className="member-detail"><b>{selected.display_name}</b><span>{resultCode(selected.self_positions)}</span><p>{memberAlias(selected)}</p><button onClick={() => setSelected(null)} aria-label="팀원 정보 닫기">×</button></aside>}</article>;
}
function TeamMembersMap({ members }: { members: MemberPosition[] }) { if (!members.length) return null; return <section className="team-member-maps"><header><div><p>TEAM MEMBER MAP</p><h2>팀원 성향 지도</h2></div><span>이름과 성향 위치만 보여주며, 원응답과 점수는 공개하지 않습니다.</span></header><div className="team-member-map-grid"><TeamMemberMap title="협업 진행 방식" xAxis={axes[0]} yAxis={axes[1]} members={members} /><TeamMemberMap title="관계 · 소통 방식" xAxis={axes[2]} yAxis={axes[3]} members={members} /></div></section>; }
function TeamReport({ snapshot, distribution, memberPositions, onPersonal }: { snapshot: TeamSnapshot | null; distribution: Distribution | null; memberPositions: MemberPosition[]; onPersonal: () => void }) { if (!snapshot) return <ResultError message="팀 결과를 아직 준비하고 있어요." />; return <section className="result-report personal-report survey-card-enter"><header className="personal-hero team-hero"><div><p className="result-kicker">우리 팀의 협업 이야기</p><h1>{snapshot.title}</h1><span>서로를 줄 세우지 않고, 각자의 방식이 만나는 지점을 찾습니다.</span></div><Image src="/duck-face-smile.png" alt="웃는 표정의 TMTI 오리" width={122} height={122} /></header><article className="team-story"><span>우리 팀의 조합</span><h2>{snapshot.formula}</h2><p>{snapshot.scene}</p><div className="keyword-list" aria-label="팀 핵심 키워드">{snapshot.keywords.map((keyword) => <b key={keyword}>#{keyword}</b>)}</div></article><TeamDistribution distribution={distribution} /><TeamMembersMap members={memberPositions} /><button className="result-team-link" onClick={onPersonal}>내 협업 스타일 보기 <b>→</b></button><ResultFooter /></section>; }

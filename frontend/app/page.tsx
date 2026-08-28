"use client";

import Image from "next/image";
import Link from "next/link";
import { useState } from "react";

const typeCodes = ["PLCD", "PLCI", "PLHD", "PLHI", "PSCD", "PSCI", "PSHD", "PSHI", "ALCD", "ALCI", "ALHD", "ALHI", "ASCD", "ASCI", "ASHD", "ASHI"];
type Tab = "home" | "survey" | "types" | "results";
const tabs: { id: Tab; icon: string; label: string }[] = [{ id: "home", icon: "⌂", label: "홈" }, { id: "survey", icon: "◌", label: "설문 문항" }, { id: "types", icon: "▦", label: "16유형" }, { id: "results", icon: "◷", label: "분석 결과" }];

export default function Home() {
  const [activeTab, setActiveTab] = useState<Tab>("home");
  return <main className="dashboard-shell"><section className="dashboard-top">
    <article className="welcome-card"><div className="welcome-brand"><span className="brand-text">TMTI+</span><span>TEAM · MATCH · TYPE · INDICATOR</span></div><div className="welcome-main"><div className="welcome-logo"><Image src="/tmti-hero.png" alt="TMTI 캐릭터 로고" width={620} height={620} priority /></div><div className="welcome-copy"><p>당신의 성장과 팀의 변화를 위한<br />따뜻한 협업 스타일 테스트.</p><h1>팀프로젝트 전<br /><strong>확인해보세요!</strong></h1><Link href="/survey" className="start-button">테스트 시작하기 <span>→</span></Link><button className="result-button" onClick={() => setActiveTab("results")}>기존 팀 분석 결과 불러오기 <span>↻</span></button><div className="welcome-links"><button onClick={() => setActiveTab("survey")}>▣ 설문 문항 미리보기</button><i /><button onClick={() => setActiveTab("types")}>▦ 16유형 미리보기</button></div></div></div></article>
    <article className="workspace-card" aria-label="TMTI 미리보기"><aside className="workspace-nav"><b>TMTI+</b>{tabs.map((tab) => <button key={tab.id} className={activeTab === tab.id ? "nav-active" : ""} onClick={() => setActiveTab(tab.id)}><span aria-hidden="true">{tab.icon}</span>{tab.label}</button>)}</aside><div className="workspace-content">{activeTab === "home" && <HomePanel />}{activeTab === "survey" && <SurveyPanel />}{activeTab === "types" && <TypesPanel />}{activeTab === "results" && <ResultsPanel />}</div></article>
  </section></main>;
}

function HomePanel() { return <><p className="workspace-greeting">새로운 팀 분석을 시작해볼까요?</p><div className="workspace-start"><span className="clipboard">✓</span><div><h2>새로운 팀 분석 시작</h2><p>팀프로젝트 전, 서로의 협업 방식을 살펴보세요.</p></div><Link href="/survey">테스트 시작하기 <span>→</span></Link></div><div className="workspace-steps"><p>테스트는 이렇게 진행돼요</p><ol><li><b>1</b> 24개 문항에 답하기</li><li><b>2</b> 팀의 협업 방식 살펴보기</li><li><b>3</b> 결과를 바탕으로 대화 시작하기</li></ol></div></> }
function SurveyPanel() { return <section className="tab-panel" aria-labelledby="survey-heading"><header className="tab-heading"><div><p>설문 문항 미리보기</p><h2 id="survey-heading">01 <span>/ 24</span></h2></div><Link href="/survey">전체 문항 보기 →</Link></header><div className="tab-question"><p className="quote-mark">“</p><h3>새로운 과제를 받았을 때,<br />나는 어떻게 시작하는 편인가?</h3><p>본인의 평소 모습에 가장 가까운 답을 골라주세요.</p><div className="tab-scale">{["매우 아니다", "아니다", "보통이다", "그렇다", "매우 그렇다"].map((label, index) => <span key={label}><b>{index + 1}</b>{label}</span>)}</div></div></section> }
function TypesPanel() { return <section className="tab-panel" aria-labelledby="types-heading"><header className="tab-heading"><div><p>16유형 미리보기</p><h2 id="types-heading">협업 스타일 16가지</h2></div></header><p className="type-description">계획성·주도성·갈등 대응·소통 직접성의 조합으로 팀 안에서의 협업 방식을 살펴봅니다.</p><div className="type-grid">{typeCodes.map((type, index) => <span key={type} className={`type-chip chip-${index % 4}`}>{type}</span>)}</div></section> }
function ResultsPanel() { return <section className="tab-panel result-empty" aria-labelledby="results-heading"><div className="result-empty-mark">◷</div><p>분석 결과</p><h2 id="results-heading">아직 불러올 결과가 없어요.</h2><span>테스트를 완료한 뒤 팀 분석 결과를 이곳에서 확인할 수 있습니다.</span><Link href="/survey">테스트 시작하기 →</Link></section> }

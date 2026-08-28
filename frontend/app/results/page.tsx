"use client";

import Image from "next/image";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { scorePersonal, scoreTeam, type Responses } from "@/lib/scoring";

type AxisKey = "plan" | "drive" | "conflict" | "communication";
type Personal = {
  displayName: string;
  result: {
    code: string | null;
    type: {
      alias: string;
      strength: string;
      caution: string;
      role: string;
    } | null;
    axes: Record<
      AxisKey,
      { label: string; ratio: number; state: string; pole: string | null }
    >;
  };
};
type Team = {
  faultline: string;
  frictions: string[];
  axisScores: Record<AxisKey, number>;
};
type DemoResultSession = {
  displayName: string;
  teamName: string;
  responses: Responses;
};
const demoResultStorageKey = "tmti-demo-result";
const demoQuestionKeys = ["P1", "P2", "P3", "P4", "P5", "P6", "L1", "L2", "L3", "L4", "L5", "L6", "C1", "C2", "C3", "C4", "C5", "C6", "D1", "D2", "D3", "D4", "D5", "D6"];

function createDemoResponses(): Responses {
  return Object.fromEntries(demoQuestionKeys.map((key, index) => [key, [4, 3, 5, 2, 4, 3][index % 6]])) as Responses;
}

const axisOrder: AxisKey[] = ["plan", "drive", "conflict", "communication"];
const axisMeta: Record<
  AxisKey,
  { high: string; low: string; color: string; light: string }
> = {
  plan: {
    high: "계획을 먼저 세움",
    low: "일단 시작해 봄",
    color: "#e4a642",
    light: "#fff7e8",
  },
  drive: {
    high: "앞에서 이끔",
    low: "뒤에서 받쳐 줌",
    color: "#ed846d",
    light: "#fff2ee",
  },
  conflict: {
    high: "문제를 바로 짚음",
    low: "관계를 먼저 조율함",
    color: "#8ca78b",
    light: "#f0f6ee",
  },
  communication: {
    high: "결론부터 말함",
    low: "배경부터 설명함",
    color: "#84a7c4",
    light: "#f0f6fb",
  },
};

export default function ResultsPage() {
  const [personal, setPersonal] = useState<Personal | null>(null);
  const [team, setTeam] = useState<Team | null>(null);
  const [view, setView] = useState<"personal" | "team">("personal");
  const [error, setError] = useState("");
  const { teamCode, memberId, demo } = useMemo(() => {
    if (typeof window === "undefined")
      return { teamCode: "", memberId: "", demo: false };
    const params = new URLSearchParams(window.location.search);
    return {
      teamCode: params.get("team") ?? "",
      memberId: params.get("member") ?? "",
      demo: params.get("demo") === "1",
    };
  }, []);

  useEffect(() => {
    if (demo) {
      try {
        const saved = JSON.parse(
          window.sessionStorage.getItem(demoResultStorageKey) ?? "null",
        ) as DemoResultSession | null;
        const responses = saved?.responses ?? createDemoResponses();
        const displayName = saved?.displayName || "나";
        const teammateResponses = Object.fromEntries(
          Object.entries(responses).map(([key, value], index) => [
            key,
            Math.max(
              1,
              Math.min(
                5,
                value + (index % 3 === 0 ? 1 : index % 3 === 1 ? -1 : 0),
              ),
            ),
          ]),
        ) as Responses;
        setPersonal({
          displayName,
          result: scorePersonal(responses),
        });
        setTeam(
          scoreTeam([
            {
              id: "me",
              displayName,
              responses,
            },
            {
              id: "demo-teammate",
              displayName: "팀원",
              responses: teammateResponses,
            },
          ]),
        );
      } catch {
        setError("결과를 준비하지 못했어요. 새로고침해 다시 열어 주세요.");
      }
      return;
    }
    if (!teamCode || !memberId) return;
    Promise.all([
      fetch(`/api/teams/${teamCode}?view=personal&memberId=${memberId}`).then(
        async (response) => (response.ok ? response.json() : Promise.reject()),
      ),
      fetch(`/api/teams/${teamCode}?view=team`).then(async (response) =>
        response.ok ? response.json() : Promise.reject(),
      ),
    ])
      .then(([personalData, teamData]) => {
        setPersonal(personalData);
        setTeam(teamData);
      })
      .catch(() =>
        setError("아직 팀 결과를 준비하고 있어요. 잠시 후 다시 확인해 주세요."),
      );
  }, [demo, memberId, teamCode]);

  if ((!demo && (!teamCode || !memberId)) || error)
    return (
      <ResultShell>
        <section className="result-message">
          <Image src="/duck-face-wink.png" alt="" width={110} height={110} />
          <h1>{error || "결과를 확인할 정보를 찾지 못했어요."}</h1>
          <Link href="/" className="button-next">
            홈으로
          </Link>
        </section>
      </ResultShell>
    );
  if (!personal || !team)
    return (
      <ResultShell>
        <section className="result-message">
          <div className="result-loader" />
          <p>팀의 협업 결과를 정리하고 있어요.</p>
        </section>
      </ResultShell>
    );

  return (
    <ResultShell>
      <section className="result-tabs" aria-label="결과 보기 방식">
        <button
          className={view === "personal" ? "active" : ""}
          onClick={() => setView("personal")}
        >
          개인 결과
        </button>
        <button
          className={view === "team" ? "active" : ""}
          onClick={() => setView("team")}
        >
          우리 팀 분석
        </button>
      </section>
      {view === "personal" ? (
        <PersonalResult personal={personal} onTeam={() => setView("team")} />
      ) : (
        <TeamResult
          team={team}
          onPersonal={() => setView("personal")}
          demo={demo}
        />
      )}
    </ResultShell>
  );
}

function ResultShell({ children }: { children: React.ReactNode }) {
  return (
    <main className="survey-shell results-shell">
      <nav className="survey-nav">
        <Link className="survey-home" href="/" aria-label="홈으로">
          ⌂
        </Link>
        <Image
          className="survey-brand-image"
          src="/tmti-survey-logo.png"
          alt="TMTI"
          width={220}
          height={124}
          priority
        />
      </nav>
      {children}
    </main>
  );
}

function PersonalResult({
  personal,
  onTeam,
}: {
  personal: Personal;
  onTeam: () => void;
}) {
  const type = personal.result.type;
  const axes = personal.result.axes;
  return (
    <section className="result-report personal-report survey-card-enter">
      <header className="personal-hero">
        <div>
          <p className="result-kicker">{personal.displayName}님의 협업 경향</p>
          <h1>{type ? type.alias : "나만의 협업 균형"}</h1>
          <span>
            {type && personal.result.code
              ? `${personal.result.code} · 네 가지 축이 보여 주는 현재의 일하는 방식이에요.`
              : "네 가지 축 중 일부가 한쪽으로 뚜렷하지 않아요. 상황에 따라 유연하게 움직이는 편이에요."}
          </span>
        </div>
        <Image
          src="/duck-face-sparkle.png"
          alt="기쁜 표정의 TMTI 오리"
          width={132}
          height={132}
          priority
        />
      </header>
      <section className="personal-overview" aria-labelledby="radar-title">
        <div className="radar-copy">
          <p>네 가지 협업 축</p>
          <h2 id="radar-title">한쪽이 좋다는 뜻은 아니에요.</h2>
          <span>
            팀에서 어떤 방식이 편한지, 서로 어떻게 맞춰 갈지 확인하는
            지도입니다.
          </span>
          <div className="radar-legend">
            {axisOrder.map((axis) => (
              <span key={axis}>
                <i style={{ background: axisMeta[axis].color }} />
                {axes[axis].label}
              </span>
            ))}
          </div>
        </div>
        <RadarChart axes={axes} />
      </section>
      <section className="axis-map" aria-label="협업 축별 위치">
        <header>
          <div>
            <p>나의 협업 지도</p>
            <h2>각 축에서 편한 방향</h2>
          </div>
          <span>상황에 따라 달라질 수 있어요</span>
        </header>
        {axisOrder.map((axis) => (
          <AxisPosition key={axis} axis={axis} score={axes[axis]} />
        ))}
      </section>
      <section className="personal-actions" aria-label="협업 제안">
        <article className="insight-strength">
          <span>잘 발휘되는 점</span>
          <p>
            {type?.strength ??
              "한쪽에 고정되지 않아, 팀 상황에 맞춰 역할을 조정할 수 있어요."}
          </p>
        </article>
        <article className="insight-caution">
          <span>함께 맞춰 볼 점</span>
          <p>
            {type?.caution ??
              "내가 편한 방식과 다른 팀원의 방식이 있을 수 있음을 먼저 확인해 보세요."}
          </p>
        </article>
        <article className="insight-role">
          <span>잘 맞는 자리</span>
          <p>
            {type?.role ??
              "회의에서 서로의 방식과 필요한 역할을 함께 정해 보세요."}
          </p>
        </article>
      </section>
      <button className="result-team-link" onClick={onTeam}>
        우리 팀 분석 보기 <b>→</b>
      </button>
    </section>
  );
}

function RadarChart({ axes }: { axes: Personal["result"]["axes"] }) {
  const center = 140;
  const radius = 104;
  const points = axisOrder.map((axis, index) => {
    const angle = -Math.PI / 2 + (index * Math.PI) / 2;
    const length = Math.max(18, axes[axis].ratio * radius);
    return [
      round(center + Math.cos(angle) * length),
      round(center + Math.sin(angle) * length),
    ] as const;
  });
  const polygon = points.map(([x, y]) => `${x},${y}`).join(" ");
  const grid = (scale: number) =>
    axisOrder
      .map((_, index) => {
        const angle = -Math.PI / 2 + (index * Math.PI) / 2;
        return `${round(center + Math.cos(angle) * radius * scale)},${round(center + Math.sin(angle) * radius * scale)}`;
      })
      .join(" ");
  return (
    <div
      className="radar-chart"
      role="img"
      aria-label="계획성, 주도성, 갈등 대응, 소통 직접성의 개인 협업 경향 그래프"
    >
      <svg viewBox="0 0 280 280" aria-hidden="true">
        <polygon className="radar-grid" points={grid(1)} />
        <polygon className="radar-grid radar-grid-inner" points={grid(0.5)} />
        {axisOrder.map((_, index) => {
          const angle = -Math.PI / 2 + (index * Math.PI) / 2;
          return (
            <line
              key={index}
              x1={center}
              y1={center}
              x2={center + Math.cos(angle) * radius}
              y2={center + Math.sin(angle) * radius}
            />
          );
        })}
        <polygon className="radar-shape" points={polygon} />
        {points.map(([x, y], index) => (
          <circle
            key={axisOrder[index]}
            cx={x}
            cy={y}
            r="5"
            style={{ fill: axisMeta[axisOrder[index]].color }}
          />
        ))}
      </svg>
      {axisOrder.map((axis, index) => (
        <span
          key={axis}
          className={`radar-label label-${index}`}
          style={{ color: axisMeta[axis].color }}
        >
          {axes[axis].label}
        </span>
      ))}
    </div>
  );
}

function AxisPosition({
  axis,
  score,
}: {
  axis: AxisKey;
  score: Personal["result"]["axes"][AxisKey];
}) {
  const meta = axisMeta[axis];
  const position = Math.max(6, Math.min(94, score.ratio * 100));
  return (
    <article
      className="axis-position"
      style={
        {
          "--axis": meta.color,
          "--axis-light": meta.light,
        } as React.CSSProperties
      }
    >
      <div className="axis-position-title">
        <b>{score.label}</b>
        <span>
          {score.pole
            ? `${score.pole} 쪽이 조금 더 편해요`
            : "두 방향을 고르게 활용해요"}
        </span>
      </div>
      <div className="axis-poles">
        <span>{meta.low}</span>
        <span>{meta.high}</span>
      </div>
      <div className="axis-line">
        <i style={{ left: `${position}%` }} aria-hidden="true" />
      </div>
    </article>
  );
}

function TeamResult({
  team,
  onPersonal,
  demo,
}: {
  team: Team;
  onPersonal: () => void;
  demo: boolean;
}) {
  return (
    <section className="result-report survey-card-enter">
      <header className="personal-hero team-hero">
        <div>
          <p className="result-kicker">
            {demo ? "시연용 팀 분석" : "우리 팀의 협업 지도"}
          </p>
          <h1>함께 맞춰 갈 부분</h1>
          <span>
            {demo
              ? "현재 기기의 응답을 바탕으로 만든 시연 결과예요. 실제 팀원 응답이 모이면 팀 결과로 바뀝니다."
              : "서로의 답을 평가하지 않고, 시작 전에 맞출 행동을 살펴봐요."}
          </span>
        </div>
        <Image
          src="/duck-face-smile.png"
          alt="웃는 표정의 TMTI 오리"
          width={122}
          height={122}
        />
      </header>
      <section className="axis-grid">
        {axisOrder.map((axis) => (
          <article key={axis}>
            <b>
              {axisMeta[axis] &&
                {
                  plan: "계획성",
                  drive: "주도성",
                  conflict: "갈등 대응",
                  communication: "소통 직접성",
                }[axis]}
            </b>
            <div>
              <i style={{ width: `${team.axisScores[axis] * 100}%` }} />
            </div>
            <span>팀의 조정 상태</span>
          </article>
        ))}
      </section>
      <section className="insight-grid">
        <article>
          <b>먼저 합의할 지점</b>
          <p>
            {team.frictions.length
              ? team.frictions.join(" ")
              : "현재는 큰 방식 차이가 보이지 않아요. 맡을 일과 의사결정 기준부터 정해보세요."}
          </p>
        </article>
        <article>
          <b>첫 회의에서 물어볼 질문</b>
          <p>
            누가 최종 결정을 정리할까요?
            <br />
            일정이 바뀌면 어디에 먼저 공유할까요?
            <br />
            의견이 다를 때 어떤 방식으로 말할까요?
          </p>
        </article>
      </section>
      <button className="result-team-link" onClick={onPersonal}>
        내 협업 스타일 보기 <b>→</b>
      </button>
    </section>
  );
}

function round(value: number) {
  return Number(value.toFixed(1));
}

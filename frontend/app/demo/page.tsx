"use client";

import Image from "next/image";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

/**
 * 시연/발표용 페이지.
 * 24문항을 손으로 누르지 않고, 프리셋 응답으로 실제 백엔드(54.64.89.202)에
 * 세션 생성 → 팀원 참여 → 설문 제출 → 팀 분석까지 돌린 뒤 /results 로 이동한다.
 *
 * 실제 설문 화면(/survey)은 손대지 않는다. 이 페이지는 완전히 독립적이다.
 */

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "/backend/api";
const SESSION_KEY = "tmti-session-id";

const GROUPS = [
  {
    key: "planning",
    title: "계획성",
    items: [
      ["P1", "새 일을 받으면 전체 순서를 먼저 그린 다음 착수한다."],
      ["P2", "마감이 다가오면 남은 일을 쪼개 하루치로 나눈다."],
      ["P3", "발표 자료를 만들 때 목차를 먼저 짜고 칸을 채운다."],
      ["P4", "일정이 틀어지면 지금 할 수 있는 것부터 처리하며 계획을 갱신한다."],
      ["P5", "되돌릴 수 있는 결정이면 먼저 정하고 확인은 나중에 한다."],
      ["P6", "작업 공간 규칙은 실제로 불편해진 시점에 만든다."],
    ],
  },
  {
    key: "agency",
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
    key: "conflict",
    title: "갈등 대응",
    items: [
      ["C1", "팀원 결과물이 아쉬우면 그 자리에서 짚는다."],
      ["C2", "작업에서 실수가 나오면 원인을 바로 짚는다."],
      ["C3", "같은 문제가 또 생기면 규칙을 바꾸자고 공식적으로 제기한다."],
      ["C4", "의견이 갈리면 접점을 찾아 좁히는 편이다."],
      ["C5", "팀원 둘이 부딪히면 감정이 상하지 않게 사이를 조율한다."],
      ["C6", "내 방식과 팀 방식이 다르면 팀 방식을 따르고 필요하면 나중에 제안한다."],
    ],
  },
  {
    key: "communication",
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

const SCALE: [number, string][] = [
  [1, "매우 아니다"],
  [2, "아니다"],
  [3, "중간"],
  [4, "그렇다"],
  [5, "매우 그렇다"],
];

// scorer.py 기준: 각 축 6문항 중 앞 3개 정방향, 뒤 3개 역방향.
// 극단 pole 을 만들려면 정방향은 높게, 역방향은 낮게 준다.
type Pole = "high" | "low" | "neutral";
const AXIS_BLOCK: Record<Pole, number[]> = {
  high: [5, 5, 4, 1, 2, 1],
  low: [1, 2, 2, 5, 4, 5],
  neutral: [3, 3, 3, 3, 3, 3],
};
type Poles = { planning: Pole; agency: Pole; conflict: Pole; communication: Pole };
type Member = { name: string; poles: Poles };

const POLE_LABEL: Record<string, Record<Pole, string>> = {
  planning: { high: "계획형", low: "적응형", neutral: "중립" },
  agency: { high: "주도형", low: "지원형", neutral: "중립" },
  conflict: { high: "직면형", low: "조율형", neutral: "중립" },
  communication: { high: "직설형", low: "배려형", neutral: "중립" },
};

function memberAnswers(p: Poles): number[] {
  return [
    ...AXIS_BLOCK[p.planning],
    ...AXIS_BLOCK[p.agency],
    ...AXIS_BLOCK[p.conflict],
    ...AXIS_BLOCK[p.communication],
  ];
}

type Preset = { id: string; label: string; blurb: string; members: Member[] };

const PRESETS: Preset[] = [
  {
    id: "planner",
    label: "계획 완벽주의 팀",
    blurb: "네 명 모두 계획형. 일정표부터 나오는 팀.",
    members: [
      { name: "나", poles: { planning: "high", agency: "neutral", conflict: "low", communication: "low" } },
      { name: "민준", poles: { planning: "high", agency: "high", conflict: "neutral", communication: "high" } },
      { name: "서연", poles: { planning: "high", agency: "low", conflict: "low", communication: "neutral" } },
      { name: "도윤", poles: { planning: "high", agency: "neutral", conflict: "high", communication: "low" } },
    ],
  },
  {
    id: "driver",
    label: "추진력 폭발 팀",
    blurb: "세 명 다 주도형. 말 나오면 이미 만들고 있는 팀.",
    members: [
      { name: "나", poles: { planning: "neutral", agency: "high", conflict: "high", communication: "high" } },
      { name: "지호", poles: { planning: "high", agency: "high", conflict: "neutral", communication: "high" } },
      { name: "하은", poles: { planning: "low", agency: "high", conflict: "high", communication: "neutral" } },
    ],
  },
  {
    id: "diverse",
    label: "다양성 팀",
    blurb: "축마다 성향이 갈리는 팀. 균형 조합.",
    members: [
      { name: "나", poles: { planning: "high", agency: "high", conflict: "high", communication: "high" } },
      { name: "민준", poles: { planning: "low", agency: "low", conflict: "low", communication: "low" } },
      { name: "서연", poles: { planning: "high", agency: "low", conflict: "neutral", communication: "low" } },
      { name: "도윤", poles: { planning: "neutral", agency: "high", conflict: "low", communication: "high" } },
    ],
  },
];

const POLE_CHOICES: Pole[] = ["high", "low", "neutral"];
const RANDOM_NAMES = ["나", "민준", "서연", "도윤"];

function randomPreset(): Preset {
  const pick = () => POLE_CHOICES[Math.floor(Math.random() * POLE_CHOICES.length)];
  return {
    id: "random",
    label: "랜덤 팀",
    blurb: "매번 무작위로 뽑히는 4인 팀.",
    members: RANDOM_NAMES.map((name) => ({
      name,
      poles: { planning: pick(), agency: pick(), conflict: pick(), communication: pick() },
    })),
  };
}

async function api<T>(method: string, path: string, body?: unknown, bearer?: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method,
    credentials: "same-origin",
    headers: {
      "content-type": "application/json",
      ...(bearer ? { Authorization: `Bearer ${bearer}` } : {}),
    },
    body: body === undefined || body === null ? undefined : JSON.stringify(body),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${method} ${path} → ${res.status} ${text.slice(0, 200)}`);
  }
  return res.status === 204 ? (null as T) : ((await res.json()) as T);
}

export default function DemoPage() {
  const [presetId, setPresetId] = useState("planner");
  const [randomSeed, setRandomSeed] = useState(0);
  const [busy, setBusy] = useState(false);
  const [log, setLog] = useState<string[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    const q = new URLSearchParams(window.location.search).get("preset");
    if (q && (q === "random" || PRESETS.some((p) => p.id === q))) setPresetId(q);
  }, []);

  const preset = useMemo(
    () => (presetId === "random" ? randomPreset() : PRESETS.find((p) => p.id === presetId) ?? PRESETS[0]),
    [presetId, randomSeed],
  );

  const me = preset.members[0];
  const myAnswers = memberAnswers(me.poles);

  const run = async () => {
    setBusy(true);
    setError("");
    setLog([]);
    const push = (line: string) => setLog((prev) => [...prev, line]);
    try {
      const n = preset.members.length;
      push(`세션 생성 (목표 인원 ${n}명)…`);
      const session = await api<{ session_id: string; invite_token: string; host_secret: string }>(
        "POST",
        "/sessions",
        { name: `시연 · ${preset.label}`, expected_member_count: n },
      );

      // "나"를 마지막에 참여시켜 participant_secret 쿠키가 "나" 것으로 남게 한다.
      const joinOrder = [...preset.members.slice(1), preset.members[0]];
      const idBySecret: Record<string, { id: string; secret: string }> = {};
      for (const m of joinOrder) {
        push(`${m.name} 참여 중…`);
        const p = await api<{ participant_id: string; participant_secret: string }>(
          "POST",
          `/invites/${session.invite_token}/participants`,
          { nickname: m.name },
        );
        idBySecret[m.name] = { id: p.participant_id, secret: p.participant_secret };
      }

      for (const m of preset.members) {
        push(`${m.name} 설문 제출 중…`);
        await api(
          "POST",
          `/participants/${idBySecret[m.name].id}/submissions/survey`,
          { answers: memberAnswers(m.poles) },
          idBySecret[m.name].secret,
        );
      }

      push("팀 분석 시작…");
      await api("POST", `/sessions/${session.session_id}/analysis`, null, session.host_secret);

      window.sessionStorage.setItem(SESSION_KEY, session.session_id);
      push("결과 페이지로 이동합니다…");
      window.location.href = `/results?session=${encodeURIComponent(session.session_id)}`;
    } catch (e) {
      setError(e instanceof Error ? e.message : "알 수 없는 오류");
      setBusy(false);
    }
  };

  return (
    <main className="survey-shell">
      <style>{demoCss}</style>
      <nav className="survey-nav" aria-label="시연">
        <Link className="survey-home" href="/" aria-label="홈으로">
          ⌂
        </Link>
        <Image className="survey-brand-image" src="/tmti-survey-logo.png" alt="TMTI" width={220} height={124} priority />
      </nav>

      <section className="survey-card dm-card">
        <div className="dm-head">
          <div>
            <p className="dm-kicker">DEMO · 시연용</p>
            <h1>응답이 채워진 설문</h1>
            <p className="dm-sub">
              24문항을 직접 누르지 않고, 아래 프리셋 응답으로 실제 백엔드에 팀 분석을 돌립니다.
            </p>
          </div>
          <Image src="/duck-face-sparkle.png" alt="" width={104} height={104} priority />
        </div>

        <div className="dm-presets" role="group" aria-label="팀 프리셋">
          {PRESETS.map((p) => (
            <button
              key={p.id}
              type="button"
              className={presetId === p.id ? "active" : ""}
              onClick={() => setPresetId(p.id)}
              disabled={busy}
            >
              <b>{p.label}</b>
              <span>{p.blurb}</span>
            </button>
          ))}
          <button
            type="button"
            className={presetId === "random" ? "active" : ""}
            onClick={() => {
              setPresetId("random");
              setRandomSeed((s) => s + 1);
            }}
            disabled={busy}
          >
            <b>랜덤 팀 ↻</b>
            <span>매번 무작위 4인</span>
          </button>
        </div>

        <div className="dm-roster">
          <p className="dm-label">팀 구성 ({preset.members.length}명)</p>
          <ul>
            {preset.members.map((m) => (
              <li key={m.name}>
                <b>{m.name}</b>
                {(["planning", "agency", "conflict", "communication"] as const).map((axis) => (
                  <span key={axis} data-neutral={m.poles[axis] === "neutral"}>
                    {POLE_LABEL[axis][m.poles[axis]]}
                  </span>
                ))}
              </li>
            ))}
          </ul>
        </div>

        <div className="dm-actions">
          <button className="button-next" onClick={run} disabled={busy}>
            {busy ? "분석 실행 중…" : "이 응답으로 팀 분석 실행 →"}
          </button>
          <Link className="button-muted" href="/survey">
            직접 설문하기
          </Link>
        </div>

        {log.length > 0 && (
          <ol className="dm-log" aria-live="polite">
            {log.map((line, i) => (
              <li key={i}>{line}</li>
            ))}
          </ol>
        )}
        {error && (
          <p className="dm-error" aria-live="polite">
            실행 실패: {error}
          </p>
        )}

        <div className="dm-preview">
          <p className="dm-label">‘{me.name}’의 응답 (미리 채워짐)</p>
          {GROUPS.map((group, gi) => (
            <div className="dm-group" key={group.key}>
              <h2>
                {group.title}
                <small>
                  {POLE_LABEL[group.key][me.poles[group.key as keyof Poles]]}
                </small>
              </h2>
              {group.items.map(([id, text], ii) => {
                const value = myAnswers[gi * 6 + ii];
                return (
                  <article className="dm-q" key={id}>
                    <span className="dm-qnum">{id}</span>
                    <p>{text}</p>
                    <div className="dm-scale" role="img" aria-label={`${id} 응답: ${value}점`}>
                      {SCALE.map(([v, label]) => (
                        <span key={v} className={v === value ? "on" : ""} title={label}>
                          {v}
                        </span>
                      ))}
                    </div>
                  </article>
                );
              })}
            </div>
          ))}
        </div>
      </section>
    </main>
  );
}

const demoCss = `
.dm-card{max-width:860px;margin:0 auto;display:flex;flex-direction:column;gap:22px}
.dm-head{display:flex;align-items:flex-start;justify-content:space-between;gap:18px}
.dm-head h1{margin:6px 0 8px;color:var(--survey-navy,#28324d);font-size:32px;letter-spacing:-1.5px}
.dm-kicker{margin:0;color:#8a93a5;font:800 11px Arial,"Malgun Gothic",sans-serif;letter-spacing:1.4px}
.dm-sub{margin:0;max-width:52ch;color:#6b7280;font-size:14px;line-height:1.6}
.dm-label{margin:0 0 10px;color:#77839a;font:800 11px Arial,"Malgun Gothic",sans-serif;letter-spacing:1px}
.dm-presets{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}
.dm-presets button{display:grid;gap:3px;text-align:left;border:1px solid #dfe4ec;border-radius:13px;padding:13px 15px;background:#fbfcfd;cursor:pointer;transition:border-color .15s,background .15s}
.dm-presets button:hover:not(:disabled){border-color:#b9c4d4}
.dm-presets button.active{border-color:#8ba889;background:#f2f7f0}
.dm-presets button b{color:#2c3a58;font-size:14px}
.dm-presets button span{color:#7b8598;font-size:12px}
.dm-presets button:disabled{opacity:.55;cursor:default}
.dm-roster ul{display:grid;gap:7px;margin:0;padding:0;list-style:none}
.dm-roster li{display:flex;flex-wrap:wrap;align-items:center;gap:6px;border:1px solid #e6eaf0;border-radius:11px;padding:9px 12px;background:#fff}
.dm-roster li b{min-width:44px;color:#2c3a58;font-size:13px}
.dm-roster li span{border-radius:6px;padding:3px 8px;background:#eef2f7;color:#516079;font:700 12px Arial,"Malgun Gothic",sans-serif}
.dm-roster li span[data-neutral="true"]{background:#f4f5f7;color:#9aa2b0}
.dm-actions{display:flex;flex-wrap:wrap;gap:10px;align-items:center}
.dm-actions .button-next{cursor:pointer}
.dm-log{margin:0;padding-left:20px;color:#5f6b80;font-size:13px;line-height:1.9}
.dm-error{margin:0;border:1px solid #e7c3bd;border-radius:10px;padding:10px 12px;background:#fdf3f1;color:#b5544a;font-size:13px;word-break:break-all}
.dm-preview{border-top:1px solid #e9edf2;padding-top:20px}
.dm-group{margin-bottom:18px}
.dm-group h2{display:flex;align-items:baseline;gap:9px;margin:0 0 9px;color:#2c3a58;font-size:16px}
.dm-group h2 small{border-radius:5px;padding:2px 7px;background:#eef2f7;color:#5a6a84;font:700 11px Arial,"Malgun Gothic",sans-serif}
.dm-q{display:grid;grid-template-columns:34px minmax(0,1fr) auto;align-items:center;gap:10px;padding:7px 0;border-bottom:1px dashed #edf0f4}
.dm-qnum{color:#9aa2b0;font:800 11px Arial,sans-serif}
.dm-q p{margin:0;color:#4f5a6f;font-size:13px;line-height:1.5}
.dm-scale{display:flex;gap:4px}
.dm-scale span{display:grid;place-items:center;width:24px;height:24px;border:1px solid #dde2ea;border-radius:7px;color:#aab2c0;font:700 11px Arial,sans-serif}
.dm-scale span.on{border-color:#7f9d7c;background:#7f9d7c;color:#fff}
@media(max-width:640px){
  .dm-presets{grid-template-columns:1fr}
  .dm-head{flex-direction:column-reverse;align-items:flex-start}
  .dm-q{grid-template-columns:30px 1fr;grid-template-rows:auto auto}
  .dm-scale{grid-column:1 / -1}
}
`;

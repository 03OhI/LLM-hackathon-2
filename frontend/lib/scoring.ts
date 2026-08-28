export const AXES = ["plan", "drive", "conflict", "communication"] as const;
export type Axis = (typeof AXES)[number];
export type Responses = Record<string, number>;

type AxisDefinition = {
  label: string;
  high: string;
  low: string;
  positive: string[];
  reverse: string[];
};

export const AXIS_DEFINITIONS: Record<Axis, AxisDefinition> = {
  plan: { label: "계획성", high: "P", low: "A", positive: ["P1", "P2", "P3"], reverse: ["P4", "P5", "P6"] },
  drive: { label: "주도성", high: "L", low: "S", positive: ["L1", "L2", "L3"], reverse: ["L4", "L5", "L6"] },
  conflict: { label: "갈등 대응", high: "C", low: "H", positive: ["C1", "C2", "C3"], reverse: ["C4", "C5", "C6"] },
  communication: { label: "소통 직접성", high: "D", low: "I", positive: ["D1", "D2", "D3"], reverse: ["D4", "D5", "D6"] },
};

export type AxisScore = {
  axis: Axis;
  label: string;
  mean: number;
  ratio: number;
  pole: string | null;
  state: "high" | "low" | "neutral";
};

export type PersonalResult = {
  axes: Record<Axis, AxisScore>;
  code: string | null;
  type: { alias: string; strength: string; caution: string; role: string } | null;
};

const TYPES: Record<string, { alias: string; strength: string; caution: string; role: string }> = {
  PLCD: { alias: "선봉 설계자", strength: "시작이 빠르고 문제가 오래 묵지 않아요.", caution: "속도에 못 따라오는 사람이 말할 틈을 잃을 수 있어요.", role: "전체 일정·결정 주도" },
  PLCI: { alias: "조심스러운 지휘자", strength: "방향을 잡으면서 사람을 안 다치게 해요.", caution: "급할 때 지적이 늦어 문제가 커질 수 있어요.", role: "이해관계가 얽힌 협의" },
  PLHD: { alias: "실무 조정자", strength: "회의가 짧고 결론이 남아요.", caution: "갈등을 덮고 넘어가 나중에 되돌아올 수 있어요.", role: "일정 관리·회의 진행" },
  PLHI: { alias: "배려하는 기획자", strength: "계획이 있으면서 팀 분위기를 안정시켜요.", caution: "말해야 할 때 타이밍을 놓칠 수 있어요.", role: "장기 계획·팀 안정" },
  PSCD: { alias: "냉정한 참모", strength: "남의 계획의 구멍을 정확히 짚어요.", caution: "대안 없이 지적만 하면 팀이 지칠 수 있어요.", role: "검토·품질 확인" },
  PSCI: { alias: "신중한 참모", strength: "준비가 꼼꼼하고 관계를 안 깨요.", caution: "의견이 이미 결정된 뒤에 도착할 수 있어요.", role: "문서·자료 정리" },
  PSHD: { alias: "효율 지원자", strength: "필요한 걸 말없이 준비해둬요.", caution: "자기 몫이 안 보여 기여가 저평가될 수 있어요.", role: "운영·반복 작업" },
  PSHI: { alias: "묵묵한 준비자", strength: "팀이 흔들려도 자리를 지켜요.", caution: "힘든 걸 말하지 않아 혼자 떠안을 수 있어요.", role: "지속적 관리" },
  ALCD: { alias: "돌파형 리더", strength: "막힌 일을 뚫고 결정을 빠르게 만들어요.", caution: "되돌아가는 비용이 커질 수 있어요.", role: "초기 프로토타입·위기 대응" },
  ALCI: { alias: "설득하는 개척자", strength: "새 시도를 하면서 사람을 데려가요.", caution: "방향이 자주 바뀌면 팀이 혼란스러울 수 있어요.", role: "새 영역 탐색" },
  ALHD: { alias: "실행 조율자", strength: "말보다 결과로 흐름을 정리해요.", caution: "왜 그렇게 했는지 공유가 빠질 수 있어요.", role: "빠른 실행·데모" },
  ALHI: { alias: "분위기 메이커", strength: "팀을 움직이게 만드는 힘이 있어요.", caution: "계획이 없으면 막판에 일이 몰릴 수 있어요.", role: "초반 동력·팀 결속" },
  ASCD: { alias: "현장 감시자", strength: "실제로 안 되는 걸 가장 먼저 발견해요.", caution: "전체 그림 없이 지엽적인 문제만 짚을 수 있어요.", role: "테스트·검증" },
  ASCI: { alias: "조용한 관찰자", strength: "문제를 알아채고 상처 없이 전해요.", caution: "신호가 약하면 아무도 알아듣지 못할 수 있어요.", role: "사용자 관점 점검" },
  ASHD: { alias: "군말 없는 실행자", strength: "시키면 바로 되고 뒤탈이 적어요.", caution: "방향을 확인하지 않으면 헛일이 생길 수 있어요.", role: "정해진 작업 처리" },
  ASHI: { alias: "팀의 완충재", strength: "누구와도 붙어서 일을 이어줘요.", caution: "자기 의견이 안 남아 소진될 수 있어요.", role: "여러 파트 연결" },
};

const round = (value: number, places = 2) => Number(value.toFixed(places));
const isResponse = (value: unknown): value is number => Number.isInteger(value) && Number(value) >= 1 && Number(value) <= 5;

export function isCompleteResponseSet(responses: Responses) {
  return Object.values(AXIS_DEFINITIONS).every((definition) => [...definition.positive, ...definition.reverse].every((key) => isResponse(responses[key])));
}

export function scorePersonal(responses: Responses): PersonalResult {
  if (!isCompleteResponseSet(responses)) throw new Error("INCOMPLETE_RESPONSES");

  const axes = {} as Record<Axis, AxisScore>;
  for (const axis of AXES) {
    const definition = AXIS_DEFINITIONS[axis];
    const values = [
      ...definition.positive.map((key) => responses[key]),
      ...definition.reverse.map((key) => 6 - responses[key]),
    ];
    const mean = values.reduce((sum, value) => sum + value, 0) / values.length;
    const ratio = (mean - 1) / 4;
    const state = ratio > 0.6 ? "high" : ratio < 0.4 ? "low" : "neutral";
    axes[axis] = { axis, label: definition.label, mean: round(mean), ratio: round(ratio), pole: state === "neutral" ? null : state === "high" ? definition.high : definition.low, state };
  }

  const code = AXES.map((axis) => axes[axis].pole).every(Boolean) ? AXES.map((axis) => axes[axis].pole).join("") : null;
  return { axes, code, type: code ? TYPES[code] : null };
}

type MemberScore = { id: string; displayName: string; result: PersonalResult };
export type TeamResult = {
  members: MemberScore[];
  axisScores: Record<Axis, number>;
  total: number;
  grade: "A" | "B" | "C";
  faultline: "고르게 섞인 조합" | "한 사람이 겉도는 조합" | "한 가지가 다른 조합" | "두 편으로 갈라진 조합" | "부분적으로 갈린 조합";
  frictions: string[];
};

const average = (numbers: number[]) => numbers.reduce((sum, value) => sum + value, 0) / numbers.length;
const nonNeutral = (scores: AxisScore[]) => scores.filter((score) => score.state !== "neutral").map((score) => score.ratio);

function scoreSimilarity(values: number[]) {
  if (values.length < 2) return 1;
  const gaps: number[] = [];
  for (let first = 0; first < values.length; first += 1) for (let second = first + 1; second < values.length; second += 1) gaps.push(Math.abs(values[first] - values[second]));
  return 1 - average(gaps);
}

function scoreFaultline(rows: number[][]) {
  const count = rows.length;
  if (count < 3) return { label: "한 가지가 다른 조합" as const, multiplier: 1 };
  const means = AXES.map((_, index) => average(rows.map((row) => row[index])));
  const totalVariance = rows.reduce((sum, row) => sum + row.reduce((inner, value, index) => inner + (value - means[index]) ** 2, 0), 0);
  if (totalVariance === 0) return { label: "고르게 섞인 조합" as const, multiplier: 1 };

  let highest = 0;
  let selectedSize = 1;
  let selectedBreadth = 0;
  const limit = 1 << (count - 1);
  for (let mask = 1; mask < limit; mask += 1) {
    const first = rows.filter((_, index) => index === 0 || (mask & (1 << (index - 1))));
    const second = rows.filter((_, index) => !(index === 0 || (mask & (1 << (index - 1)))));
    if (!second.length) continue;
    const between = AXES.reduce((sum, _, index) => sum + first.length * (average(first.map((row) => row[index])) - means[index]) ** 2 + second.length * (average(second.map((row) => row[index])) - means[index]) ** 2, 0);
    const fau = between / totalVariance;
    if (fau > highest) {
      highest = fau;
      selectedSize = first.length;
      selectedBreadth = AXES.filter((_, index) => Math.abs(average(first.map((row) => row[index])) - average(second.map((row) => row[index]))) > 0.05).length / 4;
    }
  }
  const balance = Math.min(selectedSize, count - selectedSize) / Math.max(selectedSize, count - selectedSize);
  const adjusted = highest * selectedBreadth;
  if (highest < 0.35) return { label: "고르게 섞인 조합" as const, multiplier: 1 };
  if (balance <= 0.34) return { label: "한 사람이 겉도는 조합" as const, multiplier: 0.85 };
  if (selectedBreadth <= 0.35) return { label: "한 가지가 다른 조합" as const, multiplier: 1 };
  if (adjusted >= 0.6) return { label: "두 편으로 갈라진 조합" as const, multiplier: 0.75 };
  return { label: "부분적으로 갈린 조합" as const, multiplier: 1 };
}

export function scoreTeam(members: { id: string; displayName: string; responses: Responses }[]): TeamResult {
  if (members.length < 2) throw new Error("NOT_ENOUGH_MEMBERS");
  const scored = members.map((member) => ({ id: member.id, displayName: member.displayName, result: scorePersonal(member.responses) }));
  const values = (axis: Axis) => scored.map((member) => member.result.axes[axis]);
  const planned = nonNeutral(values("plan"));
  const plan = planned.length < 2 ? 0.4 : 0.4 + 0.6 * Math.min(1, (Math.max(...planned) - Math.min(...planned)) / (2 / 3));
  const driveMean = average(values("drive").map((score) => score.ratio));
  const drive = driveMean === 0 ? 0 : driveMean >= 0.95 ? 0.25 : driveMean >= 0.6 ? 0.45 : driveMean >= 0.2 && driveMean <= 0.5 ? 1 : 0.65;
  const conflict = scoreSimilarity(nonNeutral(values("conflict")));
  const communication = scoreSimilarity(nonNeutral(values("communication")));
  const axisScores = { plan: round(plan), drive: round(drive), conflict: round(conflict), communication: round(communication) };
  const faultline = scoreFaultline(scored.map((member) => AXES.map((axis) => member.result.axes[axis].ratio)));
  const rawTotal = plan * 0.2 + drive * 0.35 + conflict * 0.2 + communication * 0.25;
  const total = round(rawTotal * faultline.multiplier);
  let grade: "A" | "B" | "C" = total >= 0.7 ? "A" : total >= 0.45 ? "B" : "C";
  if (drive === 0) grade = "C";
  else if (grade === "A" && Math.min(...Object.values(axisScores)) < 0.5) grade = "B";
  const frictions: string[] = [];
  if (planned.length < 2) frictions.push("계획을 먼저 세우는 방식과 바로 움직이는 방식의 균형을 첫 회의에서 정해보세요.");
  if (scoreSimilarity(nonNeutral(values("conflict"))) <= 0.55) frictions.push("문제를 바로 짚을지, 먼저 조율할지에 대한 약속이 필요해요.");
  if (scoreSimilarity(nonNeutral(values("communication"))) <= 0.55) frictions.push("결론부터 말하는 방식과 배경부터 설명하는 방식의 차이를 확인해보세요.");
  if (drive === 0) frictions.push("방향을 정하고 다음 행동을 확정할 사람을 먼저 정해보세요.");
  return { members: scored, axisScores, total, grade, faultline: faultline.label, frictions: frictions.slice(0, 2) };
}

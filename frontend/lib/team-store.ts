import { mkdir, readFile, writeFile } from "fs/promises";
import path from "path";
import { isCompleteResponseSet, scorePersonal, scoreTeam } from "@/lib/scoring";

export type TeamMember = { id: string; displayName: string; completed: boolean; responses?: Record<string, number> };
export type Team = { code: string; teamName: string; expectedMembers: number; members: TeamMember[]; createdAt: string };
type Store = { teams: Team[] };

const storePath = process.env.TMTI_TEAM_STORE_PATH ?? path.join(process.cwd(), "data", "teams.json");
let queue = Promise.resolve();

async function readStore(): Promise<Store> {
  try { return JSON.parse(await readFile(storePath, "utf8")) as Store; }
  catch { return { teams: [] }; }
}

async function changeStore<T>(change: (store: Store) => T): Promise<T> {
  const task = queue.then(async () => {
    const store = await readStore();
    const result = change(store);
    await mkdir(path.dirname(storePath), { recursive: true });
    await writeFile(storePath, JSON.stringify(store), "utf8");
    return result;
  });
  queue = task.then(() => undefined, () => undefined);
  return task;
}

const id = () => crypto.randomUUID();
const code = () => `TMTI-${crypto.randomUUID().slice(0, 6).toUpperCase()}`;

export async function createTeam(teamName: string, expectedMembers: number, displayName: string) {
  return changeStore((store) => {
    const team: Team = { code: code(), teamName, expectedMembers, createdAt: new Date().toISOString(), members: [{ id: id(), displayName, completed: false }] };
    store.teams.push(team);
    return { team, memberId: team.members[0].id };
  });
}

export async function joinTeam(teamCode: string, displayName: string) {
  return changeStore((store) => {
    const team = store.teams.find((candidate) => candidate.code === teamCode);
    if (!team) throw new Error("TEAM_NOT_FOUND");
    if (team.members.length >= team.expectedMembers) throw new Error("TEAM_FULL");
    if (team.members.some((member) => member.displayName === displayName)) throw new Error("NAME_TAKEN");
    const member = { id: id(), displayName, completed: false };
    team.members.push(member);
    return { team, memberId: member.id };
  });
}

export async function completeTeamMember(teamCode: string, memberId: string, responses: Record<string, number>) {
  return changeStore((store) => {
    const team = store.teams.find((candidate) => candidate.code === teamCode);
    const member = team?.members.find((candidate) => candidate.id === memberId);
    if (!team || !member) throw new Error("MEMBER_NOT_FOUND");
    if (!isCompleteResponseSet(responses)) throw new Error("INCOMPLETE_RESPONSES");
    member.completed = true;
    member.responses = responses;
    return team;
  });
}

export async function getTeam(teamCode: string) {
  const store = await readStore();
  return store.teams.find((team) => team.code === teamCode) ?? null;
}

export function publicStatus(team: Team) {
  return { code: team.code, teamName: team.teamName, expectedMembers: team.expectedMembers, joinedMembers: team.members.length, completedMembers: team.members.filter((member) => member.completed).length, members: team.members.map((member) => ({ displayName: member.displayName, completed: member.completed })), ready: team.members.length === team.expectedMembers && team.members.every((member) => member.completed) };
}

export function personalResult(team: Team, memberId: string) {
  const member = team.members.find((candidate) => candidate.id === memberId);
  if (!member?.completed || !member.responses) throw new Error("RESULT_NOT_READY");
  return { displayName: member.displayName, result: scorePersonal(member.responses) };
}

export function teamResult(team: Team) {
  if (!publicStatus(team).ready) throw new Error("RESULT_NOT_READY");
  return scoreTeam(team.members.map((member) => ({ id: member.id, displayName: member.displayName, responses: member.responses! })));
}

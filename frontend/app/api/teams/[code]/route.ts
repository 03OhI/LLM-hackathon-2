import { NextResponse } from "next/server";
import { completeTeamMember, getTeam, joinTeam, publicStatus } from "@/lib/team-store";

type Context = { params: Promise<{ code: string }> };
export async function GET(_: Request, { params }: Context) { const team = await getTeam((await params).code); return team ? NextResponse.json(publicStatus(team)) : NextResponse.json({ error: "TEAM_NOT_FOUND" }, { status: 404 }); }
export async function POST(request: Request, { params }: Context) {
  const code = (await params).code;
  const body = await request.json();
  try {
    if (body.action === "join") { const result = await joinTeam(code, String(body.displayName ?? "").trim()); return NextResponse.json({ ...publicStatus(result.team), memberId: result.memberId }); }
    if (body.action === "complete") { const team = await completeTeamMember(code, String(body.memberId ?? ""), body.responses ?? {}); return NextResponse.json(publicStatus(team)); }
    return NextResponse.json({ error: "INVALID_ACTION" }, { status: 400 });
  } catch (error) { return NextResponse.json({ error: error instanceof Error ? error.message : "UNKNOWN" }, { status: 400 }); }
}

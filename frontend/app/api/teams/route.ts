import { NextResponse } from "next/server";
import { createTeam, publicStatus } from "@/lib/team-store";

export async function POST(request: Request) {
  const body = await request.json();
  const teamName = String(body.teamName ?? "").trim();
  const displayName = String(body.displayName ?? "").trim();
  const expectedMembers = Number(body.expectedMembers);
  if (!teamName || !displayName || !Number.isInteger(expectedMembers) || expectedMembers < 2 || expectedMembers > 10) return NextResponse.json({ error: "INVALID_INPUT" }, { status: 400 });
  const { team, memberId } = await createTeam(teamName, expectedMembers, displayName);
  return NextResponse.json({ ...publicStatus(team), memberId }, { status: 201 });
}

import { NextResponse } from "next/server";
import { getCard, setStatus, updateKept } from "@/lib/db";
import type { CardStatus } from "@/lib/types";

const STATUSES: CardStatus[] = ["pending", "kept", "discarded"];

export async function GET(_: Request, { params }: { params: Promise<{ id: string }> }) {
  const card = getCard(Number((await params).id));
  return card ? NextResponse.json(card) : NextResponse.json({ error: "not found" }, { status: 404 });
}

export async function PATCH(req: Request, { params }: { params: Promise<{ id: string }> }) {
  const id = Number((await params).id);
  if (!Number.isInteger(id)) return NextResponse.json({ error: "bad id" }, { status: 400 });
  let body: { status?: string; comment?: string | null; userTags?: unknown };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "bad json" }, { status: 400 });
  }
  const comment = typeof body.comment === "string" ? body.comment.slice(0, 500) : body.comment === null ? null : undefined;
  let ok = true;
  if (body.status !== undefined) {
    if (!STATUSES.includes(body.status as CardStatus)) return NextResponse.json({ error: "bad status" }, { status: 400 });
    ok = setStatus(id, body.status as CardStatus, comment ?? null);
  } else {
    const userTags = Array.isArray(body.userTags) ? body.userTags.filter((t): t is string => typeof t === "string") : undefined;
    ok = updateKept(id, { comment, userTags });
  }
  return ok ? NextResponse.json(getCard(id)) : NextResponse.json({ error: "not found" }, { status: 404 });
}

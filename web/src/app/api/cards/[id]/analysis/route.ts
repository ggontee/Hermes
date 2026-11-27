import { NextResponse } from "next/server";
import { queueAnalysis } from "@/lib/db";

export async function POST(req: Request, { params }: { params: Promise<{ id: string }> }) {
  const id = Number((await params).id);
  let question: string | null = null;
  try {
    const body = await req.json();
    if (typeof body?.question === "string") question = body.question.slice(0, 500);
  } catch {}
  const res = queueAnalysis(id, question);
  return res.ok ? NextResponse.json(res, { status: 201 }) : NextResponse.json(res, { status: 409 });
}

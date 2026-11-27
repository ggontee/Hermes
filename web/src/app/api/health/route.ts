import { NextResponse } from "next/server";
import { getDb, pendingCount } from "@/lib/db";

export const dynamic = "force-dynamic";

export function GET() {
  try {
    getDb();
    return NextResponse.json({ ok: true, pending: pendingCount() });
  } catch (e) {
    return NextResponse.json({ ok: false, error: (e as Error).message }, { status: 503 });
  }
}

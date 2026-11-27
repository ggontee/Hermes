import Link from "next/link";
import { notFound } from "next/navigation";
import { getAnalysis, getCard } from "@/lib/db";
import { cardTitle, dateTime } from "@/lib/format";
import { renderMarkdown } from "@/lib/markdown";

export const dynamic = "force-dynamic";

// 경로의 id는 분석 id다.
export default async function AnalysisPage({ params }: { params: Promise<{ id: string }> }) {
  const a = getAnalysis(Number((await params).id));
  if (!a) notFound();
  const card = getCard(a.cardId);
  const tanaBase = process.env.HERMES_TANA_NODE_URL ?? "https://app.tana.inc/?nodeid=";

  return (
    <div>
      <Link href="/kept" className="mb-4 inline-block text-sm text-gray-400">
        ← 보관함
      </Link>
      <h1 className="text-2xl font-bold leading-snug">{a.title ?? "심화 분석"}</h1>
      <div className="mt-3 space-y-1 rounded-xl bg-gray-50 p-3 text-xs text-gray-500 dark:bg-white/5">
        {card ? (
          <p>
            원 카드: <Link href={`/card/${card.id}`} className="text-indigo-600 dark:text-indigo-400">{cardTitle(card)}</Link>
          </p>
        ) : null}
        {a.question ? <p>질문: {a.question}</p> : null}
        <p>
          생성 {dateTime(a.finishedAt ?? a.createdAt)} · 비용 ${a.costUsd.toFixed(3)} · Tana {a.tanaNodeId ? "저장됨" : "저장 전"}
        </p>
      </div>
      {a.status === "failed" ? <p className="mt-4 rounded-xl bg-red-50 p-3 text-sm text-red-600 dark:bg-red-900/20">실패: {a.error}</p> : null}
      {a.status === "queued" || a.status === "running" ? (
        <p className="mt-6 text-center text-gray-400">{a.status === "queued" ? "대기 중입니다." : "분석 중입니다."}</p>
      ) : null}
      {a.contentMd ? <article className="prose-ko mt-5" dangerouslySetInnerHTML={{ __html: renderMarkdown(a.contentMd) }} /> : null}
      {a.tanaNodeId ? (
        <a
          href={`${tanaBase}${a.tanaNodeId}`}
          target="_blank"
          rel="noreferrer"
          className="mt-8 block rounded-xl bg-gray-900 py-3 text-center text-sm font-medium text-white dark:bg-gray-100 dark:text-gray-900"
        >
          Tana에서 열기 ↗
        </a>
      ) : null}
      <p className="mt-4 text-center text-xs text-gray-400">다시 분석은 보관함 항목 메뉴에서 질문을 덧붙여 요청할 수 있습니다.</p>
    </div>
  );
}

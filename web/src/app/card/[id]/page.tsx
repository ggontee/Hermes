import Link from "next/link";
import { notFound } from "next/navigation";
import CardHeader from "@/components/CardHeader";
import DetailActions from "@/components/DetailActions";
import Linkify from "@/components/Linkify";
import LongDetail from "@/components/LongDetail";
import VideoDetail from "@/components/VideoDetail";
import { getCard } from "@/lib/db";

export const dynamic = "force-dynamic";

export default async function CardPage({ params }: { params: Promise<{ id: string }> }) {
  const card = getCard(Number((await params).id));
  if (!card) notFound();
  const notes = card.attachments.filter((a) => a.role === "note");
  const alts = card.attachments.filter((a) => a.role === "alt");

  return (
    <div className="pb-20">
      <Link href={card.status === "kept" ? "/kept" : "/"} className="mb-4 inline-block text-sm text-gray-400">
        ← 뒤로
      </Link>
      <CardHeader card={card} />

      {card.kind === "long" ? (
        <>
          <h1 className="mt-4 text-2xl font-bold leading-snug">{card.titleKo || card.titleOrig}</h1>
          {card.isPreview ? <p className="mt-2 text-xs text-amber-600">유료 글이라 앞부분만 수집했습니다.</p> : null}
          <LongDetail card={card} />
        </>
      ) : card.kind === "video" ? (
        <VideoDetail card={card} />
      ) : (
        <div className="mt-4">
          <p className="whitespace-pre-wrap text-lg leading-relaxed">
            <Linkify text={card.translationKo ?? card.paragraphs.join("\n\n")} />
          </p>
          {card.quoteTranslationKo ? (
            <div className="mt-3 rounded-xl border border-gray-200 p-3 text-sm dark:border-white/10">
              <span className="text-xs text-gray-400">인용</span>
              <p className="mt-1 whitespace-pre-wrap">{card.quoteTranslationKo}</p>
            </div>
          ) : null}
          <h3 className="mt-6 text-sm font-semibold text-gray-500">원문</h3>
          <p className="mt-2 whitespace-pre-wrap text-sm leading-relaxed text-gray-500">
            <Linkify text={card.paragraphs.join("\n\n")} />
          </p>
          <a href={card.url} target="_blank" rel="noreferrer" className="mt-4 inline-block text-sm text-indigo-600 dark:text-indigo-400">
            원문 열기 ↗
          </a>
        </div>
      )}

      {notes.length ? (
        <section className="mt-8 space-y-2">
          <h3 className="text-sm font-semibold text-gray-500">💬 작성자 한마디</h3>
          {notes.map((n, i) => (
            <a key={i} href={n.url} target="_blank" rel="noreferrer" className="block rounded-xl bg-gray-50 p-3 text-sm dark:bg-white/5">
              <span className="text-xs text-gray-400">{n.platform}</span>
              <p className="mt-1 whitespace-pre-wrap">{n.text}</p>
            </a>
          ))}
        </section>
      ) : null}
      {alts.length ? (
        <section className="mt-6">
          <h3 className="text-sm font-semibold text-gray-500">같은 내용, 다른 채널</h3>
          <ul className="mt-2 space-y-1">
            {alts.map((a, i) => (
              <li key={i}>
                <a href={a.url} target="_blank" rel="noreferrer" className="text-sm text-indigo-600 dark:text-indigo-400">
                  {a.platform} ↗
                </a>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
      {card.userComment ? (
        <p className="mt-6 rounded-xl bg-emerald-50 p-3 text-sm dark:bg-emerald-900/20">✎ {card.userComment}</p>
      ) : null}

      <DetailActions card={card} />
    </div>
  );
}

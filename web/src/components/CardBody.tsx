"use client";

import { useState } from "react";
import type { Card } from "@/lib/types";
import { clock } from "@/lib/format";
import CardHeader from "./CardHeader";
import Linkify from "./Linkify";

const stop = {
  onPointerDown: (e: React.PointerEvent) => e.stopPropagation(),
  onClick: (e: React.MouseEvent) => e.stopPropagation(),
};

function Notes({ card }: { card: Card }) {
  const notes = card.attachments.filter((a) => a.role === "note");
  if (!notes.length) return null;
  return (
    <div className="mt-4 space-y-2">
      {notes.map((n, i) => (
        <div key={i} className="rounded-xl bg-gray-50 p-3 text-sm text-gray-600 dark:bg-white/5 dark:text-gray-300">
          <span className="mr-1">💬</span>
          <span className="text-xs text-gray-400">작성자 한마디 · {n.platform}</span>
          <p className="mt-1 whitespace-pre-wrap line-clamp-4">{n.text}</p>
        </div>
      ))}
    </div>
  );
}

function Tags({ tags }: { tags: string[] }) {
  if (!tags.length) return null;
  return (
    <div className="mt-4 flex flex-wrap gap-1.5">
      {tags.map((t) => (
        <span key={t} className="rounded-full bg-gray-100 px-2 py-0.5 text-xs text-gray-500 dark:bg-white/10 dark:text-gray-400">
          #{t}
        </span>
      ))}
    </div>
  );
}

function ShortBody({ card }: { card: Card }) {
  const [orig, setOrig] = useState(false);
  const original = card.paragraphs.join("\n\n");
  const same = card.translationKo?.trim() === original.trim();
  return (
    <>
      <p className="mt-4 whitespace-pre-wrap text-[17px] leading-relaxed text-gray-900 dark:text-gray-100">
        <Linkify text={card.translationKo ?? original} />
      </p>
      {card.quoteTranslationKo ? (
        <div className="mt-3 rounded-xl border border-gray-200 p-3 text-sm text-gray-600 dark:border-white/10 dark:text-gray-300">
          <span className="text-xs text-gray-400">인용</span>
          <p className="mt-1 whitespace-pre-wrap">
            <Linkify text={card.quoteTranslationKo} />
          </p>
        </div>
      ) : null}
      {card.media.length ? (
        <div className={`mt-3 grid gap-1 overflow-hidden rounded-xl ${card.media.length > 1 ? "grid-cols-2" : ""}`}>
          {card.media.slice(0, 4).map((m) => (
            // eslint-disable-next-line @next/next/no-img-element
            <img key={m} src={m} alt="" loading="lazy" className="aspect-video w-full object-cover" draggable={false} />
          ))}
        </div>
      ) : null}
      {!same ? (
        <div className="mt-4">
          <button {...stop} onClick={(e) => (e.stopPropagation(), setOrig((v) => !v))} className="text-sm text-gray-400">
            {orig ? "▾ 원문 접기" : "▸ 원문 보기"}
          </button>
          {orig ? (
            <p className="mt-2 whitespace-pre-wrap text-sm leading-relaxed text-gray-500">
              <Linkify text={original} />
            </p>
          ) : null}
        </div>
      ) : null}
      <Notes card={card} />
    </>
  );
}

function LongBody({ card }: { card: Card }) {
  return (
    <>
      <h2 className="mt-4 text-xl font-bold leading-snug text-gray-900 line-clamp-2 dark:text-gray-50">
        {card.titleKo || card.titleOrig}
      </h2>
      {card.isPreview ? (
        <span className="mt-2 inline-block rounded bg-amber-100 px-1.5 py-0.5 text-xs text-amber-700 dark:bg-amber-900/40 dark:text-amber-300">
          미리보기만 수집됨
        </span>
      ) : null}
      <ul className="mt-4 space-y-2.5">
        {card.summaryKo.map((s, i) => (
          <li key={i} className="flex gap-2 text-[15px] leading-relaxed text-gray-800 dark:text-gray-200">
            <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-violet-400" />
            <span>{s}</span>
          </li>
        ))}
      </ul>
      {card.soWhat ? (
        <p className="mt-4 rounded-xl bg-violet-50 p-3 text-sm leading-relaxed text-violet-900 dark:bg-violet-900/20 dark:text-violet-200">
          <span className="font-semibold">왜 중요한가 </span>
          {card.soWhat}
        </p>
      ) : null}
      <Tags tags={card.tags} />
      <Notes card={card} />
    </>
  );
}

export function thumbnail(videoId: string | null): string | null {
  return videoId ? `https://i.ytimg.com/vi/${videoId}/hqdefault.jpg` : null;
}

function VideoBody({ card }: { card: Card }) {
  const thumb = thumbnail(card.videoId);
  const top = (card.top3.length ? card.top3.map((i) => card.sections[i]).filter(Boolean) : card.sections).slice(0, 3);
  return (
    <>
      {thumb ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={thumb} alt="" className="mt-3 aspect-video w-full rounded-xl object-cover" draggable={false} />
      ) : null}
      <p className="mt-2 text-xs text-gray-400 line-clamp-1">{card.titleOrig}</p>
      <h2 className="mt-2 text-lg font-bold leading-snug text-gray-900 dark:text-gray-50">{card.oneliner}</h2>
      {card.fromDescription ? (
        <span className="mt-2 inline-block rounded bg-amber-100 px-1.5 py-0.5 text-xs text-amber-700 dark:bg-amber-900/40 dark:text-amber-300">
          설명 기반 요약
        </span>
      ) : null}
      <ul className="mt-4 space-y-3">
        {top.map((s, i) => (
          <li key={i} className="flex gap-3 text-sm">
            <span className="w-14 shrink-0 font-mono text-red-500">{clock(s.t)}</span>
            <span className="text-gray-800 dark:text-gray-200">
              <span className="font-semibold">{s.title}</span>
              <span className="text-gray-500"> — {s.summary}</span>
            </span>
          </li>
        ))}
      </ul>
      <Tags tags={card.tags} />
      <Notes card={card} />
    </>
  );
}

export default function CardBody({ card }: { card: Card }) {
  return (
    <div className="p-5">
      <CardHeader card={card} />
      {card.kind === "short" ? <ShortBody card={card} /> : card.kind === "long" ? <LongBody card={card} /> : <VideoBody card={card} />}
    </div>
  );
}

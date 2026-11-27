"use client";

import { useRef, useState } from "react";
import type { Card } from "@/lib/types";
import { clock } from "@/lib/format";

export default function VideoDetail({ card }: { card: Card }) {
  const frame = useRef<HTMLIFrameElement>(null);
  const [showScript, setShowScript] = useState(false);

  // IFrame API 스크립트 없이 postMessage로 seekTo를 보낸다 (enablejsapi=1).
  const seek = (t: number) => {
    const w = frame.current?.contentWindow;
    if (!w) return;
    const cmd = (func: string, args: unknown[] = []) => w.postMessage(JSON.stringify({ event: "command", func, args }), "*");
    cmd("seekTo", [t, true]);
    cmd("playVideo");
    frame.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  return (
    <div className="mt-4">
      {card.videoId ? (
        <iframe
          ref={frame}
          className="aspect-video w-full rounded-xl bg-black"
          src={`https://www.youtube-nocookie.com/embed/${card.videoId}?enablejsapi=1&playsinline=1&rel=0`}
          title={card.titleOrig}
          allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
          allowFullScreen
        />
      ) : (
        <a href={card.url} target="_blank" rel="noreferrer" className="block rounded-xl bg-gray-900 py-3 text-center text-sm text-white">
          영상 열기 ↗
        </a>
      )}
      <p className="mt-3 text-sm text-gray-400">{card.titleOrig}</p>
      <h2 className="mt-1 text-xl font-bold leading-snug">{card.oneliner}</h2>
      {card.fromDescription ? (
        <span className="mt-2 inline-block rounded bg-amber-100 px-1.5 py-0.5 text-xs text-amber-700 dark:bg-amber-900/40 dark:text-amber-300">
          설명 기반 요약
        </span>
      ) : null}

      <h3 className="mt-6 text-sm font-semibold text-gray-500">구간</h3>
      <ul className="mt-2 divide-y divide-gray-100 dark:divide-white/5">
        {card.sections.map((s, i) => (
          <li key={i}>
            <button onClick={() => seek(s.t)} className="flex w-full gap-3 py-3 text-left">
              <span className={`w-16 shrink-0 font-mono text-sm ${card.top3.includes(i) ? "font-bold text-red-500" : "text-red-400"}`}>
                {clock(s.t)}
              </span>
              <span className="text-sm">
                <span className="font-semibold">{s.title}</span>
                <span className="block text-gray-500">{s.summary}</span>
              </span>
            </button>
          </li>
        ))}
      </ul>

      {card.transcript.length ? (
        <div className="mt-6">
          <button onClick={() => setShowScript((v) => !v)} className="text-sm font-semibold text-gray-500">
            {showScript ? "▾" : "▸"} 스크립트 번역 ({card.transcript.length}단락)
          </button>
          {showScript ? (
            <div className="mt-3 space-y-4">
              {card.transcript.map((l, i) => (
                <div key={i} className="flex gap-3">
                  {l.t != null ? (
                    <button onClick={() => seek(l.t!)} className="w-14 shrink-0 text-left font-mono text-xs text-red-400">
                      {clock(l.t)}
                    </button>
                  ) : (
                    <span className="w-14 shrink-0" />
                  )}
                  <p className="text-[15px] leading-relaxed">{l.ko || l.orig}</p>
                </div>
              ))}
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

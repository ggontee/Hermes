"use client";

import { useEffect, useState } from "react";
import type { Card } from "@/lib/types";
import { loadPref, savePref } from "@/lib/client";

const TABS = [
  ["summary", "요약"],
  ["translation", "전문 번역"],
  ["original", "원문"],
] as const;

export default function LongDetail({ card }: { card: Card }) {
  const [tab, setTab] = useState<(typeof TABS)[number][0]>("summary");
  const [side, setSide] = useState(false);
  useEffect(() => setSide(loadPref("sideBySide", false)), []);
  const pairs = card.translationPairs.length
    ? card.translationPairs
    : card.paragraphs.map((p, i) => ({ id: `p${i + 1}`, orig: p, ko: "" }));

  return (
    <div className="mt-5">
      <div className="flex gap-1 rounded-xl bg-gray-100 p-1 dark:bg-white/5">
        {TABS.map(([k, label]) => (
          <button
            key={k}
            onClick={() => setTab(k)}
            className={`flex-1 rounded-lg py-1.5 text-sm ${tab === k ? "bg-white font-semibold shadow-sm dark:bg-white/15" : "text-gray-500"}`}
          >
            {label}
          </button>
        ))}
      </div>

      {tab === "summary" ? (
        <div className="mt-5">
          <ul className="space-y-3">
            {card.summaryKo.map((s, i) => (
              <li key={i} className="flex gap-2 leading-relaxed">
                <span className="mt-2.5 h-1.5 w-1.5 shrink-0 rounded-full bg-violet-400" />
                <span>{s}</span>
              </li>
            ))}
          </ul>
          {card.soWhat ? (
            <p className="mt-5 rounded-xl bg-violet-50 p-4 text-sm leading-relaxed text-violet-900 dark:bg-violet-900/20 dark:text-violet-200">
              <span className="font-semibold">왜 중요한가 </span>
              {card.soWhat}
            </p>
          ) : null}
        </div>
      ) : null}

      {tab === "translation" ? (
        <div className="mt-4">
          <label className="mb-3 flex items-center justify-end gap-2 text-sm text-gray-500">
            원문과 나란히
            <input
              type="checkbox"
              checked={side}
              onChange={(e) => {
                setSide(e.target.checked);
                savePref("sideBySide", e.target.checked);
              }}
              className="h-4 w-4 accent-indigo-600"
            />
          </label>
          {card.translationPairs.length === 0 ? (
            <p className="mb-3 text-sm text-gray-400">전문 번역이 아직 없습니다. 원문만 보여 줍니다.</p>
          ) : null}
          <div className="space-y-4">
            {pairs.map((p) => (
              <div key={p.id}>
                {p.ko ? <p className="leading-[1.8]">{p.ko}</p> : null}
                {side || !p.ko ? <p className="mt-1.5 text-sm leading-relaxed text-gray-400">{p.orig}</p> : null}
              </div>
            ))}
          </div>
        </div>
      ) : null}

      {tab === "original" ? (
        <div className="mt-4">
          <a href={card.url} target="_blank" rel="noreferrer" className="mb-4 block rounded-xl bg-gray-900 py-3 text-center text-sm font-medium text-white dark:bg-gray-100 dark:text-gray-900">
            원문 열기 ↗
          </a>
          {card.titleOrig ? <h2 className="mb-3 text-lg font-bold">{card.titleOrig}</h2> : null}
          <div className="space-y-3 text-[15px] leading-relaxed text-gray-700 dark:text-gray-300">
            {card.paragraphs.map((p, i) => (
              <p key={i}>{p}</p>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}

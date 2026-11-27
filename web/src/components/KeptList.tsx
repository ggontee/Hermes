"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import type { AnalysisSummary, Card } from "@/lib/types";
import { KIND_BADGE, KIND_LABEL, cardTitle, relativeTime } from "@/lib/format";
import { patchCard } from "@/lib/client";
import AnalysisSheet from "./AnalysisSheet";
import CommentModal from "./CommentModal";

const STATUS_LABEL: Record<AnalysisSummary["status"], string> = {
  queued: "대기",
  running: "분석 중",
  done: "완료",
  failed: "실패",
};
const STATUS_STYLE: Record<AnalysisSummary["status"], string> = {
  queued: "bg-gray-100 text-gray-500 dark:bg-white/10",
  running: "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300",
  done: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300",
  failed: "bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300",
};

interface Props {
  cards: Card[];
  allTags: [string, number][];
  analysesLeft: number;
  tanaBase: string | null;
}

export default function KeptList({ cards: initial, allTags, analysesLeft, tanaBase }: Props) {
  const router = useRouter();
  const path = usePathname();
  const params = useSearchParams();
  const [cards, setCards] = useState(initial);
  const [menu, setMenu] = useState<number | null>(null);
  const [commentFor, setCommentFor] = useState<Card | null>(null);
  const [tagFor, setTagFor] = useState<number | null>(null);
  const [tagInput, setTagInput] = useState("");
  const [analyzeFor, setAnalyzeFor] = useState<Card | null>(null);
  const [left, setLeft] = useState(analysesLeft);

  const setParam = (k: string, v: string | null) => {
    const q = new URLSearchParams(params);
    if (v) q.set(k, v);
    else q.delete(k);
    router.replace(q.size ? `${path}?${q}` : path);
  };
  const tag = params.get("tag");
  const kind = params.get("kind") ?? "all";
  const analyzed = params.get("analyzed") === "1";

  const update = (id: number, patch: Partial<Card>) => setCards((cs) => cs.map((c) => (c.id === id ? { ...c, ...patch } : c)));

  const topTags = useMemo(() => allTags.slice(0, 20), [allTags]);

  return (
    <>
      <div className="mb-3 flex flex-wrap gap-1">
        {(["all", "short", "long", "video"] as const).map((k) => (
          <button
            key={k}
            onClick={() => setParam("kind", k === "all" ? null : k)}
            className={`rounded-full px-3 py-1 text-sm ${kind === k ? "bg-gray-900 text-white dark:bg-gray-100 dark:text-gray-900" : "bg-gray-100 text-gray-500 dark:bg-white/10"}`}
          >
            {k === "all" ? "전체" : KIND_LABEL[k]}
          </button>
        ))}
        <button
          onClick={() => setParam("analyzed", analyzed ? null : "1")}
          className={`rounded-full px-3 py-1 text-sm ${analyzed ? "bg-indigo-600 text-white" : "bg-gray-100 text-gray-500 dark:bg-white/10"}`}
        >
          분석 완료
        </button>
      </div>
      {topTags.length ? (
        <div className="mb-4 flex flex-wrap gap-1.5">
          {topTags.map(([t, n]) => (
            <button
              key={t}
              onClick={() => setParam("tag", tag === t ? null : t)}
              className={`rounded-full px-2 py-0.5 text-xs ${tag === t ? "bg-indigo-100 text-indigo-700 dark:bg-indigo-900/50 dark:text-indigo-300" : "text-gray-500"}`}
            >
              #{t} <span className="text-gray-300">{n}</span>
            </button>
          ))}
        </div>
      ) : null}

      {cards.length === 0 ? <p className="py-16 text-center text-gray-400">보관한 카드가 없습니다.</p> : null}

      <ul className="space-y-3">
        {cards.map((c) => (
          <li key={c.id} className="rounded-2xl border border-gray-200 bg-white p-4 dark:border-white/10 dark:bg-[#1b1c1f]">
            <div className="flex items-start gap-2">
              <span className={`mt-0.5 shrink-0 rounded-md px-1.5 py-0.5 text-xs font-semibold ${KIND_BADGE[c.kind]}`}>{KIND_LABEL[c.kind]}</span>
              <Link href={`/card/${c.id}`} className="min-w-0 flex-1">
                <p className="font-semibold leading-snug line-clamp-2">{cardTitle(c)}</p>
                <p className="mt-0.5 text-xs text-gray-400">
                  {c.person} · 보관 {relativeTime(c.decidedAt)}
                </p>
              </Link>
              <button onClick={() => setMenu(menu === c.id ? null : c.id)} className="-mr-1 px-2 text-gray-400" aria-label="메뉴">
                ⋯
              </button>
            </div>
            {c.userComment ? <p className="mt-2 text-sm text-gray-600 dark:text-gray-300">✎ {c.userComment}</p> : null}
            <div className="mt-2 flex flex-wrap items-center gap-1.5">
              {[...c.userTags, ...c.tags.filter((t) => !c.userTags.includes(t))].slice(0, 6).map((t) => (
                <span key={t} className={`text-xs ${c.userTags.includes(t) ? "text-indigo-500" : "text-gray-400"}`}>
                  #{t}
                </span>
              ))}
              {c.analysis ? (
                c.analysis.status === "done" ? (
                  <Link href={`/kept/${c.analysis.id}/analysis`} className={`ml-auto rounded px-1.5 py-0.5 text-xs ${STATUS_STYLE.done}`}>
                    분석 완료 ›
                  </Link>
                ) : (
                  <span className={`ml-auto rounded px-1.5 py-0.5 text-xs ${STATUS_STYLE[c.analysis.status]}`}>
                    분석 {STATUS_LABEL[c.analysis.status]}
                  </span>
                )
              ) : null}
            </div>

            {tagFor === c.id ? (
              <form
                className="mt-3 flex gap-2"
                onSubmit={async (e) => {
                  e.preventDefault();
                  const tags = tagInput.split(/[,\s]+/).map((t) => t.replace(/^#/, "")).filter(Boolean);
                  update(c.id, { userTags: tags });
                  setTagFor(null);
                  await patchCard(c.id, { userTags: tags });
                  router.refresh();
                }}
              >
                <input
                  autoFocus
                  value={tagInput}
                  onChange={(e) => setTagInput(e.target.value)}
                  placeholder="#태그 여러 개는 띄어쓰기로"
                  className="min-w-0 flex-1 rounded-lg border border-gray-200 bg-transparent px-2 py-1 text-sm dark:border-white/10"
                />
                <button className="rounded-lg bg-gray-900 px-3 text-sm text-white dark:bg-gray-100 dark:text-gray-900">저장</button>
              </form>
            ) : null}

            {menu === c.id ? (
              <div className="mt-3 grid grid-cols-2 gap-2 text-sm">
                <button onClick={() => (setCommentFor(c), setMenu(null))} className="rounded-lg bg-gray-100 py-2 dark:bg-white/10">
                  코멘트 수정
                </button>
                <button
                  onClick={() => (setTagFor(c.id), setTagInput(c.userTags.map((t) => `#${t}`).join(" ")), setMenu(null))}
                  className="rounded-lg bg-gray-100 py-2 dark:bg-white/10"
                >
                  태그 편집
                </button>
                <button
                  onClick={() => (setAnalyzeFor(c), setMenu(null))}
                  disabled={c.analysis?.status === "queued" || c.analysis?.status === "running"}
                  className="rounded-lg bg-indigo-50 py-2 font-medium text-indigo-700 disabled:opacity-40 dark:bg-indigo-900/30 dark:text-indigo-300"
                >
                  {c.analysis?.status === "done" ? "다시 분석" : "심화 분석"}
                </button>
                <button
                  onClick={async () => {
                    if (!confirm("보관을 취소할까요? 카드는 버린 것으로 바뀝니다.")) return;
                    setCards((cs) => cs.filter((x) => x.id !== c.id));
                    await patchCard(c.id, { status: "discarded" });
                  }}
                  className="rounded-lg bg-gray-100 py-2 text-red-500 dark:bg-white/10"
                >
                  보관 취소
                </button>
                {c.analysis?.tanaNodeId && tanaBase ? (
                  <a
                    href={`${tanaBase}${c.analysis.tanaNodeId}`}
                    target="_blank"
                    rel="noreferrer"
                    className="col-span-2 rounded-lg bg-gray-100 py-2 text-center dark:bg-white/10"
                  >
                    Tana에서 열기 ↗
                  </a>
                ) : null}
              </div>
            ) : null}
          </li>
        ))}
      </ul>

      <CommentModal
        card={commentFor}
        isOpen={!!commentFor}
        initial={commentFor?.userComment ?? ""}
        confirmLabel={["저장", "코멘트 지우기"]}
        onConfirm={async (comment) => {
          if (!commentFor) return;
          update(commentFor.id, { userComment: comment || null });
          const id = commentFor.id;
          setCommentFor(null);
          await patchCard(id, { comment: comment || null });
        }}
        onCancel={() => setCommentFor(null)}
      />
      <AnalysisSheet
        card={analyzeFor}
        left={left}
        estimateUsd={0.15}
        onClose={() => setAnalyzeFor(null)}
        onQueued={(cardId, id) => {
          update(cardId, { analysis: { id, status: "queued", title: null, tanaNodeId: null, createdAt: new Date().toISOString() } });
          setLeft((n) => Math.max(0, n - 1));
          setAnalyzeFor(null);
        }}
      />
    </>
  );
}
